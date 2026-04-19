# Phase 22c: oauth-google — Research

**Researched:** 2026-04-19
**Domain:** OAuth2 (Google OIDC + GitHub non-OIDC) + server-table sessions + FastAPI/Starlette middleware + Next.js 16 edge gating + Alembic destructive migration + asyncpg-per-request lookup
**Confidence:** HIGH on stack versions + authlib flow; MEDIUM on two items flagged below (test library mismatch, Next.js 16 filename migration)

## Summary

This phase welds Google + GitHub OAuth onto an existing FastAPI/asyncpg/Alembic substrate whose auth seam was deliberately left as a single `ANONYMOUS_USER_ID` constant imported across 5 files (idempotency middleware + 4 route modules). The substrate is well-shaped for the welding: a thin `request.state.*` middleware pattern already exists (correlation_id), a Stripe-shape error envelope with `UNAUTHORIZED` code already exists, Pydantic settings pattern is established, env-template is already seeded with the OAuth vars, and the frontend already has `credentials: "include"` + `SessionUser` type + cookie-aware `fetch` wrapper.

The research surfaced **two concrete blockers** that the planner MUST resolve before writing tasks, and **one documentation error** in an existing file that a task must fix:

1. **`responses` library does NOT intercept httpx [VERIFIED: responses README + respx docs]** — authlib uses httpx under the hood for its Starlette integration, so the CONTEXT D-22c-TEST-01 prescription to use `responses` is technically incorrect. The correct tool is **`respx`** (same maintainer ecosystem as httpx; purpose-built for httpx mocking). This is a one-line substitution in the test plan.
2. **Next.js 16.2 renamed `middleware.ts` → `proxy.ts` [VERIFIED: nextjs.org/blog/next-16]** — `middleware.ts` still works but emits a deprecation warning. The existing `frontend/middleware.ts` contains an INCORRECT comment asserting the rename didn't happen. CONTEXT D-22c-FE-01 says "new file `frontend/middleware.ts`" but the file ALREADY EXISTS. The planner must decide: (a) modify existing `middleware.ts` (deprecated name, keeps working), or (b) rename to `proxy.ts` + rename the export. Recommend (b) to match Next.js 16 convention and clear the wrong note.
3. **Authlib REQUIRES Starlette's `SessionMiddleware` [VERIFIED: docs.authlib.org/en/latest/client/starlette.html]** — authlib stores the CSRF state token inside `request.session` (not a separate cookie). The CONTEXT D-22c-OAUTH-05 description ("signed cookie `ap_oauth_state`") aligns with this when you realize that Starlette's SessionMiddleware IS the mechanism — its default cookie name is `"session"` but can be configured to `"ap_oauth_state"`. This means the middleware stack gains ONE more entry (Starlette `SessionMiddleware` before authlib routes can run), and a new `AP_OAUTH_STATE_SECRET` env var is required for session signing.

**Primary recommendation:** Implement in 3 waves — (Wave A) Alembic 005 + 006 + OAuth deps + config + Starlette SessionMiddleware wiring; (Wave B) auth routes + session middleware + require_user dep + ANONYMOUS_USER_ID cleanup across 5 files; (Wave C) frontend login page + dashboard layout useUser hook + navbar logout + proxy.ts gate + next.config.mjs redirects. respx-based integration test lands with Wave B.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Migrations & Users Schema:**
- **D-22c-MIG-01** — `display_name` reused for Google/GitHub `name`. No new `users.name` column. OAuth callbacks write provider's name into `display_name`. Frontend `SessionUser.display_name` stays unchanged.
- **D-22c-MIG-02** — Alembic 005 = sessions table + users columns in ONE atomic migration. Columns added: `users.sub TEXT`, `users.avatar_url TEXT`, `users.last_login_at TIMESTAMPTZ`. Constraint: `UNIQUE (provider, sub)`.
- **D-22c-MIG-03** — Alembic 006 = full-DB data purge. TRUNCATE on `agent_events`, `runs`, `agent_containers`, `agent_instances`, `idempotency_keys`, `rate_limit_counters`, `sessions`, `users`. Schema + `alembic_version` preserved. Irreversible downgrade documented in docstring.
- **D-22c-MIG-04** — Sessions table indexing: PK only + btree on `user_id`. No partial index in v1.
- **D-22c-MIG-05** — `sessions.last_seen_at` throttled updates (60s granularity). SessionMiddleware caches `last_seen_at`; UPDATE fires only when `(now - last_seen_at) > 60s`.
- **D-22c-MIG-06** — `ANONYMOUS_USER_ID` constant DELETED from `constants.py` after migration 006. `AP_SYSADMIN_TOKEN_ENV` stays.

**Auth Middleware & Routes:**
- **D-22c-AUTH-01** — SessionMiddleware placement: `CorrelationId → AccessLog → Session → RateLimit → Idempotency → routers`. Session resolves `user_id` BEFORE rate_limit + idempotency.
- **D-22c-AUTH-02** — `request.state.user_id: UUID | None`. Starlette-idiomatic. Mirrors `request.state.correlation_id`.
- **D-22c-AUTH-03** — `require_user` FastAPI dependency for protected routes. Applied to: `/v1/runs`, `/v1/agents`, `/v1/agents/:id/*`, `/v1/users/me`, `/v1/auth/logout`. Public: `/healthz`, `/readyz`, `/v1/recipes`, `/v1/schemas`, `/v1/lint`, `/v1/auth/{google,github}`, `/v1/auth/{google,github}/callback`.
- **D-22c-AUTH-04** — Complete ANONYMOUS_USER_ID cleanup across 5 files (runs.py, agents.py, agent_lifecycle.py, agent_events.py, middleware/idempotency.py).

**Frontend Auth Gating & Error UX:**
- **D-22c-FE-01** — Next.js `middleware.ts` gates `/dashboard/:path*`. Reads `ap_session` cookie PRESENCE (not validity). Absent → 307 redirect to `/login`.
- **D-22c-FE-02** — Eager dashboard render; navbar skeleton until userinfo resolves. No Suspense boundary; no full-page spinner.
- **D-22c-FE-03** — OAuth error paths → `/login?error=<code>` + toast. Backend catches `?error=access_denied`, state-mismatch (400), token-exchange 5xx, redirects to `/login?error=access_denied|state_mismatch|oauth_failed`.
- **D-22c-FE-04** — Callback always redirects to `/dashboard`. No `?next=` deep-link preservation in v1.

**OAuth Flow Specifics:**
- **D-22c-OAUTH-01** — Both Google AND GitHub ship in 22c. Four provider routes + one shared logout. `users.UNIQUE(provider, sub)` covers both.
- **D-22c-OAUTH-02** — Google scope: `openid email profile`. No `access_type=offline`. Identity-only.
- **D-22c-OAUTH-03** — GitHub scope: `read:user user:email`. Callback fetches `/user` + `/user/emails` when primary is private.
- **D-22c-OAUTH-04** — Cookie policy: `HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000` always. `Secure` only when `AP_ENV=prod`.
- **D-22c-OAUTH-05** — State token: per-request random nonce in short-lived signed cookie. `Set-Cookie: ap_oauth_state=<nonce>; HttpOnly; SameSite=Lax; Max-Age=600`. authlib's built-in state management.

**Dead-Theater Cleanup:**
- **D-22c-UI-01** — `/login` keeps BOTH Google + GitHub buttons enabled. Email/password form retained but disabled with copy "Use Google or GitHub for now".
- **D-22c-UI-02** — `/signup` server-side redirects to `/login` via `next.config.mjs::redirects()`.
- **D-22c-UI-03** — `/forgot-password` server-side redirects to `/login`. "Forgot password?" link removed.
- **D-22c-UI-04** — Navbar "Log out" becomes a real button with `onClick={async () => { await apiPost('/api/v1/auth/logout', {}); router.push('/login'); }}`.

**CI Test Strategy:**
- **D-22c-TEST-01** — Integration tests via real authlib + `responses` library. **RESEARCH FLAG: wrong library — must be `respx` (httpx mocker), not `responses` (requests mocker). See Section "Gray-Area Seams Resolved".**
- **D-22c-TEST-02** — One manual smoke per release.

### Claude's Discretion

