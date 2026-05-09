---
phase: B-stripe
plan: 07
subsystem: billing-paywall
tags: [wave-3, tier-enforcement, postgres, fastapi, asyncpg, race-safety]
requires:
  - phase: B-stripe-02
    provides: "users.tier column + ck_users_tier CHECK constraint + agent_containers.container_status='auto_paused' enum extension (D-15)"
  - phase: B-stripe-03
    provides: "TIER_LIMIT_EXCEEDED ErrorCode with type='forbidden' (already minted by Plan 03)"
  - phase: B-stripe-06
    provides: "users.tier is sole-writer-by-Stripe-webhook invariant (D-04); tier_enforcement only READS"
provides:
  - "services/tier_enforcement.py — D-05 single source of truth: agent_cap_for_tier (free=1/pro=5/ultra=10M) + retention_window_days (7/30/None) + check_can_create_agent helper"
  - "routes/agent_lifecycle.start_agent — TWO cap gates: early read-only pre-flight (UX/cost) + transactional FOR-UPDATE-row-lock gate (race-safety)"
  - "routes/agent_messages.get_messages — per-tier retention filter via list_history_for_agent(..., since=...)"
  - "inapp_messages_store.list_history_for_agent — additive optional since: datetime | None parameter (no breaking change)"
affects: [B-stripe-09, B-stripe-12]
tech-stack:
  added: []
  patterns:
    - "Defense-in-depth gating: read-only pre-flight check rejects 403 BEFORE expensive BYOK validator network probe; transactional FOR UPDATE row-lock gate inside same tx as INSERT pending row prevents 2-way concurrent races past the cap"
    - "Single-source-of-truth catalog: per-tier limits live ONLY in tier_enforcement.py constants (_TIER_AGENT_CAP, _TIER_RETENTION_DAYS, _ACTIVE_STATUSES); routes import; tests import; mobile fetches via API; never duplicated"
    - "Active-status discipline: only ('starting','running') consume a slot; auto_paused/stopped/start_failed/crashed/stopping are excluded — D-15 Pro→Free downgrade leaves 4 paused agents that don't inflate the count"
    - "Lazy tier re-read on every authenticated billing-touching call (D-18); no caching, no pub/sub; tier change reflected within next API call's latency"
    - "Additive parameter on existing SQL seam (list_history_for_agent): since: datetime | None = None default keeps every existing caller byte-identical; only the new path branches the SQL"
key-files:
  created:
    - api_server/src/api_server/services/tier_enforcement.py
    - api_server/tests/services/test_tier_enforcement.py
    - api_server/tests/services/test_messages_retention_window.py
    - api_server/tests/routes/test_agent_tier_cap.py
  modified:
    - api_server/src/api_server/routes/agent_lifecycle.py  (2 cap gates in start_agent)
    - api_server/src/api_server/services/inapp_messages_store.py  (since param + branched SQL on list_history_for_agent)
    - api_server/src/api_server/routes/agent_messages.py  (read users.tier; compute since; pass to store helper)
key-decisions:
  - "TWO gates instead of ONE: an early read-only gate is a UX + cost optimization (no 50-300ms BYOK network probe when cap is already tripped) but it does NOT replace the transactional gate. The transactional FOR UPDATE gate is the security boundary; the early gate is a fast-fail."
  - "agent_cap_for_tier(ultra)=10_000_000 (int) instead of math.inf or sys.maxsize: COUNT comparisons stay integer-typed; 10M comfortably exceeds any plausible user's collection while keeping COUNT(*) cheap on the agent_containers table."
  - "Active statuses = ('starting','running') strictly. Three other states could plausibly count: 'stopping' (about to release), 'auto_paused' (D-15 frozen), 'crashed' (terminal failure). All three EXCLUDED. Rationale: counting them double-charges a user who is mid-shutdown ('stopping'), breaks D-15's 'paused doesn't consume slot' invariant ('auto_paused'), or punishes for upstream failures ('crashed')."
  - "since=None default on list_history_for_agent (not since=now-100y or some other sentinel) so existing Plan 23 callers stay byte-identical without the new code path. Cleanly opt-in for the route handler that knows the user's tier."
  - "Both check_can_create_agent and the agent_messages handler use a single 'SELECT tier FROM users WHERE id=$1' read — defensively coalescing NULL → 'free' (per agent_cap_for_tier's safe-default contract). Avoids a tier-NULL race blowing up between user-created and tier-backfilled."
