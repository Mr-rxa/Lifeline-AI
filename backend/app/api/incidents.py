from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.api._helpers import incident_dict
from app.core.database import get_db
from app.deps import get_current_user
from app.models import (
    ROLE_ADMIN,
    ROLE_DISPATCHER,
    ROLE_HOSPITAL,
    Ambulance,
    Hospital,
    Incident,
    User,
)
from app.services import lifecycle
from app.services.ai_engine import predict_severity, recommend_ambulances, recommend_hospitals
from app.services.notify import audit
from app.services.routing import get_route
from app.ws import manager

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

ACTIVE = ("pending", "assigned", "accepted", "at_pickup", "en_route_hospital", "at_hospital")
DISPATCH_ROLES = (ROLE_ADMIN, ROLE_DISPATCHER)


def _can_view(user: User, inc: Incident, db: Session) -> bool:
    if user.role in DISPATCH_ROLES:
        return True
    if user.role == "citizen" and inc.citizen_id == user.id:
        return True
    if user.role == "driver":
        amb = db.get(Ambulance, inc.assigned_ambulance_id) if inc.assigned_ambulance_id else None
        return bool(amb and amb.driver_id == user.id)
    if user.role == ROLE_HOSPITAL:
        return inc.target_hospital_id == user.hospital_id
    return False


@router.post("", response_model=schemas.IncidentDetail, status_code=201)
def create_incident(
    payload: schemas.IncidentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    severity, score = predict_severity(payload.emergency_type, payload.description)
    inc = Incident(
        citizen_id=user.id if user.role == "citizen" else None,
        patient_name=payload.patient_name or user.full_name,
        patient_phone=payload.patient_phone or user.phone,
        emergency_type=payload.emergency_type,
        description=payload.description,
        pickup_lat=payload.pickup_lat,
        pickup_lon=payload.pickup_lon,
        pickup_address=payload.pickup_address,
        severity=severity,
        severity_score=score,
        status="pending",
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    audit(db, action="create_incident", actor=user.email, user_id=user.id, entity="incident",
          entity_id=inc.id, detail=f"severity={severity}")
    manager.broadcast("incident_new", incident_dict(inc))
    from app.services.notify import notify

    notify(db, title=f"New {severity} emergency", message=payload.pickup_address or "Pickup requested",
           type="emergency", role_target="dispatcher", incident_id=inc.id)
    return _detail(db, inc)


@router.get("", response_model=list[schemas.IncidentOut])
def list_incidents(
    status: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Incident)
    if status == "active":
        q = q.filter(Incident.status.in_(ACTIVE))
    elif status:
        q = q.filter(Incident.status == status)
    return q.order_by(Incident.created_at.desc()).limit(200).all()


@router.get("/mine", response_model=list[schemas.IncidentOut])
def my_incidents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(Incident)
        .filter(Incident.citizen_id == user.id)
        .order_by(Incident.created_at.desc())
        .all()
    )


@router.get("/{incident_id}", response_model=schemas.IncidentDetail)
def get_incident(incident_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    if not _can_view(user, inc, db):
        raise HTTPException(status_code=403, detail="Not authorized")
    return _detail(db, inc)


@router.get("/{incident_id}/recommendations")
def recommendations(
    incident_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    hospitals = recommend_hospitals(db, inc.pickup_lat, inc.pickup_lon, inc.severity)
    ambulances = recommend_ambulances(db, inc.pickup_lat, inc.pickup_lon)
    return {
        "hospitals": [
            {
                "hospital": schemas.HospitalOut.model_validate(r["hospital"]).model_dump(mode="json"),
                "distance_km": r["distance_km"],
                "eta_seconds": r["eta_seconds"],
                "score": r["score"],
            }
            for r in hospitals
        ],
        "ambulances": [
            {
                "ambulance": schemas.AmbulanceOut.model_validate(r["ambulance"]).model_dump(mode="json"),
                "distance_km": r["distance_km"],
                "eta_seconds": r["eta_seconds"],
            }
            for r in ambulances
        ],
    }


@router.get("/{incident_id}/route")
def incident_route(incident_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    if not _can_view(user, inc, db):
        raise HTTPException(status_code=403, detail="Not authorized")

    amb = db.get(Ambulance, inc.assigned_ambulance_id) if inc.assigned_ambulance_id else None
    hospital = db.get(Hospital, inc.target_hospital_id) if inc.target_hospital_id else None

    # Before patient pickup: ambulance -> pickup. After pickup: pickup -> hospital.
    if inc.status in ("en_route_hospital", "at_hospital") and hospital:
        route = get_route(inc.pickup_lat, inc.pickup_lon, hospital.lat, hospital.lon)
        phase = "to_hospital"
    elif amb and amb.last_lat is not None and amb.last_lon is not None:
        route = get_route(amb.last_lat, amb.last_lon, inc.pickup_lat, inc.pickup_lon)
        phase = "to_pickup"
    else:
        raise HTTPException(status_code=400, detail="No route available yet")
    return {"phase": phase, **route}


@router.post("/{incident_id}/cancel", response_model=schemas.IncidentDetail)
def cancel_incident(incident_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    if user.role not in DISPATCH_ROLES and not (user.role == "citizen" and inc.citizen_id == user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
    if inc.status in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail="Incident already closed")
    lifecycle.cancel(db, inc)
    audit(db, action="cancel_incident", actor=user.email, user_id=user.id, entity="incident", entity_id=inc.id)
    return _detail(db, inc)


def _detail(db: Session, inc: Incident) -> schemas.IncidentDetail:
    data = schemas.IncidentDetail.model_validate(inc)
    return data
