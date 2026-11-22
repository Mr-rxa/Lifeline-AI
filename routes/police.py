from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt

from extensions import db
from models import PoliceUnit, User

police_bp = Blueprint('police', __name__)


def is_admin():
    return get_jwt().get('role') == 'admin'


@police_bp.route('/units', methods=['GET'])
@jwt_required()
def list_units():
    return jsonify([
        {
            'id': u.id,
            'unit_number': u.unit_number,
            'station_name': u.station_name,
            'type': u.type,
            'status': u.status,
            'officer_id': u.officer_id,
        }
        for u in PoliceUnit.query.order_by(PoliceUnit.unit_number).all()
    ]), 200


@police_bp.route('/units', methods=['POST'])
@jwt_required()
def create_unit():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json() or {}
    unit_number = (data.get('unit_number') or '').strip()
    if len(unit_number) < 2:
        return jsonify({'error': 'Unit number is required'}), 400
    if PoliceUnit.query.filter_by(unit_number=unit_number).first():
        return jsonify({'error': 'Police unit number already exists'}), 409
    officer_id = data.get('officer_id')
    if officer_id:
        officer = db.session.get(User, officer_id)
        if not officer or officer.role != 'police':
            return jsonify({'error': 'Invalid police officer'}), 400
    unit = PoliceUnit(
        unit_number=unit_number,
        station_name=(data.get('station_name') or '').strip(),
        type=data.get('type') or 'Patrol',
        officer_id=officer_id,
    )
    db.session.add(unit)
    db.session.commit()
    return jsonify({'message': 'Police unit registered successfully', 'id': unit.id}), 201
