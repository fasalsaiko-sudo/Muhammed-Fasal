"""Security response headers.

CSP is intentionally strict for the API origin: the API returns JSON and the
OAuth redirect only, so there is nothing legitimate to execute here. The public
GitHub Pages origin keeps its own policy.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config.settings import Settings

# Content-Security-Policy for API responses (no inline scripts, no framing).
API_CSP = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'none'; sandbox"
)
# The interactive Swagger UI needs its own inline resources.
DOCS_CSP = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        path = request.url.path
        is_docs = path.startswith(("/docs", "/redoc"))
        response.headers.setdefault(
            "Content-Security-Policy", DOCS_CSP if is_docs else API_CSP
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(), interest-cohort=()"
        )
        response.headers.setdefault("Cache-Control", "no-store")
        if self.settings.cookie_secure or self.settings.is_production_like:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # Never advertise the framework/version.
        if "Server" in response.headers:
            del response.headers["Server"]
        return response
