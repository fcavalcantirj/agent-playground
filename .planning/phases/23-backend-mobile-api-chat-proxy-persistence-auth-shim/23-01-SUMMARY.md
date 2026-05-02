---
phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
plan: 01
subsystem: testing
tags: [spike, gzip, sse, google-auth, oauth, jwt, pydantic-settings, starlette, respx]

# Dependency graph
requires:
  - phase: 22c-oauth-google
    provides: SessionMiddleware + ap_session cookie + upsert_user/mint_session helpers (consumed by Wave 1+ plans, not this plan directly)
  - phase: 22c.3-inapp-chat-channel
    provides: existing POST /v1/agents/:id/messages + SSE /messages/stream + agent_events outbox (consumed by Wave 1+ plans)
provides:
  - "Empirical proof: Starlette ≥0.46 GZipMiddleware does NOT buffer text/event-stream (D-31 regression-prevention test)"
  - "Empirical proof: google.oauth2.id_token.verify_oauth2_token accepts list[str] audience and matches ANY list element (A1)"
  - "Empirical proof: respx does NOT intercept google-auth's transport (A2 → Plan 23-06 uses monkeypatch _fetch_certs, not respx, for JWKS-fetch boundary)"
  - "google-auth promoted from transitive to direct dependency (>=2.40,<3); production JWT verify path now stable against transitive cleanup"
  - "starlette pinned as direct dependency (>=0.46) — defense-in-depth for SSE-non-buffer behavior; closes RESEARCH §Q4"
  - "ApiSettings.oauth_google_mobile_client_ids: Annotated[list[str], NoDecode] field with CSV pre-validator (consumed by Plan 23-06 mobile-OAuth)"
  - "deploy/.env.prod.example: AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS env-var stanza with operator documentation"
affects: [23-02, 23-03, 23-04, 23-05, 23-06, 23-07, 23-08, 23-09]

# Tech tracking
tech-stack:
  added:
    - "google-auth>=2.40,<3 (direct dep — was transitive only)"
    - "starlette>=0.46 (direct dep — was transitive via fastapi==0.136.0)"
  patterns:
    - "ASGI-event-level streaming inspection in spikes (vs httpx.ASGITransport which buffers to end-of-stream and is unreliable for chunk-timing assertions)"
    - "Annotated[list[str], NoDecode] for pydantic-settings v2 fields that take CSV env vars (works around v2's default complex-type JSON decoding)"
    - "monkeypatch _fetch_certs as the JWKS-fetch test seam for google-auth (instead of HTTP-layer mocking, since google-auth's transport uses requests not httpx)"

key-files:
  created:
    - api_server/tests/spikes/test_gzip_sse_compat.py
    - api_server/tests/spikes/test_google_auth_multi_audience.py
    - api_server/tests/spikes/test_respx_intercepts_pyjwk_fetch.py
    - .planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-01-SUMMARY.md
  modified:
    - api_server/pyproject.toml
    - api_server/src/api_server/config.py
    - deploy/.env.prod.example

key-decisions:
  - "ASGI-protocol-level inspection (not httpx.ASGITransport) is the correct seam for GZip×SSE chunk-timing spikes — ASGITransport buffers internally and would produce false positives or false negatives for streaming behavior"
  - "Plan 23-06 mobile-OAuth tests use monkeypatch _fetch_certs (not respx) for JWKS-fetch stubbing — A2 spike empirically proved respx does not intercept google-auth's requests-based transport"
  - "Annotated[list[str], NoDecode] is the canonical pydantic-settings v2 pattern for CSV env vars — the plain `list[str]` type hint triggers JSON-decode-before-validator and rejects 'a.com,b.com' as invalid JSON"

patterns-established:
  - "Wave 0 spike file naming: tests/spikes/test_<question>.py with module docstring stating PASS criterion + FAIL action + OUTCOME banner where applicable"
  - "Spike isolation: each Wave 0 spike constructs its OWN inline test fixtures (FastAPI app, RSA keypair, cert mapping) and does NOT import api_server.main — survives future production-side refactors"
  - "Self-signed PEM cert + google.auth.crypt.RSASigner + google.auth.jwt.encode is the cryptographically faithful way to mint test JWTs that google-auth's PEM-format verify path accepts (no pyjwt dependency needed)"

