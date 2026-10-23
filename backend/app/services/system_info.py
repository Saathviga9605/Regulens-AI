"""Safe, non-sensitive application metadata. Never include paths, URLs or secrets."""

from app.core.config import Settings
from app.schemas.system import SystemInfoResponse

IMPLEMENTED = [
    "API health check with live database probe",
    "System metadata endpoint",
    "Dashboard shell with live backend connection status",
]

PLANNED = [
    "Application and institutional record management",
    "PDF document upload and OCR",
    "Evidence-linked structured extraction",
    "Configurable regulatory validation rules",
    "Cross-document consistency checks",
    "Preliminary anomaly detection",
    "Simulated issuer verification",
    "Reviewer queue, audit trail and preliminary scrutiny reports",
    "Authentication and role-based access",
]


def build_system_info(settings: Settings) -> SystemInfoResponse:
    return SystemInfoResponse(
        app_name=settings.app_name,
        app_version=settings.app_version,
        api_version=settings.api_version,
        environment=settings.environment,
        database_backend=settings.database_backend,
        implemented_capabilities=IMPLEMENTED,
        planned_capabilities=PLANNED,
    )
