from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.core.database import get_db
from app.deps import require_roles
from app.models import (
    ROLE_ADMIN,
    Ambulance,
    Assignment,
    AuditLog,
    Hospital,
    Incident,
    Resource,
    TrackingHistory,
    User,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/audit", response_model=list[schemas.AuditOut])
def audit_logs(limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_roles(ROLE_ADMIN))):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/stats")
def stats(db: Session = Depends(get_db), _: User = Depends(require_roles(ROLE_ADMIN))):
    return {
        "users": db.query(User).count(),
        "drivers": db.query(User).filter(User.role == "driver").count(),
        "hospitals": db.query(Hospital).count(),
        "ambulances": db.query(Ambulance).count(),
        "resources": db.query(Resource).count(),
        "incidents": db.query(Incident).count(),
        "assignments": db.query(Assignment).count(),
        "tracking_points": db.query(TrackingHistory).count(),
        "audit_logs": db.query(AuditLog).count(),
    }
