"""Shared serialization + broadcast helpers for the API routers."""

from app import schemas
from app.models import Ambulance, Incident
from app.ws import manager


def incident_dict(inc: Incident) -> dict:
    return schemas.IncidentOut.model_validate(inc).model_dump(mode="json")


def ambulance_dict(amb: Ambulance) -> dict:
    return schemas.AmbulanceOut.model_validate(amb).model_dump(mode="json")


def broadcast_incident(inc: Incident, event: str = "incident_update") -> None:
    manager.broadcast(event, incident_dict(inc))


def broadcast_ambulance(amb: Ambulance, event: str = "ambulance_update") -> None:
    manager.broadcast(event, ambulance_dict(amb))