requirements-completed: [API-04, API-05, API-07]

# Metrics
duration: ~25min
completed: 2026-05-02
---

# Phase 23 Plan 01: Wave 0 Spike + Setup Gate Summary

**Three Wave-0 spikes empirically prove GZip×SSE non-buffering, google-auth multi-audience verify semantics, and respx-vs-google-auth-transport interception (negative result → monkeypatch fallback for Plan 23-06); plus google-auth+starlette promoted to direct deps and oauth_google_mobile_client_ids CSV setting added.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-02T11:50Z (approx)
- **Completed:** 2026-05-02T12:06Z
- **Tasks:** 7 (all completed)
- **Files created:** 3 spike files + this SUMMARY
- **Files modified:** pyproject.toml + config.py + .env.prod.example

## Accomplishments

- **D-31 GZip × SSE regression-prevention spike PASSES.** Inline FastAPI app with `GZipMiddleware(minimum_size=1024)` produces ≥2 separate `http.response.body` events for an SSE route with the first arriving at <250ms (well before the 500ms total stream duration), and `content-encoding != "gzip"` for the SSE response. Companion control test confirms a 2KB JSON response IS gzipped → middleware is actually engaged, not a silent no-op.
- **A1 google-auth multi-audience verify spike PASSES.** `google.oauth2.id_token.verify_oauth2_token(token, request, audience=[client_a, client_b])` ACCEPTS a JWT whose `aud == client_b` (the SECOND list entry — the most-likely silent-failure mode). Negative path: same call with `aud == client_c` (not in list) raises with "audience" in the error. Plan 23-06's mobile endpoint can pass `settings.oauth_google_mobile_client_ids` directly without a manual loop.
- **A2 respx-vs-google-auth-transport spike PASSES (with negative outcome).** Empirically: respx does NOT intercept google-auth's `_fetch_certs` HTTP call, because `google.auth.transport.requests.Request` uses the `requests` library while respx is httpx-only. Control test in the same file confirms respx IS wired correctly for `httpx.AsyncClient` (rules out a config error vs a real stack-layer mismatch). Plan 23-06's test scaffold should monkeypatch `_fetch_certs` (the pattern A1 demonstrates) instead.
- **`google-auth>=2.40,<3` and `starlette>=0.46` are now DIRECT deps** in `api_server/pyproject.toml`. `uv sync --extra dev` resolves cleanly to google-auth 2.50.0 + starlette 1.0.0. The promotion is defense-in-depth: a future cleanup of transitive deps cannot silently break Google JWT verify, and a future FastAPI bump that relaxes its starlette floor cannot revert the SSE-non-buffer behavior D-31 + Plan 23-05 depend on.
- **`Settings.oauth_google_mobile_client_ids: Annotated[list[str], NoDecode]`** is parsed from CSV env var `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS` with whitespace trim + empty-drop, default `[]`, idempotent for list inputs. Verified empirically: env="a.com,b.com, c.com" → `["a.com", "b.com", "c.com"]`; unset → `[]`; "a.com, b.com ,  " → `["a.com", "b.com"]`. All 5 existing `tests/config/` tests still pass.
- **`deploy/.env.prod.example` documents `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS`** at line 48 with operator-facing comments: comma-separated semantics, non-secret status (IDs ship in mobile binary), GitHub-mobile-reuses-existing-app note (D-24).

## Task Commits

1. **Task 1: D-31 GZip × SSE compat spike** — `bcae608` (test)
2. **Task 4: Promote google-auth + starlette to direct deps** — `d0f4233` (chore)  *[reordered ahead of Tasks 2/3 so they could `import google.oauth2.id_token` — see Deviations]*
3. **Task 2: A1 google-auth multi-audience spike** — `e3db51f` (test)
4. **Task 3: A2 respx-vs-google-auth-transport spike** — `3db9b4c` (test)
5. **Task 5: ApiSettings.oauth_google_mobile_client_ids field** — `bcf1e81` (feat)
6. **Task 6: AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS env-var documentation** — `a97f2a2` (docs)
7. **Task 7: Wave 0 umbrella verification** — no commit (verification-only; all 3 new spikes + the existing test_respx_authlib spike PASS via `pytest tests/spikes/ -m "not api_integration"`)

