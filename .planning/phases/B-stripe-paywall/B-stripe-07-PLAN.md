---
phase: B-stripe
plan: 07
type: execute
wave: 3
depends_on: [B-stripe-02]
files_modified:
  - api_server/src/api_server/services/tier_enforcement.py
  - api_server/src/api_server/routes/agents.py
  - api_server/src/api_server/services/inapp_messages_store.py
  - api_server/tests/services/test_tier_enforcement.py
  - api_server/tests/routes/test_agent_tier_cap.py
  - api_server/tests/services/test_messages_retention_window.py
autonomous: true
gap_closure: false
requirements_addressed:
  - D-02 (Pro: 5 active agents, 30d retention; Free: 1 agent, 7d retention; Ultra: unlimited)
  - D-05 (entitlement enforcement at agent.create + messages.list)
must_haves:
  truths:
    - "agent.create returns 403 TIER_LIMIT_EXCEEDED when active-agent count would exceed the tier cap (free=1 / pro=5 / ultra=∞)"
    - "GET /v1/agents/:id/messages filters out messages older than the tier retention window (free=7d / pro=30d / ultra=unlimited)"
    - "tier_enforcement is a single service module so future tier changes update one place"
    - "Race condition: 2 concurrent agent.create calls cannot both succeed past the cap"
  artifacts:
    - path: "api_server/src/api_server/services/tier_enforcement.py"
      provides: "check_can_create_agent + retention_window_days helpers"
      exports: ["check_can_create_agent", "retention_window_days"]
  key_links:
    - from: "api_server/src/api_server/routes/agents.py"
      to: "services/tier_enforcement.py::check_can_create_agent"
      via: "called inside agent_create handler before INSERT"
      pattern: "check_can_create_agent"
---

<objective>
Pro entitlement enforcement. Two surfaces gate behavior on tier:
1. `agent.create` enforces active-agent slot cap.
2. `GET /v1/agents/:id/messages` filters by retention window.

Purpose: Pro tier exists primarily to give users 5 active agents + 30d retention. Without this enforcement, Pro and Free are indistinguishable from a behavior standpoint.
Output: services/tier_enforcement.py + handler integrations + tests including a race test for the cap.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/B-stripe-paywall/CONTEXT.md
@.planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md
@.planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md
@.planning/phases/B-stripe-paywall/B-stripe-02-SUMMARY.md
@api_server/src/api_server/routes/agents.py
@api_server/src/api_server/services/inapp_messages_store.py
@api_server/src/api_server/models/errors.py

<interfaces>
From api_server/src/api_server/routes/agents.py (existing):
- POST /v1/agents handler (read it; identify the INSERT/lock acquisition path)
- The handler currently has no tier-aware cap check

From api_server/src/api_server/services/inapp_messages_store.py (existing — Phase 23):
- get_messages_for_agent(...) returns rows ordered ASC
- We need a tier-aware variant or a `since` parameter on the existing function

agent_containers.status values that count as "active" (per D-05 pre-AMD-04 wording):
- 'running' counts
- 'starting'/'provisioning' counts
- 'auto_paused' (new in Plan 06) — does NOT count (already counted out by tier downgrade)
- 'stopped'/'failed' do NOT count
- Check existing status values via `grep -r "agent_containers.*status" api_server/`
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: services/tier_enforcement.py — agent cap + retention window helpers + agent.create gate</name>
  <files>api_server/src/api_server/services/tier_enforcement.py, api_server/src/api_server/routes/agents.py, api_server/tests/services/test_tier_enforcement.py, api_server/tests/routes/test_agent_tier_cap.py</files>
  <read_first>
    - api_server/src/api_server/routes/agents.py (FULL — locate POST /v1/agents handler + lock pattern)
    - api_server/src/api_server/services/inapp_messages_store.py (existing get_messages_for_agent shape)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"services/tier_enforcement.py" — predicate + per-user filter pattern)
    - api_server/src/api_server/auth/deps.py (require_user signature; we may need a sibling helper that returns tier too)
    - api_server/src/api_server/models/errors.py (ErrorCode.TIER_LIMIT_EXCEEDED added in Plan 03)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_tier_caps: free=1, pro=5, ultra=infinity (returns very large number)
    - test_retention_windows: free=7, pro=30, ultra=None (None = unlimited)
    - test_check_can_create_agent_returns_true_for_free_with_zero_agents
    - test_check_can_create_agent_returns_false_for_free_with_one_agent
    - test_check_can_create_agent_returns_true_for_pro_with_four_agents
    - test_check_can_create_agent_returns_false_for_pro_with_five_agents
    - test_check_can_create_agent_returns_true_for_ultra_with_thousand_agents
    - test_check_can_create_agent_excludes_stopped_failed_auto_paused_from_count
    - test_agent_create_route_returns_403_TIER_LIMIT_EXCEEDED_when_capped
    - test_agent_create_route_succeeds_for_pro_with_4_existing_agents
    - test_agent_create_race_two_concurrent_calls_under_lock_at_least_one_fails
  </behavior>
  <action>