- Sessions table partial-index shape (default: PK + btree(user_id) only)
- Error code enum values for `/login?error=` (suggested: `access_denied`, `state_mismatch`, `oauth_failed`)
- Tooltip copy for disabled password form
- Toast library choice (**VERIFIED: `sonner` ^1.7.1 already in package.json, USE IT**)
- `/signup` and `/forgot-password` redirect mechanism (prefer config-level via `next.config.mjs::redirects()`)
- Exact shape of `ap_oauth_state` cookie (authlib's default is fine)
- alembic 006 purge mechanism: `TRUNCATE … CASCADE` vs sequential `DELETE` (TRUNCATE with CASCADE preferred)
- GitHub `/user/emails` null-primary fallback (defensive: use `/user.email` if present, else 400 `oauth_failed`)
- authlib's `StarletteOAuth2App` config pattern — follow docs literally

### Deferred Ideas (OUT OF SCOPE)

- Refresh-token storage + rotation (revisit when feature needs Google Calendar / GitHub repo access)
- Deep-link preservation via `?next=` param
- PKCE for OAuth
- Dev TLS via mkcert/Caddy
- Admin "list my sessions" UI
- Multi-account linking (same email Google AND GitHub)
- Magic-link password reset
- Dedicated /signup onboarding flow
- Session expiry UX toast
- PGBouncer / pool tuning
- MTProto user-impersonation harness (from 22b)

### SPEC Amendments (from CONTEXT.md — override SPEC.md)

- **AMD-01** — GitHub OAuth IN SCOPE (SPEC said deferred to 22c.1; CONTEXT moves it into 22c)
- **AMD-02** — Refresh-token storage DROPPED. No `access_type=offline`, no encrypted refresh_token column. Does NOT use `crypto/age_cipher.py`.
- **AMD-03** — ANONYMOUS users row DELETED in migration 006.
- **AMD-04** — Migration 006 TRUNCATEs ALL data-bearing tables, not just `agent_instances`.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| R1 | `GET /v1/auth/google` → 302 to Google authorize | authlib `oauth.google.authorize_redirect(request, redirect_uri)` — sets state in request.session via SessionMiddleware |
| R2 | `GET /v1/auth/google/callback` exchanges code → user → session | authlib `oauth.google.authorize_access_token(request)` — validates state from request.session; token.get('userinfo') returns OIDC claims |
| R3 | Session middleware resolves user_id from cookie on every request | Custom ASGI middleware mirroring `correlation_id.py` shape; reads `ap_session` cookie, PG SELECT, sets `request.state.user_id` |
| R4 | `GET /v1/users/me` returns authenticated user | FastAPI route with `require_user` dep; SELECT from users by `request.state.user_id`; returns `SessionUser` shape |
| R5 | `POST /v1/auth/logout` invalidates session server-side | FastAPI route; DELETE from sessions WHERE id=cookie; `Set-Cookie: ap_session=; Max-Age=0`; 204 |
| R6 | Frontend login button starts real OAuth flow | `<button onClick={() => { window.location.href = '/api/v1/auth/google' }}>` — top-level navigation required for OAuth redirects |
| R7 | Frontend layout shows real user (replaces "Alex Chen") | `apiGet<SessionUser>('/api/v1/users/me')` in useEffect; navbar renders display_name + avatar_url |
| R8 | Existing ANONYMOUS-keyed agents purged | Alembic 006: TRUNCATE CASCADE on 8 tables; irreversible downgrade() raises |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| OAuth provider redirect (authorize) | API / Backend | — | Only backend has client_secret; browser does top-level nav to backend URL |
| OAuth provider callback (token exchange + userinfo) | API / Backend | — | client_secret + state-cookie validation are server-only |
| Session cookie minting | API / Backend | — | Opaque session_id is server-generated; PG row is the source of truth |
| Per-request user_id resolution | API / Backend (middleware) | — | The API IS the authoritative user gate |
| Dashboard auth gate (UX-only, no security) | Frontend Server (proxy.ts) | — | Pre-render redirect to avoid auth-flash; validity lives on backend |
| User profile display | Browser | Frontend Server | `apiGet('/api/v1/users/me')` fetched client-side for freshness |
| Sign-out action | Browser → API | — | POST `/v1/auth/logout` invalidates PG row, response clears cookie, router.push('/login') |
| Dead-route redirects (/signup, /forgot-password) | Frontend Server | — | `next.config.mjs::redirects()` — config-level, pre-render, zero client code |

## Standard Stack

### Core (Python API)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `authlib` | **1.6.11** [VERIFIED: pypi.org/project/Authlib 2026-04-16] | OAuth2/OIDC client | Ships StarletteOAuth2App with httpx backend; handles state mgmt, OIDC id_token validation, multi-provider registry |
| `itsdangerous` | **2.2.0** [VERIFIED: pip show — already installed as transitive dep] | Cookie signing for Starlette SessionMiddleware | Required by `starlette.middleware.sessions.SessionMiddleware` |
| `httpx` | (transitive via authlib) | HTTP client for OAuth outbound calls | authlib's Starlette integration uses httpx.AsyncOAuth2Client under the hood |

**Starlette's `SessionMiddleware` is REQUIRED by authlib** [VERIFIED: docs.authlib.org/en/latest/client/starlette.html, fastapi-google-login demo] — this is NOT our custom SessionMiddleware; it's Starlette's built-in signed-cookie session. It stores the CSRF state token (authlib's `_oauth_state` internal key) across the authorize → callback round-trip. Both middlewares coexist.

### Supporting (Python)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `starlette.middleware.sessions.SessionMiddleware` | (bundled with FastAPI/Starlette) | authlib's state storage | Add BEFORE our custom SessionMiddleware in the stack |
| `authlib.integrations.starlette_client.OAuth, OAuthError` | 1.6.11 | Multi-provider OAuth registry | Register both google + github clients at module import |
| `authlib.integrations.starlette_client.StarletteOAuth2App` | 1.6.11 | Per-provider client type (indirect; accessed via `oauth.google` / `oauth.github`) | — |

### Test-tier Additions
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `respx` | ^0.21 [CITED: lundberg.github.io/respx] | httpx mocking in tests | **Replaces CONTEXT D-22c-TEST-01's `responses`** — `responses` only intercepts `requests`, not httpx |

**Installation:**
```bash
# Add to api_server/pyproject.toml dependencies:
#   "authlib>=1.6.11,<1.7",
#   "itsdangerous>=2.2.0,<3",
# Add to api_server/pyproject.toml [project.optional-dependencies].dev:
#   "respx>=0.21,<0.22",
pip install -e ".[dev]"
```

**Version verification performed:** `pip show itsdangerous` showed 2.2.0 already installed (transitive). `authlib` and `respx` not currently installed — must be added explicitly.

