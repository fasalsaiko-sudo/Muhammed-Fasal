# Authentication and authorization

> **Status: OAuth service implemented and mock-tested — live verification pending
> credentials, and the login routes are not wired yet (Phase 5).**
>
> What exists today: `app/services/github_oauth.py` (real GitHub OAuth client),
> the configuration and its validation, and 24 mock tests covering it.
> What does **not** exist yet: the `/auth/*` routes, session issuance, the
> authentication/authorization middleware and the admin surface. Those are
> Phase 5. Do not expect to log in to the CMS from this branch.

## Intended flow (spec §6)

```
Admin opens /admin (Flutter)
   │
   ▼
GET /auth/github            backend builds the authorize URL + random state
   │
   ▼
github.com/login/oauth/authorize      (user approves)
   │
   ▼  redirect with ?code=&state=
GET /auth/github/callback
   │  1. state must match the value the backend issued
   │  2. exchange code -> access token        (server-to-server)
   │  3. GET /user with that token
   │  4. BACKEND checks the login against ALLOWED_GITHUB_USERNAME
   │  5. create session row, store only its hash
   ▼
Set-Cookie (HttpOnly) -> redirect to the Flutter dashboard
```

The authorization decision is made **on the backend** (step 4). Flutter is a
client; it is never trusted to decide who is an administrator.

## GitHub OAuth app setup

1. Go to <https://github.com/settings/developers> → **OAuth Apps** → *New OAuth App*.
2. Fill in:
   - **Application name**: `Muhammed Fasal Portfolio CMS`
   - **Homepage URL**: your admin origin, e.g. `https://muhammedfasal.com`
   - **Authorization callback URL**: must match `GITHUB_REDIRECT_URI` **exactly**,
     including scheme, host, port and path:
     - local: `http://localhost:8000/auth/github/callback`
     - production: `https://api.muhammedfasal.com/auth/github/callback`
3. Copy the **Client ID**, and generate a **Client Secret**.

The requested scope is `read:user user:email` — enough to identify the account,
no repository or organisation access. `allow_signup=false` is sent so the flow
cannot create new GitHub accounts.

## Configuration

```bash
GITHUB_CLIENT_ID=Iv1.abc123...
GITHUB_CLIENT_SECRET=           # never committed
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback
ALLOWED_GITHUB_USERNAME=Fasal17   # comma-separated for more than one admin
SESSION_SECRET=                 # python -c "import secrets; print(secrets.token_urlsafe(64))"
COOKIE_SECURE=false             # true in production (enforced)
```

Optional overrides, useful for GitHub Enterprise: `GITHUB_AUTHORIZE_URL`,
`GITHUB_TOKEN_URL`, `GITHUB_API_URL`.

### Validation enforced at startup

`Settings` refuses to boot with an insecure configuration rather than failing
later at login time:

| Condition | Applies | Behaviour |
| --- | --- | --- |
| `SESSION_SECRET` missing | production | **startup error** |
| `SESSION_SECRET` shorter than 32 characters | all | **startup error** |
| `COOKIE_SECURE=false` | production | **startup error** |
| `SESSION_COOKIE_SAMESITE=none` without `COOKIE_SECURE=true` | all | **startup error** |
| `SESSION_COOKIE_SAMESITE` not `lax`/`strict`/`none` | all | **startup error** |
| GitHub client ID/secret missing | production | **startup error** |
| `ALLOWED_GITHUB_USERNAME` empty | production | **startup error** (no default admin) |
| `API_BASE_URL` / `GITHUB_REDIRECT_URI` not https | production | **startup error** |
| `GITHUB_REDIRECT_URI` not under `API_BASE_URL` | production | **startup error** |
| `CORS_ALLOWED_ORIGINS` contains `*` | all | **startup error** |
| `CORS_ALLOWED_ORIGINS` entry is not an absolute http(s) origin | all | **startup error** |
| `CORS_ALLOWED_ORIGINS` empty, or non-https | production | **startup error** |
| `SECURE_ERRORS=false` | production | **startup error** |
| `RATE_LIMIT_ENABLED=false` | production | **startup error** |
| `DATABASE_URL` still has a placeholder password | production | **startup error** |
| `SESSION_IDLE_TTL_MINUTES` > `SESSION_TTL_MINUTES` | all | **startup error** |
| Any URL setting that is not an absolute http(s) URL | all | **startup error** |
| `SESSION_SECRET` missing in development | development | an ephemeral secret is generated (sessions do not survive a restart, which is the correct dev behaviour) |

The database URL is deliberately **not** quoted in the placeholder-password
error: deploy logs are widely readable and must not carry credentials.

`github_oauth_configured` is the single check the routes use before offering
sign-in; `GitHubOAuthClient.require_configured()` raises a clear
`GitHubAuthError` instead of handing the visitor a broken GitHub URL. When OAuth
is not configured the public portfolio still serves normally — `/health` reports
GitHub as `UNCONFIGURED` and that does not mark the service `DEGRADED`.