metrics:
  duration: "~25 minutes (TDD RED + GREEN for both tasks)"
  completed: "2026-05-09"
  tests_added: 33  # 17 service + 8 route cap + 8 retention
  tests_regression_passed: 67  # 28 (cap regression: msgs/delete) + 39 (retention regression: msgs all + idempotency)
---

# Phase B-stripe Plan 07: Tier Enforcement Summary

**One-liner:** Free=1 / Pro=5 / Ultra=∞ active-agent slot cap on POST /v1/agents/:id/start with race-safe FOR UPDATE row-lock + early-pre-flight 403; per-tier message retention (7d/30d/∞) via additive `since` SQL filter on the existing `list_history_for_agent` seam.

---

## What Shipped

### `services/tier_enforcement.py` (NEW — single source of truth)

Three exports:

```python
agent_cap_for_tier(tier: str) -> int           # free=1 / pro=5 / ultra=10_000_000
retention_window_days(tier: str) -> int | None # free=7 / pro=30 / ultra=None (unlimited)
check_can_create_agent(conn, *, user_id) -> tuple[bool, int, str]  # (allowed, count, tier)
```

Module-level constants `_TIER_AGENT_CAP`, `_TIER_RETENTION_DAYS`, `_ACTIVE_STATUSES = ('starting', 'running')`. A future "raise pro to 10 agents" or "shrink free retention to 3d" change updates ONE place.

`check_can_create_agent` opens with `SELECT tier FROM users WHERE id=$1 FOR UPDATE` so a concurrent caller blocks until the first transaction commits. Combined with the `ix_agent_containers_agent_instance_running` partial unique index, makes 2-way concurrent /start calls past the cap impossible.

Defensive: unknown tier (typo, future migration drift) falls back to `free` cap (1 agent) — safest default. Missing users row returns `(False, 0, 'free')` rather than raising.

### `routes/agent_lifecycle.start_agent` — TWO cap gates (defense-in-depth)

**Step 2a — early pre-flight (read-only):**
```python
async with pool.acquire() as conn:
    early_allowed, early_count, early_tier = await check_can_create_agent(
        conn, user_id=user_id,
    )
if not early_allowed:
    return _err(403, ErrorCode.TIER_LIMIT_EXCEEDED, ...)
```
Fires BEFORE the BYOK validator's network probe. Zero upstream calls when the user is already at-cap. Fast-fail UX optimization.

**Step 3 — transactional gate (race-safety):**
```python
async with pool.acquire() as conn:
    async with conn.transaction():
        allowed, active_count, tier = await check_can_create_agent(
            conn, user_id=user_id,  # SELECT tier FROM users FOR UPDATE
        )
        if not allowed:
            cap_blocked = True
        else:
            container_row_id = await insert_pending_agent_container(...)
if cap_blocked:
    return _err(403, ErrorCode.TIER_LIMIT_EXCEEDED, ...)
```
The row-lock survives until the transaction commits. The pending agent_containers row counts toward the next caller's count. Two concurrent /start calls cannot both succeed past the cap.

### `routes/agent_messages.get_messages` — per-tier retention filter

```python
async with pool.acquire() as conn:
    tier = await conn.fetchval("SELECT tier FROM users WHERE id = $1", user_id)
days = retention_window_days(tier or "free")
since = (
    datetime.now(timezone.utc) - timedelta(days=days)
    if days is not None
    else None
)
rows = await ims.list_history_for_agent(
    conn, agent_id=agent_id, limit=effective_limit, since=since,
)
```

Lazy re-read on every request (D-18). Ultra users get `since=None` = no SQL filter = unlimited. Free/pro get a UTC-now-derived cutoff. The pruner (Plan B-stripe-09, future) hard-deletes past the window; this filter is the read-time mirror so a downgrade IMMEDIATELY hides the older rows.

### `services/inapp_messages_store.list_history_for_agent` — additive `since` parameter

```python
async def list_history_for_agent(
    conn: asyncpg.Connection, *, agent_id: UUID, limit: int,
    since: datetime | None = None,  # NEW — Phase B Plan B-stripe-07
) -> list[dict]:
```

`since=None` (default) keeps every existing Phase 23 caller byte-identical. When set, SQL adds `AND created_at >= $3` (>=  is INCLUSIVE on the cutoff boundary).

---

## Truth Audit (must_haves.truths from PLAN.md)

