import os as _os
if _os.getenv("GEVENT_ENABLED", "0") == "1":
    from gevent import monkey
    monkey.patch_all()

import json
import os
import time
import uuid
import queue
import threading
from datetime import datetime, timedelta
import dash
from flask import Flask, redirect, request, jsonify, Response
from dash import dcc, html
from dash.dependencies import Output, Input, State
import plotly.graph_objs as go
import pandas as pd
import csv
import requests
from utils import haversine
import dashboard_registry as reg

# Single reentrant lock for all in-memory shared state
_state_lock = threading.RLock()

# ==== CONFIG ====
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
# =================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, 'live_positions.csv')

# Load hospital data
hospitals_df = pd.read_csv(os.path.join(BASE_DIR, 'hospitals.csv'))

# In-memory stores
ambulances_store = {}
notifications_log = []
positions_log = {}
incident_log = []

shared_route_state = {
    'active_ambulance': None,
    'destination': None,
    'route': [],
    'route_polyline': [],
    'siren_active': False,
    'siren_expires': None,
    'emergency': 'normal',
    'distance_km': None,
    'eta_minutes': None,
    'last_update': None,
}

_last_route_build_pos = {'lat': None, 'lon': None}

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'lat', 'lon', 'speed_kmph', 'ts', 'emergency', 'status'])


def load_hospitals():
    try:
        df = pd.read_csv(os.path.join(BASE_DIR, 'hospitals.csv'))
        return df
    except Exception:
        return pd.DataFrame(columns=['name', 'lat', 'lon'])


def cleanup_old_positions():
    try:
        current_time = time.time()
        rows = []
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, 'r') as f:
                reader = csv.DictReader(f)
                rows = [r for r in reader if r.get('ts') and (current_time - float(r.get('ts', 0))) < 300]

        with _state_lock:
            with open(CSV_FILE, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['id', 'lat', 'lon', 'speed_kmph', 'ts', 'emergency', 'status'])
                writer.writeheader()
                writer.writerows(rows)
    except Exception:
        pass


def periodic_csv_cleanup():
    while True:
        time.sleep(300)
        cleanup_old_positions()

threading.Thread(target=periodic_csv_cleanup, daemon=True).start()


def find_nearest_hospital(lat, lon):
    hospital_frame = hospitals_df
    if hospital_frame is None or hospital_frame.empty:
        hospital_frame = load_hospitals()

    min_dist = float('inf')
    nearest = None
    for _, hosp in hospital_frame.iterrows():
        try:
            dist = haversine(float(lat), float(lon), float(hosp['lat']), float(hosp['lon']))
            if dist < min_dist:
                min_dist = dist
                nearest = hosp
        except Exception:
            pass

    return nearest, min_dist


def notify_hospitals(ambulance_id, lat, lon, speed, status):
    nearest, distance = find_nearest_hospital(lat, lon)
    if nearest is None:
        return None

    notification = {
        'timestamp': datetime.now().isoformat(),
        'ambulance_id': ambulance_id,
        'location': f"{lat:.4f}, {lon:.4f}",
        'speed_kmph': float(speed),
        'status': status,
        'nearest_hospital': nearest['name'],
        'distance_km': round(distance, 2),
        'eta_minutes': max(1, round((distance / 50) * 60, 1))
    }
    with _state_lock:
        notifications_log.append(notification)
        if len(notifications_log) > 50:
            notifications_log.pop(0)

    return notification


def update_csv(aid, lat, lon, speed, ts, emergency='normal', status='active'):
    try:
        with _state_lock:
            with open(CSV_FILE, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['id', 'lat', 'lon', 'speed_kmph', 'ts', 'emergency', 'status'])
                writer.writerow({
                    'id': aid,
                    'lat': str(lat),
                    'lon': str(lon),
                    'speed_kmph': str(speed),
                    'ts': str(ts),
                    'emergency': emergency,
                    'status': status
                })
    except Exception:
        pass


def get_route_coords(lat1, lon1, lat2, lon2):
    """Fetch real turn-by-turn driving route geometry using OSRM or OpenRouteService."""
    if ORS_API_KEY:
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {"Authorization": ORS_API_KEY}
        params = {"start": f"{lon1},{lat1}", "end": f"{lon2},{lat2}"}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=4)
            if r.status_code == 200:
                data = r.json()
                coords = data['features'][0]['geometry']['coordinates']
                return [[c[1], c[0]] for c in coords]
        except Exception as e:
            print("ORS route error:", e)

    # Free Public OSRM API for real road routes (no API key required)
    try:
        osrm_url = f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
        r = requests.get(osrm_url, timeout=3)
        if r.status_code == 200:
            data = r.json()
            if data.get('routes') and len(data['routes']) > 0:
                coords = data['routes'][0]['geometry']['coordinates']
                return [[c[1], c[0]] for c in coords]
    except Exception:
        pass

    # Fallback to straight line segment
    return [[lat1, lon1], [lat2, lon2]]



def build_shared_route(lat, lon, ambulance_id, emergency='normal'):
    nearest, distance = find_nearest_hospital(lat, lon)
    destination = nearest['name'] if nearest is not None else 'Nearest hospital'
    h_lat = float(nearest['lat']) if nearest is not None else lat
    h_lon = float(nearest['lon']) if nearest is not None else lon

    polyline = get_route_coords(lat, lon, h_lat, h_lon)
    eta = max(1, int(round((distance / 50) * 60))) if distance else 5

    with _state_lock:
        shared_route_state['active_ambulance'] = ambulance_id
        shared_route_state['destination'] = destination
        shared_route_state['emergency'] = emergency
        shared_route_state['distance_km'] = round(distance, 2) if distance else 0
        shared_route_state['eta_minutes'] = eta
        shared_route_state['route'] = [{'lat': lat, 'lon': lon}, {'lat': h_lat, 'lon': h_lon}]
        shared_route_state['route_polyline'] = polyline
        shared_route_state['last_update'] = datetime.now().isoformat()
    return destination, distance


def is_siren_active():
    with _state_lock:
        if not shared_route_state.get('siren_active'):
            return False
        expires = shared_route_state.get('siren_expires')
        if expires:
            try:
                if datetime.fromisoformat(expires) < datetime.now():
                    shared_route_state['siren_active'] = False
                    return False
            except Exception:
                pass
        return True


# Create Dash App
dash_app = dash.Dash(__name__, routes_pathname_prefix='/dashboard/')
server = dash_app.server
app = server
application = app

