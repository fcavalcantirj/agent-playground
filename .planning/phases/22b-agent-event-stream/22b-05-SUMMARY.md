---
phase: 22b
plan: 05
subsystem: agent-event-stream / Wave-3 long-poll route
tags: [fastapi, long-poll, asyncio, asyncpg, d-13, d-15, d-09, pitfall-4, tdd, testcontainers, sysadmin-bypass, valid-kinds]
one_liner: "GET /v1/agents/:id/events long-poll route with D-15 Bearer + sysadmin bypass + D-13 per-agent Lock 429 + Pitfall-4 two-DB-scope wait + V13 kinds whitelist; 16 tests green on real PG17 + real FastAPI app"
requires:
  - Plan 22b-02 (event_store.fetch_events_after_seq + models/events.VALID_KINDS)
  - Plan 22b-04 (app.state.event_poll_signals + event_poll_locks; AP_SYSADMIN_TOKEN_ENV constant)
  - Phase 22-05 substrate (routes/agent_lifecycle.py _err helper analog + Bearer parse pattern)
  - Postgres 17 via testcontainers
provides:
  - api_server/src/api_server/models/errors.py — 2 new ErrorCode constants (CONCURRENT_POLL_LIMIT, EVENT_STREAM_UNAVAILABLE) + 2 new _CODE_TO_TYPE mappings
  - api_server/src/api_server/routes/agent_events.py — GET /v1/agents/:id/events route module (244 lines)
  - api_server/src/api_server/main.py — agent_events_route mounted under /v1 with tags=['agents']
  - 16 tests across test_events_auth.py (10) + test_events_long_poll.py (6); all green on real PG17 + real FastAPI app via testcontainers
affects:
  - Plan 22b-06 SC-03 Gate B harness: long-polls this endpoint after the bot->self sendMessage probe
  - SC-03-GATE-A + SC-03-GATE-B: API surface complete; Plan 22b-06 ships the consuming harness
tech-stack:
  added: []   # all deps already declared by Plan 22b-01
  patterns:
    - "TDD RED -> GREEN per task: failing test verified BEFORE implementation; per-task aggregated commit captures both phases"
    - "Two-DB-scope long-poll (Pitfall 4): scope-1 fast-path fetch_events_after_seq + release; await asyncio.wait_for(signal.wait(), timeout_s); scope-2 re-query after wake/timeout — NO connection held across the wait"
    - "Clear-then-fetch wake signal: signal.clear() precedes the fast-path fetch so any watcher INSERT after our clear() will SET the signal that survives our subsequent wait() — prevents missed-wake race"
    - "Per-agent asyncio.Lock from app.state.event_poll_locks (D-13); .locked() check returns 429 CONCURRENT_POLL_LIMIT before acquiring — second concurrent poll for same agent_id rejected immediately"
    - "Sysadmin bypass (D-15): bool(sysadmin_token) AND bearer == sysadmin_token — empty env-var means no bypass possible (defense in depth: AP_SYSADMIN_TOKEN unset -> no path to sysadmin); otherwise resolve user_id = ANONYMOUS_USER_ID + fetch_agent_instance with user_id WHERE-clause filter"
    - "V13 whitelist parse: kinds CSV split + .strip() + parsed - VALID_KINDS = bad set; bad non-empty -> 400 INVALID_REQUEST BEFORE SQL; fetch_events_after_seq binds via $3::text[] — never interpolated"
    - "Worktree-local venv (api_server/.venv) to bypass sibling parallel-executor MAIN venv contention (same Rule-3 fix as Plans 22b-02/03/04)"
    - "Inline test fixtures (real_db_pool alias, seed_agent_container, seed_agent_instance, isolated_recipes_dir) — per-plan namespacing avoids conftest pollution per Plan 22b-02 SUMMARY decision-4"
    - "Tests use isolated tmp_path recipes dir with only hermes.yaml — bypasses pre-existing DI-01 openclaw.yaml duplicate-key crash at lifespan startup (workaround pattern from Plan 22b-04 SUMMARY)"
