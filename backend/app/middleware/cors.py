"""CORS policy built from an explicit origin allowlist.

Credentials are allowed (the admin session is a cookie), so the origin list can
never be ``*`` — Starlette would silently downgrade it, but relying on that is a
misconfiguration waiting to happen.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import Settings

ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = ["Content-Type", "X-CSRF-Token", "X-Request-ID", "Authorization"]
EXPOSED_HEADERS = ["X-Request-ID", "X-CSRF-Token"]


def build_cors_middleware(app: FastAPI, settings: Settings) -> None:
    origins = settings.cors_origins
    if "*" in origins:
        # Wildcards are incompatible with credentialed requests; refuse to boot
        # rather than ship a silently broken (or accidentally open) policy.
        raise ValueError("CORS_ALLOWED_ORIGINS must not contain '*'; list explicit origins.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        expose_headers=EXPOSED_HEADERS,
        max_age=600,
    )
