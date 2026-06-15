from flask import Blueprint, request, jsonify
from extensions import db
from models import Incident, Ambulance, Hospital
from flask_jwt_extended import jwt_required
from ai_engine import predict_severity, recommend_hospital
from routes.tracking import add_notification
from datetime import datetime

inc_bp = Blueprint('incidents', __name__)

@inc_bp.route('/', methods=['GET'])
@jwt_required()
def get_incidents():
    incidents = Incident.query.order_by(Incident.created_at.desc()).all()
    return jsonify([{
        'id': i.id,
        'patient_name': i.patient_name,
        'patient_phone': i.patient_phone,
        'patient_condition_notes': i.patient_condition_notes,
        'pickup_lat': i.pickup_lat,
        'pickup_lon': i.pickup_lon,
        'pickup_address': i.pickup_address,
        'severity': i.severity,
        'status': i.status,
        'assigned_ambulance_id': i.assigned_ambulance_id,
        'target_hospital_id': i.target_hospital_id,
        'created_at': i.created_at.isoformat() if i.created_at else None,
        'dispatched_at': i.dispatched_at.isoformat() if i.dispatched_at else None,
        'en_route_pickup_at': i.en_route_pickup_at.isoformat() if i.en_route_pickup_at else None,
        'arrived_pickup_at': i.arrived_pickup_at.isoformat() if i.arrived_pickup_at else None,
        'en_route_hospital_at': i.en_route_hospital_at.isoformat() if i.en_route_hospital_at else None,
        'arrived_hospital_at': i.arrived_hospital_at.isoformat() if i.arrived_hospital_at else None,
        'completed_at': i.completed_at.isoformat() if i.completed_at else None
    } for i in incidents]), 200

@inc_bp.route('/', methods=['POST'])
def create_incident():
    data = request.get_json()
    if not data or not data.get('pickup_lat') or not data.get('pickup_lon'):
        return jsonify({'error': 'Missing location'}), 400
        
    severity = data.get('severity')
    if not severity:
        severity = predict_severity(data.get('description', ''))
        
    incident = Incident(
        patient_name=data.get('patient_name', 'Unknown'),
        patient_phone=data.get('patient_phone', ''),
        patient_condition_notes=data.get('description', ''),
        pickup_lat=float(data['pickup_lat']),
        pickup_lon=float(data['pickup_lon']),
        pickup_address=data.get('pickup_address', ''),
        severity=severity,
        status='pending'
    )
    
    # Recommend Hospital
    best_hospital = recommend_hospital(incident.pickup_lat, incident.pickup_lon, severity)
    ai_reasoning = ""
    if best_hospital:
        incident.target_hospital_id = best_hospital.id
        ai_reasoning = f"AI Recommended {best_hospital.name} based on capacity & proximity."
        
    db.session.add(incident)
    db.session.commit()
    
    add_notification(f"New {severity.upper()} emergency logged! {ai_reasoning}", "warning")
    
    return jsonify({
        'message': 'Incident created successfully', 
        'id': incident.id,
        'target_hospital': best_hospital.id if best_hospital else None,
        'ai_reasoning': ai_reasoning
    }), 201

@inc_bp.route('/<int:inc_id>', methods=['GET'])
def get_incident(inc_id):
    i = Incident.query.get_or_404(inc_id)
    return jsonify({
        'id': i.id,
        'patient_name': i.patient_name,
        'patient_phone': i.patient_phone,
        'patient_condition_notes': i.patient_condition_notes,
        'pickup_lat': i.pickup_lat,
        'pickup_lon': i.pickup_lon,
        'pickup_address': i.pickup_address,
        'severity': i.severity,
        'status': i.status,
        'assigned_ambulance_id': i.assigned_ambulance_id,
        'target_hospital_id': i.target_hospital_id,
        'created_at': i.created_at.isoformat() if i.created_at else None,
        'dispatched_at': i.dispatched_at.isoformat() if i.dispatched_at else None,
        'en_route_pickup_at': i.en_route_pickup_at.isoformat() if i.en_route_pickup_at else None,
        'arrived_pickup_at': i.arrived_pickup_at.isoformat() if i.arrived_pickup_at else None,
        'en_route_hospital_at': i.en_route_hospital_at.isoformat() if i.en_route_hospital_at else None,
        'arrived_hospital_at': i.arrived_hospital_at.isoformat() if i.arrived_hospital_at else None,
        'completed_at': i.completed_at.isoformat() if i.completed_at else None
    }), 200

@inc_bp.route('/<int:inc_id>/assign', methods=['POST'])
@jwt_required()
def assign_ambulance(inc_id):
    data = request.get_json()
    incident = Incident.query.get_or_404(inc_id)
    amb_id = data.get('ambulance_id')
    
    if not amb_id:
        return jsonify({'error': 'Missing ambulance_id'}), 400
        
    amb = Ambulance.query.get_or_404(amb_id)
    if amb.status != 'available' and amb.current_incident_id != incident.id:
        return jsonify({'error': 'Ambulance is not available'}), 400
        
    # If the incident already had an ambulance, free the old one
    if incident.assigned_ambulance_id and incident.assigned_ambulance_id != amb.id:
        old_amb = Ambulance.query.get(incident.assigned_ambulance_id)
        if old_amb:
            old_amb.status = 'available'
            old_amb.current_incident_id = None
            
    incident.assigned_ambulance_id = amb.id
    incident.status = 'assigned'
    incident.dispatched_at = datetime.utcnow()
    
    amb.status = 'dispatched'
    amb.current_incident_id = incident.id
    
    db.session.commit()
    add_notification(f"Ambulance {amb.vehicle_number} dispatched to Incident #{incident.id}", "info")
    return jsonify({'message': 'Ambulance assigned'}), 200

@inc_bp.route('/<int:inc_id>/unassign', methods=['POST'])
@jwt_required()
def unassign_ambulance(inc_id):
    incident = Incident.query.get_or_404(inc_id)
    
    if incident.assigned_ambulance_id:
        amb = Ambulance.query.get(incident.assigned_ambulance_id)
        if amb:
            amb.status = 'available'
            amb.current_incident_id = None
        
        incident.assigned_ambulance_id = None
        incident.status = 'pending'
        db.session.commit()
        add_notification(f"Ambulance unassigned from Incident #{incident.id}", "warning")
        return jsonify({'message': 'Ambulance unassigned'}), 200
        
    return jsonify({'message': 'No ambulance was assigned'}), 200

@inc_bp.route('/<int:inc_id>/status', methods=['PUT'])
@jwt_required()
def update_status(inc_id):
    data = request.get_json()
    incident = Incident.query.get_or_404(inc_id)
    new_status = data.get('status')
    
    if new_status:
        incident.status = new_status
        now = datetime.utcnow()
        
        if new_status == 'en_route_pickup':
            incident.en_route_pickup_at = now
        elif new_status == 'arrived_pickup':
            incident.arrived_pickup_at = now
        elif new_status == 'en_route_hospital':
            incident.en_route_hospital_at = now
        elif new_status == 'arrived_hospital':
            incident.arrived_hospital_at = now
        elif new_status in ['completed', 'cancelled']:
            incident.completed_at = now
            if incident.assigned_ambulance_id:
                amb = Ambulance.query.get(incident.assigned_ambulance_id)
                if amb:
                    amb.status = 'available'
                    amb.current_incident_id = None
                    
        add_notification(f"Incident #{incident.id} status changed to: {new_status.replace('_', ' ').upper()}", "success" if new_status == 'completed' else "info")
    
    db.session.commit()
    return jsonify({'message': 'Status updated successfully'}), 200
