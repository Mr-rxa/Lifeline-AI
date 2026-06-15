from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.core.database import get_db
from app.deps import get_current_user, require_roles
from app.models import ROLE_ADMIN, ROLE_DISPATCHER, Ambulance, Hospital, Incident, TrackingHistory, User
from app.services.routing import get_route

router = APIRouter(prefix="/api/tracking", tags=["tracking"])


@router.get("/ambulances")
def live_ambulances(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = (
        db.query(Ambulance)
        .filter(Ambulance.last_lat.isnot(None), Ambulance.last_lon.isnot(None))
        .all()
    )
    return [
        {
            "id": a.id,
            "vehicle_number": a.vehicle_number,
            "type": a.type,
            "lat": a.last_lat,
            "lon": a.last_lon,
            "status": a.status,
            "on_shift": a.on_shift,
            "incident_id": a.current_incident_id,
            "last_update": a.last_update,
        }
        for a in rows
    ]


@router.get("/incident/{incident_id}")
def track_incident(incident_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    # Owner citizen, dispatch staff, assigned driver, or target hospital may track.
    allowed = user.role in (ROLE_ADMIN, ROLE_DISPATCHER) or (
        user.role == "citizen" and inc.citizen_id == user.id
    )
    amb = db.get(Ambulance, inc.assigned_ambulance_id) if inc.assigned_ambulance_id else None
    if not allowed and user.role == "driver" and amb and amb.driver_id == user.id:
        allowed = True
    if not allowed and user.role == "hospital" and inc.target_hospital_id == user.hospital_id:
        allowed = True
    if not allowed:
        raise HTTPException(status_code=403, detail="Not authorized")

    hospital = db.get(Hospital, inc.target_hospital_id) if inc.target_hospital_id else None
    route = None
    if inc.status in ("en_route_hospital", "at_hospital") and hospital:
        route = {"phase": "to_hospital", **get_route(inc.pickup_lat, inc.pickup_lon, hospital.lat, hospital.lon)}
    elif amb and amb.last_lat is not None:
        route = {"phase": "to_pickup", **get_route(amb.last_lat, amb.last_lon, inc.pickup_lat, inc.pickup_lon)}

    return {
        "incident": schemas.IncidentOut.model_validate(inc).model_dump(mode="json"),
        "ambulance": {
            "id": amb.id,
            "vehicle_number": amb.vehicle_number,
            "lat": amb.last_lat,
            "lon": amb.last_lon,
            "status": amb.status,
        }
        if amb
        else None,
        "hospital": schemas.HospitalOut.model_validate(hospital).model_dump(mode="json") if hospital else None,
        "route": route,
    }


@router.get("/history/{ambulance_id}")
def track_history(
    ambulance_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(ROLE_ADMIN, ROLE_DISPATCHER)),
):
    rows = (
        db.query(TrackingHistory)
        .filter(TrackingHistory.ambulance_id == ambulance_id)
        .order_by(TrackingHistory.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [{"lat": r.lat, "lon": r.lon, "speed": r.speed, "timestamp": r.timestamp} for r in reversed(rows)]
