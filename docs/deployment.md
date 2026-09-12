# Deployment and staging verification

How to deploy this backend, and what has and has not actually been verified.

Every result below is labelled with **where it was observed**. A result observed
against a local stand-in is not a result observed against real GitHub, and this
document does not blur that line.

---

## 1. What you need before you start

| Thing | Where it comes from |
| --- | --- |
| A hosting platform for the backend | Render, Fly.io, Railway, a VPS — anything that runs `uvicorn` over HTTPS |
| A managed PostgreSQL database | The migrations use `jsonb`, so a real PostgreSQL is required |
| A GitHub **OAuth App** | Created by hand at <https://github.com/settings/developers>. There is no API to create one. |
| The environment variables | `backend/.env.staging.example` is the template |

Backend entrypoint: `app.main:create_app` (factory). Run it with:

```bash
uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT" \
  --proxy-headers --forwarded-allow-ips='*'
```

`--proxy-headers` matters: without it the recorded session IP and the rate
limiter see the proxy's address instead of the client's.

## 2. Variable names in this project

Two names are commonly assumed and do not exist here:

| Assumed name | What this project uses |
| --- | --- |
| `FRONTEND_ORIGIN` | `CORS_ALLOWED_ORIGINS` (comma-separated) plus `FRONTEND_URL`, which is also added to the allowlist |
| `CSRF_SECRET` | Nothing. The CSRF value is derived as `HMAC(SESSION_SECRET, session_token_hash)`, so it is bound to the session and unforgeable without `SESSION_SECRET`. A second secret would add a second thing to rotate without adding security. |

## 3. Environment selection

| `ENVIRONMENT` | Behaviour |
| --- | --- |
| `development` | Ephemeral session secret, non-Secure cookies, `/docs` on. Local use only. |
| `testing` | Used by the suite. `NullPool` unless `DATABASE_POOL_CLASS` says otherwise. |
| `staging` | **Hardened exactly like production.** Secure cookies, https, explicit allowlist, no stack traces, rate limiting, no `/docs`. |
| `production` | As staging, and the intended final target. |

Staging is deliberately hardened identically to production: a staging box that
is hardened less validates nothing. Before this, `ENVIRONMENT=staging` booted
with `secure_errors` off, rate limiting off, an empty administrator allowlist
and `http` CORS origins.

Startup refuses to boot when any of these hold in staging or production:
missing `SESSION_SECRET`, `COOKIE_SECURE=false`, missing GitHub credentials,
empty `ALLOWED_GITHUB_USERNAME`, non-https `API_BASE_URL`/`GITHUB_REDIRECT_URI`,
a callback URL not served by `API_BASE_URL`, empty or non-https
`CORS_ALLOWED_ORIGINS`, `CORS_ALLOWED_ORIGINS=*`, `SECURE_ERRORS=false`,
`RATE_LIMIT_ENABLED=false`, or a placeholder database password.

## 4. GitHub OAuth App

1. <https://github.com/settings/developers> → **OAuth Apps** → **New OAuth App**.
2. **Homepage URL** — the deployed frontend, e.g. `https://staging.example.com`.
3. **Authorization callback URL** — exactly
   `https://<api-host>/auth/github/callback`, character for character.
4. Create a **separate app per environment**. Never share one between staging
   and production.
5. Store the client secret only in the hosting provider's secret store.

The callback must match `GITHUB_REDIRECT_URI` exactly; a mismatch is the usual
cause of GitHub's `redirect_uri_mismatch`. Startup validation also requires the
callback to be served by `API_BASE_URL`, which catches most of these before
they reach GitHub.

## 5. Deploying the backend

```bash
# 1. dependencies
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 2. configuration (never committed)
cp .env.staging.example .env.staging     # then fill in real values

# 3. migrations against the staging database
export $(grep -v '^#' .env.staging | xargs)
alembic upgrade head

# 4. run
uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT" \
  --proxy-headers --forwarded-allow-ips='*'
```

Verify after deploy:

```bash
curl -s https://<api-host>/health      # overall ONLINE, database ONLINE
curl -s -o /dev/null -w '%{http_code}\n' https://<api-host>/docs   # 404
```

## 6. Deploying the frontend

The public site is a static GitHub Pages site and is **not** rebuilt or
modified by this project. It currently contains no API origin at all — there is
no `assets/js/api.js` yet — so there is no localhost API URL to remove. When the
public site is wired to the API in a later phase, the API base URL must come
from build-time configuration, never from a committed localhost default, and the
deployed origin must be listed in `CORS_ALLOWED_ORIGINS`.

## 7. Recorded staging verification

Environment used for the observations below:

- Backend: `uvicorn`, `ENVIRONMENT=staging`, `COOKIE_SECURE=true`,
  `DOCS_ENABLED=false`, `SECURE_ERRORS=true`, `RATE_LIMIT_ENABLED=true`,
  `SESSION_COOKIE_SAMESITE=lax`.
