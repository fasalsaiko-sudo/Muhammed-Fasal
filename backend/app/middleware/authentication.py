"""Authentication context middleware.

This middleware **never rejects a request**. It resolves the session cookie when
one is present and exposes the result on ``request.state`` so routes, logging and
audit can see who is calling. Enforcement is done by the dependencies in
``app/routes/dependencies.py`` — that separation is what keeps the public API
reachable anonymously while admin routes stay protected.

A database failure here degrades to "anonymous"; it must not take the site down.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config.database import get_session_factory
from app.config.settings import Settings
from app.services import auth_service

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.user = None
        request.state.session = None

        raw_token = request.cookies.get(self.settings.session_cookie_name)
        if raw_token:
            session_factory = get_session_factory()
            db = session_factory()
            try:
                pair = auth_service.resolve_session(db, raw_token)
                if pair is not None:
                    session, user = pair
                    request.state.session = session
                    request.state.user = user
                    # Idle window only; the absolute deadline is never extended.
                    auth_service.touch_session(db, session)
            except Exception:  # noqa: BLE001 - auth context must not break the request
                logger.warning("auth_context_unavailable path=%s", request.url.path)
            finally:
                db.close()

        return await call_next(request)
