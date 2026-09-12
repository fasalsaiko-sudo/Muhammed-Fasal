"""Response models for the authentication endpoints.

Deliberately narrow: the authenticated user's own identity and nothing else. No
token, no session internals, no allowlist, no client configuration.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CurrentUser(BaseModel):
    """`GET /auth/me` — who the caller is."""

    model_config = ConfigDict(extra="ignore")

    id: int
    github_username: str
    display_name: str | None = None
    avatar_url: str | None = None
    role: str
