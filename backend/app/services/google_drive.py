"""Google Drive storage backend.

Drive holds the bytes, PostgreSQL holds the metadata. The Google credentials
only ever exist here — no route, schema or client ever sees them.

Three backends share one interface:

``GoogleDriveStorage``  production, service-account authenticated
``InMemoryStorage``     local development and tests without Google credentials
``NullStorage``         misconfigured deployments; every call fails loudly and
                        the health endpoint reports DEGRADED
"""

from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.config.settings import Settings, get_settings
from app.utils.helpers import utcnow

logger = logging.getLogger(__name__)


class StorageUnavailable(RuntimeError):
    """Raised when the configured storage backend cannot serve a request."""


@dataclass(frozen=True)
class StoredObject:
    file_id: str
    filename: str
    mime_type: str
    size_bytes: int
    web_view_link: str | None = None
    web_content_link: str | None = None
    thumbnail_link: str | None = None


@dataclass(frozen=True)
class DriveEntry:
    file_id: str
    name: str
    mime_type: str
    size_bytes: int = 0
    is_folder: bool = False
    modified_time: str | None = None


@dataclass
class DriveHealth:
    connected: bool
    status: str  # CONNECTED | DEGRADED | UNCONFIGURED
    message: str
    root_folder_id: str | None = None
    backend: str = "none"
    checked_at: datetime = field(default_factory=utcnow)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "status": self.status,
            "message": self.message,
            "root_folder_id_masked": (
                f"{self.root_folder_id[:4]}…{self.root_folder_id[-4:]}"
                if self.root_folder_id and len(self.root_folder_id) > 12
                else None
            ),
            "backend": self.backend,
            "checked_at": self.checked_at.isoformat(),
            "diagnostics": self.diagnostics,
        }


FOLDER_MIME = "application/vnd.google-apps.folder"


class StorageBackend(Protocol):
    backend_name: str

    @property
    def available(self) -> bool: ...

    def ensure_folder(self, path: list[str]) -> str: ...

    def upload(self, *, folder_id: str, filename: str, data: bytes, mime_type: str) -> StoredObject: ...

    def get_file(self, file_id: str) -> DriveEntry | None: ...

    def delete(self, file_id: str) -> bool: ...

    def list_folder(self, folder_id: str) -> list[DriveEntry]: ...

    def health(self) -> DriveHealth: ...


def _escape_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def public_links(file_id: str) -> dict[str, str]:
    return {
        "web_view_link": f"https://drive.google.com/file/d/{file_id}/view",
        "web_content_link": f"https://drive.google.com/uc?export=download&id={file_id}",
        "thumbnail_link": (
            "https://drive.google.com/thumbnail?sz=w1000&id=" + file_id
        ),
    }


