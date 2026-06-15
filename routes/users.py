from flask import Blueprint, request, jsonify
from extensions import db, bcrypt
from models import User
from flask_jwt_extended import jwt_required, get_jwt

users_bp = Blueprint('users', __name__)

def is_admin():
    claims = get_jwt()
    return claims and claims.get('role') == 'admin'

@users_bp.route('/', methods=['GET'])
@jwt_required()
def get_users():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    users = User.query.all()
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'email': u.email,
        'role': u.role,
        'status': u.status,
        'last_login': u.last_login.isoformat() if u.last_login else None,
        'created_at': u.created_at.isoformat() if u.created_at else None
    } for u in users]), 200

@users_bp.route('/', methods=['POST'])
@jwt_required()
def create_user():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password') or not data.get('email'):
        return jsonify({'error': 'Missing required fields'}), 400

    if User.query.filter_by(username=data['username']).first() or User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'User already exists'}), 400

    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    new_user = User(
        username=data['username'],
        email=data['email'],
        password_hash=hashed_password,
        role=data.get('role', 'dispatcher'),
        status=data.get('status', 'active')
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User created successfully'}), 201

@users_bp.route('/<int:user_id>', methods=['PUT'])
@jwt_required()
def update_user(user_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
        
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    if 'email' in data and data['email'] != user.email:
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already in use'}), 400
        user.email = data['email']
        
    if 'role' in data:
        user.role = data['role']
    if 'status' in data:
        user.status = data['status']
    if 'password' in data and data['password']:
        user.password_hash = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        
    db.session.commit()
    return jsonify({'message': 'User updated successfully'}), 200

@users_bp.route('/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
        
    user = User.query.get_or_404(user_id)
    
    # Prevent deleting the last admin
    if user.role == 'admin':
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count <= 1:
            return jsonify({'error': 'Cannot delete the last admin account'}), 400
            
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted successfully'}), 200
