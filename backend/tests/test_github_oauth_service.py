"""GitHub OAuth service — mock-tested, no live credentials required.

Status: **implemented and mock-tested — live verification pending credentials.**
Every test here runs against ``httpx.MockTransport``, so the suite never needs a
real OAuth application. The real ``GitHubOAuthClient`` code path is exercised;
only the network boundary is faked.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.services import github_oauth
from app.services.github_oauth import (
    GitHubAuthError,
    GitHubOAuthClient,
    identity_from_payload,
    is_allowed,
)

CLIENT_SECRET = "super-secret-value-that-must-never-leak"


@pytest.fixture
def oauth_settings(settings, monkeypatch):
    monkeypatch.setattr(settings, "github_client_id", "test-client-id")
    monkeypatch.setattr(settings, "github_client_secret", CLIENT_SECRET)
    monkeypatch.setattr(settings, "github_redirect_uri", "https://api.example.com/auth/github/callback")
    monkeypatch.setattr(settings, "allowed_github_username", "Fasal17")
    return settings


def _client(settings, handler) -> GitHubOAuthClient:
    return GitHubOAuthClient(settings=settings, transport=httpx.MockTransport(handler))


# ------------------------------------------------------------- authorize step
def test_authorize_url_carries_client_id_state_and_scopes(oauth_settings):
    url = GitHubOAuthClient(settings=oauth_settings).authorize_url("random-state-123")
    query = parse_qs(urlparse(url).query)

    assert url.startswith(oauth_settings.github_authorize_url)
    assert query["client_id"] == ["test-client-id"]
    assert query["state"] == ["random-state-123"]
    assert query["redirect_uri"] == ["https://api.example.com/auth/github/callback"]
    assert query["allow_signup"] == ["false"]
    assert "read:user" in query["scope"][0]


def test_authorize_url_never_contains_the_client_secret(oauth_settings):
    url = GitHubOAuthClient(settings=oauth_settings).authorize_url("state")
    assert CLIENT_SECRET not in url
    assert "client_secret" not in url


@pytest.mark.parametrize("field", ["github_client_id", "github_client_secret"])
def test_unconfigured_oauth_is_rejected_before_any_network_call(settings, monkeypatch, field):
    """A missing credential must produce a clear error, not a broken GitHub URL."""
    monkeypatch.setattr(settings, "github_client_id", "id")
    monkeypatch.setattr(settings, "github_client_secret", "secret")
    monkeypatch.setattr(settings, field, "")
    client = GitHubOAuthClient(settings=settings)

    with pytest.raises(GitHubAuthError) as excinfo:
        client.authorize_url("state")
    assert "not configured" in str(excinfo.value)

    with pytest.raises(GitHubAuthError):
        client.exchange_code("code")


# --------------------------------------------------------------- token exchange
def test_exchange_code_returns_the_access_token(oauth_settings):
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"access_token": "gho_token", "token_type": "bearer"})

    token = _client(oauth_settings, handler).exchange_code("the-code")
    assert token == "gho_token"
    assert seen["url"] == oauth_settings.github_token_url
    # The secret is sent to GitHub (required) but must not appear in logs.
    assert CLIENT_SECRET in str(seen["body"])


def test_exchange_code_sends_the_secret_but_never_logs_it(oauth_settings, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "gho_token"})

    with caplog.at_level("DEBUG"):
        _client(oauth_settings, handler).exchange_code("code")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert CLIENT_SECRET not in logged
    assert "gho_token" not in logged


def test_exchange_code_raises_on_http_error_status(oauth_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad_verification_code"})

    with pytest.raises(GitHubAuthError):
        _client(oauth_settings, handler).exchange_code("bad-code")


def test_exchange_code_raises_when_github_reports_error_in_a_200_body(oauth_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "redirect_uri_mismatch",
                                        "error_description": "The redirect_uri MUST match"})

    with pytest.raises(GitHubAuthError) as excinfo:
        _client(oauth_settings, handler).exchange_code("code")
    assert "redirect_uri" in str(excinfo.value)


def test_exchange_code_raises_on_a_non_json_200_response(oauth_settings):
    """A proxy or captive portal returning HTML must not surface as a 500."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(GitHubAuthError):
        _client(oauth_settings, handler).exchange_code("code")


