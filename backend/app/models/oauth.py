"""Server-side OAuth state records.

The ``state`` parameter is the CSRF defence for the OAuth callback. A signed
stateless value plus a cookie proves *binding*, but it cannot prove
*single use* — the same signed value can be replayed until it expires.

So the nonce is persisted here, hashed, with an expiry and a ``used_at`` column.
The callback consumes the row with a conditional UPDATE before it exchanges the
GitHub code, which makes replay impossible even under concurrency.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class OAuthState(Base):
    """One pending (or consumed) OAuth authorization attempt."""

    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # SHA-256 hex of the random value handed to GitHub. The raw value is never
    # stored, so a database read cannot be replayed into a login.
    state_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    # NULL while unused. Set by the atomic consume in the callback.
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    @property
    def is_expired(self) -> bool:
        return utcnow() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OAuthState id={self.id} used={self.is_used} expired={self.is_expired}>"