server.static_folder = os.path.join(BASE_DIR, 'static')
_landing_html = None


@server.route('/')
def landing_page():
    global _landing_html
    with _state_lock:
        if _landing_html is None:
            with open(os.path.join(BASE_DIR, 'index.html'), 'r', encoding='utf-8') as f:
                _landing_html = f.read()
    return _landing_html, 200, {'Content-Type': 'text/html; charset=utf-8'}


@server.route('/dashboard')
def dashboard_redirect():
    return redirect('/dashboard/', code=302)


def parse_update_payload():
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    if request.form:
        return request.form.to_dict()
    raw_body = request.get_data(as_text=True)
    if raw_body:
        try:
            parsed = json.loads(raw_body)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


# -------------------------------------------------------------------
# AMBULANCE INTERFACE ROUTE (/ambulance) - REAL GPS TELEMETRY
# -------------------------------------------------------------------
@server.route('/ambulance')
def ambulance_interface():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <title>LifeLine AI — Ambulance Dispatch</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    :root {
      --bg-beige: #f6eee3;
      --card-bg: rgba(255, 250, 243, 0.92);
      --card-border: rgba(180, 140, 100, 0.22);
      --text-main: #2c221e;
      --text-muted: #7a6859;
      --accent-red: #d93829;
      --accent-amber: #e08b2b;
      --accent-green: #16a34a;
      --accent-blue: #1d4ed8;
      --shadow-soft: 0 14px 35px rgba(110, 80, 50, 0.12);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', sans-serif;
      background: radial-gradient(circle at 50% 0%, #fbf5eb 0%, #f0e4d2 100%);
      color: var(--text-main);
      min-height: 100vh;
      padding: 12px;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    .app-container {
      width: min(100%, 540px);
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .header {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      padding: 14px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      box-shadow: var(--shadow-soft);
    }
    .logo { font-size: 1.25rem; font-weight: 900; color: var(--accent-red); }
    .status-badge { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; font-weight: 700; color: var(--accent-green); background: rgba(22, 163, 74, 0.1); padding: 5px 12px; border-radius: 999px; border: 1px solid rgba(22,163,74,0.25); }
    .status-badge.searching { color: var(--accent-amber); background: rgba(224,139,43,0.1); border-color: rgba(224,139,43,0.25); }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent-green); box-shadow: 0 0 8px var(--accent-green); animation: pulse 1.5s infinite; }
    .dot.amber { background: var(--accent-amber); box-shadow: 0 0 8px var(--accent-amber); }
    @keyframes pulse { 0%, 100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.4); opacity: 0.6; } }

    .map-card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      overflow: hidden;
      box-shadow: var(--shadow-soft);
    }
    #map { height: 250px; width: 100%; background: #eae2d6; }

    .card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      padding: 16px;
      box-shadow: var(--shadow-soft);
    }
    .card-title { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-muted); margin-bottom: 8px; font-weight: 700; }
    
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .metric-box { background: rgba(255,255,255,0.7); border: 1px solid rgba(180,140,100,0.15); padding: 10px; border-radius: 14px; text-align: center; }
    .metric-val { font-family: 'JetBrains Mono', monospace; font-size: 1.05rem; font-weight: 700; color: var(--text-main); }
    .metric-lbl { font-size: 0.7rem; color: var(--text-muted); margin-top: 2px; }

    .emergency-selector { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 8px; }
    .btn-level {
      padding: 12px 8px; border-radius: 14px; border: 1px solid transparent; font-weight: 800; font-size: 0.8rem; cursor: pointer; text-align: center; transition: all 0.2s ease;
      background: rgba(255,255,255,0.7); color: var(--text-muted); opacity: 0.7;
    }
    .btn-level.active { opacity: 1; transform: scale(1.03); box-shadow: 0 4px 15px rgba(0,0,0,0.08); }
    .btn-normal.active { background: rgba(22, 163, 74, 0.15); border-color: var(--accent-green); color: var(--accent-green); }
    .btn-urgent.active { background: rgba(224, 139, 43, 0.15); border-color: var(--accent-amber); color: var(--accent-amber); }
    .btn-critical.active { background: rgba(217, 56, 41, 0.15); border-color: var(--accent-red); color: var(--accent-red); }

    .btn-siren {
      width: 100%;
      padding: 18px;
      border-radius: 18px;
      border: none;
      background: linear-gradient(135deg, #d93829 0%, #b82518 100%);
      color: white;
      font-size: 1.05rem;
      font-weight: 900;
      letter-spacing: 0.04em;
      cursor: pointer;
      box-shadow: 0 10px 25px rgba(217, 56, 41, 0.35);
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
    }
    .btn-siren:active { transform: scale(0.97); }

    .action-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .btn-sec { padding: 12px; border-radius: 14px; border: 1px solid var(--card-border); background: rgba(255,255,255,0.8); color: var(--text-main); font-weight: 700; font-size: 0.85rem; cursor: pointer; }

    .toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #2c221e; border: 1px solid var(--accent-amber); padding: 12px 20px; border-radius: 999px; font-size: 0.85rem; font-weight: 600; color: #fff; box-shadow: 0 10px 30px rgba(0,0,0,0.3); z-index: 9999; display: none; }
  </style>
</head>
<body>
  <div class="app-container">
    <div class="header">
      <div class="logo">🚑 LifeLine AI</div>
      <div class="status-badge searching" id="gpsBadge"><div class="dot amber" id="gpsDot"></div> ACQUIRING GPS</div>
    </div>

    <!-- Synchronized Leaflet Map -->
    <div class="map-card">
      <div id="map"></div>
    </div>

    <!-- Live Telemetry Card -->
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
        <span class="card-title" style="margin:0;">Vehicle ID</span>
        <input id="ambId" value="AMB-01" style="background:transparent; border:none; color:var(--accent-amber); font-weight:800; font-family:'JetBrains Mono'; text-align:right; width:90px; outline:none;" />
      </div>
      <div class="grid-2">
        <div class="metric-box">
          <div class="metric-val" id="dispLat">Acquiring...</div>
          <div class="metric-lbl">LATITUDE</div>
        </div>
        <div class="metric-box">
          <div class="metric-val" id="dispLon">Acquiring...</div>
          <div class="metric-lbl">LONGITUDE</div>
        </div>
        <div class="metric-box">
          <div class="metric-val" id="dispSpeed">0 km/h</div>
          <div class="metric-lbl">REAL-TIME SPEED</div>
        </div>
        <div class="metric-box">
          <div class="metric-val" id="dispHospital">Finding...</div>
          <div class="metric-lbl">NEAREST HOSPITAL</div>
        </div>
      </div>
    </div>

    <!-- Emergency Level Selector -->
    <div class="card">
      <div class="card-title">Select Emergency Priority</div>
      <div class="emergency-selector">
        <button class="btn-level btn-normal active" onclick="setEmergency('normal', this)">NORMAL</button>
        <button class="btn-level btn-urgent" onclick="setEmergency('urgent', this)">URGENT</button>
        <button class="btn-level btn-critical" onclick="setEmergency('critical', this)">CRITICAL</button>
      </div>
    </div>

    <!-- Trigger Siren Button -->
    <button class="btn-siren" onclick="triggerSirenRemote()">
      <span>🚨</span> TRIGGER SIREN ON DASHBOARD
    </button>

    <div class="action-row">
      <button class="btn-sec" onclick="triggerAlertRemote()">📢 Notify Nearby</button>
      <button class="btn-sec" style="border-color:rgba(22,163,74,0.4);" onclick="markArrived()">🏥 Mark Arrived</button>
    </div>

    <div style="text-align:center; font-size:0.78rem; color:var(--text-muted); margin-top:4px;" id="dashWatcherCount">
      👮 Checking active control dashboards...
    </div>
  </div>

  <div id="toast" class="toast">Update sent</div>

  <script>
    let currentEmergency = 'normal';
    let currentLat = null, currentLon = null, currentSpeed = 0;
    let prevLat = null, prevLon = null, prevTime = null;
    let map, ambMarker, polylineLayer;

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 3000);
    }

    function initMap(initialLat, initialLon) {
      map = L.map('map', { zoomControl: false }).setView([initialLat, initialLon], 13);
      L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 19,
        subdomains: 'abcd'
      }).addTo(map);

      const ambIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background:#d93829; width:16px; height:16px; border-radius:50%; border:3px solid #fff; box-shadow:0 0 10px #d93829;'></div>",
        iconSize: [16, 16],
        iconAnchor: [8, 8]
      });

      ambMarker = L.marker([initialLat, initialLon], { icon: ambIcon }).addTo(map);
    }

    function setEmergency(level, btn) {
      currentEmergency = level;
      document.querySelectorAll('.btn-level').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      sendLocationUpdate();
    }

    function haversineDist(lat1, lon1, lat2, lon2) {
      const R = 6371;
      const toRad = deg => deg * Math.PI / 180;
      const dLat = toRad(lat2 - lat1);
      const dLon = toRad(lon2 - lon1);
      const a = Math.sin(dLat/2)*Math.sin(dLat/2) + Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLon/2)*Math.sin(dLon/2);
      return 2 * R * Math.asin(Math.sqrt(a));
    }

    async function sendLocationUpdate() {
      if (currentLat === null || currentLon === null) return;
      const payload = {
        id: document.getElementById('ambId').value || 'AMB-01',
        lat: currentLat,
        lon: currentLon,
        speed_kmph: currentSpeed,
        emergency: currentEmergency
      };
      try {
        const res = await fetch('/update_location', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === 'ok') {
          syncRoute();
        }
      } catch(e) {
        showToast('⚠️ Network connection issue');
      }
    }

    async function triggerSirenRemote() {
      const aid = document.getElementById('ambId').value || 'AMB-01';
      showToast('🚨 Sending siren signal to control dashboards...');
      try {
        const res = await fetch('/api/siren', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: aid, lat: currentLat || 28.6139, lon: currentLon || 77.2090, emergency: currentEmergency })
        });
        const data = await res.json();
        showToast(`🚨 Siren activated on ${data.notified_dashboards || 0} control dashboard(s)!`);
      } catch(e) {
        showToast('Failed to trigger siren');
      }
    }

    async function triggerAlertRemote() {
      const aid = document.getElementById('ambId').value || 'AMB-01';
      fetch('/trigger_alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: aid })
      }).then(() => showToast('📢 Hospital alert dispatched.'));
    }

    function markArrived() {
      currentSpeed = 0;
      const normalBtn = document.querySelector('.btn-normal');
      if (normalBtn) setEmergency('normal', normalBtn);
      else currentEmergency = 'normal';
      showToast('🏥 Arrived at destination hospital.');
      fetch('/api/route/clear', { method: 'POST' });
    }

    async function syncRoute() {
      try {
        const res = await fetch('/api/route');
        const data = await res.json();
        document.getElementById('dispHospital').textContent = data.destination || 'Finding...';

        if (data.route_polyline && data.route_polyline.length > 0 && map) {
          if (polylineLayer) map.removeLayer(polylineLayer);
          polylineLayer = L.polyline(data.route_polyline, { color: '#d93829', weight: 4, opacity: 0.85 }).addTo(map);
        } else if (polylineLayer && map) {
          map.removeLayer(polylineLayer);
          polylineLayer = null;
        }
      } catch(e) {}
    }

    async function checkDashboardStatus() {
      try {
        const res = await fetch('/api/dashboard/status');
        const data = await res.json();
        const count = data.count || 0;
        document.getElementById('dashWatcherCount').innerHTML = `👮 <strong>${count}</strong> active control dashboard(s) online`;
      } catch(e) {}
    }

    function handleNewPosition(lat, lon, speedFromGps) {
      const now = Date.now();
      currentLat = lat;
      currentLon = lon;

      if (speedFromGps && speedFromGps > 0) {
        currentSpeed = Math.round(speedFromGps * 3.6);
      } else if (prevLat !== null && prevLon !== null && prevTime !== null) {
        const distKm = haversineDist(prevLat, prevLon, lat, lon);
        const hours = (now - prevTime) / 3600000;
        if (hours > 0) {
          currentSpeed = Math.round(distKm / hours);
        }
      }
      prevLat = lat;
      prevLon = lon;
      prevTime = now;

      document.getElementById('dispLat').textContent = currentLat.toFixed(4);
      document.getElementById('dispLon').textContent = currentLon.toFixed(4);
      document.getElementById('dispSpeed').textContent = currentSpeed + ' km/h';

      const b = document.getElementById('gpsBadge');
      b.className = 'status-badge';
      b.innerHTML = '<div class="dot"></div> GPS LOCKED';

      if (!map) {
        initMap(currentLat, currentLon);
      } else {
        if (ambMarker) ambMarker.setLatLng([currentLat, currentLon]);
        map.panTo([currentLat, currentLon]);
      }

      sendLocationUpdate();
    }

    if (navigator.geolocation) {
      navigator.geolocation.watchPosition(pos => {
        handleNewPosition(pos.coords.latitude, pos.coords.longitude, pos.coords.speed);
      }, () => {
        handleNewPosition(28.6139, 77.2090, 42);
      }, { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 });
    } else {
      handleNewPosition(28.6139, 77.2090, 42);
    }

    setTimeout(checkDashboardStatus, 2000);
    setInterval(checkDashboardStatus, 5000);
    setInterval(sendLocationUpdate, 5000);
  </script>
