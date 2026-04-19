---
phase: 22c-oauth-google
plan: 03
subsystem: auth
tags: [oauth, authlib, pydantic, google, github, fastapi, starlette]

# Dependency graph
requires:
  - phase: 22c-oauth-google
    provides: "alembic 005 — sessions table + users.sub/avatar_url/last_login_at columns + UNIQUE(provider, sub) WHERE sub IS NOT NULL partial index; Wave 0 spike evidence that respx×authlib 1.6.11 interop works"
provides:
  - "7 new Pydantic Settings fields parsing AP_OAUTH_{GOOGLE,GITHUB}_{CLIENT_ID,CLIENT_SECRET,REDIRECT_URI} + AP_OAUTH_STATE_SECRET"
  - "api_server.auth.oauth.get_oauth(settings) — cached authlib OAuth() registry with google (OIDC) + github (non-OIDC) providers"
  - "api_server.auth.oauth.upsert_user(conn, *, provider, sub, email, display_name, avatar_url) -> UUID"
  - "api_server.auth.oauth.mint_session(conn, *, user_id, request) -> str"
  - "api_server.auth.oauth.reset_oauth_for_tests() — test-only cache reset"
  - "Fail-loud-in-prod pattern for OAuth creds (mirrors crypto/age_cipher.py::_master_key)"
  - "AP_OAUTH_STATE_SECRET stanza in deploy/.env.prod.example"
affects: [22c-04, 22c-05, 22c-09]

# Tech tracking
tech-stack:
  added: []  # authlib, itsdangerous, respx already in pyproject.toml from 22c-01
  patterns:
    - "auth/ sub-package under api_server.src.api_server — new namespace for authentication primitives"
    - "Module-level OAuth() singleton cached behind idempotent get_oauth(settings)"
    - "Fail-loud-in-prod gating via _resolve_or_fail helper — mirrors age_cipher._master_key"

key-files:
  created:
    - api_server/src/api_server/auth/__init__.py
    - api_server/src/api_server/auth/oauth.py
    - api_server/tests/auth/test_oauth_config.py
  modified:
    - api_server/src/api_server/config.py
    - deploy/.env.prod.example

key-decisions:
  - "sessions.id doubles as the opaque session token — gen_random_uuid() provides 122 bits of randomness so no separate token_urlsafe column is needed"
  - "Dev placeholder constants are module-level (_DEV_PLACEHOLDER, _DEV_REDIRECT_GOOGLE, _DEV_REDIRECT_GITHUB, _DEV_STATE_SECRET); all include the literal string 'not-for-prod' or 'localhost' as a belt-and-braces guard against accidental prod use"
  - "Redirect URIs and AP_OAUTH_STATE_SECRET are read through _resolve_or_fail even though they are NOT passed into oauth.register — this keeps the prod fail-loud check total (all 7 vars) instead of partial"

patterns-established:
  - "Pattern: auth sub-package. New Python modules owning authentication concerns live under api_server/src/api_server/auth/ — 22c-04 (SessionMiddleware) and 22c-05 (routes) will add more siblings here."
  - "Pattern: cached OAuth() registry. Module-level _oauth singleton + idempotent get_oauth(settings) + reset_oauth_for_tests() escape hatch."
  - "Pattern: prod fail-loud discipline. Any new AP_* env var that is REQUIRED in prod follows the _resolve_or_fail shape — dev fallback + prod RuntimeError naming the env var."

requirements-completed: [R1, R2, AMD-01, AMD-02, AMD-07]

# Metrics
duration: ~12min
completed: 2026-04-19
---

# Phase 22c Plan 03: OAuth Config + authlib Registry Summary

**7 Pydantic OAuth settings + cached authlib OAuth() registry (Google OIDC + GitHub non-OIDC) + upsert_user / mint_session helpers + prod fail-loud discipline mirroring crypto/age_cipher.py.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-04-19T23:40Z
- **Completed:** 2026-04-19T23:52Z
- **Tasks:** 3
- **Files modified:** 2 (config.py, .env.prod.example)
- **Files created:** 3 (auth/__init__.py, auth/oauth.py, tests/auth/test_oauth_config.py)

