from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UTCDateTime, utcnow
from app.models.enums import ContentStatus, Severity
from app.models.media import Media
from app.models.project import Tag, project_tags  # noqa: F401  (shared Tag model)

writeup_tags = Table(
    "writeup_tags",
    Base.metadata,
    Column("writeup_id", ForeignKey("writeups.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Writeup(SoftDeleteMixin, TimestampMixin, Base):
    """Security write-up. Content is plain text / Markdown — never raw HTML."""

    __tablename__ = "writeups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), unique=True, nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    severity: Mapped[Severity | None] = mapped_column(
        Enum(Severity, native_enum=False, length=16, name="severity", create_constraint=True)
    )
    cvss_score: Mapped[float | None] = mapped_column(Float)
    cwe: Mapped[str | None] = mapped_column(String(32))
    owasp_category: Mapped[str | None] = mapped_column(String(128))
    target_summary: Mapped[str | None] = mapped_column(String(180))
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, native_enum=False, length=16, name="content_status", create_constraint=True),
        default=ContentStatus.DRAFT,
        nullable=False,
        index=True,
    )
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reading_time_minutes: Mapped[int | None] = mapped_column(Integer)

    tags: Mapped[list[Tag]] = relationship(secondary=writeup_tags, backref="writeups")
    media: Mapped[list[WriteupMedia]] = relationship(
        back_populates="writeup",
        cascade="all, delete-orphan",
        order_by="WriteupMedia.sort_order",
        passive_deletes=True,
    )


class WriteupMedia(Base):
    __tablename__ = "writeup_media"
    __table_args__ = (UniqueConstraint("writeup_id", "media_id", name="writeup_media_unique"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    writeup_id: Mapped[int] = mapped_column(
        ForeignKey("writeups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True
    )
    caption: Mapped[str | None] = mapped_column(String(255))
    alt_text: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )

    writeup: Mapped[Writeup] = relationship(back_populates="media")
    media_item: Mapped[Media] = relationship()