</body>
</html>"""


# -------------------------------------------------------------------
# API ENDPOINTS
# -------------------------------------------------------------------
@server.route('/update_location', methods=['POST'])
def update_location():
    try:
        data = parse_update_payload()
        aid = str(data.get('id') or data.get('ambulance_id') or ('AMB-' + str(uuid.uuid4())[:8])).strip()

        try:
            lat = float(data.get('lat', 28.6139))
        except (TypeError, ValueError):
            lat = 28.6139

        try:
            lon = float(data.get('lon', 77.2090))
        except (TypeError, ValueError):
            lon = 77.2090

        try:
            speed = float(data.get('speed_kmph', 0))
        except (TypeError, ValueError):
            speed = 0

        emergency = str(data.get('emergency') or 'normal')
        status = 'in_transit' if speed > 5 else 'stationary'
        ts = time.time()

        with _state_lock:
            ambulances_store[aid] = {
                'id': aid,
                'lat': lat,
                'lon': lon,
                'speed': speed,
                'status': status,
                'emergency': emergency,
                'last_update': ts
            }
            positions_log.setdefault(aid, []).append({'lat': lat, 'lon': lon, 'ts': ts})
            if len(positions_log[aid]) > 50:
                positions_log[aid] = positions_log[aid][-50:]

            notification = notify_hospitals(aid, lat, lon, speed, status)
            update_csv(aid, lat, lon, speed, ts, emergency, status)

            prev = _last_route_build_pos
            should_rebuild = (
                prev['lat'] is None or
                haversine(prev['lat'], prev['lon'], lat, lon) > 0.2
            )
            if should_rebuild:
                build_shared_route(lat, lon, aid, emergency)
                _last_route_build_pos['lat'] = lat
                _last_route_build_pos['lon'] = lon

            path_copy = list(positions_log.get(aid, []))

        return jsonify({'status': 'ok', 'ambulance_id': aid, 'notification': notification, 'path': path_copy}), 200
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 400


@server.route('/api/siren', methods=['POST'])
def api_siren():
    data = parse_update_payload()
    aid = str(data.get('id') or data.get('ambulance_id') or 'AMB-01').strip()
    lat = float(data.get('lat', 28.6139))
    lon = float(data.get('lon', 77.2090))
    emergency = str(data.get('emergency') or 'critical')

    targets = reg.find_within_radius(lat, lon, radius_km=10)
    if not targets:
        nearest = reg.find_nearest(lat, lon)
        if nearest:
            targets = [nearest]
        else:
            targets = [s['session_id'] for s in reg.all_sessions()]

    event = {
        'type': 'siren_trigger',
        'ambulance_id': aid,
        'emergency': emergency,
        'lat': lat,
        'lon': lon,
        'timestamp': datetime.now().isoformat()
    }

    pushed_count = 0
    for sid in targets:
        target_id = sid if isinstance(sid, str) else sid.get('session_id')
        if target_id and reg.push(target_id, event):
            pushed_count += 1

    with _state_lock:
        shared_route_state['siren_active'] = True
        shared_route_state['last_update'] = datetime.now().isoformat()
        shared_route_state['siren_expires'] = (datetime.now() + timedelta(seconds=60)).isoformat()
        shared_route_state['active_ambulance'] = aid

        incident_log.append({
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'ambulance_id': aid,
            'emergency': emergency,
            'destination': shared_route_state.get('destination', 'Unknown Hospital')
        })
        if len(incident_log) > 50:
            incident_log.pop(0)

    return jsonify({'status': 'ok', 'ambulance_id': aid, 'siren_active': True, 'notified_dashboards': pushed_count}), 200


@server.route('/api/siren/stop', methods=['POST'])
def api_siren_stop():
    with _state_lock:
        shared_route_state['siren_active'] = False
    for s in reg.all_sessions():
        reg.push(s['session_id'], {'type': 'siren_stop'})
    return jsonify({'status': 'ok', 'siren_active': False}), 200


@server.route('/api/route/clear', methods=['POST'])
def api_route_clear():
    with _state_lock:
        shared_route_state['route_polyline'] = []
        shared_route_state['route'] = []
        shared_route_state['active_ambulance'] = None
        shared_route_state['siren_active'] = False
    return jsonify({'status': 'ok'}), 200


@server.route('/api/dashboard/register', methods=['POST'])
def api_dashboard_register():
    data = parse_update_payload()
    sid = data.get('session_id')
    lat = data.get('lat')
    lon = data.get('lon')
    if sid:
        reg.register(sid, lat, lon)
    return jsonify({'status': 'ok', 'session_id': sid, 'active_dashboards': reg.count()}), 200


@server.route('/api/dashboard/ping', methods=['POST'])
def api_dashboard_ping():
    data = parse_update_payload()
    sid = data.get('session_id')
    if sid:
        reg.heartbeat(sid)
    return jsonify({'status': 'ok', 'active_dashboards': reg.count()}), 200


@server.route('/api/dashboard/status', methods=['GET'])
def api_dashboard_status():
    return jsonify({'count': reg.count(), 'dashboards': reg.all_sessions()}), 200


@server.route('/api/events/<session_id>')
def sse_events(session_id):
    def event_stream():
        q = reg.get_queue(session_id)
        yield f"data: {json.dumps({'type': 'connected', 'session_id': session_id})}\n\n"
        while True:
            try:
                msg = q.get(timeout=15)
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"

    return Response(event_stream(), mimetype="text/event-stream", headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })


@server.route('/api/route', methods=['GET'])
def api_route():
    with _state_lock:
        siren_on = is_siren_active()
        return jsonify({
            'active_ambulance': shared_route_state['active_ambulance'],
            'destination': shared_route_state['destination'],
            'route': shared_route_state['route'],
            'route_polyline': shared_route_state['route_polyline'],
            'siren_active': siren_on,
            'emergency': shared_route_state['emergency'],
            'distance_km': shared_route_state['distance_km'],
            'eta_minutes': shared_route_state['eta_minutes'],
            'last_update': shared_route_state['last_update'],
        }), 200


@server.route('/api/alerts/nearby', methods=['GET'])
def get_alerts_nearby():
    try:
        lat = float(request.args.get('lat', 28.6139))
        lon = float(request.args.get('lon', 77.2090))
        radius = float(request.args.get('radius_km', 3.0))
    except Exception:
        return jsonify({'error': 'invalid parameters'}), 400

    results = []
    with _state_lock:
        for amb in ambulances_store.values():
            try:
                dist = haversine(lat, lon, amb['lat'], amb['lon'])
                if dist <= radius:
                    eta_minutes = round((dist / max(amb.get('speed', 40), 10)) * 60, 1)
                    entry = dict(amb)
                    entry['distance_km'] = round(dist, 2)
                    entry['eta_minutes'] = eta_minutes
                    results.append(entry)
            except Exception:
                continue

    results.sort(key=lambda x: x.get('distance_km', 0))
    return jsonify({'count': len(results), 'radius_km': radius, 'ambulances': results}), 200


@server.route('/alert')
def citizen_alert_page():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>LifeLine AI — Citizen Proximity Alert</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; margin: 0; background: #f6eee3; color: #2c221e; min-height: 100vh; display: grid; place-items: center; padding: 16px; }
    .card { width: min(100%, 460px); background: rgba(255, 250, 243, 0.9); backdrop-filter: blur(16px); border: 1px solid rgba(180,140,100,0.2); border-radius: 24px; padding: 28px; box-shadow: 0 15px 40px rgba(110,80,50,0.12); text-align: center; }
    h1 { font-size: 1.5rem; margin-bottom: 8px; font-weight: 900; color: #d93829; }
    .status-card { margin-top: 20px; padding: 20px; border-radius: 18px; background: rgba(255,255,255,0.7); border: 1px solid rgba(180,140,100,0.15); }
    .alert-active { background: rgba(217,56,41,0.12); border-color: rgba(217,56,41,0.3); color: #b82518; }
    .alert-clear { background: rgba(22,163,74,0.12); border-color: rgba(22,163,74,0.3); color: #15803d; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🚨 Citizen Proximity Radar</h1>
    <p style="color:#7a6859; font-size:0.9rem;">Live emergency vehicle proximity status</p>
    <div id="statusCard" class="status-card">Locating nearby emergency services...</div>
  </div>
  <script>
    function checkProximity(lat, lon) {
      fetch(`/api/alerts/nearby?lat=${lat}&lon=${lon}&radius_km=3`)
        .then(r => r.json())
        .then(data => {
          const card = document.getElementById('statusCard');
          if (data.count > 0) {
            const amb = data.ambulances[0];
            card.className = 'status-card alert-active';
            card.innerHTML = `<div style="font-size:2rem; margin-bottom:8px;">🚑 ALERT</div>
              <div style="font-weight:800; font-size:1.2rem;">Ambulance (${amb.id}) Nearby</div>
              <div style="margin-top:6px;">Distance: <strong>${amb.distance_km} km</strong> • ETA: <strong>${amb.eta_minutes} min</strong></div>
              <div style="margin-top:12px; font-size:0.85rem; font-weight:700;">PLEASE CLEAR THE ROAD FOR EMERGENCY VEHICLE PASSAGE</div>`;
          } else {
            card.className = 'status-card alert-clear';
            card.innerHTML = `<div style="font-size:2rem; margin-bottom:8px;">✅</div>
              <div style="font-weight:800; font-size:1.1rem;">Roads Clear</div>
              <div style="margin-top:4px; font-size:0.85rem;">No emergency ambulances active within 3 km radius</div>`;
          }
        });
    }

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(p => checkProximity(p.coords.latitude, p.coords.longitude),
        () => checkProximity(28.6139, 77.2090));
    } else {
      checkProximity(28.6139, 77.2090);
    }
    setInterval(() => {
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(p => checkProximity(p.coords.latitude, p.coords.longitude));
      }
    }, 5000);
  </script>
</body>
</html>"""


