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


def ai_capabilities(ocr_engine) -> dict:
    from app.services.ocr import describe
    from app.services.reuse_visual import CV2_VERSION

    return {
        "ocr": describe(ocr_engine) if ocr_engine is not None else {"engine": "none", "available": False, "local_only": True},
        "computer_vision": {"engine": "opencv", "available": CV2_VERSION is not None, "version": CV2_VERSION,
                            "used_for": "page alignment (ORB + RANSAC), residual difference regions, rectification"},
        "extraction": {"method": "deterministic labelled-field rules with evidence quotes and coordinates",
                       "model": None},
        "local_vision_model": {"configured": False, "note": "No local vision or multimodal model is configured."},
        "local_text_model": {"configured": False,
                             "note": "No local language model is configured; explanations are generated deterministically."},
        "remote_services": "none (no network calls are made for analysis)",
    }


def build_system_info(settings: Settings, ocr_engine=None) -> SystemInfoResponse:
    return SystemInfoResponse(
        app_name=settings.app_name,
        app_version=settings.app_version,
        api_version=settings.api_version,
        environment=settings.environment,
        demo_mode=settings.environment != "production" and settings.demo_users_enabled,
        database_backend=settings.database_backend,
        implemented_capabilities=IMPLEMENTED,
        planned_capabilities=PLANNED,
        ai_capabilities=ai_capabilities(ocr_engine),
    )
