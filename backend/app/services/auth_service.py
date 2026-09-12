"""Authentication service: single-use OAuth state and session lifecycle.

Two invariants this module is responsible for:

1. **An OAuth state can be consumed exactly once.** Consumption is a conditional
   ``UPDATE ... WHERE used_at IS NULL`` committed *before* the GitHub code is
   exchanged, so two concurrent replays cannot both succeed.
2. **``expires_at`` is written once and never extended.** Activity refreshes
   ``last_seen_at`` only. A session is valid when it is unrevoked and inside
   *both* windows, i.e. ``min(absolute, idle)``.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models import AdminSession, OAuthState, User, UserRole, utcnow
from app.models.audit import AuditLog
from app.services.github_oauth import GitHubIdentity
from app.utils.security import generate_token, hash_token, sign_state

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- state
def issue_state(db: Session, settings: Settings, ip_address: str | None) -> str:
    """Persist a fresh single-use state and return the raw value for GitHub."""
    purge_expired_states(db)
    raw = generate_token(32)
    now = utcnow()
    db.add(
        OAuthState(
            state_hash=hash_token(raw),
            created_at=now,
            expires_at=now + timedelta(seconds=settings.oauth_state_ttl_seconds),
            ip_address=ip_address,
        )
    )
    db.commit()
    return raw


def purge_expired_states(db: Session) -> int:
    """Bounded housekeeping so the table cannot grow without a scheduler."""
    result = db.execute(delete(OAuthState).where(OAuthState.expires_at < utcnow()))
    db.commit()
    return result.rowcount or 0


def consume_state(db: Session, raw_state: str | None) -> bool:
    """Atomically mark a state used. True only for the single winning caller.

    Returns False when the state is absent, already used, or expired — the
    caller cannot distinguish those, which is deliberate.
    """
    if not raw_state:
        return False
    now = utcnow()
    result = db.execute(
        update(OAuthState)
        .where(
            OAuthState.state_hash == hash_token(raw_state),
            OAuthState.used_at.is_(None),
            OAuthState.expires_at > now,
        )
        .values(used_at=now)
    )
    db.commit()
    return (result.rowcount or 0) == 1


def get_state_row(db: Session, raw_state: str | None) -> OAuthState | None:
    if not raw_state:
        return None
    return db.scalar(select(OAuthState).where(OAuthState.state_hash == hash_token(raw_state)))


# ------------------------------------------------------------------- sessions
def csrf_token_for(session_token_hash: str, settings: Settings) -> str:
    """Derive the CSRF value from the session hash instead of storing it.

    HMAC(session_secret, session_token_hash) is bound to that exact session,
    needs no extra column, and cannot be forged without the secret. The cookie
    is readable by the admin's JavaScript (not HttpOnly) so it can be echoed in
    a header; an attacker on another origin cannot read it.
    """
    return sign_state(session_token_hash, settings.session_secret)


def csrf_is_valid(provided: str | None, session_token_hash: str, settings: Settings) -> bool:
    from app.utils.security import constant_time_equals

    if not provided:
        return False
    return constant_time_equals(provided, csrf_token_for(session_token_hash, settings))


def resolve_session(db: Session, raw_token: str | None) -> tuple[AdminSession, User] | None:
    """Return the session and user when the token is currently valid.

    Performs **no write** on a rejected token: a revoked or expired session can
    never be refreshed, un-revoked, or have its timestamps touched.
    """
    if not raw_token:
        return None
    row = db.scalar(
        select(AdminSession).where(AdminSession.session_token_hash == hash_token(raw_token))
    )
    if row is None or row.revoked:
        return None
    now = utcnow()
    if now >= row.expires_at:  # absolute deadline — never moved
        return None
    idle_deadline = row.last_seen_at + timedelta(seconds=_idle_seconds(db))
    if now >= idle_deadline:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return row, user


def _idle_seconds(db: Session) -> int:
    from app.config.settings import get_settings

    return get_settings().session_idle_ttl_seconds


def touch_session(db: Session, row: AdminSession) -> None:
    """Refresh the idle window only. ``expires_at`` is deliberately untouched."""
    row.last_seen_at = utcnow()
    db.add(row)
    db.commit()


def create_session(
    db: Session,
    settings: Settings,
    user: User,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    """Create a session and return ``(raw_session_token, csrf_token)``.

    Only the SHA-256 hash of the session token is stored.
    """
    now = utcnow()
    raw_token = generate_token(32)
    db.add(
        AdminSession(
            user_id=user.id,
            session_token_hash=hash_token(raw_token),
            created_at=now,
            expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
            last_seen_at=now,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:512] or None,
        )
    )
    db.commit()
    enforce_session_cap(db, settings, user.id)
    stored_hash = hash_token(raw_token)
    return raw_token, csrf_token_for(stored_hash, settings)


def enforce_session_cap(db: Session, settings: Settings, user_id: int) -> None:
    """Revoke the oldest sessions beyond ``MAX_SESSIONS_PER_USER``."""
    cap = settings.max_sessions_per_user
    if cap <= 0:
        return
    active = list(
        db.scalars(
            select(AdminSession)
            .where(
                AdminSession.user_id == user_id,
                AdminSession.revoked.is_(False),
                AdminSession.expires_at > utcnow(),
            )
            .order_by(AdminSession.created_at.desc(), AdminSession.id.desc())
        )
    )
    for stale in active[cap:]:
        stale.revoked = True
        db.add(stale)
    if len(active) > cap:
        db.commit()
        logger.info("sessions_capped user_id=%s revoked=%s", user_id, len(active) - cap)


def revoke_session(db: Session, row: AdminSession) -> None:
    row.revoked = True
    db.add(row)
    db.commit()


# --------------------------------------------------------------------- users
def upsert_user(db: Session, identity: GitHubIdentity) -> User:
    """Match on the immutable ``github_id``; refresh the mutable profile fields."""
    user = db.scalar(select(User).where(User.github_id == identity.github_id))
    now = utcnow()
    if user is None:
        user = User(
            github_id=identity.github_id,
            github_username=identity.username,
            github_avatar_url=identity.avatar_url,
            display_name=identity.display_name,
            email=identity.email,
            role=UserRole.ADMIN,
            last_login_at=now,
        )
        db.add(user)
    else:
        user.github_username = identity.username
        user.github_avatar_url = identity.avatar_url
        user.display_name = identity.display_name
        user.email = identity.email
        user.last_login_at = now
        db.add(user)
    db.commit()
    return user


def hash_username(username: str) -> str:
    """Log-safe identifier: proves two denials are the same account without
    writing the username to the logs."""
    return hash_token(username.lower())[:16]


def record_login(db: Session, user: User | None, *, success: bool, reason: str | None = None) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action="LOGIN",
            resource_type="admin_session",
            description=None if success else reason,
            status="SUCCESS" if success else "FAILURE",
        )
    )
    db.commit()


def record_logout(db: Session, user: User) -> None:
    db.add(
        AuditLog(
            user_id=user.id,
            action="LOGOUT",
            resource_type="admin_session",
            status="SUCCESS",
        )
    )
    db.commit()