### Core (Next.js Frontend — no new deps needed)
| Library | Version (package.json) | Purpose | Why |
|---------|---------|---------|-----|
| `sonner` | ^1.7.1 (already present) | Toast library for `/login?error=` path (D-22c-FE-03) | Already in deps; zero new dep; matches shadcn-style |
| (No OAuth deps on frontend) | — | — | Auth flow is fully server-side; frontend just hits `/api/v1/auth/google` via `window.location.href` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| authlib | `fastapi-sso`, `python-social-auth`, hand-roll with `httpx` | authlib is the most battle-tested + matches CONTEXT lock. Hand-roll is ~300 lines of CSRF + JWK discovery; authlib handles both. |
| Starlette `SessionMiddleware` | Store state in our own PG table | authlib expects `request.session` to be dict-like; building a PG-backed session just for OAuth state is overkill for a 10-minute nonce |
| `respx` | `pytest-httpx` | Both work with httpx. `respx` has decorator + context-manager modes; `pytest-httpx` is fixture-first. Either is fine; respx is more popular. |
| server-table sessions | JWT bearer tokens | Locked by SPEC. JWT revocation requires a PG lookup anyway, so the ergonomic gain disappears. |

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│  BROWSER                                                                  │
│                                                                           │
│   /login (React)                        /dashboard/* (React)             │
│     │                                     │                               │
│     │ click "Continue with Google"        │ eager render                 │
│     │ window.location.href = /api/v1/auth/google                         │
│     │                                     │ useEffect → apiGet('/api/v1/users/me')
│     ▼                                     ▼                               │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │  proxy.ts (frontend edge gate — Next 16 rename of middleware)│       │
│  │  matcher: /dashboard/:path*                                   │       │
│  │  if (!request.cookies.get('ap_session')) redirect /login     │       │
│  └────────────────┬─────────────────────────────────────────────┘       │
└───────────────────┼──────────────────────────────────────────────────────┘
                    │  (same-origin via next.config.mjs rewrites)
                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FASTAPI (api_server)  —  middleware stack, request-in top→bottom       │
│                                                                           │
│  CorrelationIdMiddleware    (mints X-Request-Id, binds contextvar)       │
│  AccessLogMiddleware         (structured access log, allowlist headers)  │
│  Starlette SessionMiddleware ← NEW. Signed cookie for authlib state.    │
│  (our) SessionMiddleware    ← NEW. Reads ap_session, PG lookup,         │
│                                sets request.state.user_id : UUID|None    │
│  RateLimitMiddleware        (already keyed on subject — now real user)  │
│  IdempotencyMiddleware      (already keyed on user_id — now real user)  │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ PUBLIC routes (no require_user):                             │        │
│  │   GET  /v1/auth/{google,github}        → oauth.authorize_redirect     │
│  │   GET  /v1/auth/{google,github}/callback → authorize_access_token    │
│  │        - validates state from request.session                │        │
│  │        - google: token.get('userinfo') (OIDC)                │        │
│  │        - github: oauth.github.get('user', token) +          │        │
│  │                  if email null: oauth.github.get('user/emails') │    │
│  │        - upsert users by (provider, sub)                     │        │
│  │        - INSERT sessions row, Set-Cookie ap_session         │        │
│  │        - 302 → /dashboard                                    │        │
│  │   GET  /healthz, /readyz, /v1/recipes, /v1/schemas, /v1/lint│        │
│  │                                                              │        │
│  │ PROTECTED routes (require_user dep):                         │        │
│  │   GET  /v1/users/me           → SELECT users WHERE id = user_id       │
│  │   POST /v1/auth/logout        → DELETE sessions WHERE id=cookie      │
│  │   GET  /v1/agents                                            │        │
│  │   POST /v1/runs                                              │        │
│  │   POST /v1/agents/:id/start   (etc. — 4 lifecycle endpoints) │        │
│  │   GET  /v1/agents/:id/events  (+ sysadmin bypass unchanged)  │        │
│  └─────────────────────────────────────────────────────────────┘        │
└──────────────┬─────────────────────────────────────────┬─────────────────┘
               │                                         │
               ▼                                         ▼
      ┌────────────────────┐                    ┌────────────────────┐
      │  Google / GitHub   │                    │  Postgres          │
      │  (via httpx through│                    │   users            │
      │  authlib internals)│                    │   sessions (NEW)   │
      │                    │                    │   agent_instances  │
      │  google.token      │                    │   agent_containers │
      │  google.userinfo   │                    │   runs             │
      │  github.token      │                    │   agent_events     │
      │  github./user      │                    │   idempotency_keys │
      │  github./user/emails│                   │   rate_limit_counters│
      └────────────────────┘                    └────────────────────┘
```

### Recommended Project Structure (additions only)

```
api_server/src/api_server/
├── config.py                          # ADD: AP_OAUTH_* fields, AP_OAUTH_STATE_SECRET
├── constants.py                       # DELETE: ANONYMOUS_USER_ID (keep AP_SYSADMIN_TOKEN_ENV)
├── main.py                            # ADD: 2 middlewares + 1 router include
├── middleware/
│   ├── correlation_id.py              # unchanged — template pattern source
│   └── session.py                     # NEW: custom SessionMiddleware (request.state.user_id)
├── routes/
│   ├── auth.py                        # NEW: 5 endpoints (google, google/cb, github, github/cb, logout)
│   ├── users.py                       # NEW: /v1/users/me
│   ├── runs.py                        # MODIFY: require_user, drop ANONYMOUS
│   ├── agents.py                      # MODIFY: require_user, drop ANONYMOUS
│   ├── agent_lifecycle.py             # MODIFY: require_user (except sysadmin bypass), drop ANONYMOUS
│   └── agent_events.py                # MODIFY: require_user (except sysadmin bypass), drop ANONYMOUS
├── services/
│   ├── oauth.py                       # NEW: OAuth() singleton + register(google, github); upsert_user(); mint_session()
│   └── session_store.py               # NEW: session CRUD + throttled last_seen_at update
├── dependencies/
│   └── auth.py                        # NEW: require_user dep → raises HTTPException(401) with Stripe envelope
└── alembic/versions/
    ├── 005_sessions_and_users_cols.py # NEW: additive — sessions + users.sub/avatar_url/last_login_at + UNIQUE(provider,sub)
    └── 006_purge_anonymous.py         # NEW: destructive — TRUNCATE 8 tables CASCADE

frontend/
├── proxy.ts                           # NEW (replaces middleware.ts per Next 16) — /dashboard gate
├── middleware.ts                      # DELETE (rename to proxy.ts; Next 16 deprecation)
├── app/
│   ├── login/page.tsx                 # REWRITE: real buttons, disabled password, ?error toast
│   ├── signup/page.tsx                # UNCHANGED (redirect handles it)
│   ├── forgot-password/page.tsx       # UNCHANGED (redirect handles it)
│   └── dashboard/layout.tsx           # REWRITE: useUser() hook replaces "Alex Chen"
├── components/
│   └── navbar.tsx                     # MODIFY: <Link href="/login"> Log out → real <button>
├── hooks/
│   └── use-user.ts                    # NEW: apiGet('/api/v1/users/me') + 401 redirect
├── lib/
│   └── api.ts                         # unchanged — SessionUser type already correct
└── next.config.mjs                    # MODIFY: add async redirects() with /signup + /forgot-password
```

### Pattern 1: authlib Multi-Provider Registration

**What:** Register Google (OIDC via discovery URL) + GitHub (non-OIDC, manual endpoints) on a single `OAuth()` registry.

**When to use:** Both providers in one codebase share the same OAuth() instance.

**Example:**
```python
# api_server/src/api_server/services/oauth.py
# Source: docs.authlib.org/en/latest/client/starlette.html + authlib/demo-oauth-client/fastapi-google-login
from authlib.integrations.starlette_client import OAuth, OAuthError

_oauth: OAuth | None = None

def get_oauth(settings) -> OAuth:
    global _oauth
    if _oauth is None:
        _oauth = OAuth()
        # Google — OIDC discovery URL auto-populates endpoints + JWK set for id_token validation
        _oauth.register(
            name="google",
            client_id=settings.oauth_google_client_id,
            client_secret=settings.oauth_google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        # GitHub — non-OIDC; must hand-specify endpoints + api_base_url
        _oauth.register(
            name="github",
            client_id=settings.oauth_github_client_id,
            client_secret=settings.oauth_github_client_secret,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )
    return _oauth
```

### Pattern 2: authlib authorize_redirect + authorize_access_token (Google OIDC path)

```python
# api_server/src/api_server/routes/auth.py
@router.get("/auth/google")
async def google_login(request: Request):
    oauth = get_oauth(request.app.state.settings)
    redirect_uri = request.app.state.settings.oauth_google_redirect_uri
    return await oauth.google.authorize_redirect(request, redirect_uri)
    # ^ implicitly writes state token to request.session["_state_google_..."]
    # ^ returns 302 to https://accounts.google.com/o/oauth2/v2/auth?...&state=...

@router.get("/auth/google/callback")
async def google_callback(request: Request):
    oauth = get_oauth(request.app.state.settings)
    try:
        token = await oauth.google.authorize_access_token(request)
        # ^ validates state against request.session; raises OAuthError on mismatch
        # ^ hits https://oauth2.googleapis.com/token + validates id_token against JWK set
    except OAuthError as e:
        return RedirectResponse(f"/login?error=oauth_failed", status_code=302)
    userinfo = token.get("userinfo") or await oauth.google.userinfo(token=token)
    # userinfo: {sub, email, email_verified, name, picture, given_name, family_name, locale}
    user_id = await upsert_user(
        conn, provider="google", sub=userinfo["sub"],
        email=userinfo["email"], display_name=userinfo.get("name") or userinfo["email"],
        avatar_url=userinfo.get("picture"),
    )
    session_id = await mint_session(conn, user_id, request)
    resp = RedirectResponse("/dashboard", status_code=302)
    _set_session_cookie(resp, session_id, settings)
    return resp
```

### Pattern 3: GitHub non-OIDC flow with /user/emails fallback

```python
# api_server/src/api_server/routes/auth.py
@router.get("/auth/github/callback")
async def github_callback(request: Request):
    oauth = get_oauth(request.app.state.settings)
    try:
        token = await oauth.github.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse("/login?error=oauth_failed", status_code=302)

    # Fetch /user (non-OIDC — no userinfo in the token)
    resp = await oauth.github.get("user", token=token)
    profile = resp.json()
    # profile: {id (int), login, name, email (nullable!), avatar_url, ...}

    email = profile.get("email")
    if not email:
        # Fallback: /user/emails returns [{email, primary, verified, visibility}]
        # Needs scope 'user:email' which D-22c-OAUTH-03 provisions.
        emails_resp = await oauth.github.get("user/emails", token=token)
        emails = emails_resp.json()
        primary_verified = next(
            (e["email"] for e in emails if e.get("primary") and e.get("verified")),
            None,
        )
        email = primary_verified
    if not email:
        # Defensive fallback per Claude's Discretion D-22c-OAUTH-03.
        return RedirectResponse("/login?error=oauth_failed", status_code=302)

    user_id = await upsert_user(
        conn, provider="github", sub=str(profile["id"]),
        email=email,
        display_name=profile.get("name") or profile["login"],
        avatar_url=profile.get("avatar_url"),
    )
    # ... same session mint + cookie + redirect as Google path
```

**Source:** `oauth.github.get("user", token=token)` pattern confirmed in authlib loginpass repo [CITED: github.com/authlib/loginpass]. `/user/emails` payload shape [CITED: docs.github.com/en/rest/users/emails].

### Pattern 4: Custom SessionMiddleware (request.state.user_id resolution)

```python
# api_server/src/api_server/middleware/session.py
# Mirrors the correlation_id.py re-export shape but with a real body.
# NOT Starlette's SessionMiddleware — that one is bundled from starlette.middleware.sessions.
from __future__ import annotations
import logging
import time
from uuid import UUID
from starlette.types import ASGIApp, Receive, Scope, Send

_log = logging.getLogger("api_server.session")
SESSION_COOKIE_NAME = "ap_session"

class SessionMiddleware:
    """Resolves `request.state.user_id` from the `ap_session` cookie.

    - No cookie → request.state.user_id = None (anonymous; protected routes 401 via require_user)
    - Cookie present, session valid → request.state.user_id = <UUID>
    - Cookie present, session expired/revoked → request.state.user_id = None
    - Cookie present, PG outage → request.state.user_id = None + log (fail-closed on unknowns)

    Also performs THROTTLED last_seen_at update (D-22c-MIG-05: 60s granularity).
    Cache lives in app.state.session_last_seen (dict[session_id, float_monotonic]).
    """
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send); return
        session_id = self._extract_cookie(scope, SESSION_COOKIE_NAME)
        user_id: UUID | None = None
        if session_id:
            app = scope["app"]
            try:
                async with app.state.db.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT user_id, last_seen_at FROM sessions "
                        "WHERE id = $1 AND revoked_at IS NULL AND expires_at > NOW()",
                        session_id,
                    )
                if row:
                    user_id = row["user_id"]
                    await self._maybe_touch_last_seen(app, conn, session_id, row["last_seen_at"])
            except Exception:
                _log.exception("session resolution failed; treating as anonymous")
        # Starlette pattern for "inject into downstream request.state":
        # The downstream layers read from scope['state'] which Starlette wires to request.state.
        scope.setdefault("state", {})["user_id"] = user_id
        await self.app(scope, receive, send)

    @staticmethod
    def _extract_cookie(scope: Scope, name: str) -> str | None:
        for h_name, h_val in scope.get("headers", []):
            if h_name == b"cookie":
                # Minimal cookie parser — avoid importing http.cookies for the hot path.
                for piece in h_val.decode("latin-1", errors="ignore").split(";"):
                    k, _, v = piece.strip().partition("=")
                    if k == name and v:
                        return v
        return None
    # (_maybe_touch_last_seen implementation: check app.state.session_last_seen, compare,
    #  UPDATE sessions SET last_seen_at=NOW() WHERE id=$1 only if stale >60s)
```

**Key insight on `scope["state"]`:** Starlette's `Request` exposes `request.state` as a live view over `scope["state"]` when the route handler runs. Writing to `scope["state"]` before calling the downstream app is the canonical way for ASGI middleware to seed `request.state.X` [VERIFIED: starlette source + asgi-correlation-id pattern already used here].

### Pattern 5: require_user FastAPI Dependency

```python
# api_server/src/api_server/dependencies/auth.py
from uuid import UUID
from fastapi import HTTPException, Request
from ..models.errors import ErrorCode, make_error_envelope

async def require_user(request: Request) -> UUID:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail=make_error_envelope(
                ErrorCode.UNAUTHORIZED,
                "authentication required",
                param="ap_session",
            ),
        )
    return user_id

# Usage in routes:
from fastapi import Depends
@router.get("/users/me")
async def get_me(request: Request, user_id: UUID = Depends(require_user)):
    async with request.app.state.db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, display_name, avatar_url, provider, created_at "
            "FROM users WHERE id = $1", user_id,
        )
    return dict(row)
```

**Caveat:** `HTTPException` + FastAPI's default handler returns `{"detail": <envelope-dict>}` — which wraps our envelope one level too deep. The correct approach: return a `JSONResponse` directly from the dep (impossible — deps must raise or return a value), OR register a global exception handler for `HTTPException` that unwraps `detail` when it's already an envelope dict. Most Stripe-shape codebases install such a handler. **Plan-level decision: install `app.add_exception_handler(HTTPException, ...)` OR use the existing `_err()` helper pattern and skip require_user in favor of inline checks.** [VERIFIED: existing agent_events.py already uses the `_err()` inline pattern — this codebase prefers inline over exception-based]. Recommendation: **inline auth check via `request.state.user_id` directly + `_err()` for 401 — matches codebase muscle memory.** require_user can still be a thin helper that returns a tuple `(user_id, None) | (None, JSONResponse)`.

### Pattern 6: Alembic Destructive Migration (006)

```python
# api_server/alembic/versions/006_purge_anonymous.py
"""006_purge_anonymous — IRREVERSIBLE data purge.

Phase 22c AMD-04: all current DB data is dev mock from Phase 19/22 execution.
Zero real customer data exists. This migration TRUNCATEs every data-bearing
table so OAuth users start with a clean slate.

PRESERVED:
  - Schema (all tables, columns, indexes, FKs stay)
  - alembic_version table (this very migration's row lands here on upgrade)

DESTROYED (CASCADE order not strictly needed with TRUNCATE … CASCADE, but
document the FK graph for the reader):
  - agent_events → FK agent_containers (ON DELETE CASCADE)
  - runs → FK agent_instances
  - agent_containers → FK agent_instances + users
  - agent_instances → FK users (UNIQUE user_id, recipe_name, model)
  - idempotency_keys → FK users + runs
  - rate_limit_counters (no FK)
  - sessions → FK users (added in 005)
  - users (includes ANONYMOUS row; post-AMD-03)

IRREVERSIBLE: downgrade() raises NotImplementedError. Restore from backup
if needed. (Dev/mock-only data; no backup strategy.)

Revision ID: 006_purge_anonymous
Revises: 005_sessions_and_users_cols
Create Date: 2026-04-19
"""
from alembic import op

revision = "006_purge_anonymous"
down_revision = "005_sessions_and_users_cols"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # TRUNCATE … CASCADE is transactional + fast. One statement covers the
    # full dependency graph because every data table's FKs either point
    # into this set or aren't enforced (rate_limit_counters).
    op.execute(
        "TRUNCATE TABLE "
        "agent_events, runs, agent_containers, agent_instances, "
        "idempotency_keys, rate_limit_counters, sessions, users "
        "CASCADE"
    )

def downgrade() -> None:
    raise NotImplementedError(
        "006_purge_anonymous is irreversible. "
        "Data was dev-mock only; restore from PG dump if truly needed."
    )
```

**Source on idiom:** Alembic supports arbitrary SQL via `op.execute()` and raising in `downgrade()` is the conventional marker for destructive migrations [CITED: alembic.sqlalchemy.org/en/latest/ops.html + cookbook]. No dedicated "mark irreversible" flag exists.

### Pattern 7: Next.js 16 proxy.ts (cookie-presence gate)

```typescript
// frontend/proxy.ts   (renamed from middleware.ts per Next 16)
// Source: nextjs.org/docs/app/api-reference/file-conventions/proxy
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export default function proxy(request: NextRequest) {
  const session = request.cookies.get("ap_session");
  if (!session) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl, 307);
  }
  return NextResponse.next();
}

export const config = {
  // Matches ONLY dashboard subtree. Other routes (landing, /login, /api/*) pass through.
  matcher: ["/dashboard/:path*"],
};
```

**Caveat:** The existing `frontend/middleware.ts` has a broader matcher `["/((?!api|_next/static|_next/image|favicon.ico).*)"]` that runs on ALL routes and sets `x-ap-has-session`. The new `proxy.ts` either replaces it entirely OR both coexist during migration. Recommend: **replace `middleware.ts` with `proxy.ts` in ONE task** — the old broader matcher did no real work and the `x-ap-has-session` header has no downstream reader.

### Pattern 8: next.config.mjs redirects() for dead theater

```javascript
// frontend/next.config.mjs — add at config root
async redirects() {
  return [
    { source: "/signup", destination: "/login", permanent: false },
    { source: "/forgot-password", destination: "/login", permanent: false },
  ];
}
```

`permanent: false` uses 307 (temporary) so behavior can be reversed in a future phase when signup flow lands.

### Anti-Patterns to Avoid

- **DON'T: Use `responses` library for authlib tests.** `responses` intercepts `requests`, not `httpx`. authlib's Starlette integration uses httpx. Use `respx` instead. (CONTEXT D-22c-TEST-01 is wrong about this — it's a documentation correction, not a gray area.)
- **DON'T: Skip Starlette's SessionMiddleware.** Without it, `oauth.google.authorize_redirect()` raises `AssertionError: SessionMiddleware must be installed` — authlib uses `request.session` for CSRF state storage.
- **DON'T: Use `HTTPException` with dict `detail` for Stripe-envelope errors.** FastAPI double-wraps as `{"detail": {"error": {...}}}`. Use inline `_err()` helper (existing codebase pattern in `agent_events.py::_err`, `runs.py::_err`).
- **DON'T: Set `Secure` cookie in dev.** Dev is `http://localhost:8000` + `:3000`; `Secure=true` causes browsers to drop the cookie entirely on HTTP. Env-gate on `AP_ENV=prod`.
- **DON'T: Read session cookie in Starlette SessionMiddleware's signed store.** authlib's `request.session` is the signed-cookie store; our `ap_session` cookie is a SEPARATE opaque session_id pointing to a PG row. Two different mechanisms for two different purposes.
- **DON'T: Cache `users/me` response in frontend.** Dashboard layout must fetch on every mount; TTL caching is deferred (specifics.md line 232). 401 → hard redirect.
- **DON'T: Put OAuth client secrets in `deploy/.env.prod.example`.** The template stays with empty values; real secrets go in `deploy/.env.prod` (gitignored). Both Google + GitHub secrets were leaked in chat on 2026-04-19 — the ROTATE warning comment in `.env.prod` is the forcing function.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OAuth2 authorize → token → userinfo flow | Custom httpx calls + state nonce | `authlib.integrations.starlette_client.OAuth` | JWK set caching, id_token validation, state rotation, OIDC discovery — ~400 lines of edge cases |
| CSRF state nonce storage | Write our own signed cookie for `ap_oauth_state` | `starlette.middleware.sessions.SessionMiddleware` (authlib uses it) | `itsdangerous` signing + rotation + expiry already solved |
| OIDC id_token JWK validation | Parse JWT, fetch Google JWK set, verify RS256 | authlib internal — happens inside `authorize_access_token()` | Full JWS/JWA stack; authlib imports `authlib.jose` |
| Cookie parsing in middleware | `http.cookies.SimpleCookie` with header rebuild | Minimal inline `split(";")` (shown in Pattern 4) | 5 lines of code; no edge case we care about (we look up ONE cookie) |
| Session opaque-id minting | Custom random + base64 encoding | `secrets.token_urlsafe(32)` (stdlib) | Cryptographically secure, URL-safe, 43-char output. Perfect for opaque cookie values. |
| Stripe-envelope 401 | Inline dict construction | `make_error_envelope(ErrorCode.UNAUTHORIZED, ...)` | Already exists + already registered in `_CODE_TO_TYPE` map |

**Key insight:** authlib + Starlette's SessionMiddleware + `secrets.token_urlsafe` + `make_error_envelope` handle 95% of the auth mechanics. Custom code in this phase is ~300 lines total across 8 new files — all plumbing, no crypto primitives, no protocol edge cases.

## Runtime State Inventory

> Phase 22c is a pure code/schema/data-purge phase. No OS-registered state, no live services holding the old strings.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **59 agent_instances rows + child agent_containers + runs + agent_events keyed to `00000000-0000-0000-0000-000000000001` (ANONYMOUS_USER_ID).** Also idempotency_keys + rate_limit_counters accumulated during dev. | Migration 006 TRUNCATEs all. Per AMD-04 + D-22c-MIG-03. |
| Live service config | **None.** No Google/GitHub app on production side yet — test-users mode only. No Caddy/Datadog/Cloudflare reg with the old user scheme. | None. |
| OS-registered state | **None.** No launchd/systemd/Task Scheduler tasks referencing ANONYMOUS_USER_ID. | None. |
| Secrets/env vars | **New required vars:** `AP_OAUTH_GOOGLE_CLIENT_ID`, `AP_OAUTH_GOOGLE_CLIENT_SECRET`, `AP_OAUTH_GOOGLE_REDIRECT_URI`, `AP_OAUTH_GITHUB_CLIENT_ID`, `AP_OAUTH_GITHUB_CLIENT_SECRET`, `AP_OAUTH_GITHUB_REDIRECT_URI`, `AP_OAUTH_STATE_SECRET` (new — for Starlette SessionMiddleware cookie signing). Already seeded in `deploy/.env.prod.example` except `AP_OAUTH_STATE_SECRET`. **Two secrets (Google + GitHub client_secret) leaked in chat 2026-04-19** — user must rotate before prod deploy. | Code-side: add 7 fields to `config.py`. Ops-side: rotate leaked secrets; generate `AP_OAUTH_STATE_SECRET` via `openssl rand -hex 32`; update `.env.prod.example` with the new var (keep empty value). |
| Build artifacts / installed packages | **None.** `authlib` + `respx` are new pip deps, nothing to un-install or rename. | None. |

## Common Pitfalls

### Pitfall 1: authlib state cookie lost between authorize and callback

**What goes wrong:** User clicks "Continue with Google", gets redirected to Google, consents, Google redirects back with `?code=X&state=Y` — but authlib's `authorize_access_token()` raises `MismatchingStateError`. The state was written to `request.session` during the authorize step, but the session cookie didn't survive the round-trip.

**Why it happens:** (1) Starlette's `SessionMiddleware` not installed at all. (2) It IS installed but `https_only=True` in dev where localhost is HTTP. (3) `SameSite` is set to `Strict` (blocks cross-origin redirects; Google IS cross-origin). (4) Cookie domain is wrong.

**How to avoid:** Install `starlette.middleware.sessions.SessionMiddleware` with:
- `secret_key=settings.oauth_state_secret` (loaded from AP_OAUTH_STATE_SECRET env)
- `session_cookie="ap_oauth_state"` (matches D-22c-OAUTH-05 naming)
- `max_age=600` (10 minutes — covers the authorize → callback round trip)
- `same_site="lax"` (REQUIRED — Lax allows cross-origin top-level GETs which is exactly what Google's redirect back is)
- `https_only=(settings.env == "prod")` (prod-only Secure flag)
- `path="/"` (default; cookie must be sent on both `/v1/auth/google` and `/v1/auth/google/callback`)

**Warning signs:** 400 with `mismatching_state` in OAuthError; no `ap_oauth_state` cookie visible in browser DevTools Application → Cookies after the authorize step.

### Pitfall 2: Google userinfo "token.get('userinfo')" returns None

**What goes wrong:** After `authorize_access_token()`, `token.get("userinfo")` returns `None` even though `openid email profile` scope was requested.

**Why it happens:** authlib populates `token["userinfo"]` from the id_token's claims ONLY when OIDC is properly negotiated (scope contains `openid` AND server returns an id_token). If the id_token is present but not decoded (e.g. JWK discovery failed silently), `userinfo` is absent.

**How to avoid:** Fallback — if `token.get("userinfo")` is None, call `await oauth.google.userinfo(token=token)` explicitly. authlib's docs show both patterns; the second is the defensive choice.

**Warning signs:** `AttributeError: 'NoneType' object has no attribute 'get'` when reading `userinfo["sub"]`.

### Pitfall 3: GitHub `/user` returns null email even with scope user:email

**What goes wrong:** User has "Keep my email addresses private" enabled in GitHub settings. `/user` returns `{"email": null, ...}` despite valid `user:email` scope.

**Why it happens:** GitHub only returns the email in `/user` if it's set to public. The `/user/emails` endpoint is the authoritative source and requires the same `user:email` scope.

**How to avoid:** Always call `/user/emails` as a fallback when `/user.email` is null. Pick `primary && verified` entry. If no such entry exists, treat as OAuth failure (defensive per Claude's Discretion). [CITED: docs.github.com/en/rest/users/emails]

**Warning signs:** `TypeError: expected str, got None` when passing the email to `upsert_user`.

### Pitfall 4: Idempotency middleware receives `None` user_id for authenticated POST /v1/runs

**What goes wrong:** After SessionMiddleware resolves `request.state.user_id = None` (no cookie), the request reaches IdempotencyMiddleware which does `user_id = request.state.user_id` and calls `check_or_reserve(conn, user_id, ...)` with None — NOT NULL constraint violation on `idempotency_keys.user_id`.

**Why it doesn't happen in practice (per D-22c-AUTH-01 + D-22c-AUTH-03):** Middleware order is `Session → RateLimit → Idempotency → routers`. Idempotency runs BEFORE the route handler — so BEFORE `require_user` fires. If user_id is None and the route is protected, `require_user` will 401, but idempotency has already touched the DB. **UNLESS** the protected route's 401 is raised from the dep BEFORE the route body runs. FastAPI dependency resolution happens INSIDE the route handler, not in middleware. So the order is:

```
Session (None user_id)
  → RateLimit (keys on subject: falls back to IP when user_id is None — rate_limit.py:_subject_from_scope already handles this correctly)
    → Idempotency (ASSUMES user_id is the real user from request.state; on None it would corrupt)
      → router
        → require_user dep → 401 (too late; idempotency already ran)
```

**How to avoid:** Two options, both acceptable:
- **Option A (SIMPLEST):** In IdempotencyMiddleware, if `request.state.user_id` is None, pass through (skip idempotency check). Any anonymous POST /v1/runs is going to 401 from require_user anyway, so caching anonymous replays is moot. One-line change in `middleware/idempotency.py::__call__`.
- **Option B:** Make SessionMiddleware a REJECT-gate for POST /v1/runs specifically (short-circuit 401 at middleware level). Harder to test, couples auth policy to middleware.

**Recommendation:** Option A. Rationale: keeps auth policy centralized in `require_user` deps; idempotency is a cache, not a security boundary; 401 reaches the client identically either way. Document in idempotency.py docstring.

**Warning signs:** `asyncpg.NotNullViolationError: null value in column "user_id" of relation "idempotency_keys"` during anonymous requests.

### Pitfall 5: Starlette SessionMiddleware session-cookie name clash

**What goes wrong:** We want `ap_oauth_state` as the authlib state cookie. Starlette's SessionMiddleware defaults to `session_cookie="session"`. If we set `session_cookie="ap_oauth_state"`, any other consumer of `request.session` (none today, but future) gets the same cookie — and there's no mechanism to have a "second session" on a different cookie.

**How to avoid:** This is fine because the Starlette session IS ONLY for authlib OAuth state in this phase. If a future phase wants a separate session store, introduce a `starsessions` library (separate project) with a different cookie name. Document in main.py that the "Starlette session" is reserved for OAuth state only.

**Warning signs:** Any code calling `request.session["foo"] = bar` in a route handler — that code is sharing the OAuth-state cookie with business data.

### Pitfall 6: Session cookie Max-Age > sessions.expires_at drift

**What goes wrong:** Cookie `Max-Age=2592000` (30 days) but `sessions.expires_at = NOW() + 30 days` computed at INSERT time. After 29 days + 23 hours, clock skew between the browser (sending the cookie) and PG (evaluating expires_at) can diverge by seconds — rare but possible.

**How to avoid:** Non-issue at 30-day horizon. Add a 1-hour buffer: `cookie Max-Age = 30 days - 1 hour`. OR: don't worry about it; sessions naturally expire a few seconds late at most.

**Warning signs:** User reports "I had to log back in after exactly 30 days but the app sometimes lets me in once more and sometimes doesn't". Cosmetic, not functional.

### Pitfall 7: `last_seen_at` throttle cache survives across uvicorn workers

**What goes wrong:** D-22c-MIG-05 specifies a 60s throttle on `UPDATE sessions SET last_seen_at = NOW()`. If the cache lives in a per-worker dict (`app.state.session_last_seen`), each uvicorn worker has its own cache — so 2 workers = 2 writes per minute, not 1.

**How to avoid:** Live with it. uvicorn single-worker is the dev default; prod uvicorn+4-workers gives 4x write rate which is still ~25x reduction from per-request. Alternative (deferred): Redis-backed cache — overkill for v1.

**Warning signs:** `last_seen_at` in PG shows N updates per minute where N = worker count. Acceptable.

## Code Examples

Verified patterns from official sources — see Architecture Patterns section above for the full set. Key snippets repeated here for quick access:

### Register authlib OAuth clients (Google + GitHub)

```python
# Source: docs.authlib.org/en/latest/client/starlette.html + fastapi-google-login demo
from authlib.integrations.starlette_client import OAuth
oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.oauth_google_client_id,
    client_secret=settings.oauth_google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
oauth.register(
    name="github",
    client_id=settings.oauth_github_client_id,
    client_secret=settings.oauth_github_client_secret,
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "read:user user:email"},
)
```

### Wire Starlette SessionMiddleware (authlib's CSRF store) + our SessionMiddleware

```python
# api_server/src/api_server/main.py — add in create_app() BEFORE existing middlewares
from starlette.middleware.sessions import SessionMiddleware as StarletteSessionMiddleware
from .middleware.session import SessionMiddleware

# Declaration order OUTERMOST LAST — same convention already used here.
# Effective request-in order: CorrelationId → AccessLog → StarletteSession → OurSession → RateLimit → Idempotency
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SessionMiddleware)                    # OUR session (ap_session cookie → user_id)
app.add_middleware(                                      # authlib state (ap_oauth_state cookie)
    StarletteSessionMiddleware,
    secret_key=settings.oauth_state_secret,
    session_cookie="ap_oauth_state",
    max_age=600,
    same_site="lax",
    https_only=(settings.env == "prod"),
    path="/",
)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(CorrelationIdMiddleware)
```

### respx test stub pattern (replaces CONTEXT D-22c-TEST-01's responses)

```python
# Source: lundberg.github.io/respx + github.com/authlib/authlib issues resolved in modern versions
import respx, httpx
from httpx import Response

@respx.mock
async def test_google_callback_success(app_with_testcontainer_pg):
    # Stub Google's token endpoint
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=Response(200, json={
            "access_token": "ya29.test", "token_type": "Bearer",
            "expires_in": 3600, "id_token": "<valid-JWT>", "scope": "openid email profile",
        })
    )
    # Stub the JWK set authlib fetches to validate the id_token — OR use a test id_token that's pre-signed.
    respx.get("https://www.googleapis.com/oauth2/v3/certs").mock(
        return_value=Response(200, json={"keys": [...]})
    )
    # Stub userinfo
    respx.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
        return_value=Response(200, json={
            "sub": "1234567890", "email": "test@gmail.com",
            "name": "Test User", "picture": "https://example.com/a.png",
        })
    )
    # Now hit /v1/auth/google/callback with a real state cookie — authlib round-trip fully exercised.
```

**Caveat on id_token validation in tests:** authlib validates the id_token against Google's JWK set. Either (a) stub the JWK endpoint with a JWK set matching a test private key and sign your own id_token, or (b) disable id_token validation in the test via authlib's `claims_options={}` register flag and use `userinfo()` endpoint fetch instead of `token.get("userinfo")`. Option (b) is simpler and aligns with the Pattern 2 defensive fallback.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `middleware.ts` in Next.js | `proxy.ts` (renamed) | Next.js 16 (2025-10-21) [CITED: nextjs.org/blog/next-16] | `middleware.ts` still works with deprecation warning; rename in this phase to future-proof |
| `nhooyr.io/websocket` | `coder/websocket` | Not relevant to 22c (backend is Python) | — |
| `responses` for httpx mocking | `respx` | `responses` never supported httpx | Correction vs CONTEXT D-22c-TEST-01 |
| Flask-style `@app.route` | FastAPI APIRouter + Depends | N/A for 22c — we're FastAPI throughout | — |

**Deprecated/outdated in CONTEXT.md:**
- CONTEXT D-22c-TEST-01 specifies `responses` — **wrong library for httpx; use `respx`** (not a behavior change, a library mismatch)
- CONTEXT D-22c-FE-01 and specific ref "new file `frontend/middleware.ts`" — **in Next 16 this file is now `proxy.ts`**; existing `middleware.ts` has a wrong note claiming no rename (fix in same task)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `TRUNCATE TABLE … CASCADE` will not fail on Postgres permissions — api user has truncate privilege on all 8 tables. [ASSUMED based on migration pattern that the same user runs prior migrations that own all tables] | Pattern 6 | Low — if this fails, fall back to sequential `DELETE FROM` in FK-aware order. Planner can add a spike. |
| A2 | authlib's state token uses Starlette's session store exclusively — no secondary cookie. [ASSUMED from authlib demo; docs describe `request.session` use but don't explicitly enumerate all internal state storage] | Pattern 1, Pitfall 1 | Low — if authlib also sets a separate cookie, our cookie plan needs one more entry, but doesn't break anything. |
| A3 | `sonner` toast library plays nicely with client components + Next 16 App Router. [VERIFIED: sonner is in package.json and shadcn officially recommends it; commonly used in Next 16 projects] | Discretion items | — |
| A4 | `scope.setdefault("state", {})["user_id"] = ...` correctly propagates to `request.state.user_id` downstream. [VERIFIED via asgi-correlation-id's source which does exactly this] | Pattern 4 | Low — established pattern. |
| A5 | Starlette's SessionMiddleware 30-day `max_age` with `https_only=False` in dev will not be rejected by Chrome/Firefox/Safari. [ASSUMED from standard cookie behavior; modern browsers only reject `SameSite=None` without `Secure`, not `SameSite=Lax` without `Secure`] | Pitfall 1 | Very low — `SameSite=Lax` without `Secure` is fully supported on HTTP. |
| A6 | `Starlette SessionMiddleware(session_cookie="ap_oauth_state", max_age=600)` coexists with our custom `SessionMiddleware` (cookie `ap_session`) — no name or path collision. [VERIFIED — distinct cookie names + both default path="/"] | Wiring example | — |
| A7 | Adding `AP_OAUTH_STATE_SECRET` to `deploy/.env.prod.example` is scope-in for 22c. [ASSUMED from CONTEXT.md "keep ALL the envs updated"] | Runtime State Inventory | None — template update is cheap. |
| A8 | `require_user` as a FastAPI Depends causing `HTTPException` works with the existing Stripe-envelope pattern, OR the codebase will prefer the inline `_err()` pattern. [ASSUMED based on observed code in `agent_events.py`, `runs.py` — they use inline `_err()`, not HTTPException. Planner should lean inline.] | Pattern 5 | Low — either pattern works; codebase consistency argues for inline `_err()`. |
| A9 | Existing `middleware.ts` global edge matcher `((?!api|_next/static|_next/image|favicon.ico).*)` has no downstream consumer of the `x-ap-has-session` header it sets. [VERIFIED via grep: no component or route reads this header] | Pattern 7 | None. |
| A10 | The existing sysadmin bypass in `agent_events.py:183-184` continues to work unchanged after introducing `require_user` — that endpoint stays Bearer-authenticated on both paths. [VERIFIED: bypass explicitly does NOT call require_user; it reads `Authorization: Bearer` header directly] | Project Constraints | None — sysadmin bypass is preserved. |

**If this table is empty:** (Not empty — see 10 items above. Most are low-risk; A1 and A8 warrant explicit planner consideration.)

## Open Questions

1. **How does the planner handle `require_user` vs inline `_err()` style inconsistency?**
   - What we know: `agent_events.py` and `runs.py` use inline `_err()` returning JSONResponse. FastAPI's `Depends(require_user)` that raises `HTTPException` would wrap the envelope one level too deep.
   - What's unclear: Does the team want to (a) introduce a global exception handler to unwrap HTTPException detail, (b) make `require_user` return `(user_id, None) | (None, JSONResponse)` tuple, (c) skip `require_user` dep and do inline checks in each route?
   - Recommendation: **(c)** — matches codebase muscle memory. `require_user` becomes a thin helper that returns `JSONResponse | UUID`; route code does `if isinstance(result, JSONResponse): return result`.

2. **Where does the SessionMiddleware's `last_seen_at` cache live across workers?**
   - What we know: D-22c-MIG-05 says throttled 60s. Per-worker dict means N workers = Nx write rate.
   - What's unclear: Is this acceptable or does the planner want Redis?
   - Recommendation: Per-worker dict in `app.state.session_last_seen`. Document the worker-count amplification. Redis is deferred.

3. **Does `TRUNCATE … CASCADE` correctly handle `agent_events → agent_containers` with ON DELETE CASCADE?**
   - What we know: 004 migration creates agent_events with `ondelete="CASCADE"` on the FK.
   - What's unclear: Empirically verified? Spike recommended per golden rule 5.
   - Recommendation: **Planner adds a Wave 0 spike** — run migration 006 against a fresh testcontainer PG seeded with mock data; verify row counts are 0 post-upgrade. Takes 5 minutes; closes the gray area cleanly.

4. **Does `AP_OAUTH_STATE_SECRET` need to be in the env template AND rotate-loud in prod?**
   - What we know: Starlette SessionMiddleware signs cookies with it. Rotating it invalidates all mid-flight OAuth state cookies (~10min window).
   - What's unclear: Should it follow the age-KEK pattern (`crypto/age_cipher.py::_master_key` fail-loud at boot if missing in prod)?
   - Recommendation: YES — match the age-KEK pattern. In prod, missing `AP_OAUTH_STATE_SECRET` = boot failure. In dev, default to a fixed dev-only placeholder like `"dev-oauth-state-key-not-for-prod"` so local dev works without env setup.

5. **Does `respx` intercept httpx calls made from within authlib's `StarletteOAuth2App`?**
   - What we know: Historical bug (respx issue #46) was fixed by authlib 0.15.1 + httpx 0.16.1 + respx 0.14.0. Modern versions (authlib 1.6.11, httpx 0.27+, respx 0.21+) should work.
   - What's unclear: Not empirically verified on THIS codebase.
   - Recommendation: **Wave 0 spike** — write a 10-line respx test that stubs Google token endpoint, invoke `oauth.google.authorize_access_token(fake_request)`, verify the stub fires. If it doesn't, fall back to `pytest-httpx`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (testcontainers image) | Integration tests (real PG) | ✓ (via pyproject `testcontainers[postgres]>=4.14.2`) | 4.14+ | — |
| Python `authlib` | OAuth client | ✗ Not installed | — | pip install `authlib>=1.6.11` — must add to pyproject deps |
| Python `itsdangerous` | SessionMiddleware signing | ✓ Installed (transitive) | 2.2.0 | — |
| Python `respx` | httpx mocking in tests | ✗ Not installed | — | pip install `respx>=0.21` — must add to pyproject dev-deps |
| Python `httpx` | Used by authlib | ✓ Installed (dev dep) | >=0.27 | — |
| Google OAuth credentials | Manual smoke | ✓ Provisioned in `deploy/.env.prod` (test-users mode) | — | Secret MUST be rotated per chat leak 2026-04-19 |
| GitHub OAuth credentials | Manual smoke | ✓ Provisioned in `deploy/.env.prod` | Client ID `Ov23liFwpCaeY2Cpv9s4` | Secret MUST be rotated per chat leak 2026-04-19 |
| `openssl` (for key gen) | `AP_OAUTH_STATE_SECRET` generation | ✓ (macOS + Linux default) | — | — |

**Missing dependencies with no fallback:** None — `authlib` and `respx` install cleanly from PyPI.

**Missing dependencies with fallback:** None required.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 8.x + `pytest-asyncio` 0.23+ (configured in `pyproject.toml::[tool.pytest.ini_options]`) |
| Config file | `api_server/pyproject.toml` |
| Quick run command | `pytest api_server/tests -x --no-header` |
| Full suite command | `pytest api_server/tests -m "not api_integration"` (fast) + `pytest api_server/tests -m api_integration` (live PG + full OAuth) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R1 | `GET /v1/auth/google` returns 302 + Set-Cookie ap_oauth_state | integration (httpx TestClient + real authlib) | `pytest api_server/tests/test_auth_routes.py::test_google_authorize_302 -x` | ❌ Wave 0 |
| R1 | Smoke: curl returns 302 + Location Google | curl | `curl -sI http://localhost:8000/v1/auth/google \| grep -E '^(Location\|Set-Cookie):'` | ✅ (requires running server) |
| R2 | Callback with valid state exchanges code → upserts user + session | integration (respx stubs + testcontainers PG) | `pytest api_server/tests/test_auth_routes.py::test_google_callback_success -x` | ❌ Wave 0 |
| R2 | Callback with mismatched state → 400 BAD_REQUEST | integration | `pytest api_server/tests/test_auth_routes.py::test_google_callback_state_mismatch -x` | ❌ Wave 0 |
| R2 | GitHub non-OIDC path + /user/emails fallback | integration (respx stubs) | `pytest api_server/tests/test_auth_routes.py::test_github_callback_private_email -x` | ❌ Wave 0 |
| R3 | SessionMiddleware resolves user_id from valid cookie | integration | `pytest api_server/tests/test_session_middleware.py::test_valid_cookie_resolves_user -x` | ❌ Wave 0 |
| R3 | No cookie → user_id=None → protected routes 401 | integration | `pytest api_server/tests/test_session_middleware.py::test_no_cookie_returns_401_on_protected -x` | ❌ Wave 0 |
| R3 | Expired/revoked cookie → user_id=None | integration | `pytest api_server/tests/test_session_middleware.py::test_expired_session_returns_none -x` | ❌ Wave 0 |
| R3 | grep check — no ANONYMOUS_USER_ID in routes | grep | `! grep -rn ANONYMOUS_USER_ID api_server/src/api_server/routes/ api_server/src/api_server/middleware/` | ✅ |
| R4 | GET /v1/users/me 200 with valid cookie | integration | `pytest api_server/tests/test_users_me.py::test_me_returns_200_with_valid_session -x` | ❌ Wave 0 |
| R4 | GET /v1/users/me 401 without cookie | integration | `pytest api_server/tests/test_users_me.py::test_me_returns_401_without_cookie -x` | ❌ Wave 0 |
| R4 | Smoke: curl with cookie | curl | `curl --cookie 'ap_session=<id>' http://localhost:8000/v1/users/me` | ✅ (requires running server) |
| R5 | POST /v1/auth/logout deletes PG row + clears cookie | integration | `pytest api_server/tests/test_auth_routes.py::test_logout_removes_session -x` | ❌ Wave 0 |
| R5 | Subsequent /v1/users/me returns 401 | integration | `pytest api_server/tests/test_auth_routes.py::test_logout_invalidates_cookie -x` | ❌ Wave 0 |
| R6 | grep check — no setTimeout in login page | grep | `! grep -c setTimeout frontend/app/login/page.tsx` | ✅ |
| R6 | grep check — window.location.href references present | grep | `grep -c "window.location.href.*/api/v1/auth/google" frontend/app/login/page.tsx` should = 1 | ✅ |
| R7 | grep check — no "Alex Chen" in dashboard layout | grep | `! grep -c "Alex Chen" frontend/app/dashboard/layout.tsx` | ✅ |
| R7 | Manual smoke: log in, see real Gmail display_name | manual | Human clicks login, verifies dashboard navbar name | ✅ (manual) |
| R8 | Post-migration: 0 agent_instances with ANONYMOUS user_id | psql | `psql "$DATABASE_URL" -tc "SELECT COUNT(*) FROM agent_instances"` returns 0 | ✅ (requires DB) |
| R8 | Post-migration: 0 rows in all 8 data tables | psql | (one command per table, or a UNION SELECT aggregate) | ✅ (requires DB) |
| R8 | Alembic 006 is marked irreversible | grep | `grep -n "raise NotImplementedError" api_server/alembic/versions/006_purge_anonymous.py` | ❌ Wave 0 |
| — (cross-cutting) | Cross-user isolation: 2 real users see only their own agents | integration | `pytest api_server/tests/test_cross_user_isolation.py::test_two_users_see_separate_agents -x` | ❌ Wave 0 |
| — (cross-cutting) | Refresh-token round-trip — **DROPPED per AMD-02** | — | (not applicable — removed from scope) | — |

