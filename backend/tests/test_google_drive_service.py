"""Google Drive storage service — mock-tested, no live credentials required.

Status: **implemented and mock-tested — live verification pending credentials.**
The fake below mimics the ``googleapiclient`` fluent surface (``files()``,
``permissions()``, ``.execute()``), so the real ``GoogleDriveStorage`` code path
runs end to end; only the network boundary is faked. Live verification against
Drive requires a service account and is documented in docs/google-drive.md.
"""

from __future__ import annotations

import pytest

from app.services.google_drive import (
    FOLDER_MIME,
    GoogleDriveStorage,
    InMemoryStorage,
    StorageUnavailable,
)

PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nFAKEFAKEFAKE\n-----END PRIVATE KEY-----"
ROOT = "1gGcnYdfjX5PCWJP-gwwUwIFflHZlVqIW"


class _FakeRequest:
    def __init__(self, result=None, error=None):
        self._result = result if result is not None else {}
        self._error = error

    def execute(self):
        if self._error is not None:
            raise self._error
        return self._result


class _FakeFiles:
    def __init__(self, harness):
        self._h = harness

    def create(self, **kwargs):
        self._h.calls.append(("create", kwargs))
        if self._h.create_error:
            return _FakeRequest(error=self._h.create_error)
        body = kwargs.get("body", {})
        self._h.next_id += 1
        return _FakeRequest(
            {
                "id": self._h.next_folder_id if body.get("mimeType") == FOLDER_MIME else f"file-{self._h.next_id}",
                "name": body.get("name", ""),
                "mimeType": body.get("mimeType", "application/octet-stream"),
                "size": "4096",
            }
        )

    def get(self, **kwargs):
        self._h.calls.append(("get", kwargs))
        if self._h.get_error:
            return _FakeRequest(error=self._h.get_error)
        return _FakeRequest(self._h.get_result)

    def delete(self, **kwargs):
        self._h.calls.append(("delete", kwargs))
        return _FakeRequest(error=self._h.delete_error)

    def list(self, **kwargs):
        self._h.calls.append(("list", kwargs))
        return _FakeRequest(self._h.next_list_response())


class _FakePermissions:
    def __init__(self, harness):
        self._h = harness

    def create(self, **kwargs):
        self._h.calls.append(("permissions", kwargs))
        return _FakeRequest(error=self._h.permission_error)