## Accomplishments

- **config.py** gains 7 new fields (`oauth_google_client_id`, `oauth_google_client_secret`, `oauth_google_redirect_uri`, `oauth_github_client_id`, `oauth_github_client_secret`, `oauth_github_redirect_uri`, `oauth_state_secret`), all `str | None` with `None` default so dev continues to boot without creds.
- **auth/oauth.py** ships three call sites the downstream waves consume: `get_oauth(settings)` returns a cached `authlib.integrations.starlette_client.OAuth()` registry with **both** `google` (OIDC via `server_metadata_url`) and `github` (non-OIDC with hand-specified `access_token_url` / `authorize_url` / `api_base_url`) registered; `upsert_user` targets the partial unique index `uq_users_provider_sub` created by alembic 005; `mint_session` writes the sessions row and returns the row's `id` UUID as the opaque session token.
- **Prod fail-loud** is total: in `AP_ENV=prod`, a missing value on ANY of the 7 OAuth env vars raises `RuntimeError` naming the variable — mirrors `crypto/age_cipher.py::_master_key` and covers AP_OAUTH_STATE_SECRET (the AMD-07-introduced var most at risk of being forgotten).
- **deploy/.env.prod.example** gains the `AP_OAUTH_STATE_SECRET=` stanza with the `openssl rand -hex 32` generation hint, adjacent to the existing Google and GitHub OAuth stanzas. `deploy/.env.prod` (which already holds the real secret) was intentionally NOT modified.
- **12 unit tests** cover Settings field parsing, env-alias plumbing, dev placeholder fallback, dev override with real creds, `get_oauth` idempotency, `reset_oauth_for_tests` behavior, prod fail-loud on first-missing-var AND middle-missing-var, helper function signatures, and placeholder sanity.

## Task Commits

Each task was committed atomically on main:

1. **Task 1: Add 7 OAuth Pydantic settings to config.py** — `4f5b01f` (feat)
2. **Task 2: Write auth/oauth.py (registry + upsert_user + mint_session) + unit tests** — `6fdde21` (feat)
3. **Task 3: Update deploy/.env.prod.example with AP_OAUTH_STATE_SECRET** — `7428b86` (feat)

_All three commits land on `main` directly per the sequential_execution context note — the live Docker stack bind-mounts `api_server/` so these edits are picked up on next container restart._

## Files Created/Modified

- `api_server/src/api_server/config.py` — 7 new Pydantic fields appended to `Settings` (oauth_google_*, oauth_github_*, oauth_state_secret), all using `validation_alias="AP_OAUTH_..."`. Pre-existing fields unchanged.
- `api_server/src/api_server/auth/__init__.py` — empty package marker.
- `api_server/src/api_server/auth/oauth.py` — authlib OAuth() singleton + `get_oauth(settings)` + `reset_oauth_for_tests()` + `upsert_user(...)` + `mint_session(...)` + `_resolve_or_fail(settings, field, dev_fallback)` helper + module-level dev placeholder constants.
- `api_server/tests/auth/test_oauth_config.py` — 12 unit tests (Settings fields, env parsing, dev path, dev placeholder discipline, dev override, idempotency, reset_for_tests, prod fail-loud on google_client_id, prod fail-loud on state_secret, prod happy path, helper signatures, placeholder sanity).
- `deploy/.env.prod.example` — appended 13-line stanza for `AP_OAUTH_STATE_SECRET` with generation hint.

## Decisions Made

