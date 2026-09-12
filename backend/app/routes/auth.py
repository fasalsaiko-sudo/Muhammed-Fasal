"""GitHub OAuth login, callback, identity and logout (spec §6).

Authorization is decided here, on the backend. The Flutter admin is a client and
is never trusted to decide who may administer the CMS.

Ordering that matters:
* the OAuth state is **consumed before** the GitHub code is exchanged, so a
  replayed callback can never reach GitHub twice;
* the allowlist check happens **before** a ``users`` row is created, so an
  arbitrary GitHub account cannot populate the table.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.settings import Settings, get_settings
from app.middleware.rate_limit import rate_limit_dependency
from app.routes.dependencies import get_current_pair, get_current_user, require_csrf
from app.schemas.auth import CurrentUser
from app.services import auth_service
from app.services.github_oauth import (
    GitHubAuthError,
    GitHubIdentity,
    get_github_client,
    identity_from_payload,
    is_allowed,
)
from app.utils.security import constant_time_equals

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["auth"])

_auth_limit = rate_limit_dependency("auth", "rate_limit_auth_per_minute")

STATE_COOKIE = "mf_cms_oauth_state"

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign-in with GitHub failed."
)
BAD_STATE = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST, detail="The sign-in request is no longer valid."
)
NOT_AUTHORIZED = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="This account is not authorized to access the CMS.",
)

DbSession = Annotated[Session, Depends(get_db)]


def _cookie_kwargs(settings: Settings, *, http_only: bool, max_age: int) -> dict[str, object]:
    return {
        "httponly": http_only,
        "secure": settings.cookie_secure,
        "samesite": settings.session_cookie_samesite,
        "path": "/",
        "max_age": max_age,
    }


@auth_router.get(
    "/github",
    summary="Begin GitHub sign-in",
    dependencies=[Depends(_auth_limit)],
    include_in_schema=True,
)
def begin_login(request: Request, db: DbSession, settings: Annotated[Settings, Depends(get_settings)]):
    if not settings.github_oauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub sign-in is not configured on this server.",
        )

    raw_state = auth_service.issue_state(db, settings, request.client.host if request.client else None)
    url = get_github_client().authorize_url(raw_state)

    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    # Binding cookie: the callback requires the state to match what this browser
    # was issued. Single-use itself is guaranteed by the oauth_states row.
    response.set_cookie(
        STATE_COOKIE,
        raw_state,
        **_cookie_kwargs(settings, http_only=True, max_age=settings.oauth_state_ttl_seconds),
    )
    return response


@auth_router.get(
    "/github/callback",
    summary="GitHub OAuth callback",
    dependencies=[Depends(_auth_limit)],
    include_in_schema=True,
)
def oauth_callback(request: Request, db: DbSession, settings: Annotated[Settings, Depends(get_settings)]):
    params = request.query_params
    if params.get("error"):
        raise UNAUTHORIZED

    state = params.get("state")
    cookie_state = request.cookies.get(STATE_COOKIE)
    if not state or not cookie_state or not constant_time_equals(state, cookie_state):
        # Missing, mismatched, or presented from a different browser session.
        raise BAD_STATE

    # Consume BEFORE any call to GitHub. Atomic and irreversible.
    if not auth_service.consume_state(db, state):
        logger.info("oauth_state_rejected reason=unknown_used_or_expired")
        raise BAD_STATE

    code = params.get("code")
    if not code:
        raise BAD_STATE

    client = get_github_client()
    try:
        access_token = client.exchange_code(code)
        payload = client.fetch_user(access_token)
        identity: GitHubIdentity = identity_from_payload(payload)
    except GitHubAuthError as exc:
        logger.info("oauth_failed reason=%s", type(exc).__name__)
        auth_service.record_login(db, None, success=False, reason="github_rejected")
        raise UNAUTHORIZED from exc

    # Authorization decision — backend only. Checked before any row is created.
    if not is_allowed(identity.username, settings):
        logger.info("oauth_denied username_hash=%s", auth_service.hash_username(identity.username))
        auth_service.record_login(db, None, success=False, reason="not_allowlisted")
        raise NOT_AUTHORIZED

    user = auth_service.upsert_user(db, identity)
    if not user.is_active:
        auth_service.record_login(db, user, success=False, reason="inactive")
        raise NOT_AUTHORIZED

    raw_token, csrf_token = auth_service.create_session(
        db,
        settings,
        user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    auth_service.record_login(db, user, success=True)

    response = RedirectResponse(settings.admin_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        settings.session_cookie_name,
        raw_token,
        **_cookie_kwargs(settings, http_only=True, max_age=settings.session_ttl_seconds),
    )
    # Readable by the admin's JavaScript so it can be echoed in a header.
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        **_cookie_kwargs(settings, http_only=False, max_age=settings.session_ttl_seconds),
    )
    response.delete_cookie(STATE_COOKIE, path="/")
    return response


@auth_router.get("/me", response_model=CurrentUser, summary="Current administrator")
def me(user: Annotated[object, Depends(get_current_user)]) -> dict[str, object]:
    """The caller's own identity. 401 when unauthenticated.

    No token, no session internals, no allowlist, no client configuration.
    """
    return {
        "id": user.id,
        "github_username": user.github_username,
        "display_name": user.display_name,
        "avatar_url": user.github_avatar_url,
        "role": user.role.value,
    }


@auth_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out",
    dependencies=[Depends(require_csrf)],
)
def logout(
    response: Response,
    pair: Annotated[tuple, Depends(get_current_pair)],
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    session, user = pair
    auth_service.revoke_session(db, session)
    auth_service.record_logout(db, user)

    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    return response
