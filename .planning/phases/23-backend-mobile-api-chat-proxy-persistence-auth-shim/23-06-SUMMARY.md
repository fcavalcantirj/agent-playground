---
phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
plan: 06
subsystem: auth
tags: [oauth, mobile, google, github, jwt, integration, d-30]

# Dependency graph
requires:
  - phase: 22c-oauth-google
    provides: upsert_user + mint_session helpers + ApSessionMiddleware (consumed verbatim by the new mobile handlers)
  - plan: 23-01
    provides: "settings.oauth_google_mobile_client_ids field; google-auth + starlette as direct deps; A1+A2 spike OUTCOMEs (multi-aud verify works; respx does NOT intercept google-auth's transport → use _fetch_certs monkeypatch)"
provides:
  - "POST /v1/auth/google/mobile — additive endpoint that verifies a native-SDK Google id_token JWT, upserts the user, mints a session, returns {session_id, expires_at, user} (no Set-Cookie)"
  - "POST /v1/auth/github/mobile — additive endpoint mirroring the browser GitHub callback's email-fallback contract, returns the same body shape"
  - "auth/oauth.py::verify_google_id_token(id_token, mobile_client_ids) async helper — wraps google.oauth2.id_token.verify_oauth2_token in asyncio.to_thread with list[str] audience"
  - "auth/oauth.py::verify_github_access_token(access_token, http_client) async helper — GET /user with Bearer + /user/emails fallback for private email"
  - "tests/auth/conftest.py::authenticated_mobile_session fixture — mobile-flavored analog of authenticated_cookie; signs in via POST /v1/auth/google/mobile and yields a Cookie: ap_session=<uuid> header"
  - "9-cell D-30 coverage matrix in tests/auth/test_oauth_mobile.py — 5 Google + 3 GitHub + 1 cookie-continuity, all green"
affects: [23-07]

# Tech tracking
tech-stack:
  added: []                 # all libraries already direct deps via Plan 23-01
  patterns:
    - "asyncio.to_thread wrapping for blocking google-auth verify path (HTTP keep-alive amortizes via process-wide _GOOGLE_REQUEST)"
    - "monkeypatch _google_id_token._fetch_certs as the JWKS test seam (per A2 spike OUTCOME — respx is httpx-only, google-auth uses requests)"
    - "Pydantic Field(min_length=1) on credential body fields as the empty-token DoS gate (T-23-V5-EMPTY-TOKEN)"
    - "session_id-in-body contract for clients without a cookie jar — D-17 verified end-to-end via the cookie-continuity test cell"

key-files:
  created:
    - api_server/tests/auth/conftest.py
    - api_server/tests/auth/test_oauth_mobile.py
    - .planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-06-SUMMARY.md
  modified:
    - api_server/src/api_server/auth/oauth.py
    - api_server/src/api_server/routes/auth.py

key-decisions:
  - "JWKS-mocking: monkeypatch google.oauth2.id_token._fetch_certs (NOT respx). Plan 23-01 Task 3 OUTCOME proved respx does not intercept google-auth's requests-based transport. The monkeypatch survives library version drift since _fetch_certs is the single network seam in id_token.verify_token's PEM verify path."
  - "GitHub helper kept duplicated (NOT extracted as a shared helper between browser and mobile callbacks). The browser path uses authlib's oauth.github.get(...) (authlib's httpx_client), and the mobile path uses our raw httpx.AsyncClient — different transports. Consolidating would force authlib's client into the mobile path or our raw client into the browser path; both are larger surface changes than the MVP justifies. Logged as a deferred-ideas item."
  - "GitHub HTTP transport reuses app.state.bot_http_client (already wired in lifespan). The verify_github_access_token helper passes timeout=10.0 per-request so /user fetch fails fast vs. the bot client's 600s overall timeout (which is for long-poll Telegram channels). Plan 23-05's openrouter_http_client did not exist yet at execution time; switching is a one-line change when 23-05 lands."
  - "JWT-mint helpers duplicated across tests/spikes/test_google_auth_multi_audience.py, tests/auth/conftest.py, and tests/auth/test_oauth_mobile.py. Extraction to tests/auth/_jwt_helpers.py is deferred until a third caller appears outside this plan (currently only spike + Phase 23-06 use them)."
  - "No 6h JWKS cache wrapper around google-auth's verify call — RESEARCH §Pattern 5 recommendation followed. google-auth's own caching is sufficient for MVP, and a hand-rolled cache risks masking key-rotation incidents (the most likely failure mode)."

