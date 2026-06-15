from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.api._helpers import broadcast_incident
from app.core.database import get_db
from app.deps import get_current_user, require_roles
from app.models import ROLE_ADMIN, ROLE_HOSPITAL, Hospital, Incident, Resource, User
from app.services.notify import audit
from app.ws import manager

router = APIRouter(prefix="/api/hospitals", tags=["hospitals"])

ACTIVE_STATUSES = ("assigned", "accepted", "en_route_pickup", "at_pickup", "en_route_hospital")


def _can_manage(user: User, hospital_id: int) -> bool:
    return user.role == ROLE_ADMIN or (user.role == ROLE_HOSPITAL and user.hospital_id == hospital_id)


def _broadcast_hospital(h: Hospital) -> None:
    manager.broadcast("hospital_update", schemas.HospitalOut.model_validate(h).model_dump(mode="json"))


@router.get("", response_model=list[schemas.HospitalOut])
def list_hospitals(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Hospital).order_by(Hospital.name).all()


@router.get("/me", response_model=schemas.HospitalOut)
def my_hospital(db: Session = Depends(get_db), user: User = Depends(require_roles(ROLE_HOSPITAL))):
    if not user.hospital_id:
        raise HTTPException(status_code=404, detail="No hospital linked to this operator")
    h = db.get(Hospital, user.hospital_id)
    if not h:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return h


@router.get("/{hospital_id}", response_model=schemas.HospitalOut)
def get_hospital(hospital_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    h = db.get(Hospital, hospital_id)
    if not h:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return h


@router.get("/{hospital_id}/incoming", response_model=list[schemas.IncidentOut])
def incoming_patients(
    hospital_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _can_manage(user, hospital_id):
        raise HTTPException(status_code=403, detail="Not authorized for this hospital")
    return (
        db.query(Incident)
        .filter(Incident.target_hospital_id == hospital_id, Incident.status.in_(ACTIVE_STATUSES))
        .order_by(Incident.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.HospitalOut, status_code=201)
def create_hospital(
    payload: schemas.HospitalCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(ROLE_ADMIN)),
):
    h = Hospital(**payload.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    audit(db, action="create_hospital", actor=admin.email, user_id=admin.id, entity="hospital", entity_id=h.id)
    return h


@router.patch("/{hospital_id}/capacity", response_model=schemas.HospitalOut)
def update_capacity(
    hospital_id: int,
    payload: schemas.HospitalCapacityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _can_manage(user, hospital_id):
        raise HTTPException(status_code=403, detail="Not authorized for this hospital")
    h = db.get(Hospital, hospital_id)
    if not h:
        raise HTTPException(status_code=404, detail="Hospital not found")

    data = payload.model_dump(exclude_none=True)
    for field, value in data.items():
        setattr(h, field, value)
    # Clamp availability to capacity.
    h.available_beds = max(0, min(h.available_beds, h.total_beds))
    h.available_icu_beds = max(0, min(h.available_icu_beds, h.total_icu_beds))
    db.commit()
    db.refresh(h)
    audit(db, action="update_capacity", actor=user.email, user_id=user.id, entity="hospital", entity_id=h.id)
    _broadcast_hospital(h)
    return h


@router.post("/{hospital_id}/resources", response_model=schemas.ResourceOut, status_code=201)
def add_resource(
    hospital_id: int,
    payload: schemas.ResourceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _can_manage(user, hospital_id):
        raise HTTPException(status_code=403, detail="Not authorized for this hospital")
    if not db.get(Hospital, hospital_id):
        raise HTTPException(status_code=404, detail="Hospital not found")
    r = Resource(hospital_id=hospital_id, name=payload.name, total=payload.total, available=payload.available)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.patch("/resources/{resource_id}", response_model=schemas.ResourceOut)
def update_resource(
    resource_id: int,
    payload: schemas.ResourceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = db.get(Resource, resource_id)
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not _can_manage(user, r.hospital_id):
        raise HTTPException(status_code=403, detail="Not authorized for this hospital")
    r.available = max(0, min(payload.available, r.total))
    db.commit()
    db.refresh(r)
    h = db.get(Hospital, r.hospital_id)
    if h:
        _broadcast_hospital(h)
    return r