class GoogleDriveStorage:
    """Service-account authenticated Drive client."""

    backend_name = "google-drive"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._service = None
        self._lock = threading.Lock()
        self._folder_cache: dict[str, str] = {}

    # ------------------------------------------------------------ credentials
    def _build_service(self):
        # Imported lazily so the API can boot (and serve public endpoints) even
        # when the Google client libraries are not installed.
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/drive.file"]
        settings = self._settings
        if settings.google_application_credentials:
            credentials = service_account.Credentials.from_service_account_file(
                settings.google_application_credentials, scopes=scopes
            )
        else:
            info = {
                "type": "service_account",
                "client_email": settings.google_service_account_email,
                "project_id": "portfolio-cms",
                "private_key": settings.google_private_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        return build("drive", "v3", credentials=credentials, cache_discovery=False)

    @property
    def service(self):
        with self._lock:
            if self._service is None:
                self._service = self._build_service()
            return self._service

    @property
    def available(self) -> bool:
        return self._settings.google_drive_configured

    @property
    def root_folder_id(self) -> str:
        return self._settings.google_drive_root_folder_id

    # ------------------------------------------------------------------ folders
    def _find_child_folder(self, parent_id: str, name: str) -> str | None:
        query = (
            f"'{_escape_query_value(parent_id)}' in parents and "
            f"name = '{_escape_query_value(name)}' and "
            f"mimeType = '{FOLDER_MIME}' and trashed = false"
        )
        response = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(id,name)", pageSize=10, supportsAllDrives=True)
            .execute()
        )
        files = response.get("files") or []
        return files[0]["id"] if files else None

    def _create_folder(self, parent_id: str, name: str) -> str:
        body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
        created = (
            self.service.files()
            .create(body=body, fields="id", supportsAllDrives=True)
            .execute()
        )
        return created["id"]

    def ensure_folder(self, path: list[str]) -> str:
        """Resolve (creating when needed) ``Portfolio CMS/<a>/<b>`` and cache it."""
        if not self.available:
            raise StorageUnavailable("Google Drive is not configured on this server")
        clean = [segment for segment in path if segment]
        cache_key = "/".join(clean)
        with self._lock:
            if cache_key in self._folder_cache:
                return self._folder_cache[cache_key]
        parent = self.root_folder_id
        for segment in clean:
            existing = self._find_child_folder(parent, segment)
            parent = existing or self._create_folder(parent, segment)
        with self._lock:
            self._folder_cache[cache_key] = parent
        return parent

    # ------------------------------------------------------------------- files
    def upload(self, *, folder_id: str, filename: str, data: bytes, mime_type: str) -> StoredObject:
        from googleapiclient.http import MediaIoBaseUpload

        if not self.available:
            raise StorageUnavailable("Google Drive is not configured on this server")
        body = {"name": filename, "mimeType": mime_type, "parents": [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=False)
        created = (
            self.service.files()
            .create(body=body, media_body=media, fields="id,name,mimeType,size", supportsAllDrives=True)
            .execute()
        )
        file_id = created["id"]
        if self._settings.drive_public_read:
            try:
                self.service.permissions().create(
                    fileId=file_id, body={"type": "anyone", "role": "reader"}, supportsAllDrives=True
                ).execute()
            except Exception:  # noqa: BLE001 - sharing failure must not lose the upload
                # Logged, never silent: the file exists but is not publicly
                # readable, so the public site will show a broken thumbnail.
                logger.warning("drive_share_failed file_id=%s", file_id)
        links = public_links(file_id)
        return StoredObject(
            file_id=file_id,
            filename=created.get("name", filename),
            mime_type=created.get("mimeType", mime_type),
            size_bytes=int(created.get("size") or len(data)),
            **links,
        )

    def get_file(self, file_id: str) -> DriveEntry | None:
        try:
            found = (
                self.service.files()
                .get(fileId=file_id, fields="id,name,mimeType,size,modifiedTime", supportsAllDrives=True)
                .execute()
            )
        except Exception:  # noqa: BLE001 - treated as "not found / unreachable"
            return None
        if not found:
            return None
        return DriveEntry(
            file_id=found["id"],
            name=found.get("name", ""),
            mime_type=found.get("mimeType", "application/octet-stream"),
            size_bytes=int(found.get("size") or 0),
            is_folder=found.get("mimeType") == FOLDER_MIME,
            modified_time=found.get("modifiedTime"),
        )

    def delete(self, file_id: str) -> bool:
        try:
            self.service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            return True
        except Exception:  # noqa: BLE001
            return False

    def list_folder(self, folder_id: str) -> list[DriveEntry]:
        query = f"'{_escape_query_value(folder_id)}' in parents and trashed = false"
        entries: list[DriveEntry] = []
        page_token: str | None = None
        while True:
            response = (
                self.service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken,files(id,name,mimeType,size,modifiedTime)",
                    pageSize=200,
                    pageToken=page_token,
                    supportsAllDrives=True,
                )
                .execute()
            )
            for item in response.get("files") or []:
                entries.append(
                    DriveEntry(
                        file_id=item["id"],
                        name=item.get("name", ""),
                        mime_type=item.get("mimeType", "application/octet-stream"),
                        size_bytes=int(item.get("size") or 0),
                        is_folder=item.get("mimeType") == FOLDER_MIME,
                        modified_time=item.get("modifiedTime"),
                    )
                )
            page_token = response.get("nextPageToken")
            if not page_token:
                return entries

    def health(self) -> DriveHealth:
        if not self.available:
            missing = []
            if not self._settings.google_drive_root_folder_id:
                missing.append("GOOGLE_DRIVE_ROOT_FOLDER_ID")
            if not self._settings.google_service_account_email:
                missing.append("GOOGLE_SERVICE_ACCOUNT_EMAIL")
            if not self._settings.google_private_key and not self._settings.google_application_credentials:
                missing.append("GOOGLE_PRIVATE_KEY or GOOGLE_APPLICATION_CREDENTIALS")
            return DriveHealth(
                connected=False,
                status="UNCONFIGURED",
                message="Google Drive credentials are not configured; uploads are disabled.",
                root_folder_id=self._settings.google_drive_root_folder_id or None,
                backend=self.backend_name,
                diagnostics={"missing": missing},
            )
        try:
            entry = self.get_file(self.root_folder_id)
        except Exception as exc:  # noqa: BLE001
            return DriveHealth(
                connected=False,
                status="DEGRADED",
                message="Google Drive connection unavailable.",
                root_folder_id=self.root_folder_id,
                backend=self.backend_name,
                diagnostics={"error_category": type(exc).__name__},
            )
        if entry is None:
            return DriveHealth(
                connected=False,
                status="DEGRADED",
                message=(
                    "The Portfolio CMS root folder is not reachable. Share the Drive folder with the "
                    "service account email (Editor) — see docs/google-drive.md."
                ),
                root_folder_id=self.root_folder_id,
                backend=self.backend_name,
                diagnostics={"root_folder_reachable": False},
            )
        return DriveHealth(
            connected=True,
            status="CONNECTED",
            message="Portfolio CMS storage boundary is reachable.",
            root_folder_id=self.root_folder_id,
            backend=self.backend_name,
            diagnostics={"root_folder_reachable": True, "root_folder_name": entry.name},
        )