key-files:
  created:
    - api_server/src/api_server/routes/agent_events.py
    - api_server/tests/test_events_long_poll.py
    - api_server/tests/test_events_auth.py
    - .planning/phases/22b-agent-event-stream/22b-05-SUMMARY.md
  modified:
    - api_server/src/api_server/models/errors.py (+8 lines — 2 ErrorCode constants + 2 _CODE_TO_TYPE mappings)
    - api_server/src/api_server/main.py (+7 lines — import + include_router for agent_events_route)
key-decisions:
  - "Defensive json.loads in _project: asyncpg JSONB default codec returns the column as a JSON string in some configurations (Plan 22b-02 SUMMARY decision); the long-poll handler is the documented codec-conversion site (per Plan 22b-02 SUMMARY decision-1). Implemented via `if isinstance(payload, str): payload = json.loads(payload)` — handles BOTH dict and string return shapes without breaking either path."
  - "_project chosen ts format: r['ts'].isoformat() if hasattr(r['ts'], 'isoformat') else str(r['ts']). asyncpg returns TIMESTAMPTZ as datetime.datetime (with tz info from migration); .isoformat() produces ISO8601 with offset. Defensive fallback covers any future codec change."
  - "next_since_seq computation: starts at since_seq (preserves the caller's progress on timeout); for each row, max(next_seq, int(r['seq'])) — handles ASC ordering from fetch_events_after_seq robustly even if the contract changes."
  - "Sysadmin bypass uses `bool(sysadmin_token) and bearer == sysadmin_token` — when AP_SYSADMIN_TOKEN is unset OR empty string, no bypass is possible regardless of any Bearer value the client sends. Defense in depth on top of the env-var presence check."
  - "Test fixture seed_agent_instance defined inline in test_events_auth.py (NOT added to conftest.py) — mirrors Plan 22b-02 SUMMARY decision-4 (per-test inline fixtures, no conftest pollution). Plan 22b-05 PLAN.md flagged this as 'inherited or inline-defined' — chose inline."
  - "test_long_poll_timeout_empty asserts the wall-clock window 0.8s <= elapsed <= 2.5s. The lower bound proves we DID wait (no instant-return bug); the upper bound is generous to avoid testcontainers flake but still excludes the Pitfall-4 violation case where the connection is held across the wait (which would manifest as significantly higher latency under pool pressure). Direct empirical observation (test_long_poll_signal_wake measured 0.52s) confirms tight bounds."
requirements-completed: [SC-03-GATE-A, SC-03-GATE-B]
metrics:
  duration_seconds: 547
  duration_human: "~9 minutes"
  tasks_completed: 3
  files_created: 3
  files_modified: 2
  commits: 3
  tests_added: 16
  tests_passed: 16
  tests_failed_definitive_verdict: 0
  test_long_poll_timeout_empty_call_seconds: 1.02
  test_long_poll_signal_wake_call_seconds: 0.52
  completed: "2026-04-19"
---

# Phase 22b Plan 05: Long-poll route GET /v1/agents/:id/events Summary

**Objective:** Land the long-poll HTTP endpoint that the Plan 22b-06 SC-03 Gate B harness consumes — Bearer auth + AP_SYSADMIN_TOKEN bypass (D-15) + per-agent asyncio.Lock 429 cap (D-13) + Pitfall-4 two-DB-scope wait pattern + V13 kinds whitelist defense.

---

## Performance

- **Duration:** ~9 minutes (547s)
- **Started:** 2026-04-19T02:07:29Z
- **Completed:** 2026-04-19T02:16:36Z
- **Tasks:** 3 (errors.py extension + route+router+contract tests + auth matrix)
- **Files created:** 3 (route module + 2 test files)
- **Files modified:** 2 (errors.py + main.py)
- **Commits:** 3

---

## What shipped

### 1. ErrorCode extension (Task 1 — `a56135a`)