class _Harness:
    """Configurable stand-in for the Drive API client."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.next_id = 100
        self.next_folder_id = "folder-new"
        self.create_error = None
        self.get_error = None
        self.get_result = {"id": "root-1", "name": "Portfolio CMS", "mimeType": FOLDER_MIME}
        self.delete_error = None
        self.permission_error = None
        self.list_pages: list[dict] = []

    def next_list_response(self) -> dict:
        return self.list_pages.pop(0) if self.list_pages else {"files": []}

    def files(self):
        return _FakeFiles(self)

    def permissions(self):
        return _FakePermissions(self)

    def of(self, name: str) -> list[dict]:
        return [kwargs for op, kwargs in self.calls if op == name]


@pytest.fixture
def drive_settings(settings, monkeypatch):
    monkeypatch.setattr(settings, "google_drive_root_folder_id", ROOT)
    monkeypatch.setattr(settings, "google_service_account_email", "cms@portfolio.iam.gserviceaccount.com")
    monkeypatch.setattr(settings, "google_private_key", PRIVATE_KEY)
    monkeypatch.setattr(settings, "google_application_credentials", "")
    return settings


def _storage(settings) -> tuple[GoogleDriveStorage, _Harness]:
    harness = _Harness()
    storage = GoogleDriveStorage(settings)
    storage._service = harness  # bypasses credential loading and the network
    return storage, harness


# --------------------------------------------------------------------- upload
def test_upload_places_the_file_in_the_requested_folder(drive_settings):
    storage, harness = _storage(drive_settings)
    stored = storage.upload(folder_id="folder-abc", filename="cover.png",
                            data=b"png-bytes", mime_type="image/png")

    create = harness.of("create")[0]
    assert create["body"]["parents"] == ["folder-abc"]
    assert create["body"]["name"] == "cover.png"
    assert create["body"]["mimeType"] == "image/png"
    assert stored.filename == "cover.png"
    assert stored.size_bytes == 4096
    assert stored.file_id.startswith("file-")


def test_upload_shares_publicly_only_when_configured(drive_settings, monkeypatch):
    storage, harness = _storage(drive_settings)
    storage.upload(folder_id="f", filename="a.png", data=b"x", mime_type="image/png")
    shared = harness.of("permissions")
    assert shared and shared[0]["body"] == {"type": "anyone", "role": "reader"}

    monkeypatch.setattr(drive_settings, "drive_public_read", False)
    storage2, harness2 = _storage(drive_settings)
    storage2.upload(folder_id="f", filename="b.png", data=b"x", mime_type="image/png")
    assert harness2.of("permissions") == []


def test_upload_survives_a_sharing_failure_and_logs_it(drive_settings, caplog):
    storage, harness = _storage(drive_settings)
    harness.permission_error = PermissionError("insufficient permissions")

    with caplog.at_level("WARNING"):
        stored = storage.upload(folder_id="f", filename="a.png", data=b"x", mime_type="image/png")

    assert stored.file_id  # the upload is not lost
    assert "drive_share_failed" in caplog.text


def test_upload_raises_a_clear_error_when_drive_is_unconfigured(settings, monkeypatch):
    monkeypatch.setattr(settings, "google_private_key", "")
    monkeypatch.setattr(settings, "google_service_account_email", "")
    storage, _ = _storage(settings)
    with pytest.raises(StorageUnavailable) as excinfo:
        storage.upload(folder_id="f", filename="a.png", data=b"x", mime_type="image/png")
    assert "not configured" in str(excinfo.value)


def test_upload_propagates_drive_errors(drive_settings):
    storage, harness = _storage(drive_settings)
    harness.create_error = PermissionError("403 quota exceeded")
    with pytest.raises(PermissionError):
        storage.upload(folder_id="f", filename="a.png", data=b"x", mime_type="image/png")


# --------------------------------------------------------------------- listing
def test_list_folder_queries_the_folder_it_was_given(drive_settings):
    """Regression: this once built the query from an undefined ``file_id``."""
    storage, harness = _storage(drive_settings)
    harness.list_pages = [{"files": [{"id": "f1", "name": "a.png", "mimeType": "image/png", "size": "10"}]}]

    entries = storage.list_folder("folder-xyz")

    query = harness.of("list")[0]["q"]
    assert "folder-xyz" in query
    assert "in parents" in query
    assert [entry.file_id for entry in entries] == ["f1"]
    assert entries[0].name == "a.png"
    assert entries[0].is_folder is False


def test_list_folder_follows_pagination(drive_settings):
    storage, harness = _storage(drive_settings)
    harness.list_pages = [
        {"files": [{"id": "f1", "name": "a", "mimeType": "image/png"}], "nextPageToken": "page-2"},
        {"files": [{"id": "f2", "name": "b", "mimeType": "image/png"}]},
    ]
    entries = storage.list_folder("folder-1")
    assert [entry.file_id for entry in entries] == ["f1", "f2"]
    assert harness.of("list")[1]["pageToken"] == "page-2"


def test_folder_mime_type_is_detected(drive_settings):
    storage, harness = _storage(drive_settings)
    harness.list_pages = [{"files": [{"id": "sub", "name": "WebSafeScan", "mimeType": FOLDER_MIME}]}]
    assert storage.list_folder("root")[0].is_folder is True


# --------------------------------------------------------------------- folders
def test_ensure_folder_reuses_an_existing_child(drive_settings):
    storage, harness = _storage(drive_settings)
    harness.list_pages = [{"files": [{"id": "existing-projects", "name": "Projects"}]}]

    assert storage.ensure_folder(["Projects"]) == "existing-projects"
    assert harness.of("create") == []


def test_ensure_folder_creates_the_path_when_missing(drive_settings):
    storage, harness = _storage(drive_settings)
    harness.list_pages = [{"files": []}, {"files": []}]  # Projects/, then WebSafeScan/

    folder_id = storage.ensure_folder(["Projects", "WebSafeScan"])

    creates = harness.of("create")
    assert len(creates) == 2
    assert creates[0]["body"]["parents"] == [ROOT]
    assert creates[0]["body"]["name"] == "Projects"
    assert creates[1]["body"]["name"] == "WebSafeScan"
    assert folder_id == harness.next_folder_id


def test_ensure_folder_result_is_cached(drive_settings):
    storage, harness = _storage(drive_settings)
    harness.list_pages = [{"files": [{"id": "cached-id", "name": "CV"}]}]

    first = storage.ensure_folder(["CV"])
    second = storage.ensure_folder(["CV"])
    assert first == second == "cached-id"
    assert len([op for op, _ in harness.calls if op == "list"]) == 1


def test_ensure_folder_escapes_quotes_in_folder_names(drive_settings):
    storage, harness = _storage(drive_settings)
    storage.ensure_folder(["O'Reilly"])
    query = harness.of("list")[0]["q"]
    assert "\\'" in query  # the apostrophe is escaped, not injected


# ------------------------------------------------------------------ single file
def test_get_file_maps_the_entry(drive_settings):
    storage, harness = _storage(drive_settings)
    harness.get_result = {"id": "abc", "name": "cv.pdf", "mimeType": "application/pdf",
                          "size": "2048", "modifiedTime": "2026-09-01T00:00:00Z"}
    entry = storage.get_file("abc")
    assert entry is not None
    assert entry.name == "cv.pdf"
    assert entry.size_bytes == 2048
    assert entry.is_folder is False


def test_get_file_returns_none_on_a_permission_error(drive_settings):
    storage, harness = _storage(drive_settings)
    harness.get_error = PermissionError("403 forbidden")
    assert storage.get_file("abc") is None


def test_delete_reports_failure_instead_of_raising(drive_settings):
    storage, harness = _storage(drive_settings)
    assert storage.delete("abc") is True
    harness.delete_error = PermissionError("403")
    assert storage.delete("abc") is False


# --------------------------------------------------------------------- health
def test_health_reports_unconfigured_without_leaking_values(settings, monkeypatch):
    monkeypatch.setattr(settings, "google_drive_root_folder_id", "")
    monkeypatch.setattr(settings, "google_private_key", "")
    monkeypatch.setattr(settings, "google_service_account_email", "")
    health = GoogleDriveStorage(settings).health()

    assert health.connected is False
    assert health.status == "UNCONFIGURED"
    payload = health.payload()
    assert "GOOGLE_DRIVE_ROOT_FOLDER_ID" in payload["diagnostics"]["missing"]
    # Only variable NAMES are reported, never their values.
    assert PRIVATE_KEY not in str(payload)
    assert ROOT not in str(payload)


def test_health_is_connected_when_the_root_folder_is_readable(drive_settings):
    storage, _ = _storage(drive_settings)
    health = storage.health()
    assert health.connected is True
    assert health.payload()["backend"] == "google-drive"


def test_health_is_degraded_when_the_root_folder_is_unreachable(drive_settings):
    storage, harness = _storage(drive_settings)
    harness.get_error = PermissionError("403 access denied")
    health = storage.health()
    assert health.connected is False
    assert PRIVATE_KEY not in str(health.payload())


def test_credentials_never_appear_in_logs(drive_settings, caplog):
    storage, _ = _storage(drive_settings)
    with caplog.at_level("DEBUG"):
        storage.upload(folder_id="f", filename="a.png", data=b"x", mime_type="image/png")
        storage.health()
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert PRIVATE_KEY not in logged
    assert "FAKEFAKEFAKE" not in logged


# ------------------------------------------------------- in-memory test backend
def test_in_memory_backend_satisfies_the_storage_contract():
    """The backend the unit tests use must behave like the real one."""
    store = InMemoryStorage(root_folder_id=ROOT)
    assert store.available is True

    folder = store.ensure_folder(["Projects", "WebSafeScan"])
    stored = store.upload(folder_id=folder, filename="shot.png", data=b"1234", mime_type="image/png")

    listed = store.list_folder(folder)
    assert [entry.name for entry in listed] == ["shot.png"]
    assert store.get_file(stored.file_id) is not None
    assert store.delete(stored.file_id) is True
    assert store.list_folder(folder) == []
    assert store.get_file(stored.file_id) is None
    assert store.health().connected is True
