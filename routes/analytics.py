from flask import Blueprint, jsonify
from extensions import db
from models import Incident, Ambulance, Hospital
from sqlalchemy import func
from flask_jwt_extended import jwt_required

stats_bp = Blueprint('analytics', __name__)

@stats_bp.route('/summary', methods=['GET'])
@jwt_required()
def get_summary():
    total_incidents = Incident.query.count()
    active_incidents = Incident.query.filter(Incident.status.notin_(['completed', 'cancelled'])).count()
    completed_incidents = Incident.query.filter_by(status='completed').count()
    critical_active = Incident.query.filter(Incident.status.notin_(['completed', 'cancelled']), Incident.severity == 'critical').count()
    
    # Calculate Average Response Time (arrived_pickup_at - created_at)
    completed = Incident.query.filter(Incident.arrived_pickup_at.isnot(None), Incident.created_at.isnot(None)).all()
    avg_response_seconds = 0
    if completed:
        total_seconds = sum((inc.arrived_pickup_at - inc.created_at).total_seconds() for inc in completed)
        avg_response_seconds = total_seconds / len(completed)
    
    total_ambulances = Ambulance.query.count()
    available_ambulances = Ambulance.query.filter_by(status='available').count()
    assigned_ambulances = Ambulance.query.filter(Ambulance.status.in_(['dispatched', 'en_route_pickup', 'arrived_pickup', 'en_route_hospital', 'arrived_hospital'])).count()
    maintenance_ambulances = Ambulance.query.filter_by(status='maintenance').count()
    
    total_beds = db.session.query(func.sum(Hospital.total_beds)).scalar() or 0
    available_beds = db.session.query(func.sum(Hospital.available_beds)).scalar() or 0
    total_icu = db.session.query(func.sum(Hospital.total_icu_beds)).scalar() or 0
    available_icu = db.session.query(func.sum(Hospital.available_icu_beds)).scalar() or 0
    hospitals_with_icu = Hospital.query.filter(Hospital.available_icu_beds > 0).count()
    
    return jsonify({
        'incidents': {
            'total': total_incidents,
            'active': active_incidents,
            'critical_active': critical_active,
            'completed': completed_incidents,
            'avg_response_time_seconds': round(avg_response_seconds)
        },
        'ambulances': {
            'total': total_ambulances,
            'available': available_ambulances,
            'assigned': assigned_ambulances,
            'maintenance': maintenance_ambulances
        },
        'hospitals': {
            'total_beds': total_beds,
            'available_beds': available_beds,
            'total_icu': total_icu,
            'available_icu': available_icu,
            'with_icu': hospitals_with_icu
        }
    }), 200

@stats_bp.route('/heatmap', methods=['GET'])
@jwt_required()
def get_heatmap():
    incidents = Incident.query.filter(Incident.status.in_(['completed', 'cancelled'])).all()
    points = []
    for inc in incidents:
        # Intensity based on severity
        intensity = 0.5
        if inc.severity == 'urgent': intensity = 0.8
        if inc.severity == 'critical': intensity = 1.0
        points.append([inc.pickup_lat, inc.pickup_lon, intensity])
    return jsonify(points), 200