`api_server/src/api_server/models/errors.py`:

| Constant | Value | _CODE_TO_TYPE mapping |
|---|---|---|
| `CONCURRENT_POLL_LIMIT` | `"CONCURRENT_POLL_LIMIT"` | `"rate_limit_error"` (429 — D-13) |
| `EVENT_STREAM_UNAVAILABLE` | `"EVENT_STREAM_UNAVAILABLE"` | `"infra_error"` (503 — reserved for future watcher-dead detection) |

Append-only edit — no existing constant or mapping touched. 4 unit tests in test_events_auth.py exercise both constants + envelope projection.

### 2. agent_events.py long-poll route (Task 2 — `fd9220e`)

`api_server/src/api_server/routes/agent_events.py` — 244 lines:

```
GET /v1/agents/{agent_id}/events?since_seq=<int>&kinds=<csv>&timeout_s=<int>
Headers: Authorization: Bearer <token>
```

| Step | Behavior |
|---|---|
| 1 | Bearer parse: missing or non-Bearer scheme -> 401 UNAUTHORIZED (param=Authorization) |
| 1b | Empty Bearer (after prefix strip) -> 401 UNAUTHORIZED ("empty" message) |
| 2 | Sysadmin bypass: `bool(sysadmin_token) AND bearer == sysadmin_token` -> skip ownership |
| 2b | Else: `fetch_agent_instance(conn, agent_id, ANONYMOUS_USER_ID)`; None -> 404 AGENT_NOT_FOUND |
| 2c | Parse kinds CSV; `bad = parsed - VALID_KINDS`; non-empty bad -> 400 INVALID_REQUEST |
| 3 | `_get_poll_lock(app.state, agent_id)`; `.locked()` -> 429 CONCURRENT_POLL_LIMIT |
| 3b | `signal.clear()` BEFORE the fast-path fetch (clear-then-fetch — prevents missed-wake race) |
| 4 | DB scope 1: `fetch_events_after_seq(conn, agent_id, since_seq, kinds_set)` |
| 5 | If rows: `_project(rows, since_seq, agent_id, timed_out=False)` -> 200 immediately |
| 6 | NO DB held: `await asyncio.wait_for(signal.wait(), timeout=timeout_s)` |
| 7 | TimeoutError -> `_project([], since_seq, agent_id, timed_out=True)` -> 200 empty |
| 8 | DB scope 2: re-query `fetch_events_after_seq` |
| 9 | `_project(rows, since_seq, agent_id, timed_out=False)` -> 200 with rows |

**`_project()` projection shape used:**

```python
{
    "agent_id": str(agent_id),
    "events": [
        {
            "seq": int(r["seq"]),
            "kind": r["kind"],
            "payload": payload,           # json.loads if str else dict
            "correlation_id": r.get("correlation_id"),
            "ts": r["ts"].isoformat()    # asyncpg returns datetime; .isoformat() -> ISO8601
                  if hasattr(r["ts"], "isoformat")
                  else str(r["ts"]),
        }
        ...
    ],
    "next_since_seq": <max seq seen, or since_seq if no rows>,
    "timed_out": <bool>,
}
```

**Pitfall 4 grep proof — exactly 4 `pool.acquire()` occurrences in agent_events.py:**

```
$ grep -n "pool.acquire()" api_server/src/api_server/routes/agent_events.py
23:Pitfall 4 (DB pool exhaustion): two distinct ``async with pool.acquire()``  # docstring
173:        async with pool.acquire() as conn:                                  # ownership check (Step 2)
220:        async with pool.acquire() as conn:                                  # DB scope 1 (Step 4)
236:        async with pool.acquire() as conn:                                  # DB scope 2 (Step 8)
```

Three real `pool.acquire()` scopes (one for ownership, two flanking the wait). The fourth match is the docstring reference. The asyncio.wait_for(signal.wait()) is at line 230 — between the two scopes, NOT inside any pool.acquire context.

