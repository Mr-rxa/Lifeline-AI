from extensions import db
from datetime import datetime

class SystemConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    setup_complete = db.Column(db.Boolean, default=False)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='dispatcher') # admin, dispatcher, hospital, driver
    status = db.Column(db.String(20), default='active') # active, suspended
    last_login = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital.id'), nullable=True)

class Hospital(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(255))
    
    total_beds = db.Column(db.Integer, default=0)
    available_beds = db.Column(db.Integer, default=0)
    total_icu_beds = db.Column(db.Integer, default=0)
    available_icu_beds = db.Column(db.Integer, default=0)
    ventilators_available = db.Column(db.Integer, default=0)
    blood_bank_status = db.Column(db.String(255), default='A+, O+, B+')

class Ambulance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(20), unique=True, nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    status = db.Column(db.String(20), default='available') # available, dispatched, en_route_pickup, arrived_pickup, en_route_hospital, arrived_hospital, busy, maintenance
    type = db.Column(db.String(20), default='ALS') # ALS, BLS
    condition = db.Column(db.String(20), default='good') # good, needs_repair
    mileage = db.Column(db.Float, default=0.0)
    last_maintenance = db.Column(db.DateTime, nullable=True)
    
    last_lat = db.Column(db.Float, nullable=True)
    last_lon = db.Column(db.Float, nullable=True)
    last_update = db.Column(db.DateTime, nullable=True)
    
    current_incident_id = db.Column(db.Integer, db.ForeignKey('incident.id'), nullable=True)

class Incident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(100))
    patient_phone = db.Column(db.String(20))
    patient_condition_notes = db.Column(db.Text)
    
    pickup_lat = db.Column(db.Float, nullable=False)
    pickup_lon = db.Column(db.Float, nullable=False)
    pickup_address = db.Column(db.String(255))
    
    severity = db.Column(db.String(20), default='normal') # normal, urgent, critical
    status = db.Column(db.String(20), default='pending') # pending, assigned, en_route_pickup, arrived_pickup, en_route_hospital, arrived_hospital, completed, cancelled
    
    assigned_ambulance_id = db.Column(db.Integer, db.ForeignKey('ambulance.id'), nullable=True)
    target_hospital_id = db.Column(db.Integer, db.ForeignKey('hospital.id'), nullable=True)
    
    # Precise Lifecycle Timestamps for Analytics
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    dispatched_at = db.Column(db.DateTime, nullable=True)
    en_route_pickup_at = db.Column(db.DateTime, nullable=True)
    arrived_pickup_at = db.Column(db.DateTime, nullable=True)
    en_route_hospital_at = db.Column(db.DateTime, nullable=True)
    arrived_hospital_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

class TrackingLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ambulance_id = db.Column(db.Integer, db.ForeignKey('ambulance.id'), nullable=False)
    incident_id = db.Column(db.Integer, db.ForeignKey('incident.id'), nullable=True)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    speed = db.Column(db.Float, default=0.0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