- **sessions.id doubles as the opaque session token.** The plan's own docstring reconciled this: the cookie carries `sessions.id` directly (122 bits of randomness via `gen_random_uuid()`); no separate `token_urlsafe(32)` column is needed. `mint_session` simply returns `str(row["id"])`. `SESSION_TTL = timedelta(days=30)` is a module constant for consistency with the cookie `Max-Age=2592000` that 22c-05 will set.
- **All 7 env vars are routed through `_resolve_or_fail` even though redirect URIs and state secret are not passed into `oauth.register`.** This keeps the prod fail-loud discipline total (7-of-7 vars covered) instead of partial (4-of-7), matching the `_master_key` pattern's invariant that every REQUIRED prod env var raises on absence.
- **Module-level dev placeholders use `"not-for-prod"` / `"localhost"` literals** (`_DEV_PLACEHOLDER`, `_DEV_REDIRECT_GOOGLE`, `_DEV_REDIRECT_GITHUB`, `_DEV_STATE_SECRET`) so an accidentally-leaked placeholder to Google/GitHub is both self-describing (OAuth error logs will show the placeholder string clearly) and un-resolvable (Google/GitHub reject unknown client_ids). A `test_dev_placeholder_constants_are_non_secret` test locks this in.
- **`upsert_user` ON CONFLICT target mirrors alembic 005 verbatim.** The docstring flags this as a "CROSS-PLAN INVARIANT" so future migrations know that changing the partial index definition requires updating the query's ON CONFLICT clause (and vice versa).

## Deviations from Plan

**None — plan executed exactly as written.**

The plan's own body resolved the only ambiguity (cookie carries `sessions.id` or `secrets.token_urlsafe(32)`?) in favor of `sessions.id`; the implementation follows that resolution. No Rule 1/2/3 fixes were needed; no Rule 4 architectural calls were required.

