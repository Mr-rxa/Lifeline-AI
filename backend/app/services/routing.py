import httpx

from app.core.config import settings
from app.services.geo import eta_seconds_from_distance, haversine_km

ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"


def _fallback(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    """Straight-line estimate used when ORS is unavailable or no key configured.
    Applies a 1.3x road-network factor for realism."""
    straight = haversine_km(lat1, lon1, lat2, lon2)
    road = straight * 1.3
    return {
        "distance_km": round(road, 2),
        "eta_seconds": eta_seconds_from_distance(road),
        "geometry": [[lat1, lon1], [lat2, lon2]],
        "source": "estimate",
    }


def get_route(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    """Return a driving route between two points.

    Tries OpenRouteService for a real road route + ETA, and always falls back to a
    haversine estimate so the platform functions without internet/keys.
    Geometry is returned as a list of [lat, lon] pairs (Leaflet order).
    """
    if not settings.ORS_API_KEY:
        return _fallback(lat1, lon1, lat2, lon2)

    try:
        resp = httpx.post(
            ORS_URL,
            headers={"Authorization": settings.ORS_API_KEY, "Content-Type": "application/json"},
            json={"coordinates": [[lon1, lat1], [lon2, lat2]]},
            timeout=6.0,
        )
        resp.raise_for_status()
        data = resp.json()
        feature = data["features"][0]
        summary = feature["properties"]["summary"]
        coords = feature["geometry"]["coordinates"]  # [lon, lat]
        geometry = [[c[1], c[0]] for c in coords]
        return {
            "distance_km": round(summary["distance"] / 1000.0, 2),
            "eta_seconds": int(summary["duration"]),
            "geometry": geometry,
            "source": "ors",
        }
    except Exception:
        return _fallback(lat1, lon1, lat2, lon2)
