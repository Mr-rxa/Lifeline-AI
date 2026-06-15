from sqlalchemy.orm import Session

from app.models import AuditLog, Notification
from app.ws import manager


def notify(
    db: Session,
    *,
    title: str,
    message: str = "",
    type: str = "info",
    user_id: int | None = None,
    role_target: str | None = None,
    incident_id: int | None = None,
) -> Notification:
    """Persist a notification and push it over the websocket in one call."""
    n = Notification(
        title=title,
        message=message,
        type=type,
        user_id=user_id,
        role_target=role_target,
        incident_id=incident_id,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    manager.broadcast(
        "notification",
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.type,
            "user_id": n.user_id,
            "role_target": n.role_target,
            "incident_id": n.incident_id,
        },
    )
    return n


def audit(
    db: Session,
    *,
    action: str,
    actor: str = "",
    user_id: int | None = None,
    entity: str = "",
    entity_id: int | None = None,
    detail: str = "",
) -> None:
    db.add(
        AuditLog(
            action=action,
            actor=actor,
            user_id=user_id,
            entity=entity,
            entity_id=entity_id,
            detail=detail,
        )
    )
    db.commit()