patterns-established:
  - "Mobile credential-exchange endpoint shape: Pydantic body model with min_length=1 → verify-helper raises ValueError → route maps ValueError to 401 envelope param=<field_name> → on success upsert_user + mint_session + body-only response (no cookie)."
  - "Test-side: settings monkeypatching pattern via async_client._transport.app.state.settings — works for any test that needs to flip a setting on the running FastAPI instance without rebuilding the app."

requirements-completed: [API-05]

# Metrics
duration: ~30min
completed: 2026-05-02
---

# Phase 23 Plan 06: Mobile-OAuth Credential Exchange Endpoints Summary

**Two additive endpoints (`POST /v1/auth/google/mobile` + `POST /v1/auth/github/mobile`) that verify a native-SDK-issued credential server-side, upsert the user via the existing 22c helper, mint a 30-day session, and return `{session_id, expires_at, user}` in the response body (no Set-Cookie — mobile has no cookie jar; the Flutter app re-sends the session_id as `Cookie: ap_session=<uuid>` on subsequent requests). 9 of 9 D-30 matrix cells green; existing browser callbacks untouched.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-02
- **Completed:** 2026-05-02
- **Tasks:** 4 (all completed via TDD RED→GREEN cycle)
- **Files created:** 2 (tests/auth/conftest.py + tests/auth/test_oauth_mobile.py) + this SUMMARY
- **Files modified:** 2 (auth/oauth.py + routes/auth.py)
- **Per-task commits:** 6 (3 RED + 3 GREEN, ~315 LOC source + 540 LOC test)

## Accomplishments

- **`verify_google_id_token` helper added** (auth/oauth.py:277-317). Wraps `google.oauth2.id_token.verify_oauth2_token` in `asyncio.to_thread`. The `audience` argument is passed as a `list[str]` directly (Wave 0 spike A1 confirmed multi-audience matching works on non-first list entries — this is the load-bearing semantic for D-23 Android + iOS coexistence). On any failure (signature mismatch, expiry, audience mismatch, missing claim, library error) the helper raises `ValueError`. On empty `mobile_client_ids` (env not configured) it raises immediately before contacting google-auth.

- **`verify_github_access_token` helper added** (auth/oauth.py:320-402). Mirrors the browser GitHub callback's `/user` + `/user/emails` fallback contract (D-22c-OAUTH-03) but uses our raw `httpx.AsyncClient` instead of authlib's token-aware client. Per-request `timeout=10.0` keeps the GitHub fetch fail-fast even when the shared `bot_http_client` has a 600s overall timeout. Returns `{sub, email, display_name, avatar_url}` on success; raises `ValueError` on every failure mode.

- **`POST /v1/auth/google/mobile` handler added** (routes/auth.py:361-429). Pydantic body `{id_token: str, min_length=1}`, calls the verify helper, applies a route-level "missing required claims" gate for `sub`/`email` (the JWT can be signature-valid but incomplete — google-auth's PEM verify path doesn't enforce these), upserts via `upsert_user`, mints via `mint_session`, fetches the row to surface `expires_at` + the full user shape, returns `{session_id, expires_at, user}`. **Does NOT call `_set_session_cookie`** (D-17 contract).

- **`POST /v1/auth/github/mobile` handler added** (routes/auth.py:432-498). Same body-shape, error-mapping, upsert/mint/fetch flow as the Google handler. Reuses `request.app.state.bot_http_client` for the GitHub `/user` + `/user/emails` calls — already wired in the `lifespan` hook by Phase 22c.3, so no new HTTP-client lifecycle is introduced.

