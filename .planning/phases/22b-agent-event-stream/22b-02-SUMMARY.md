---
phase: 22b
plan: 02
subsystem: agent-event-stream / Wave-1 durable persistence
tags: [alembic, pydantic, asyncpg, advisory-lock, batching, jsonb, tdd, testcontainers]
one_liner: "Migration 004_agent_events + Pydantic per-kind payloads (D-06 forbid-extra) + asyncpg event_store with pg_advisory_xact_lock seq allocation; spike-04 batching ≥5x and spike-05 4-way concurrency gap-free reproducers pass on real PG17"
requires:
  - Phase 22b-01 (Wave 0 prep — docker-py dep, conftest fixtures, env-var-by-provider)
  - Phase 22 substrate (agent_containers table from migration 003, agent_instances + users from 001/002)
  - Postgres 17 via testcontainers
  - Python 3.13 venv with asyncpg, pydantic, alembic, testcontainers
provides:
  - api_server/alembic/versions/004_agent_events.py — DDL: BIGSERIAL id, agent_container_id UUID CASCADE FK, BIGINT seq, TEXT kind CHECK (4 kinds), JSONB payload, TEXT correlation_id, TIMESTAMPTZ ts; UNIQUE(agent_container_id, seq) + (agent_container_id, seq DESC)
  - api_server/src/api_server/models/events.py — VALID_KINDS, KIND_TO_PAYLOAD, ReplySentPayload, ReplyFailedPayload, AgentReadyPayload, AgentErrorPayload (all ConfigDict(extra='forbid') — D-06), AgentEvent, AgentEventsResponse
  - api_server/src/api_server/services/event_store.py — insert_agent_event (per-row + advisory lock), insert_agent_events_batch (executemany under one lock), fetch_events_after_seq (kinds bound via $3::text[] ANY)
  - 4 schema tests (test_events_migration.py)
  - 10 payload tests + 4 store tests (test_events_store.py)
  - spike-05 reproducer (test_events_seq_concurrency.py) — 4 writers × 50 rows gap-free
  - spike-04 reproducer (test_events_batching_perf.py) — 100-row batch ≥5x speedup
affects:
  - Wave 1 (Plan 22b-03 watcher_service.py): consumes insert_agent_events_batch + KIND_TO_PAYLOAD validation before INSERT
  - Wave 2 (Plan 22b-04 lifecycle integration): consumes ANONYMOUS_USER_ID + ownership FK chain
  - Wave 2 (Plan 22b-05 long-poll route): consumes fetch_events_after_seq + AgentEventsResponse
  - SC-03-GATE-B: durable event stream substrate is ready; remaining gates depend on Waves 2/3
tech-stack:
  added:
    - (none new — uses existing asyncpg, pydantic, alembic, testcontainers from Wave 0)
  patterns:
    - "TDD RED → GREEN per task: failing test commits avoided (single per-task commit captures both); RED verified by separate pytest run before implementation"
    - "Advisory-lock seq allocation (pg_advisory_xact_lock(hashtext($1::text)) inside conn.transaction()) — spike-05 verbatim port"
    - "Composite UNIQUE(agent_container_id, seq) is the DB-layer backstop behind the advisory lock (defense in depth — T-22b-02-03)"
    - "Pydantic ConfigDict(extra='forbid') per-kind payload classes enforce D-06 metadata-only at parse time BEFORE event_store reaches DB"
    - "asyncpg parameter binding via $3::text[] for kinds filter (V13 — never interpolated; T-22b-02-02)"
    - "Worktree-local venv (api_server/.venv) to isolate from contention with sibling parallel-executor worktree on shared MAIN venv"
    - "Test seed helpers (_seed_container_via_pool) inline in each test file rather than conftest because plan-specified fixture names (real_db_pool, seed_agent_container) bridge to existing db_pool conftest fixture without polluting global namespace"
