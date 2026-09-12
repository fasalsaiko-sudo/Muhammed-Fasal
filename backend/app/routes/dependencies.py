"""Route dependencies: authentication, authorization and CSRF enforcement.

Split of responsibility, deliberately:

* ``app/middleware/authentication.py`` only *populates* ``request.state`` — it
  never rejects, so unauthenticated requests still reach the public API.
* Enforcement lives here, as dependencies, so a route opts in explicitly and the
  401/403 distinction is testable per route.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.settings import Settings, get_settings
from app.models import AdminSession, User, UserRole
from app.services import auth_service

UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required.",
    headers={"WWW-Authenticate": "Cookie"},
)
# One message for every authorization failure: "not on the allowlist" and
# "account disabled" must be indistinguishable from the outside.
FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="This account is not authorized to access the CMS."
)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _session_token(request: Request, settings: Settings) -> str | None:
    return request.cookies.get(settings.session_cookie_name)


def get_current_pair(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> tuple[AdminSession, User]:
    """Resolve the caller's session, or raise 401. Never writes on failure."""
    settings = get_settings()
    pair = auth_service.resolve_session(db, _session_token(request, settings))
    if pair is None:
        raise UNAUTHENTICATED
    return pair


def get_current_user(pair: Annotated[tuple[AdminSession, User], Depends(get_current_pair)]) -> User:
    return pair[1]


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Authorization gate: authenticated *and* an active administrator."""
    if user.role is not UserRole.ADMIN or not user.is_active:
        raise FORBIDDEN
    return user


def require_csrf(
    request: Request, pair: Annotated[tuple[AdminSession, User], Depends(get_current_pair)]
) -> None:
    """Double-submit CSRF check for unsafe methods.

    The expected value is derived from the session hash, so it is bound to this
    session and cannot be forged without ``SESSION_SECRET``.
    """
    if request.method in SAFE_METHODS:
        return
    settings = get_settings()
    provided = request.headers.get(settings.csrf_header_name)
    session, _ = pair
    if not auth_service.csrf_is_valid(provided, session.session_token_hash, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed.",
        )


CurrentUser = Annotated[User, Depends(require_admin)]
