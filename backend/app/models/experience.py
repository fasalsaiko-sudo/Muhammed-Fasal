from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Boolean, Date, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Experience(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "experience"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(180), nullable=False)
    role: Mapped[str] = mapped_column(String(180), nullable=False)
    location: Mapped[str | None] = mapped_column(String(128))
    employment_type: Mapped[str | None] = mapped_column(String(64))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    highlights: Mapped[list[str] | None] = mapped_column(JSONType, default=list)
    technologies: Mapped[list[str] | None] = mapped_column(JSONType, default=list)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    @property
    def date_range(self) -> str:
        """Human label used by the public timeline, e.g. ``Feb 2026 — Present``."""
        start = self.start_date.strftime("%b %Y") if self.start_date else "—"
        if self.is_current or self.end_date is None:
            return f"{start} — Present"
        return f"{start} — {self.end_date.strftime('%b %Y')}"
