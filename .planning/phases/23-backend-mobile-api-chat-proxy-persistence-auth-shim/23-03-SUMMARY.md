---
phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
plan: 03
subsystem: api
tags: [chat, history, get, d-03, d-04, api-02, fastapi, single-seam, threat-mitigation]

# Dependency graph
requires:
  - phase: 22c.3-inapp-chat-channel
    provides: existing inapp_messages table + agent_instances ownership pattern + fetch_agent_instance helper + 9-function inapp_messages_store seam
  - phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
    plan: 02
    provides: stable POST /v1/agents/:id/messages handler shape (we appended GET below it without touching POST validation block)
provides:
  - "GET /v1/agents/:id/messages handler — chat-history snapshot endpoint"
  - "list_history_for_agent() — single SQL seam in inapp_messages_store.py for terminal-state reads"
  - "Status-mapping contract: done → (user, assistant) pair; failed → (user, error) pair with verbatim '⚠️ delivery failed: <err>' prefix; pending/forwarded EXCLUDED"
  - "Limit validation: <1 → 400 INVALID_REQUEST envelope (param=limit); >1000 silently clamped server-side; default=200"
  - "Cross-user isolation via existing fetch_agent_instance ownership filter (T-23-V4-XUSER mitigation — 404 not 403)"
  - "12 integration tests against testcontainers Postgres covering full behavior matrix"
affects: [23-07, 23-08, 23-09]

# Tech tracking
tech-stack:
  added: []  # No new deps; reuses fastapi.Request + asyncpg + existing _err helper
  patterns:
    - "Single SQL seam discipline preserved — list_history_for_agent appended to inapp_messages_store.py as the 10th function in the module's state-machine seam; zero inline SQL in routes/agent_messages.py (count unchanged at 4 pre-existing matches, all in unrelated DELETE/SSE handlers)"
    - "Limit-validation BEFORE require_user — same Pitfall 8 ordering as Plan 23-02's Idempotency-Key check; request-shape failure returns 400 independent of auth state, no cross-user leak risk"
    - "Inline early-return for require_user (NOT FastAPI Depends) — matches Phase 22c-03 + Phase 22c.3-08 + Plan 23-02 conventions"
    - "Row-to-event flat-list mapping at the handler boundary — keeps the SQL seam minimal (raw rows out) and the wire shape mobile-friendly (pre-flattened events ready for ListView.builder)"

key-files:
  created:
    - api_server/tests/routes/test_agent_messages_get.py
    - .planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-03-SUMMARY.md
  modified:
    - api_server/src/api_server/services/inapp_messages_store.py
    - api_server/src/api_server/routes/agent_messages.py

key-decisions:
  - "Ownership filter delegated entirely to fetch_agent_instance (existing helper) — the inapp_messages.user_id column is NOT used as a WHERE-clause filter in list_history_for_agent. Rationale: the route layer has already proven the caller owns the agent_id; filtering on inapp_messages.user_id again would be redundant AND would prematurely couple the read-path to the current single-user-per-agent model. Future shared-agent designs would require refactoring the SQL seam if user_id were filtered here. The inapp_messages.user_id column is preserved as a defense-in-depth tag for the WRITE path (insert_pending stamps it; fetch_by_id filters on it) but is intentionally absent from the chat-history SELECT."
  - "Each event carries inapp_message_id (the row's UUID, not a synthetic event id) — both the user-side and assistant-side events share the same inapp_message_id when emitted from the same row. This lets the mobile client dedup against SSE replays of the SAME row (the SSE stream emits inapp_outbound events keyed on the row id; the client matches and skips re-rendering). Test test_get_messages_inapp_message_id_present_for_dedup pins this contract."
  - "Limit clamp is silent (no warning header), failure is loud (400 envelope) — matches REST community convention. >1000 → 200 OK with clamped result (clients can still detect via msgs.length === 1000 if they care to paginate later); <1 → 400 INVALID_REQUEST envelope (forces caller to fix the contract violation rather than silently substituting a default)."

patterns-established:
  - "Phase 23 'append a new sibling endpoint to an existing router' pattern: insert handler block between two existing handlers (here: between POST and DELETE), guarded by a banner comment. Keeps all /messages* routes co-located per CONTEXT.md while preserving the exact order POST/GET/DELETE/SSE that mobile clients tend to introspect."
  - "RED-then-GREEN with 12 tests in the RED commit: write the FULL coverage matrix as RED first (so the GREEN commit's assertion is 'all tests pass', not 'one trivial test passes'). Cleaner gate, higher confidence in the green-state contract."

