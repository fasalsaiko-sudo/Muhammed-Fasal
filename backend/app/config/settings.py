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

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

Environment = Literal["development", "testing", "staging", "production"]


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
    secure_errors: bool = True

    # --- GitHub OAuth ------------------------------------------------------
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/auth/github/callback"
    allowed_github_username: str = "Fasal17"
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
        if self.environment == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production.")
            if not self.github_client_secret or not self.github_client_id:
                raise ValueError("GitHub OAuth credentials are required in production.")
        object.__setattr__(self, "log_level", self.log_level.upper())
        return self

    # ---------------------------------------------------------------- helpers
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def allowed_github_usernames(self) -> set[str]:
        return {name.strip().lower() for name in _split_csv(self.allowed_github_username)}

    @property
    def cors_origins(self) -> list[str]:
        origins = _split_csv(self.cors_allowed_origins)
        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)
        if self.admin_url and self.admin_url not in origins:
            origins.append(self.admin_url)
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
