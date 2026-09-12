"""Security headers, CORS policy and rate limiting."""

from __future__ import annotations


def test_security_headers_on_every_response(client):
    headers = client.get("/health").headers
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"
    assert headers["cross-origin-opener-policy"] == "same-origin"
    assert "geolocation=()" in headers["permissions-policy"]


def test_api_csp_is_locked_down(client):
    csp = client.get("/health").headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_docs_csp_allows_swagger_ui(client):
    csp = client.get("/docs").headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "'unsafe-inline'" in csp


def test_server_header_is_removed(client):
    assert "Server" not in client.get("/health").headers


def test_hsts_only_over_https(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        assert "strict-transport-security" not in test_client.get("/health").headers

    settings.cookie_secure = True
    try:
        with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
            assert "max-age=" in test_client.get("/health").headers["strict-transport-security"]
    finally:
        settings.cookie_secure = False


def test_cors_blocks_unlisted_origin(client):
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_listed_origin(client, settings):
    origin = settings.cors_origins[0]
    response = client.get("/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_wildcard_cors_is_refused_at_startup(settings):
    import pytest

    from app.main import create_app

    settings.cors_allowed_origins = "*"
    try:
        with pytest.raises(ValueError, match="must not contain"):
            create_app(settings)
    finally:
        settings.cors_allowed_origins = "http://localhost:8080"


def test_rate_limit_returns_429_with_retry_after(client, settings, monkeypatch):
    from app.middleware.rate_limit import get_limiter

    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_public_per_minute", 2)
    get_limiter().reset()
    assert [client.get("/healthz").status_code for _ in range(2)] == [200, 200]
    limited = client.get("/healthz")
    assert limited.status_code == 429
    assert limited.headers["retry-after"].isdigit()
    assert "slow down" in limited.json()["detail"].lower()


def test_rate_limit_can_be_disabled(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_public_per_minute", 1)
    assert [client.get("/healthz").status_code for _ in range(5)] == [200] * 5
