import dash
from dash import dcc, html
from dash.dependencies import Output, Input, State
import plotly.graph_objs as go
import pandas as pd
import csv
import requests
from utils import haversine

# ==== CONFIG ====
ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjIzNzYyNThjYzMxNzQ3NTA5NGUyYzc1YjVjNmFjZjMyIiwiaCI6Im11cm11cjY0In0="  # Replace with your key
# =================

# Load hospital data
hospitals_df = pd.read_csv('hospitals.csv')

# Simulation globals
SIM_START = (28.6139, 77.2090)
SIM_ROUTE = []
SIM_INDEX = 0
SIM_ROUTE_NAME = ""

app = dash.Dash(__name__)
server = app.server  # Expose server for gunicorn
app.layout = html.Div([
    html.H2("🚑 LifeLine AI — Smart Ambulance Tracker"),
    dcc.Dropdown(
        id='mode',
        options=[
            {'label': 'Live GPS', 'value': 'live'},
            {'label': 'Simulation', 'value': 'sim'}
        ],
        value='live',
        style={'width': '300px'}
    ),
    dcc.Graph(id='live-map', style={'height': '80vh'}),
    dcc.Interval(id='interval', interval=3000, n_intervals=0),
])

def get_route(lat1, lon1, lat2, lon2):
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

@app.callback(
    Output('live-map', 'figure'),
    Input('interval', 'n_intervals'),
    State('mode', 'value')
)
def update_map(n, mode):
    global SIM_INDEX, SIM_ROUTE
    live_positions = []
    route_lats, route_lons = [], []
    route_name = ""

    if mode == 'live':
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
                mode='markers',
                marker=dict(size=size, color=color),
                name=f"{aid} ({emergency.upper()})",
                text=f"ID: {aid}<br>Status: {status}<br>Emergency: {emergency}"
            ))

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
        uirevision='constant'  # Preserve zoom/pan state when map updates
    )
    return fig

if __name__ == '__main__':
    print("🚀 Starting Smart Ambulance Tracker...")
    app.run(debug=True)