@server.route('/api/health', methods=['GET'])
def health_check():
    with _state_lock:
        amb_count = len(ambulances_store)
    return jsonify({'status': 'ok', 'service': 'lifeline-ai', 'ambulances': amb_count, 'dashboards': reg.count()}), 200


@server.route('/api/ambulance', methods=['GET'])
def api_ambulance():
    lat = request.args.get('lat', 28.6139, type=float)
    lon = request.args.get('lon', 77.2090, type=float)
    nearest, distance = find_nearest_hospital(lat, lon)
    eta = max(1, int(round((distance / 50) * 60 if distance else 5)))
    payload = {
        'status': 'ok',
        'nearestHospital': {
            'name': nearest['name'] if nearest is not None else 'No hospital found',
            'lat': float(nearest['lat']) if nearest is not None else None,
            'lon': float(nearest['lon']) if nearest is not None else None,
        },
        'distanceKm': round(distance, 2) if nearest is not None else None,
        'etaMinutes': eta,
        'coordinates': {'lat': lat, 'lon': lon},
    }
    return jsonify(payload), 200


@server.route('/api/ambulances', methods=['GET'])
def api_ambulances():
    enriched = []
    with _state_lock:
        for aid, data in ambulances_store.items():
            item = dict(data)
            item['path'] = positions_log.get(aid, [])
            enriched.append(item)
    return jsonify(enriched), 200