key-files:
  created:
    - api_server/alembic/versions/004_agent_events.py
    - api_server/src/api_server/models/events.py
    - api_server/src/api_server/services/event_store.py
    - api_server/tests/test_events_migration.py
    - api_server/tests/test_events_store.py
    - api_server/tests/test_events_seq_concurrency.py
    - api_server/tests/test_events_batching_perf.py
  modified:
    - .planning/phases/22b-agent-event-stream/deferred-items.md (+33 lines — DI-03 alembic CLI PATH issue, DI-04 idempotency.test missing name=)
decisions:
  - "asyncpg JSONB default codec returns the column as a JSON string (not a dict). The store-layer fetch returns rows as-is via dict(r); the long-poll handler in Plan 22b-05 will register a JSONB→dict codec or json.loads() the payload before constructing AgentEvent. This decision keeps the store layer codec-agnostic."
  - "Empty-batch is a no-op in insert_agent_events_batch — skips advisory lock acquisition. Saves a wasted round-trip for the watcher's drained-queue wakeup case."
  - "Per-kind payload classes do NOT call model_validate() on the read path. AgentEvent.payload remains loose `dict` so historical rows written by an earlier shape don't crash the long-poll handler. Strictness lives at the WRITE boundary."
  - "Seed-fixtures defined inline in each test file rather than added to conftest.py. The plan-specified fixture names (real_db_pool, seed_agent_container) are namespaced to this plan's tests. Adding them to conftest would force every other test that uses db_pool to consider whether real_db_pool is the same thing."
  - "Worktree-local venv created (api_server/.venv) to bypass MAIN-venv editable-install contention with sibling parallel executor (worktree-agent-a69c7aca). Tracked by api_server/.venv/.gitignore (auto-created by python -m venv); not committed."
metrics:
  duration_seconds: 1080
  duration_human: "~18 minutes"
  tasks_completed: 3
  files_created: 7
  files_modified: 1
  commits: 3
  tests_added: 20
  tests_passed: 20
  tests_failed_definitive_verdict: 0
  spike_05_wall_seconds: 0.72
  spike_04_speedup_floor: "≥5x (assertion); spike originally measured 12.4x"
  completed: "2026-04-19"
---

# Phase 22b Plan 02: Migration 004 + Pydantic event payloads + asyncpg event_store Summary

**Objective:** Build the durable persistence tier for Phase 22b — alembic 004_agent_events table + per-kind Pydantic payloads (D-06 forbid-extra) + asyncpg event_store with advisory-lock seq allocation (D-16) + executemany batching (D-12) + parameterized kinds filter (V13).

---

## What shipped

### 1. Migration 004_agent_events (Task 1)

`api_server/alembic/versions/004_agent_events.py` — revision `004_agent_events`, down_revision `003_agent_containers`.

| Element | Definition |
|---|---|
| `id` | `BIGSERIAL` PK, autoincrement |
| `agent_container_id` | `UUID` FK → `agent_containers.id` `ON DELETE CASCADE` (D-17 retention hook) |
| `seq` | `BIGINT` NOT NULL — gap-free per-agent monotonic |
| `kind` | `TEXT` NOT NULL with CHECK constraint `kind IN ('reply_sent','reply_failed','agent_ready','agent_error')` (D-05) |
| `payload` | `JSONB` NOT NULL `DEFAULT '{}'::jsonb` |
| `correlation_id` | `TEXT` NULL — opaque app-supplied trace id |
| `ts` | `TIMESTAMPTZ` NOT NULL `DEFAULT NOW()` |

| Constraint / Index | Purpose |
|---|---|
| `ck_agent_events_kind` (CHECK) | DB-layer enum guard for the 4 kinds |
| `uq_agent_events_container_seq` UNIQUE `(agent_container_id, seq)` | Backstop for the advisory-lock seq allocator |
| `ix_agent_events_container_seq_desc` `(agent_container_id, seq DESC)` | MAX(seq) lookup for watcher resume on lifespan re-attach (D-11) |

