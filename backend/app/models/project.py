from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UTCDateTime, utcnow
from app.models.enums import ContentStatus, MediaType, Severity
from app.models.media import Media

JSONType = JSON().with_variant(JSONB(), "postgresql")

project_tags = Table(
    "project_tags",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)


class Project(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    short_description: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    # Case-study blocks used by the public project dialog.
    problem: Mapped[str | None] = mapped_column(Text)
    solution: Mapped[str | None] = mapped_column(Text)
    methodology: Mapped[str | None] = mapped_column(Text)

    technologies: Mapped[list[str] | None] = mapped_column(JSONType, default=list)

    # --- optional security metadata (null for non-security projects) -------
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    security_focus: Mapped[str | None] = mapped_column(String(128))
    vulnerability_type: Mapped[str | None] = mapped_column(String(128))
    severity: Mapped[Severity | None] = mapped_column(
        Enum(Severity, native_enum=False, length=16, name="severity", create_constraint=True)
    )
    cvss_score: Mapped[float | None] = mapped_column(Float)
    cwe: Mapped[str | None] = mapped_column(String(32))
    owasp_category: Mapped[str | None] = mapped_column(String(128))
    target_type: Mapped[str | None] = mapped_column(String(64))
    testing_methodology: Mapped[str | None] = mapped_column(Text)
    tools_used: Mapped[list[str] | None] = mapped_column(JSONType, default=list)
    findings_summary: Mapped[str | None] = mapped_column(Text)
    remediation_summary: Mapped[str | None] = mapped_column(Text)

    # --- links -------------------------------------------------------------
    github_url: Mapped[str | None] = mapped_column(String(512))
    demo_url: Mapped[str | None] = mapped_column(String(512))
    writeup_url: Mapped[str | None] = mapped_column(String(512))

    # --- display -----------------------------------------------------------
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, native_enum=False, length=16, name="content_status", create_constraint=True),
        default=ContentStatus.DRAFT,
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    tags: Mapped[list[Tag]] = relationship(secondary=project_tags, backref="projects")
    media: Mapped[list[ProjectMedia]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectMedia.sort_order",
        passive_deletes=True,
    )


class ProjectMedia(Base):
    __tablename__ = "project_media"
    __table_args__ = (UniqueConstraint("project_id", "media_id", name="project_media_unique"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, native_enum=False, length=16, name="media_type", create_constraint=True),
        default=MediaType.IMAGE,
        nullable=False,
    )
    caption: Mapped[str | None] = mapped_column(String(255))
    alt_text: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="media")
    media_item: Mapped[Media] = relationship()