class InMemoryStorage:
    """Development backend: keeps bytes in RAM, mimics Drive semantics."""

    backend_name = "in-memory"

    def __init__(self, root_folder_id: str = "dev-root") -> None:
        self.root_folder_id = root_folder_id
        self.folders: dict[str, str] = {root_folder_id: ""}
        self.files: dict[str, StoredObject] = {}
        self.blobs: dict[str, bytes] = {}
        self.children: dict[str, list[str]] = {root_folder_id: []}

    @property
    def available(self) -> bool:
        return True

    def ensure_folder(self, path: list[str]) -> str:
        parent = self.root_folder_id
        for segment in [part for part in path if part]:
            found = next(
                (fid for fid in self.children.get(parent, []) if self.folders.get(fid) == segment),
                None,
            )
            if found is None:
                found = f"folder-{len(self.folders) + 1}"
                self.folders[found] = segment
                self.children.setdefault(parent, []).append(found)
                self.children.setdefault(found, [])
            parent = found
        return parent

    def upload(self, *, folder_id: str, filename: str, data: bytes, mime_type: str) -> StoredObject:
        file_id = f"drive-{len(self.files) + 1}"
        stored = StoredObject(
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
            **public_links(file_id),
        )
        self.files[file_id] = stored
        self.blobs[file_id] = data
        self.children.setdefault(folder_id, []).append(file_id)
        return stored

    def get_file(self, file_id: str) -> DriveEntry | None:
        stored = self.files.get(file_id)
        if stored is None:
            return None
        return DriveEntry(
            file_id=stored.file_id,
            name=stored.filename,
            mime_type=stored.mime_type,
            size_bytes=stored.size_bytes,
        )

    def delete(self, file_id: str) -> bool:
        if file_id not in self.files:
            return False
        self.files.pop(file_id)
        self.blobs.pop(file_id, None)
        return True

    def list_folder(self, folder_id: str) -> list[DriveEntry]:
        entries: list[DriveEntry] = []
        for child in self.children.get(folder_id, []):
            if child in self.folders:
                entries.append(
                    DriveEntry(file_id=child, name=self.folders[child], mime_type=FOLDER_MIME, is_folder=True)
                )
            elif child in self.files:
                stored = self.files[child]
                entries.append(
                    DriveEntry(
                        file_id=stored.file_id,
                        name=stored.filename,
                        mime_type=stored.mime_type,
                        size_bytes=stored.size_bytes,
                    )
                )
        return entries

    def health(self) -> DriveHealth:
        return DriveHealth(
            connected=True,
            status="CONNECTED",
            message="Local in-memory storage (development only). Configure a service account for production.",
            root_folder_id=self.root_folder_id,
            backend=self.backend_name,
            diagnostics={"development": True},
        )


class NullStorage:
    """Storage is not usable; the API keeps serving public content."""

    backend_name = "none"

    def __init__(self, reason: str = "Google Drive is not configured.") -> None:
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    def _fail(self) -> None:
        raise StorageUnavailable(self.reason)

    def ensure_folder(self, path: list[str]) -> str:
        self._fail()
        return ""

    def upload(self, *, folder_id: str, filename: str, data: bytes, mime_type: str) -> StoredObject:
        self._fail()
        return StoredObject("", "", "", 0)

    def get_file(self, file_id: str) -> DriveEntry | None:
        return None

    def delete(self, file_id: str) -> bool:
        return False

    def list_folder(self, folder_id: str) -> list[DriveEntry]:
        return []

    def health(self) -> DriveHealth:
        return DriveHealth(
            connected=False,
            status="UNCONFIGURED",
            message=self.reason,
            backend=self.backend_name,
            diagnostics={"configured": False},
        )


_storage: StorageBackend | None = None
_storage_lock = threading.Lock()


def build_storage(settings: Settings | None = None, *, allow_in_memory: bool = True) -> StorageBackend:
    settings = settings or get_settings()
    if settings.google_drive_configured:
        return GoogleDriveStorage(settings)
    if allow_in_memory and settings.environment in {"development", "testing"}:
        return InMemoryStorage(settings.google_drive_root_folder_id or "dev-root")
    return NullStorage()


def get_storage() -> StorageBackend:
    global _storage
    with _storage_lock:
        if _storage is None:
            _storage = build_storage()
        return _storage


def set_storage(storage: StorageBackend | None) -> None:
    """Override the backend (tests inject a fake; ``None`` restores the default)."""
    global _storage
    with _storage_lock:
        _storage = storage


def folder_path_for(category: str, project_slug: str | None = None) -> list[str]:
    """Map a media category onto the documented Drive folder layout."""
    mapping = {
        "CV": ["CV"],
        "PROFILE": ["Profile"],
        "CERTIFICATION": ["Certifications"],
        "WRITEUP": ["Writeups"],
        "EXPERIENCE": ["Experience"],
        "PROJECT": ["Projects", project_slug] if project_slug else ["Projects"],
    }
    return mapping.get(category, ["Other"])
