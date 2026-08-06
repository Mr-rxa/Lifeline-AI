import os
import time
import uuid
from datetime import datetime
import dash
from dash import dcc, html
from dash.dependencies import Output, Input, State
import plotly.graph_objs as go
import pandas as pd
import csv
import requests
from flask import request, jsonify
from utils import haversine

# ==== CONFIG ====
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
# =================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, 'live_positions.csv')

# Load hospital data
hospitals_df = pd.read_csv(os.path.join(BASE_DIR, 'hospitals.csv'))

# Ambulance state
ambulances_store = {}
notifications_log = []
positions_log = {}
WEBHOOK_URLS = [u.strip() for u in os.getenv('WEBHOOK_URLS', '').split(',') if u.strip()]

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'lat', 'lon', 'speed_kmph', 'ts', 'emergency', 'status'])


def load_hospitals():
    try:
        hospitals_df = pd.read_csv(os.path.join(BASE_DIR, 'hospitals.csv'))
        return hospitals_df
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

        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['id', 'lat', 'lon', 'speed_kmph', 'ts', 'emergency', 'status'])
            writer.writeheader()
            writer.writerows(rows)
    except Exception:
        pass


def find_nearest_hospital(lat, lon):
    if hospitals_df.empty:
        hospitals_df = load_hospitals()

    min_dist = float('inf')
    nearest = None
    for _, hosp in hospitals_df.iterrows():
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
        'eta_minutes': round((distance / 60) * 60, 1)
    }
    notifications_log.append(notification)
    if len(notifications_log) > 50:
        notifications_log.pop(0)

    return notification


def update_csv(aid, lat, lon, speed, ts, emergency='normal', status='active'):
    cleanup_old_positions()
    rows = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

    rows = [r for r in rows if r.get('id') != aid]
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


# Dash app + WSGI entrypoint for hosting platforms
# Create this before the Flask route decorators so the routes register correctly.
dash_app = dash.Dash(__name__)
server = dash_app.server
app = server
application = app


@server.route('/ambulance')
def ambulance_interface():
    return """
    <!DOCTYPE html>
    <html lang=\"en\">
    <head>
      <meta charset=\"UTF-8\" />
      <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
      <title>LifeLine AI — Ambulance Interface</title>
      <style>
        body { font-family: Inter, sans-serif; margin: 0; background: linear-gradient(135deg, #07111f, #132a4d); color: white; min-height: 100vh; display: grid; place-items: center; }
        .card { width: min(92vw, 560px); background: rgba(8, 15, 30, 0.92); border: 1px solid rgba(255,255,255,0.12); border-radius: 24px; padding: 24px; box-shadow: 0 20px 50px rgba(0,0,0,0.35); }
        h1 { margin-top: 0; font-size: 1.6rem; }
        label { display: block; margin: 10px 0 6px; color: #8db7ff; }
        input, select, button { width: 100%; padding: 12px 13px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.15); background: rgba(255,255,255,0.08); color: white; margin-bottom: 10px; }
        button { cursor: pointer; background: linear-gradient(90deg, #4fd1c5, #5b8cff); color: #03111d; font-weight: 700; border: none; }
        .status { margin-top: 10px; padding: 12px; border-radius: 12px; background: rgba(79, 209, 197, 0.15); }
      </style>
    </head>
    <body>
      <div class=\"card\">
        <h1>🚑 Ambulance Dispatch</h1>
        <p>Share live location updates for the control room.</p>
        <label>Ambulance ID</label>
        <input id=\"id\" value=\"AMB-01\" />
        <label>Latitude</label>
        <input id=\"lat\" type=\"number\" step=\"0.0001\" />
        <label>Longitude</label>
        <input id=\"lon\" type=\"number\" step=\"0.0001\" />
        <label>Emergency Level</label>
        <select id=\"emergency\">
          <option value=\"normal\">Normal</option>
          <option value=\"urgent\">Urgent</option>
          <option value=\"critical\">Critical</option>
        </select>
        <button onclick=\"sendLocation()\">Send live update</button>
        <div id=\"status\" class=\"status\">Waiting for a signal…</div>
      </div>
      <script>
        const idInput = document.getElementById('id');
        const latInput = document.getElementById('lat');
        const lonInput = document.getElementById('lon');
        const statusEl = document.getElementById('status');

        function setLocationFromBrowser() {
          if (!navigator.geolocation) {
            statusEl.textContent = 'Location access is not supported on this device.';
            return;
          }
          navigator.geolocation.getCurrentPosition((pos) => {
            latInput.value = pos.coords.latitude.toFixed(6);
            lonInput.value = pos.coords.longitude.toFixed(6);
            statusEl.textContent = 'Live coordinates captured.';
          }, () => {
            latInput.value = '28.6139';
            lonInput.value = '77.2090';
            statusEl.textContent = 'Using fallback coordinates.';
          });
        }

        async function sendLocation() {
          const payload = {
            id: idInput.value || 'AMB-01',
            lat: Number(latInput.value || 28.6139),
            lon: Number(lonInput.value || 77.2090),
            speed_kmph: 42,
            emergency: document.getElementById('emergency').value
          };
          statusEl.textContent = 'Sending update...';
          const response = await fetch('/update_location', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          const data = await response.json();
          statusEl.textContent = data.status === 'ok' ? 'Update sent successfully.' : 'Update failed.';
        }

        setLocationFromBrowser();
      </script>
    </body>
    </html>
    """


