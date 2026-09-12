# Public API

All endpoints are **anonymous**, read-only, rate-limited and JSON. Live OpenAPI
is at `/docs` and `/redoc` (disabled automatically when `ENVIRONMENT=production`
unless `DOCS_ENABLED=true`).

Base path: the backend origin, e.g. `https://api.muhammedfasal.com`.

| Endpoint | Returns |
| --- | --- |
| `GET /api/profile` | `PublicProfile` — name, headline, bios, location, availability, contact, profile image, **enabled** social links |
| `GET /api/projects` | `ProjectSummary[]` — published projects, ordered by `sort_order` |
| `GET /api/projects?category=&featured=` | filtered list |
| `GET /api/projects/{slug}` | `ProjectDetail` — includes description, security fields and media |
| `GET /api/certifications` | `PublicCertification[]` |
| `GET /api/experience` | `PublicExperience[]` — only rows with `visible = true` |
| `GET /api/skills` | `PublicSkillCategory[]`, each with its `skills[]` |
| `GET /api/writeups` | `WriteupSummary[]` — newest first |
| `GET /api/writeups?category=&limit=` | filtered; `limit` is 1–100 (default 24) |
| `GET /api/writeups/{slug}` | `WriteupDetail` — adds `content` and `target_summary` |
| `GET /api/cv` | `PublicCV` — the current, non-archived CV |
| `GET /api/settings/public` | `PublicSettings` — SEO, OG, contact, theme, feature flags |

Health: `GET /healthz` (liveness) and `GET /health` (database + API status).

## Filtering rules

Three guarantees hold on every public endpoint (spec §38, §44):

1. **Published only.** Only `status = PUBLISHED` rows are selected. Drafts and
   archived items never appear in a list or by slug.
2. **Soft-deleted rows are excluded** (`deleted_at IS NULL`).
3. **404 parity.** A draft slug and a non-existent slug return byte-identical
   404 responses, so a visitor cannot discover that unpublished content exists.

Media URLs are nulled unless the media row's `access_policy` is `PUBLIC`, so
`RESTRICTED` files (private certificates, the CV in Drive-private mode) never
expose a direct Drive link.

## Envelope and errors

Successful responses are the resource itself — no wrapper. Errors use:

```json
{ "detail": "Project not found" }
```

Validation failures (a bad `limit`, for example) return `422` with a stable
shape that never echoes the submitted value:

```json
{ "detail": "Validation failed", "errors": [ { "field": "limit", "message": "..." } ] }
```

Database failures return `503`; unexpected failures return `500` with a generic
message when `SECURE_ERRORS` is on. Stack traces, connection strings and internal
paths are never returned or logged.

## Caching

Public payloads are cached in-process for `PUBLIC_CACHE_TTL_SECONDS` (default 60)
per namespace. Admin mutations call `portfolio_service.invalidate(...)`, so a
publish is visible immediately while anonymous traffic is served from memory.
The store is a single module (`app/utils/cache.py`); swap it for Redis in a
multi-instance deployment without touching the routes.

## Snapshot

`portfolio_service.snapshot(db)` assembles every public payload plus
`generated_at` into one object — the basis for `data/portfolio.json` (spec §77),
which lets the static site degrade gracefully when the API is unreachable.
Writing it is opt-in via `ENABLE_SNAPSHOT_WRITE`.

## Security posture

- The response models in `app/schemas/public.py` use `extra="ignore"`, so
  FastAPI drops any field a service adds by accident. This is the enforcement
  point, not a convention.
- A test scans every public response for 16 forbidden keys (`session_token_hash`,
  `github_id`, `ip_address`, `drive_file_id`, `checksum`, `deleted_at`, …) and
  fails if any appear.
- Every public route is behind the `public` rate-limit scope
  (`RATE_LIMIT_PUBLIC_PER_MINUTE`, default 120).
- Security headers are set by middleware: CSP, `X-Content-Type-Options`,
  `X-Frame-Options: DENY`, `Referrer-Policy`, and an `X-Request-Id` per request.

## Test coverage

`backend/tests/test_public_api.py` — 24 tests: draft/archive/soft-delete
exclusion across every module, 404 parity, restricted-media redaction, invisible
experience, write-up limit validation, public CV and archived-CV handling,
settings shape, the forbidden-key scan, cache hit/invalidation, TTL-0 behaviour
and OpenAPI completeness.

Verified on SQLite and on PostgreSQL 18.3 against the Alembic-migrated schema.