@server.route('/api/notifications', methods=['GET'])
def api_notifications():
    limit = request.args.get('limit', 20, type=int)
    with _state_lock:
        logs = notifications_log[-limit:] if notifications_log else []
    return jsonify(logs), 200


@server.route('/trigger_alert', methods=['POST'])
def trigger_alert():
    data = request.get_json(force=True, silent=True) or {}
    aid = data.get('id')
    with _state_lock:
        if not aid or aid not in ambulances_store:
            return jsonify({'error': 'ambulance id not found', 'status': 'error'}), 404
        amb = ambulances_store[aid]
        notification = notify_hospitals(aid, amb.get('lat', 0), amb.get('lon', 0), amb.get('speed', 0), amb.get('status', 'stationary'))
    return jsonify({'status': 'ok', 'ambulance_id': aid, 'notification': notification}), 200


# -------------------------------------------------------------------
# DASHBOARD INDEX STRING & LAYOUT
# -------------------------------------------------------------------
dash_app.index_string = '''<!DOCTYPE html>
<html lang="en">
    <head>
        {%metas%}
        <title>LifeLine AI — Control Room Dashboard</title>
        {%favicon%}
        {%css%}
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
        <style>
          .audio-prompt { background: #fef3c7; border-bottom: 1px solid #f59e0b; color: #92400e; padding: 10px 20px; display: flex; align-items: center; justify-content: space-between; font-family: 'Inter', sans-serif; }
          .siren-banner { display: none; position: fixed; top: 0; left: 0; right: 0; z-index: 999999; background: linear-gradient(90deg, #d93829, #b82518); color: #ffffff; padding: 14px 24px; align-items: center; justify-content: space-between; font-family: 'Inter', sans-serif; box-shadow: 0 10px 30px rgba(217, 56, 41, 0.4); animation: bannerPulse 1s infinite alternate; }
          @keyframes bannerPulse { 0% { opacity: 0.95; } 100% { opacity: 1.0; } }
        </style>
    </head>
    <body style="margin:0; background:#f6eee3;">
        <!-- Audio Enable Prompt Banner -->
        <div id="audio-unlock-banner" class="audio-prompt">
            <span style="font-weight:700; font-size:13px;">🔊 Click anywhere on this dashboard or tap "Test Siren Audio" to enable loud siren alerts.</span>
            <button id="btn-test-audio" style="background:#d93829; color:#fff; border:none; padding:6px 16px; border-radius:999px; font-weight:800; cursor:pointer; font-size:12px;">🔊 Enable / Test Siren Audio</button>
        </div>

        <!-- Flashing Siren Alert Banner -->
        <div id="siren-alert-banner" class="siren-banner">
            <div>
                <span style="font-weight:900; font-size:1.1rem; letter-spacing:0.05em;">🚨 EMERGENCY SIREN TRIGGERED</span>
                <span id="siren-banner-info" style="margin-left:15px; font-weight:700;"></span>
            </div>
            <button id="btn-stop-siren" style="background:#ffffff; color:#d93829; border:none; padding:8px 18px; border-radius:999px; font-weight:800; cursor:pointer; box-shadow:0 4px 14px rgba(0,0,0,0.2);">🔇 Stop Siren</button>
        </div>

        {%app_entry%}

        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
            <script>
                (function(){
                  const sessionId = 'dash_' + Math.random().toString(36).substring(2, 10);
                  let audioUnlocked = false;
                  let sirenAudio = null;
                  let sirenTimer = null;
                  let fallbackAudioCtx = null;
                  let fallbackOsc = null;
                  let fallbackInterval = null;

                  // 1. Register Session Immediately with fallback coords, update when GPS resolves
                  function registerDashboard(lat, lon) {
                    fetch('/api/dashboard/register', {
                      method: 'POST',
                      headers: {'Content-Type':'application/json'},
                      body: JSON.stringify({ session_id: sessionId, lat: lat, lon: lon })
                    }).then(r => r.json()).then(data => {
                      console.log("Dashboard Registered:", sessionId, data);
                    }).catch(err => console.error("Register Error:", err));
                  }

                  registerDashboard(28.6139, 77.2090);
                  if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition(function(p){
                      registerDashboard(p.coords.latitude, p.coords.longitude);
                    }, function(){});
                  }

                  // 2. Heartbeat ping every 5 seconds
                  setInterval(function(){
                    fetch('/api/dashboard/ping', {
                      method: 'POST',
                      headers: {'Content-Type':'application/json'},
                      body: JSON.stringify({ session_id: sessionId })
                    });
                  }, 5000);

                  // 3. Audio unlock logic
                  function unlockAudio() {
                    if (audioUnlocked) return;
                    if (!sirenAudio) {
                      sirenAudio = new Audio('/static/siren.wav');
                      sirenAudio.loop = true;
                      sirenAudio.volume = 1.0;
                    }
                    audioUnlocked = true;

                    const b = document.getElementById('audio-unlock-banner');
                    if (b) b.style.display = 'none';
                  }

                  window.addEventListener('click', unlockAudio);
                  window.addEventListener('touchstart', unlockAudio);

                  // 4. Synthesized Siren Fallback (guaranteed audio)
                  function playSynthSirenFallback() {
                    stopSynthSirenFallback();
                    const AudioCtx = window.AudioContext || window.webkitAudioContext;
                    if (!AudioCtx) return;
                    fallbackAudioCtx = new AudioCtx();
                    if (fallbackAudioCtx.state === 'suspended') {
                      fallbackAudioCtx.resume();
                    }
                    fallbackOsc = fallbackAudioCtx.createOscillator();
                    const gain = fallbackAudioCtx.createGain();
                    fallbackOsc.type = 'sawtooth';
                    let high = false;
                    fallbackOsc.frequency.setValueAtTime(800, fallbackAudioCtx.currentTime);
                    fallbackInterval = setInterval(function(){
                      if (!fallbackAudioCtx) return;
                      high = !high;
                      fallbackOsc.frequency.linearRampToValueAtTime(high ? 1200 : 750, fallbackAudioCtx.currentTime + 0.35);
                    }, 400);
                    gain.gain.setValueAtTime(0.2, fallbackAudioCtx.currentTime);
                    fallbackOsc.connect(gain);
                    gain.connect(fallbackAudioCtx.destination);
                    fallbackOsc.start();
                  }

                  function stopSynthSirenFallback() {
                    if (fallbackInterval) { clearInterval(fallbackInterval); fallbackInterval = null; }
                    if (fallbackOsc) { try { fallbackOsc.stop(); } catch(e){} fallbackOsc = null; }
                    if (fallbackAudioCtx) { try { fallbackAudioCtx.close(); } catch(e){} fallbackAudioCtx = null; }
                  }

                  // 5. Play / Stop Siren
                  function stopSiren() {
                    if (sirenAudio) {
                      sirenAudio.pause();
                      sirenAudio.currentTime = 0;
                    }
                    stopSynthSirenFallback();
                    if (sirenTimer) {
                      clearTimeout(sirenTimer);
                      sirenTimer = null;
                    }
                    const banner = document.getElementById('siren-alert-banner');
                    if (banner) banner.style.display = 'none';
                    fetch('/api/siren/stop', {
                      method: 'POST',
                      headers: {'Content-Type':'application/json'},
                      body: JSON.stringify({ session_id: sessionId })
                    });
                  }

                  function triggerSirenSound(data) {
                    const banner = document.getElementById('siren-alert-banner');
                    const info = document.getElementById('siren-banner-info');
                    if (banner) {
                      banner.style.display = 'flex';
                      if (info) info.textContent = (data.ambulance_id || 'AMB-01') + ' • Priority: ' + (data.emergency || 'CRITICAL').toUpperCase();
                    }

                    if (!sirenAudio) {
                      sirenAudio = new Audio('/static/siren.wav');
                      sirenAudio.loop = true;
                      sirenAudio.volume = 1.0;
                    }

                    sirenAudio.play().catch(function(err){
                      console.warn("Static audio play failed, using WebAudio synth fallback:", err);
                      playSynthSirenFallback();
                    });

                    if (sirenTimer) clearTimeout(sirenTimer);
                    sirenTimer = setTimeout(stopSiren, 60000);
                  }

                  // Event delegation for test and stop buttons
                  document.addEventListener('click', function(e){
                    if (e.target) {
                      if (e.target.id === 'btn-test-audio') {
                        triggerSirenSound({ ambulance_id: 'TEST-SIREN', emergency: 'CRITICAL' });
                        setTimeout(stopSiren, 3000);
                      } else if (e.target.id === 'btn-stop-siren') {
                        stopSiren();
                      }
                    }
                  });

                  // 6. SSE Event Listener
                  const evtSource = new EventSource('/api/events/' + sessionId);
                  evtSource.onmessage = function(e) {
                    try {
                      const msg = JSON.parse(e.data);
                      console.log("SSE Event Received:", msg);
                      if (msg.type === 'siren_trigger') {
                        triggerSirenSound(msg);
                      } else if (msg.type === 'siren_stop') {
                        stopSiren();
                      }
                    } catch(err) {}
                  };
                })();
            </script>
        </footer>
    </body>
</html>'''

