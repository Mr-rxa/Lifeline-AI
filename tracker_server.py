from flask import Flask, request, jsonify, render_template_string





import csv, time, os, json, traceback, uuid
import requests
from datetime import datetime

app = Flask(__name__)
CSV_FILE = 'live_positions.csv'

# In-memory storage for active ambulances and notifications
ambulances = {}
notifications_log = []
hospitals_cache = []
positions_log = {}  # per-ambulance recent path points
WEBHOOK_URLS = [u.strip() for u in os.getenv('WEBHOOK_URLS', '').split(',') if u.strip()]

# Create CSV file with header if missing
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'lat', 'lon', 'speed_kmph', 'ts', 'emergency', 'status'])

def load_hospitals():
    """Load hospitals from CSV"""
    global hospitals_cache
    try:
        with open('hospitals.csv', 'r') as f:
            reader = csv.DictReader(f)
            hospitals_cache = list(reader)
    except:
        hospitals_cache = []

load_hospitals()

def cleanup_old_positions():
    """Remove positions older than 5 minutes (300 seconds)"""
    try:
        current_time = time.time()
        rows = []
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, 'r') as f:
                reader = csv.DictReader(f)
                rows = [r for r in reader if r.get('ts') and (current_time - float(r.get('ts', 0))) < 300]
        
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['id', 'lat', 'lon', 'speed_kmph', 'ts', 'emergency', 'status'])
            writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        print(f"Cleanup error: {str(e)}")

def find_nearest_hospital(lat, lon):
    """Find nearest hospital"""
    if not hospitals_cache:
        load_hospitals()
    
    min_dist = float('inf')
    nearest = None
    for hosp in hospitals_cache:
        try:
            from utils import haversine
            dist = haversine(float(lat), float(lon), float(hosp['lat']), float(hosp['lon']))
            if dist < min_dist:
                min_dist = dist
                nearest = hosp
        except:
            pass
    
    return nearest, min_dist

def notify_hospitals(ambulance_id, lat, lon, speed, status):
    """Create notification for nearby hospitals"""
    nearest, distance = find_nearest_hospital(lat, lon)
    
    if nearest:
        notification = {
            'timestamp': datetime.now().isoformat(),
            'ambulance_id': ambulance_id,
            'location': f"{lat:.4f}, {lon:.4f}",
            'speed_kmph': float(speed),
            'status': status,
            'nearest_hospital': nearest['name'],
            'distance_km': round(distance, 2),
            'eta_minutes': round((distance / 60) * 60, 1)
        }
        notifications_log.append(notification)
        
        # Keep only last 50 notifications
        if len(notifications_log) > 50:
            notifications_log.pop(0)
        
        print(f"🚑 ALERT: {ambulance_id} -> {nearest['name']} ({distance:.1f}km away)")
        broadcast_webhooks(notification)
        return notification
    
    return None

def broadcast_webhooks(notification):
    """Send notification to configured webhook URLs (best effort)."""
    if not WEBHOOK_URLS:
        return
    for url in WEBHOOK_URLS:
        try:
            requests.post(url, json=notification, timeout=2)
        except Exception as e:
            print(f"Webhook error to {url}: {e}")

def update_csv(aid, lat, lon, speed, ts, emergency='normal', status='active'):
    cleanup_old_positions()  # Remove stale data
    
    rows = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

    # Remove old entry for this ambulance
    rows = [r for r in rows if r['id'] != aid]
    rows.append({
        'id': aid,
        'lat': str(lat),
        'lon': str(lon),
        'speed_kmph': str(speed),
        'ts': str(ts),
        'emergency': emergency,
        'status': status
    })

    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'lat', 'lon', 'speed_kmph', 'ts', 'emergency', 'status'])
        writer.writeheader()
        writer.writerows(rows)