### Sampling Rate

- **Per task commit:** `pytest api_server/tests -x -m "not api_integration"` (fast unit/contract tests) + `pnpm --dir frontend lint`
- **Per wave merge:** Full suite — `pytest api_server/tests` (includes `api_integration` marked tests against testcontainers PG)
- **Phase gate:** Full suite green + manual smoke (one human click-through for Google + one for GitHub) + psql row-count assertions post-006

### Wave 0 Gaps

- [ ] `api_server/tests/test_auth_routes.py` — covers R1, R2, R5; needs respx + testcontainers PG fixtures
- [ ] `api_server/tests/test_session_middleware.py` — covers R3
- [ ] `api_server/tests/test_users_me.py` — covers R4
- [ ] `api_server/tests/test_cross_user_isolation.py` — cross-cutting 2-user test per SPEC §Acceptance Criteria line 109
- [ ] `api_server/tests/conftest.py` extensions: `oauth_client` fixture (pre-registered authlib), `valid_session_cookie` fixture (creates real PG row + returns cookie value), `respx_google_stubs` + `respx_github_stubs` fixture factories
- [ ] Alembic dep: add `authlib>=1.6.11,<1.7` + `itsdangerous>=2.2.0,<3` to `[project].dependencies`; `respx>=0.21,<0.22` to `[project.optional-dependencies].dev`
- [ ] **Wave 0 spike (recommended):** respx × authlib interop — write a 10-line test that stubs Google's token endpoint and invokes `oauth.google.authorize_access_token()`, verifying the stub fires and authlib parses the response. Closes Assumption A5 + Open Question 5. **Spike evidence → plan; plan not sealed without it.**
- [ ] **Wave 0 spike (recommended):** TRUNCATE CASCADE on testcontainers PG — seed mock data mirroring the 8 data tables, run 006 upgrade, assert row counts are 0. Closes Assumption A1 + Open Question 3.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | authlib (OIDC id_token validation + OAuth2 token exchange); server-table sessions with opaque cookie |
| V3 Session Management | yes | Server-table sessions (`sessions` table + `revoked_at`); HttpOnly + SameSite=Lax + Secure-in-prod cookies; 30-day expiry; per-session `user_agent` + `ip_address` captured at mint time |
| V4 Access Control | yes | `require_user` dep on every protected route; per-query `WHERE user_id = $1` filter (defense-in-depth beyond the middleware boundary) |
| V5 Input Validation | yes | Pydantic request models at route boundary; authlib state validation; GitHub `/user.email` explicit null check |
| V6 Cryptography | yes | Starlette SessionMiddleware uses `itsdangerous` HMAC-SHA256 cookie signing; session_id minted via `secrets.token_urlsafe(32)` (128 bits entropy); NO hand-rolled crypto |