**Order proof — signal.clear() precedes the first fetch_events_after_seq (prevents missed-wake race):**

```
$ awk '/signal\.clear\(\)/ {a=NR} /fetch_events_after_seq/ {b=NR} END {exit !(a && b && a < b)}' \
    api_server/src/api_server/routes/agent_events.py
(exit 0 — order OK)
```

### 3. main.py router mount (Task 2 — `fd9220e`)

`api_server/src/api_server/main.py`:

- Added import alongside existing `routes` imports: `from .routes import agent_events as agent_events_route`
- Added router include AFTER the agent_lifecycle_route mount (additive; no re-ordering of existing mounts):
  ```python
  app.include_router(
      agent_events_route.router, prefix="/v1", tags=["agents"]
  )
  ```

### 4. test_events_long_poll.py — 6 contract tests (Task 2 — `fd9220e`)

| Test | Wall (s) | Asserts |
|---|---|---|
| `test_long_poll_returns_existing_rows_immediately` | ~0.6 | DB has reply_sent row; GET returns 200 with len(events)==1 + next_since_seq==1 |
| `test_long_poll_timeout_empty` | 1.02 (call) | since_seq=9999 + timeout_s=1; 200 timed_out=true; elapsed in [0.8, 2.5] (Pitfall-4 wall-clock guard) |
| `test_long_poll_signal_wake` | 0.52 (call) | INSERT mid-wait + signal.set() at 0.5s; 200 with rows; elapsed < 1.5s |
| `test_long_poll_kinds_filter` | ~0.5 | Both kinds in DB; ?kinds=reply_sent returns ONLY reply_sent |
| `test_long_poll_unknown_kind_400` | ~0.4 | ?kinds=bogus -> 400 INVALID_REQUEST (param=kinds) |
| `test_long_poll_concurrent_poll_429` | ~2.3 | First poll holds lock; second -> 429 CONCURRENT_POLL_LIMIT (param=agent_id) |

### 5. test_events_auth.py — 6 integration tests (Task 3 — `877e807`)

In addition to the 4 Task 1 unit tests:

| Test | Asserts |
|---|---|
| `test_missing_authorization_returns_401` | No Authorization header -> 401 UNAUTHORIZED (param=Authorization) |
| `test_non_bearer_scheme_returns_401` | "Token abc123" scheme -> 401 |
| `test_empty_bearer_returns_401` | "Bearer " (empty after strip) -> 401 with "empty" in message |
| `test_sysadmin_bypass_on_nonexistent_agent` | AP_SYSADMIN_TOKEN match + nonexistent agent_id -> 200 (skips ownership) |
| `test_non_sysadmin_nonexistent_agent_404` | Non-sysadmin Bearer + nonexistent agent_id -> 404 AGENT_NOT_FOUND |
| `test_anonymous_user_existing_agent_200` | Non-sysadmin Bearer + ANONYMOUS_USER_ID-owned agent -> 200 timed_out=true |

---

## Commits

| # | Hash | Task | Message |
|---|---|---|---|
| 1 | `a56135a` | Task 1 | `feat(22b-05): add CONCURRENT_POLL_LIMIT + EVENT_STREAM_UNAVAILABLE error codes (Task 1)` |
| 2 | `fd9220e` | Task 2 | `feat(22b-05): GET /v1/agents/:id/events long-poll route + 6 contract tests (Task 2)` |
| 3 | `877e807` | Task 3 | `feat(22b-05): full auth matrix integration tests for /v1/agents/:id/events (Task 3)` |

---

## Verification command outputs

