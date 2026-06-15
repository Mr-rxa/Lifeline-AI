from flask import Blueprint, request, jsonify
from extensions import db, bcrypt
from models import User, SystemConfig
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
import datetime

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/setup/status', methods=['GET'])
def setup_status():
    config = SystemConfig.query.first()
    return jsonify({'setup_complete': config.setup_complete if config else False}), 200

@auth_bp.route('/setup/complete', methods=['POST'])
def setup_complete():
    config = SystemConfig.query.first()
    if config and config.setup_complete:
        return jsonify({'error': 'Setup already completed'}), 400

    data = request.get_json()
    if not data or not data.get('username') or not data.get('password') or not data.get('email'):
        return jsonify({'error': 'Missing required fields'}), 400

    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    admin_user = User(
        username=data['username'],
        email=data['email'],
        password_hash=hashed_password,
        role='admin',
        status='active'
    )
    db.session.add(admin_user)
    
    if not config:
        config = SystemConfig(setup_complete=True)
        db.session.add(config)
    else:
        config.setup_complete = True
        
    db.session.commit()
    return jsonify({'message': 'Setup completed successfully'}), 200

@auth_bp.route('/register', methods=['POST'])
def register():
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
        role=data.get('role', 'dispatcher')
    )
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'User registered successfully'}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Missing required fields'}), 400

    user = User.query.filter_by(username=data['username']).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, data['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
        
    if user.status != 'active':
        return jsonify({'error': 'Account is suspended'}), 403

    user.last_login = datetime.datetime.utcnow()
    db.session.commit()

    access_token = create_access_token(
        identity=str(user.id), 
        additional_claims={'role': user.role, 'username': user.username}, 
        expires_delta=datetime.timedelta(days=1)
    )
    return jsonify({
        'access_token': access_token,
        'user': {
            'id': user.id,
            'username': user.username,
            'role': user.role
        }
    }), 200

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    # Since we are using standard JWTs without a blocklist right now, 
    # actual logout is primarily client-side token deletion.
    # A successful 200 response tells the client to drop the token.
    return jsonify({'message': 'Successfully logged out'}), 200

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    if not data or not data.get('email'):
        return jsonify({'error': 'Email required'}), 400
        
    user = User.query.filter_by(email=data['email']).first()
    # Always return 200 to prevent email enumeration
    if user:
        # Mocking email send here
        print(f"Password reset link generated for {user.email}")
        
    return jsonify({'message': 'If your email is registered, a reset link has been sent.'}), 200

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    # In a real app, you would validate a secure token here instead of just taking the username
    if not data or not data.get('username') or not data.get('new_password'):
        return jsonify({'error': 'Missing required fields'}), 400
        
    user = User.query.filter_by(username=data['username']).first()
    if not user:
        return jsonify({'error': 'Invalid request'}), 400
        
    user.password_hash = bcrypt.generate_password_hash(data['new_password']).decode('utf-8')
    db.session.commit()
    
    return jsonify({'message': 'Password reset successfully'}), 200

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_me():
    user_id = get_jwt_identity()
    claims = get_jwt()
    return jsonify({'id': user_id, 'role': claims.get('role'), 'username': claims.get('username')}), 200