### Known Threat Patterns for Python/FastAPI + OAuth + PG

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CSRF on OAuth callback (forced login) | Tampering | authlib state token (per-request nonce in Starlette signed session cookie); callback REJECTS with 400 on mismatch |
| Session fixation | Spoofing | Session_id minted server-side at callback time; never accepts a client-supplied session_id |
| Cookie theft via XSS | Information Disclosure | HttpOnly (blocks document.cookie read); Secure in prod (blocks HTTP leak); SameSite=Lax (blocks most CSRF) |
| SQL injection on cookie value | Tampering | asyncpg parameterized queries (`$1`) used everywhere — confirmed in idempotency + agent_events code; session middleware uses same pattern |
| OAuth state secret leak in logs | Information Disclosure | AccessLogMiddleware allowlist excludes `Cookie` header by construction (verified in log_redact.py line 27-33 — no cookie logging possible) |
| Phishing via open redirect on callback | Tampering | Fixed redirect to `/dashboard` (no `?next=` param); callback never follows user-supplied URL |
| Replay of old session cookie after logout | Repudiation | Logout DELETEs the PG row; subsequent lookup misses → user_id=None → 401 |
| Timing side-channel on session lookup | Information Disclosure | Low risk — PG PK lookup is ~O(log n), effectively constant; no bcrypt-style hash on the critical path |
| GitHub `/user/emails` leakage | Information Disclosure | Only the primary+verified email is stored; others discarded; no intermediate log line contains the full list |
| OAuth provider MITM | Spoofing | authlib validates provider TLS via httpx (cert verification on by default); id_token validated against Google's JWK set |