- **`MobileGoogleAuthRequest` / `MobileGitHubAuthRequest` / `MobileSessionResponse` Pydantic models** in routes/auth.py:332-358. The body models gate empty-string credentials at the boundary (T-23-V5-EMPTY-TOKEN mitigation). `MobileSessionResponse` documents the response shape for Phase 24's typed-client codegen.

- **`authenticated_mobile_session` fixture added** (tests/auth/conftest.py — new file). Mobile-flavored analog of `authenticated_cookie`: mints a fresh RSA-2048 keypair + self-signed PEM cert, mints an RS256-signed JWT with `aud = phase23-06-fixture.apps.googleusercontent.com`, monkeypatches `app.state.settings.oauth_google_mobile_client_ids` AND `_google_id_token._fetch_certs`, POSTs to `/v1/auth/google/mobile`, asserts 200, yields `{Cookie, _user_id, _session_id}` for downstream consumers.

- **9-cell D-30 coverage matrix green** (tests/auth/test_oauth_mobile.py — new file, 540 LOC). The 9 cells:
  - **Google happy** — valid JWT with iOS audience (2nd list entry) → 200 + DB rows verified.
  - **Google invalid signature** — JWT signed by attacker key, JWKS only has real cert → 401 param=`id_token`.
  - **Google expired** — `exp_offset_seconds=-3600` → 401.
  - **Google audience mismatch** — `aud=other-app.apps.googleusercontent.com` not in settings → 401 (T-23-AUD-CONFUSION mitigation).
  - **Google missing claims** — valid signature + audience but no `email` → 401 with "missing required claims" message (route-level gate).
  - **GitHub public email** — `/user` returns email → single fetch → 200.
  - **GitHub private email** — `/user` email null → `/user/emails` fallback picks the FIRST `primary+verified` entry. Test puts a non-primary verified entry FIRST in the response array to confirm the filter is correct (regression trap against an order bug).
  - **GitHub invalid token** — `/user` returns 401 → 401 envelope `param=access_token`.
  - **Cookie continuity (D-17)** — sign in via fixture → `Cookie: ap_session=<uuid>` on `/v1/users/me` → 200 with the same user; proves `ApSessionMiddleware` resolves explicit Cookie headers transparently.

- **Empty-token boundary tests** (2 extras) confirm `Field(min_length=1)` rejects empty bodies with HTTP 422 BEFORE any verify path runs (T-23-V5-EMPTY-TOKEN).

- **Zero regression** in pre-existing auth tests: `pytest tests/auth/ -m api_integration` returns 28 passed (was 15 before this plan; +13 new from `test_oauth_mobile.py`).

- **Existing browser callbacks (`google_callback`, `github_callback`) byte-identical to pre-plan.** `git diff 515f72f..HEAD -- src/api_server/routes/auth.py | grep -E "^[+-]"` shows zero modifications to the existing handler bodies — the only changes to that file are the additive imports, the new Pydantic models block, and the two new mobile handlers + their `# Phase 23-06` divider.

## Task Commits

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 RED | Failing helper-import test | `0aea10c` | tests/auth/test_oauth_mobile.py |
| 1 GREEN | verify_google_id_token + verify_github_access_token helpers | `c4f9334` | api_server/auth/oauth.py |
| 2 RED | Route-handler import + min-length-1 boundary tests | `85f28b9` | tests/auth/test_oauth_mobile.py |
| 2 GREEN | POST /v1/auth/google/mobile + /v1/auth/github/mobile handlers | `e429d1e` | api_server/routes/auth.py |
| 3 | authenticated_mobile_session fixture | `0da25e7` | tests/auth/conftest.py |
| 4 | D-30 9-cell coverage matrix | `9d3ae4a` | tests/auth/test_oauth_mobile.py |

## Files Created/Modified