@app.route('/update_location', methods=['POST'])
def update_location():
    """Update ambulance location and send hospital notifications"""
    try:
        raw_body = request.get_data(as_text=True)
        data = request.get_json(force=True, silent=True)
        if not data:
          print(f"Invalid JSON body: {raw_body}")
          return jsonify({'error': 'Invalid JSON', 'body': raw_body, 'status': 'error'}), 400
        
        aid = data.get('id', 'AMB-' + str(uuid.uuid4())[:8])
        lat = float(data.get('lat', 28.6139))
        lon = float(data.get('lon', 77.2090))
        speed = float(data.get('speed_kmph', 0))
        emergency = data.get('emergency', 'normal')
        status = 'in_transit' if speed > 5 else 'stationary'
        ts = time.time()

        # Update ambulances dictionary
        ambulances[aid] = {
            'id': aid,
            'lat': lat,
            'lon': lon,
            'speed': speed,
            'status': status,
            'emergency': emergency,
            'last_update': ts
        }

        # Track recent path for each ambulance (last 50 points)
        if aid not in positions_log:
          positions_log[aid] = []
        positions_log[aid].append({'lat': lat, 'lon': lon, 'ts': ts})
        if len(positions_log[aid]) > 50:
          positions_log[aid] = positions_log[aid][-50:]
        
        # Send hospital notification
        notification = notify_hospitals(aid, lat, lon, speed, status)
        
        # Save to CSV
        rows = []
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, 'r') as f:
                reader = csv.DictReader(f)
                rows = [r for r in reader if r.get('id') != aid]
        
        rows.append({
            'id': aid,
            'lat': str(lat),
            'lon': str(lon),
            'speed_kmph': str(speed),
            'ts': str(ts),
            'emergency': emergency,
            'status': status
        })
        
        if len(rows) > 50:
            rows = rows[-50:]
        
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['id', 'lat', 'lon', 'speed_kmph', 'ts', 'emergency', 'status'])
            writer.writeheader()
            writer.writerows(rows)
        
        return jsonify({
            'status': 'ok',
            'ambulance_id': aid,
            'notification': notification,
            'path': positions_log.get(aid, [])
        }), 200
    
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON', 'status': 'error'}), 400
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}, {'status': 'error'}), 400

@app.route('/api/ambulances', methods=['GET'])
def get_ambulances():
    """Get all active ambulances"""
    enriched = []
    for aid, data in ambulances.items():
        item = dict(data)
        item['path'] = positions_log.get(aid, [])
        enriched.append(item)
    return jsonify(enriched), 200

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    """Get recent notifications"""
    limit = request.args.get('limit', 20, type=int)
    return jsonify(notifications_log[-limit:] if notifications_log else []), 200

@app.route('/trigger_alert', methods=['POST'])
def trigger_alert():
  """Manually trigger notification for an ambulance by id."""
  try:
    data = request.get_json(force=True, silent=True) or {}
    aid = data.get('id')
    if not aid or aid not in ambulances:
      return jsonify({'error': 'ambulance id not found', 'status': 'error'}), 404

    amb = ambulances[aid]
    notification = notify_hospitals(
      aid,
      amb.get('lat'),
      amb.get('lon'),
      amb.get('speed', 0),
      amb.get('status', 'stationary')
    )

    return jsonify({
      'status': 'ok',
      'ambulance_id': aid,
      'notification': notification
    }), 200
  except Exception as e:
    return jsonify({'error': str(e), 'status': 'error'}), 400

@app.route('/api/alerts/nearby', methods=['GET'])
def get_alerts_nearby():
  """Return ambulances within radius_km of given lat/lon for citizen alerts."""
  try:
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    radius = float(request.args.get('radius_km', 2.0))
  except Exception:
    return jsonify({'error': 'lat, lon required'}), 400

  results = []
  for amb in ambulances.values():
    try:
      from utils import haversine
      dist = haversine(lat, lon, amb['lat'], amb['lon'])
      if dist <= radius:
        eta_minutes = round((dist / max(amb.get('speed', 10) or 10, 10)) * 60, 1)
        entry = dict(amb)
        entry['distance_km'] = round(dist, 2)
        entry['eta_minutes'] = eta_minutes
        results.append(entry)
    except Exception as e:
      print(f"alerts_nearby error: {e}")
      continue

  # Sort closest first
  results.sort(key=lambda x: x.get('distance_km', 0))
  return jsonify({'count': len(results), 'radius_km': radius, 'ambulances': results}), 200