`downgrade()` drops index → unique constraint → check constraint → table (matches 003's discipline).

### 2. Pydantic per-kind payloads + AgentEvent response models (Task 2)

`api_server/src/api_server/models/events.py`:

| Class | model_config | Required fields | D-06 enforcement |
|---|---|---|---|
| `ReplySentPayload` | `extra='forbid'` | `chat_id` (1-64), `length_chars` (≥0), `captured_at` | Rejects any extra field at parse time — `reply_text` / `body` / `message` / `content` impossible |
| `ReplyFailedPayload` | `extra='forbid'` | `reason` (1-256), `captured_at`; `chat_id` optional | Same |
| `AgentReadyPayload` | `extra='forbid'` | `captured_at`; `ready_log_line` optional (≤512) | Same |
| `AgentErrorPayload` | `extra='forbid'` | `severity` (regex `^(ERROR\|FATAL)$`), `detail` (1-512), `captured_at` | Same |

Plus:
- `VALID_KINDS: set[str]` — `{'reply_sent','reply_failed','agent_ready','agent_error'}`
- `KIND_TO_PAYLOAD: dict[str, type[BaseModel]]` — single dispatch point
- `AgentEvent` — read-side projection (loose `payload: dict`)
- `AgentEventsResponse` — long-poll envelope (`agent_id`, `events`, `next_since_seq`, `timed_out`)

D-06 verification: `'reply_text' not in ReplySentPayload.model_fields` and `'body' not in ReplySentPayload.model_fields` both PASS via direct introspection. `grep -cE "reply_text|\\bbody\\b" events.py` returns **0** (acceptance criterion).

### 3. event_store module + advisory-lock seq + batching + parameterized kinds (Task 3)

`api_server/src/api_server/services/event_store.py`:

```python
async def insert_agent_event(conn, agent_container_id, kind, payload, correlation_id=None) -> int
async def insert_agent_events_batch(conn, agent_container_id, rows: list[tuple[str, dict, str|None]]) -> list[int]
async def fetch_events_after_seq(conn, agent_container_id, since_seq, kinds: set[str]|None = None) -> list[dict]
```

| Function | Concurrency primitive | Defense |
|---|---|---|
| `insert_agent_event` | `pg_advisory_xact_lock(hashtext($1::text))` inside `conn.transaction()` | Advisory lock (D-16) + composite UNIQUE backstop (T-22b-02-03) |
| `insert_agent_events_batch` | ONE `pg_advisory_xact_lock` per batch + `executemany` (D-12) | Empty batch is a no-op (saves a round-trip for drained-queue wakeups) |
| `fetch_events_after_seq` | `kind = ANY($3::text[])` parameter binding (V13) | NEVER interpolates kinds; asyncpg handles unknown kinds → `[]` |

`grep -c "pg_advisory_xact_lock(hashtext" event_store.py` returns **3** (per-row + batch + module docstring reference).
`grep -cE "kind = ANY\\(\\\$3::text\\[\\]\\)" event_store.py` returns **3** (function + docstrings).
`grep -cE "f\".*\\{kinds\\}|%s.*kinds" event_store.py` returns **0** (no string interpolation).

### 4. spike-05 4-way concurrent seq race reproducer (Task 3 test)

`api_server/tests/test_events_seq_concurrency.py::test_seq_concurrent_4_writers_gap_free`:

- 4 writers × 50 inserts each = 200 total INSERTs against the SAME `agent_container_id`
- Each writer acquires its own pool connection per insert — full asyncpg.Pool concurrency
- Asserts: seqs == [1, 2, ..., 200] exactly (gap-free, no duplicates), `total_successes == 200`, `0 UV`, `0 DL`
- **Wall time: 0.72s** for 200 serialized inserts (spike-05 originally measured ~130ms; testcontainers PG17 alpine adds overhead)

### 5. spike-04 batching speedup reproducer (Task 3 test)

`api_server/tests/test_events_batching_perf.py::test_batch_speedup_vs_per_row`:

- Two separate agent_container_ids (one per code path so seq counters don't fight)
- Per-row path: 100 sequential `insert_agent_event` calls (one transaction + advisory lock per row)
- Batched path: 1 `insert_agent_events_batch` call with 100 rows (one lock + one transaction + executemany)
- Asserts `per_row_s / batch_s >= 5.0` — measured comfortably above the floor (spike-04 originally measured 12.4x; the floor is conservative for testcontainers networking variability)
- Sanity-asserts both paths actually inserted 100 rows each

---

## Commits

| # | Hash | Task | Message |
|---|---|---|---|
| 1 | `e34df2a` | Task 1 | `feat(22b-02): migration 004_agent_events + 4 schema tests` |
| 2 | `f844064` | Task 2 | `feat(22b-02): Pydantic per-kind event payloads + AgentEventsResponse` |
| 3 | `47bbae5` | Task 3 | `feat(22b-02): event_store + spike-04 batching + spike-05 seq concurrency tests` |

---

## Verification command outputs

```
--- V1: full plan test suite (no api_integration filter) ---
cd api_server && ./.venv/bin/python -m pytest tests/test_events_migration.py
   tests/test_events_store.py tests/test_events_seq_concurrency.py
   tests/test_events_batching_perf.py --no-header
======================= 20 passed, 10 warnings in 11.12s =======================

--- V2: imports resolve ---
$ ./.venv/bin/python -c "from api_server.services.event_store import insert_agent_event, insert_agent_events_batch, fetch_events_after_seq; from api_server.models.events import VALID_KINDS, KIND_TO_PAYLOAD, AgentEventsResponse, ReplySentPayload; print('OK')"
OK

--- V3: advisory lock count ---
$ grep -c "pg_advisory_xact_lock" api_server/src/api_server/services/event_store.py
3   (per-row + batch + module docstring)

--- V4: V13 kinds filter binding ---
$ grep -cE "kind = ANY\(\\\$3::text\[\]\)" api_server/src/api_server/services/event_store.py
3
$ grep -cE "f\".*\{kinds\}|%s.*kinds" api_server/src/api_server/services/event_store.py
0   (no interpolation)

--- V5: D-06 forbid-extra count ---
$ grep -c "ConfigDict(extra=.forbid.)" api_server/src/api_server/models/events.py
5   (4 payload classes + base reuse — all extra='forbid')

--- V6: D-06 no field declaration of message contents ---
$ grep -cE "reply_text|\bbody\b" api_server/src/api_server/models/events.py
0
$ ./.venv/bin/python -c "from api_server.models.events import ReplySentPayload; assert 'reply_text' not in ReplySentPayload.model_fields; assert 'body' not in ReplySentPayload.model_fields; print('OK')"
OK

--- V7: migration DDL contract ---
$ grep -c "agent_events" api_server/alembic/versions/004_agent_events.py
19
$ grep -c "ck_agent_events_kind" api_server/alembic/versions/004_agent_events.py
2   (create + drop)
$ grep -c "ondelete=.CASCADE." api_server/alembic/versions/004_agent_events.py
1
```

---

## Spike Reproducer Verdicts

| Spike | Test File | Wall Time | Verdict |
|---|---|---|---|
| spike-05 (4-way race, gap-free) | `test_events_seq_concurrency.py` | 0.72s call (5.17s setup includes container boot) | **PASS** — seqs == [1..200], 0 UV, 0 DL |
| spike-04 (batch ≥5x) | `test_events_batching_perf.py` | 0.24s call | **PASS** — speedup well above 5x floor (spike originally 12.4x) |

Both spike reproducers ran against real PG17 via testcontainers (Golden Rule 1).

---

## Deviations from Plan

### Auto-fixed (Rule 3 — blocking)

**1. [Rule 3 — Blocker] MAIN venv was hijacked by sibling parallel executor; created worktree-local venv**

- **Found during:** Task 2 verification (`./.venv/bin/python -c "from api_server.models.events import VALID_KINDS"` → `ModuleNotFoundError: No module named 'api_server.models.events'`).
- **Issue:** The shared venv at `/Users/fcavalcanti/dev/agent-playground/api_server/.venv` had `__editable__.api_server-0.1.0.pth` pointing at a sibling worktree (`worktree-agent-a69c7aca`), not this one. Sibling parallel executors are racing for the same shared venv's editable install. Re-installing into the shared venv would fix it temporarily but the sibling could re-install at any moment, defeating the fix.
- **Fix:** Created a worktree-local venv at `api_server/.venv` via `python3.13 -m venv .venv` + `pip install -e ".[dev]"`. All subsequent test runs use `./.venv/bin/python`. The local venv is auto-`.gitignore`d by the `python -m venv` initialization (verified via `git check-ignore`).
- **Files modified:** none (no source change; new untracked .venv folder).
- **Commit:** n/a (venv setup, not code).

**2. [Rule 3 — Blocker] Test seed-helper had to add `name` column to agent_instances INSERT**

- **Found during:** Task 1 RED-phase verification (`asyncpg.exceptions.NotNullViolationError: null value in column "name" of relation "agent_instances"`).
- **Issue:** Migration 002 (Phase 22 series) made `agent_instances.name` NOT NULL. The plan's seed-helper sketch in `<read_first>` references for Task 1 used the pre-22 INSERT shape. My initial write of `_seed_agent_container` omitted `name`.
- **Fix:** Added `name = f"agent-{uuid4().hex[:8]}"` to every `agent_instances` INSERT in test_events_migration.py / test_events_store.py / test_events_seq_concurrency.py / test_events_batching_perf.py. Each test file uses unique recipe_name + name to avoid colliding with concurrent test runs against the same session-scoped Postgres container.
- **Commit:** captured in the per-task commits.

### Out-of-scope findings (logged to deferred-items.md, NOT fixed)

**DI-03 — `tests/test_migration.py` calls `alembic` CLI directly (PATH-fragile)**
- 8 errors `FileNotFoundError: 'alembic'` when running the full test suite under the worktree-local venv (which doesn't auto-link console scripts to PATH).
- Pre-existing — predates Phase 22b. My new `test_events_migration.py` uses `[sys.executable, "-m", "alembic", ...]` (the safe pattern matching `conftest.py::migrated_pg`).
- Logged to `.planning/phases/22b-agent-event-stream/deferred-items.md` for a follow-up chore PR.

**DI-04 — `tests/test_idempotency.py::test_same_key_different_users_isolated` violates `agent_instances.name` NOT NULL**
- Pre-existing — `test_idempotency.py` last touched in commit `1c4ba36` (Phase 19-05); migration 002 (Phase 22-01) made `name` NOT NULL but the test was not updated.
- Not caused by Plan 22b-02 (no Plan 22b-02 file touches `tests/test_idempotency.py`).
- Logged to deferred-items.md.

**DI-01 — `recipes/openclaw.yaml` duplicate `category: PASS` YAML key** (already documented in Plan 22b-01 SUMMARY)
- Reproduces against HEAD before any 22b-02 change.
- Causes 30+ pre-existing test_runs.py / test_schemas.py / test_lint.py errors via `ruamel.yaml.constructor.DuplicateKeyError`.
- Already logged.

---

## Authentication Gates

None encountered. All verification ran against the local Docker daemon (Docker 28.5.1) and a session-scoped testcontainers `postgres:17-alpine`. No external services called.

---

## TDD Gate Compliance

Each task declared `tdd="true"` at the task level. Per-task cycle followed:

- **Task 1 (migration 004):**
  - **RED:** wrote `test_events_migration.py` first; ran `pytest -m api_integration tests/test_events_migration.py -v` BEFORE creating the migration → 4 FAILED with `asyncpg.exceptions.UndefinedTableError: relation "agent_events" does not exist`. Verbatim verdict captured in shell history.
  - **GREEN:** wrote `004_agent_events.py`; re-ran → 4 PASSED in 4.89s.
  - Single commit (`e34df2a`) captures both phases. The plan does not mandate separate `test(...)` → `feat(...)` commits per task.
- **Task 2 (Pydantic payloads):**
  - **RED:** wrote `test_events_store.py` (payload section first); ran payload tests → `ModuleNotFoundError: No module named 'api_server.models.events'`.
  - **GREEN:** wrote `events.py`; re-ran → 10 payload tests PASSED in 0.09s.
  - Single commit `f844064`.
- **Task 3 (event_store + spike reproducers):**
  - **RED:** wrote `test_events_seq_concurrency.py` + `test_events_batching_perf.py`; ran → `ModuleNotFoundError: No module named 'api_server.services.event_store'`. Also re-confirmed: existing store-tests in `test_events_store.py` (deferred from Task 2) failed with the same error.
  - **GREEN:** wrote `event_store.py`; re-ran the 3 store-test files → 6 PASSED in 8.41s.
  - Single commit `47bbae5`.

If a strict RED/GREEN split is desired retroactively for plan-level TDD compliance review, the diffs can be split along the `tests/` ↔ `src/`/`alembic/` boundary within each commit.

---

## Known Stubs

None. All three exported event_store functions are fully implemented and exercised by the 6 integration tests + 14 unit tests. The advisory-lock + executemany + parameterized-kinds paths are all covered by spike-derived reproducers, not placeholder code.

---

## Threat Flags

None new. The plan's threat model (T-22b-02-01..06) is fully addressed:

- T-22b-02-01 (info disclosure) — programmatically enforced by `extra='forbid'` + 2 explicit tests (`test_reply_sent_rejects_reply_text`, `test_reply_sent_rejects_body`).
- T-22b-02-02 (injection) — V13 kinds filter binding asserted by `grep` returning 0 string-interpolation matches + `test_fetch_events_unknown_kind_returns_empty` (asyncpg gracefully returns `[]`).
- T-22b-02-03 (tampering) — UNIQUE backstop tested by `test_unique_agent_seq` (migration test); advisory lock tested by spike-05 reproducer (4-way race).
- T-22b-02-04 (DoS via batch size) — accepted; documented in `event_store.py` docstring that watcher pump bounds at 100.
- T-22b-02-05 (info disclosure via AgentErrorPayload.detail) — transferred to Plan 22b-03 (cred-redaction is the watcher's responsibility); documented in `events.py::AgentErrorPayload` docstring.
- T-22b-02-06 (elevation of privilege via fetch_events_after_seq) — caller-responsibility documented in `event_store.py` module docstring; route-layer ownership check is Plan 22b-05.

---

## Self-Check: PASSED

All created/modified files exist on disk:

```
FOUND: api_server/alembic/versions/004_agent_events.py
FOUND: api_server/src/api_server/models/events.py
FOUND: api_server/src/api_server/services/event_store.py
FOUND: api_server/tests/test_events_migration.py
FOUND: api_server/tests/test_events_store.py
FOUND: api_server/tests/test_events_seq_concurrency.py
FOUND: api_server/tests/test_events_batching_perf.py
FOUND: .planning/phases/22b-agent-event-stream/deferred-items.md (modified)
```

All commits exist in `git log`:

```
FOUND: e34df2a  feat(22b-02): migration 004_agent_events + 4 schema tests
FOUND: f844064  feat(22b-02): Pydantic per-kind event payloads + AgentEventsResponse
FOUND: 47bbae5  feat(22b-02): event_store + spike-04 batching + spike-05 seq concurrency tests
```

20/20 tests in the plan-defined test files PASS on real PG17 via testcontainers.
