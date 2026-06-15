from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.api._helpers import broadcast_ambulance
from app.core.database import get_db
from app.deps import require_roles
from app.models import ROLE_ADMIN, ROLE_DISPATCHER, Ambulance, Assignment, Hospital, Incident, User, utcnow
from app.services import lifecycle
from app.services.ai_engine import recommend_hospitals
from app.services.geo import eta_seconds_from_distance, haversine_km
from app.services.notify import audit
from app.services.routing import get_route

router = APIRouter(prefix="/api/incidents", tags=["dispatch"])

DISPATCH_ROLES = (ROLE_ADMIN, ROLE_DISPATCHER)


def _pick_hospital(db: Session, inc: Incident, hospital_id: int | None) -> Hospital | None:
    if hospital_id:
        h = db.get(Hospital, hospital_id)
        if not h:
            raise HTTPException(status_code=404, detail="Hospital not found")
        return h
    recs = recommend_hospitals(db, inc.pickup_lat, inc.pickup_lon, inc.severity, limit=1)
    return recs[0]["hospital"] if recs else None


def _eta_to_pickup(amb: Ambulance, inc: Incident) -> tuple[int | None, float | None]:
    if amb.last_lat is None or amb.last_lon is None:
        return None, None
    route = get_route(amb.last_lat, amb.last_lon, inc.pickup_lat, inc.pickup_lon)
    return route["eta_seconds"], route["distance_km"]


@router.post("/{incident_id}/assign", response_model=schemas.IncidentDetail)
def assign(
    incident_id: int,
    payload: schemas.AssignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*DISPATCH_ROLES)),
):
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    if inc.status not in ("pending",):
        raise HTTPException(status_code=400, detail=f"Incident is {inc.status}, not assignable")

    amb = db.get(Ambulance, payload.ambulance_id)
    if not amb:
        raise HTTPException(status_code=404, detail="Ambulance not found")
    if amb.status != "available" or not amb.on_shift:
        raise HTTPException(status_code=409, detail="Ambulance is not available")

    hospital = _pick_hospital(db, inc, payload.hospital_id)
    eta, dist = _eta_to_pickup(amb, inc)
    lifecycle.assign(db, inc, amb, hospital, eta, dist)
    audit(db, action="assign", actor=user.email, user_id=user.id, entity="incident", entity_id=inc.id,
          detail=f"ambulance={amb.id} hospital={hospital.id if hospital else None}")
    return schemas.IncidentDetail.model_validate(inc)


@router.post("/{incident_id}/reassign", response_model=schemas.IncidentDetail)
def reassign(
    incident_id: int,
    payload: schemas.AssignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*DISPATCH_ROLES)),
):
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    if inc.status in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail="Incident already closed")

    new_amb = db.get(Ambulance, payload.ambulance_id)
    if not new_amb:
        raise HTTPException(status_code=404, detail="Ambulance not found")
    if new_amb.id == inc.assigned_ambulance_id:
        raise HTTPException(status_code=400, detail="Already assigned to this ambulance")
    if new_amb.status != "available" or not new_amb.on_shift:
        raise HTTPException(status_code=409, detail="Ambulance is not available")

    # Release the currently assigned ambulance and reserved bed.
    old = db.get(Ambulance, inc.assigned_ambulance_id) if inc.assigned_ambulance_id else None
    if old:
        old.status = "available"
        old.current_incident_id = None
        broadcast_ambulance(old)
    db.query(Assignment).filter(
        Assignment.incident_id == inc.id, Assignment.status.in_(("offered", "accepted"))
    ).update({Assignment.status: "rejected", Assignment.resolved_at: utcnow()}, synchronize_session=False)
    if inc.target_hospital_id:
        old_h = db.get(Hospital, inc.target_hospital_id)
        if old_h:
            lifecycle._release_bed(old_h, inc.severity)
    inc.assigned_ambulance_id = None
    inc.target_hospital_id = None
    inc.status = "pending"
    db.commit()

    hospital = _pick_hospital(db, inc, payload.hospital_id)
    eta, dist = _eta_to_pickup(new_amb, inc)
    lifecycle.assign(db, inc, new_amb, hospital, eta, dist)
    audit(db, action="reassign", actor=user.email, user_id=user.id, entity="incident", entity_id=inc.id,
          detail=f"ambulance={new_amb.id}")
    return schemas.IncidentDetail.model_validate(inc)