@app.route('/api/hospitals/nearest', methods=['GET'])
def get_nearest_hospital():
    """Get nearest hospital for coordinates"""
    try:
        lat = float(request.args.get('lat', 28.6139))
        lon = float(request.args.get('lon', 77.2090))
        
        nearest, distance = find_nearest_hospital(lat, lon)
        
        return jsonify({
            'hospital': nearest,
            'distance_km': round(distance, 2),
            'eta_minutes': round((distance / 60) * 60, 1)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Serve GPS sender page at root and /ambulance for nginx proxy
@app.route('/')
@app.route('/ambulance')
def serve_gps_sender():
    return """
    <!DOCTYPE html>
    <html>
    <head>
      <title>🚑 LifeLine AI - Ambulance Tracker</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          min-height: 100vh;
          padding: 20px;
        }
        .container { 
          max-width: 500px; 
          margin: 0 auto;
          background: white;
          border-radius: 20px;
          box-shadow: 0 20px 60px rgba(0,0,0,0.3);
          overflow: hidden;
        }
        .header {
          background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
          color: white;
          padding: 30px 20px;
          text-align: center;
        }
        .header h1 { font-size: 24px; margin-bottom: 5px; }
        .header p { opacity: 0.9; font-size: 14px; }
        
        .content { padding: 20px; }
        
        .card {
          background: #f8f9fa;
          border-radius: 12px;
          padding: 15px;
          margin-bottom: 15px;
        }
        
        .card h3 { 
          font-size: 14px; 
          color: #666; 
          margin-bottom: 8px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        
        .card-value {
          font-size: 18px;
          font-weight: bold;
          color: #333;
          word-break: break-all;
        }
        
        .coords { 
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
        }
        
        .coord-item {
          background: white;
          padding: 12px;
          border-radius: 8px;
          text-align: center;
        }
        
        .coord-label {
          font-size: 11px;
          color: #999;
          text-transform: uppercase;
        }
        
        .coord-value {
          font-size: 16px;
          font-weight: bold;
          color: #333;
          margin-top: 5px;
        }
        
        .status {
          padding: 12px;
          border-radius: 8px;
          margin-bottom: 15px;
          font-weight: 500;
          text-align: center;
        }
        
        .status.success {
          background: #d4edda;
          color: #155724;
          border: 2px solid #c3e6cb;
        }
        
        .status.error {
          background: #f8d7da;
          color: #721c24;
          border: 2px solid #f5c6cb;
        }
        
        .status.warning {
          background: #fff3cd;
          color: #856404;
          border: 2px solid #ffeaa7;
        }
        
        .emergency-buttons {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
          margin-bottom: 15px;
        }
        
        button {
          padding: 15px;
          border: none;
          border-radius: 10px;
          font-size: 16px;
          font-weight: bold;
          cursor: pointer;
          transition: all 0.3s;
        }
        
        button:active {
          transform: scale(0.95);
        }
        
        .btn-critical {
          background: #dc3545;
          color: white;
        }
        
        .btn-urgent {
          background: #ffc107;
          color: #333;
        }
        
        .btn-normal {
          background: #28a745;
          color: white;
        }
        
        .btn-arrived {
          background: #6c757d;
          color: white;
        }
        
        .pulse {
          animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        
        .info-box {
          background: #e3f2fd;
          padding: 15px;
          border-radius: 10px;
          border-left: 4px solid #2196f3;
          margin-top: 15px;
        }
        
        .info-box h4 {
          color: #1976d2;
          margin-bottom: 8px;
          font-size: 14px;
        }
        
        .info-box p {
          color: #555;
          font-size: 13px;
          line-height: 1.6;
        }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>🚑 LifeLine AI</h1>
          <p>Real-Time Ambulance Tracking System</p>
        </div>
        
        <div class="content">
          <div class="card">
            <h3>🆔 Device ID</h3>
            <div class="card-value" id="deviceId">Initializing...</div>
          </div>
          
          <div class="card">
            <h3>📍 Live Location</h3>
            <div class="coords">
              <div class="coord-item">
                <div class="coord-label">Latitude</div>
                <div class="coord-value" id="lat">--</div>
              </div>
              <div class="coord-item">
                <div class="coord-label">Longitude</div>
                <div class="coord-value" id="lon">--</div>
              </div>
              <div class="coord-item">
                <div class="coord-label">Speed</div>
                <div class="coord-value" id="speed">-- km/h</div>
              </div>
              <div class="coord-item">
                <div class="coord-label">Accuracy</div>
                <div class="coord-value" id="accuracy">-- m</div>
              </div>
            </div>
          </div>
          
          <div id="statusBox"></div>
          
          <div class="card">
            <h3>🚨 Emergency Level</h3>
            <div class="emergency-buttons">
              <button class="btn-critical" onclick="setEmergency('critical')">🚨 CRITICAL</button>
              <button class="btn-urgent" onclick="setEmergency('urgent')">⚠️ URGENT</button>
              <button class="btn-normal" onclick="setEmergency('normal')">✅ NORMAL</button>
              <button class="btn-arrived" onclick="setStatus('arrived')">🏥 ARRIVED</button>
              <button class="btn-normal" style="background:#007bff" onclick="triggerAlert()">📢 Notify Nearby</button>
            </div>
          </div>
          
          <div id="hospitalInfo"></div>
        </div>
      </div>

      <script>
        const SERVER_URL = window.location.origin;
        let currentEmergency = 'normal';
        let currentStatus = 'active';
        let deviceId = null;
        
        // Generate unique device ID based on browser fingerprint
        function generateDeviceId() {
          const nav = navigator;
          const screen = window.screen;
          const fingerprint = [
            nav.userAgent,
            nav.language,
            screen.colorDepth,
            screen.width + 'x' + screen.height,
            new Date().getTimezoneOffset(),
            !!window.sessionStorage,
            !!window.localStorage
          ].join('|');
          
          // Simple hash function
          let hash = 0;
          for (let i = 0; i < fingerprint.length; i++) {
            const char = fingerprint.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
          }
          
          const storedId = localStorage.getItem('ambulance_device_id');
          if (storedId) {
            return storedId;
          }
          
          const newId = 'AMB-' + Math.abs(hash).toString(36).toUpperCase().substring(0, 8);
          localStorage.setItem('ambulance_device_id', newId);
          return newId;
        }
        
        deviceId = generateDeviceId();
        document.getElementById('deviceId').innerText = deviceId;
        
        function setEmergency(level) {
          currentEmergency = level;
          showStatus(`Emergency level set to: ${level.toUpperCase()}`, 'warning');
        }
        
        function setStatus(status) {
          currentStatus = status;
          if (status === 'arrived') {
            showStatus('✅ Marked as ARRIVED at hospital', 'success');
          }
        }
        
        function showStatus(message, type = 'success') {
          const box = document.getElementById('statusBox');
          box.innerHTML = `<div class="status ${type}">${message}</div>`;
        }
        
        function showHospitalInfo(data) {
          const info = document.getElementById('hospitalInfo');
          info.innerHTML = `
            <div class="info-box">
              <h4>🏥 Nearest Hospital</h4>
              <p><strong>${data.nearest_hospital}</strong></p>
              <p>📏 Distance: ${data.distance_km} km</p>
              <p>⏱️ ETA: ${data.eta_minutes} minutes</p>
            </div>
          `;
        }

        function sendLocation(lat, lon, speed, accuracy) {
          const payload = { 
            id: deviceId,
            lat: lat, 
            lon: lon, 
            speed_kmph: speed || 0,
            emergency: currentEmergency,
            status: currentStatus
          };

          fetch(SERVER_URL + "/update_location", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          })
          .then(res => res.json())
          .then(data => {
            const time = new Date().toLocaleTimeString();
            showStatus(`✅ Location sent successfully at ${time}`, 'success');
            if (data && data.notification) {
              showHospitalInfo(data.notification);
            } else if (data && data.nearest_hospital) {
              showHospitalInfo(data);
            } else {
              showStatus('✅ Location updated, waiting for nearest hospital info...', 'warning');
            }
          })
          .catch(err => {
            showStatus(`❌ Error: ${err.message}`, 'error');
          });
        }

        function triggerAlert() {
          fetch(SERVER_URL + "/trigger_alert", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: deviceId })
          })
          .then(res => res.json())
          .then(data => {
            if (data && data.notification) {
              showStatus('📢 Alert sent to nearby hospitals', 'success');
              showHospitalInfo(data.notification);
            } else {
              showStatus('⚠️ Alert sent, waiting for hospital response', 'warning');
            }
          })
          .catch(err => {
            showStatus(`❌ Alert error: ${err.message}`, 'error');
          });
        }

        function success(pos) {
          const lat = pos.coords.latitude.toFixed(6);
          const lon = pos.coords.longitude.toFixed(6);
          const speed = pos.coords.speed ? (pos.coords.speed * 3.6).toFixed(1) : 0;
          const accuracy = pos.coords.accuracy ? pos.coords.accuracy.toFixed(0) : 'N/A';

          document.getElementById('lat').innerText = lat;
          document.getElementById('lon').innerText = lon;
          document.getElementById('speed').innerText = speed;
          document.getElementById('accuracy').innerText = accuracy;
          
          sendLocation(lat, lon, speed, accuracy);
        }

        function error(err) {
          showStatus(`⚠️ GPS Error: ${err.message}`, 'error');
          console.warn("GPS error:", err);
        }

        if ("geolocation" in navigator) {
          showStatus('🔄 Acquiring GPS location...', 'warning');
          navigator.geolocation.watchPosition(success, error, {
            enableHighAccuracy: true,
            maximumAge: 0,
            timeout: 10000
          });
        } else {
          showStatus('❌ Geolocation not supported', 'error');
        }
      </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
