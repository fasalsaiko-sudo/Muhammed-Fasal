"""In-memory fixed-window rate limiting.

Deliberately dependency-free and deterministic so it can be unit tested. For a
multi-instance deployment, swap :class:`RateLimiter`'s store for Redis — the
call sites do not change.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.config.settings import get_settings


@dataclass
class Decision:
    allowed: bool
    remaining: int
    retry_after: int


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def hit(self, *, scope: str, key: str, limit: int, window_seconds: int = 60) -> Decision:
        now = time.monotonic()
        bucket_key = f"{scope}:{key}"
        with self._lock:
            window = [t for t in self._buckets[bucket_key] if now - t < window_seconds]
            if len(window) >= limit:
                retry_after = int(window_seconds - (now - window[0])) + 1
                self._buckets[bucket_key] = window
                return Decision(allowed=False, remaining=0, retry_after=max(1, retry_after))
            window.append(now)
            self._buckets[bucket_key] = window
            return Decision(allowed=True, remaining=limit - len(window), retry_after=0)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    return _limiter


def client_key(request: Request) -> str:
    """Rate-limit key: forwarded IP when trusted, otherwise the peer address."""
    settings = request.app.state.settings
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit_dependency(scope: str, limit_attr: str):
    """Build a dependency that rate-limits a route by IP."""

    def dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        limit = int(getattr(settings, limit_attr))
        decision = _limiter.hit(scope=scope, key=client_key(request), limit=limit)
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(decision.retry_after)},
            )

    return dependency
