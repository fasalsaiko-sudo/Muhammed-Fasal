"""Per-request context: request id, timing and a redacted access log."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("portfolio.access")

# Header values that must never appear in logs.
REDACTED_HEADERS = {"authorization", "cookie", "x-csrf-token"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        # A caller-supplied id is only echoed when it looks like an id.
        if not (4 <= len(request_id) <= 40 and request_id.replace("-", "").isalnum()):
            request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "endpoint": request.url.path,
                    "status": 500,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        user = getattr(request.state, "user", None)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "endpoint": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "user": user.github_username if user is not None else None,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
