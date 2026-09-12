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

A **managed, remote** PostgreSQL is still blocked — see section 9.6. However the
PostgreSQL compatibility question itself is now answered: see 7.4.

### 7.4 Verified against native PostgreSQL 16.2

The SQLite caveat above no longer applies. A real PostgreSQL server was run
locally (`pgserver`, which ships upstream binaries — not PGlite, not SQLite) and
the whole stack was re-verified against it.

| Check | Result |
| --- | --- |
| Server | `PostgreSQL 16.2 on x86_64-pc-linux-gnu, compiled by gcc (GCC) 10.2.1, 64-bit`, `max_connections=100` |
| `alembic upgrade head` from an empty schema | EXIT 0 → **23 tables**, `oauth_states` present, head `a7c4e91f3b52` |
| Migration round trip | `upgrade head` → `downgrade -1` (`d9a6f32bce4c`) → `upgrade head` (`a7c4e91f3b52`), all EXIT 0 |
| Column types | **7 `jsonb`** columns, **43 `timestamp with time zone`**, **0** naive timestamps |
| `jsonb` round trip via the ORM | `technologies`, `tools_used`, `metadata` preserve nested bools and ints; bound as `::JSONB` |
| `jsonb` operators server-side | `->`, `->>`, `@>`, `jsonb_array_elements` all evaluated in the server |
| Full suite | **289 tests, 0 failures, 0 skipped**, twice |
| Full suite on SQLite | **289 tests, 0 failures, 26 skipped** — the 26 skipped are exactly `tests/test_postgres_backend.py`, which is gated on a real PostgreSQL server and must never pass on SQLite |
| Server-side constraints | `DROP INDEX ix_projects_slug` → `test_unique_slug_is_enforced_by_the_server` fails; restored → passes |
| Schema mutation checks | 4 mutations applied and **all caught**: `projects.technologies` → `text`, `admin_sessions.expires_at` → naive `timestamp`, drop `ix_projects_slug`, `audit_logs.metadata` → `text`. Schema restored exactly afterwards (23/43/0/7/1) |
| **Session survives a restart** | a session created before a process restart (PID 14580 → 14656) authenticated afterwards with the **same cookie**: `/auth/me` → **200**. In-process equivalent: `reset_engine()` disposes the pool and drops the cached factory, and the row is still readable |
| Only hashes persisted | `admin_sessions.session_token_hash` and `oauth_states.state_hash` are 64-char digests; no raw token/state column exists |

Two notes on how this was obtained, so the result is not over-read:

- The session used in the restart test was minted by the **local stand-in**, so
  this proves session *storage* survives a restart. It does not prove real
  GitHub issues a working session — that is still item 5.
- The server was local to the sandbox. It is genuine PostgreSQL, so column
  types, operators, constraints and connection handling are all real; what it
  does not prove is connectivity to a *remote* managed instance over TLS.

## 8. Remaining manual steps

1. Provision a staging host with HTTPS (section 9 covers Render) and a managed
   PostgreSQL.
2. Create the staging GitHub OAuth App with the exact callback URL.
3. Fill in `.env.staging` from the template; keep it out of git.
4. `alembic upgrade head` against the staging database.
5. Deploy and confirm `/health` is `ONLINE` and `/docs` is `404`.
6. Walk `docs/authentication.md` → *Manual deployment verification* end to end
   with a real GitHub account, and record each result.
7. Only then treat the login flow as verified.

## 9. Render deployment runbook

Render is the reference platform for this project: it terminates TLS at its edge
(giving the permanent public HTTPS URL the OAuth callback needs) and offers a
managed PostgreSQL. Everything below is a procedure to run by hand — it has
**not** been executed, because no Render account or API key was available in the
environment where this document was written. Each command is nevertheless
checked against the code in this repository.

### 9.1 Prerequisites

- A Render account, and either `render` CLI authenticated (`render login`) or
  dashboard access.
- A GitHub OAuth App for staging (section 4).
- The repository pushed to GitHub.

### 9.2 Create the managed PostgreSQL

