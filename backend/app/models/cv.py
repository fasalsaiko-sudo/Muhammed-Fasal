from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, UTCDateTime, utcnow
from app.models.media import Media


class CVVersion(SoftDeleteMixin, Base):
    """A single CV revision. Exactly one row has ``is_current = True``."""

    __tablename__ = "cv_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)

    media_item: Mapped[Media] = relationship()

    def public_payload(self) -> dict[str, object]:
        """Exactly the shape documented for ``GET /api/cv``."""
        media = self.media_item
        return {
            "name": media.filename if media else self.version_name,
            "version": self.version_name,
            "updated_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "download_url": media.download_url if media else None,
            "view_url": media.drive_url if media else None,
            "size_bytes": media.size_bytes if media else None,
            "mime_type": media.mime_type if media else None,
        }
