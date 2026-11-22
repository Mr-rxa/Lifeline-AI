from flask import Blueprint, request, jsonify
from extensions import db
from models import Ambulance, User
from flask_jwt_extended import jwt_required

amb_bp = Blueprint('ambulances', __name__)

@amb_bp.route('/', methods=['GET'])
def get_ambulances():
    ambulances = Ambulance.query.all()
    return jsonify([{
        'id': a.id,
        'vehicle_number': a.vehicle_number,
        'status': a.status,
        'type': a.type,
        'last_lat': a.last_lat,
        'last_lon': a.last_lon,
        'driver_id': a.driver_id,
        'current_incident_id': a.current_incident_id
    } for a in ambulances]), 200

@amb_bp.route('/', methods=['POST'])
@jwt_required()
def add_ambulance():
    data = request.get_json()
    if not data or not data.get('vehicle_number'):
        return jsonify({'error': 'Missing vehicle number'}), 400
    if Ambulance.query.filter_by(vehicle_number=data['vehicle_number']).first():
        return jsonify({'error': 'Vehicle number already exists'}), 409
    type_name = data.get('type', 'ALS')
    if type_name not in {'ALS', 'BLS'}:
        return jsonify({'error': 'Invalid ambulance type'}), 400
    driver_id = data.get('driver_id')
    if driver_id:
        driver = db.session.get(User, driver_id)
        if not driver or driver.role != 'driver':
            return jsonify({'error': 'Invalid driver'}), 400
        
    amb = Ambulance(
        vehicle_number=data['vehicle_number'],
        type=type_name,
        driver_id=driver_id,
        status='available'
    )
    db.session.add(amb)
    db.session.commit()
    return jsonify({'message': 'Ambulance added successfully', 'id': amb.id}), 201

@amb_bp.route('/<int:amb_id>/assign', methods=['POST'])
@jwt_required()
def assign_driver(amb_id):
    data = request.get_json()
    driver_id = data.get('driver_id')
    amb = Ambulance.query.get_or_404(amb_id)
    amb.driver_id = driver_id
    db.session.commit()
    return jsonify({'message': 'Driver assigned'}), 200
