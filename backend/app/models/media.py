from __future__ import annotations

from sqlalchemy import BigInteger, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UTCDateTime, utcnow
from app.models.enums import AccessPolicy, MediaCategory, MediaType


class Media(SoftDeleteMixin, TimestampMixin, Base):
    """Metadata for a file that physically lives in Google Drive.

    ``drive_file_id`` is the stable identifier — never the filename.
    """

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    drive_file_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    drive_folder_id: Mapped[str | None] = mapped_column(String(128), index=True)
    category: Mapped[MediaCategory] = mapped_column(
        Enum(MediaCategory, native_enum=False, length=24, name="media_category", create_constraint=True),
        default=MediaCategory.OTHER,
        nullable=False,
        index=True,
    )
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, native_enum=False, length=16, name="media_type", create_constraint=True),
        default=MediaType.OTHER,
        nullable=False,
        index=True,
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    drive_url: Mapped[str | None] = mapped_column(String(1024))
    download_url: Mapped[str | None] = mapped_column(String(1024))
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024))
    access_policy: Mapped[AccessPolicy] = mapped_column(
        Enum(AccessPolicy, native_enum=False, length=16, name="access_policy", create_constraint=True),
        default=AccessPolicy.PUBLIC,
        nullable=False,
    )
    # Set when the Drive object could not be confirmed to exist.
    missing_in_drive: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_verified_at: Mapped[object | None] = mapped_column(UTCDateTime, default=utcnow)

    def public_payload(self) -> dict[str, object]:
        """Fields the public API may expose — deliberately small."""
        return {
            "id": self.id,
            "media_type": self.media_type.value,
            "mime_type": self.mime_type,
            "url": self.drive_url if self.access_policy is AccessPolicy.PUBLIC else None,
            "thumbnail_url": self.thumbnail_url if self.access_policy is AccessPolicy.PUBLIC else None,
            "download_url": self.download_url if self.access_policy is AccessPolicy.PUBLIC else None,
            "size_bytes": self.size_bytes,
        }
