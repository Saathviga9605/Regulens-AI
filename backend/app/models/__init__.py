"""ORM models. Import each model here so Alembic autogenerate and metadata see it."""

from app.models.application import Application, ApplicationProgramme, IdSequence
from app.models.institution import Institution

__all__ = ["Application", "ApplicationProgramme", "IdSequence", "Institution"]