### API docs exposure

`DOCS_ENABLED` is the development master switch. Production additionally
requires `DOCS_ENABLED_IN_PRODUCTION=true`, because `DOCS_ENABLED` defaults to
true and interactive docs would otherwise publish the entire admin surface to
anonymous callers. With the production default, `/docs`, `/redoc` and
`/openapi.json` all return 404.

## Session design (spec §10)

| Property | Value |
| --- | --- |
| Storage | `admin_sessions` table; the raw token is **never** stored, only `session_token_hash` |
| Absolute lifetime | `SESSION_TTL_MINUTES` (default 480) |
| Idle timeout | `SESSION_IDLE_TTL_MINUTES` (default 120) |
| Cookie | `SESSION_COOKIE_NAME` (default `mf_cms_session`), **HttpOnly**, **SameSite**, `Secure` in production |
| CSRF | separate `CSRF_COOKIE_NAME` (default `mf_cms_csrf`) read by JavaScript and echoed in a header for state-changing requests |
| Recorded per session | `ip_address`, `user_agent`, `last_seen_at`, `revoked` |

Logout revokes the row rather than only clearing the cookie.

## Authorization

`is_allowed(username)` is the only gate for administrator access. It trims and
lower-cases before comparing, so `Fasal17`, `fasal17` and ` FASAL17 ` all match,
while `Fasal170` does not. The allowlist comes from configuration, never from
frontend code.

Expected API behaviour once Phase 5 lands:

| Situation | Response |
| --- | --- |
| No session | `401` |
| Authenticated GitHub account that is not on the allowlist | `403` |
| Valid session, allowed account | session issued |

## Local development

```bash
cd backend
cp .env.example .env      # fill in GITHUB_CLIENT_ID / _SECRET / SESSION_SECRET
. .venv/bin/activate
uvicorn app.main:create_app --factory --reload --host 0.0.0.0 --port 8000
```

For local testing set the callback URL to `http://localhost:8000/auth/github/callback`
and keep `COOKIE_SECURE=false` (the `Secure` flag would stop the browser sending
the cookie over plain HTTP).

## Production

Minimum production configuration:

```bash
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://<user>:<real-password>@<host>:5432/<db>
SESSION_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(64))">
COOKIE_SECURE=true
SECURE_ERRORS=true
RATE_LIMIT_ENABLED=true
API_BASE_URL=https://api.example.com
GITHUB_CLIENT_ID=<from the GitHub OAuth App>
GITHUB_CLIENT_SECRET=<from the platform secret manager>
GITHUB_REDIRECT_URI=https://api.example.com/auth/github/callback
ALLOWED_GITHUB_USERNAME=Fasal17
CORS_ALLOWED_ORIGINS=https://admin.example.com
FRONTEND_URL=https://fasalsaiko-sudo.github.io/Muhammed-Fasal/
ADMIN_URL=https://admin.example.com/admin
SESSION_COOKIE_SAMESITE=lax        # or none - see below
```

- Serve over HTTPS only; `COOKIE_SECURE=true` is enforced by validation.
- Put the client secret and session secret in the platform secret manager.
- Set `GITHUB_REDIRECT_URI` to the production callback and register the same URL
  in the GitHub app — a mismatch is the most common cause of
  `redirect_uri_mismatch`. Startup validation also requires the callback to be
  served by `API_BASE_URL`.
- `FRONTEND_URL` and `ADMIN_URL` are added to the CORS allowlist, so they must be
  real https URLs in production. Their paths are normalised away, because a
  browser `Origin` header never carries one.
- If the app runs behind a proxy, set `TRUST_PROXY_HEADERS=true` so rate limiting
  and the recorded session IP are correct. Leaving it false while directly
  exposed is the safe choice.

### Choosing SameSite

`SameSite` decides whether the browser sends the session cookie on a
cross-origin request, so it depends on how the admin is hosted:

| Deployment | `SESSION_COOKIE_SAMESITE` |
| --- | --- |
| Admin and API on the same registrable domain (`muhammedfasal.com` + `api.muhammedfasal.com`) | `lax` |
| Local development (both on `localhost:8000`) | `lax` |
| Admin on `fasalsaiko-sudo.github.io`, API on a different domain | `none` (and `COOKIE_SECURE=true`) |

`github.io` and any custom API domain have different registrable domains, so
they are **cross-site**: with `lax` the cookie is omitted from
`fetch(credentials: 'include')` and every admin call returns 401. Browsers
reject `SameSite=None` without `Secure`, so the app refuses to start with that
combination instead of logging every administrator out.

### Manual deployment verification

