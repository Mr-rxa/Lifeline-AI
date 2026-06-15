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
