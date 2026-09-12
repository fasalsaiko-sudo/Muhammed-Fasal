from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UTCDateTime, utcnow
from app.models.enums import CertificationStatus, ContentStatus
from app.models.media import Media


class Certification(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    issuer: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    credential_id: Mapped[str | None] = mapped_column(String(128))
    credential_url: Mapped[str | None] = mapped_column(String(512))
    issue_date: Mapped[date | None] = mapped_column(nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(nullable=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expiry_status: Mapped[CertificationStatus] = mapped_column(
        Enum(
            CertificationStatus,
            native_enum=False,
            length=16,
            name="certification_status",
        ),
        default=CertificationStatus.NO_EXPIRY,
        nullable=False,
    )
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, native_enum=False, length=16, name="content_status", create_constraint=True),
        default=ContentStatus.DRAFT,
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    media: Mapped[list[CertificationMedia]] = relationship(
        back_populates="certification",
        cascade="all, delete-orphan",
        order_by="CertificationMedia.sort_order",
        passive_deletes=True,
    )

    @property
    def primary_image(self) -> Media | None:
        for item in self.media:
            if item.media_item is not None:
                return item.media_item
        return None


class CertificationMedia(Base):
    __tablename__ = "certification_media"
    __table_args__ = (
        UniqueConstraint("certification_id", "media_id", name="certification_media_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    certification_id: Mapped[int] = mapped_column(
        ForeignKey("certifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True
    )
    caption: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )

    certification: Mapped[Certification] = relationship(back_populates="media")
    media_item: Mapped[Media] = relationship()