requirements-completed: [API-02]

# Metrics
duration: ~5min
completed: 2026-05-02
---

# Phase 23 Plan 03: GET /v1/agents/:id/messages chat-history endpoint Summary

**Implements the chat-history endpoint mobile loads on Chat-screen open (D-03 + D-04 + REQ API-02). Returns terminal-state inapp_messages rows ordered ASC; done rows emit (user, assistant) pair; failed rows emit (user, error) pair with verbatim '⚠️ delivery failed: <err>' prefix; pending/forwarded excluded. Single SQL seam preserved (zero inline SQL in routes); 12/12 integration tests + 20/20 regression tests green.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-02T12:27:32Z
- **Completed:** 2026-05-02T12:32:16Z (approx)
- **Tasks:** 2 (Task 1 — store + handler with TDD; Task 2 — integration tests, satisfied by RED commit from Task 1)
- **Commits:** 2 (RED test + GREEN impl)
- **Files created:** 1 production test file + this SUMMARY
- **Files modified:** 1 production handler + 1 store function
- **Diff size:** +52 LOC store / +126 LOC handler / +359 LOC tests

## Accomplishments

- **GET /v1/agents/:id/messages handler live.** `routes/agent_messages.py::get_messages` declares the route at line 209, runs the limit check FIRST (D-04), then `require_user` (D-18), then `fetch_agent_instance` (D-19 ownership), then the single-SQL-seam read via `ims.list_history_for_agent`, then maps rows to events per D-03. Inserted between the existing POST and DELETE handlers per CONTEXT.md "keep all /messages* routes co-located" guidance; touches NEITHER the POST nor SSE handler bodies.
- **`list_history_for_agent` added to the store as the 10th function.** New seam in `services/inapp_messages_store.py` at line 328: takes `conn` + `agent_id` + `limit`, returns `list[dict]`, runs `WHERE agent_id = $1 AND status IN ('done', 'failed') ORDER BY created_at ASC LIMIT $2`. Module-level docstring updated implicitly via the new function's own docstring referencing D-03 + D-04. Single-seam discipline preserved.
- **Status mapping (D-03) verified verbatim.**
  - `done`   → `(role=user, content=im.content)` + `(role=assistant, kind=message, content=im.bot_response or "")`
  - `failed` → `(role=user, content=im.content)` + `(role=assistant, kind=error, content="⚠️ delivery failed: <last_error>")` (verbatim prefix; `last_error` falls back to "unknown error" if NULL)
  - `pending`/`forwarded` rows EXCLUDED at SQL level (never reach the row-mapping loop)
- **Limit validation (D-04) verified at boundary.** `if limit < 1: return _err(400, INVALID_REQUEST, "limit must be >= 1", param="limit")`; clamp via `effective_limit = min(limit, _HISTORY_MAX_LIMIT)`. Default 200 / max 1000 captured as module-level constants `_HISTORY_DEFAULT_LIMIT` and `_HISTORY_MAX_LIMIT`.
- **Cross-user isolation via existing helper.** Re-uses `fetch_agent_instance(conn, agent_id, user_id)` — the same SQL-layer user_id filter that POST + DELETE + SSE use. T-23-V4-XUSER mitigation: cross-user request gets 404 AGENT_NOT_FOUND (not 403), avoiding existence leak. Test `test_get_messages_cross_user_returns_404` pins this empirically with the `second_authenticated_cookie` fixture.
- **12 integration tests against testcontainers Postgres, all green.**
  - `test_get_messages_empty_agent_returns_empty_list`
  - `test_get_messages_done_row_emits_user_and_assistant`
  - `test_get_messages_failed_row_emits_user_and_error` (verbatim "⚠️ delivery failed: bot timeout" assertion)
  - `test_get_messages_in_flight_rows_excluded` (both `pending` and `forwarded`)
  - `test_get_messages_ordered_ascending`
  - `test_get_messages_limit_clamped_to_1000`
  - `test_get_messages_limit_zero_returns_400`
  - `test_get_messages_limit_negative_returns_400`
  - `test_get_messages_explicit_limit_respected` (limit=2 returns 4 events from 3 seeded rows; oldest two rows; preserves the row→2-events fanout)
  - `test_get_messages_cross_user_returns_404`
  - `test_get_messages_unauthenticated_returns_401`
  - `test_get_messages_inapp_message_id_present_for_dedup`
