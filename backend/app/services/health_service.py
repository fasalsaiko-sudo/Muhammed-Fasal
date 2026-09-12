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


def api_status() -> dict[str, Any]:
    return {"name": "api", "status": "ONLINE", "connected": True}


def overview() -> dict[str, Any]:
    """Aggregate status. Never includes credentials or driver internals."""
    services = [database_status(), api_status()]
    return {
        "overall": "ONLINE" if all(item["connected"] for item in services) else "DEGRADED",
        "services": services,
        "checked_at": iso(utcnow()),
    }
