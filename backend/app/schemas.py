from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=4)
    phone: str = ""
    role: str = "citizen"  # citizen/dispatcher/driver/hospital (admin only created by admin)
    hospital_id: int | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: str
    phone: str
    role: str
    status: str
    hospital_id: int | None = None
    created_at: datetime | None = None
    last_login: datetime | None = None


# ---------- Hospitals ----------
class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    total: int
    available: int


class ResourceUpdate(BaseModel):
    available: int


class ResourceCreate(BaseModel):
    name: str
    total: int
    available: int


class HospitalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    lat: float
    lon: float
    address: str
    phone: str
    total_beds: int
    available_beds: int
    total_icu_beds: int
    available_icu_beds: int
    accepting: bool
    resources: list[ResourceOut] = []


class HospitalCreate(BaseModel):
    name: str
    lat: float
    lon: float
    address: str = ""
    phone: str = ""
    total_beds: int = 0
    available_beds: int = 0
    total_icu_beds: int = 0
    available_icu_beds: int = 0


class HospitalCapacityUpdate(BaseModel):
    available_beds: int | None = None
    available_icu_beds: int | None = None
    total_beds: int | None = None
    total_icu_beds: int | None = None
    accepting: bool | None = None


# ---------- Ambulances ----------
class AmbulanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vehicle_number: str
    type: str
    status: str
    condition: str
    on_shift: bool
    driver_id: int | None = None
    current_incident_id: int | None = None
    last_lat: float | None = None
    last_lon: float | None = None
    last_update: datetime | None = None


class AmbulanceCreate(BaseModel):
    vehicle_number: str
    type: str = "ALS"
    driver_id: int | None = None


class LocationUpdate(BaseModel):
    lat: float
    lon: float
    speed: float = 0.0


# ---------- Incidents ----------
class IncidentCreate(BaseModel):
    patient_name: str = ""
    patient_phone: str = ""
    emergency_type: str = "medical"
    description: str = ""
    pickup_lat: float
    pickup_lon: float
    pickup_address: str = ""


class HospitalRecommendation(BaseModel):
    hospital: HospitalOut
    distance_km: float
    eta_seconds: int
    score: float


class AmbulanceRecommendation(BaseModel):
    ambulance: AmbulanceOut
    distance_km: float
    eta_seconds: int


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    citizen_id: int | None = None
    patient_name: str
    patient_phone: str
    emergency_type: str
    description: str
    pickup_lat: float
    pickup_lon: float
    pickup_address: str
    severity: str
    severity_score: int
    status: str
    assigned_ambulance_id: int | None = None
    target_hospital_id: int | None = None
    created_at: datetime | None = None
    dispatched_at: datetime | None = None
    accepted_at: datetime | None = None
    arrived_pickup_at: datetime | None = None
    en_route_hospital_at: datetime | None = None
    arrived_hospital_at: datetime | None = None
    completed_at: datetime | None = None


class IncidentDetail(IncidentOut):
    ambulance: AmbulanceOut | None = None
    hospital: HospitalOut | None = None


class AssignRequest(BaseModel):
    ambulance_id: int
    hospital_id: int | None = None


class StatusUpdate(BaseModel):
    status: str


# ---------- Notifications ----------
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    message: str
    type: str
    incident_id: int | None = None
    read: bool
    created_at: datetime | None = None


# ---------- Audit ----------
class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor: str
    action: str
    entity: str
    entity_id: int | None = None
    detail: str
    created_at: datetime | None = None


TokenResponse.model_rebuild()
