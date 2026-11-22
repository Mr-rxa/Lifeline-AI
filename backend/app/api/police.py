from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import require_roles
from app.models import ROLE_ADMIN, ROLE_DISPATCHER, PoliceUnit, User
from app.services.notify import audit

router = APIRouter(prefix="/api/police", tags=["police"])


class PoliceUnitCreate(BaseModel):
    unit_number: str = Field(min_length=2, max_length=30)
    station_name: str = ""
    type: str = "Patrol"
    officer_id: int | None = None


class PoliceUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    unit_number: str
    station_name: str
    type: str
    status: str
    officer_id: int | None
    last_lat: float | None
    last_lon: float | None



@router.get("/units", response_model=list[PoliceUnitOut])
def list_units(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(ROLE_ADMIN, ROLE_DISPATCHER)),
):
    return db.query(PoliceUnit).order_by(PoliceUnit.unit_number).all()


@router.post("/units", response_model=PoliceUnitOut, status_code=201)
def create_unit(
    payload: PoliceUnitCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(ROLE_ADMIN)),
):
    if db.query(PoliceUnit).filter(PoliceUnit.unit_number == payload.unit_number).first():
        raise HTTPException(status_code=409, detail="Police unit number already exists")
    if payload.officer_id:
        officer = db.get(User, payload.officer_id)
        if not officer or officer.role != "police":
            raise HTTPException(status_code=400, detail="officer_id must reference a police user")
    unit = PoliceUnit(**payload.model_dump())
    db.add(unit)
    db.commit()
    db.refresh(unit)
    audit(db, action="create_police_unit", actor=admin.email, user_id=admin.id,
          entity="police_unit", entity_id=unit.id)
    return unit
