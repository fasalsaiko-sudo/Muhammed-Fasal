"""Small shared helpers (time normalisation, pagination, reading time)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

WORDS_PER_MINUTE = 220


def as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to naive datetimes (SQLite returns naive values)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    normalized = as_utc(value)
    return normalized.isoformat() if normalized else None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Page:
    items: list[Any]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return max(1, math.ceil(self.total / self.page_size)) if self.page_size else 1

    def payload(self, serializer=lambda item: item) -> dict[str, Any]:
        return {
            "items": [serializer(item) for item in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "pages": self.pages,
        }


def paginate(page: int, page_size: int, max_page_size: int = 100) -> tuple[int, int]:
    safe_page = max(1, page)
    safe_size = min(max(1, page_size), max_page_size)
    return safe_page, safe_size


def offset_for(page: int, page_size: int) -> int:
    return (page - 1) * page_size


def reading_time_minutes(text: str) -> int:
    words = len((text or "").split())
    return max(1, math.ceil(words / WORDS_PER_MINUTE)) if words else 0


def human_size(size_bytes: int | None) -> str:
    if not size_bytes:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"
