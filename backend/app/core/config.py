"""Centralised, environment-based application settings.

All configuration is read here; other modules receive a ``Settings`` instance.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root (regulens-ai/), used to resolve relative SQLite paths.
REPO_ROOT = Path(__file__).resolve().parents[3]
SQLITE_PREFIX = "sqlite:///"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REGULENS_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ReguLens AI"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    api_prefix: str = "/api/v1"
    api_version: str = "v1"

    host: str = "127.0.0.1"
    port: int = 8000

    # Relative SQLite paths are resolved against the repository root.
    database_url: str = "sqlite:///data/regulens.db"

    # Comma-separated allowed frontend origins. No wildcard by default.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    log_level: str = "INFO"

    # Private document storage. Relative paths resolve against the repository root.
    # Must not be inside frontend/ (which may be served publicly).
    document_storage_dir: str = "data/documents"
    # Maximum accepted PDF size in bytes (default 20 MiB). Allowed range: 1 KiB – 200 MiB.
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=200 * 1024 * 1024)

    # --- Document processing / OCR -------------------------------------------------------------
    # Tesseract executable. Empty = auto-detect on PATH or the default Windows install location.
    tesseract_cmd: str = ""
    ocr_enabled: bool = True
    ocr_language: str = Field(default="eng", pattern=r"^[A-Za-z_+]{3,40}$")
    ocr_dpi: int = Field(default=200, ge=72, le=400)
    ocr_timeout_seconds: int = Field(default=30, ge=5, le=300)
    # Pages whose text layer has fewer non-whitespace characters than this are OCR candidates.
    min_page_text_chars: int = Field(default=25, ge=1, le=2000)
    max_processing_pages: int = Field(default=50, ge=1, le=500)

    # --- Local authentication (prototype) --------------------------------------------------------
    session_ttl_minutes: int = Field(default=480, ge=5, le=1440)
    login_max_failures: int = Field(default=5, ge=3, le=50)  # per username within login_lockout_minutes
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    # LOCAL DEMO ONLY — CHANGE BEFORE SHARING. Used only by the demo bootstrap (`seed` / `create-demo-users`);
    # never sent to the frontend, logged or audited. Mirrored in .env.example (a test keeps them in sync).
    # Demo bootstrap is refused in production, and enabling it in production is a configuration error.
    demo_users_enabled: bool = True
    demo_reviewer_username: str = Field(default="demo.reviewer", pattern=r"^[a-zA-Z0-9._-]{3,60}$")
    demo_reviewer_password: str = Field(default="Reviewer@Demo2026", min_length=10, max_length=200)
    demo_admin_username: str = Field(default="demo.admin", pattern=r"^[a-zA-Z0-9._-]{3,60}$")
    demo_admin_password: str = Field(default="Admin@Demo2026", min_length=10, max_length=200)

    @model_validator(mode="after")
    def _no_demo_users_in_production(self):
        if self.environment == "production" and self.demo_users_enabled:
            # An explicit request for demo accounts in production is a configuration error; the
            # local-friendly default is simply switched off so production never gets them silently.
            if "demo_users_enabled" in self.model_fields_set:
                raise ValueError("REGULENS_DEMO_USERS_ENABLED must be false when REGULENS_ENVIRONMENT=production.")
            self.demo_users_enabled = False
        if self.demo_reviewer_username.lower() == self.demo_admin_username.lower():
            raise ValueError("Demo reviewer and administrator usernames must differ.")
        return self

    @field_validator("document_storage_dir")
    @classmethod
    def _check_storage_dir(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document_storage_dir must not be empty.")
        path = Path(value)
        resolved = (path if path.is_absolute() else REPO_ROOT / path).resolve()
        frontend = (REPO_ROOT / "frontend").resolve()
        if resolved == frontend or frontend in resolved.parents:
            raise ValueError("document_storage_dir must not be inside the frontend directory.")
        if resolved.parent == resolved:
            raise ValueError("document_storage_dir must not be a filesystem root.")
        return str(resolved)

    @property
    def document_storage_path(self) -> Path:
        return Path(self.document_storage_dir)

    @field_validator("database_url")
    @classmethod
    def _resolve_sqlite_path(cls, value: str) -> str:
        if value.startswith(SQLITE_PREFIX) and value != "sqlite:///:memory:":
            path = Path(value[len(SQLITE_PREFIX):])
            if not path.is_absolute():
                path = (REPO_ROOT / path).resolve()
            return f"{SQLITE_PREFIX}{path.as_posix()}"
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if "*" in origins and self.environment == "production":
            raise ValueError("Wildcard CORS origin is not permitted in production.")
        return origins

    @property
    def sqlite_path(self) -> Path | None:
        if self.database_url.startswith(SQLITE_PREFIX) and self.database_url != "sqlite:///:memory:":
            return Path(self.database_url[len(SQLITE_PREFIX):])
        return None

    @property
    def database_backend(self) -> str:
        return self.database_url.split(":", 1)[0].split("+", 1)[0]


@lru_cache
def get_settings() -> Settings:
    return Settings()
