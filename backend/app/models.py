from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Role constants
ROLE_CITIZEN = "citizen"
ROLE_DISPATCHER = "dispatcher"
ROLE_DRIVER = "driver"
ROLE_HOSPITAL = "hospital"
ROLE_ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(30), default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_CITIZEN)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, suspended

    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    hospital = relationship("Hospital", backref="staff", foreign_keys=[hospital_id])


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")

    total_beds: Mapped[int] = mapped_column(Integer, default=0)
    available_beds: Mapped[int] = mapped_column(Integer, default=0)
    total_icu_beds: Mapped[int] = mapped_column(Integer, default=0)
    available_icu_beds: Mapped[int] = mapped_column(Integer, default=0)

    accepting: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    resources = relationship("Resource", back_populates="hospital", cascade="all, delete-orphan")


class Resource(Base):
    """Trackable hospital resources (ventilators, oxygen cylinders, blood units, etc.)."""

    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0)
    available: Mapped[int] = mapped_column(Integer, default=0)

    hospital = relationship("Hospital", back_populates="resources")


class Ambulance(Base):
    __tablename__ = "ambulances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(10), default="ALS")  # ALS (advanced) / BLS (basic)
    # available, offered, en_route_pickup, at_pickup, en_route_hospital, at_hospital, offline, maintenance
    status: Mapped[str] = mapped_column(String(20), default="offline")
    condition: Mapped[str] = mapped_column(String(20), default="good")
    on_shift: Mapped[bool] = mapped_column(Boolean, default=False)

    driver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    current_incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)

    last_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    driver = relationship("User", foreign_keys=[driver_id])


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    citizen_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    patient_name: Mapped[str] = mapped_column(String(120), default="")
    patient_phone: Mapped[str] = mapped_column(String(30), default="")
    emergency_type: Mapped[str] = mapped_column(String(40), default="medical")
    description: Mapped[str] = mapped_column(Text, default="")

    pickup_lat: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_lon: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_address: Mapped[str] = mapped_column(String(255), default="")

    severity: Mapped[str] = mapped_column(String(20), default="normal")  # normal, urgent, critical
    severity_score: Mapped[int] = mapped_column(Integer, default=0)
    # pending, assigned, accepted, en_route_pickup, at_pickup, en_route_hospital, at_hospital, completed, cancelled
    status: Mapped[str] = mapped_column(String(25), default="pending")

    assigned_ambulance_id: Mapped[int | None] = mapped_column(ForeignKey("ambulances.id"), nullable=True)
    target_hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrived_pickup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    en_route_hospital_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrived_hospital_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ambulance = relationship("Ambulance", foreign_keys=[assigned_ambulance_id])
    hospital = relationship("Hospital", foreign_keys=[target_hospital_id])


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    ambulance_id: Mapped[int] = mapped_column(ForeignKey("ambulances.id"), nullable=False)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="offered")  # offered, accepted, rejected, completed
    eta_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrackingHistory(Base):
    __tablename__ = "tracking_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ambulance_id: Mapped[int] = mapped_column(ForeignKey("ambulances.id"), nullable=False)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    speed: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    role_target: Mapped[str | None] = mapped_column(String(20), nullable=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(30), default="info")
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor: Mapped[str] = mapped_column(String(120), default="")
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
