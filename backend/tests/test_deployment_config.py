"""Deployment readiness: configuration that is safe to run in production.

These tests cover the boundary between "works on my machine" and "safe to
deploy". They assert what the application *refuses to start with*, because a
misconfiguration caught at boot cannot become a silent authentication bypass.

Nothing here talks to GitHub. External calls are either avoided (pure
configuration) or mocked.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config.settings import Settings
from app.models import OAuthState
from app.services.github_oauth import (
    GitHubAuthError,
    GitHubOAuthClient,
    get_github_client,
)

TEST_DB = "sqlite:///./deployment-test.db"
SECRET = "s3cr3t-value-that-must-never-be-echoed"

# conftest exports ENVIRONMENT/COOKIE_SECURE/RATE_LIMIT_ENABLED into os.environ,
# and Settings(_env_file=None) still reads os.environ. Every production case
# therefore states all of its inputs explicitly instead of inheriting them.
PROD = {
    "environment": "production",
    "database_url": "postgresql+psycopg://cms:real-password@db.internal:5432/cms",
    "session_secret": SECRET,
    "cookie_secure": True,
    "secure_errors": True,
    "rate_limit_enabled": True,
    "github_client_id": "Iv1.productionclientid",
    "github_client_secret": "gh-secret-placeholder",
    "github_redirect_uri": "https://api.example.com/auth/github/callback",
    "api_base_url": "https://api.example.com",
    "frontend_url": "https://fasalsaiko-sudo.github.io/Muhammed-Fasal/",
    "admin_url": "https://admin.example.com/admin",
    "allowed_github_username": "Fasal17",
    "cors_allowed_origins": "https://admin.example.com",
}


def prod_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{**PROD, **overrides})


def dev_settings(**overrides) -> Settings:
    base = {"environment": "development", "database_url": TEST_DB}
    return Settings(_env_file=None, **{**base, **overrides})


def failure_message(exc: BaseException) -> str:
    """The first 'Value error, ...' line, which is the message an operator sees."""
    text = str(exc)
    for line in text.splitlines():
        if "Value error," in line:
            return line.split("Value error,", 1)[1].strip()
    return text


# ================================================== GitHub OAuth configuration
def test_missing_github_configuration_is_detected():
    settings = dev_settings(github_client_id="", github_client_secret="")
    assert settings.github_oauth_configured is False


@pytest.mark.parametrize(
    ("client_id", "client_secret", "redirect_uri"),
    [
        ("", "", "https://api.example.com/auth/github/callback"),  # nothing set
        ("id", "", "https://api.example.com/auth/github/callback"),  # no secret
        ("", "secret", "https://api.example.com/auth/github/callback"),  # no id
        ("id", "secret", ""),  # no callback
    ],
)
def test_incomplete_github_configuration_is_never_reported_configured(
    client_id, client_secret, redirect_uri
):
    settings = dev_settings(
        github_client_id=client_id,
        github_client_secret=client_secret,
        github_redirect_uri=redirect_uri,
    )
    assert settings.github_oauth_configured is False


def test_unconfigured_client_refuses_to_build_an_authorize_url():
    """A URL missing client_id would send the visitor to an opaque GitHub error."""
    client = GitHubOAuthClient(dev_settings(github_client_id="", github_client_secret=""))
    with pytest.raises(GitHubAuthError):
        client.authorize_url("some-state")
    with pytest.raises(GitHubAuthError):
        client.exchange_code("some-code")


def test_configured_client_puts_the_redirect_uri_in_both_github_calls():
    """GitHub rejects the token exchange unless it matches the authorize URL."""
    settings = dev_settings(
        github_client_id="Iv1.id",
        github_client_secret="sec",
        github_redirect_uri="https://api.example.com/auth/github/callback",
    )
    url = GitHubOAuthClient(settings).authorize_url("state-123")
    assert "redirect_uri=https%3A%2F%2Fapi.example.com%2Fauth%2Fgithub%2Fcallback" in url
    assert "state=state-123" in url
    assert "allow_signup=false" in url


def test_production_requires_github_credentials():
    with pytest.raises(ValueError) as exc:
        prod_settings(github_client_id="", github_client_secret="")
    assert "GitHub OAuth" in failure_message(exc.value)


# ============================================================= CORS policy
def test_wildcard_origin_is_rejected_at_startup():
    with pytest.raises(ValueError) as exc:
        dev_settings(cors_allowed_origins="*")
    assert "must not contain '*'" in failure_message(exc.value)


def test_wildcard_mixed_with_real_origins_is_also_rejected():
    with pytest.raises(ValueError, match="must not contain"):
        dev_settings(cors_allowed_origins="https://admin.example.com,*")


def test_cors_entries_must_be_absolute_origins():
    with pytest.raises(ValueError) as exc:
        dev_settings(cors_allowed_origins="admin.example.com")
    assert "absolute http(s) origins" in failure_message(exc.value)


def test_origins_are_normalised_so_frontend_url_actually_matches():
    """A browser Origin header never carries a path, so paths must be stripped.

    Without this, FRONTEND_URL=https://user.github.io/Repo/ would be stored
    verbatim and never match a real Origin header - the admin would appear
    configured while every credentialed request was blocked.
    """
    settings = dev_settings(
        cors_allowed_origins="https://admin.example.com/dashboard",
        frontend_url="https://fasalsaiko-sudo.github.io/Muhammed-Fasal/",
        admin_url="https://admin.example.com/admin",
    )
    assert settings.cors_origins == [
        "https://admin.example.com",
        "https://fasalsaiko-sudo.github.io",
    ]


def test_duplicate_origins_are_collapsed():
    settings = dev_settings(
        cors_allowed_origins="https://a.example.com/x,https://a.example.com/y",
        frontend_url="https://a.example.com/z",
        admin_url="https://a.example.com",
    )
    assert settings.cors_origins == ["https://a.example.com"]


@pytest.mark.parametrize("env", ["production", "staging"])
def test_internet_facing_environments_reject_non_https_origins(env):
    with pytest.raises(ValueError) as exc:
        prod_settings(environment=env, cors_allowed_origins="http://admin.example.com")
    message = failure_message(exc.value)
    assert f"https when ENVIRONMENT={env}" in message


def test_production_rejects_a_leftover_localhost_frontend_url():
    """The dev default is appended to the allowlist, so it must be overridden.

    Left in place it would let any page on a visitor's own localhost make
    credentialed cross-origin requests to the admin API.
    """
    with pytest.raises(ValueError) as exc:
        prod_settings(frontend_url="http://localhost:8080")
    assert "localhost:8080" in failure_message(exc.value)


def test_cors_middleware_refuses_a_wildcard_even_when_built_directly():
    """Defence in depth for a Settings object built programmatically."""
    from fastapi import FastAPI

    from app.middleware.cors import build_cors_middleware

    settings = dev_settings()
    object.__setattr__(settings, "cors_allowed_origins", "*")
    with pytest.raises(ValueError, match="must not contain"):
        build_cors_middleware(FastAPI(), settings)


# ============================================================ cookie behaviour
def test_production_requires_secure_cookies():
    with pytest.raises(ValueError) as exc:
        prod_settings(cookie_secure=False)
    assert "COOKIE_SECURE" in failure_message(exc.value)


def test_samesite_none_requires_secure():
    with pytest.raises(ValueError) as exc:
        dev_settings(session_cookie_samesite="none", cookie_secure=False)
    assert "COOKIE_SECURE" in failure_message(exc.value)


def test_samesite_none_with_secure_is_accepted():
    assert dev_settings(session_cookie_samesite="None", cookie_secure=True).session_cookie_samesite == "none"


@pytest.mark.parametrize("value", ["", "disabled", "no", "Lax-ish"])
def test_unknown_samesite_value_is_rejected(value):
    with pytest.raises(ValueError, match="must be one of"):
        dev_settings(session_cookie_samesite=value)


def test_samesite_value_is_normalised_to_lowercase():
    for raw in ("LAX", "Strict", "lax"):
        assert dev_settings(session_cookie_samesite=raw).session_cookie_samesite == raw.lower()


# ==================================================== OAuth callback URL
@pytest.mark.parametrize(
    "redirect_uri",
    ["not-a-url", "ftp://api.example.com/cb", "api.example.com/auth/github/callback", "://x"],
)
def test_callback_url_must_be_an_absolute_http_url(redirect_uri):
    with pytest.raises(ValueError) as exc:
        dev_settings(github_redirect_uri=redirect_uri)
    assert "absolute http(s) URL" in failure_message(exc.value)


@pytest.mark.parametrize("env", ["production", "staging"])
def test_internet_facing_environments_require_an_https_callback(env):
    with pytest.raises(ValueError) as exc:
        prod_settings(
            environment=env,
            github_redirect_uri="http://api.example.com/auth/github/callback",
            api_base_url="http://api.example.com",
        )
    assert f"https when ENVIRONMENT={env}" in failure_message(exc.value)


def test_production_callback_url_must_be_served_by_this_api():
    """Catches the most common live OAuth failure: redirect_uri_mismatch."""
    with pytest.raises(ValueError) as exc:
        prod_settings(github_redirect_uri="https://staging.example.com/auth/github/callback")
    assert "API_BASE_URL" in failure_message(exc.value)


def test_production_callback_url_may_sit_behind_a_path_prefix():
    settings = prod_settings(
        api_base_url="https://api.example.com/cms",
        github_redirect_uri="https://api.example.com/cms/auth/github/callback",
    )
    assert settings.github_redirect_uri.startswith(settings.api_base_url)


# ============================================ production vs development policy
@pytest.mark.parametrize(
    "overrides",
    [
        {"allowed_github_username": ""},
        {"secure_errors": False},
        {"rate_limit_enabled": False},
        {"cookie_secure": False},
        {"database_url": "postgresql+psycopg://cms:change-me@db:5432/cms"},
    ],
)
def test_staging_is_hardened_exactly_like_production(overrides):
    """Staging rehearses the deployment, so it may not be hardened less.

    Before this, ENVIRONMENT=staging booted with secure_errors off, rate
    limiting off, no administrator allowlist and http CORS origins - it would
    have validated nothing that production depends on.
    """
    with pytest.raises(ValueError):
        prod_settings(environment="staging", **overrides)
    # And the same override is refused in production, so the two cannot drift.
    with pytest.raises(ValueError):
        prod_settings(environment="production", **overrides)


def test_staging_does_not_serve_api_docs_by_default():
    assert prod_settings(environment="staging").serve_api_docs is False


def test_production_requires_an_explicit_administrator_allowlist():
    """There is no hardcoded admin; a stale default must not survive a deploy."""
    with pytest.raises(ValueError) as exc:
        prod_settings(allowed_github_username="")
    assert "ALLOWED_GITHUB_USERNAME" in failure_message(exc.value)


def test_no_administrator_is_hardcoded_in_the_defaults():
    assert Settings.model_fields["allowed_github_username"].default == ""


def test_production_requires_a_real_database_password():
    with pytest.raises(ValueError) as exc:
        prod_settings(database_url="postgresql+psycopg://cms:change-me@db:5432/cms")
    assert "placeholder password" in failure_message(exc.value)


def test_the_database_url_is_not_echoed_in_that_error():
    """The message names the problem without publishing the connection string.

    Deploy logs are widely readable; a URL with credentials in it must not be
    printed just because it was rejected.
    """
    url = "postgresql+psycopg://cms_user:change-me@db.internal:5432/cms"
    with pytest.raises(ValueError) as exc:
        prod_settings(database_url=url)
    text = str(exc.value)
    assert "placeholder password" in text
    assert url not in text
    assert "cms_user" not in text
    assert "db.internal" not in text


def test_production_requires_secure_errors_and_rate_limiting():
    with pytest.raises(ValueError, match="SECURE_ERRORS"):
        prod_settings(secure_errors=False)
    with pytest.raises(ValueError, match="RATE_LIMIT_ENABLED"):
        prod_settings(rate_limit_enabled=False)


def test_production_requires_a_session_secret():
    with pytest.raises(ValueError, match="SESSION_SECRET"):
        prod_settings(session_secret="")


def test_development_still_works_with_minimal_configuration():
    """Hardening production must not make local development unusable."""
    settings = dev_settings()
    assert len(settings.session_secret) >= 32  # ephemeral, documented
    assert settings.cookie_secure is False
    assert settings.github_oauth_configured is False  # sign-in simply unavailable


def test_idle_window_may_not_exceed_the_absolute_one():
    with pytest.raises(ValueError) as exc:
        dev_settings(session_ttl_minutes=10, session_idle_ttl_minutes=60)
    assert "SESSION_IDLE_TTL_MINUTES" in failure_message(exc.value)


@pytest.mark.parametrize("minutes", [0, -5])
def test_non_positive_session_windows_are_rejected(minutes):
    with pytest.raises(ValueError, match="must be positive"):
        dev_settings(session_ttl_minutes=minutes)


def test_non_positive_state_ttl_is_rejected():
    with pytest.raises(ValueError, match="OAUTH_STATE_TTL_SECONDS"):
        dev_settings(oauth_state_ttl_seconds=0)


# ============================================================ docs exposure
def test_production_never_serves_docs_by_default():
    assert prod_settings().serve_api_docs is False


def test_production_docs_need_both_switches():
    assert prod_settings(docs_enabled=True, docs_enabled_in_production=True).serve_api_docs is True
    assert prod_settings(docs_enabled=False, docs_enabled_in_production=True).serve_api_docs is False


def test_development_honours_the_docs_switch():
    assert dev_settings(docs_enabled=True).serve_api_docs is True
    assert dev_settings(docs_enabled=False).serve_api_docs is False


def test_production_app_exposes_no_openapi_document(settings):
    """End-to-end: the routes themselves are absent, not just unlinked."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.middleware.rate_limit import get_limiter

    get_limiter().reset()
    production = prod_settings(database_url=settings.database_url)
    assert production.serve_api_docs is False
    with TestClient(create_app(production)) as prod_client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert prod_client.get(path).status_code == 404, path


