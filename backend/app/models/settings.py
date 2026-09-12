from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

JSONType = JSON().with_variant(JSONB(), "postgresql")


class SiteSettings(TimestampMixin, Base):
    """Single-row SEO / branding / feature-flag record (id is always 1)."""

    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    portfolio_title: Mapped[str] = mapped_column(
        String(180), default="Muhammed Fasal | Cybersecurity & VAPT Portfolio", nullable=False
    )
    seo_description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[str | None] = mapped_column(Text)
    og_title: Mapped[str | None] = mapped_column(String(180))
    og_description: Mapped[str | None] = mapped_column(Text)
    og_image_url: Mapped[str | None] = mapped_column(String(1024))
    canonical_url: Mapped[str | None] = mapped_column(String(512))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    availability_status: Mapped[str | None] = mapped_column(String(128))
    footer_text: Mapped[str | None] = mapped_column(String(255))
    theme: Mapped[str] = mapped_column(String(16), default="dark", nullable=False)
    # Feature toggles the public site reads, e.g. {"show_threat_map": true}.
    feature_flags: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    def public_payload(self) -> dict[str, object]:
        return {
            "portfolio_title": self.portfolio_title,
            "seo_description": self.seo_description,
            "keywords": self.keywords,
            "og_title": self.og_title,
            "og_description": self.og_description,
            "og_image_url": self.og_image_url,
            "canonical_url": self.canonical_url,
            "contact_email": self.contact_email,
            "availability_status": self.availability_status,
            "footer_text": self.footer_text,
            "theme": self.theme,
            "feature_flags": self.feature_flags or {},
        }


def default_feature_flags() -> dict[str, bool]:
    """Toggles for optional public-site modules (application features stay in code)."""
    return {
        "show_writeups": True,
        "show_certifications": True,
        "show_experience": True,
        "show_resume_section": True,
    }