**File 1 — `api_server/src/api_server/services/tier_enforcement.py`:**

```python
from __future__ import annotations
from typing import Final
from uuid import UUID
import asyncpg

# D-05 — single source of truth for tier-derived limits.
_TIER_AGENT_CAP: Final[dict[str, int]] = {
    "free": 1,
    "pro": 5,
    "ultra": 10_000_000,    # effectively infinite for free-tier accounting
}
_TIER_RETENTION_DAYS: Final[dict[str, int | None]] = {
    "free": 7,
    "pro": 30,
    "ultra": None,           # None = unlimited
}

# Status values that count as "active" toward the cap.
_ACTIVE_STATUSES: Final[tuple[str, ...]] = (
    "starting", "provisioning", "running", "ready",
)

def agent_cap_for_tier(tier: str) -> int:
    return _TIER_AGENT_CAP.get(tier, _TIER_AGENT_CAP["free"])

def retention_window_days(tier: str) -> int | None:
    return _TIER_RETENTION_DAYS.get(tier, _TIER_RETENTION_DAYS["free"])


async def check_can_create_agent(
    conn: asyncpg.Connection, *, user_id: UUID,
) -> tuple[bool, int, str]:
    """Returns (allowed, current_active_count, tier).
    Caller MUST hold an advisory lock or row-lock on the user to prevent races."""
    tier = await conn.fetchval(
        "SELECT tier FROM users WHERE id = $1 FOR UPDATE", user_id,
    )
    if tier is None:
        return (False, 0, "free")
    placeholders = ",".join(f"${i+2}" for i in range(len(_ACTIVE_STATUSES)))
    count = await conn.fetchval(
        f"SELECT COUNT(*)::int FROM agent_containers "
        f"WHERE user_id = $1 AND status IN ({placeholders})",
        user_id, *_ACTIVE_STATUSES,
    )
    cap = agent_cap_for_tier(tier)
    return (count < cap, int(count), tier)
```

**File 2 — `api_server/src/api_server/routes/agents.py` modification:** Locate the POST /v1/agents handler. Add the cap check BEFORE the existing INSERT. Pattern:

```python
from ..services.tier_enforcement import check_can_create_agent

# Inside the handler, after require_user resolves user_id:
async with pool.acquire() as conn:
    async with conn.transaction():
        allowed, active_count, tier = await check_can_create_agent(conn, user_id=user_id)
        if not allowed:
            return _err(
                403, ErrorCode.TIER_LIMIT_EXCEEDED,
                f"agent cap reached for tier '{tier}' "
                f"({active_count} active, cap {agent_cap_for_tier(tier)})",
            )
        # ...existing INSERT into agent_containers...
```

**Race protection:** the `SELECT tier FROM users WHERE id = $1 FOR UPDATE` inside the transaction ensures a concurrent POST blocks on the row lock until the first transaction commits. The second call then re-reads the count and trips the cap.

