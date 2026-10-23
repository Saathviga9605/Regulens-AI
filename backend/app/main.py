"""FastAPI application factory and ASGI entrypoint (``uvicorn app.main:app``)."""

import logging
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.context import current_request_id
from app.core.errors import register_error_handlers
from app.core.limits import UploadSizeLimitMiddleware
from app.core.logging import configure_logging
from app.db.init_db import init_db
from app.db.session import build_engine, build_session_factory
from app.services import rule_catalog
from app.services.pdf_text import TesseractOcr
from app.services.storage import DocumentStorage

logger = logging.getLogger("regulens.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            init_db(app.state.engine)
        except Exception as exc:
            # Keep serving so /health can report the degraded state accurately.
            logger.error("Database initialisation failed", extra={"error_type": type(exc).__name__})
        try:
            with app.state.session_factory() as session:
                rule_catalog.ensure_default_rules(session)
        except Exception as exc:
            logger.error("Default scrutiny rules could not be ensured", extra={"error_type": type(exc).__name__})
        if not app.state.ocr_engine.available:
            logger.warning("OCR unavailable: Tesseract not found or disabled; image-only pages will not be read")
        try:
            app.state.document_storage.ensure_dirs()
        except OSError as exc:
            logger.error("Document storage unavailable", extra={"error_type": type(exc).__name__})
        logger.info(f"{settings.app_name} started in {settings.environment} mode")
        yield
        app.state.engine.dispose()

    is_prod = settings.environment == "production"
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = build_engine(settings)
    app.state.session_factory = build_session_factory(app.state.engine)
    app.state.document_storage = DocumentStorage(settings.document_storage_path)
    app.state.ocr_engine = TesseractOcr.from_settings(settings)

    # Middleware order: the last added is outermost. CORS wraps everything (so 413s carry CORS headers),
    # then request IDs, then the upload size limit.
    app.add_middleware(
        UploadSizeLimitMiddleware,
        max_bytes=settings.max_upload_bytes,
        path_pattern=rf"{re.escape(settings.api_prefix)}/applications/[^/]+/documents",
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        current_request_id.set(request.state.request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=s.environment == "development")