dash_app.layout = html.Div([
    # Warm Beige Header Bar
    html.Div([
        html.Div([
            html.Span('TRAFFIC CONTROL ROOM', style={'display': 'inline-block', 'padding': '5px 12px', 'borderRadius': '999px', 'background': 'rgba(217, 56, 41, 0.12)', 'color': '#d93829', 'fontWeight': '800', 'fontSize': '11px', 'letterSpacing': '0.1em'}),
            html.H1('LifeLine AI', style={'margin': '0', 'fontSize': '28px', 'fontWeight': '900', 'color': '#2c221e'})
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px'}),
        html.Div([
            html.Div('🔴 SYSTEM LIVE', style={'display': 'inline-block', 'padding': '6px 14px', 'borderRadius': '999px', 'background': 'rgba(22, 163, 74, 0.12)', 'color': '#16a34a', 'fontWeight': '700', 'fontSize': '12px', 'border': '1px solid rgba(22,163,74,0.3)'}),
            html.A('📱 Ambulance Device', href='/ambulance', target='_blank', style={'marginLeft': '14px', 'color': '#1d4ed8', 'textDecoration': 'none', 'fontWeight': '700', 'fontSize': '13px'}),
            html.A('🚨 Citizen Radar', href='/alert', target='_blank', style={'marginLeft': '14px', 'color': '#e08b2b', 'textDecoration': 'none', 'fontWeight': '700', 'fontSize': '13px'})
        ], style={'display': 'flex', 'alignItems': 'center'})
    ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'padding': '18px 24px', 'background': 'rgba(255, 250, 243, 0.95)', 'borderBottom': '1px solid rgba(180, 140, 100, 0.2)', 'backdropFilter': 'blur(16px)'}),

    # Main Grid Content
    html.Div([
        # Left Control Sidebar
        html.Div([
            html.Div([
                html.Div('Synchronized Emergency Route', style={'fontSize': '11px', 'textTransform': 'uppercase', 'letterSpacing': '0.12em', 'color': '#7a6859', 'marginBottom': '8px', 'fontWeight': '700'}),
                html.Div(id='route-status', style={'padding': '12px', 'borderRadius': '14px', 'background': 'rgba(255, 255, 255, 0.7)', 'color': '#1d4ed8', 'fontWeight': '700', 'fontSize': '13px', 'border': '1px solid rgba(180,140,100,0.2)'})
            ], style={'padding': '16px', 'borderRadius': '18px', 'background': 'rgba(255, 250, 243, 0.85)', 'border': '1px solid rgba(180, 140, 100, 0.2)', 'boxShadow': '0 10px 25px rgba(110,80,50,0.08)'}),
            
            html.Div([
                html.Div('Active Emergency Units', style={'fontSize': '11px', 'textTransform': 'uppercase', 'letterSpacing': '0.12em', 'color': '#7a6859', 'marginBottom': '8px', 'fontWeight': '700'}),
                html.Div(id='ambulance-list', style={'height': '220px', 'overflowY': 'auto', 'padding': '10px', 'borderRadius': '14px', 'background': 'rgba(255, 255, 255, 0.7)', 'border': '1px solid rgba(180, 140, 100, 0.15)'})
            ], style={'padding': '16px', 'borderRadius': '18px', 'background': 'rgba(255, 250, 243, 0.85)', 'border': '1px solid rgba(180, 140, 100, 0.2)', 'boxShadow': '0 10px 25px rgba(110,80,50,0.08)'}),
            
            html.Div([
                html.Div('Hospital Alerts Feed', style={'fontSize': '11px', 'textTransform': 'uppercase', 'letterSpacing': '0.12em', 'color': '#7a6859', 'marginBottom': '8px', 'fontWeight': '700'}),
                html.Div(id='notifications-list', style={'height': '180px', 'overflowY': 'auto', 'padding': '10px', 'borderRadius': '14px', 'background': 'rgba(255, 255, 255, 0.7)', 'border': '1px solid rgba(180, 140, 100, 0.15)'})
            ], style={'padding': '16px', 'borderRadius': '18px', 'background': 'rgba(255, 250, 243, 0.85)', 'border': '1px solid rgba(180, 140, 100, 0.2)', 'boxShadow': '0 10px 25px rgba(110,80,50,0.08)'}),

            html.Div([
                html.Div('Tracking Mode', style={'fontSize': '11px', 'textTransform': 'uppercase', 'letterSpacing': '0.12em', 'color': '#7a6859', 'marginBottom': '6px', 'fontWeight': '700'}),
                dcc.Dropdown(
                    id='mode',
                    options=[
                        {'label': 'Live Tracking', 'value': 'live'},
                        {'label': 'Simulation Mode', 'value': 'sim'}
                    ],
                    value='live',
                    clearable=False,
                    style={'color': '#2c221e'}
                )
            ], style={'padding': '14px', 'borderRadius': '18px', 'background': 'rgba(255, 250, 243, 0.85)', 'border': '1px solid rgba(180, 140, 100, 0.2)'})
        ], style={'width': '330px', 'display': 'flex', 'flexDirection': 'column', 'gap': '14px'}),

        # Main Plotly Map Frame
        html.Div([
            dcc.Graph(id='live-map', config={'displayModeBar': False}, style={'height': '78vh', 'width': '100%'})
        ], style={'flex': '1', 'borderRadius': '20px', 'overflow': 'hidden', 'border': '1px solid rgba(180, 140, 100, 0.2)', 'boxShadow': '0 15px 35px rgba(110,80,50,0.12)'})
    ], style={'display': 'flex', 'gap': '16px', 'padding': '16px'}),

    dcc.Interval(id='interval', interval=2000, n_intervals=0),
], style={'minHeight': '100vh', 'background': 'radial-gradient(circle at 50% 0%, #fbf5eb 0%, #f0e4d2 100%)', 'fontFamily': "'Inter', sans-serif", 'color': '#2c221e'})


# Dash Callback for Map and Lists
@dash_app.callback(
    [Output('live-map', 'figure'),
     Output('ambulance-list', 'children'),
     Output('notifications-list', 'children'),
     Output('route-status', 'children')],
    [Input('interval', 'n_intervals'),
     Input('mode', 'value')]
)
def update_map(n, mode):
    with _state_lock:
        siren_on = is_siren_active()
        ambulances = [dict(item) for item in ambulances_store.values()]
        notifications = list(notifications_log[-20:] if notifications_log else [])
        route_poly = list(shared_route_state.get('route_polyline', []))
        dest = shared_route_state.get('destination')

    if not ambulances and os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, 'r') as handle:
                reader = csv.DictReader(handle)
                ambulances = [
                    {
                        'id': row['id'],
                        'lat': float(row['lat']),
                        'lon': float(row['lon']),
                        'speed': float(row.get('speed_kmph', 0) or 0),
                        'status': row.get('status', 'active'),
                        'emergency': row.get('emergency', 'normal')
                    }
                    for row in reader
                ]
        except Exception:
            ambulances = []

    fig = go.Figure()

    # Hospital Markers
    fig.add_trace(go.Scattermap(
        lat=hospitals_df['lat'], lon=hospitals_df['lon'],
        mode='markers',
        marker=dict(size=14, color='#d93829'),
        text=hospitals_df['name'],
        name='Hospitals',
        hovertemplate='<b>%{text}</b><extra></extra>'
    ))

    center_lat, center_lon = 28.6139, 77.2090
    zoom_level = 12

    if ambulances:
        center_lat = float(ambulances[0]['lat'])
        center_lon = float(ambulances[0]['lon'])

        for pos in ambulances:
            lat = float(pos['lat'])
            lon = float(pos['lon'])
            aid = pos['id']
            emergency = pos.get('emergency', 'normal')

            color = '#d93829' if emergency == 'critical' else '#e08b2b' if emergency == 'urgent' else '#16a34a'
            size = 18 if emergency == 'critical' else 15

            fig.add_trace(go.Scattermap(
                lat=[lat], lon=[lon],
                mode='markers+text',
                marker=dict(size=size, color=color),
                text=aid,
                textposition='top center',
                name=f"{aid} ({emergency.upper()})",
                hovertemplate=f"<b>{aid}</b><br>Emergency: {emergency}<extra></extra>"
            ))

    # Synchronized Polyline Route
    if route_poly:
        lats = [p[0] for p in route_poly]
        lons = [p[1] for p in route_poly]
        fig.add_trace(go.Scattermap(
            lat=lats, lon=lons,
            mode='lines',
            line=dict(width=5, color='#1d4ed8'),
            name=f"Route to {dest or 'Hospital'}"
        ))

    fig.update_layout(
        map=dict(center=dict(lat=center_lat, lon=center_lon), zoom=zoom_level, style='carto-positron'),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        uirevision='constant',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )

    route_summary = f"Destination: {dest or 'Awaiting Emergency'}"
    if siren_on:
        route_summary += ' • 🚨 SIREN ACTIVE'

    # Build Ambulance Cards
    amb_list = []
    for amb in ambulances:
        col = '#d93829' if amb.get('emergency') == 'critical' else '#e08b2b' if amb.get('emergency') == 'urgent' else '#16a34a'
        amb_list.append(html.Div([
            html.Div(f"🚑 {amb['id']}", style={'fontWeight': '800', 'color': col}),
            html.Div(f"Speed: {amb.get('speed', 0):.1f} km/h • Level: {amb.get('emergency', 'normal').upper()}", style={'fontSize': '11px', 'color': '#7a6859'}),
        ], style={'padding': '8px 12px', 'borderRadius': '10px', 'background': 'rgba(255,255,255,0.7)', 'marginBottom': '6px', 'borderLeft': f"4px solid {col}"}))

    if not amb_list:
        amb_list = [html.Div("No active emergency units online", style={'color': '#7a6859', 'fontSize': '12px'})]

    # Build Notifications List
    notif_list = []
    for notif in reversed(notifications[:10]):
        notif_list.append(html.Div([
            html.Div(f"🏥 {notif.get('nearest_hospital', 'Hospital')}", style={'fontWeight': '700', 'fontSize': '12px', 'color': '#2c221e'}),
            html.Div(f"{notif.get('ambulance_id')} → {notif.get('distance_km')} km, ETA: {notif.get('eta_minutes')} min", style={'fontSize': '11px', 'color': '#7a6859'}),
        ], style={'padding': '8px', 'borderBottom': '1px solid rgba(180,140,100,0.15)'}))

    if not notif_list:
        notif_list = [html.Div("No notifications logged", style={'color': '#7a6859', 'fontSize': '12px'})]

    return fig, amb_list, notif_list, route_summary


if __name__ == '__main__':
    print("🚀 Starting LifeLine AI Platform...")
    dash_app.run(debug=True, port=5000, threaded=True, use_reloader=False, dev_tools_hot_reload=False)