- **`api_server/src/api_server/auth/oauth.py`** *(modified, +146 LOC)* — added 4 imports (`asyncio`, `httpx`, google.auth.exceptions, transport.requests, oauth2.id_token), the module-level `_GOOGLE_REQUEST` constant, and the two new async helpers. Existing functions (`get_oauth`, `upsert_user`, `mint_session`, `reset_oauth_for_tests`, `_resolve_or_fail`) are byte-identical to pre-plan.
- **`api_server/src/api_server/routes/auth.py`** *(modified, +203 LOC)* — added 3 imports (`datetime`, `pydantic`, `SessionUserResponse`), the 3 Pydantic body models, the 2 mobile handlers, and 2 entries in `__all__`. Existing handlers (`google_login`, `google_callback`, `github_login`, `github_callback`, `logout`, `_set_session_cookie`, `_clear_session_cookie`, `_login_redirect_with_error`, `_read_session_cookie_uuid`, `_err`) are byte-identical to pre-plan.
- **`api_server/tests/auth/conftest.py`** *(new, 145 LOC)* — `authenticated_mobile_session` fixture + JWT/JWKS helpers (`_generate_keypair_and_cert`, `_mint_id_token`).
- **`api_server/tests/auth/test_oauth_mobile.py`** *(new, 540 LOC)* — full D-30 9-cell coverage matrix + 2 boundary tests + 2 import-smoke tests = 13 tests total.

## Sample Response JSON (redacted)

For Phase 24 typed-client codegen — Google sign-in success path:

```json
{
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "expires_at": "2026-06-01T13:30:00.123456+00:00",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "alice-mobile@test.example",
    "display_name": "Alice Mobile",
    "avatar_url": "https://example.com/alice.png",
    "provider": "google",
    "created_at": "2026-05-02T13:30:00.123456+00:00"
  }
}
```

GitHub success path is byte-identical except `provider="github"`. Failure responses (401) follow the existing Stripe-shape envelope:

```json
{
  "error": {
    "type": "unauthorized",
    "code": "UNAUTHORIZED",
    "message": "google id_token rejected: ...",
    "param": "id_token"
  }
}
```

## Decisions Made

- **JWKS-mock seam: monkeypatch `_google_id_token._fetch_certs`, NOT respx.** Plan 23-01 Task 3 (spike A2) empirically proved respx does NOT intercept google-auth's requests-based transport. We use the same monkeypatch pattern A1's spike demonstrated, which is the cleanest seam: `_fetch_certs` is the single network call inside `id_token.verify_oauth2_token`'s PEM verify path. Documented at the top of `test_oauth_mobile.py` so future contributors understand WHY the file does not use the project-wide `respx_oauth_providers` fixture for the Google path.