**Secrets handling note:** Both Google + GitHub `client_secret` values leaked in chat on 2026-04-19 and MUST be rotated BEFORE any production deploy. This is not a code concern — it's an operational action tracked in `deploy/.env.prod` with inline ROTATE comments. Add a pre-deploy checklist item.

## Project Constraints (from CLAUDE.md)

Golden rules that gate every task in this phase:

1. **Golden Rule 1 (No mocks, no stubs in core substrate)** — authlib tests use REAL authlib + REAL asyncpg + testcontainers PG. Only the network boundary (Google/GitHub HTTPS endpoints) is stubbed via respx. Authlib internals are NEVER monkeypatched.
2. **Golden Rule 2 (Dumb client)** — the frontend never stores a user catalog. `/api/v1/users/me` is fetched every time dashboard layout mounts. No React state hardcode of the logged-in user (deletes "Alex Chen").
3. **Golden Rule 3 (Ship e2e locally first)** — before any prod deploy, manual smoke on localhost: click Google button, consent, land on /dashboard, see real email. Click GitHub button, same. Click Log out, verify /login.
4. **Golden Rule 4 (Root cause first)** — if a migration fails or a test fails post-implementation, investigate the mechanism; don't fix-to-pass.
5. **Golden Rule 5 (Spike gray areas before planning)** — Wave 0 spikes: (a) respx × authlib interop proof (Open Question 5), (b) TRUNCATE CASCADE on testcontainers PG (Open Question 3). Both ~10-minute probes; evidence must be captured in plan docstrings before PLAN is sealed.

