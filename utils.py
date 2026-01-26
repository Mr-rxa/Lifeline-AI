import math

def haversine(lat1, lon1, lat2, lon2):
    """Return distance in kilometers between two lat/lon points."""
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def interpolate_point(a, b, frac):
    """Linear interpolation between two (lat,lon) points."""
    lat = a[0] + (b[0] - a[0]) * frac
    lon = a[1] + (b[1] - a[1]) * frac
    return (lat, lon)