1. Dashboard → **New → PostgreSQL** → region close to the web service.
2. After provisioning, copy the **Internal Database URL**.
3. **Rewrite the scheme.** Render hands out `postgresql://…`, but this project
   ships `psycopg` 3 only — there is no `psycopg2`. Verified locally:

   ```text
   postgresql://            -> ModuleNotFoundError: No module named 'psycopg2'
   postgresql+psycopg://    -> OK
   ```

   So set `DATABASE_URL` to `postgresql+psycopg://user:pass@host:5432/db`.
   `Settings.database_url` is used verbatim; it does not normalise the scheme.
   If the internal URL is unavailable, use the External one and add
   `?sslmode=require`.

### 9.3 Create the web service

**New → Web Service**, connect the repo, then:

| Field | Value |
| --- | --- |
| Root directory | `backend` |
| Runtime | `Python 3` |
| Build command | `pip install -r requirements.txt` |
| Pre-deploy command | `python -m alembic upgrade head` |
| Start command | `uvicorn app.main:create_app --factory --host 0.0.0.0 --port $PORT` |
| Health check path | `/healthz` |
| Plan | Starter or above (free tier spins down, which drops sessions from the app's point of view) |

Use the **pre-deploy command** for migrations, not the start command: Render runs
it once per deploy, so concurrent instances never race each other on the schema.

### 9.4 Environment variables

Set these on the service. Names and constraints are enforced at startup by
`app/config/settings.py`; a wrong value fails the boot rather than degrading
silently.

| Variable | Example | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `staging` | Hardened exactly like `production` |
| `API_BASE_URL` | `https://staging-api.onrender.com` | Must be `https`; must match the public URL |
| `DATABASE_URL` | `postgresql+psycopg://…` | See 9.2 — the scheme matters |
| `DATABASE_POOL_CLASS` | `auto` | Never `static` outside the PGlite harness |
| `GITHUB_CLIENT_ID` | `Ov23li…` | From the OAuth App |
| `GITHUB_CLIENT_SECRET` | *(secret)* | Mark **Secret** in Render |
| `GITHUB_REDIRECT_URI` | `https://staging-api.onrender.com/auth/github/callback` | Must start with `API_BASE_URL` — checked at startup |
| `ALLOWED_GITHUB_USERNAME` | `Fasal17` | Comma-separated; empty refuses to boot in staging |
| `SESSION_SECRET` | *(secret, ≥32 chars)* | Rotating it signs every session out |
| `COOKIE_SECURE` | `true` | Required for staging/production |
| `SESSION_COOKIE_SAMESITE` | `lax` | See `docs/authentication.md` → *Choosing SameSite* |
| `CORS_ALLOWED_ORIGINS` | `https://fasalsaiko.github.io` | https only, no `*` |
| `FRONTEND_URL` | `https://fasalsaiko.github.io/Muhammed-Fasal` | Post-login redirect target |
| `ADMIN_URL` | same as `FRONTEND_URL` | |
| `SECURE_ERRORS` | `true` | No stack traces to clients |
| `RATE_LIMIT_ENABLED` | `true` | |
| `DOCS_ENABLED` | `false` | `/docs`, `/redoc`, `/openapi.json` → 404 |
| `TRUST_PROXY_HEADERS` | `true` | Render terminates TLS at its edge |

Render injects `PORT`; the start command already binds `$PORT`.

### 9.5 Post-deploy smoke test

```bash
API=https://staging-api.onrender.com          # your real host

curl -fsS "$API/healthz"                      # 200 liveness
curl -fsS "$API/health" | jq .                # overall ONLINE, database ONLINE
curl -s -o /dev/null -w '%{http_code}\n' "$API/docs"          # 404
curl -s -o /dev/null -w '%{http_code}\n' "$API/openapi.json"  # 404
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' "$API/auth/github"
#   expect 302 -> https://github.com/login/oauth/authorize?client_id=...&state=...
curl -s -D- -o /dev/null -H "Origin: https://fasalsaiko.github.io" "$API/healthz" \
  | grep -i 'access-control-allow-origin'     # echoes the approved origin
```

Then confirm in the Render log stream that a full sign-in writes **no** client
secret, session secret, access token, raw session token or raw OAuth state, and
no tracebacks.

### 9.6 Rollback

Render has **no `render deploys rollback` CLI command**. Rollback is available in
two places only, and they differ in an important way:

**A. Dashboard** — service → **Deploys** → pick the last good deploy →
**Rollback** → confirm. This reuses the stored build artifact, so it is fast.
It **disables autodeploys** for the service; re-enable them from **Settings**
once the issue is fixed, or the service stays on manual deploy indefinitely.

**B. API** — does *not* disable autodeploys, so a new push can immediately
reintroduce the change you just rolled back:

```bash
curl -X POST "https://api.render.com/v1/services/<service-id>/rollback" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"deployId": "<previous-deploy-id>"}'
```

**C. CLI fallback** — the CLI can list deploys and deploy a specific commit, so
you can pin back to the last good SHA instead of using the rollback artifact:

```bash
render deploys list <service-id> -o json      # find the last good deploy/commit
render deploys create <service-id> --commit <sha> --wait --confirm
render logs -r <service-id>                   # tail the log while it comes up
```

`render deploys list` takes the service id as a **positional** argument, not
`--service`.

**Rollback never touches the database.** It restores code, build artifact, start
command, health check path, env vars and instance count — but not schema state.
Two consequences:

- `alembic downgrade -1` is *not* run for you, and it reverses only the last
  revision. `a7c4e91f3b52` (adding `oauth_states`) is the current head.
- Keep migrations backward-compatible ("expand and contract") so the previous
  build can run against the current schema. Today the schema is additive, so a
  code rollback needs **no** schema change — the older code simply ignores
  `oauth_states`. Prefer that over downgrading the schema while a newer instance
  may still be serving traffic.

Take a dump before any deploy that carries a destructive migration:

```bash
pg_dump "$DATABASE_URL" --no-owner --format=custom --file=pre-deploy.dump
# restore:
pg_restore --clean --if-exists -d "$DATABASE_URL" pre-deploy.dump
```

Two limits worth knowing before you rely on rollback: Render only keeps a fixed
number of recent build artifacts per plan, so an old deploy may no longer be
rollback-able; and if the health check keeps failing for 15 consecutive minutes
(each check gets 5 seconds), Render cancels the deploy and keeps the previous
instance serving — which is the automatic rollback you want during a bad release.

**Rotate a compromised secret** without a code change: update `SESSION_SECRET`
(and/or `GITHUB_CLIENT_SECRET`) in the Render environment and redeploy. Changing
`SESSION_SECRET` invalidates every session, because the stored value is a hash
derived from it.

### 9.7 Secret management

- Store `GITHUB_CLIENT_SECRET` and `SESSION_SECRET` as Render **Secret** env
  vars. They must never appear in `render.yaml`, the repo, or a log line.
- `backend/.env.staging.example` is a template with placeholders only. The real
  `.env.staging` is git-ignored; `.gitignore` carries an explicit
  `!.env.*.example` negation so templates stay committable while real env files
  do not.
- Generate secrets, do not reuse them:
  `python -c "import secrets;print(secrets.token_urlsafe(48))"`.
- Keep the staging OAuth App separate from production.

### 9.8 Known limitations

- This runbook is **unexecuted**. No Render account existed in the writing
  environment, so no service, no database and no public HTTPS URL were created.
- Consequently the real GitHub OAuth round trip is still unverified — see 7.2
  and 7.3.
- The public frontend has **no API integration yet**: there is no login control,
  no `api.js`, and no configured origin. Until that lands, the deployed backend
  can only be exercised with `curl` or a browser hitting `/auth/github` directly.
- `SameSite=lax` is the safe default, but a cross-site frontend on
  `github.io` calling an `onrender.com` API will not send cookies on
  cross-site POSTs. If the frontend and API end up on different sites, either
  serve them from one origin or move to `SameSite=None; Secure` after reading
  `docs/authentication.md` → *Choosing SameSite*.
