"""GitHub OAuth login, sessions, authentication and authorization (Phase 5).

GitHub is always ``FakeGitHub`` — no live credentials are needed, and none of
these tests touch the network. The real ``GitHubOAuthClient`` is covered
separately in ``test_github_oauth_service.py``.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.config.database import get_session_factory
from app.models import AdminSession, OAuthState, User, UserRole, utcnow
from app.services import auth_service
from app.services.github_oauth import GitHubAuthError, set_github_client
from app.utils.security import hash_token

STATE_COOKIE = "mf_cms_oauth_state"


class FakeGitHub:
    """Stand-in for GitHubOAuthClient with the same three-method surface."""

    def __init__(self, *, username="Fasal17", payload=None, exchange_error=False, fetch_error=False):
        self.username = username
        self.payload = payload
        self.exchange_error = exchange_error
        self.fetch_error = fetch_error
        self.codes: list[str] = []
        self.tokens: list[str] = []

    def authorize_url(self, state: str) -> str:
        return f"https://github.com/login/oauth/authorize?client_id=cid&state={state}&scope=read:user"

    def exchange_code(self, code: str) -> str:
        self.codes.append(code)
        if self.exchange_error:
            raise GitHubAuthError("rejected")
        return "gho_fake_access_token"

    def fetch_user(self, access_token: str) -> dict:
        self.tokens.append(access_token)
        if self.fetch_error:
            raise GitHubAuthError("no profile")
        if self.payload is not None:
            return self.payload
        return {"id": 4242, "login": self.username, "name": "Muhammed Fasal",
                "avatar_url": "https://avatars.example/4242", "email": "me@example.com"}


@pytest.fixture
def oauth(settings, monkeypatch):
    monkeypatch.setattr(settings, "github_client_id", "cid")
    monkeypatch.setattr(settings, "github_client_secret", "csec")
    monkeypatch.setattr(settings, "github_redirect_uri", "http://testserver/auth/github/callback")
    monkeypatch.setattr(settings, "allowed_github_username", "Fasal17")
    return settings


@pytest.fixture
def gh(oauth):
    fake = FakeGitHub()
    set_github_client(fake)
    try:
        yield fake
    finally:
        set_github_client(None)


def _begin(client) -> tuple[object, str]:
    response = client.get("/auth/github", follow_redirects=False)
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    return response, state


def _callback(client, state, code="the-code", *, cookie_state="__jar__"):
    headers = {}
    if cookie_state != "__jar__":
        headers["Cookie"] = f"{STATE_COOKIE}={cookie_state}" if cookie_state else ""
    return client.get(
        "/auth/github/callback",
        params={"code": code, "state": state},
        headers=headers,
        follow_redirects=False,
    )


def _login(client, gh) -> object:
    _, state = _begin(client)
    return _callback(client, state)


def _session_rows():
    factory = get_session_factory()
    with factory() as db:
        return list(db.scalars(select(AdminSession)))


def _release(db) -> None:
    """End the fixture session's transaction so its connection is returned.

    The test database runs on PGlite, whose socket server serves exactly one
    connection at a time (verified: a second connect() times out while the first
    is mid-transaction). Tests run under NullPool, so every session is its own
    connection. Any test that reads through ``db`` and then makes another request
    must release this transaction first or it will hold the only connection.
    """
    db.commit()


# ======================================================= unauthenticated -> 401
def test_me_without_cookie_is_401(client, gh):
    assert client.get("/auth/me").status_code == 401


def test_logout_without_cookie_is_401(client, gh):
    assert client.post("/auth/logout").status_code == 401


def test_forged_cookie_is_401(client, gh, oauth):
    client.cookies.set(oauth.session_cookie_name, "not-a-real-token")
    assert client.get("/auth/me").status_code == 401


def test_well_formed_but_unknown_token_is_401(client, gh, oauth):
    client.cookies.set(oauth.session_cookie_name, "a" * 43)
    assert client.get("/auth/me").status_code == 401


def test_revoked_session_is_401(client, gh, oauth, db):
    _login(client, gh)
    row = _session_rows()[0]
    row.revoked = True
    db.add(row)
    db.commit()
    assert client.get("/auth/me").status_code == 401


def test_expired_session_is_401(client, gh, oauth, db):
    _login(client, gh)
    row = _session_rows()[0]
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.add(row)
    db.commit()
    assert client.get("/auth/me").status_code == 401


def test_idle_timed_out_session_is_401(client, gh, oauth, db, monkeypatch):
    _login(client, gh)
    monkeypatch.setattr(oauth, "session_idle_ttl_minutes", 30)
    row = _session_rows()[0]
    row.last_seen_at = utcnow() - timedelta(minutes=31)
    db.add(row)
    db.commit()
    assert client.get("/auth/me").status_code == 401


def test_logout_without_csrf_header_is_403(client, gh):
    _login(client, gh)
    response = client.post("/auth/logout")
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


# ============================================================ login initiation
def test_begin_login_redirects_to_github(client, gh, oauth):
    response, state = _begin(client)
    assert response.status_code == 302
    assert response.headers["location"].startswith(oauth.github_authorize_url)
    assert len(state) >= 32


def test_state_is_persisted_hashed_and_unused(client, gh, db):
    _, state = _begin(client)
    row = db.scalar(select(OAuthState))
    assert row is not None
    assert row.state_hash == hash_token(state)
    assert row.state_hash != state          # raw value is never stored
    assert row.used_at is None
    assert row.expires_at > utcnow()


def test_begin_login_unconfigured_is_503_and_creates_no_state(client, gh, oauth, monkeypatch, db):
    monkeypatch.setattr(oauth, "github_client_secret", "")
    response = client.get("/auth/github", follow_redirects=False)
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
    assert db.scalar(select(OAuthState)) is None


def test_begin_login_is_rate_limited(client, gh, oauth, monkeypatch):
    from app.middleware.rate_limit import get_limiter

    monkeypatch.setattr(oauth, "rate_limit_enabled", True)
    monkeypatch.setattr(oauth, "rate_limit_auth_per_minute", 2)
    get_limiter().reset()
    assert [client.get("/auth/github", follow_redirects=False).status_code for _ in range(2)] == [302, 302]
    assert client.get("/auth/github", follow_redirects=False).status_code == 429


# ================================================================= state handling
def test_callback_without_state_is_400(client, gh):
    _begin(client)
    response = client.get("/auth/github/callback", params={"code": "c"}, follow_redirects=False)
    assert response.status_code == 400


def test_callback_with_unknown_state_is_400(client, gh):
    _begin(client)
    assert _callback(client, "never-issued").status_code == 400


def test_callback_with_expired_state_is_400(client, gh, db):
    _, state = _begin(client)
    row = db.scalar(select(OAuthState))
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.add(row)
    db.commit()
    assert _callback(client, state).status_code == 400


def test_state_replay_is_rejected_and_creates_no_second_session(client, gh):
    begun, state = _begin(client)
    binding = begun.cookies.get(STATE_COOKIE)
    assert binding, "the binding cookie must be set on initiation"

    first = _callback(client, state)
    assert first.status_code == 302
    assert len(_session_rows()) == 1

    # Replay with the cookie deliberately re-sent: the successful callback clears
    # it, so without this the cookie check alone would reject the replay and the
    # server-side single-use guard would go untested.
    replay = _callback(client, state, cookie_state=binding)
    assert replay.status_code == 400
    assert len(_session_rows()) == 1        # no second session was created


def test_consume_state_rejects_a_second_sequential_call(db, oauth):
    """The single-use guard itself, isolated from cookies and HTTP."""
    from app.services import auth_service

    raw = auth_service.issue_state(db, oauth, ip_address="203.0.113.9")
    assert auth_service.consume_state(db, raw) is True
    assert auth_service.consume_state(db, raw) is False
    assert auth_service.consume_state(db, None) is False
    assert auth_service.consume_state(db, "never-issued") is False


def test_state_cannot_be_reused_across_two_attempts(client, gh):
    _, state = _begin(client)
    assert _callback(client, state).status_code == 302
    assert _callback(client, state).status_code == 400


def test_state_from_a_different_browser_session_is_rejected(client, gh):
    _, state = _begin(client)
    # Same state, but presented without the matching binding cookie.
    assert _callback(client, state, cookie_state="someone-elses-state").status_code == 400
    assert _callback(client, state, cookie_state="").status_code == 400


def test_state_is_consumed_even_when_github_rejects_the_code(client, gh, db):
    _, state = _begin(client)
    gh.exchange_error = True
    assert _callback(client, state).status_code == 401

    row = db.scalar(select(OAuthState))
    used = row.used_at
    _release(db)                            # free the connection before the replay
    assert used is not None                 # consumed, not returned to the pool
    assert _callback(client, state).status_code == 400


def test_consume_state_is_atomic_under_concurrent_callers(db):
    """Two callers read the same unused row; exactly one may consume it."""
    from app.config.settings import get_settings

    raw = auth_service.issue_state(db, get_settings(), "127.0.0.1")

    factory = get_session_factory()
    with factory() as first, factory() as second:
        results = [
            auth_service.consume_state(first, raw),
            auth_service.consume_state(second, raw),
        ]
    assert results == [True, False], f"expected exactly one winner, got {results}"


# ================================================================ callback outcomes
def test_callback_with_github_error_param_is_401(client, gh):
    _begin(client)
    response = client.get(
        "/auth/github/callback", params={"error": "access_denied", "state": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 401


def test_callback_when_token_exchange_fails_is_401(client, gh):
    _, state = _begin(client)
    gh.exchange_error = True
    assert _callback(client, state).status_code == 401
    assert _session_rows() == []


def test_callback_when_profile_fetch_fails_is_401(client, gh):
    _, state = _begin(client)
    gh.fetch_error = True
    assert _callback(client, state).status_code == 401
    assert _session_rows() == []


@pytest.mark.parametrize("payload", [{}, {"id": "x", "login": "Fasal17"}, {"login": "Fasal17"}])
def test_callback_with_incomplete_profile_is_401(client, gh, payload):
    _, state = _begin(client)
    gh.payload = payload
    assert _callback(client, state).status_code == 401
    assert _session_rows() == []


def test_successful_login_creates_session_cookie_and_audit(client, gh, oauth, db):
    response = _login(client, gh)
    assert response.status_code == 302
    assert response.headers["location"] == oauth.admin_url
    assert response.cookies.get(oauth.session_cookie_name)
    assert response.cookies.get(oauth.csrf_cookie_name)

    user = db.scalar(select(User))
    assert user.github_username == "Fasal17"
    assert user.last_login_at is not None
    assert len(list(db.scalars(select(AdminSession)))) == 1
    _release(db)

    from app.models.audit import AuditLog

    assert db.scalar(select(AuditLog).where(AuditLog.action == "LOGIN")).status == "SUCCESS"


def test_only_the_token_hash_is_stored(client, gh, oauth, db):
    response = _login(client, gh)
    raw = response.cookies.get(oauth.session_cookie_name)
    stored = _session_rows()[0].session_token_hash
    assert stored == hash_token(raw)
    assert raw not in stored
    assert stored != raw


def test_second_login_creates_a_second_working_session(client, gh):
    assert _login(client, gh).status_code == 302
    assert _login(client, gh).status_code == 302
    assert len(_session_rows()) == 2
    assert client.get("/auth/me").status_code == 200


# ================================================================ authorization
def test_account_not_on_allowlist_is_403_and_gets_no_user_row(client, gh, db):
    gh.username = "attacker"
    _, state = _begin(client)
    assert _callback(client, state).status_code == 403
    assert db.scalar(select(User)) is None
    _release(db)
    assert _session_rows() == []


@pytest.mark.parametrize("username", ["Fasal17", "fasal17", "  FASAL17  "])
def test_allowlist_match_is_trimmed_and_case_insensitive(client, gh, username):
    gh.username = username
    assert _login(client, gh).status_code == 302


def test_inactive_allowlisted_account_is_403(client, gh, db):
    _login(client, gh)
    user = db.scalar(select(User))
    user.is_active = False
    db.add(user)
    db.commit()
    client.cookies.clear()

    _, state = _begin(client)
    assert _callback(client, state).status_code == 403


def test_denial_reasons_are_indistinguishable(client, gh, db):
    gh.username = "attacker"
    _, state = _begin(client)
    not_allowlisted = _callback(client, state)

    client.cookies.clear()
    gh.username = "Fasal17"          # allowlisted this time, so a user row is created
    _login(client, gh)
    user = db.scalar(select(User))
    assert user is not None
    user.is_active = False
    db.add(user)
    db.commit()
    client.cookies.clear()
    _, state2 = _begin(client)
    inactive = _callback(client, state2)

    assert not_allowlisted.status_code == inactive.status_code == 403
    assert not_allowlisted.json() == inactive.json()


# ============================================================== expiry semantics
def test_absolute_expiry_is_never_extended_by_activity(client, gh, db):
    _login(client, gh)
    before = _session_rows()[0].expires_at

    assert client.get("/auth/me").status_code == 200
    after = _session_rows()[0].expires_at
    assert after == before, "activity must not extend the absolute deadline"


def test_activity_refreshes_idle_but_not_absolute(client, gh, db):
    _login(client, gh)
    row = _session_rows()[0]
    absolute, idle = row.expires_at, row.last_seen_at

    assert client.get("/auth/me").status_code == 200
    row = _session_rows()[0]
    assert row.expires_at == absolute
    assert row.last_seen_at >= idle


def test_session_dies_at_absolute_expiry_even_when_used(client, gh, db):
    _login(client, gh)
    row = _session_rows()[0]
    row.expires_at = utcnow() - timedelta(seconds=1)
    row.last_seen_at = utcnow()          # recently active, but past the deadline
    db.add(row)
    db.commit()
    assert client.get("/auth/me").status_code == 401


def test_rejected_session_is_not_refreshed(client, gh, db):
    _login(client, gh)
    row = _session_rows()[0]
    row.revoked = True
    frozen_absolute, frozen_idle = row.expires_at, row.last_seen_at
    db.add(row)
    db.commit()

    assert client.get("/auth/me").status_code == 401

    row = _session_rows()[0]
    assert row.revoked is True
    assert row.expires_at == frozen_absolute
    assert row.last_seen_at == frozen_idle


def test_session_cap_revokes_the_oldest(client, gh, oauth, monkeypatch):
    monkeypatch.setattr(oauth, "max_sessions_per_user", 2)
    for _ in range(4):
        assert _login(client, gh).status_code == 302

    rows = _session_rows()
    assert len(rows) == 4
    assert sum(1 for r in rows if not r.revoked) == 2


# ==================================================================== authorized
def test_me_returns_the_caller_identity(client, gh):
    _login(client, gh)
    payload = client.get("/auth/me").json()
    assert payload["github_username"] == "Fasal17"
    assert payload["display_name"] == "Muhammed Fasal"
    assert payload["avatar_url"] == "https://avatars.example/4242"
    assert payload["role"] == "ADMIN"


def test_me_never_exposes_session_internals(client, gh):
    _login(client, gh)
    payload = client.get("/auth/me").json()
    assert set(payload) == {"id", "github_username", "display_name", "avatar_url", "role"}
    for forbidden in ("session_token_hash", "ip_address", "user_agent", "revoked", "expires_at"):
        assert forbidden not in payload


def test_logout_revokes_and_clears_cookies(client, gh, oauth):
    _login(client, gh)
    csrf = client.cookies.get(oauth.csrf_cookie_name)
    response = client.post("/auth/logout", headers={oauth.csrf_header_name: csrf})

    assert response.status_code == 204
    assert _session_rows()[0].revoked is True


def test_cookie_is_unusable_after_logout(client, gh, oauth):
    _login(client, gh)
    token = client.cookies.get(oauth.session_cookie_name)
    csrf = client.cookies.get(oauth.csrf_cookie_name)
    client.post("/auth/logout", headers={oauth.csrf_header_name: csrf})

    client.cookies.clear()
    client.cookies.set(oauth.session_cookie_name, token)
    assert client.get("/auth/me").status_code == 401


# ============================================================ guard for phase 7-8
@pytest.fixture
def probe_app(app, settings):
    """Bolt a protected route onto the real app to test the guard contract."""
    from fastapi import Depends

    from app.routes.dependencies import require_admin

    @app.get("/_probe/admin")
    def _protected(user=Depends(require_admin)):  # noqa: B008 - FastAPI dependency idiom
        return {"ok": True, "username": user.github_username}

    return app


@pytest.fixture
def probe_client(probe_app):
    from fastapi.testclient import TestClient

    with TestClient(probe_app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_protected_route_without_session_is_401(probe_client, gh):
    assert probe_client.get("/_probe/admin").status_code == 401


def test_protected_route_with_non_admin_role_is_403(probe_client, gh, db):
    """A valid session is not enough: the role gate must reject EDITOR/VIEWER."""
    _login(probe_client, gh)
    assert probe_client.get("/_probe/admin").status_code == 200

    for role in (UserRole.EDITOR, UserRole.VIEWER):
        user = db.scalar(select(User))
        user.role = role
        db.add(user)
        db.commit()
        response = probe_client.get("/_probe/admin")
        assert response.status_code == 403, f"{role} must not reach admin routes"
        assert "not authorized" in response.json()["detail"].lower()


def test_protected_route_with_admin_session_is_200(probe_client, gh):
    _login(probe_client, gh)
    response = probe_client.get("/_probe/admin")
    assert response.status_code == 200
    assert response.json()["username"] == "Fasal17"


def test_protected_route_with_revoked_session_is_401(probe_client, gh, db):
    _login(probe_client, gh)
    row = _session_rows()[0]
    row.revoked = True
    db.add(row)
    db.commit()
    assert probe_client.get("/_probe/admin").status_code == 401


# ======================================================================= cookies
def test_session_cookie_flags(client, gh, oauth):
    response = _login(client, gh)
    header = response.headers.get_list("set-cookie")
    session_cookie = next(h for h in header if h.startswith(f"{oauth.session_cookie_name}="))
    assert "httponly" in session_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()
    assert "path=/" in session_cookie.lower()


def test_csrf_cookie_is_readable_but_session_cookie_is_not(client, gh, oauth):
    response = _login(client, gh)
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(h for h in cookies if h.startswith(f"{oauth.session_cookie_name}="))
    csrf_cookie = next(h for h in cookies if h.startswith(f"{oauth.csrf_cookie_name}="))
    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie


def test_secure_flag_follows_configuration(client, gh, oauth, monkeypatch):
    """Secure is present when configured and absent when not.

    Asserted on the initiation response: once cookies are Secure an http:// test
    client cannot echo them back, so the callback cannot complete over plain HTTP
    - which is exactly the browser behaviour being relied on.
    """
    monkeypatch.setattr(oauth, "cookie_secure", True)
    cookies = client.get("/auth/github", follow_redirects=False).headers.get_list("set-cookie")
    assert cookies and all("secure" in c.lower() for c in cookies)

    monkeypatch.setattr(oauth, "cookie_secure", False)
    client.cookies.clear()
    cookies = client.get("/auth/github", follow_redirects=False).headers.get_list("set-cookie")
    assert cookies and all("secure" not in c.lower() for c in cookies)


def test_csrf_header_must_match_the_session(client, gh, oauth):
    _login(client, gh)
    assert client.post("/auth/logout", headers={oauth.csrf_header_name: "wrong"}).status_code == 403
    csrf = client.cookies.get(oauth.csrf_cookie_name)
    assert client.post("/auth/logout", headers={oauth.csrf_header_name: csrf}).status_code == 204


def test_csrf_is_not_required_on_safe_methods(client, gh):
    _login(client, gh)
    assert client.get("/auth/me").status_code == 200


def test_csrf_token_is_bound_to_the_session(client, gh, oauth):
    """A CSRF value from one session must not validate another."""
    _login(client, gh)
    first_csrf = client.cookies.get(oauth.csrf_cookie_name)
    _login(client, gh)
    second_csrf = client.cookies.get(oauth.csrf_cookie_name)
    assert first_csrf != second_csrf


# ====================================================================== leakage
def test_no_token_or_secret_appears_in_responses_or_logs(client, gh, oauth, caplog):
    with caplog.at_level("DEBUG"):
        _login(client, gh)
        client.get("/auth/me")

    bodies = "\n".join(
        str(response.text) for response in [client.get("/auth/me")]
    )
    logs = "\n".join(record.getMessage() for record in caplog.records)
    for secret in ("csec", "gho_fake_access_token", oauth.session_secret):
        assert secret not in bodies
        assert secret not in logs


def test_health_reports_oauth_configuration_only(client, gh, oauth, monkeypatch):
    services = {s["name"]: s["status"] for s in client.get("/health").json()["services"]}
    assert services["github"] == "CONFIGURED"

    monkeypatch.setattr(oauth, "github_client_secret", "")
    from app.utils.cache import reset_cache

    reset_cache()
    services = {s["name"]: s["status"] for s in client.get("/health").json()["services"]}
    assert services["github"] == "UNCONFIGURED"

    body = client.get("/health").text
    assert "cid" not in body
    assert "csec" not in body
    assert oauth.github_redirect_uri not in body
    assert "Fasal17" not in body


def test_openapi_documents_the_auth_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    for expected in ("/auth/github", "/auth/github/callback", "/auth/me", "/auth/logout"):
        assert expected in paths
    assert "/auth/status" not in paths
