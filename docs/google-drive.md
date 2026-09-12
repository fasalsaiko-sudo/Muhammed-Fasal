# Google Drive storage

> **Status: implemented and mock-tested — live verification pending credentials.**
>
> `app/services/google_drive.py` contains the real integration. Its test suite
> (`backend/tests/test_google_drive_service.py`, 20 tests) runs the real code
> path against a fake `googleapiclient` client, so nothing in CI needs a Google
> account. **No end-to-end call against live Drive has been made**, because no
> service-account credentials have been supplied. Do not treat this as verified
> until the checklist at the bottom has been completed.

## What this module does

Drive is the file store; PostgreSQL holds only metadata (spec §78). The module
exposes a `StorageBackend` protocol with two implementations:

| Implementation | Used by |
| --- | --- |
| `GoogleDriveStorage` | production — service-account authenticated Drive v3 |
| `InMemoryStorage` | unit tests only |

Operations: `ensure_folder(path)`, `upload(...)`, `get_file(id)`,
`list_folder(id)`, `delete(id)`, `health()`. `build_storage(settings)` picks the
backend, so application code never imports a concrete client.

## Folder layout

The root folder is the **only** storage boundary the application touches. Child
folders are created on demand by `ensure_folder`, so you never share individual
files:

```
Portfolio CMS/                      <- GOOGLE_DRIVE_ROOT_FOLDER_ID
├── CV/
├── Profile/
├── Projects/
│   ├── WebSafeScan/
│   └── AutoBrowserSwitch/
├── Certifications/
├── Writeups/
├── Experience/
└── Other/
```

## One-time Google Cloud setup

1. **Create or select a project** — <https://console.cloud.google.com/projectcreate>.
   Any project name works; the code defaults its internal `project_id` label to
   `portfolio-cms` when using an inline key.
2. **Enable the Drive API** — APIs & Services → Library → search **Google Drive
   API** → Enable.
3. **Create a service account** — IAM & Admin → Service Accounts → *Create*.
   No project roles are required; access is granted per-folder in step 5, which
   keeps the blast radius minimal.
4. **Create a key** — Service account → Keys → *Add key* → *Create new key* →
   **JSON**. This downloads a file such as `portfolio-cms-3f1a2b.json`.
5. **Share the CMS folder with the service account** — in Google Drive, right-click
   the *Portfolio CMS* folder → Share → add the service account's
   `client_email` (looks like `portfolio-cms@your-project.iam.gserviceaccount.com`)
   → role **Editor** → *Send*.
   - Share **only that folder**. Never share your Drive root and never use "anyone
     with the link".
   - Editor is required because the backend creates folders and uploads files.
6. Confirm the folder ID from its URL:
   `https://drive.google.com/drive/folders/<THIS_IS_THE_ID>`.

## Configuration

Two mutually exclusive ways to supply the key:

```bash
# Option A — key file on disk (simplest for a VM/container with a mounted secret)
GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/portfolio-cms.json
GOOGLE_DRIVE_ROOT_FOLDER_ID=1gGcnYdfjX5PCWJP-gwwUwIFflHZlVqIW

# Option B — inline values ( suits platform secret managers )
GOOGLE_SERVICE_ACCOUNT_EMAIL=portfolio-cms@your-project.iam.gserviceaccount.com
GOOGLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
GOOGLE_DRIVE_ROOT_FOLDER_ID=1gGcnYdfjX5PCWJP-gwwUwIFflHZlVqIW

# Whether uploaded files get an "anyone with the link: reader" permission.
DRIVE_PUBLIC_READ=true
```

`GOOGLE_APPLICATION_CREDENTIALS` wins when both are set. `google_drive_configured`
is true only when the root folder ID **and** one of the two credential forms are
present; otherwise uploads raise `StorageUnavailable` and `/health` reports
`UNCONFIGURED` rather than failing at boot.

`GOOGLE_PRIVATE_KEY` keeps literal `\n` escapes — pydantic converts them to real
newlines, so the value can live on one line in a secret manager.

## Local development

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in the Google values
alembic upgrade head
uvicorn app.main:create_app --factory --reload --host 0.0.0.0 --port 8000
```

`.env` is gitignored; `.env.example` is the only committed template and holds
placeholders only.

Without credentials the API still runs and still serves the public portfolio —
Drive is reported as `UNCONFIGURED` and uploads are refused cleanly.

## Production

- Store the key in the platform secret manager (Render/Fly/Cloud Run secret,
  Vault). Do not bake it into an image or commit it.
- On Cloud Run you can attach the service account directly and use
  Workload Identity instead of a key file.
- Keep `ENVIRONMENT=production`: this disables `/docs`, enables secure cookies and
  switches error responses to generic messages.
- `DRIVE_PUBLIC_READ=false` is the safer default for private documents; the media
  `access_policy` column then governs whether a URL is exposed at all
  (`RESTRICTED` media never returns `url`/`thumbnail_url`/`download_url`).

## Credential rotation

1. Create a **new** key for the same service account (do not delete the old one yet).
2. Update the secret in the platform manager and redeploy.
3. Confirm `/health` reports Drive as connected.
4. Delete the old key in the Cloud console.

Rotate on a schedule and immediately on any suspected leak. Revoking a key in the
console invalidates it within minutes.

## Security notes

- The scope requested is `https://www.googleapis.com/auth/drive.file` — the
  narrowest scope that permits access to files the app creates or that are shared
  with it. It is deliberately **not** the full-drive scope.
- Credentials exist only in backend process memory. They are never sent to the
  Flutter admin or the public site, and never appear in an API response.
- `health()` reports missing variable **names** only. A test asserts the private
  key and root folder ID never appear in the payload or in logs.
- `_escape_query_value` escapes quotes in folder names before they enter a Drive
  query string (covered by `test_ensure_folder_escapes_quotes_in_folder_names`).

## What is verified vs. not

| Behaviour | Verified |
| --- | --- |
| Upload targets the requested parent folder | mock test |
| Public sharing on/off, and surviving a sharing failure | mock test |
| Listing, pagination, folder detection | mock test |
| `ensure_folder` create/reuse/cache and query escaping | mock test |
| Permission errors → `None` / `False`, not a crash | mock test |
| Unconfigured → `StorageUnavailable` + `UNCONFIGURED` health | mock test |
| No credential leakage into logs or responses | mock test |
| **Real authentication against Google** | **not verified** |
| **Real upload/download/list against Drive** | **not verified** |
| **Thumbnail generation by Drive** | **not verified** |

### Live verification checklist

1. Complete the Google Cloud setup above and put the key in `backend/.env`.
2. Start the API and confirm `GET /health` shows Drive connected.
3. Upload one small image through the media service and confirm it appears under
   `Portfolio CMS/Projects/<project>/` in Drive.
4. Confirm the returned `thumbnail_link` renders.
5. Delete it through the API and confirm it is trashed in Drive.
6. Only then treat this integration as verified.