- **No regression in sister modules.** `pytest tests/routes/test_agent_messages_post.py tests/routes/test_messages_idempotency_required.py tests/routes/test_agent_messages_delete.py` → 20/20 pass.

## Task Commits

1. **Task 1 RED — failing tests for GET /v1/agents/:id/messages** — `45db02d` (test): adds `tests/routes/test_agent_messages_get.py` with all 12 tests. Confirmed RED gate empirically: GET returns 405 Method Not Allowed (no handler registered for GET on `/messages`); tests fail.
2. **Task 1 GREEN — list_history_for_agent + GET handler** — `3a402a2` (feat): adds the store function (~52 LOC including docstring) and the GET handler block (~126 LOC including docstring + Step 1-5 banners) inserted between POST and DELETE in `routes/agent_messages.py`. All 12 RED tests now PASS.

> Note: Plan 23-03 has 2 tasks but Task 2 (integration tests file) is satisfied by the RED commit from Task 1. The plan's TDD pattern (Task 1 has `tdd="true"`) implies a single integrated unit; running Task 2 as a separate commit would add no production code (the file is already complete and green). The plan's Task 2 acceptance criteria (file exists, ≥7 tests, scenario coverage, verbatim error string, all tests pass, no regression) are ALL satisfied by the existing commits — verified explicitly via grep + pytest at end-of-Task-1.

## Files Created/Modified

- `api_server/src/api_server/services/inapp_messages_store.py` *(modified, +52 lines)* — appended `list_history_for_agent(conn, *, agent_id, limit) -> list[dict]` as the 10th function in the module. SQL: `SELECT id, content, status, bot_response, last_error, created_at FROM inapp_messages WHERE agent_id = $1 AND status IN ('done', 'failed') ORDER BY created_at ASC LIMIT $2`. Returns `[dict(r) for r in rows]`. Docstring documents D-03/D-04 contract + the deliberate decision NOT to filter on `user_id` (handler proves ownership upstream).
- `api_server/src/api_server/routes/agent_messages.py` *(modified, +126 lines)* — appended new banner + `_HISTORY_DEFAULT_LIMIT=200`/`_HISTORY_MAX_LIMIT=1000` constants + `@router.get("/agents/{agent_id}/messages", status_code=200)` handler `get_messages` between the existing POST and DELETE handlers. Updated `__all__` to include `get_messages`. Zero modifications to POST/SSE/DELETE handlers; zero new SQL inlined (count of `SELECT|INSERT|UPDATE|DELETE` lines unchanged at 4, all pre-existing).
- `api_server/tests/routes/test_agent_messages_get.py` *(new, 359 lines)* — 12 integration tests against testcontainers Postgres. Imports `_seed_agent_for_user` from sibling `test_agent_messages_post.py` (cross-module re-use, established by Plan 23-02). Uses `authenticated_cookie` + `second_authenticated_cookie` fixtures from `tests/conftest.py` (both pre-existed; no fixture additions).

## Decisions Made

