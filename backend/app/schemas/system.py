from typing import Literal

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    status: Literal["ok", "unavailable"]
    detail: str | None = None


class HealthResponse(BaseModel):
    app_name: str
    api_version: str
    status: Literal["ok", "degraded"]
    database: DependencyStatus


class SystemInfoResponse(BaseModel):
    app_name: str
    app_version: str
    api_version: str
    environment: str
    # True outside production when local demo accounts are enabled. Never includes credentials.
    demo_mode: bool
    database_backend: str
    implemented_capabilities: list[str]
    planned_capabilities: list[str]
