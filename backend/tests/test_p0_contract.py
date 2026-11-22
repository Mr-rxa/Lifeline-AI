from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models import Ambulance, Hospital, ROLE_ADMIN, ROLE_CITIZEN, User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.add_all(
        [
            User(
                full_name="System Admin",
                email="admin@example.com",
                password_hash=hash_password("admin-pass"),
                role=ROLE_ADMIN,
            ),
            User(
                full_name="Test Citizen",
                email="citizen@example.com",
                password_hash=hash_password("citizen-pass"),
                role=ROLE_CITIZEN,
            ),
        ]
    )
    db.commit()
    db.close()


def teardown_module():
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def login(email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_public_registration_only_accepts_citizen():
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Public Citizen",
            "email": "public@example.com",
            "password": "secure-pass",
            "role": "citizen",
        },
    )
    assert response.status_code == 200

    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Public Dispatcher",
            "email": "public-dispatcher@example.com",
            "password": "secure-pass",
            "role": "dispatcher",
        },
    )
    assert response.status_code == 400


def test_password_must_be_at_least_eight_characters():
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Short Password",
            "email": "short@example.com",
            "password": "1234567",
            "role": "citizen",
        },
    )
    assert response.status_code == 422


def test_incident_rejects_invalid_coordinates():
    token = login("citizen@example.com", "citizen-pass")
    response = client.post(
        "/api/incidents",
        headers=auth(token),
        json={
            "patient_name": "Test Patient",
            "emergency_type": "cardiac",
            "description": "Chest pain",
            "pickup_lat": 91,
            "pickup_lon": 77,
        },
    )
    assert response.status_code == 422


def test_dispatch_lifecycle_reserves_and_releases_capacity():
    admin_token = login("admin@example.com", "admin-pass")

    hospital_response = client.post(
        "/api/hospitals",
        headers=auth(admin_token),
        json={
            "name": "Test Emergency Hospital",
            "lat": 28.61,
            "lon": 77.20,
            "total_beds": 20,
            "available_beds": 10,
            "total_icu_beds": 5,
            "available_icu_beds": 2,
        },
    )
    assert hospital_response.status_code == 201
    hospital_id = hospital_response.json()["id"]

    citizen_token = login("citizen@example.com", "citizen-pass")
    incident_response = client.post(
        "/api/incidents",
        headers=auth(citizen_token),
        json={
            "patient_name": "Test Patient",
            "emergency_type": "cardiac",
            "description": "Severe chest pain",
            "pickup_lat": 28.62,
            "pickup_lon": 77.21,
        },
    )
    assert incident_response.status_code == 201
    incident_id = incident_response.json()["id"]

    db = TestingSessionLocal()
    try:
        driver = User(
            full_name="Test Driver",
            email="driver@example.com",
            password_hash=hash_password("driver-pass"),
            role="driver",
        )
        db.add(driver)
        db.flush()
        ambulance = Ambulance(
            vehicle_number="TEST-AMB-1",
            type="ALS",
            status="available",
            on_shift=True,
            driver_id=driver.id,
            last_lat=28.62,
            last_lon=77.21,
        )
        db.add(ambulance)
        db.commit()
        ambulance_id = ambulance.id
    finally:
        db.close()

    assign_response = client.post(
        f"/api/incidents/{incident_id}/assign",
        headers=auth(admin_token),
        json={"ambulance_id": ambulance_id, "hospital_id": hospital_id},
    )
    assert assign_response.status_code == 200

    hospital = client.get(
        f"/api/hospitals/{hospital_id}",
        headers=auth(admin_token),
    ).json()
    assert hospital["available_icu_beds"] == 1

    cancel_response = client.post(
        f"/api/incidents/{incident_id}/cancel",
        headers=auth(admin_token),
    )
    assert cancel_response.status_code == 200

    hospital = client.get(
        f"/api/hospitals/{hospital_id}",
        headers=auth(admin_token),
    ).json()
    assert hospital["available_icu_beds"] == 2
