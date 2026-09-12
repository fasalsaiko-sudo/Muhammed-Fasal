from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.media import Media


class Profile(TimestampMixin, Base):
    """Single-row public identity record (id is always 1)."""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(255))
    short_bio: Mapped[str | None] = mapped_column(Text)
    long_bio: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(128))
    availability_status: Mapped[str | None] = mapped_column(String(128))
    profile_image_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(48))

    profile_image: Mapped[Media | None] = relationship(foreign_keys=[profile_image_media_id])
    social_links: Mapped[list[SocialLink]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="SocialLink.sort_order",
    )


class SocialLink(Base):
    """Public professional links (GitHub, LinkedIn, Bugcrowd, ...)."""

    __tablename__ = "social_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), nullable=False, default=1
    )
    platform: Mapped[str] = mapped_column(String(48), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(48))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped[Profile] = relationship(back_populates="social_links")