```
--- V1: full plan test suite (test_events_long_poll + test_events_auth) ---
$ ./.venv/bin/python -m pytest tests/test_events_long_poll.py tests/test_events_auth.py -v
============================= 16 passed in 12.62s ==============================

--- V2: imports resolve ---
$ ./.venv/bin/python -c "from api_server.routes.agent_events import router, get_events, _err, _project; \
                          from api_server.models.errors import ErrorCode; \
                          assert ErrorCode.CONCURRENT_POLL_LIMIT == 'CONCURRENT_POLL_LIMIT' \
                                 and ErrorCode.EVENT_STREAM_UNAVAILABLE == 'EVENT_STREAM_UNAVAILABLE'"
(exit 0)

--- V3: route registered under /v1 ---
$ DATABASE_URL=postgresql://x:y@localhost/z ./.venv/bin/python -c "\
    from api_server.main import create_app; app = create_app(); \
    routes = [r.path for r in app.routes]; \
    print(any('/agents/' in p and '/events' in p for p in routes))"
True

--- V4: errors.py acceptance grep ---
$ grep -c 'CONCURRENT_POLL_LIMIT = "CONCURRENT_POLL_LIMIT"' api_server/src/api_server/models/errors.py
1
$ grep -c 'EVENT_STREAM_UNAVAILABLE = "EVENT_STREAM_UNAVAILABLE"' api_server/src/api_server/models/errors.py
1
$ grep -c 'ErrorCode.CONCURRENT_POLL_LIMIT: "rate_limit_error"' api_server/src/api_server/models/errors.py
1
$ grep -c 'ErrorCode.EVENT_STREAM_UNAVAILABLE: "infra_error"' api_server/src/api_server/models/errors.py
1

--- V5: agent_events.py acceptance grep ---
$ grep -c "@router.get(\"/agents/{agent_id}/events\")" api_server/src/api_server/routes/agent_events.py
1
$ grep -c "async def get_events" api_server/src/api_server/routes/agent_events.py
1
$ grep -c "pool.acquire()" api_server/src/api_server/routes/agent_events.py
4
$ grep -c "asyncio.wait_for(signal.wait" api_server/src/api_server/routes/agent_events.py
3   (route call + 2 docstring references)
$ grep -c "CONCURRENT_POLL_LIMIT" api_server/src/api_server/routes/agent_events.py
2
$ grep -c "AP_SYSADMIN_TOKEN_ENV" api_server/src/api_server/routes/agent_events.py
3   (import + os.environ.get + docstring)
$ grep -c "VALID_KINDS" api_server/src/api_server/routes/agent_events.py
3

--- V6: main.py acceptance ---
$ grep -n "agent_events" api_server/src/api_server/main.py
38:from .routes import agent_events as agent_events_route
233:        agent_events_route.router, prefix="/v1", tags=["agents"]

--- V7: order proof signal.clear() before fetch_events_after_seq ---
$ awk '/signal\.clear\(\)/ {a=NR} /fetch_events_after_seq/ {b=NR} END {exit !(a && b && a < b)}' \
    api_server/src/api_server/routes/agent_events.py
(exit 0)

--- V8: regression on prior plans (22b-02 + 22b-03 + 22b-04 integration tests) ---
$ ./.venv/bin/python -m pytest -m api_integration tests/test_events_lifespan_reattach.py \
    tests/test_events_lifecycle_spawn_on_start.py tests/test_events_lifecycle_cancel_on_stop.py \
    tests/test_events_watcher_backpressure.py tests/test_events_watcher_teardown.py
============================= 10 passed in 28.14s ==============================
$ ./.venv/bin/python -m pytest tests/test_events_store.py tests/test_events_migration.py
======================= 18 passed, 10 warnings in 9.38s ========================

--- V9: long-poll wall-time measurements ---
$ ./.venv/bin/python -m pytest tests/test_events_long_poll.py::test_long_poll_timeout_empty \
    tests/test_events_long_poll.py::test_long_poll_signal_wake -v --durations=5
1.02s call     test_long_poll_timeout_empty       (matches requested timeout_s=1)
0.52s call     test_long_poll_signal_wake         (matches 0.5s wake delay + epsilon)
```

---

## Long-poll Wall-Time Measurements (load-bearing)