One intentional addition worth flagging (not a deviation, a discretionary deliverable named in the plan's success criteria): **12 unit tests** were added at `api_server/tests/auth/test_oauth_config.py`. The plan's success criteria listed "Unit tests for the new config exist and pass" as a checkbox — these tests cover Settings fields, env aliases, dev path, prod fail-loud on multiple positions (first-missing-var AND middle-missing-var), idempotency, the test-cache-reset hook, helper signatures, and placeholder sanity. All 12 pass in 0.21s.

## Issues Encountered

**authlib, respx, itsdangerous were not installed in the api_server venv at session start** (spike was run from a different context in 22c-01). Resolved by running `./.venv/bin/pip install -e ".[dev]"` against the existing `api_server/.venv/` — picked up the existing `pyproject.toml` pins (authlib 1.6.11, respx 0.23.1, itsdangerous 2.2.0) already landed by 22c-01. No pyproject.toml edits were needed.

## User Setup Required

None — `deploy/.env.prod` already holds the real `AP_OAUTH_STATE_SECRET` (generated by the operator via `openssl rand -hex 32` before Wave 0 per the amd_notes section of the execution prompt). Operators cloning `.env.prod.example` for a new environment now see all 7 OAuth env vars documented with generation hints.

## Next Phase Readiness

**Wave 2 (Plan 22c-04 — SessionMiddleware) unblocks.** 22c-04 will:
- Import `get_oauth` from `api_server.auth.oauth` at app construction time (or lazy on first request).
- Add Starlette's built-in `SessionMiddleware` with `secret_key=settings.oauth_state_secret` for authlib's CSRF-state cookie (`ap_oauth_state`, 10-minute TTL).
- Add our custom `SessionMiddleware` (separate class, NOT the Starlette one) that resolves `request.state.user_id` from the `ap_session` cookie via a PG lookup.

**22c-05 (5 auth routes + /users/me)** will import `get_oauth`, `upsert_user`, `mint_session` directly. The three helpers' signatures match what `routes/auth.py` needs verbatim.

No blockers.

## Cross-Plan Invariant Confirmed

`upsert_user`'s `ON CONFLICT (provider, sub) WHERE sub IS NOT NULL` clause exactly mirrors the `uq_users_provider_sub` partial unique index created by alembic migration 005 (22c-02, committed at `ec19e7f`). The partial index preserves the seeded ANONYMOUS row (`provider=NULL`, `sub=NULL`) — alembic 006 (22c-06) deletes that row. Between now and 22c-06, `upsert_user` must be called ONLY with a non-NULL `sub`; callers in 22c-05 guarantee this by only invoking it from the OAuth callback handlers where `sub` is always present.

## 7 Env Vars Wired (Pydantic alias ↔ field)

| Env Var                            | Pydantic Field                | Role                                                                                  |
| ---------------------------------- | ----------------------------- | ------------------------------------------------------------------------------------- |
| `AP_OAUTH_GOOGLE_CLIENT_ID`        | `oauth_google_client_id`      | Google confidential client ID; consumed by `oauth.google` registration                |
| `AP_OAUTH_GOOGLE_CLIENT_SECRET`    | `oauth_google_client_secret`  | Google confidential client secret; consumed by `oauth.google` registration            |
| `AP_OAUTH_GOOGLE_REDIRECT_URI`     | `oauth_google_redirect_uri`   | Google callback URL; consumed by `routes/auth.py::/v1/auth/google` (22c-05)           |
| `AP_OAUTH_GITHUB_CLIENT_ID`        | `oauth_github_client_id`      | GitHub OAuth App client ID; consumed by `oauth.github` registration                   |
| `AP_OAUTH_GITHUB_CLIENT_SECRET`    | `oauth_github_client_secret`  | GitHub OAuth App client secret; consumed by `oauth.github` registration               |
| `AP_OAUTH_GITHUB_REDIRECT_URI`     | `oauth_github_redirect_uri`   | GitHub callback URL; consumed by `routes/auth.py::/v1/auth/github` (22c-05)           |
| `AP_OAUTH_STATE_SECRET` (AMD-07)   | `oauth_state_secret`          | Starlette `SessionMiddleware` signing key for `ap_oauth_state` cookie (22c-04)        |

## get_oauth() Dev/Prod Behavior Confirmed

**Dev (`AP_ENV=dev` or unset):** Missing values log a warning and fall back to deterministic placeholders. Both `google` and `github` providers land in `oauth._registry`. 7 WARNING log lines appear — one per missing var — matching the test `test_get_oauth_dev_uses_placeholders_when_creds_missing`.

**Prod (`AP_ENV=prod`) with all 7 vars set:** Returns a fully-registered `OAuth()` instance; no exception. Matches `test_get_oauth_prod_succeeds_when_all_creds_present`.

**Prod with ANY missing var:** Raises `RuntimeError` with message shape `"<FIELD_UPPER> (env AP_<FIELD_UPPER>) required when AP_ENV=prod"`. Matches `test_get_oauth_prod_raises_when_google_client_id_missing` (first-var case) AND `test_get_oauth_prod_raises_when_state_secret_missing` (middle-var case — the AMD-07 regression trap).

## Self-Check: PASSED

- `api_server/src/api_server/config.py` — MODIFIED (7 new fields). Verified: `grep -c "validation_alias=\"AP_OAUTH_" api_server/src/api_server/config.py` returns 7.
- `api_server/src/api_server/auth/__init__.py` — CREATED (empty). Verified present.
- `api_server/src/api_server/auth/oauth.py` — CREATED. Verified importable: `from api_server.auth.oauth import get_oauth, upsert_user, mint_session, reset_oauth_for_tests` succeeds.
- `api_server/tests/auth/test_oauth_config.py` — CREATED. 12 tests, all PASSED in 0.21s (`pytest tests/auth/test_oauth_config.py -v`).
- `deploy/.env.prod.example` — MODIFIED. Verified: `grep -c "AP_OAUTH_STATE_SECRET=" deploy/.env.prod.example` returns 1; `grep -c "openssl rand -hex 32"` returns 3 (POSTGRES_PASSWORD + AP_SYSADMIN_TOKEN + new AP_OAUTH_STATE_SECRET).
- Commit `4f5b01f` — FOUND in `git log --oneline` (Task 1 feat commit).
- Commit `6fdde21` — FOUND (Task 2 feat commit).
- Commit `7428b86` — FOUND (Task 3 feat commit).
- `deploy/.env.prod` — NOT MODIFIED (confirmed via `git status --short` showing only `deploy/.env.prod.example` as M in the task-3 commit; `.env.prod` is gitignored but also untouched on disk per the plan's instruction).

---
*Phase: 22c-oauth-google*
*Plan: 03*
*Completed: 2026-04-19*
