import math

# Average urban ambulance speed (km/h) used for fallback ETA estimates.
AVG_URBAN_SPEED_KMH = 32.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometers."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def eta_seconds_from_distance(distance_km: float, speed_kmh: float = AVG_URBAN_SPEED_KMH) -> int:
    if speed_kmh <= 0:
        speed_kmh = AVG_URBAN_SPEED_KMH
    return int((distance_km / speed_kmh) * 3600)
