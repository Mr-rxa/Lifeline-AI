"""Decision-support engine for triage and resource recommendation.

- predict_severity: keyword + emergency-type weighted scoring -> severity band.
- recommend_hospitals: ranks hospitals by capacity-aware proximity score.
- recommend_ambulances: ranks on-shift, available ambulances by ETA.
"""

from sqlalchemy.orm import Session

from app.models import Ambulance, Hospital
from app.services.geo import eta_seconds_from_distance, haversine_km

CRITICAL_KEYWORDS = [
    "cardiac", "heart attack", "heart", "not breathing", "no pulse", "unconscious",
    "stroke", "seizure", "severe bleeding", "hemorrhage", "drowning", "choking",
    "overdose", "anaphyl", "gunshot", "stab", "amputat", "electrocut",
]
URGENT_KEYWORDS = [
    "breath", "chest pain", "fracture", "broken", "accident", "collision", "burn",
    "deep cut", "labor", "pregnan", "allergic", "fall", "head injury", "fainted",
    "high fever", "dehydrat",
]

EMERGENCY_TYPE_WEIGHT = {
    "cardiac": 60,
    "trauma": 45,
    "accident": 45,
    "respiratory": 40,
    "stroke": 55,
    "obstetric": 35,
    "burn": 35,
    "medical": 15,
    "other": 10,
}


def predict_severity(emergency_type: str, description: str) -> tuple[str, int]:
    """Return (severity_band, score 0-100)."""
    text = (description or "").lower()
    score = EMERGENCY_TYPE_WEIGHT.get((emergency_type or "").lower(), 10)

    for kw in CRITICAL_KEYWORDS:
        if kw in text:
            score += 40
            break
    for kw in URGENT_KEYWORDS:
        if kw in text:
            score += 20
            break

    score = max(0, min(100, score))
    if score >= 70:
        band = "critical"
    elif score >= 35:
        band = "urgent"
    else:
        band = "normal"
    return band, score


def recommend_hospitals(db: Session, lat: float, lon: float, severity: str, limit: int = 3) -> list[dict]:
    """Rank hospitals by a capacity-aware proximity score.

    Critical patients require an available ICU bed; others require a general bed.
    Score rewards proximity and spare capacity.
    """
    hospitals = db.query(Hospital).filter(Hospital.accepting.is_(True)).all()
    ranked: list[dict] = []

    for h in hospitals:
        dist = max(haversine_km(lat, lon, h.lat, h.lon) * 1.3, 0.1)

        if severity == "critical":
            if h.available_icu_beds <= 0:
                continue
            capacity_bonus = h.available_icu_beds * 6
        else:
            if h.available_beds <= 0:
                continue
            capacity_bonus = h.available_beds * 1.5

        score = (100.0 / dist) + capacity_bonus
        ranked.append(
            {
                "hospital": h,
                "distance_km": round(dist, 2),
                "eta_seconds": eta_seconds_from_distance(dist),
                "score": round(score, 2),
            }
        )

    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:limit]


def recommend_ambulances(db: Session, lat: float, lon: float, limit: int = 3) -> list[dict]:
    """Rank available, on-shift ambulances with a known location by ETA to pickup."""
    ambulances = (
        db.query(Ambulance)
        .filter(
            Ambulance.status == "available",
            Ambulance.on_shift.is_(True),
            Ambulance.last_lat.isnot(None),
            Ambulance.last_lon.isnot(None),
        )
        .all()
    )
    ranked: list[dict] = []
    for a in ambulances:
        dist = max(haversine_km(lat, lon, a.last_lat, a.last_lon) * 1.3, 0.1)
        ranked.append(
            {
                "ambulance": a,
                "distance_km": round(dist, 2),
                "eta_seconds": eta_seconds_from_distance(dist),
            }
        )
    ranked.sort(key=lambda r: r["eta_seconds"])
    return ranked[:limit]
