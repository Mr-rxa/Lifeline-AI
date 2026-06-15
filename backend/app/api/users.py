from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app import schemas
from app.core.database import get_db
from app.core.security import hash_password
from app.deps import require_roles
from app.models import ROLE_ADMIN, ROLE_DISPATCHER, User
from app.services.notify import audit

router = APIRouter(prefix="/api/users", tags=["users"])

ALL_ROLES = {"citizen", "dispatcher", "driver", "hospital", "admin"}


class AdminCreateUser(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    phone: str = ""
    role: str
    hospital_id: int | None = None


class StatusPatch(BaseModel):
    status: str


@router.get("", response_model=list[schemas.UserOut])
def list_users(
    role: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(ROLE_ADMIN)),
):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    return q.order_by(User.created_at.desc()).all()


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(
    payload: AdminCreateUser,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(ROLE_ADMIN)),
):
    if payload.role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=payload.role,
        hospital_id=payload.hospital_id if payload.role == "hospital" else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, action="create_user", actor=admin.email, user_id=admin.id, entity="user", entity_id=user.id,
          detail=f"role={user.role}")
    return user


@router.patch("/{user_id}/status", response_model=schemas.UserOut)
def set_status(
    user_id: int,
    payload: StatusPatch,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(ROLE_ADMIN)),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.status not in {"active", "suspended"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    user.status = payload.status
    db.commit()
    db.refresh(user)
    audit(db, action="set_user_status", actor=admin.email, user_id=admin.id, entity="user",
          entity_id=user.id, detail=payload.status)
    return user


@router.get("/drivers", response_model=list[schemas.UserOut])
def list_drivers(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(ROLE_ADMIN, ROLE_DISPATCHER)),
):
    return db.query(User).filter(User.role == "driver").order_by(User.full_name).all()