- **GitHub `verify_github_access_token` kept duplicated (NOT a shared helper).** The plan flagged this as an executor decision conditional on the diff being mechanical. It is NOT mechanical — the browser callback uses `authlib.oauth.github.get(...)` (authlib's httpx_client), and the new mobile helper takes a raw `httpx.AsyncClient`. Consolidating would force one transport into the other path; both are bigger surface changes than this MVP justifies. The GitHub-side helper still mirrors the `/user` + `/user/emails` + first-primary+verified contract byte-for-byte at the contract level.

- **Reused `app.state.bot_http_client` for the GitHub /user calls** (NOT `openrouter_http_client`, which doesn't exist yet — Plan 23-05 has not shipped at the time of this execution). Per-request `timeout=10.0` in the helper keeps the GitHub fetch fail-fast even though the bot client's overall timeout is 600s (which is for long-poll Telegram channels). When Plan 23-05 ships its dedicated `openrouter_http_client`, switching is a one-line change (route handler line that reads `request.app.state.bot_http_client`).

- **Settings monkeypatch via `async_client._transport.app`.** The shared `async_client` fixture in `tests/conftest.py` does NOT export `._app` (only `started_api_server` does). We read the running FastAPI instance from `httpx.ASGITransport`'s `.app` attribute — same instance, no fixture-shape change needed. This is the canonical hook for any test that needs to flip a setting on the live app without rebuilding it.

- **No 6h JWKS cache.** RESEARCH §Pattern 5 recommendation followed: rely on google-auth's own caching for MVP. A hand-rolled cache could mask key-rotation incidents (the most likely failure mode for a JWKS-validated path), so we'd rather pay the ~150ms HTTPS round-trip per sign-in than introduce a stateful caching layer at this surface.

## Deviations from Plan

### None of substance.

The plan's prescriptions were followed verbatim with two notes:

**Note 1 (informational):** The plan's Task 2 action block said "Reuse openrouter_http_client (10s timeout) for the GitHub /user calls". `openrouter_http_client` does not exist in this worktree — Plan 23-05 has not shipped yet (depends_on for 23-06 is only 23-01). The plan author left this as a "if 23-05 has shipped" forward-reference. We used the already-wired `bot_http_client` instead, with `timeout=10.0` passed per-request to the helper. This is a one-line switch when 23-05 lands. Documented inline in the route handler's docstring.

**Note 2 (informational):** The plan's Task 3 fixture pseudocode used `async_client._app`. The shared `async_client` fixture in `tests/conftest.py` does NOT set `._app` (only `started_api_server` does). We read the FastAPI instance via `async_client._transport.app` — same object, different attribute, zero shape change to existing fixtures. Documented inline.

Neither item is a Rule 1/2/3 deviation — they are upstream-document references that resolved cleanly without code-shape change.

## JWKS-Mocking Strategy Used

**`monkeypatch _google_id_token._fetch_certs`** (NOT respx). Decided per Plan 23-01 Task 3 OUTCOME (spike A2) which empirically proved respx is httpx-only and google-auth uses requests under the hood. The pattern is identical to Wave-0 spike A1 (`tests/spikes/test_google_auth_multi_audience.py`).

GitHub side uses respx (httpx-based, intercepts cleanly per A2's control test) — `respx.mock` context manager wraps each test that needs to mock `https://api.github.com/user` and/or `/user/emails`.

## Whether `verify_github_access_token` Was Extracted as a Shared Helper

**No** — kept duplicated between the browser callback (`github_callback` in routes/auth.py:227-297) and the mobile path (`verify_github_access_token` helper in auth/oauth.py + `github_mobile` handler in routes/auth.py). Justification:

- Browser path uses `authlib.oauth.github.get(...)` (authlib's httpx_client, token-aware).
- Mobile path uses our raw `httpx.AsyncClient` from `app.state.bot_http_client`.

Refactoring to consolidate would force one transport into the other path — bigger surface change than the MVP justifies. The contract-level mirroring (status check → email field → /user/emails fallback → first primary+verified) is byte-identical between the two implementations.

Logged as a deferred-ideas item: when both paths use the same `httpx.AsyncClient` (Plan 23-05's `openrouter_http_client` may unify them), revisit and extract.

## Whether `bot_http_client` or `openrouter_http_client` Was Used for GitHub /user

**`bot_http_client`** — the shared httpx.AsyncClient already wired by Phase 22c.3's lifespan hook in main.py:137. Plan 23-05 has not shipped at execution time, so `openrouter_http_client` does not yet exist on `app.state`. The verify helper passes `timeout=10.0` per-request so the GitHub fetch fails fast; the bot client's 600s overall timeout is for long-poll Telegram polls and does not apply when an explicit per-request timeout is given.

When 23-05 ships its dedicated client, switching is a one-line edit at routes/auth.py:451 (`http_client = request.app.state.bot_http_client` → `... .openrouter_http_client`).

## Issues Encountered

- **Two `pytest.mark.asyncio` warnings on the sync import-smoke tests** (`test_helpers_exist_on_auth_oauth_module` + `test_google_mobile_and_github_mobile_route_handlers_importable`). The module-level `pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]` applies to all tests; pytest-asyncio warns when the asyncio mark is on a sync function. The warnings are cosmetic (do not fail the test run) and could be cleaned up by either splitting the file (sync tests in a separate module) or removing the asyncio mark from the synchronous helpers individually. Defer to a low-priority cleanup pass — does not affect plan acceptance criteria.

- **Pre-existing `tests/spikes/test_truncate_cascade.py` Docker-network requirement** — out of scope. Same finding as Plan 23-01's SUMMARY; unchanged from baseline.

## User Setup Required

**None.** The two new endpoints accept tokens issued by Google's OAuth2 / GitHub's OAuth2 servers — there is no new env var to provision beyond `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS` (already added by Plan 23-01). Existing `AP_OAUTH_GITHUB_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` are NOT consumed by the mobile flow (D-24 — the same GitHub OAuth app credentials are reused; the mobile app exchanges a `flutter_appauth`-issued access_token directly without a second authorize round-trip).

## Next Phase Readiness

- **Plan 23-07 (frontend D-21 + REQUIREMENTS amendments + integration sweep):** unblocked. The mobile-OAuth contract is now empirically frozen; Phase 24's Flutter app can integrate against the documented `{session_id, expires_at, user}` body shape (sample in this SUMMARY).
- **Plan 23-08 / 23-09:** unblocked (downstream of 23-07).

No new blockers. The pre-existing `test_truncate_cascade.py` Docker-network requirement is unchanged from baseline.

## Self-Check: PASSED

Created files exist on disk:
- `api_server/tests/auth/conftest.py` — FOUND
- `api_server/tests/auth/test_oauth_mobile.py` — FOUND
- `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-06-SUMMARY.md` — FOUND (this file)

Per-task commits in git log:
- `0aea10c` Task 1 RED — FOUND
- `c4f9334` Task 1 GREEN — FOUND
- `85f28b9` Task 2 RED — FOUND
- `e429d1e` Task 2 GREEN — FOUND
- `0da25e7` Task 3 — FOUND
- `9d3ae4a` Task 4 — FOUND

All `must_haves.truths` verified in committed code:
- ✓ POST /v1/auth/google/mobile accepts `{id_token: string}`, verifies via `verify_oauth2_token(audience=settings.oauth_google_mobile_client_ids)`, upserts, mints, returns `{session_id, expires_at, user}` (routes/auth.py:361-429).
- ✓ POST /v1/auth/github/mobile accepts `{access_token: string}`, calls `/user` + `/user/emails` fallback, upserts, mints, returns same shape (routes/auth.py:432-498).
- ✓ Invalid Google id_token (signature/expiry/audience/missing-claims) → 401 with Stripe envelope (cells 2-5; param="id_token").
- ✓ Invalid GitHub access_token (non-200 or no recoverable email) → 401 with Stripe envelope (cell 8; param="access_token").
- ✓ Browser OAuth callbacks NOT modified — `git diff 515f72f..HEAD` shows zero edits inside `google_callback` / `github_callback` function bodies.
- ✓ Mobile responses return session_id in BODY, do NOT call `_set_session_cookie` — verified by the happy-path test (`assert "set-cookie" not in r.headers`).
- ✓ 9-cell coverage matrix per D-30 — 5 Google + 3 GitHub + 1 cookie-continuity all green (`pytest tests/auth/test_oauth_mobile.py -m api_integration` → 13 passed; `pytest tests/auth/ -m api_integration` → 28 passed).

Final verification block (from the plan's `<verification>` section):
- ✓ `pytest tests/auth/test_oauth_mobile.py -x` exits 0 (13 passed).
- ✓ `pytest tests/auth/ -x` exits 0 (28 passed; no regression).
- ✓ 2 helpers added (`grep -cE "async def verify_google_id_token|async def verify_github_access_token"` returns 2).
- ✓ 2 routes added (`grep -cE "auth/google/mobile|auth/github/mobile"` returns 6 — ≥2).
- ✓ Existing handlers byte-identical (zero diff on `google_callback`/`github_callback` bodies).

---
*Phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim*
*Completed: 2026-05-02*
