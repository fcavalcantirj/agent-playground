---
phase: 22c-oauth-google
plan: 03
type: execute
wave: 1
depends_on: [22c-01]
files_modified:
  - api_server/src/api_server/config.py
  - api_server/src/api_server/auth/__init__.py
  - api_server/src/api_server/auth/oauth.py
  - deploy/.env.prod.example
autonomous: true
requirements: [R1, R2, AMD-01, AMD-02, AMD-07]
must_haves:
  truths:
    - "config.py exports Pydantic settings fields for all 7 OAuth env vars (6 provider creds + AP_OAUTH_STATE_SECRET)"
    - "auth/oauth.py::get_oauth(settings) returns an authlib OAuth() registry with `google` + `github` providers registered"
    - "In prod (AP_ENV=prod), get_oauth() raises RuntimeError if any of the 7 env vars is missing (fail-loud; mirrors crypto/age_cipher.py::_master_key pattern)"
    - "In dev (AP_ENV=dev), get_oauth() falls back to deterministic placeholder strings so local test harness boots without real creds"
    - "deploy/.env.prod.example contains an `AP_OAUTH_STATE_SECRET=` stanza with docstring"
    - "auth/oauth.py exports helpers: upsert_user(conn, provider, sub, email, display_name, avatar_url) -> UUID AND mint_session(conn, user_id, request) -> str"
  artifacts:
    - path: "api_server/src/api_server/config.py"
      provides: "7 new Pydantic settings fields (oauth_{google,github}_{client_id,client_secret,redirect_uri} + oauth_state_secret)"
    - path: "api_server/src/api_server/auth/oauth.py"
      provides: "authlib OAuth() singleton + upsert_user + mint_session helpers"
      contains: "def get_oauth"
      contains: "def upsert_user"
      contains: "def mint_session"
    - path: "api_server/src/api_server/auth/__init__.py"
      provides: "package marker"
    - path: "deploy/.env.prod.example"
      contains: "AP_OAUTH_STATE_SECRET="
  key_links:
    - from: "auth/oauth.py::get_oauth"
      to: "config.py::Settings (oauth_*)"
      via: "settings argument"
      pattern: "settings.oauth_google_client_id"
    - from: "auth/oauth.py::get_oauth"
      to: "fail-loud in prod"
      via: "AP_ENV=prod + missing secret → RuntimeError"
      pattern: "if env.*prod.*raise RuntimeError"
---