## Files Created/Modified

- `api_server/tests/spikes/test_gzip_sse_compat.py` *(new, 220 lines)* — D-31 regression-prevention spike. ASGI-event-level inspection of GZipMiddleware × SSE; companion control test for non-SSE compression.
- `api_server/tests/spikes/test_google_auth_multi_audience.py` *(new, 216 lines)* — A1 multi-audience semantic spike. Generates RSA-2048 keypair + self-signed PEM x509 cert, monkeypatches `_fetch_certs`, mints RS256-signed test JWTs with `google.auth.crypt.RSASigner`.
- `api_server/tests/spikes/test_respx_intercepts_pyjwk_fetch.py` *(new, 155 lines)* — A2 respx-vs-google-auth-transport spike. Drives `_fetch_certs` directly with the production transport; OUTCOME banner: NO interception → use monkeypatch fallback in Plan 23-06.
- `api_server/pyproject.toml` *(modified, +11 lines)* — added `google-auth>=2.40,<3` and `starlette>=0.46` to `[project] dependencies` block (alphabetic-sorted insertion).
- `api_server/src/api_server/config.py` *(modified, +37 lines, -3 lines)* — added `oauth_google_mobile_client_ids: Annotated[list[str], NoDecode]` field with `validation_alias="AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS"`, default_factory=list, plus `_split_mobile_client_ids_csv` `field_validator(mode="before")`. Imports updated for `Annotated`, `field_validator`, `NoDecode`.
- `deploy/.env.prod.example` *(modified, +10 lines)* — appended Phase 23 (D-23) stanza after the existing GitHub OAuth block.

## Decisions Made

