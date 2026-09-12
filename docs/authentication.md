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

| Condition | Behaviour |
| --- | --- |
| `SESSION_SECRET` missing in production | **startup error** |
| `SESSION_SECRET` shorter than 32 characters | **startup error** |
| `COOKIE_SECURE=false` in production | **startup error** |
| GitHub client ID/secret missing in production | **startup error** |
| `SESSION_SECRET` missing in development | an ephemeral secret is generated (sessions do not survive a restart, which is the correct dev behaviour) |

`github_oauth_configured` is the single check the routes use before offering
sign-in; `GitHubOAuthClient.require_configured()` raises a clear
`GitHubAuthError` instead of handing the visitor a broken GitHub URL.

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

- Serve over HTTPS only; `COOKIE_SECURE=true` is enforced by validation.
- Put the client secret and session secret in the platform secret manager.
- Set `GITHUB_REDIRECT_URI` to the production callback and register the same URL
  in the GitHub app — a mismatch is the most common cause of
  `redirect_uri_mismatch`.
- If the app runs behind a proxy, set `TRUST_PROXY_HEADERS=true` so rate limiting
  and the recorded session IP are correct. Leaving it false while directly
  exposed is the safe choice.

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

`backend/tests/test_github_oauth_service.py` — 24 tests against
`httpx.MockTransport`, covering: authorize URL contents and secret absence;
token exchange success, HTTP error, error-in-200-body, non-JSON body,
unreachable host; user fetch success, 401, unreachable; identity mapping and
incomplete-profile rejection; the allowlist gate; secret/token non-logging; and
the client injection seam.

**Not verified:** any real round trip with `github.com`. That needs a real OAuth
application and is the first item once credentials are available.