Phase-specific constraints from CLAUDE.md:
- Recipe v0.1 phase is **on hold but not blocking 22c** — 22c operates on the API/frontend substrate, not on the recipe runner. No conflict.
- "Do NOT touch api/, deploy/, test/, or the old substrate" — this rule from CLAUDE.md refers to a DIFFERENT abandoned track. The ACTIVE api_server at `api_server/src/api_server/` (not `api/`) is in-scope; the abandoned `api/` Go directory doesn't exist in this repo. Confirmed by grep: only `api_server/` exists. No conflict.

## Sources

### Primary (HIGH confidence)
- [Authlib Starlette docs](https://docs.authlib.org/en/latest/client/starlette.html) — canonical `OAuth.register()` + `authorize_redirect` + `authorize_access_token` pattern; confirmed requires Starlette SessionMiddleware
- [Authlib FastAPI docs](https://docs.authlib.org/en/latest/client/fastapi.html) — FastAPI-specific integration (identical to Starlette since FastAPI inherits)
- [Authlib demo: fastapi-google-login](https://github.com/authlib/demo-oauth-client/blob/master/fastapi-google-login/app.py) — complete working reference implementation; verified SessionMiddleware + secret_key requirement
- [Authlib PyPI](https://pypi.org/project/Authlib/) — confirmed version 1.6.11 released 2026-04-16
- [Next.js 16 blog](https://nextjs.org/blog/next-16) — confirmed `middleware.ts` → `proxy.ts` rename, deprecation path
- [Next.js 16 Upgrade Guide](https://nextjs.org/docs/app/guides/upgrading/version-16) — migration steps for middleware→proxy
- [GitHub REST: /user/emails](https://docs.github.com/en/rest/users/emails) — payload shape `{email, primary, verified, visibility}`; requires `user:email` scope
- [Starlette middleware docs](https://starlette.dev/middleware/) — SessionMiddleware parameters: `secret_key`, `session_cookie`, `max_age`, `same_site`, `https_only`, `path`
- [respx GitHub](https://github.com/lundberg/respx) — httpx mocking; historical authlib compat issue resolved in modern versions
- [Alembic ops reference](https://alembic.sqlalchemy.org/en/latest/ops.html) — `op.execute()` for raw SQL in migrations
- Local: `api_server/src/api_server/middleware/correlation_id.py`, `main.py`, `idempotency.py`, `rate_limit.py`, `models/errors.py`, `config.py`, `constants.py`, `routes/{agents,runs,agent_lifecycle,agent_events}.py`
- Local: `api_server/alembic/versions/{001_baseline,003_agent_containers,004_agent_events}.py` — migration idioms + current schema state
- Local: `frontend/{middleware.ts,next.config.mjs,package.json,lib/api.ts,app/login/page.tsx,app/dashboard/layout.tsx,components/navbar.tsx}`
- Local: `deploy/.env.prod.example` — already seeded with `AP_OAUTH_*` vars
- Local: `pip show itsdangerous` — confirmed 2.2.0 installed

### Secondary (MEDIUM confidence)
- [Authlib loginpass GitHub email fix](https://github.com/authlib/loginpass/issues/32) — confirms `/user/emails` fallback pattern
- [nextauthjs null email discussion](https://github.com/nextauthjs/next-auth/discussions/7932) — independent confirmation of GitHub private-email behavior
- [respx × authlib compat](https://github.com/lundberg/respx/issues/46) — historical issue, modern versions resolved
- [Renaming middleware to proxy](https://nextjs.org/docs/messages/middleware-to-proxy) — deprecation warning details
- [MSV `api/pkg/migrate/sql/006_web_users.sql`](file:///Users/fcavalcanti/dev/meusecretariovirtual/api/pkg/migrate/sql/006_web_users.sql) — **MSV prior art is LIMITED** — MSV uses `google_id` column (not `sub`), has Telegram coupling we don't want, uses magic-code flow not session-cookie. Pattern shape (upsert on provider id) is transferable; column naming is NOT.

### Tertiary (LOW confidence — flagged for validation if leaned on)
- Medium blog posts on Next 16 migration — used to corroborate primary source, not for authoritative facts

## Metadata

**Confidence breakdown:**
- Standard stack (authlib 1.6.11, itsdangerous 2.2.0, respx 0.21+, Next 16.2 proxy.ts): HIGH — all verified against primary docs and/or local pip
- Architecture (middleware order, dual SessionMiddleware, require_user pattern, provider registration): HIGH — grounded in existing code shapes + authlib's own demo
- Pitfalls (state cookie loss, null email, idempotency NULL user_id): MEDIUM-HIGH — 6 of 7 corroborated by ecosystem issues; #4 (idempotency) is codebase-specific reasoning
- CONTEXT.md contradictions surfaced (responses→respx, middleware.ts→proxy.ts): HIGH — library docs are authoritative on both
- MSV prior art usability: LOW — MSV uses magic-code flow not session-cookie; patterns diverge
- Wave 0 spikes needed: 2 (respx×authlib + TRUNCATE CASCADE) — planner must land these before sealing plans

**Research date:** 2026-04-19
**Valid until:** 2026-05-19 (30 days — authlib + respx are stable; Next.js 16 shipped Oct 2025; re-verify only if a major authlib release lands)