| Truth | Status | Evidence |
|---|---|---|
| `agent.create returns 403 TIER_LIMIT_EXCEEDED when active-agent count would exceed the tier cap (free=1 / pro=5 / ultra=∞)` | ✅ PASS | `test_agent_start_returns_403_when_free_user_at_cap`, `test_agent_start_returns_403_when_pro_user_at_5_active_agents`, `test_agent_start_ultra_user_with_many_agents_passes_cap` (8 route tests, all green) |
| `GET /v1/agents/:id/messages filters out messages older than the tier retention window (free=7d / pro=30d / ultra=unlimited)` | ✅ PASS | `test_get_messages_no_retention_filter_for_ultra`, `test_get_messages_filters_by_30d_for_pro`, `test_get_messages_filters_by_7d_for_free`, `test_get_messages_with_messages_at_boundary_8d_for_free_excludes_oldest` |
| `tier_enforcement is a single service module so future tier changes update one place` | ✅ PASS | `_TIER_AGENT_CAP`, `_TIER_RETENTION_DAYS`, `_ACTIVE_STATUSES` constants in services/tier_enforcement.py; no duplicates anywhere in the repo |
| `Race condition: 2 concurrent agent.create calls cannot both succeed past the cap` | ✅ PASS | `test_agent_start_race_two_concurrent_calls_at_most_one_succeeds_past_cap` — asserts COUNT of active agent_containers <= 1 after concurrent gather() of 2 POSTs against a free-cap=1 user |

## Done Criteria (Task <done> blocks)

| Check | Status |
|---|---|
| All cap-related tests pass | ✅ 25/25 (17 service + 8 route) |
| All retention tests pass | ✅ 8/8 |
| `grep -c 'check_can_create_agent' routes/agent_lifecycle.py` ≥ 1 | ✅ 3 |
| `grep -c 'retention_window_days' routes/agent_messages.py` ≥ 1 | ✅ 2 |
| `grep -c 'since' services/inapp_messages_store.py` ≥ 2 | ✅ 9 |
| Race test asserts at-most-one-success under 2-way concurrency | ✅ Asserts `active <= 1` AND `not (both 200)` |
| The cap function uses `WHERE status IN (...)` matching real enum | ✅ `('starting','running')` matches migration 003 / 014 enum |
| Existing Phase 23 messages.list tests still pass | ✅ 39/39 regression on test_agent_messages_{get,post,delete,sse} + test_messages_idempotency_required |

## Threat-Model Audit

