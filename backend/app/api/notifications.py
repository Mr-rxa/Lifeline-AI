from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import schemas
from app.core.database import get_db
from app.deps import get_current_user
from app.models import Notification, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[schemas.NotificationOut])
def my_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(Notification)
        .filter(or_(Notification.user_id == user.id, Notification.role_target == user.role))
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )


@router.post("/{notification_id}/read", response_model=schemas.NotificationOut)
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(Notification, notification_id)
    if not n or (n.user_id not in (None, user.id) and n.role_target != user.role):
        raise HTTPException(status_code=404, detail="Notification not found")
    n.read = True
    db.commit()
    db.refresh(n)
    return n


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(Notification).filter(
        or_(Notification.user_id == user.id, Notification.role_target == user.role),
        Notification.read.is_(False),
    ).update({Notification.read: True}, synchronize_session=False)
    db.commit()
    return {"ok": True}
