from flask import Blueprint, request, jsonify
from extensions import db
from models import Hospital
from flask_jwt_extended import jwt_required

hosp_bp = Blueprint('hospitals', __name__)

@hosp_bp.route('/', methods=['GET'])
def get_hospitals():
    hospitals = Hospital.query.all()
    return jsonify([{
        'id': h.id,
        'name': h.name,
        'lat': h.lat,
        'lon': h.lon,
        'address': h.address,
        'available_beds': h.available_beds,
        'total_beds': h.total_beds,
        'available_icu_beds': h.available_icu_beds,
        'ventilators_available': h.ventilators_available
    } for h in hospitals]), 200

@hosp_bp.route('/', methods=['POST'])
@jwt_required()
def create_hospital():
    from flask_jwt_extended import get_jwt
    if get_jwt().get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json() or {}
    required = ('name', 'lat', 'lon')
    if not all(field in data for field in required):
        return jsonify({'error': 'Missing hospital details'}), 400
    try:
        lat = float(data['lat'])
        lon = float(data['lon'])
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid coordinates'}), 400
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({'error': 'Invalid coordinates'}), 400
    hosp = Hospital(
        name=data['name'].strip(),
        lat=lat,
        lon=lon,
        address=data.get('address', ''),
        total_beds=int(data.get('total_beds', 0)),
        available_beds=int(data.get('available_beds', 0)),
        total_icu_beds=int(data.get('total_icu_beds', 0)),
        available_icu_beds=int(data.get('available_icu_beds', 0)),
    )
    if not hosp.name:
        return jsonify({'error': 'Hospital name is required'}), 400
    hosp.available_beds = min(max(hosp.available_beds, 0), hosp.total_beds)
    hosp.available_icu_beds = min(max(hosp.available_icu_beds, 0), hosp.total_icu_beds)
    db.session.add(hosp)
    db.session.commit()
    return jsonify({'message': 'Hospital registered successfully', 'id': hosp.id}), 201

@hosp_bp.route('/<int:hosp_id>', methods=['PUT'])
@jwt_required()
def update_hospital(hosp_id):
    data = request.get_json()
    hosp = Hospital.query.get_or_404(hosp_id)
    
    if 'available_beds' in data:
        hosp.available_beds = data['available_beds']
    if 'available_icu_beds' in data:
        hosp.available_icu_beds = data['available_icu_beds']
    if 'ventilators_available' in data:
        hosp.ventilators_available = data['ventilators_available']
        
    db.session.commit()
    return jsonify({'message': 'Hospital updated successfully'}), 200
