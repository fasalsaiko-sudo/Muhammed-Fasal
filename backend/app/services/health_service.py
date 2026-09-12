"""Dependency health reporting (Phase 2: database + API)."""

from __future__ import annotations

from typing import Any

from app.config.database import database_is_reachable
from app.utils.helpers import iso, utcnow


def database_status() -> dict[str, Any]:
    reachable = database_is_reachable()
    return {
        "name": "database",
        "status": "ONLINE" if reachable else "OFFLINE",
        "connected": reachable,
    }


def github_status() -> dict[str, Any]:
    """OAuth *configuration* status only.

    Deliberately not "CONNECTED": whether anyone is connected is a property of a
    user session, which `/auth/me` reports. Exposing a live connection state here
    would leak deployment detail to anonymous callers.
    """
    from app.config.settings import get_settings

    configured = get_settings().github_oauth_configured
    return {
        "name": "github",
        "status": "CONFIGURED" if configured else "UNCONFIGURED",
        "connected": configured,
    }


def api_status() -> dict[str, Any]:
    return {"name": "api", "status": "ONLINE", "connected": True}


def overview() -> dict[str, Any]:
    """Aggregate status. Never includes credentials or driver internals."""
    core = [database_status(), api_status()]
    # GitHub is reported for visibility but excluded from ``overall``: an
    # unconfigured OAuth app does not stop the public portfolio from working, so
    # it must not mark the whole service DEGRADED.
    services = [*core, github_status()]
    return {
        "overall": "ONLINE" if all(item["connected"] for item in core) else "DEGRADED",
        "services": services,
        "checked_at": iso(utcnow()),
    }
