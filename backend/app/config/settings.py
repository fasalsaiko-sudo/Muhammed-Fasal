"""Central application configuration.

Every environment-specific value lives here. Nothing in the codebase reads
``os.environ`` directly — that keeps secrets auditable in one place and makes the
application testable by overriding a single dependency.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

Environment = Literal["development", "testing", "staging", "production"]


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _scheme_and_netloc(url: str) -> tuple[str, str]:
    parsed = urlparse(url or "")
    return parsed.scheme.lower(), parsed.netloc


# Value shipped in .env.example; booting production with it still in place means
# the database credentials were never actually configured.
_PLACEHOLDER_DB_PASSWORDS = {"change-me", "changeme", "password", ""}


def _validate_urls(settings: Settings) -> None:
    """Reject OAuth/API URLs that cannot work, in every environment.

    A malformed callback URL otherwise surfaces much later as an opaque
    ``redirect_uri_mismatch`` page on github.com.
    """
    for name in ("api_base_url", "github_redirect_uri", "frontend_url", "admin_url"):
        value = getattr(settings, name)
        if not value:
            continue
        scheme, netloc = _scheme_and_netloc(value)
        if scheme not in {"http", "https"} or not netloc:
            raise ValueError(
                f"{name.upper()} must be an absolute http(s) URL with a host, got {value!r}."
            )
    for entry in _split_csv(settings.cors_allowed_origins):
        if entry == "*":
            # Refused here rather than in the middleware: credentials are always
            # allowed, and a wildcard with credentials is never acceptable.
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must not contain '*'. The API allows credentialed "
                "requests, so every origin has to be listed explicitly."
            )
        scheme, netloc = _scheme_and_netloc(entry)
        if scheme not in {"http", "https"} or not netloc:
            raise ValueError(
                f"CORS_ALLOWED_ORIGINS entries must be absolute http(s) origins, got {entry!r}. "
                "An origin has a scheme and host only - no path and no trailing slash."
            )


def _validate_session_windows(settings: Settings) -> None:
    """Idle longer than absolute would make the absolute deadline meaningless."""
    if settings.session_ttl_minutes <= 0 or settings.session_idle_ttl_minutes <= 0:
        raise ValueError("SESSION_TTL_MINUTES and SESSION_IDLE_TTL_MINUTES must be positive.")
    if settings.session_idle_ttl_minutes > settings.session_ttl_minutes:
        raise ValueError(
            "SESSION_IDLE_TTL_MINUTES must not exceed SESSION_TTL_MINUTES; "
            "the absolute deadline is the outer bound and is never extended."
        )
    if settings.oauth_state_ttl_seconds <= 0:
        raise ValueError("OAUTH_STATE_TTL_SECONDS must be positive.")


def _validate_production(settings: Settings) -> None:
    """Every check that must hold before this app faces the internet.

    Applies to ``staging`` as well as ``production``: staging rehearses the real
    deployment, so hardening it less would hide exactly the misconfigurations it
    exists to catch. Each failure names the variable to fix at startup, rather
    than degrading silently into a deployment that cannot authenticate anyone.
    """
    env = settings.environment

    if not settings.allowed_github_usernames:
        raise ValueError(
            f"ALLOWED_GITHUB_USERNAME is required when ENVIRONMENT={env}; there is no "
            "default administrator. Comma-separate more than one GitHub login."
        )
    for name in ("api_base_url", "github_redirect_uri"):
        value = getattr(settings, name)
        if _scheme_and_netloc(value)[0] != "https":
            raise ValueError(
                f"{name.upper()} must use https when ENVIRONMENT={env}, got {value!r}."
            )
    api_base = settings.api_base_url.rstrip("/")
    if api_base and not settings.github_redirect_uri.startswith(f"{api_base}/"):
        raise ValueError(
            "GITHUB_REDIRECT_URI must be served by this API: it has to start with "
            f"API_BASE_URL ({api_base!r}), got {settings.github_redirect_uri!r}. "
            "A mismatch is the usual cause of GitHub's redirect_uri_mismatch error."
        )
    origins = settings.cors_origins
    if not origins:
        raise ValueError(
            f"CORS_ALLOWED_ORIGINS is required when ENVIRONMENT={env}; with no origin "
            "the browser admin cannot call the API at all."
        )
    for origin in origins:
        if _scheme_and_netloc(origin)[0] != "https":
            raise ValueError(
                f"CORS_ALLOWED_ORIGINS must be https when ENVIRONMENT={env}, got {origin!r}."
            )
    if not settings.cookie_secure:
        raise ValueError(f"COOKIE_SECURE must be true when ENVIRONMENT={env}.")
    if not settings.secure_errors:
        raise ValueError(
            f"SECURE_ERRORS must be true when ENVIRONMENT={env}; stack traces must not leak."
        )
    if not settings.rate_limit_enabled:
        raise ValueError(f"RATE_LIMIT_ENABLED must be true when ENVIRONMENT={env}.")
    password = _db_password(settings.database_url)
    if password in _PLACEHOLDER_DB_PASSWORDS:
        raise ValueError(
            f"DATABASE_URL still has a placeholder password when ENVIRONMENT={env}; "
            "set a real credential."
        )


def _db_password(database_url: str) -> str | None:
    """Extract the password without ever putting the URL in an error message."""
    try:
        return make_url(database_url).password
    except Exception:  # noqa: BLE001 - an unparseable URL is a different failure
        return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- runtime -----------------------------------------------------------
    environment: Environment = "development"
    log_level: str = "INFO"
    api_base_url: str = "http://localhost:8000"

    # --- database ----------------------------------------------------------
    database_url: str = "postgresql+psycopg://portfolio_cms:change-me@localhost:5432/portfolio_cms"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    # "auto" keeps the historical behaviour: NullPool while testing (a fresh
    # connection per session, so no test inherits another's dirty transaction),
    # QueuePool otherwise.
    #
    # "static" reuses one connection for the whole process. The PGlite test
    # harness needs this: it serves a single connection at a time and closes
    # connections that arrive during rapid reconnect churn (measured: 17 failures
    # in 150 sequential connect/close cycles). SQLAlchemy rolls a connection
    # back when it returns to the pool, so isolation is preserved.
    #
    # "queue" forces the pooled production configuration even while testing.
    database_pool_class: Literal["auto", "static", "queue"] = "auto"
    secure_errors: bool = True

    # --- GitHub OAuth ------------------------------------------------------
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/auth/github/callback"
    # Deliberately empty: there is no hardcoded administrator. The allowlist must
    # come from the environment, and production refuses to boot without it —
    # otherwise a stale default account would silently retain admin access.
    allowed_github_username: str = ""
    github_api_url: str = "https://api.github.com"
    github_authorize_url: str = "https://github.com/login/oauth/authorize"
    github_token_url: str = "https://github.com/login/oauth/access_token"

    # --- session -----------------------------------------------------------
    session_secret: str = ""
    session_cookie_name: str = "mf_cms_session"
    csrf_cookie_name: str = "mf_cms_csrf"
    session_ttl_minutes: int = 480
    session_idle_ttl_minutes: int = 120
    cookie_secure: bool = False
    # "lax" when the admin and API share a site (current dev: localhost:8000).
    # A cross-site admin (e.g. Pages origin talking to a different API host)
    # needs "none", which browsers accept only together with Secure.
    session_cookie_samesite: str = "lax"
    csrf_header_name: str = "X-CSRF-Token"
    max_sessions_per_user: int = 5

    # --- oauth state -------------------------------------------------------
    oauth_state_ttl_seconds: int = 600

    # --- frontend ----------------------------------------------------------
    frontend_url: str = "http://localhost:8080"
    admin_url: str = "http://localhost:8000/admin"
    cors_allowed_origins: str = "http://localhost:8080,http://localhost:5173"

    # --- Google Drive ------------------------------------------------------
    google_drive_root_folder_id: str = ""
    google_service_account_email: str = ""
    google_private_key: str = ""
    google_application_credentials: str = ""
    google_drive_folder_template: str = "Portfolio CMS"
    drive_public_read: bool = True

    # --- upload limits -----------------------------------------------------
    max_upload_image_bytes: int = 10 * 1024 * 1024
    max_upload_pdf_bytes: int = 20 * 1024 * 1024
    max_upload_video_bytes: int = 500 * 1024 * 1024
    max_upload_document_bytes: int = 20 * 1024 * 1024

    # --- rate limiting -----------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = 10
    rate_limit_upload_per_minute: int = 30
    rate_limit_public_per_minute: int = 120

    # --- caching / snapshot ------------------------------------------------
    public_cache_ttl_seconds: int = 60
    public_snapshot_path: str = "data/portfolio.json"
    enable_snapshot_write: bool = False

    # --- proxies -----------------------------------------------------------
    # Only enable behind a trusted reverse proxy (Render/Fly/nginx/Cloudflare).
    trust_proxy_headers: bool = False

    # --- docs --------------------------------------------------------------
    docs_enabled: bool = True
    # Interactive API docs are a development aid. In production they publish the
    # entire admin surface to anonymous callers, so they stay off unless this is
    # explicitly enabled. `docs_enabled` alone is never enough in production.
    docs_enabled_in_production: bool = False

    # ---------------------------------------------------------------- derived
    @field_validator("google_private_key")
    @classmethod
    def _decode_private_key(cls, value: str) -> str:
        """Allow the PEM key to be supplied with escaped newlines."""
        if not value:
            return value
        return value.replace("\\n", "\n").strip()

    @model_validator(mode="after")
    def _apply_runtime_rules(self) -> Settings:
        if not self.session_secret:
            if self.environment == "production":
                raise ValueError(
                    "SESSION_SECRET is required in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
                )
            # Local convenience only: an ephemeral secret means existing sessions
            # do not survive a restart, which is the correct dev behaviour.
            object.__setattr__(self, "session_secret", secrets.token_urlsafe(64))
        if len(self.session_secret) < 32:
            raise ValueError("SESSION_SECRET must be at least 32 characters long.")
        samesite = self.session_cookie_samesite.strip().lower()
        if samesite not in {"lax", "strict", "none"}:
            raise ValueError("SESSION_COOKIE_SAMESITE must be one of: lax, strict, none.")
        object.__setattr__(self, "session_cookie_samesite", samesite)
        if samesite == "none" and not self.cookie_secure:
            # Browsers reject SameSite=None without Secure, which would silently
            # log every administrator out. Fail at startup instead.
            raise ValueError(
                "SESSION_COOKIE_SAMESITE=none requires COOKIE_SECURE=true; "
                "browsers discard SameSite=None cookies that are not Secure."
            )
        if self.environment == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production.")
            if not self.github_client_secret or not self.github_client_id:
                raise ValueError("GitHub OAuth credentials are required in production.")
        _validate_urls(self)
        _validate_session_windows(self)
        if self.is_production_like:
            _validate_production(self)
        object.__setattr__(self, "log_level", self.log_level.upper())
        return self

    # ---------------------------------------------------------------- helpers
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_production_like(self) -> bool:
        """Environments that are internet-facing and must behave like production.

        Staging exists to rehearse a production deployment, so hardening it less
        than production defeats the purpose: the checks that matter (secure
        cookies, https, an explicit administrator allowlist, no stack traces,
        rate limiting) must already be in force there.
        """
        return self.environment in {"staging", "production"}

    @property
    def serve_api_docs(self) -> bool:
        """Whether /docs, /redoc and /openapi.json are exposed.

        ``docs_enabled`` is the master switch; production additionally requires
        its own opt-in, because ``docs_enabled`` defaults to true for development
        convenience and treating that as consent would publish the whole admin
        API surface to anonymous callers.
        """
        return self.docs_enabled and (
            self.docs_enabled_in_production or not self.is_production_like
        )

    @property
    def allowed_github_usernames(self) -> set[str]:
        return {name.strip().lower() for name in _split_csv(self.allowed_github_username)}

    @property
    def cors_origins(self) -> list[str]:
        """Explicit origin allowlist, normalised to ``scheme://host[:port]``.

        A browser's ``Origin`` header never carries a path, so an entry such as
        ``https://example.github.io/Repo/`` could never match. Reducing every
        entry to its origin makes FRONTEND_URL/ADMIN_URL work as written instead
        of silently allowing nothing.
        """
        candidates = [
            *_split_csv(self.cors_allowed_origins),
            self.frontend_url,
            self.admin_url,
        ]
        origins: list[str] = []
        for candidate in candidates:
            if not candidate:
                continue
            if candidate == "*":
                # _validate_urls already refuses this; kept verbatim so a
                # programmatically built Settings still trips the middleware
                # guard instead of being silently normalised away.
                origins.append(candidate)
                continue
            scheme, netloc = _scheme_and_netloc(candidate)
            if not scheme or not netloc:
                continue
            origin = f"{scheme}://{netloc}"
            if origin not in origins:
                origins.append(origin)
        return origins

    @property
    def github_oauth_configured(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret and self.github_redirect_uri)

    @property
    def google_drive_configured(self) -> bool:
        return bool(
            self.google_drive_root_folder_id
            and (
                (self.google_service_account_email and self.google_private_key)
                or self.google_application_credentials
            )
        )

    @property
    def snapshot_path(self) -> Path:
        path = Path(self.public_snapshot_path)
        return path if path.is_absolute() else (REPO_ROOT / path)

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_ttl_minutes * 60

    @property
    def session_idle_ttl_seconds(self) -> int:
        return self.session_idle_ttl_minutes * 60


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    """Drop the cached settings instance (used by the test-suite)."""
    get_settings.cache_clear()
