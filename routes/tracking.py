from flask import Blueprint, request, jsonify, Response
from extensions import db
from models import Ambulance, TrackingLog
from flask_jwt_extended import jwt_required
import json
import time

track_bp = Blueprint('tracking', __name__)

# Basic in-memory store for active live positions to avoid hitting DB on every tick for SSE
live_positions = {}
# Global notifications queue (last 20 notifications)
recent_notifications = []

def add_notification(message, type="info"):
    recent_notifications.insert(0, {
        "id": int(time.time() * 1000),
        "message": message,
        "type": type,
        "timestamp": time.time()
    })
    if len(recent_notifications) > 20:
        recent_notifications.pop()

@track_bp.route('/update', methods=['POST'])
@jwt_required()
def update_location():
    data = request.get_json()
    amb_id = data.get('ambulance_id')
    lat = data.get('lat')
    lon = data.get('lon')
    speed = data.get('speed', 0)
    
    if not all([amb_id, lat, lon]):
        return jsonify({'error': 'Missing tracking data'}), 400
        
    amb = Ambulance.query.get(amb_id)
    if amb:
        amb.last_lat = float(lat)
        amb.last_lon = float(lon)
        
        live_positions[amb_id] = {
            'lat': lat,
            'lon': lon,
            'speed': speed,
            'status': amb.status,
            'timestamp': time.time()
        }
        
        # Periodically save to TrackingLog
        log = TrackingLog(ambulance_id=amb_id, lat=lat, lon=lon, speed=speed)
        db.session.add(log)
        db.session.commit()
        
    return jsonify({'status': 'ok'}), 200

@track_bp.route('/stream', methods=['GET'])
def stream():
    def event_stream():
        while True:
            # Yield current positions and notifications as SSE
            payload = {
                "positions": live_positions,
                "notifications": recent_notifications
            }
            yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(2) # Send update every 2 seconds
            
    return Response(event_stream(), mimetype="text/event-stream")
