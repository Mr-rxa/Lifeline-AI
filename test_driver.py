from app import create_app
from extensions import db
import requests
import time
import subprocess
import threading

app = create_app()

def run_server():
    app.run(port=5001, use_reloader=False)

server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()
time.sleep(2)

BASE_URL = 'http://localhost:5001/api'

try:
    # We already have admin from previous test if DB persists? Wait, DB might be persistent.
    # Let's register a new driver
    res = requests.post(f'{BASE_URL}/auth/register', json={'username':'driver1', 'email':'d1@ll.ai', 'password':'pass'})
    if res.status_code == 400: # Already exists
        pass
    
    # Login as admin to add ambulance
    admin_token = requests.post(f'{BASE_URL}/auth/login', json={'username':'admin', 'password':'pass'}).json().get('access_token')
    
    if admin_token:
        headers = {'Authorization': f'Bearer {admin_token}'}
        
        # Get users to find driver1 ID
        users = requests.get(f'{BASE_URL}/users/', headers=headers).json()
        driver_id = next((u['id'] for u in users if u['username'] == 'driver1'), None)
        
        # Change user role to driver
        requests.put(f'{BASE_URL}/users/{driver_id}', json={'role':'driver'}, headers=headers)
        
        # Create Ambulance
        res = requests.post(f'{BASE_URL}/ambulances/', json={'vehicle_number': 'AMB-999', 'type': 'ALS'}, headers=headers)
        amb_id = res.json().get('id') if res.status_code == 201 else None
        
        if not amb_id:
            # Maybe already exists, find it
            ambs = requests.get(f'{BASE_URL}/ambulances/', headers=headers).json()
            amb_id = next((a['id'] for a in ambs if a['vehicle_number'] == 'AMB-999'), None)
        
        # Assign driver to ambulance
        requests.post(f'{BASE_URL}/ambulances/{amb_id}/assign', json={'driver_id': driver_id}, headers=headers)
        
        # Login as driver
        driver_token = requests.post(f'{BASE_URL}/auth/login', json={'username':'driver1', 'password':'pass'}).json()['access_token']
        d_headers = {'Authorization': f'Bearer {driver_token}'}
        
        # Test location ping (driver.js does this)
        res = requests.post(f'{BASE_URL}/tracking/update', json={'ambulance_id': amb_id, 'lat': 12.34, 'lon': 56.78, 'speed': 45}, headers=d_headers)
        print("Ping Status:", res.status_code, res.text)
        assert res.status_code == 200
        print("Driver tracking ping passed.")

finally:
    subprocess.run(['kill', '-9', str(subprocess.check_output(['lsof', '-t', '-i', ':5001']).decode().strip())])

