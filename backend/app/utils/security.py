"""Cryptographic and encoding primitives.

Everything security-sensitive that is not HTTP-level lives here so it has one
implementation and one place to review.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from typing import Any

# Keys whose values must never reach logs, audit metadata or API responses.
SENSITIVE_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "session",
    "session_token",
    "session_token_hash",
    "cookie",
    "authorization",
    "password",
    "secret",
    "client_secret",
    "github_client_secret",
    "session_secret",
    "private_key",
    "google_private_key",
    "credentials",
    "database_url",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_HTML_TAG_RE = re.compile(r"<[^>]*>")
_DANGEROUS_URL_RE = re.compile(r"^\s*(javascript|data|vbscript|file)\s*:", re.IGNORECASE)


def generate_token(nbytes: int = 32) -> str:
    """URL-safe opaque token with ``2 * nbytes`` of entropy in base64 chars."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """SHA-256 hex digest — the only form of a session token that is stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sign_state(payload: str, secret: str) -> str:
    """HMAC-signed OAuth ``state`` value (prevents CSRF on the callback)."""
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{digest[:32]}"


def verify_state(signed: str, secret: str) -> str | None:
    """Return the payload when the signature is valid, otherwise ``None``."""
    if not signed or "." not in signed:
        return None
    payload, _, signature = signed.rpartition(".")
    expected = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]
    if not hmac.compare_digest(signature, expected):
        return None
    return payload


def slugify(value: str, max_length: int = 200) -> str:
    """Deterministic, URL-safe slug.

    Unicode is transliterated rather than dropped so non-ASCII titles still get
    a readable slug instead of an empty string.
    """
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_RE.sub("-", ascii_text).strip("-")
    return slug[:max_length].rstrip("-") or "item"


def sanitize_filename(filename: str, max_length: int = 120) -> str:
    """Strip path separators, traversal sequences and control characters.

    The result is never trusted as a filesystem path — Drive identifiers are —
    but it is used as the object name and must not contain separators.
    """
    base = (filename or "").replace("\\", "/").split("/")[-1]
    base = base.replace("\x00", "").strip()
    base = _FILENAME_RE.sub("-", base).strip("-._")
    base = base.lstrip(".")  # rejects ".htaccess", "..", "." and hidden files
    if not base:
        base = "file"
    if len(base) > max_length:
        stem, dot, extension = base.rpartition(".")
        if dot and len(extension) <= 12:
            base = f"{stem[: max_length - len(extension) - 1]}.{extension}"
        else:
            base = base[:max_length]
    return base


def redact_secrets(payload: Any) -> Any:
    """Recursively replace sensitive values before logging or auditing."""
    if isinstance(payload, dict):
        return {
            key: "***redacted***" if key.lower() in SENSITIVE_KEYS else redact_secrets(value)
            for key, value in payload.items()
        }
    if isinstance(payload, (list, tuple)):
        return [redact_secrets(item) for item in payload]
    if isinstance(payload, str) and len(payload) > 64 and payload.startswith(("-----BEGIN", "ghp_", "gho_")):
        return "***redacted***"
    return payload


def mask(value: str | None, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return f"{'*' * (len(value) - visible)}{value[-visible:]}"


def strip_html(value: str) -> str:
    """Remove all markup — used for plaintext summaries and search text."""
    return _HTML_TAG_RE.sub("", value or "")


def contains_dangerous_url(value: str) -> bool:
    return bool(_DANGEROUS_URL_RE.search(value or ""))


def safe_relative_path(*parts: str) -> str:
    """Join untrusted path parts, rejecting traversal and absolute paths."""
    cleaned: list[str] = []
    for part in parts:
        segment = (part or "").replace("\\", "/").strip("/")
        if not segment or segment in {".", ".."} or ".." in segment.split("/"):
            raise ValueError(f"Unsafe path segment: {part!r}")
        cleaned.extend(segment.split("/"))
    if not cleaned:
        raise ValueError("Empty path")
    return "/".join(cleaned)