def test_exchange_code_raises_when_github_is_unreachable(oauth_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(GitHubAuthError) as excinfo:
        _client(oauth_settings, handler).exchange_code("code")
    assert "Unable to reach GitHub" in str(excinfo.value)


def test_error_messages_never_echo_the_code_or_secret(oauth_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad_verification_code"})

    with pytest.raises(GitHubAuthError) as excinfo:
        _client(oauth_settings, handler).exchange_code("one-time-code-abc")
    message = str(excinfo.value)
    assert "one-time-code-abc" not in message
    assert CLIENT_SECRET not in message


# ------------------------------------------------------------------- user fetch
def test_fetch_user_returns_the_profile(oauth_settings):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json={"id": 4242, "login": "Fasal17", "name": "Muhammed Fasal"})

    payload = _client(oauth_settings, handler).fetch_user("gho_token")
    assert payload["login"] == "Fasal17"
    assert seen["auth"] == "Bearer gho_token"


def test_fetch_user_raises_on_401(oauth_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    with pytest.raises(GitHubAuthError):
        _client(oauth_settings, handler).fetch_user("expired")


def test_fetch_user_raises_when_unreachable(oauth_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    with pytest.raises(GitHubAuthError):
        _client(oauth_settings, handler).fetch_user("token")


def test_access_token_is_not_logged(oauth_settings, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": 1, "login": "Fasal17"})

    with caplog.at_level("DEBUG"):
        _client(oauth_settings, handler).fetch_user("gho_secret_token_value")
    assert "gho_secret_token_value" not in "\n".join(r.getMessage() for r in caplog.records)


# ------------------------------------------------- identity + authorization gate
def test_identity_from_payload_maps_all_fields():
    identity = identity_from_payload(
        {"id": 4242, "login": "Fasal17", "name": "Muhammed Fasal",
         "avatar_url": "https://avatars.example/4242", "email": "me@example.com"}
    )
    assert identity.github_id == 4242
    assert identity.username == "Fasal17"
    assert identity.display_name == "Muhammed Fasal"
    assert identity.email == "me@example.com"


def test_identity_falls_back_to_username_when_name_is_absent():
    assert identity_from_payload({"id": 1, "login": "Fasal17"}).display_name == "Fasal17"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"id": "not-an-int", "login": "Fasal17"},
        {"id": 1},
        {"login": "Fasal17"},
    ],
)
def test_incomplete_profile_is_rejected(payload):
    with pytest.raises(GitHubAuthError):
        identity_from_payload(payload)


def test_only_the_configured_administrator_is_allowed(oauth_settings):
    assert is_allowed("Fasal17", oauth_settings) is True
    assert is_allowed("  FASAL17  ", oauth_settings) is True  # trimmed + case-insensitive
    assert is_allowed("attacker", oauth_settings) is False
    assert is_allowed("", oauth_settings) is False
    assert is_allowed("Fasal170", oauth_settings) is False


def test_allowlist_supports_multiple_configured_admins(oauth_settings, monkeypatch):
    monkeypatch.setattr(oauth_settings, "allowed_github_username", "Fasal17, SecondAdmin")
    assert is_allowed("secondadmin", oauth_settings) is True
    assert is_allowed("third", oauth_settings) is False


# ------------------------------------------------------------- DI seam for tests
def test_client_can_be_injected_and_restored():
    class _Fake:
        def exchange_code(self, code: str) -> str:
            return "fake"

        def fetch_user(self, access_token: str) -> dict:
            return {"id": 1, "login": "Fasal17"}

    github_oauth.set_github_client(_Fake())
    try:
        assert github_oauth.get_github_client().exchange_code("x") == "fake"
    finally:
        github_oauth.set_github_client(None)
    assert isinstance(github_oauth.get_github_client(), GitHubOAuthClient)
