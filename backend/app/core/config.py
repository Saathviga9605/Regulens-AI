"""Centralised, environment-based application settings.

All configuration is read here; other modules receive a ``Settings`` instance.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
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