@server.route('/update_location', methods=['POST'])
def update_location():
    try:
        data = request.get_json(force=True, silent=True) or {}
        aid = data.get('id', 'AMB-' + str(uuid.uuid4())[:8])
        lat = float(data.get('lat', 28.6139))
        lon = float(data.get('lon', 77.2090))
        speed = float(data.get('speed_kmph', 0))
        emergency = data.get('emergency', 'normal')
        status = 'in_transit' if speed > 5 else 'stationary'
        ts = time.time()

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
        return jsonify({'status': 'ok', 'ambulance_id': aid, 'notification': notification, 'path': positions_log.get(aid, [])}), 200
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 400


@server.route('/api/ambulances', methods=['GET'])
def api_ambulances():
    enriched = []
    for aid, data in ambulances_store.items():
        item = dict(data)
        item['path'] = positions_log.get(aid, [])
        enriched.append(item)
    return jsonify(enriched), 200


@server.route('/api/notifications', methods=['GET'])
def api_notifications():
    limit = request.args.get('limit', 20, type=int)
    return jsonify(notifications_log[-limit:] if notifications_log else []), 200


@server.route('/trigger_alert', methods=['POST'])
def trigger_alert():
    data = request.get_json(force=True, silent=True) or {}
    aid = data.get('id')
    if not aid or aid not in ambulances_store:
        return jsonify({'error': 'ambulance id not found', 'status': 'error'}), 404
    amb = ambulances_store[aid]
    notification = notify_hospitals(aid, amb.get('lat', 0), amb.get('lon', 0), amb.get('speed', 0), amb.get('status', 'stationary'))
    return jsonify({'status': 'ok', 'ambulance_id': aid, 'notification': notification}), 200

# Simulation globals
SIM_START = (28.6139, 77.2090)
SIM_ROUTE = []
SIM_INDEX = 0
SIM_ROUTE_NAME = ""

