"""Phase 2 middleware.

Authentication and authorization middleware are added in Phase 5, once GitHub
OAuth exists to authenticate against.
"""

from app.middleware.cors import build_cors_middleware
from app.middleware.rate_limit import RateLimiter, get_limiter, rate_limit_dependency
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security import SecurityHeadersMiddleware

__all__ = [
    "RateLimiter",
    "RequestContextMiddleware",
    "SecurityHeadersMiddleware",
    "build_cors_middleware",
    "get_limiter",
    "rate_limit_dependency",
]