def test_development_app_serves_docs(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(dev_settings(database_url=settings.database_url))) as dev_client:
        assert dev_client.get("/openapi.json").status_code == 200


# ======================================================== health endpoint
def test_health_reports_github_as_configuration_only(client):
    """CONFIGURED/UNCONFIGURED only: connection is a property of a session."""
    body = client.get("/health").json()
    github = next(s for s in body["services"] if s["name"] == "github")
    assert github["status"] in {"CONFIGURED", "UNCONFIGURED"}
    # "connected" exists as a boolean field; the point is that no *status* claims
    # a live connection, which is session-specific and belongs to /auth/me.
    for service in body["services"]:
        assert service["status"] != "CONNECTED"


def test_health_never_contains_configured_secret_values(client, settings, monkeypatch):
    sentinels = {
        "github_client_secret": "SENTINEL-GITHUB-SECRET",
        "session_secret": "SENTINEL-SESSION-SECRET",
        "google_private_key": "SENTINEL-PRIVATE-KEY",
        "database_url": "postgresql+psycopg://cms:SENTINEL-DB-PASSWORD@db:5432/cms",
    }
    for key, value in sentinels.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(settings, "github_client_id", "SENTINEL-CLIENT-ID")
    body = client.get("/health").text
    for value in sentinels.values():
        assert value not in body, value
    assert "SENTINEL-CLIENT-ID" not in body
    assert "SENTINEL-DB-PASSWORD" not in body


