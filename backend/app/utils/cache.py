"""Small in-process TTL cache for public endpoints.

Public portfolio data changes only when the administrator publishes something,
so responses are cached for ``PUBLIC_CACHE_TTL_SECONDS`` and explicitly
invalidated by the mutation paths. For multi-instance deployments swap the store
for Redis — only this module changes.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class TTLCache:
    def __init__(self, default_ttl: int = 60) -> None:
        self._default_ttl = max(0, default_ttl)
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        effective_ttl = self._default_ttl if ttl is None else ttl
        if effective_ttl <= 0:
            return
        with self._lock:
            self._store[key] = (time.monotonic() + effective_ttl, value)

    def invalidate(self, *prefixes: str) -> int:
        """Drop every key starting with any of the given namespaces."""
        if not prefixes:
            with self._lock:
                removed = len(self._store)
                self._store.clear()
                return removed
        with self._lock:
            doomed = [key for key in self._store if key.startswith(prefixes)]
            for key in doomed:
                self._store.pop(key, None)
            return len(doomed)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


class CacheNamespace:
    PROFILE = "profile"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"
    EXPERIENCE = "experience"
    SKILLS = "skills"
    WRITEUPS = "writeups"
    CV = "cv"
    SETTINGS = "settings"
    SNAPSHOT = "snapshot"


_cache: TTLCache | None = None


def get_cache(default_ttl: int = 60) -> TTLCache:
    global _cache
    if _cache is None:
        _cache = TTLCache(default_ttl)
    return _cache


def reset_cache() -> None:
    global _cache
    _cache = None