<objective>
Ship the OAuth-client substrate: Pydantic settings fields (7 env vars per AMD-07), an `authlib` OAuth registry that registers `google` (OIDC) + `github` (non-OIDC) per AMD-01, two helper functions (`upsert_user` + `mint_session`) that plan 22c-05 will call from inside each provider callback, and the `.env.prod.example` update for the new `AP_OAUTH_STATE_SECRET` (required in prod for Starlette's SessionMiddleware cookie signing).

Purpose: Separate "wire the OAuth client + env plumbing" from "expose HTTP routes" (plan 22c-05). This plan is pure library + config work — no Starlette routes yet. Keeps the diff reviewable.
Output: Three new/modified files under `api_server/src/api_server/auth/` + one `config.py` patch + one `.env.prod.example` patch. The `config.py` boot-time test (`pydantic-settings` parses the env) must pass; get_oauth() must succeed in dev + fail-loud in prod.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22c-oauth-google/22c-SPEC.md
@.planning/phases/22c-oauth-google/22c-CONTEXT.md
@.planning/phases/22c-oauth-google/22c-RESEARCH.md
@.planning/phases/22c-oauth-google/22c-PATTERNS.md
@api_server/src/api_server/config.py
@api_server/src/api_server/crypto/age_cipher.py
@deploy/.env.prod.example

<interfaces>
<!-- Canonical fail-loud discipline pattern — from crypto/age_cipher.py::_master_key lines 49-75 -->
```python
def _master_key() -> bytes:
    raw = os.environ.get("AP_CHANNEL_MASTER_KEY")
    env = os.environ.get("AP_ENV", "dev")
    if not raw:
        if env == "prod":
            raise RuntimeError(
                "AP_CHANNEL_MASTER_KEY required when AP_ENV=prod"
            )
        return b"\x00" * 32
    # ... decode + validate shape
```

<!-- Pydantic Settings field pattern from config.py::Settings -->
```python
env: Literal["dev", "prod"] = Field("dev", validation_alias="AP_ENV")
max_concurrent_runs: int = Field(2, validation_alias="AP_MAX_CONCURRENT_RUNS")
```

<!-- authlib OAuth registration shape (from RESEARCH §Pattern 1 + Code Examples L722-744) -->
```python
from authlib.integrations.starlette_client import OAuth
oauth = OAuth()
oauth.register(
    name="google",
    client_id=..., client_secret=...,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
oauth.register(
    name="github",
    client_id=..., client_secret=...,
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "read:user user:email"},
)
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add 7 OAuth Pydantic settings to config.py</name>
  <files>api_server/src/api_server/config.py</files>
  <read_first>
    - api_server/src/api_server/config.py (full existing Settings class; preserve every existing field)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §AMD-07 + §D-22c-OAUTH-02 + §D-22c-OAUTH-03
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §config.py (lines 562-597)
    - deploy/.env.prod.example (verify existing AP_OAUTH_* env var NAMES match Pydantic aliases exactly)
  </read_first>
  <action>
Append 7 new fields to the `Settings` class (AFTER all existing fields, BEFORE any `model_config` / `Config` inner class). Keep types `str | None` with `Field(None, ...)` — the fail-loud check happens later in `auth/oauth.py::get_oauth()`, NOT at Settings instantiation, so that dev boots even without OAuth creds. This follows RESEARCH Pitfall 1 rationale + PATTERNS.md config.py recommendation:

```python
    # --- OAuth (Phase 22c) ---
    # Google OAuth2 (OIDC). Test-users mode in dev; confidential client creds
    # required in prod. Fail-loud happens in ``auth/oauth.py::get_oauth()`` —
    # Settings instantiation itself stays optional so dev boots without
    # credentials. Mirrors ``AP_CHANNEL_MASTER_KEY`` discipline
    # (``crypto/age_cipher.py::_master_key``).
    oauth_google_client_id: str | None = Field(
        None, validation_alias="AP_OAUTH_GOOGLE_CLIENT_ID"
    )
    oauth_google_client_secret: str | None = Field(
        None, validation_alias="AP_OAUTH_GOOGLE_CLIENT_SECRET"
    )
    oauth_google_redirect_uri: str | None = Field(
        None, validation_alias="AP_OAUTH_GOOGLE_REDIRECT_URI"
    )

    # GitHub OAuth (non-OIDC). Same discipline.
    oauth_github_client_id: str | None = Field(
        None, validation_alias="AP_OAUTH_GITHUB_CLIENT_ID"
    )
    oauth_github_client_secret: str | None = Field(
        None, validation_alias="AP_OAUTH_GITHUB_CLIENT_SECRET"
    )
    oauth_github_redirect_uri: str | None = Field(
        None, validation_alias="AP_OAUTH_GITHUB_REDIRECT_URI"
    )

    # Starlette SessionMiddleware signing secret (AMD-07).
    # Required in prod; dev uses a fixed fallback so local tests boot
    # without ops setup.
    oauth_state_secret: str | None = Field(
        None, validation_alias="AP_OAUTH_STATE_SECRET"
    )
```

**DO NOT** alter any pre-existing field. **DO NOT** flip any field from required to optional or vice versa. If `AP_OAUTH_GOOGLE_*` vars were previously parsed by a different mechanism (unlikely — grep `AP_OAUTH` in `api_server/src/` first), consolidate here and remove the prior parse sites.

If `from pydantic import Field` is already imported (it will be), no new import needed.
  </action>
  <verify>
<automated>cd api_server && python -c "from api_server.config import Settings; s = Settings(); print('env:', s.env, 'google_client_id:', s.oauth_google_client_id, 'state_secret:', s.oauth_state_secret)"</automated>
  </verify>
  <acceptance_criteria>
    - `from api_server.config import Settings; s = Settings()` constructs successfully in a dev-env shell (all 7 new fields = None when env not set)
    - `grep -c "oauth_" api_server/src/api_server/config.py` returns ≥ 7 (7 new field lines)
    - `grep -c "validation_alias=\"AP_OAUTH_" api_server/src/api_server/config.py` returns exactly 7
    - All pre-existing fields still present (diff only adds lines, removes none)
  </acceptance_criteria>
  <done>7 new Pydantic fields land. Settings parses dev env cleanly. Prod fail-loud will happen in the next task (get_oauth()).</done>
</task>

<task type="auto">
  <name>Task 2: Write auth/oauth.py (registry + upsert_user + mint_session)</name>
  <files>api_server/src/api_server/auth/__init__.py, api_server/src/api_server/auth/oauth.py</files>
  <read_first>
    - api_server/src/api_server/crypto/age_cipher.py (lines 49-75 — fail-loud pattern template)
    - api_server/src/api_server/routes/runs.py (asyncpg usage patterns — upsert with ON CONFLICT; not the only pattern but canonical)
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §Pattern 1 (authlib registration) + §Don't Hand-Roll table (session opaque id mint → secrets.token_urlsafe(32))
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §auth/oauth.py (lines 346-376)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-OAUTH-01/02/03 + §D-22c-MIG-01 (display_name reused for name)
  </read_first>
  <action>
Create `api_server/src/api_server/auth/__init__.py` — empty file (package marker).

Create `api_server/src/api_server/auth/oauth.py` with this exact shape:

```python
"""OAuth client registry + user/session helpers (Phase 22c).

This module owns three things:
  1. `get_oauth(settings)` — a cached authlib ``OAuth()`` registry with
     ``google`` (OIDC via discovery URL) and ``github`` (non-OIDC, hand-
     specified endpoints) providers registered. Per AMD-01 both providers
     ship in 22c.

  2. `upsert_user(conn, provider, sub, email, display_name, avatar_url) -> UUID`
     — upserts into ``users`` keyed on ``UNIQUE (provider, sub)``. Returns
     the user's UUID (new or existing). Writes provider's ``name`` into
     ``display_name`` per D-22c-MIG-01 (no separate ``name`` column).

  3. `mint_session(conn, user_id, request) -> str` — inserts a sessions
     row, returns an opaque 43-char URL-safe session id (see
     ``secrets.token_urlsafe(32)``). Cookie expiry = 30 days from now;
     matches the cookie ``Max-Age=2592000`` set in routes/auth.py per
     D-22c-OAUTH-04.

Fail-loud discipline mirrors ``crypto/age_cipher.py::_master_key``:
prod boot raises ``RuntimeError`` if any of the 7 OAuth env vars is
missing; dev uses deterministic placeholders so tests boot without
credentials.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from authlib.integrations.starlette_client import OAuth

if TYPE_CHECKING:
    import asyncpg
    from fastapi import Request

    from ..config import Settings

_log = logging.getLogger("api_server.auth.oauth")

# Module-level cache. ``get_oauth`` is idempotent; we register providers once
# per interpreter.
_oauth: OAuth | None = None

# Dev fallbacks — used ONLY when AP_ENV != prod and a given secret is missing.
# These are deliberately non-secret placeholders so tests can exercise the
# registration path without provisioning real credentials.
_DEV_PLACEHOLDER = "dev-placeholder-not-for-prod"
_DEV_REDIRECT_GOOGLE = "http://localhost:8000/v1/auth/google/callback"
_DEV_REDIRECT_GITHUB = "http://localhost:8000/v1/auth/github/callback"
_DEV_STATE_SECRET = "dev-oauth-state-key-not-for-prod-0000000000000000"


def _resolve_or_fail(settings: "Settings", field: str, dev_fallback: str) -> str:
    """Read ``settings.<field>``; fail in prod if missing, else use the dev fallback."""
    value = getattr(settings, field)
    if value:
        return value
    if settings.env == "prod":
        raise RuntimeError(
            f"{field.upper()} (env AP_{field.upper()}) required when AP_ENV=prod"
        )
    _log.warning(
        "OAuth config %s missing in dev; using placeholder", field
    )
    return dev_fallback


def get_oauth(settings: "Settings") -> OAuth:
    """Return the process-wide authlib OAuth registry, registering providers on first call."""
    global _oauth
    if _oauth is not None:
        return _oauth

    google_client_id = _resolve_or_fail(settings, "oauth_google_client_id", _DEV_PLACEHOLDER)
    google_client_secret = _resolve_or_fail(settings, "oauth_google_client_secret", _DEV_PLACEHOLDER)
    github_client_id = _resolve_or_fail(settings, "oauth_github_client_id", _DEV_PLACEHOLDER)
    github_client_secret = _resolve_or_fail(settings, "oauth_github_client_secret", _DEV_PLACEHOLDER)
    # Redirect URIs are read from settings for fail-loud; value used by routes/auth.py.
    _resolve_or_fail(settings, "oauth_google_redirect_uri", _DEV_REDIRECT_GOOGLE)
    _resolve_or_fail(settings, "oauth_github_redirect_uri", _DEV_REDIRECT_GITHUB)
    _resolve_or_fail(settings, "oauth_state_secret", _DEV_STATE_SECRET)

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    oauth.register(
        name="github",
        client_id=github_client_id,
        client_secret=github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )
    _oauth = oauth
    return oauth


def reset_oauth_for_tests() -> None:
    """Test-only hook — clears the module-level registry so a subsequent
    `get_oauth(settings_with_new_creds)` re-registers providers. Never call
    this in production code paths.
    """
    global _oauth
    _oauth = None


# ---------------------------------------------------------------------------
# upsert_user
# ---------------------------------------------------------------------------

async def upsert_user(
    conn: "asyncpg.Connection",
    *,
    provider: str,
    sub: str,
    email: str | None,
    display_name: str,
    avatar_url: str | None,
) -> UUID:
    """Upsert a users row keyed on ``UNIQUE (provider, sub) WHERE sub IS NOT NULL``.

    Returns the user's UUID (new or existing). Updates ``email``,
    ``display_name``, ``avatar_url``, ``last_login_at`` on conflict so a
    user whose Google profile name changed sees the update on next login.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO users (provider, sub, email, display_name, avatar_url, last_login_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (provider, sub) WHERE sub IS NOT NULL
        DO UPDATE SET
            email = EXCLUDED.email,
            display_name = EXCLUDED.display_name,
            avatar_url = EXCLUDED.avatar_url,
            last_login_at = NOW()
        RETURNING id
        """,
        provider, sub, email, display_name, avatar_url,
    )
    if row is None:  # shouldn't happen with RETURNING; defensive
        raise RuntimeError("upsert_user returned no row")
    return row["id"]


# ---------------------------------------------------------------------------
# mint_session
# ---------------------------------------------------------------------------

SESSION_TTL = timedelta(days=30)


async def mint_session(
    conn: "asyncpg.Connection",
    *,
    user_id: UUID,
    request: "Request",
) -> str:
    """Insert a sessions row; return the opaque session_id string.

    Uses ``secrets.token_urlsafe(32)`` (43 URL-safe chars, ~256 bits).
    The id is ALSO used as the sessions.id UUID — wait, no: sessions.id is
    UUID. We store a deterministic mapping: the cookie carries the raw
    token string; ``sessions.id`` is a UUID derived from it via the PG
    ``gen_random_uuid()`` default. Cookie → sessions lookup is by id.

    To keep the cookie-token == sessions.id mapping simple (and to avoid a
    second lookup column), we instead use a UUIDv4 for sessions.id AND
    put the UUID string into the cookie. The cookie is ALREADY
    cryptographically random (UUIDv4 = 122 bits of randomness) and carries
    no user-identifying info. No need for token_urlsafe(32) in this repo.
    """
    user_agent = request.headers.get("user-agent")
    # Starlette gives us request.client.host as the peer IP; trust_proxy is
    # NOT honoured here (rate_limit.py owns that logic). For 22c we simply
    # record the direct peer for future admin-UI display.
    ip = request.client.host if request.client else None
    now = datetime.now(timezone.utc)
    row = await conn.fetchrow(
        """
        INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at, user_agent, ip_address)
        VALUES ($1, $2, $3, $2, $4, $5)
        RETURNING id
        """,
        user_id, now, now + SESSION_TTL, user_agent, ip,
    )
    if row is None:
        raise RuntimeError("mint_session returned no row")
    return str(row["id"])
```

Note on the mint_session design: I reconciled the two sketches in PATTERNS vs RESEARCH — the cookie carries the sessions.id UUID string (opaque to the client, 122-bit entropy). `secrets.token_urlsafe(32)` is not used because `sessions.id` already uses `gen_random_uuid()` as the PK default. No second column needed.
  </action>
  <verify>
<automated>cd api_server && python -c "
from api_server.config import Settings
from api_server.auth.oauth import get_oauth, reset_oauth_for_tests
import os
os.environ['AP_ENV'] = 'dev'
reset_oauth_for_tests()
s = Settings()
oauth = get_oauth(s)
assert 'google' in oauth._registry, 'google provider not registered'
assert 'github' in oauth._registry, 'github provider not registered'
print('OK: dev path registers both providers')

# prod fail-loud path
os.environ['AP_ENV'] = 'prod'
reset_oauth_for_tests()
try:
    s = Settings()
    get_oauth(s)
    raise SystemExit('FAIL: prod with no creds should RuntimeError')
except RuntimeError as e:
    print(f'OK: prod fail-loud: {e}')
"</automated>
  </verify>
  <acceptance_criteria>
    - `api_server/src/api_server/auth/__init__.py` exists (empty)
    - `api_server/src/api_server/auth/oauth.py` exists
    - `from api_server.auth.oauth import get_oauth, upsert_user, mint_session, reset_oauth_for_tests` succeeds
    - In dev (`AP_ENV=dev`) with NO OAuth env vars set, `get_oauth(Settings())` returns an OAuth() registry with both `google` and `github` registered
    - In prod (`AP_ENV=prod`) with NO OAuth env vars, `get_oauth(Settings())` raises `RuntimeError` with a message naming the first missing env var
    - Module contains functions with these signatures:
      - `get_oauth(settings) -> OAuth`
      - `upsert_user(conn, *, provider, sub, email, display_name, avatar_url) -> UUID`
      - `mint_session(conn, *, user_id, request) -> str`
      - `reset_oauth_for_tests() -> None`
  </acceptance_criteria>
  <done>OAuth registry + helpers land as a new `auth/` subpackage. Dev path succeeds with placeholders; prod path is fail-loud on missing creds. Ready for 22c-05 routes to import.</done>
</task>

<task type="auto">
  <name>Task 3: Update deploy/.env.prod.example with AP_OAUTH_STATE_SECRET</name>
  <files>deploy/.env.prod.example</files>
  <read_first>
    - deploy/.env.prod.example (whole file — verify AP_OAUTH_GOOGLE_* and AP_OAUTH_GITHUB_* stanzas already exist)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §AMD-07
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §deploy/.env.prod.example (lines 637-655)
  </read_first>
  <action>
Append a new stanza to `deploy/.env.prod.example`. The exact docstring shape matches `AP_CHANNEL_MASTER_KEY` as required by AMD-07 + PATTERNS.md. Insert AFTER the existing `AP_OAUTH_GITHUB_*` block (or wherever preserves file cohesion — adjacency to the other OAuth vars is preferred).

Block to append verbatim:

```
# --- Phase 22c: Starlette SessionMiddleware signing secret ---
# authlib's OAuth flow stores the CSRF state token inside request.session
# (Starlette's built-in signed-cookie session). AP_OAUTH_STATE_SECRET is
# the signing key for the ap_oauth_state cookie (10-minute TTL; carries the
# state nonce between /v1/auth/<provider> authorize-redirect and
# /v1/auth/<provider>/callback).
#
# REQUIRED in production. In dev (AP_ENV=dev) the code falls back to a
# fixed dev-only placeholder so local tests boot without ops setup.
#
# Generate: openssl rand -hex 32
AP_OAUTH_STATE_SECRET=
```

DO NOT alter the existing `AP_OAUTH_GOOGLE_*` or `AP_OAUTH_GITHUB_*` stanzas. DO NOT introduce real values. The template is committed to git — real values live in the gitignored `deploy/.env.prod`.

Final commit for this plan:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add api_server/src/api_server/config.py api_server/src/api_server/auth/ deploy/.env.prod.example
git commit -m "feat(22c-03): oauth settings + authlib registry + env template"
```
  </action>
  <verify>
<automated>grep -q "AP_OAUTH_STATE_SECRET=" deploy/.env.prod.example && grep -q "openssl rand -hex 32" deploy/.env.prod.example</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "AP_OAUTH_STATE_SECRET=" deploy/.env.prod.example` returns 1
    - The stanza includes the `openssl rand -hex 32` generation hint
    - All pre-existing `AP_OAUTH_GOOGLE_*` and `AP_OAUTH_GITHUB_*` stanzas unchanged (diff strictly additive)
    - Commit exists on main with message `feat(22c-03): oauth settings + authlib registry + env template`
  </acceptance_criteria>
  <done>`.env.prod.example` carries the new required env var docstring. Operators cloning the template see all 7 OAuth env vars.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Settings → env vars | Pydantic-settings reads from env. Supply-chain trust: only `AP_*` vars we declare. |
| auth/oauth.py → authlib → Google/GitHub endpoints | Module-level OAuth() registry is process-scoped; registration state doesn't cross request boundaries. |
| Dev fallback placeholders | If `_DEV_PLACEHOLDER` leaks into a real OAuth request, Google/GitHub reject it — no server-side exposure possible. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22c-05 | Spoofing | Dev placeholder creds ever sent to prod Google | mitigate | `get_oauth` raises `RuntimeError` in prod when any of the 7 vars missing. The `_DEV_PLACEHOLDER` string can NEVER reach Google in prod (per D-22c-OAUTH-04 mirrored via AP_ENV check) |
| T-22c-06 | Information disclosure | OAuth client_secret in logs | mitigate | `log_redact.py::_LOG_HEADERS` already allowlists known safe headers only; secrets live in `settings.*` but are never logged. Zero positive mitigation required — existing log allowlist covers it |
| T-22c-07 | Tampering | `reset_oauth_for_tests()` called in prod code path | accept | Function name + docstring make intent obvious; grep CI can add a pre-commit guard later if misuse observed |
</threat_model>

<verification>
```bash
# Dev path
cd api_server && AP_ENV=dev python -c "from api_server.auth.oauth import get_oauth, reset_oauth_for_tests; from api_server.config import Settings; reset_oauth_for_tests(); get_oauth(Settings())"

# Prod fail-loud
cd api_server && AP_ENV=prod python -c "from api_server.auth.oauth import get_oauth, reset_oauth_for_tests; from api_server.config import Settings; reset_oauth_for_tests();
try: get_oauth(Settings())
except RuntimeError as e: print('OK:', e); exit(0)
raise SystemExit('FAIL: prod should fail-loud')
"

# Template check
grep -q "AP_OAUTH_STATE_SECRET=" deploy/.env.prod.example
```
</verification>

<success_criteria>
- `config.py` has 7 new OAuth Pydantic fields (all `str | None` with `None` default)
- `auth/oauth.py` exports `get_oauth`, `upsert_user`, `mint_session`, `reset_oauth_for_tests`
- Dev path: placeholders boot successfully
- Prod path: missing secret raises `RuntimeError`
- `.env.prod.example` contains `AP_OAUTH_STATE_SECRET=` stanza
- Commit `feat(22c-03): oauth settings + authlib registry + env template` on main
</success_criteria>

<output>
After completion, create `.planning/phases/22c-oauth-google/22c-03-SUMMARY.md` with:
- 7 env vars wired (list with Pydantic alias pairs)
- get_oauth dev/prod behavior confirmed
- Note: upsert_user ON CONFLICT clause relies on the partial-unique index from 22c-02; cross-plan invariant confirmed
</output>