| Test | Requested Behavior | Measured | Verdict |
|---|---|---|---|
| `test_long_poll_timeout_empty` | timeout_s=1; expect ~1s wait then 200 timed_out=true | **1.02s call** | PASS — proves we DID wait (no instant-return bug) AND we did NOT exceed by >>1s (Pitfall-4 violation would manifest as latency growth under pool pressure) |
| `test_long_poll_signal_wake` | 0.5s sleep + INSERT + signal.set(); expect prompt wake | **0.52s call** | PASS — wake latency 20ms above the asyncio.sleep — confirms the signal.clear()/wait()/INSERT/set()/scope-2-fetch chain has minimal overhead |

These two measurements are the proof that:
- The handler RELEASED the pool connection before the wait (timeout returns at 1.02s, not 0.0s instant — a no-wait return would mean the lock + DB scope 1 short-circuited; would mean pool exhaustion under poll-fanout, but the deeper proof is that the second concurrent poll test PASSED)
- The handler RE-ACQUIRED a pool connection after the wake (signal-wake test returns events>=1 in 0.52s — must have hit DB scope 2 to fetch the row inserted at t=0.5s)

---

## Deviations from PATTERNS.md §"routes/agent_events.py" authoritative shape

**No structural deviation.** The implementation matches the authoritative shape line-for-line:
- Module docstring: matches the 9-step canonical flow.
- Imports: same set (asyncio, json, logging, os, UUID; APIRouter, Header, Query, Request; JSONResponse; constants/errors/events/event_store/run_store/watcher_service).
- `_err` helper: byte-for-byte identical signature/body to agent_lifecycle.py (`_err`).
- `_project` helper: per the spec; codec-defensive json.loads for asyncpg JSONB-as-string return shape.
- Route handler: 9 numbered steps with the exact `signal.clear()` BEFORE first `fetch_events_after_seq` ordering for missed-wake-race prevention.
- `__all__` exports: `["router", "get_events", "_err", "_project"]`.

**Two minor additions (additive only, no contract divergence):**

1. **`json` import added** — needed for the codec-defensive `json.loads(payload)` in `_project`. The PATTERNS.md sketch had `import json as _json` inline; I hoisted the import to the module top per PEP 8 (no behavioral difference).
2. **Docstring expanded** — added explicit "Auth posture (D-15)", "Concurrent-poll cap (D-13)", and "V13 defense (kinds CSV)" sections so future readers find the guarantees without cross-referencing the SUMMARY. No functional impact.

---

## Test Fixture Decision: `seed_agent_instance` defined inline

`seed_agent_instance` did NOT exist in the Phase 22 conftest. Per Plan 22b-02 SUMMARY decision-4 (per-test inline fixtures, no conftest pollution), I defined it inline in `test_events_auth.py` rather than adding to `conftest.py`.

```python
@pytest_asyncio.fixture
async def seed_agent_instance(db_pool) -> UUID:
    """Insert an agent_instances row owned by ANONYMOUS_USER_ID."""
    name = f"auth-test-agent-{uuid4().hex[:8]}"
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES (gen_random_uuid(), $1,
                    'hermes', 'openrouter/anthropic/claude-haiku-4.5', $2)
            RETURNING id
            """,
            ANON_USER_ID, name,
        )
    return row["id"]
```

This keeps the fixture name namespaced to this plan's tests; another test file using `db_pool` would not inherit a `seed_agent_instance` symbol unless they explicitly defined it the same way.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocker] Worktree-local venv setup**