| Threat ID | Mitigation Applied |
|---|---|
| T-B-CAP (EoP — concurrent /start past cap) | `SELECT tier FROM users WHERE id=$1 FOR UPDATE` inside same tx as `insert_pending_agent_container`. Row-lock blocks concurrent caller until commit; second caller's count includes the new pending row. Verified via `test_agent_start_race_two_concurrent_calls_at_most_one_succeeds_past_cap`. |
| T-B-RET (InfoDisclosure — tier-changed user reads old messages) | Lazy re-read of `users.tier` on every GET /v1/agents/:id/messages call (no caching). UTC-now-derived cutoff means clock-skew safe. Verified via `test_get_messages_handler_reads_user_tier_then_applies_filter` (flips tier mid-test). |
| T-B-XT (cross-tenant probe via tier_enforcement) | `check_can_create_agent` takes `user_id` explicitly + uses it in WHERE clause. Cross-tenant SELECT impossible (no cross-user JOIN). Verified via `test_check_can_create_agent_cross_tenant_isolation` (user A's 5 agents do not block user B). |

## Decisions Made

1. **TWO gates, not ONE.** Early read-only gate before BYOK validator (UX + cost); transactional gate inside pending-insert tx (security boundary). The early gate is a fast-fail optimization, the transactional gate is the correctness boundary.

2. **`agent_cap_for_tier(ultra) = 10_000_000`** rather than `math.inf` or `sys.maxsize`. Keeps COUNT comparisons integer-typed. Comfortably exceeds plausible per-user agent collection.

3. **Active statuses = `('starting', 'running')` strictly.** Excluded: `'stopping'` (mid-shutdown), `'auto_paused'` (D-15 frozen — wouldn't make sense to count post-downgrade), `'crashed'` / `'start_failed'` (terminal failure not user's fault). The enum has 7 values; only 2 consume a slot.

4. **`since=None` default** on `list_history_for_agent` — every Phase 23 caller stays byte-identical. The route handler is the only opt-in caller for the new code path.

5. **Defensive `tier or "free"`** in agent_messages handler: a user row with NULL tier (impossible by migration 014's NOT NULL DEFAULT, but defense-in-depth) coerces to free's 7d window — safest default.

## Deviations from Plan

**1. [Rule 3 - Blocking issue] Repositioned cap check to BEFORE the BYOK validator**

- **Found during:** Task 1 — first run of `test_agent_start_returns_403_when_free_user_at_cap` returned 401 instead of 403 because the BYOK validator hit real OpenRouter with `Bearer test-key` and rejected before reaching the (originally inserted) cap check.
- **Issue:** The plan's example placed the cap check inside the same tx as `insert_pending_agent_container` (Step 3). That works for race-safety but means a free-tier user at-cap eats a 50-300ms upstream BYOK probe before getting the 403.
- **Fix:** Added a SECOND, EARLIER cap check (`Step 2a`) right after `fetch_agent_instance` proves ownership. Read-only, non-locking. Returns 403 immediately. The transactional gate at Step 3 stays — defense-in-depth, race-safety boundary.
- **Files modified:** `api_server/src/api_server/routes/agent_lifecycle.py`
- **Commit:** `59fc8bc`

**2. [Rule 1 - Bug] Docstring merge collision**

- **Found during:** Task 2 GREEN — first edit added a Phase B paragraph and accidentally placed a closing `"""` in the middle of the existing module docstring, leaving the trailing paragraph as bare Python that triggered `SyntaxError: invalid decimal literal` on import.
- **Issue:** Self-introduced typo from a partial edit.
- **Fix:** Re-merged the entire module docstring as a single block.
- **Files modified:** `api_server/src/api_server/services/inapp_messages_store.py`
- **Commit:** included in `4c0061e` (caught + fixed in the same GREEN cycle, before the test pass landed).

**3. [Rule 2 - Critical functionality] Function name correction (`list_history_for_agent`, not `get_messages_for_agent`)**

- **Found during:** Task 2 — the plan's `<action>` block referenced `get_messages_for_agent` as the function to extend, but the actual function called by the route is `list_history_for_agent`. (`fetch_history_for_agent` exists too but isn't on the GET /messages path.)
- **Issue:** Plan referenced a function name that doesn't exist; following it literally would have orphaned the new code path.
- **Fix:** Extended the function actually called by the handler (`list_history_for_agent`).
- **Files modified:** `api_server/src/api_server/services/inapp_messages_store.py`, `api_server/src/api_server/routes/agent_messages.py`
- **Commit:** `4c0061e`

## Self-Check: PASSED

- ✅ `services/tier_enforcement.py` exists at `/Users/fcavalcanti/dev/agent-playground/api_server/src/api_server/services/tier_enforcement.py`
- ✅ `tests/services/test_tier_enforcement.py` exists
- ✅ `tests/services/test_messages_retention_window.py` exists
- ✅ `tests/routes/test_agent_tier_cap.py` exists
- ✅ `routes/agent_lifecycle.py` calls `check_can_create_agent` (3 occurrences — import + 2 gate sites)
- ✅ `routes/agent_messages.py` calls `retention_window_days`
- ✅ `services/inapp_messages_store.py` accepts `since` parameter (9 occurrences — param sig, docstring, branched SQL)
- ✅ Commits exist: `20dd94f` (RED Task 1), `59fc8bc` (GREEN Task 1), `6f0a325` (RED Task 2), `4c0061e` (GREEN Task 2)
- ✅ Plan success_criteria green: `pytest tests/services/test_tier_enforcement.py tests/routes/test_agent_tier_cap.py tests/services/test_messages_retention_window.py` = 33/33 PASS
- ✅ Plan regression gate green: `pytest tests/routes/test_agent_messages_{get,post,delete,sse}.py tests/routes/test_messages_idempotency_required.py tests/routes/test_agent_delete.py` = 67/67 PASS

## TDD Gate Compliance

Plan-level type=execute (not type=tdd at the plan level), but each task carried `tdd="true"` and the per-task RED/GREEN cycle was honored:

- Task 1 RED: `20dd94f test(B-stripe-07): add failing tests for tier_enforcement service + agent.create cap (RED gate)`
- Task 1 GREEN: `59fc8bc feat(B-stripe-07): tier_enforcement service + agent.create cap gate (GREEN gate)`
- Task 2 RED: `6f0a325 test(B-stripe-07): add failing tests for messages.list per-tier retention window (RED gate)`
- Task 2 GREEN: `4c0061e feat(B-stripe-07): per-tier retention window on GET /v1/agents/:id/messages (GREEN gate)`

REFACTOR not needed — both implementations are minimal-and-final.
