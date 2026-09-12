"""Application entry point — Phase 2 backend foundation.

Scope of this module is deliberately small: application factory, logging with
secret redaction, security middleware, health endpoints and error handling.
Authentication (Phase 5), Google Drive (Phase 4) and the CMS routes (Phases 7-8)
are added later, each with its own verified tests.
"""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from typing import ClassVar

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config.settings import Settings, get_settings
from app.middleware.authentication import AuthenticationMiddleware
from app.middleware.cors import build_cors_middleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.routes import health_router
from app.routes.auth import auth_router
from app.routes.public import public_router

_SECRET_PATTERN = re.compile(r"(?i)(token|secret|password|private_key|authorization)=([^\s&]+)")


class RedactingFilter(logging.Filter):
    """Belt-and-braces log scrubbing: never write a secret to the log stream."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _SECRET_PATTERN.sub(lambda m: f"{m.group(1)}=***redacted***", record.getMessage())
        record.args = ()
        return True


class _LogDefaults(logging.Filter):
    """Fill the access-log fields so non-request records still format."""

    _DEFAULTS: ClassVar[dict[str, str]] = {
        "request_id": "-",
        "endpoint": "-",
        "status": "-",
        "duration_ms": "-",
        "user": "-",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self._DEFAULTS.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s "
            "endpoint=%(endpoint)s status=%(status)s duration_ms=%(duration_ms)s "
            "user=%(user)s | %(message)s"
        )
    )
    handler.addFilter(RedactingFilter())
    handler.addFilter(_LogDefaults())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, settings.log_level, logging.INFO))
    # Uvicorn's own handlers would duplicate every line.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.error").handlers = []


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    # Production needs its own opt-in (see Settings.serve_api_docs): the old
    # `docs_enabled or not is_production` expression served /docs in production
    # whenever DOCS_ENABLED was left at its default, and ignored
    # DOCS_ENABLED=false in development.
    docs_enabled = settings.serve_api_docs

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        yield

    app = FastAPI(
        title="Muhammed Fasal Portfolio CMS API",
        version=__version__,
        description=(
            "Control layer for the Muhammed Fasal cybersecurity portfolio. "
            "Phase 2 foundation: configuration, database access, health reporting, "
            "security middleware and error handling."
        ),
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Middleware order matters: outermost first.
    app.add_middleware(AuthenticationMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    build_cors_middleware(app, settings)

    app.include_router(health_router)
    app.include_router(public_router)
    app.include_router(auth_router)
    _register_error_handlers(app, settings)
    return app


def _register_error_handlers(app: FastAPI, settings: Settings) -> None:
    """Uniform error responses.

    Nothing internal — stack traces, SQL, filesystem paths, credentials — leaves
    the process in a response body. The detail stays in the server log.
    """

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: object, exc: RequestValidationError):
        errors = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
            errors.append(
                {"field": location or "payload", "message": error.get("msg", "Invalid value")}
            )
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed.", "errors": errors},
            headers={"X-Request-ID": _request_id(request)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request, exc: StarletteHTTPException):
        headers = dict(exc.headers or {})
        headers.setdefault("X-Request-ID", _request_id(request))
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)

    @app.exception_handler(SQLAlchemyError)
    async def database_handler(request, exc: SQLAlchemyError):
        logging.getLogger("portfolio.error").exception(
            "database_error", extra={"request_id": _request_id(request)}
        )
        return JSONResponse(
            status_code=503,
            content={"detail": "The portfolio service is temporarily unavailable. Please retry."},
            headers={"X-Request-ID": _request_id(request)},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request, exc: Exception):
        logging.getLogger("portfolio.error").exception(
            "unhandled_error", extra={"request_id": _request_id(request)}
        )
        if not settings.secure_errors:
            return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred. The event has been logged."},
            headers={"X-Request-ID": _request_id(request)},
        )


def _request_id(request) -> str:
    return getattr(getattr(request, "state", None), "request_id", "-")


app = create_app()

__all__ = ["app", "configure_logging", "create_app"]
