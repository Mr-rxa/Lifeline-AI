from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.api._helpers import broadcast_ambulance
from app.core.database import get_db
from app.deps import require_roles
from app.models import ROLE_DRIVER, Ambulance, Incident, TrackingHistory, User, utcnow
from app.services import lifecycle
from app.ws import manager

router = APIRouter(prefix="/api/driver", tags=["driver"])


def _my_ambulance(db: Session, user: User) -> Ambulance:
    amb = db.query(Ambulance).filter(Ambulance.driver_id == user.id).first()
    if not amb:
        raise HTTPException(status_code=404, detail="No ambulance assigned to this driver")
    return amb


@router.get("/me")
def driver_state(db: Session = Depends(get_db), user: User = Depends(require_roles(ROLE_DRIVER))):
    amb = db.query(Ambulance).filter(Ambulance.driver_id == user.id).first()
    incident = None
    if amb and amb.current_incident_id:
        inc = db.get(Incident, amb.current_incident_id)
        if inc:
            incident = schemas.IncidentDetail.model_validate(inc).model_dump(mode="json")
    return {
        "ambulance": schemas.AmbulanceOut.model_validate(amb).model_dump(mode="json") if amb else None,
        "incident": incident,
    }


@router.post("/shift/start", response_model=schemas.AmbulanceOut)
def start_shift(db: Session = Depends(get_db), user: User = Depends(require_roles(ROLE_DRIVER))):
    amb = _my_ambulance(db, user)
    amb.on_shift = True
    if amb.status in ("offline", "maintenance"):
        amb.status = "available"
    amb.last_update = utcnow()
    db.commit()
    db.refresh(amb)
    broadcast_ambulance(amb)
    return amb


@router.post("/shift/end", response_model=schemas.AmbulanceOut)
def end_shift(db: Session = Depends(get_db), user: User = Depends(require_roles(ROLE_DRIVER))):
    amb = _my_ambulance(db, user)
    if amb.current_incident_id:
        raise HTTPException(status_code=409, detail="Finish the active incident before ending shift")
    amb.on_shift = False
    amb.status = "offline"
    db.commit()
    db.refresh(amb)
    broadcast_ambulance(amb)
    return amb


@router.post("/location", response_model=schemas.AmbulanceOut)
def update_location(
    payload: schemas.LocationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_DRIVER)),
):
    amb = _my_ambulance(db, user)
    amb.last_lat = payload.lat
    amb.last_lon = payload.lon
    amb.last_update = utcnow()
    db.add(
        TrackingHistory(
            ambulance_id=amb.id,
            incident_id=amb.current_incident_id,
            lat=payload.lat,
            lon=payload.lon,
            speed=payload.speed,
        )
    )
    db.commit()
    db.refresh(amb)
    manager.broadcast(
        "ambulance_location",
        {
            "ambulance_id": amb.id,
            "vehicle_number": amb.vehicle_number,
            "lat": amb.last_lat,
            "lon": amb.last_lon,
            "speed": payload.speed,
            "status": amb.status,
            "incident_id": amb.current_incident_id,
        },
    )
    return amb


@router.post("/assignment/accept", response_model=schemas.IncidentDetail)
def accept_assignment(db: Session = Depends(get_db), user: User = Depends(require_roles(ROLE_DRIVER))):
    amb = _my_ambulance(db, user)
    if not amb.current_incident_id:
        raise HTTPException(status_code=400, detail="No assignment to accept")
    inc = db.get(Incident, amb.current_incident_id)
    if not inc or inc.status != "assigned":
        raise HTTPException(status_code=400, detail="No pending assignment")
    lifecycle.accept(db, inc, amb)
    return schemas.IncidentDetail.model_validate(inc)


@router.post("/assignment/reject", response_model=schemas.AmbulanceOut)
def reject_assignment(db: Session = Depends(get_db), user: User = Depends(require_roles(ROLE_DRIVER))):
    amb = _my_ambulance(db, user)
    if not amb.current_incident_id:
        raise HTTPException(status_code=400, detail="No assignment to reject")
    inc = db.get(Incident, amb.current_incident_id)
    if not inc or inc.status != "assigned":
        raise HTTPException(status_code=400, detail="Assignment already accepted or closed")
    lifecycle.reject(db, inc, amb)
    db.refresh(amb)
    return amb


@router.post("/status", response_model=schemas.IncidentDetail)
def update_status(
    payload: schemas.StatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_DRIVER)),
):
    amb = _my_ambulance(db, user)
    if not amb.current_incident_id:
        raise HTTPException(status_code=400, detail="No active incident")
    inc = db.get(Incident, amb.current_incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    try:
        lifecycle.advance(db, inc, payload.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.IncidentDetail.model_validate(inc)