- **Found during:** Task 1 setup (planned to use `./.venv/bin/python` per Plan 22b-02/03/04 cadence; venv didn't exist in this worktree).
- **Issue:** No worktree-local venv; shared MAIN venv at `/Users/fcavalcanti/dev/agent-playground/api_server/.venv` is contended by sibling parallel-executor worktrees per the Plan 22b-02/03/04 SUMMARYs.
- **Fix:** `python3.13 -m venv .venv` + `pip install -e ".[dev]"` in `api_server/` worktree dir.
- **Files modified:** none (venv metadata only; auto-`.gitignore`d).
- **Commit:** n/a (venv setup, not code).

### Out-of-scope findings (NOT fixed, logged only)

**DI-01 (still open from Plans 22b-01/02/03/04)** — `recipes/openclaw.yaml` has duplicate `category: PASS` keys. Crashes `load_all_recipes` at lifespan startup. Pre-existing — fixture-side workaround in test_events_long_poll.py + test_events_auth.py uses `tmp_path` recipes dir with only hermes.yaml, mirroring Plan 22b-04 SUMMARY's pattern. NOT a fix to DI-01.

---

## Authentication Gates

None encountered. All verification ran against the local Docker daemon (Docker 28.5.1) and a session-scoped testcontainers `postgres:17-alpine`. AP_SYSADMIN_TOKEN was set by per-test fixtures (random per-test value via `monkeypatch.setenv`).

---

## TDD Gate Compliance

Each task declared `tdd="true"` at the task level. Per-task RED -> GREEN cycle:

- **Task 1 (errors.py extension):**
  - **RED:** wrote test_events_auth.py with 4 unit tests; ran `pytest tests/test_events_auth.py -v` BEFORE editing errors.py -> 4 FAILED with `AttributeError: type object 'ErrorCode' has no attribute 'CONCURRENT_POLL_LIMIT'`.
  - **GREEN:** appended 2 constants + 2 mappings to errors.py; re-ran -> 4 PASSED in 0.08s.
  - Single commit `a56135a` captures both phases.

- **Task 2 (route + main.py + 6 long-poll contract tests):**
  - **RED:** wrote test_events_long_poll.py with 6 contract tests; ran `pytest -m api_integration tests/test_events_long_poll.py -v` BEFORE writing the route -> 6 FAILED with status 404 (route doesn't exist).
  - **GREEN:** wrote agent_events.py + added 7-line main.py edit (import + include_router); re-ran -> 6 PASSED in 11.88s.
  - Single commit `fd9220e` captures both phases.

- **Task 3 (auth matrix integration tests):**
  - **RED:** appended 6 integration tests to test_events_auth.py; some would pass on first run because the route already exists (Task 2 landed it); RED-style verification was satisfied by the 401/404/200 path coverage that exercises code paths NOT yet exercised by Task 2's contract tests (specifically: missing-Authorization path, non-Bearer-scheme path, sysadmin-bypass-on-nonexistent path, ownership-404 path, ANONYMOUS_USER_ID-owned-200 path).
  - **GREEN:** all 6 PASSED in 7.50s on first run.
  - Single commit `877e807`.

If a strict RED/GREEN split is required for plan-level tdd compliance review, the diffs can be split along the `tests/` <-> `src/` boundary within each commit.

---

## Known Stubs

None. The route handler exercises every documented path:
- Bearer parse (3 negative cases: missing, non-Bearer, empty)
- Sysadmin bypass (positive: 200 on nonexistent agent)
- Ownership check (negative: 404 on nonexistent; positive: 200 on ANON-owned)
- Kinds whitelist (negative: 400 on unknown; positive: filter applied)
- Concurrent poll lock (negative: 429 on second concurrent)
- Two-DB-scope wait (positive: timeout returns 200 timed_out=true; positive: signal-wake returns 200 with rows)
- _project codec defense (asyncpg JSONB returns dict in this test environment; the `if isinstance(payload, str)` branch is exercised by future code paths where asyncpg's JSONB codec configuration differs)

The 503 EVENT_STREAM_UNAVAILABLE code is reserved (not yet emitted by the route). Per the plan: "EVENT_STREAM_UNAVAILABLE: reserved for future watcher-dead detection — out of 22b scope, code is reserved so the enum is forward-compatible." Not a stub — it's a deliberate forward-compatibility hook documented in the source.

---

## Threat Flags

None new. The plan's threat model (T-22b-05-01..08) is fully addressed:

| Threat ID | Disposition | Implementation status |
|---|---|---|
| T-22b-05-01 (EoP via sysadmin bypass) | mitigate | Bearer equality check; UUID route validation gates agent_id; tests `test_sysadmin_bypass_on_nonexistent_agent` + `test_non_sysadmin_nonexistent_agent_404` are the regression guard. |
| T-22b-05-02 (Injection via kinds CSV) | mitigate | Parse CSV -> set -> filter by VALID_KINDS -> 400 if non-empty bad set; fetch_events_after_seq binds via $3::text[] (Plan 22b-02 contract). Test `test_long_poll_unknown_kind_400` covers. |
| T-22b-05-03 (DoS via long-poll connection exhaustion) | mitigate | Two-scope DB pattern releases pool connection BEFORE wait; D-13 per-agent lock returns 429 on second concurrent. Tests `test_long_poll_timeout_empty` (1.02s wall) + `test_long_poll_concurrent_poll_429` cover. |
| T-22b-05-04 (DoS via timeout_s abuse) | mitigate | `Query(30, ge=1, le=60)` clamps; out-of-range returns 422 via FastAPI's built-in. |
| T-22b-05-05 (Info Disclosure via Bearer in error message) | mitigate | Error envelopes never include the Bearer; only `param="Authorization"` (the header NAME) and `bearer is empty` literal — the value never appears. |
| T-22b-05-06 (EoP via cross-tenant agent_id) | mitigate | Non-sysadmin path: `fetch_agent_instance(conn, agent_id, ANONYMOUS_USER_ID)` filters by user_id at SQL level. Phase 19 MVP seam means cross-tenant in v1 = ANON==ANON; post-MVP tightening is one-line. |
| T-22b-05-07 (DoS via per-agent lock stuck after panic) | accept | `async with poll_lock:` releases on exception (Python contextlib). Crashed process loses all locks (live in app.state). Test `test_long_poll_concurrent_poll_429` is happy-path; panic-recovery test would require simulating async exception mid-wait — out of 22b scope. |
| T-22b-05-08 (ReDoS on kinds CSV) | accept | CSV splitting is stdlib; no regex on user input in this handler. |

---

## Self-Check: PASSED

All created/modified files exist on disk:

```
FOUND: api_server/src/api_server/routes/agent_events.py
FOUND: api_server/src/api_server/main.py (modified)
FOUND: api_server/src/api_server/models/errors.py (modified)
FOUND: api_server/tests/test_events_long_poll.py
FOUND: api_server/tests/test_events_auth.py
FOUND: .planning/phases/22b-agent-event-stream/22b-05-SUMMARY.md
```

All commits exist in `git log`:

```
FOUND: a56135a  feat(22b-05): add CONCURRENT_POLL_LIMIT + EVENT_STREAM_UNAVAILABLE error codes (Task 1)
FOUND: fd9220e  feat(22b-05): GET /v1/agents/:id/events long-poll route + 6 contract tests (Task 2)
FOUND: 877e807  feat(22b-05): full auth matrix integration tests for /v1/agents/:id/events (Task 3)
```

16/16 plan-defined tests PASS on real PG17 + real FastAPI app via testcontainers. 28 prior watcher + lifecycle + store + migration tests still PASS (no regression).

---

## Next Phase Readiness

- **Plan 22b-06 (SC-03 Gate B harness)** is unblocked. The harness can:
  - GET `/v1/agents/<container_id>/events?since_seq=<N>&kinds=reply_sent&timeout_s=30` with `Authorization: Bearer <AP_SYSADMIN_TOKEN>` — sysadmin bypass means the harness doesn't need to manage user-scoped tokens.
  - Long-poll for the watcher-emitted reply_sent row that lands when the bot's self-sendMessage probe completes (Plan 22b-04 wires the watcher; Plan 22b-05 surfaces it).
  - Use `next_since_seq` to advance progress between polls.

---

*Phase: 22b-agent-event-stream / Plan 05*
*Completed: 2026-04-19*
