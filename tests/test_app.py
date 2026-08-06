import app


def test_dashboard_route():
    client = app.app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    body = response.get_data(as_text=True).lower()
    assert 'lifeline ai' in body


def test_health_endpoint():
    client = app.app.test_client()
    response = client.get('/api/health')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['status'] == 'ok'


def test_dashboard_callback_renders():
    figure, amb_list, notif_list, siren_zone = app.update_map(0, 'live')
    assert figure is not None
    assert len(figure.data) >= 1
    assert isinstance(amb_list, list)
    assert isinstance(notif_list, list)
    assert siren_zone is not None


def test_shared_route_endpoint():
    client = app.app.test_client()
    response = client.get('/api/route')
    assert response.status_code == 200
    payload = response.get_json()
    assert 'hospital' in payload or 'destination' in payload


def test_siren_endpoint():
    client = app.app.test_client()
    response = client.post('/api/siren', json={'id': 'AMB-TEST'})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['status'] == 'ok'
    # confirm route reflects siren state
    r = client.get('/api/route')
    rp = r.get_json()
    assert rp.get('siren_active') is True


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