If the existing handler already has its own lock acquisition (e.g. `SETNX` Redis lock for v1's "max 1 active agent" invariant in SES-02), confirm that the new check happens INSIDE that same lock OR adapt to use the row-lock pattern instead. Goal: zero possibility of 2 concurrent POSTs both succeeding past the cap.

**File 3 — `api_server/tests/services/test_tier_enforcement.py`:** Pure-Python unit tests for the lookup helpers (no DB needed for `agent_cap_for_tier` / `retention_window_days`). Use a Postgres testcontainer for `check_can_create_agent` tests — seed user + agent_containers rows, call helper, assert tuple result.

**File 4 — `api_server/tests/routes/test_agent_tier_cap.py`:** Postgres testcontainer + async_client. Behaviors per `<behavior>` list. The race test uses `asyncio.gather(client.post(...), client.post(...))` against a fresh user with tier=free and cap=1 — assert exactly one POST returns 200 and the other returns 403 (or both retry semantics; depends on the existing handler's lock — confirm one of them DOES get 403, not both 200).
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/services/test_tier_enforcement.py tests/routes/test_agent_tier_cap.py -x</automated>
  </verify>
  <done>
- All cap-related tests pass.
- `grep -c 'check_can_create_agent' api_server/src/api_server/routes/agents.py` ≥ 1.
- Race test asserts at-most-one-success under 2-way concurrency.
- The cap function uses `WHERE status IN (...)` — verify against the actual agent_containers status enum values (run `grep "ck_agent_containers_status\|ck_agent_status" api_server/alembic/versions/` to find the constraint).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: messages.list retention window — services/inapp_messages_store.py + handler integration</name>
  <files>api_server/src/api_server/services/inapp_messages_store.py, api_server/src/api_server/routes/agent_messages.py, api_server/tests/services/test_messages_retention_window.py</files>
  <read_first>
    - api_server/src/api_server/services/inapp_messages_store.py (FULL — current get_messages_for_agent + per-user filter)
    - api_server/src/api_server/routes/agent_messages.py (existing GET /v1/agents/:id/messages handler)
    - api_server/src/api_server/services/tier_enforcement.py (Task 1 — retention_window_days helper)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_get_messages_no_retention_filter_for_ultra
    - test_get_messages_filters_by_30d_for_pro
    - test_get_messages_filters_by_7d_for_free
    - test_get_messages_with_messages_at_boundary_8d_for_free_excludes_oldest
    - test_get_messages_handler_reads_user_tier_then_applies_filter
  </behavior>
  <action>
**File 1 — `api_server/src/api_server/services/inapp_messages_store.py` modification:** Add an optional `since: datetime | None` parameter to the existing `get_messages_for_agent` (or sibling helper) function. When `since is not None`, the SQL query adds `AND created_at >= $N`. When `None`, no filter applied.

```python
async def get_messages_for_agent(
    conn: asyncpg.Connection, *, agent_id: UUID, user_id: UUID,
    limit: int = 200, since: datetime | None = None,
) -> list[dict]:
    if since is None:
        rows = await conn.fetch(
            "SELECT id, role, content, created_at FROM inapp_messages "
            "WHERE agent_id = $1 AND user_id = $2 "
            "ORDER BY created_at ASC LIMIT $3",
            agent_id, user_id, limit,
        )
    else:
        rows = await conn.fetch(
            "SELECT id, role, content, created_at FROM inapp_messages "
            "WHERE agent_id = $1 AND user_id = $2 AND created_at >= $3 "
            "ORDER BY created_at ASC LIMIT $4",
            agent_id, user_id, since, limit,
        )
    # ...existing serialization...
```

**File 2 — `api_server/src/api_server/routes/agent_messages.py` modification:** Locate the GET /v1/agents/:id/messages handler. Read user.tier inside the handler (one extra fetchval), then compute `since` and pass it to the store helper:

```python
from datetime import datetime, timedelta, timezone
from ..services.tier_enforcement import retention_window_days

# inside the handler:
async with pool.acquire() as conn:
    tier = await conn.fetchval("SELECT tier FROM users WHERE id = $1", user_id)
    days = retention_window_days(tier or "free")
    since = (
        datetime.now(timezone.utc) - timedelta(days=days)
        if days is not None
        else None
    )
    msgs = await get_messages_for_agent(
        conn, agent_id=agent_id, user_id=user_id, limit=limit, since=since,
    )
return MessagesResponse(messages=msgs)
```

**File 3 — `api_server/tests/services/test_messages_retention_window.py`:** Postgres testcontainer. Seed users (free, pro, ultra). Seed inapp_messages rows with `created_at` at: 1d, 5d, 8d, 31d, 365d ago. Call the handler (or store helper) for each user, assert the rows returned match the expected retention window.

For the "at boundary 8d for free" test: 7d retention + a row at exactly 8 days ago → row should be excluded (`>= now - 7d` is the predicate). Verify the boundary semantics match the SQL.
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/services/test_messages_retention_window.py -x</automated>
  </verify>
  <done>
- All 5 retention tests pass.
- `grep -c 'retention_window_days' api_server/src/api_server/routes/agent_messages.py` ≥ 1.
- `grep -c 'since' api_server/src/api_server/services/inapp_messages_store.py` ≥ 2 (param + SQL clause).
- Existing Phase 23 messages.list tests still pass (regression gate; these test free-tier users and 7d retention is more permissive than what they're seeding by default).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Mobile/web → POST /v1/agents | session-cookie auth + Pro tier cap predicate |
| Mobile/web → GET /v1/agents/:id/messages | session-cookie auth + per-tier retention filter |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-CAP | EoP | services/tier_enforcement.py + routes/agents.py | mitigate | SELECT tier FROM users WHERE id = $1 FOR UPDATE inside the same transaction as the count check + INSERT — prevents races past the cap |
| T-B-RET | InfoDisclosure | services/inapp_messages_store.py | mitigate | retention filter applied at query time using a UTC-now derived cutoff; per-user user_id filter unchanged |
| T-B-XT | InfoDisclosure | tier_enforcement.check_can_create_agent | mitigate | function takes user_id explicitly + uses it in WHERE clause; no cross-tenant probe path |
</threat_model>

<verification>
- All cap + retention tests pass (~16 tests total).
- Race test proves cap holds under concurrent POSTs.
- Existing agent.create + messages.list tests still pass.
</verification>

<success_criteria>
- `cd api_server && uv run pytest tests/services/test_tier_enforcement.py tests/routes/test_agent_tier_cap.py tests/services/test_messages_retention_window.py -x` green.
- `cd api_server && uv run pytest tests/routes/test_agent_lifecycle_inapp.py tests/routes/test_agent_messages.py -x` regression gate green.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-07-SUMMARY.md` documenting the cap + retention helpers and any agent_containers status enum updates.
</output>
