from app import create_app
from extensions import db
import requests
import time
import subprocess
import threading

app = create_app()

def run_server():
    app.run(port=5000, use_reloader=False)

server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()
time.sleep(2)

BASE_URL = 'http://localhost:5000/api'

try:
    # 1. Setup Admin
    requests.post(f'{BASE_URL}/auth/setup/complete', json={'username':'admin', 'email':'admin@lifeline.ai', 'password':'pass'})
    token = requests.post(f'{BASE_URL}/auth/login', json={'username':'admin', 'password':'pass'}).json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    # 2. Add Ambulance
    res = requests.post(f'{BASE_URL}/ambulances/', json={'vehicle_number': 'AMB-101', 'type': 'ALS'}, headers=headers)
    assert res.status_code == 201
    amb_id = res.json()['id']

    # 3. Create Incident
    res = requests.post(f'{BASE_URL}/incidents/', json={'pickup_lat': 40.71, 'pickup_lon': -74.00, 'description': 'Heart attack'}, headers=headers)
    assert res.status_code == 201
    inc_id = res.json()['id']

    # 4. Assign Ambulance to Incident
    res = requests.post(f'{BASE_URL}/incidents/{inc_id}/assign', json={'ambulance_id': amb_id}, headers=headers)
    assert res.status_code == 200

    # 5. Update Status Flow
    requests.put(f'{BASE_URL}/incidents/{inc_id}/status', json={'status': 'en_route_pickup'}, headers=headers)
    requests.put(f'{BASE_URL}/incidents/{inc_id}/status', json={'status': 'arrived_pickup'}, headers=headers)
    requests.put(f'{BASE_URL}/incidents/{inc_id}/status', json={'status': 'completed'}, headers=headers)

    # 6. Fetch Analytics
    res = requests.get(f'{BASE_URL}/analytics/summary', headers=headers)
    data = res.json()
    assert data['incidents']['completed'] == 1
    # Response time should be small but calculated
    assert data['incidents']['avg_response_time_seconds'] >= 0

    print("REALISM TESTS PASSED!")

finally:
    subprocess.run(['kill', '-9', str(subprocess.check_output(['lsof', '-t', '-i', ':5000']).decode().strip())])

