"""Safe, non-sensitive application metadata. Never include paths, URLs or secrets."""

from app.core.config import Settings
from app.schemas.system import SystemInfoResponse

# Keep in step with the README "Capabilities" table; statements must match what the code actually does.
IMPLEMENTED = [
    "Institution and EoA application records with internal workflow states",
    "PDF, PNG and JPEG upload with signature, integrity and duplicate checks",
    "Local OCR for scanned and photographed pages when an OCR engine is installed",
    "Evidence-linked field extraction with quoted source lines and page references",
    "Configurable, versioned scrutiny rules: production profile and APH EoA profile (default for new runs)",
    "APH EoA rules cited to the pinned AICTE Approval Process Handbook 2024–25 to 2026–27; "
    "classified partially verified, formal approval pending",
    "Cross-document consistency checks and anomaly indicators for human review",
    "Cross-case document reuse detection with traceable explanations",
    "Issuer verification: simulated registry (SIMULATED) or reviewer-recorded manual checks (NOT_CONNECTED)",
    "QR, reference-format and signature-field integrity indicators (not issuer confirmation)",
    "Review queue, finding actions, evidence requests, alerts and preliminary scrutiny reports",
    "Role-based access, cross-case permission and an application-level append-only audit log",
]

PLANNED = [
    "Live issuer verification (no issuing-authority integration is connected)",
    "Evaluation on real photographed documents (current reuse evaluation uses synthetic data only)",
    "Formal approval record for the APH EoA rules",
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