dash_app.layout = html.Div([
    html.H2("🚑 LifeLine AI — Smart Ambulance Tracker", style={'color': '#f5576c', 'textAlign': 'center', 'padding': '20px'}),
    
    html.Div([
        html.Div([
            html.H4("Active Ambulances"),
            html.Div(id='ambulance-list', style={'height': '300px', 'overflowY': 'auto', 'border': '1px solid #ddd', 'padding': '10px', 'borderRadius': '5px'})
        ], style={'width': '32%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginRight': '2%'}),
        
        html.Div([
            html.H4("Hospital Notifications"),
            html.Div(id='notifications-list', style={'height': '300px', 'overflowY': 'auto', 'border': '1px solid #ddd', 'padding': '10px', 'borderRadius': '5px'})
        ], style={'width': '32%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginRight': '2%'}),
        
        html.Div([
            html.H4("Map Mode"),
            dcc.Dropdown(
                id='mode',
                options=[
                    {'label': 'Live Tracking', 'value': 'live'},
                    {'label': 'Demo Simulation', 'value': 'sim'}
                ],
                value='live'
            )
        ], style={'width': '32%', 'display': 'inline-block', 'verticalAlign': 'top'})
    ], style={'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '8px', 'marginBottom': '20px'}),
    
    dcc.Graph(id='live-map', style={'height': '70vh'}),
    dcc.Interval(id='interval', interval=2000, n_intervals=0),
])

def get_route(lat1, lon1, lat2, lon2):
    if not ORS_API_KEY:
        return [], []

    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {"Authorization": ORS_API_KEY}
    params = {"start": f"{lon1},{lat1}", "end": f"{lon2},{lat2}"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        coords = data['features'][0]['geometry']['coordinates']
        lons, lats = zip(*coords)
        return list(lats), list(lons)
    except Exception as e:
        print("Route error:", e)
        return [], []

def setup_simulation():
    global SIM_ROUTE, SIM_INDEX, SIM_ROUTE_NAME
    SIM_INDEX = 0
    nearest = None
    min_dist = float('inf')
    for _, hosp in hospitals_df.iterrows():
        d = haversine(SIM_START[0], SIM_START[1], hosp['lat'], hosp['lon'])
        if d < min_dist:
            min_dist = d
            nearest = hosp
    if nearest is not None:
        lats, lons = get_route(SIM_START[0], SIM_START[1], nearest['lat'], nearest['lon'])
        SIM_ROUTE = list(zip(lats, lons))
        SIM_ROUTE_NAME = nearest['name']
    else:
        SIM_ROUTE = [(SIM_START[0], SIM_START[1])]
        SIM_ROUTE_NAME = "Unknown Hospital"

@dash_app.callback(
    [Output('live-map', 'figure'),
     Output('ambulance-list', 'children'),
     Output('notifications-list', 'children')],
    [Input('interval', 'n_intervals'),
     Input('mode', 'value')]
)
def update_map(n, mode):
    global SIM_INDEX, SIM_ROUTE
    
    # Get ambulances and notifications from the shared server state
    ambulances = []
    notifications = []
    try:
        ambulances = [dict(item) for item in ambulances_store.values()]
    except Exception:
        ambulances = []

    try:
        notifications = notifications_log[-20:] if notifications_log else []
    except Exception:
        notifications = []
    
    live_positions = []
    route_lats, route_lons = [], []
    route_name = ""

    if mode == 'live':
        if ambulances:
            # Prefer live API data
            live_positions = ambulances
        else:
            try:
                with open('live_positions.csv', 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        live_positions.append(row)
            except FileNotFoundError:
                pass

            # Sort by timestamp and keep latest per ambulance
            live_positions.sort(key=lambda x: float(x.get('ts', 0)), reverse=True)
            latest_positions = {}
            for row in live_positions:
                if row['id'] not in latest_positions:
                    latest_positions[row['id']] = row
            live_positions = list(latest_positions.values())

    else:
        if not SIM_ROUTE:
            setup_simulation()
        if SIM_ROUTE:
            lat, lon = SIM_ROUTE[SIM_INDEX]
            live_positions = [{'id': 'SIM1', 'lat': lat, 'lon': lon}]
            route_lats, route_lons = zip(*SIM_ROUTE)
            route_name = SIM_ROUTE_NAME
            SIM_INDEX += 1
            if SIM_INDEX >= len(SIM_ROUTE):
                SIM_INDEX = 0
                setup_simulation()

    fig = go.Figure()

    # Plot hospitals
    fig.add_trace(go.Scattermap(
        lat=hospitals_df['lat'], lon=hospitals_df['lon'],
        mode='markers',
        marker=dict(size=12, color='red', symbol='hospital'),
        text=hospitals_df['name'],
        name='Hospitals'
    ))

    center_lat, center_lon = 20, 78
    zoom_level = 4
    all_route_lats, all_route_lons = [], []

    if live_positions:
        center_lat = float(live_positions[0]['lat'])
        center_lon = float(live_positions[0]['lon'])
        zoom_level = 12

        for pos in live_positions:
            lat = float(pos['lat'])
            lon = float(pos['lon'])
            aid = pos['id']
            emergency = pos.get('emergency', 'normal')
            status = pos.get('status', 'active')
            path = pos.get('path') or []
            
            # Set color based on emergency level
            if emergency == 'critical':
                color = 'red'
                size = 18
            elif emergency == 'urgent':
                color = 'orange'
                size = 16
            else:
                color = 'blue'
                size = 14
            
            # Skip if arrived
            if status == 'arrived':
                color = 'gray'
                size = 12
            
            fig.add_trace(go.Scattermap(
                lat=[lat], lon=[lon],
                mode='markers+text',
                marker=dict(size=size, color=color),
                text=aid,
                textposition='top center',
                name=f"{aid} ({emergency.upper()})",
                hovertemplate=f"<b>{aid}</b><br>Emergency: {emergency}<br>Status: {status}<extra></extra>"
            ))

            # Draw recent path for this ambulance if available
            if path and len(path) > 1:
                path_lats = [float(p.get('lat')) for p in path]
                path_lons = [float(p.get('lon')) for p in path]
                fig.add_trace(go.Scattermap(
                    lat=path_lats, lon=path_lons,
                    mode='lines',
                    line=dict(width=2, color=color),
                    name=f"Route {aid}",
                    showlegend=False
                ))
                all_route_lats.extend(path_lats)
                all_route_lons.extend(path_lons)

        if mode == 'sim' and route_lats:
            fig.add_trace(go.Scattermap(
                lat=route_lats, lon=route_lons,
                mode='lines',
                line=dict(width=4, color='green'),
                name=f"Route to {route_name}"
            ))
            all_route_lats.extend(route_lats)
            all_route_lons.extend(route_lons)

        if mode == 'live':
            lat = float(live_positions[0]['lat'])
            lon = float(live_positions[0]['lon'])
            nearest = None
            min_dist = float('inf')
            for _, hosp in hospitals_df.iterrows():
                d = haversine(lat, lon, hosp['lat'], hosp['lon'])
                if d < min_dist:
                    min_dist = d
                    nearest = hosp
            if nearest is not None:
                rlats, rlons = get_route(lat, lon, nearest['lat'], nearest['lon'])
                if rlats:
                    fig.add_trace(go.Scattermap(
                        lat=rlats, lon=rlons,
                        mode='lines',
                        line=dict(width=4, color='green'),
                        name=f"Route to {nearest['name']}"
                    ))
                    all_route_lats.extend(rlats)
                    all_route_lons.extend(rlons)

    # Auto-fit map to route bounds if route exists
    if all_route_lats and all_route_lons:
        min_lat, max_lat = min(all_route_lats), max(all_route_lats)
        min_lon, max_lon = min(all_route_lons), max(all_route_lons)
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2
        
        # Calculate zoom level based on bounds
        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon
        max_range = max(lat_range, lon_range)
        
        if max_range < 0.01:
            zoom_level = 14
        elif max_range < 0.05:
            zoom_level = 12
        elif max_range < 0.1:
            zoom_level = 11
        elif max_range < 0.5:
            zoom_level = 10
        elif max_range < 1:
            zoom_level = 9
        else:
            zoom_level = 8

    fig.update_layout(
        map=dict(center=dict(lat=center_lat, lon=center_lon), zoom=zoom_level, style="open-street-map"),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        uirevision='constant',
        hovermode='closest'
    )
    
    # Build ambulance list
    amb_list = []
    for amb in ambulances:
        color = 'red' if amb.get('emergency') == 'critical' else 'orange' if amb.get('emergency') == 'urgent' else 'green'
        amb_list.append(html.Div([
            html.Div(f"🚑 {amb['id']}", style={'fontWeight': 'bold', 'color': color}),
            html.Div(f"Speed: {amb.get('speed', 0):.1f} km/h", style={'fontSize': '12px'}),
            html.Div(f"Status: {amb.get('status', 'unknown')}", style={'fontSize': '12px', 'color': '#666'}),
        ], style={'padding': '10px', 'borderBottom': '1px solid #eee', 'marginBottom': '5px'}))
    
    if not amb_list:
        amb_list = [html.Div("No active ambulances", style={'color': '#999', 'padding': '10px'})]
    
    # Build notifications list
    notif_list = []
    for notif in reversed(notifications[:15]):
        notif_list.append(html.Div([
            html.Div(f"🏥 {notif.get('nearest_hospital', 'Unknown')}", style={'fontWeight': 'bold', 'fontSize': '12px'}),
            html.Div(f"{notif.get('ambulance_id')} → {notif.get('distance_km')} km, ETA: {notif.get('eta_minutes')} min", style={'fontSize': '11px', 'color': '#666'}),
        ], style={'padding': '8px', 'borderBottom': '1px solid #eee', 'marginBottom': '5px'}))
    
    if not notif_list:
        notif_list = [html.Div("No notifications yet", style={'color': '#999', 'padding': '10px'})]
    
    return fig, amb_list, notif_list

if __name__ == '__main__':
    print("🚀 Starting Smart Ambulance Tracker...")
    dash_app.run(debug=True)
