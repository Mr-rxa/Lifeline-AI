from models import Hospital
import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def predict_severity(description):
    """
    Mock AI Severity Prediction.
    In production, this would use NLP (e.g. HuggingFace zero-shot classification)
    """
    desc = description.lower()
    critical_keywords = ['heart', 'attack', 'breath', 'unconscious', 'bleeding', 'stroke']
    urgent_keywords = ['broken', 'fracture', 'pain', 'accident', 'fall']
    
    if any(word in desc for word in critical_keywords):
        return 'critical'
    if any(word in desc for word in urgent_keywords):
        return 'urgent'
    return 'normal'

def recommend_hospital(lat, lon, severity):
    """
    Smart Hospital Recommendation Engine.
    Considers distance AND available ICU/regular beds based on severity.
    """
    hospitals = Hospital.query.all()
    best_hospital = None
    best_score = float('-inf')
    
    for h in hospitals:
        dist = haversine(lat, lon, h.lat, h.lon)
        if dist == 0: dist = 0.1 # prevent div by zero
        
        # Base score is inverse of distance
        score = 100 / dist
        
        # Modify score based on availability and severity requirements
        if severity == 'critical':
            if h.available_icu_beds <= 0:
                continue # Skip hospitals without ICU for critical
            score += (h.available_icu_beds * 5)
        else:
            if h.available_beds <= 0:
                continue
            score += (h.available_beds * 2)
            
        if score > best_score:
            best_score = score
            best_hospital = h
            
    return best_hospital
