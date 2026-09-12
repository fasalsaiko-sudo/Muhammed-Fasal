"""GitHub OAuth client and the authorization decision.

The authorization check happens here, on the backend. The Flutter app never
decides who is an administrator — it only renders whatever this service allows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from app.config.settings import Settings, get_settings

HTTP_TIMEOUT = 15.0


class GitHubAuthError(RuntimeError):
    """Raised when the OAuth exchange fails (mapped to a safe HTTP error)."""


class GitHubNotAuthorized(GitHubAuthError):
    """The GitHub account is valid but not on the administrator allowlist."""


@dataclass(frozen=True)
class GitHubIdentity:
    github_id: int
    username: str
    avatar_url: str | None = None
    display_name: str | None = None
    email: str | None = None


class GitHubClient(Protocol):
    def exchange_code(self, code: str) -> str: ...

    def fetch_user(self, access_token: str) -> dict[str, Any]: ...


class GitHubOAuthClient:
    """Minimal GitHub OAuth implementation (no third-party OAuth library)."""

    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        self._transport = transport

    def _client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {"timeout": HTTP_TIMEOUT, "follow_redirects": False}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def require_configured(self) -> None:
        """Fail loudly and early when OAuth is not configured.

        Without this the service would hand the visitor a GitHub URL missing
        ``client_id``, which GitHub answers with an opaque error page.
        """
        if not self.settings.github_client_id or not self.settings.github_client_secret:
            raise GitHubAuthError("GitHub sign-in is not configured on this server.")

    def authorize_url(self, state: str) -> str:
        self.require_configured()
        params = {
            "client_id": self.settings.github_client_id,
            "redirect_uri": self.settings.github_redirect_uri,
            "scope": "read:user user:email",
            "state": state,
            "allow_signup": "false",
        }
        return f"{self.settings.github_authorize_url}?{urlencode(params)}"

    def exchange_code(self, code: str) -> str:
        self.require_configured()
        payload = {
            "client_id": self.settings.github_client_id,
            "client_secret": self.settings.github_client_secret,
            "code": code,
            "redirect_uri": self.settings.github_redirect_uri,
        }
        headers = {"Accept": "application/json"}
        try:
            with self._client() as client:
                response = client.post(self.settings.github_token_url, data=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise GitHubAuthError("Unable to reach GitHub. Please try again.") from exc
        if response.status_code != 200:
            raise GitHubAuthError("GitHub rejected the sign-in attempt.")
        data = _parse_json(response)
        token = data.get("access_token")
        if not token:
            # GitHub reports errors in the body with a 200 status.
            raise GitHubAuthError(data.get("error_description") or "GitHub sign-in failed.")
        return str(token)

    def fetch_user(self, access_token: str) -> dict[str, Any]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            with self._client() as client:
                response = client.get(f"{self.settings.github_api_url}/user", headers=headers)
        except httpx.HTTPError as exc:
            raise GitHubAuthError("Unable to reach GitHub. Please try again.") from exc
        if response.status_code != 200:
            raise GitHubAuthError("GitHub did not return a profile.")
        return _parse_json(response)


def _parse_json(response: httpx.Response) -> dict[str, Any]:
    """Parse a GitHub response, turning malformed bodies into a clean error.

    A proxy or captive portal can return HTML with a 200 status; without this
    the JSON decode error would escape as an unhandled 500.
    """
    try:
        data = response.json()
    except ValueError as exc:
        raise GitHubAuthError("GitHub returned an unexpected response.") from exc
    if not isinstance(data, dict):
        raise GitHubAuthError("GitHub returned an unexpected response.")
    return data


def identity_from_payload(payload: dict[str, Any]) -> GitHubIdentity:
    github_id = payload.get("id")
    username = payload.get("login")
    if not isinstance(github_id, int) or not username:
        raise GitHubAuthError("GitHub returned an incomplete profile.")
    return GitHubIdentity(
        github_id=github_id,
        username=str(username),
        avatar_url=payload.get("avatar_url"),
        display_name=payload.get("name") or str(username),
        email=payload.get("email"),
    )


def is_allowed(username: str, settings: Settings | None = None) -> bool:
    """The single authorization gate for administrator access."""
    settings = settings or get_settings()
    return username.strip().lower() in settings.allowed_github_usernames


_client: GitHubClient | None = None


def get_github_client() -> GitHubClient:
    global _client
    if _client is None:
        _client = GitHubOAuthClient()
    return _client


def set_github_client(client: GitHubClient | None) -> None:
    """Tests inject a fake client; ``None`` restores the real one."""
    global _client
    _client = client
