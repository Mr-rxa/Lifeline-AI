from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import schemas
from app.core.database import get_db
from app.deps import require_roles
from app.models import ROLE_ADMIN, ROLE_DISPATCHER, Ambulance, User
from app.services.notify import audit

router = APIRouter(prefix="/api/ambulances", tags=["ambulances"])


class AmbulancePatch(BaseModel):
    driver_id: int | None = None
    type: str | None = None
    condition: str | None = None


@router.get("", response_model=list[schemas.AmbulanceOut])
def list_ambulances(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(ROLE_ADMIN, ROLE_DISPATCHER)),
):
    return db.query(Ambulance).order_by(Ambulance.vehicle_number).all()


@router.post("", response_model=schemas.AmbulanceOut, status_code=201)
def create_ambulance(
    payload: schemas.AmbulanceCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(ROLE_ADMIN)),
):
    if db.query(Ambulance).filter(Ambulance.vehicle_number == payload.vehicle_number).first():
        raise HTTPException(status_code=409, detail="Vehicle number already exists")
    if payload.driver_id:
        driver = db.get(User, payload.driver_id)
        if not driver or driver.role != "driver":
            raise HTTPException(status_code=400, detail="driver_id must reference a driver user")
    amb = Ambulance(vehicle_number=payload.vehicle_number, type=payload.type, driver_id=payload.driver_id)
    db.add(amb)
    db.commit()
    db.refresh(amb)
    audit(db, action="create_ambulance", actor=admin.email, user_id=admin.id, entity="ambulance", entity_id=amb.id)
    return amb


@router.patch("/{ambulance_id}", response_model=schemas.AmbulanceOut)
def update_ambulance(
    ambulance_id: int,
    payload: AmbulancePatch,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(ROLE_ADMIN)),
):
    amb = db.get(Ambulance, ambulance_id)
    if not amb:
        raise HTTPException(status_code=404, detail="Ambulance not found")
    data = payload.model_dump(exclude_none=True)
    if "driver_id" in data and data["driver_id"]:
        driver = db.get(User, data["driver_id"])
        if not driver or driver.role != "driver":
            raise HTTPException(status_code=400, detail="driver_id must reference a driver user")
    for field, value in data.items():
        setattr(amb, field, value)
    db.commit()
    db.refresh(amb)
    audit(db, action="update_ambulance", actor=admin.email, user_id=admin.id, entity="ambulance", entity_id=amb.id)
    return amb


@router.get("/{ambulance_id}", response_model=schemas.AmbulanceOut)
def get_ambulance(
    ambulance_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(ROLE_ADMIN, ROLE_DISPATCHER)),
):
    amb = db.get(Ambulance, ambulance_id)
    if not amb:
        raise HTTPException(status_code=404, detail="Ambulance not found")
    return amb
