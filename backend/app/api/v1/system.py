from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.core.config import Settings
from app.schemas.system import DependencyStatus, HealthResponse, SystemInfoResponse
from app.services.health import check_database
from app.services.system_info import build_system_info

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_app_settings), db: Session = Depends(get_db)) -> HealthResponse:
    db_ok, detail = check_database(db)
    return HealthResponse(
        app_name=settings.app_name,
        api_version=settings.api_version,
        status="ok" if db_ok else "degraded",
        database=DependencyStatus(status="ok" if db_ok else "unavailable", detail=detail),
    )


@router.get("/system/info", response_model=SystemInfoResponse)
def system_info(settings: Settings = Depends(get_app_settings)) -> SystemInfoResponse:
    return build_system_info(settings)
