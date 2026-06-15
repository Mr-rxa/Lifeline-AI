from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import require_roles
from app.models import ROLE_ADMIN, ROLE_DISPATCHER, Ambulance, Hospital, Incident, User

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

STAFF = (ROLE_ADMIN, ROLE_DISPATCHER)
ACTIVE = ("assigned", "accepted", "at_pickup", "en_route_hospital", "at_hospital")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _seconds_between(a: datetime | None, b: datetime | None) -> float | None:
    a, b = _aware(a), _aware(b)
    if a and b:
        return (b - a).total_seconds()
    return None


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF))):
    incidents = db.query(Incident).all()
    ambulances = db.query(Ambulance).all()
    hospitals = db.query(Hospital).all()

    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    response_times = [
        s
        for inc in incidents
        if (s := _seconds_between(inc.dispatched_at, inc.arrived_pickup_at)) is not None
    ]
    avg_response = round(sum(response_times) / len(response_times)) if response_times else 0

    completed_today = sum(
        1 for inc in incidents if inc.completed_at and (_aware(inc.completed_at) >= start_today)
    )

    return {
        "total_incidents": len(incidents),
        "active_incidents": sum(1 for i in incidents if i.status in ACTIVE),
        "pending_incidents": sum(1 for i in incidents if i.status == "pending"),
        "completed_incidents": sum(1 for i in incidents if i.status == "completed"),
        "completed_today": completed_today,
        "avg_response_seconds": avg_response,
        "ambulances_total": len(ambulances),
        "ambulances_available": sum(1 for a in ambulances if a.status == "available" and a.on_shift),
        "ambulances_on_shift": sum(1 for a in ambulances if a.on_shift),
        "ambulances_busy": sum(1 for a in ambulances if a.current_incident_id is not None),
        "hospitals_total": len(hospitals),
        "beds_available": sum(h.available_beds for h in hospitals),
        "beds_total": sum(h.total_beds for h in hospitals),
        "icu_available": sum(h.available_icu_beds for h in hospitals),
        "icu_total": sum(h.total_icu_beds for h in hospitals),
        "severity_breakdown": {
            "critical": sum(1 for i in incidents if i.severity == "critical"),
            "urgent": sum(1 for i in incidents if i.severity == "urgent"),
            "normal": sum(1 for i in incidents if i.severity == "normal"),
        },
    }


@router.get("/response-times")
def response_times(days: int = 7, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF))):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    incidents = db.query(Incident).filter(Incident.dispatched_at.isnot(None)).all()

    buckets: dict[str, list[float]] = defaultdict(list)
    for inc in incidents:
        d = _aware(inc.dispatched_at)
        secs = _seconds_between(inc.dispatched_at, inc.arrived_pickup_at)
        if d and d >= start and secs is not None:
            buckets[d.strftime("%Y-%m-%d")].append(secs)

    series = []
    for i in range(days):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        vals = buckets.get(day, [])
        series.append(
            {"date": day, "avg_seconds": round(sum(vals) / len(vals)) if vals else 0, "count": len(vals)}
        )
    return series


@router.get("/hospital-utilization")
def hospital_utilization(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF))):
    hospitals = db.query(Hospital).all()
    out = []
    for h in hospitals:
        bed_used = h.total_beds - h.available_beds
        icu_used = h.total_icu_beds - h.available_icu_beds
        out.append(
            {
                "id": h.id,
                "name": h.name,
                "bed_utilization": round(bed_used / h.total_beds * 100, 1) if h.total_beds else 0,
                "icu_utilization": round(icu_used / h.total_icu_beds * 100, 1) if h.total_icu_beds else 0,
                "available_beds": h.available_beds,
                "available_icu_beds": h.available_icu_beds,
                "total_beds": h.total_beds,
                "total_icu_beds": h.total_icu_beds,
            }
        )
    out.sort(key=lambda r: r["bed_utilization"], reverse=True)
    return out


@router.get("/fleet-utilization")
def fleet_utilization(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF))):
    ambulances = db.query(Ambulance).all()
    counts: dict[str, int] = defaultdict(int)
    for a in ambulances:
        counts[a.status] += 1
    return [{"status": k, "count": v} for k, v in counts.items()]


@router.get("/incident-trends")
def incident_trends(days: int = 14, db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF))):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    incidents = db.query(Incident).all()

    daily: dict[str, dict] = {}
    for i in range(days):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        daily[day] = {"date": day, "count": 0, "critical": 0, "urgent": 0, "normal": 0}

    for inc in incidents:
        c = _aware(inc.created_at)
        if c and c >= start:
            key = c.strftime("%Y-%m-%d")
            if key in daily:
                daily[key]["count"] += 1
                daily[key][inc.severity] = daily[key].get(inc.severity, 0) + 1

    return list(daily.values())


@router.get("/heatmap")
def heatmap(db: Session = Depends(get_db), _: User = Depends(require_roles(*STAFF))):
    weight = {"critical": 1.0, "urgent": 0.6, "normal": 0.3}
    incidents = db.query(Incident).all()
    return [[i.pickup_lat, i.pickup_lon, weight.get(i.severity, 0.3)] for i in incidents]
