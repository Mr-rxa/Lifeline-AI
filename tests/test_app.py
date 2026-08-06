import app


def test_dashboard_route():
    client = app.app.test_client()
    response = client.get('/')
    assert response.status_code == 200


def test_ambulance_route():
    client = app.app.test_client()
    response = client.get('/ambulance')
    assert response.status_code == 200


def test_update_location():
    client = app.app.test_client()
    response = client.post('/update_location', json={
        'id': 'AMB-TEST',
        'lat': 28.6,
        'lon': 77.2,
        'speed_kmph': 42,
        'emergency': 'critical'
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['status'] == 'ok'
