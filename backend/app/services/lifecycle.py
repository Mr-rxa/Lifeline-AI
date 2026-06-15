"""Incident lifecycle: assignment, acceptance, status advancement, cancellation.

Centralizes the state machine so dispatcher and driver routers stay thin and the
side effects (ambulance status, bed reservation, timestamps, websocket broadcasts,
notifications) happen in exactly one place.
"""

from sqlalchemy.orm import Session

from app import schemas
from app.api._helpers import broadcast_ambulance, broadcast_incident
from app.models import Ambulance, Assignment, Hospital, Incident, utcnow
from app.services.notify import notify
from app.ws import manager

# Forward-only order of incident statuses the driver moves through.
DRIVER_FLOW = ["accepted", "at_pickup", "en_route_hospital", "at_hospital", "completed"]

# incident.status -> ambulance.status
AMB_STATUS = {
    "assigned": "offered",
    "accepted": "en_route_pickup",
    "at_pickup": "at_pickup",
    "en_route_hospital": "en_route_hospital",
    "at_hospital": "at_hospital",
    "completed": "available",
    "cancelled": "available",
}

INCIDENT_TIMESTAMP = {
    "accepted": "accepted_at",
    "at_pickup": "arrived_pickup_at",
    "en_route_hospital": "en_route_hospital_at",
    "at_hospital": "arrived_hospital_at",
    "completed": "completed_at",
}


def _broadcast_hospital(h: Hospital) -> None:
    manager.broadcast("hospital_update", schemas.HospitalOut.model_validate(h).model_dump(mode="json"))


def _reserve_bed(h: Hospital, severity: str) -> None:
    if severity == "critical" and h.available_icu_beds > 0:
        h.available_icu_beds -= 1
    elif h.available_beds > 0:
        h.available_beds -= 1


def _release_bed(h: Hospital, severity: str) -> None:
    if severity == "critical":
        h.available_icu_beds = min(h.available_icu_beds + 1, h.total_icu_beds)
    else:
        h.available_beds = min(h.available_beds + 1, h.total_beds)


def assign(
    db: Session,
    incident: Incident,
    ambulance: Ambulance,
    hospital: Hospital | None,
    eta_seconds: int | None,
    distance_km: float | None,
) -> Assignment:
    incident.assigned_ambulance_id = ambulance.id
    incident.target_hospital_id = hospital.id if hospital else None
    incident.status = "assigned"
    incident.dispatched_at = utcnow()

    ambulance.status = "offered"
    ambulance.current_incident_id = incident.id

    if hospital:
        _reserve_bed(hospital, incident.severity)

    assignment = Assignment(
        incident_id=incident.id,
        ambulance_id=ambulance.id,
        driver_id=ambulance.driver_id,
        hospital_id=hospital.id if hospital else None,
        status="offered",
        eta_seconds=eta_seconds,
        distance_km=distance_km,
    )
    db.add(assignment)
    db.commit()
    db.refresh(incident)
    db.refresh(ambulance)
    db.refresh(assignment)

    broadcast_incident(incident, "incident_update")
    broadcast_ambulance(ambulance)
    if hospital:
        _broadcast_hospital(hospital)
    if ambulance.driver_id:
        notify(
            db,
            title="New assignment",
            message=f"Incident #{incident.id} ({incident.severity}) — {incident.pickup_address or 'pickup'}",
            type="assignment",
            user_id=ambulance.driver_id,
            incident_id=incident.id,
        )
    if hospital:
        notify(
            db,
            title="Incoming patient",
            message=f"Incident #{incident.id} ({incident.severity}) inbound",
            type="incoming",
            role_target="hospital",
            incident_id=incident.id,
        )
    return assignment


def accept(db: Session, incident: Incident, ambulance: Ambulance) -> None:
    incident.status = "accepted"
    incident.accepted_at = utcnow()
    ambulance.status = AMB_STATUS["accepted"]

    active = (
        db.query(Assignment)
        .filter(Assignment.incident_id == incident.id, Assignment.status == "offered")
        .order_by(Assignment.id.desc())
        .first()
    )
    if active:
        active.status = "accepted"
        active.resolved_at = utcnow()
    db.commit()
    db.refresh(incident)
    db.refresh(ambulance)
    broadcast_incident(incident)
    broadcast_ambulance(ambulance)
    notify(db, title="Ambulance accepted", message=f"Incident #{incident.id} accepted by crew",
           type="info", role_target="dispatcher", incident_id=incident.id)


def reject(db: Session, incident: Incident, ambulance: Ambulance) -> None:
    """Driver declines: free the ambulance, release the reserved bed, requeue incident."""
    if incident.target_hospital_id:
        h = db.get(Hospital, incident.target_hospital_id)
        if h:
            _release_bed(h, incident.severity)
            _broadcast_hospital(h)

    active = (
        db.query(Assignment)
        .filter(Assignment.incident_id == incident.id, Assignment.status == "offered")
        .order_by(Assignment.id.desc())
        .first()
    )
    if active:
        active.status = "rejected"
        active.resolved_at = utcnow()

    ambulance.status = "available"
    ambulance.current_incident_id = None
    incident.status = "pending"
    incident.assigned_ambulance_id = None
    incident.target_hospital_id = None
    incident.dispatched_at = None
    db.commit()
    db.refresh(incident)
    db.refresh(ambulance)
    broadcast_incident(incident)
    broadcast_ambulance(ambulance)
    notify(db, title="Assignment declined", message=f"Incident #{incident.id} returned to queue",
           type="warning", role_target="dispatcher", incident_id=incident.id)


def advance(db: Session, incident: Incident, new_status: str) -> None:
    if new_status not in DRIVER_FLOW:
        raise ValueError("Invalid status")
    # Enforce forward-only progression.
    current = incident.status
    if current in DRIVER_FLOW:
        if DRIVER_FLOW.index(new_status) <= DRIVER_FLOW.index(current):
            raise ValueError(f"Cannot move from {current} to {new_status}")
    elif new_status != "accepted":
        raise ValueError(f"Cannot move from {current} to {new_status}")

    incident.status = new_status
    setattr(incident, INCIDENT_TIMESTAMP[new_status], utcnow())

    ambulance = db.get(Ambulance, incident.assigned_ambulance_id) if incident.assigned_ambulance_id else None
    if ambulance:
        ambulance.status = AMB_STATUS[new_status]
        if new_status == "completed":
            ambulance.current_incident_id = None

    db.commit()
    if ambulance:
        db.refresh(ambulance)
    db.refresh(incident)
    broadcast_incident(incident)
    if ambulance:
        broadcast_ambulance(ambulance)

    if new_status == "completed":
        notify(db, title="Incident completed", message=f"Incident #{incident.id} closed",
               type="success", role_target="dispatcher", incident_id=incident.id)


def cancel(db: Session, incident: Incident) -> None:
    if incident.target_hospital_id:
        h = db.get(Hospital, incident.target_hospital_id)
        if h:
            _release_bed(h, incident.severity)
            _broadcast_hospital(h)
    if incident.assigned_ambulance_id:
        amb = db.get(Ambulance, incident.assigned_ambulance_id)
        if amb:
            amb.status = "available"
            amb.current_incident_id = None
            broadcast_ambulance(amb)
    incident.status = "cancelled"
    incident.completed_at = utcnow()
    db.commit()
    db.refresh(incident)
    broadcast_incident(incident)
