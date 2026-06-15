from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import schemas
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.deps import get_current_user
from app.models import ROLE_ADMIN, User, utcnow
from app.services.notify import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

PUBLIC_ROLES = {"citizen", "dispatcher", "driver", "hospital"}


def _issue(db: Session, user: User) -> schemas.TokenResponse:
    user.last_login = utcnow()
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.role)
    return schemas.TokenResponse(access_token=token, user=schemas.UserOut.model_validate(user))


@router.post("/register", response_model=schemas.TokenResponse)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    if payload.role not in PUBLIC_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role for self-registration")
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
    audit(db, action="register", actor=user.email, user_id=user.id, entity="user", entity_id=user.id)
    return _issue(db, user)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
    return _issue(db, user)


@router.post("/token", response_model=schemas.TokenResponse)
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password flow (used by Swagger UI). `username` field = email."""
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _issue(db, user)


@router.get("/me", response_model=schemas.UserOut)
def me(user: User = Depends(get_current_user)):
    return user