def test_unconfigured_oauth_does_not_mark_the_whole_service_degraded(client, settings, monkeypatch):
    """The public portfolio must stay ONLINE without an OAuth app configured."""
    monkeypatch.setattr(settings, "github_client_id", "")
    monkeypatch.setattr(settings, "github_client_secret", "")
    body = client.get("/health").json()
    github = next(s for s in body["services"] if s["name"] == "github")
    assert github["status"] == "UNCONFIGURED"
    assert body["overall"] == "ONLINE"


# ============================================ no secrets in errors or logs
def test_validation_errors_do_not_echo_secret_values():
    """A typo in .env should not end up printed in a deploy log with the secret."""
    with pytest.raises(ValueError) as exc:
        prod_settings(
            github_redirect_uri="https://other.example.com/cb",
            github_client_secret="SENTINEL-GITHUB-SECRET",
            session_secret="SENTINEL-SESSION-SECRET",
        )
    text = str(exc.value)
    assert "SENTINEL-GITHUB-SECRET" not in text
    assert "SENTINEL-SESSION-SECRET" not in text


def test_unhandled_error_response_contains_no_configuration_secrets(client, settings, monkeypatch):
    from app.routes.public import public_router

    sentinel = "SENTINEL-LEAKED-SECRET"
    monkeypatch.setattr(settings, "github_client_secret", sentinel)
    monkeypatch.setattr(settings, "session_secret", sentinel)

    @public_router.get("/_boom")
    def _boom():
        raise RuntimeError(f"boom {sentinel}")

    try:
        response = client.get("/api/_boom")
        assert response.status_code == 500
        assert sentinel not in response.text
        assert "RuntimeError" not in response.text
        assert "Traceback" not in response.text
    finally:
        public_router.routes = [r for r in public_router.routes if r.path != "/_boom"]


def test_expired_oauth_states_are_purged(db, settings):
    """Bounded table growth without needing a scheduled job."""
    from datetime import timedelta

    from app.models import utcnow
    from app.services import auth_service

    auth_service.issue_state(db, settings, ip_address="203.0.113.5")
    row = db.scalar(select(OAuthState))
    assert row is not None and row.used_at is None
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.add(row)
    db.commit()

    assert auth_service.purge_expired_states(db) == 1
    assert db.scalar(select(OAuthState)) is None


def test_a_consumed_state_is_not_purged_as_expired(db, settings):
    """used_at and expiry are independent; consuming must not delete evidence."""
    from app.services import auth_service

    raw = auth_service.issue_state(db, settings, ip_address="203.0.113.5")
    assert auth_service.consume_state(db, raw) is True
    assert auth_service.purge_expired_states(db) == 0
    assert db.scalar(select(OAuthState)).used_at is not None


def test_get_github_client_is_the_injection_seam():
    """Tests swap the client here; production code never knows the difference."""
    assert get_github_client() is not None