- **ASGI-event-level inspection (not httpx.ASGITransport stream timing) for GZip×SSE spike.** Empirically discovered while writing Task 1: `httpx.ASGITransport` buffers the full body before surfacing a single chunk to `aiter_bytes()`/`aiter_raw()` (verified: even WITHOUT GZipMiddleware, the test produced 1 chunk at 511ms regardless). Switched to driving the ASGI `app(scope, receive, send)` callable directly and recording every `http.response.body` send event with timestamps. This is a faithful proxy for what uvicorn flushes to a real socket.
- **Plan 23-06 mobile-OAuth test scaffold uses monkeypatch `_fetch_certs`, NOT respx, for JWKS-fetch stubbing.** A2 spike empirically proved respx does not intercept google-auth's `requests`-based transport. The monkeypatch pattern (demonstrated in A1's spike) is cleaner and survives library version drift since `_fetch_certs` is the single network seam in `id_token.verify_token`.
- **`Annotated[list[str], NoDecode]` is the right pydantic-settings v2 idiom for CSV env vars.** The plain `list[str]` type hint (which the plan's spec assumed) triggers pydantic-settings's complex-type JSON-decode path BEFORE the field_validator runs — `"a.com,b.com"` is rejected as invalid JSON. Adding `NoDecode` to the annotation tells the env source NOT to JSON-decode, leaving the CSV split entirely to the validator. The plan's INTENT (CSV → list) is preserved 100%.
- **Self-signed PEM cert + `google.auth.crypt.RSASigner` for test JWT minting.** Avoids needing pyjwt as a test-only dep (which would need to be added). `id_token._GOOGLE_OAUTH2_CERTS_URL` defaults to the v1 PEM endpoint, so the verify path stays in `google.auth.jwt.decode` (PEM mode, no pyjwt) — verified by reading google-auth source.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Reordered Task 4 (deps) ahead of Tasks 2 and 3 (spikes that import google-auth)**
- **Found during:** Pre-Task 2 dep check
- **Issue:** Plan task order is 1→2→3→4. But Tasks 2 and 3 `import google.oauth2.id_token` and `from google.auth.transport import requests`, and the worktree's freshly-synced venv did NOT have google-auth installed (it was transitive in the main repo's main-branch venv but `uv sync --extra dev` in the worktree resolved without it). Running Task 2 with the original order would have failed at import.
- **Fix:** Executed Task 4 immediately after Task 1 (both Task 1's GZip×SSE spike has zero google-auth deps and runs cleanly first). Task order on disk: 1 → 4 → 2 → 3 → 5 → 6 → 7. Commit content for each task is unchanged from the plan's specification.
- **Files modified:** none beyond what each task already specified
- **Verification:** All Wave-0 spikes pass via `pytest tests/spikes/ -m "not api_integration" -x`
- **Committed in:** d0f4233 (Task 4 promoted ahead)

**2. [Rule 1 — Bug] `Annotated[list[str], NoDecode]` instead of plain `list[str]` for the new Pydantic field**
- **Found during:** Task 5 verify
- **Issue:** The plan's literal type hint `oauth_google_mobile_client_ids: list[str] = Field(default_factory=list, validation_alias="AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS")` failed at runtime when `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS=a.com,b.com,c.com` was set: `pydantic_settings.exceptions.SettingsError: error parsing value for field "oauth_google_mobile_client_ids" from source "EnvSettingsSource"` caused by `json.decoder.JSONDecodeError: Expecting value`. Pydantic-settings v2.14.0 detected `list[str]` as a complex type and tried to `json.loads("a.com,b.com,c.com")` BEFORE running the field_validator. The plan's verify command itself would have failed.
- **Fix:** Annotated the field as `Annotated[list[str], NoDecode]` (NoDecode from `pydantic_settings`). This tells the env source NOT to attempt JSON-decode, leaving CSV parsing to the field_validator. The plan's intent (CSV → list) is preserved verbatim.
- **Files modified:** `api_server/src/api_server/config.py` (added `Annotated` and `NoDecode` imports + field annotation)
- **Verification:** `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS='a.com,b.com, c.com'` → `['a.com', 'b.com', 'c.com']`; default empty → `[]`; whitespace+empties → trimmed/dropped. All 5 existing `tests/config/` tests still pass.
- **Committed in:** bcf1e81 (Task 5 commit)
- **Side effect:** the plan's literal grep `oauth_google_mobile_client_ids: list\[str\]` no longer matches verbatim (the file now reads `oauth_google_mobile_client_ids: Annotated[list[str], NoDecode]`). The grep's INTENT — does the field exist with the right value type? — is satisfied; the regex is too tight for the working implementation.

**3. [Rule 1 — Bug] GZip×SSE spike rewritten to use ASGI-event-level inspection (not httpx.ASGITransport stream timing)**
- **Found during:** Task 1 first run
- **Issue:** Initial implementation followed the plan's literal "Drive it with httpx.AsyncClient(transport=httpx.ASGITransport(app)) and a streaming GET ... record arrival time of each chunk" prescription. Empirically: even WITHOUT GZipMiddleware in the spike app, `aiter_bytes()`/`aiter_raw()` produced exactly 1 chunk at 511ms (i.e. a single end-of-stream blob), making any chunk-timing assertion meaningless. `httpx.ASGITransport` runs the ASGI app to completion and surfaces the buffered response — it cannot observe streaming.
- **Fix:** Rewrote the spike to drive the ASGI `app(scope, receive, send)` callable directly and capture every `http.response.body` send event with `time.monotonic()` timestamps. This is a faithful proxy for what uvicorn would flush over a real socket: each send event corresponds to one yield from the underlying generator, exactly the chunks the wire would see. The PASS criterion (≥2 separate body events with first <250ms) survives this seam shift unchanged.
- **Files modified:** `api_server/tests/spikes/test_gzip_sse_compat.py` (the only file the task touches)
- **Verification:** Both spike tests pass; companion `/json` route confirms GZipMiddleware is engaged (control test).
- **Committed in:** bcae608 (Task 1 commit, only the post-rewrite version was committed)

---

**Total deviations:** 3 auto-fixed (1 blocking, 2 bug)
**Impact on plan:** All three deviations preserve the plan's INTENT — Wave 0 spike gate empirically green, dep promotions live, CSV env var parses to list. The deviations were forced by infrastructure realities (worktree dep state, pydantic-settings v2 complex-type behavior, httpx.ASGITransport buffering) the plan author could reasonably not have known about without spiking each one — which is exactly what Wave 0 is for. No scope creep; no shipped substrate touched.

## Issues Encountered

- **`tests/spikes/test_truncate_cascade.py` (pre-existing, NOT this plan)** errored during the umbrella `pytest tests/spikes/ -x` run because it requires a Docker bridge network (`SPIKE_DOCKER_NETWORK=deploy_default`) that doesn't exist on a fresh worktree without `docker-compose up`. Test is `@pytest.mark.api_integration` and was added by Phase 22c-01 (commit 9cf282c). Phase 23-01 did not modify this file. Verified by running `pytest tests/spikes/ -m "not api_integration" -x` → 8/8 passed (truncate_cascade correctly deselected). **Logged for downstream attention but not fixed in this plan** — it is outside the scope boundary (pre-existing test, not directly caused by Phase 23-01 changes).

## User Setup Required

None — Phase 23-01 is a Wave 0 spike + setup gate. No external services to configure. The new `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS` env var has a sensible default (`[]`) and only becomes operationally relevant when Plan 23-06 (mobile-OAuth endpoint) ships AND a real mobile app needs to verify Google ID tokens against platform-specific client IDs. Operator runbook step is documented in the .env.prod.example comment block.

## Next Phase Readiness

Wave 0 spike gate is GREEN for Phase 23 plans 02–09:

- **Plan 23-02 (Idempotency-Key required + handler):** unblocked. No spike dependency.
- **Plan 23-03 (list_agents LATERAL):** unblocked. No spike dependency.
- **Plan 23-04 (GET /v1/models proxy):** unblocked. No spike dependency.
- **Plan 23-05 (GZipMiddleware in main.py):** unblocked — D-31 spike PASSES, so adding `GZipMiddleware(minimum_size=1024)` is safe without a content-type-exclude config (Starlette's default already excludes text/event-stream). The starlette>=0.46 direct pin protects against drift.
- **Plan 23-06 (mobile-OAuth credential endpoints):** unblocked — A1 confirms multi-audience verify works with `audience=[client_a, client_b]`; A2 dictates monkeypatch `_fetch_certs` (NOT respx) for JWKS stubbing in `tests/auth/test_oauth_mobile.py`. The new `Settings.oauth_google_mobile_client_ids` field is ready for the endpoint to consume.
- **Plan 23-07 (frontend D-21 + REQUIREMENTS amendments + integration sweep):** unblocked.
- **Plans 23-08 / 23-09:** unblocked (downstream of 23-02..06).

No blockers. The pre-existing `test_truncate_cascade.py` Docker-network requirement is unchanged from the Phase 22c baseline and does not affect Phase 23 forward motion.

## Self-Check: PASSED

Created files exist on disk:
- `api_server/tests/spikes/test_gzip_sse_compat.py` — FOUND
- `api_server/tests/spikes/test_google_auth_multi_audience.py` — FOUND
- `api_server/tests/spikes/test_respx_intercepts_pyjwk_fetch.py` — FOUND
- `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-01-SUMMARY.md` — FOUND (this file)

Per-task commits in git log:
- `bcae608` Task 1 — FOUND
- `d0f4233` Task 4 — FOUND
- `e3db51f` Task 2 — FOUND
- `3db9b4c` Task 3 — FOUND
- `bcf1e81` Task 5 — FOUND
- `a97f2a2` Task 6 — FOUND

Wave 0 gate command (`pytest tests/spikes/ -m "not api_integration" -x`): 8 passed, 1 deselected (pre-existing test_truncate_cascade.py which is `api_integration` and a known macOS Docker-network issue unrelated to this plan).

---
*Phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim*
*Completed: 2026-05-02*
