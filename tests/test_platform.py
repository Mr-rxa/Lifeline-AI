import time
import dashboard_registry as reg
import app


def test_dashboard_registry():
    sid1 = "dash_test_1"
    sid2 = "dash_test_2"

    reg.register(sid1, 28.6139, 77.2090)
    reg.register(sid2, 28.5672, 77.2100)

    assert reg.count() >= 2

    # Check nearest search
    nearest = reg.find_nearest(28.6140, 77.2091)
    assert nearest == sid1

    # Check queue push
    assert reg.push(sid1, {"type": "test_event"}) is True

    # Check queue retrieval
    q = reg.get_queue(sid1)
    msg = q.get_nowait()
    assert msg["type"] == "test_event"


def test_api_dashboard_endpoints():
    client = app.app.test_client()

    # Register dashboard
    r1 = client.post('/api/dashboard/register', json={
        'session_id': 'dash_client_test',
        'lat': 28.61,
        'lon': 77.21
    })
    assert r1.status_code == 200
    assert r1.get_json()['status'] == 'ok'

    # Ping heartbeat
    r2 = client.post('/api/dashboard/ping', json={'session_id': 'dash_client_test'})
    assert r2.status_code == 200
    assert r2.get_json()['status'] == 'ok'

    # Get status
    r3 = client.get('/api/dashboard/status')
    assert r3.status_code == 200
    assert r3.get_json()['count'] >= 1


def test_api_siren_and_stop():
    client = app.app.test_client()

    # Trigger siren
    r1 = client.post('/api/siren', json={
        'id': 'AMB-99',
        'lat': 28.6139,
        'lon': 77.2090,
        'emergency': 'critical'
    })
    assert r1.status_code == 200
    p1 = r1.get_json()
    assert p1['status'] == 'ok'
    assert p1['siren_active'] is True

    # Check route reflects active siren and synchronized polyline
    route_res = client.get('/api/route')
    assert route_res.status_code == 200
    route_data = route_res.get_json()
    assert route_data['siren_active'] is True
    assert 'route_polyline' in route_data

    # Stop siren
    r2 = client.post('/api/siren/stop', json={'session_id': 'dash_client_test'})
    assert r2.status_code == 200
    assert r2.get_json()['siren_active'] is False

    # Confirm siren state is stopped in route
    r3 = client.get('/api/route')
    assert r3.get_json()['siren_active'] is False


def test_citizen_alerts_nearby():
    client = app.app.test_client()

    # Post an ambulance location
    client.post('/update_location', json={
        'id': 'AMB-NEARBY',
        'lat': 28.6139,
        'lon': 77.2090,
        'speed_kmph': 50,
        'emergency': 'critical'
    })

    # Query alerts nearby
    res = client.get('/api/alerts/nearby?lat=28.6140&lon=77.2091&radius_km=3')
    assert res.status_code == 200
    data = res.get_json()
    assert data['count'] >= 1
    assert data['ambulances'][0]['id'] == 'AMB-NEARBY'


def test_citizen_alert_page_route():
    client = app.app.test_client()
    res = client.get('/alert')
    assert res.status_code == 200
    assert 'Citizen Proximity Alert' in res.get_data(as_text=True)