- Database: SQLite with the real Alembic migrations applied
  (`alembic upgrade head` → 23 tables, `oauth_states` present,
  `a7c4e91f3b52`).
- Public HTTPS URL: `https://8000-<sandbox-id>.e2b.app`.

### 7.1 Verified against the running staging server

Observed over real HTTP against the deployed uvicorn process.

| # | Check | Result |
| --- | --- | --- |
| 1 | `GET /health` | **200**, `overall: ONLINE`, database `ONLINE`, github `CONFIGURED` |
| 2 | `/docs`, `/redoc`, `/openapi.json` | **404, 404, 404** |
| 3 | CORS, approved origin | `Access-Control-Allow-Origin` echoed verbatim + `Allow-Credentials: true` |
| 3 | CORS, unapproved origin | **no** `Access-Control-Allow-Origin` header emitted |
| 3 | CORS preflight | 200, allows `X-CSRF-Token`, echoes the approved origin |
| 4 | `GET /auth/github` | **302** to `https://github.com/login/oauth/authorize` with `client_id`, `redirect_uri`, `scope`, `state`, `allow_signup=false` |
| 4 | redirect target | reached **real `github.com`**, which carried our `client_id`, `redirect_uri`, `scope` and `state` through its login page |
| 6 | session cookie | `HttpOnly; Max-Age=28800; Path=/; SameSite=lax; Secure` |
| 6 | CSRF cookie | **not** HttpOnly (readable by JS, as designed), `Secure`, `SameSite=lax` |
| 6 | state cookie on success | cleared (`Max-Age=0`) |
| 7 | `GET /auth/me` | **200** with `id`, `github_username`, `display_name`, `avatar_url`, `role` only |
| 8 | session persistence | two consecutive `/auth/me` calls → **200, 200** |
| 9 | OAuth state replay | **400** `The sign-in request is no longer valid.`; sessions in DB unchanged (+0) |
| 9 | state without binding cookie | **400** |
| 10 | logout with CSRF | **204**; both cookies cleared; replaying the same cookie → **401** |
| 11 | logout without CSRF header | **403** `CSRF validation failed.` |
| 11 | logout with wrong CSRF | **403** |
| 12 | unauthenticated `/auth/me` | **401** |
| 13 | non-allowlisted origin | **no** `Access-Control-Allow-Origin` header |
| 14 | forged session token | **401** |
| 15 | secrets in `/auth/me` body | **0** occurrences of the client secret or session secret |
| 15 | secrets in the server log | grepped a real 1460-byte log after a full flow: client secret, session secret, access token, raw session token and raw OAuth state **all absent**; 0 tracebacks |
| — | state storage | only a 64-char SHA-256 hash is stored; the raw state is **not** present in the database; `used_at` set after consumption |

### 7.2 Verified against a local GitHub-API stand-in — NOT real GitHub

The callback, session and authorization behaviour above required a completed
OAuth exchange. No GitHub OAuth App exists, so `GITHUB_TOKEN_URL` and
`GITHUB_API_URL` were pointed at a local HTTP stand-in that mimics
`POST /login/oauth/access_token` and `GET /user`.

This exercised the backend's **real** `httpx` code path and is why items 5–10
could be observed. It does **not** prove that real GitHub issues a code, that
the real token exchange succeeds, or that a real profile is returned. Items 5–10
must be repeated against a real OAuth App before the flow can be called
verified.

### 7.3 Blocked — not verified

| Item | Blocker |
| --- | --- |
| 5 | A real GitHub OAuth round trip. GitHub exposes **no API to create an OAuth App** (`POST /user/oauth_apps` → `404`), and creating one needs a human at the web UI. No credentials were available. |
| 3, 6, 8 | The public HTTPS URL through the proxy. The hostname resolves, but outbound TLS from this sandbox fails (`SSL_ERROR_SYSCALL`), so the TLS/proxy layer was not observed. A browser can reach it; this environment could not. |
| 3 | The frontend loading without console errors — no frontend build exists that calls the API yet. |

The staging database was SQLite, not managed PostgreSQL. The migrations ran
cleanly on it, but production uses `jsonb` columns and must be verified against
a real PostgreSQL instance.

## 8. Remaining manual steps

1. Provision a staging host with HTTPS and a managed PostgreSQL.
2. Create the staging GitHub OAuth App with the exact callback URL.
3. Fill in `.env.staging` from the template; keep it out of git.
4. `alembic upgrade head` against the staging database.
5. Deploy and confirm `/health` is `ONLINE` and `/docs` is `404`.
6. Walk `docs/authentication.md` → *Manual deployment verification* end to end
   with a real GitHub account, and record each result.
7. Only then treat the login flow as verified.
