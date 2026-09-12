"""Phase 2 routes: health and liveness only.

Content routes arrive in later phases, each with its own verified test suite:
public portfolio API (Phase 10), admin CMS (Phases 7-8), auth (Phase 5).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.middleware.rate_limit import rate_limit_dependency
from app.services import health_service

health_router = APIRouter(tags=["system"])

_health_limit = rate_limit_dependency("public", "rate_limit_public_per_minute")


@health_router.get("/healthz", summary="Liveness probe", dependencies=[Depends(_health_limit)])
def liveness() -> dict[str, str]:
    """Cheap, dependency-free probe for load balancers and uptime checks."""
    return {"status": "ok", "version": __version__}


@health_router.get("/health", summary="Dependency health")
def health() -> dict[str, object]:
    """Reports database and API status.

    Public and deliberately thin: no connection strings, no driver details, no
    internal paths. Google Drive and GitHub OAuth statuses are added in Phases 4
    and 5 respectively.
    """
    return health_service.overview()