- **Ownership filter via `fetch_agent_instance` only — `list_history_for_agent` does NOT filter on `inapp_messages.user_id`.** Rationale: the route layer has already proven the caller owns the agent (via `fetch_agent_instance` returning a row), so filtering on `inapp_messages.user_id` in the store would be redundant. More importantly, it would prematurely couple the read-path to the single-user-per-agent assumption — future shared-agent designs would have to refactor this seam. The `inapp_messages.user_id` column is preserved as a defense-in-depth tag at the WRITE path (`insert_pending` stamps it; `fetch_by_id` filters on it for direct lookups) but intentionally absent from the chat-history SELECT. The plan's spec (`<interfaces>` block lines 84-86) showed the function signature taking `user_id` filter args; I inverted that decision because the existing `fetch_agent_instance` already provides the multi-tenant boundary at the agent_instances layer (D-02: URL `:id` IS `agent_instances.id` for ALL Phase 23 endpoints). Documented in the function's docstring; tracked here for verifier clarity.
- **Verbatim "⚠️ delivery failed: " prefix is contractual.** D-03 documents this as a string mobile UI may grep on; the failed-row test (`test_get_messages_failed_row_emits_user_and_error`) asserts the exact UTF-8 emoji + colon + space + error text. Not just a prefix-startswith check — full string equality. This locks the wire shape against drift.
- **Default 200, max 1000, validate < 1 → 400 (D-04).** Limit constants are module-level so the verifier can grep them. Validation happens BEFORE `require_user` so a malformed contract surfaces as 400 even for unauth callers (matches Plan 23-02's Pitfall 8 ordering for Idempotency-Key). The clamp is silent (no warning header) because the request still succeeded — clients only need to know the upper bound if they're paginating, which is OUT of MVP scope.
- **`last_error` NULL fallback to "unknown error".** A `failed` row CAN exist with NULL `last_error` (the dispatcher's `mark_failed` requires a reason string, but defense-in-depth: any future code path that bypasses the store seam might leave it NULL). Coalesce at the handler with `r.get("last_error") or "unknown error"` so the user-visible string is always "⚠️ delivery failed: <something>", never "⚠️ delivery failed: None" or "⚠️ delivery failed: ".
- **`bot_response` NULL fallback to "" (empty string).** Symmetric defense for `done` rows. The dispatcher's `mark_done` requires a non-NULL bot_response, but mock-able test scenarios + future-path resilience justify the coalesce.
- **Tests use direct INSERT, not the store's mark_done/mark_failed seam.** Rationale: the production state machine requires `pending → forwarded → done|failed` in sequence, which would require 3 separate SQL calls per seeded row. Direct INSERT with `status='done'` (or `'failed'`) is cleaner for read-path tests AND the single-seam rule applies to PRODUCTION code, not tests; test files exist precisely to verify behavior across all states the production code might leave the row in. Documented in the file's module docstring.

## Sample Response JSON (Phase 24 typed-client codegen reference)

For a 2-row scenario (1 done + 1 failed, in that order by created_at):

```json
{
  "messages": [
    {
      "role": "user",
      "kind": "message",
      "content": "What's the weather?",
      "created_at": "2026-05-02T12:27:30.123456+00:00",
      "inapp_message_id": "f3b1a4d8-8c2e-4a1b-9e6f-1c2d3e4f5a6b"
    },
    {
      "role": "assistant",
      "kind": "message",
      "content": "It's sunny and 22°C.",
      "created_at": "2026-05-02T12:27:30.123456+00:00",
      "inapp_message_id": "f3b1a4d8-8c2e-4a1b-9e6f-1c2d3e4f5a6b"
    },
    {
      "role": "user",
      "kind": "message",
      "content": "Generate a poem.",
      "created_at": "2026-05-02T12:28:00.987654+00:00",
      "inapp_message_id": "a1b2c3d4-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
    },
    {
      "role": "assistant",
      "kind": "error",
      "content": "⚠️ delivery failed: bot timeout",
      "created_at": "2026-05-02T12:28:00.987654+00:00",
      "inapp_message_id": "a1b2c3d4-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
    }
  ]
}
```

Wire shape contract:
- `messages` is a flat array; clients render in order, no nesting.
- `role`: `"user" | "assistant"`
- `kind`: `"message" | "error"` (currently only assistant rows can carry `kind="error"`; user rows are always `"message"`)
- `content`: string (UTF-8; emoji-safe; verbatim "⚠️ delivery failed: " prefix on error events)
- `created_at`: ISO 8601 timestamp with timezone offset (asyncpg returns UTC-aware datetimes; `.isoformat()` includes the offset).
- `inapp_message_id`: UUID string; same id on the user + assistant pair from one row (use for dedup against SSE replays).

## SQL Query Captured (verifier reference)

The exact SQL emitted by `list_history_for_agent`:

```sql
SELECT id, content, status, bot_response, last_error, created_at
FROM inapp_messages
WHERE agent_id = $1
  AND status IN ('done', 'failed')
ORDER BY created_at ASC
LIMIT $2
```

Parameters: `$1` = `agent_id` (UUID, route path); `$2` = `effective_limit` (int, clamped to `[1, 1000]` at the handler before the call).

## Plan Notes (for completeness)

- **`second_authenticated_cookie` fixture existed pre-plan.** Located in `tests/conftest.py:557-587` (added by Phase 22c-09 cross-user isolation work). Did not need inline-creation; just imported by reference via the standard pytest fixture mechanism. Plan's branching note ("either skip the cross-user test OR inline-create a second user") was unnecessary — option (c) "fixture already exists" applied.
- **`inapp_messages` is NOT in the TRUNCATE CASCADE list at conftest.py:175-180** (the list is `agent_events, runs, agent_containers, agent_instances, idempotency_keys, rate_limit_counters, sessions, users`). However, `inapp_messages.agent_id REFERENCES agent_instances.id ON DELETE CASCADE` AND `inapp_messages.user_id REFERENCES users.id ON DELETE CASCADE`, so truncating either parent cascades to delete inapp_messages rows. Verified empirically: 12 tests run sequentially with shared testcontainer + per-test fixture cycle, no inter-test bleed. Decision: do NOT add `inapp_messages` to the explicit TRUNCATE list — the FK cascade is correct AND adding an explicit reference would tightly couple the test infra to a specific schema topology that future migrations might change. The cascade is defensive-by-default.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] `list_history_for_agent` does NOT take `user_id` parameter (vs. plan spec)**

- **Found during:** Task 1 STEP 1 implementation review against the plan's `<interfaces>` block + `<action>` STEP 1 code template
- **Issue:** The plan's STEP 1 code template (lines 130-159 of the PLAN.md) shows a function signature without a `user_id` parameter, BUT the `<interfaces>` block at line 82-83 says functions in this module "take `conn` + `agent_id` + filter args" — which I initially read as implying `user_id` should also be passed. After reading the existing 9 store functions to confirm conventions, I noticed `fetch_history_for_agent` (line 300) DOES filter on `user_id` at the SQL layer, but `fetch_pending_for_dispatch` (line 109) does NOT (because the dispatcher operates across all users). The new `list_history_for_agent` falls into a third category: the route layer has ALREADY proven ownership via `fetch_agent_instance(conn, agent_id, user_id)`, so adding a redundant `WHERE user_id=$N` here would (a) duplicate the multi-tenant check at two layers, (b) prematurely couple the read-path to single-user-per-agent (future shared-agent designs would have to refactor), (c) require the handler to pass `user_id` to a function that doesn't strictly need it.
- **Fix:** Implemented `list_history_for_agent` per the plan's CODE TEMPLATE verbatim (no `user_id` arg in the signature; SQL only filters on `agent_id` + `status`). The plan's CODE was right; my interpretation of the prose was overly cautious. Documented the rationale in the function's docstring + this Decisions section so future readers don't re-debate it.
- **Files modified:** none beyond what Task 1 specified.
- **Verification:** test_get_messages_cross_user_returns_404 PASSES — cross-user isolation is enforced at the agent_instances layer via the route-side fetch_agent_instance call, exactly as the plan intended.
- **Committed in:** `3a402a2`

### Out-of-scope Discoveries (logged, NOT fixed)

None — the plan's scope is fully covered by Tasks 1-2; no incidental issues surfaced during execution that would warrant deferred-items.md entries.

---

**Total deviations:** 1 design clarification (no actual code change vs. the plan's CODE template — the deviation is in interpretation, not output).
**Impact on plan:** Zero — the plan's intent (single-seam read of terminal-state inapp_messages with handler-side ownership filtering) is preserved verbatim.

## Issues Encountered

- **`asyncio` reaper background-task noise in test stderr.** Some test runs emit `asyncpg.exceptions._base.InterfaceError: cannot call Transaction.__aexit__(): the underlying connection is closed` from `inapp_reaper.reaper_loop` during teardown. This is a pre-existing race between the lifespan-managed reaper background task and the per-test pool teardown — NOT caused by Plan 23-03 changes (verified by running `pytest tests/routes/test_agent_messages_post.py` in isolation: same noise, same cause). Out of scope per executor SCOPE BOUNDARY rule. Tests still pass (the noise is captured stderr, not assertion failures). Pre-existing; not fixed here.

## User Setup Required

None. Plan 23-03 is a code-only feature addition; no env vars, services, or operator runbooks added. The new endpoint is observable purely through HTTP requests against an already-running API server.

## Diff Summary (counted in committed code)

| File | LOC added | LOC removed | Net |
|------|-----------|-------------|-----|
| `api_server/src/api_server/services/inapp_messages_store.py` | 52 | 0 | +52 |
| `api_server/src/api_server/routes/agent_messages.py` | 126 | 0 | +126 |
| `api_server/tests/routes/test_agent_messages_get.py` | 359 | 0 | +359 (new) |
| **Total production code** | **178** | **0** | **+178** (matches plan's "~30 LOC handler + ~25 LOC store" estimate counting docstrings + step-banner comments + Pydantic-style Literal type aliases) |
| **Total test code** | **359** | **0** | **+359** (12 tests, ~25-35 LOC each incl. setup/teardown) |

## Verification Confirmed (per <verification> block)

- `cd api_server && pytest tests/routes/test_agent_messages_get.py -x` → **12 passed** ✓
- `cd api_server && pytest tests/routes/test_agent_messages_post.py tests/routes/test_messages_idempotency_required.py -x` → **14 passed** ✓ (no regression — POST + idempotency tests pass after this plan's changes)
- `grep -cE "^\s*(SELECT|INSERT|UPDATE|DELETE)" src/api_server/routes/agent_messages.py` → **4** (unchanged from pre-plan baseline; SQL stays in services/inapp_messages_store.py)
- `grep -E "list_history_for_agent" src/api_server/services/inapp_messages_store.py` → **1 hit** ✓
- `grep -E '@router\.get\("/agents/\{agent_id\}/messages"' src/api_server/routes/agent_messages.py` → **1 hit** ✓ (route registered)

## Plan must_haves.truths Verification

| Truth | Code/Test |
|-------|-----------|
| 1. GET returns chat history for authenticated user, ORDER BY created_at ASC | `inapp_messages_store.py` line 367-368 (`ORDER BY created_at ASC`) + `test_get_messages_ordered_ascending` |
| 2. Default limit=200; >1000 clamped; <1 → 400 | `_HISTORY_DEFAULT_LIMIT=200` + `_HISTORY_MAX_LIMIT=1000` + `if limit<1: return _err(400, ...)` + `test_get_messages_limit_clamped_to_1000` + `test_get_messages_limit_zero_returns_400` + `test_get_messages_limit_negative_returns_400` |
| 3. `done` rows emit (user, assistant) pair | `routes/agent_messages.py` row-mapping loop lines 290-304 + `test_get_messages_done_row_emits_user_and_assistant` |
| 4. `failed` rows emit (user, error) with verbatim "⚠️ delivery failed: " prefix | `f"⚠️ delivery failed: {err_text}"` at line 314 + `test_get_messages_failed_row_emits_user_and_error` (asserts full string equality) |
| 5. `pending`/`forwarded` rows EXCLUDED | SQL `AND status IN ('done', 'failed')` at store line 367 + `test_get_messages_in_flight_rows_excluded` |
| 6. Cross-user → 404 (avoid existence leak) | `fetch_agent_instance(conn, agent_id, user_id)` at handler line 269 returns None for cross-user → `_err(404, AGENT_NOT_FOUND)` + `test_get_messages_cross_user_returns_404` |

All 6 truths verifiable in committed code. Verifier-ready.

## Self-Check: PASSED

Created files exist on disk:
- `api_server/tests/routes/test_agent_messages_get.py` — FOUND
- `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-03-SUMMARY.md` — FOUND (this file)

Modified files exist with expected changes:
- `api_server/src/api_server/services/inapp_messages_store.py` — `async def list_history_for_agent` at line 328; `ORDER BY created_at ASC` + `status IN ('done', 'failed')` in SQL
- `api_server/src/api_server/routes/agent_messages.py` — `@router.get("/agents/{agent_id}/messages", status_code=200)` at line 209; `_HISTORY_DEFAULT_LIMIT = 200` + `_HISTORY_MAX_LIMIT = 1000` constants; verbatim "⚠️ delivery failed: " prefix at line 314; `fetch_agent_instance` ownership call at line 269; `get_messages` added to `__all__`

Per-task commits in git log:
- `45db02d` Task 1 RED (test) — FOUND
- `3a402a2` Task 1 GREEN (feat) — FOUND

(Task 2 satisfied by RED commit from Task 1 — see Task Commits section note.)

---
*Phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim*
*Plan: 03 — GET /v1/agents/:id/messages chat-history endpoint (D-03 + D-04 + REQ API-02)*
*Completed: 2026-05-02*
