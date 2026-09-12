"""Declarative base, shared mixins and naming conventions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

# An explicit naming convention keeps Alembic autogenerate stable: without it
# constraint names are derived per-dialect and migrations drift.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Timezone-aware UTC now — the single time source for the whole app."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC column that behaves identically on every backend.

    PostgreSQL stores ``TIMESTAMP WITH TIME ZONE`` natively; SQLite stores a
    naive string. This decorator normalises both directions so comparisons such
    as ``session.is_expired`` never mix naive and aware values.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    """Cooperative deletion.

    Content rows are never hard-deleted by the admin API; ``deleted_at`` marks
    them as removed so they can be recovered and so Google Drive deletion can be
    reconciled deliberately.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
