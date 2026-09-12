from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime
from app.models.enums import UserRole


class User(TimestampMixin, Base):
    """An administrator authenticated through GitHub OAuth.

    GitHub is the identity provider; this table is the local authorization
    record. ``role`` plus ``is_active`` are what the API checks — never the
    GitHub username alone.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    github_username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    github_avatar_url: Mapped[str | None] = mapped_column(String(512))
    display_name: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(254))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=16, name="user_role", create_constraint=True),
        default=UserRole.ADMIN,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    sessions: Mapped[list[AdminSession]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="user")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.github_username} role={self.role}>"
