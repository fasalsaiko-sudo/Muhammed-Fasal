"""Health and liveness endpoints."""

from __future__ import annotations


def test_liveness_probe(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_health_reports_database_and_api(client):
    body = client.get("/health").json()
    assert body["overall"] == "ONLINE"
    names = {service["name"] for service in body["services"]}
    assert names == {"database", "api", "github"}
    # GitHub reports configuration state only - connection is session-specific
    # and belongs to /auth/me.
    github = next(s for s in body["services"] if s["name"] == "github")
    assert github["status"] in {"CONFIGURED", "UNCONFIGURED"}
    assert body["checked_at"]


def test_health_exposes_no_connection_details(client):
    text = client.get("/health").text.lower()
    for forbidden in ("postgresql", "psycopg", "sqlite", "password", "://", "/home/"):
        assert forbidden not in text, forbidden


def test_health_reports_degraded_when_database_is_unreachable(client, monkeypatch):
    from app.services import health_service

    monkeypatch.setattr(health_service, "database_is_reachable", lambda: False)
    body = client.get("/health").json()
    assert body["overall"] == "DEGRADED"
    database = next(s for s in body["services"] if s["name"] == "database")
    assert database["status"] == "OFFLINE"


def test_health_endpoint_is_anonymous(client):
    """No session cookie is required — uptime checks are unauthenticated."""
    assert client.get("/health").status_code == 200