Automated tests cover configuration, replay, expiry, CSRF, cookie flags and
authorization. They cannot cover a real browser, a real GitHub OAuth App or a
real TLS deployment. After deploying, walk through this list by hand and record
the results:

1. `GET /health` returns `200`, `overall: ONLINE`, and GitHub as `CONFIGURED`.
2. `GET /docs` returns `404` (unless deliberately enabled in production).
3. From the deployed admin origin, in the browser console:
   `fetch('<API_BASE_URL>/api/projects', {credentials:'include'})` returns `200`
   and the response carries `Access-Control-Allow-Origin` for that exact origin
   plus `Access-Control-Allow-Credentials: true`.
4. `GET /auth/github` returns `302` to `github.com/login/oauth/authorize` with
   `client_id`, `redirect_uri` and `state` in the query string.
5. GitHub sign-in redirects back and lands on `ADMIN_URL`; the browser stores
   `mf_cms_session` (`HttpOnly`, `Secure`, expected `SameSite`) and `mf_cms_csrf`
   (readable by JavaScript, `Secure`).
6. `GET /auth/me` returns `200` with your GitHub username and role.
7. Reload the page — the session survives.
8. Replay the callback URL from the browser history: it must return `400`
   (`The sign-in request is no longer valid.`) and must not create a session.
9. `POST /auth/logout` with `X-CSRF-Token` returns `204`; afterwards
   `GET /auth/me` returns `401` even if the old cookie is replayed.
10. `POST /auth/logout` **without** the CSRF header returns `403`.
11. Signing in with a GitHub account that is not on the allowlist returns `403`
    and creates no `users` row.
12. An unauthenticated request to any admin route returns `401`.

## Credential rotation

- **GitHub client secret**: generate a new secret in the GitHub app, update the
  platform secret, redeploy, then delete the old one. Existing sessions remain
  valid; users re-authenticate only when their session expires.
- **Session secret**: rotating it invalidates every active session immediately —
  do it if the secret is ever exposed.

## Security notes

- The client secret is sent only in the server-to-server token exchange. A test
  asserts it never appears in the authorize URL, in an error message, or in logs.
- Access tokens are not logged (asserted by test) and are not persisted.
- `exchange_code` and `fetch_user` convert transport failures, non-200 statuses,
  GitHub error bodies and malformed (non-JSON) responses into `GitHubAuthError`
  with a user-safe message — no stack trace, no credentials.
- `follow_redirects=False` on the HTTP client, so a redirect cannot smuggle the
  token to another host.

## Test status

255 tests in the backend suite, run against SQLite and against the PGlite
PostgreSQL-compatible harness.

```bash
cd backend && . .venv/bin/activate

# SQLite
python -m pytest

# PostgreSQL-compatible (PGlite harness), after `alembic upgrade head`
export DATABASE_URL="postgresql+psycopg://<user>:<password>@127.0.0.1:5433/portfolio_cms"
export SKIP_SCHEMA_SETUP=1 DATABASE_POOL_CLASS=static
python -m pytest
```

`DATABASE_POOL_CLASS=static` is required against the PGlite harness and must not
be confused with native PostgreSQL testing. PGlite is the real PostgreSQL engine
compiled to WASM, but it is single-process and serves **one connection at a
time**; it also closes connections that arrive during rapid reconnect churn
(measured: 17 failures in 150 sequential connect/query/close cycles, independent
of application code). The default `auto` setting uses `NullPool` while testing —
one fresh connection per session — which that harness cannot sustain.

`backend/tests/test_github_oauth_service.py` — 24 tests against
`httpx.MockTransport`, covering: authorize URL contents and secret absence;
token exchange success, HTTP error, error-in-200-body, non-JSON body,
unreachable host; user fetch success, 401, unreachable; identity mapping and
incomplete-profile rejection; the allowlist gate; secret/token non-logging; and
the client injection seam.

`backend/tests/test_auth.py` — 58 tests: single-use state (including replay with
the binding cookie re-sent, cross-browser state, expiry, and atomic consumption
under concurrent callers), absolute and idle session expiry, revoked sessions,
the session cap, cookie flags, CSRF binding and enforcement, the allowlist and
role gates, and token/secret non-logging. The single-use guard is
mutation-verified: removing `used_at IS NULL` from the conditional UPDATE fails
four of these tests.

`backend/tests/test_deployment_config.py` — 55 tests for deployment readiness:
missing and incomplete OAuth configuration, invalid CORS configuration,
wildcard rejection, origin normalisation, `SameSite`/`Secure` behaviour, callback
URL validation, the full production-versus-development policy, docs exposure,
and the absence of secrets from health responses, error responses, and startup
error messages.

**Not verified:** any real round trip with `github.com`, and any live deployment
(real TLS, real browser cookies, real CORS preflight from the hosted admin). Both
need credentials and a deployed environment; see the manual checklist above.
