---
phase: B-stripe
plan: 09
type: execute
wave: 4
depends_on: [B-stripe-02, B-stripe-06]
files_modified:
  - api_server/src/api_server/temporal/activities/prune_messages.py
  - api_server/src/api_server/temporal/activities/reconcile_stripe.py
  - api_server/src/api_server/temporal/activities/reconcile_ledger.py
  - api_server/src/api_server/temporal/workflows/prune_messages.py
  - api_server/src/api_server/temporal/workflows/reconcile_stripe.py
  - api_server/src/api_server/temporal/workflows/reconcile_ledger.py
  - api_server/src/api_server/temporal/schedules.py
  - api_server/src/api_server/temporal/worker.py
  - api_server/src/api_server/main.py
  - api_server/tests/temporal/test_prune_messages_workflow.py
  - api_server/tests/temporal/test_reconcile_stripe_workflow.py
  - api_server/tests/temporal/test_reconcile_ledger_workflow.py
  - api_server/tests/temporal/test_schedules_idempotent.py
autonomous: true
gap_closure: false
requirements_addressed:
  - D-09 (daily prune_messages_workflow — retention enforcement)
  - D-17 (nightly reconcile_ledger_workflow — drift detection + Sentry alert)
  - D-Discretion (reconcile_stripe_workflow — 5-min poller backstops missed webhooks)
must_haves:
  truths:
    - "PruneMessagesWorkflow runs daily, deletes inapp_messages older than the user's tier retention window (free=7d, pro=30d, ultra=never)"
    - "ReconcileStripeWorkflow runs every 5 min, queries Stripe for checkout.session.completed events in the last 15 min that aren't in stripe_webhook_events, and processes them via the same handler logic as the webhook"
    - "ReconcileLedgerWorkflow runs nightly, recomputes credit_balances.balance_cents from credit_transactions SUM, logs Sentry on any drift > $0.01"
    - "register_schedules helper is idempotent — first call creates, second call updates without error (Pitfall 8 mitigated)"
    - "schedules registered ONCE per worker boot in worker.py main"
  artifacts:
    - path: "api_server/src/api_server/temporal/schedules.py"
      provides: "register_schedules(client, task_queue) helper using try/RPCError/update fallback"
      exports: ["register_schedules"]
    - path: "api_server/src/api_server/temporal/workflows/prune_messages.py"
      provides: "daily-cron workflow"
      contains: "@workflow.defn"
    - path: "api_server/src/api_server/temporal/workflows/reconcile_stripe.py"
      provides: "5-min cron workflow"
    - path: "api_server/src/api_server/temporal/workflows/reconcile_ledger.py"
      provides: "nightly cron workflow with Sentry drift logging"
  key_links:
    - from: "temporal/worker.py"
      to: "temporal/schedules.py::register_schedules"
      via: "called once after Temporal client connect, before worker.run()"
      pattern: "register_schedules"
---

<objective>
Three Temporal scheduled workflows + idempotent registration helper. Daily prune (retention enforcement), 5-min reconcile (missed-webhook backstop), nightly ledger drift check. Reuses existing Temporal substrate from Phase 28 (worker.py, RetryPolicy, sandbox-passthrough imports).

Purpose: The webhook is the primary path for Stripe events — but webhooks can be lost (network blip, Stripe retry exhausted). The 5-min reconcile catches these. The nightly ledger reconcile catches drift between cache and ledger truth. The daily prune enforces D-09 retention.
Output: 3 activities + 3 workflows + schedules.py + worker.py registration + integration tests.
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
@.planning/phases/B-stripe-paywall/B-stripe-01-SUMMARY.md
@api_server/src/api_server/temporal/activities/record_usage.py
@api_server/src/api_server/temporal/activities/backfill_openrouter_cost.py
@api_server/src/api_server/temporal/workflows/dispatch_message.py
@api_server/src/api_server/temporal/worker.py
@api_server/src/api_server/services/tier_enforcement.py
@api_server/src/api_server/instrumentation/sentry.py

<interfaces>
From api_server/src/api_server/services/tier_enforcement.py (Plan 07):
- retention_window_days(tier) -> int | None  # free=7, pro=30, ultra=None

From api_server/src/api_server/instrumentation/sentry.py (Phase 31 H6):
- sentry_sdk.capture_message("...", level="error") for drift alerts

From api_server/src/api_server/routes/billing_webhook.py (Plan 06):
- _handle_checkout_completed(conn, event) — re-used by reconcile_stripe

From Wave 0 spike-d artifact:
- register_schedules(client, task_queue) helper template (try/RPCError/update fallback)

Stripe SDK list events:
```python
events = client.events.list(params={"type": "checkout.session.completed", "created": {"gte": now-900}})
# returns paginated list; for v1 reconcile we accept the first page's 100 events
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: 3 activities + 3 workflows + schedules.py</name>
  <files>api_server/src/api_server/temporal/activities/prune_messages.py, api_server/src/api_server/temporal/activities/reconcile_stripe.py, api_server/src/api_server/temporal/activities/reconcile_ledger.py, api_server/src/api_server/temporal/workflows/prune_messages.py, api_server/src/api_server/temporal/workflows/reconcile_stripe.py, api_server/src/api_server/temporal/workflows/reconcile_ledger.py, api_server/src/api_server/temporal/schedules.py</files>
  <read_first>
    - api_server/src/api_server/temporal/activities/record_usage.py (FULL — class-bound activity template)
    - api_server/src/api_server/temporal/activities/backfill_openrouter_cost.py (FULL — class-bound activity that talks to upstream + writes DB)
    - api_server/src/api_server/temporal/workflows/dispatch_message.py:1-50, 86-238 (FULL — workflow shape, sandbox imports, retry policy)
    - api_server/src/api_server/services/tier_enforcement.py (Plan 07 — retention_window_days)
    - api_server/tests/_spikes/spike_d_temporal_schedule.py (Wave 0 — exact try/RPCError/update template)
    - api_server/src/api_server/instrumentation/sentry.py (Phase 31 H6)
  </read_first>
  <behavior>
    Tests written FIRST in Task 2 (this task is implementation; behavior verification covered in tests below).
  </behavior>
  <action>
**File 1 — `temporal/activities/prune_messages.py`:**

```python
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from temporalio import activity

_log = logging.getLogger("api_server.temporal.prune_messages")


class PruneMessagesActivities:
    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="prune_messages")
    async def prune_messages(self) -> int:
        """Delete inapp_messages older than each tier's retention window. Returns total deleted."""
        from ...services.tier_enforcement import retention_window_days
        now = datetime.now(timezone.utc)

        async with self.db_pool.acquire() as conn:
            total_deleted = 0
            for tier, days in (("free", retention_window_days("free")),
                               ("pro", retention_window_days("pro")),
                               ("ultra", retention_window_days("ultra"))):
                if days is None:
                    continue  # ultra = unlimited retention
                cutoff = now - timedelta(days=days)
                deleted = await conn.fetchval(
                    """
                    WITH del AS (
                      DELETE FROM inapp_messages m
                      USING users u
                      WHERE m.user_id = u.id AND u.tier = $1 AND m.created_at < $2
                      RETURNING m.id
                    )
                    SELECT COUNT(*) FROM del
                    """,
                    tier, cutoff,
                )
                total_deleted += int(deleted or 0)
                _log.info("prune_messages.tier_done tier=%s deleted=%s", tier, deleted)
        return total_deleted
```

**File 2 — `temporal/activities/reconcile_stripe.py`:**

```python
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import stripe
from temporalio import activity

_log = logging.getLogger("api_server.temporal.reconcile_stripe")


class ReconcileStripeActivities:
    def __init__(self, *, db_pool: Any, stripe_client: stripe.StripeClient) -> None:
        self.db_pool = db_pool
        self.stripe_client = stripe_client

    @activity.defn(name="reconcile_stripe")
    async def reconcile(self) -> int:
        """Query Stripe for checkout.session.completed events in last 15 min not in our table.
        Returns count of newly-applied events. Idempotency via stripe_webhook_events UNIQUE."""
        # Open Q #3 — query window 15 min (3× redundancy on the schedule period).
        from ...routes.billing_webhook import _handle_checkout_completed

        cutoff = int((datetime.now(timezone.utc) - timedelta(minutes=15)).timestamp())
        events = self.stripe_client.events.list(params={
            "type": "checkout.session.completed",
            "created": {"gte": cutoff},
            "limit": 100,
        })
        applied = 0
        async with self.db_pool.acquire() as conn:
            for event in events.data:
                # Check if already in our table.
                already = await conn.fetchval(
                    "SELECT 1 FROM stripe_webhook_events WHERE stripe_event_id = $1",
                    event.id,
                )
                if already is not None:
                    continue
                # Apply via same handler used by the webhook route.
                async with conn.transaction():
                    inserted = await conn.fetchval(
                        """
                        INSERT INTO stripe_webhook_events (stripe_event_id, event_type, payload)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (stripe_event_id) DO NOTHING
                        RETURNING stripe_event_id
                        """,
                        event.id, event.type, str(event),  # str(event) is acceptable; payload is audit-only
                    )
                    if inserted is None:
                        continue
                    await _handle_checkout_completed(conn, event)
                    applied += 1
                    _log.info("reconcile_stripe.applied_missed_event id=%s", event.id)
        return applied
```

**File 3 — `temporal/activities/reconcile_ledger.py`:**

```python
from __future__ import annotations
import logging
from typing import Any

import sentry_sdk
from temporalio import activity

_log = logging.getLogger("api_server.temporal.reconcile_ledger")


class ReconcileLedgerActivities:
    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="reconcile_ledger")
    async def reconcile(self) -> int:
        """For every credit_balances row, recompute SUM(amount_cents) from ledger.
        If cache != truth by > 1 cent, log Sentry alert. Returns drift count."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                  b.user_id,
                  b.balance_cents AS cache_cents,
                  COALESCE((
                    SELECT SUM(amount_cents) FROM credit_transactions
                    WHERE user_id = b.user_id
                  ), 0)::BIGINT AS truth_cents
                FROM credit_balances b
                """,
            )
            drift_count = 0
            for r in rows:
                drift = int(r["cache_cents"]) - int(r["truth_cents"])
                if abs(drift) >= 1:
                    drift_count += 1
                    _log.warning(
                        "reconcile_ledger.drift user_id=%s cache_cents=%s truth_cents=%s drift=%s",
                        r["user_id"], r["cache_cents"], r["truth_cents"], drift,
                    )
                    sentry_sdk.capture_message(
                        f"credit_balances cache drift detected user_id={r['user_id']} drift_cents={drift}",
                        level="error",
                    )
                    # Repair the cache from ledger truth.
                    await conn.execute(
                        "UPDATE credit_balances SET balance_cents = $1, updated_at = NOW() WHERE user_id = $2",
                        int(r["truth_cents"]), r["user_id"],
                    )
            return drift_count
```

**Files 4-6 — `temporal/workflows/{prune_messages,reconcile_stripe,reconcile_ledger}.py`:** Mirror `dispatch_message.py:1-50, 86-238`. Each is a thin workflow that executes its activity by name with `RetryPolicy(maximum_attempts=3)` and `start_to_close_timeout=timedelta(seconds=120)` (or 300 for reconcile_stripe given the network round-trip).

```python
# Example for prune_messages.py — replicate shape for the other two with appropriate name + activity ref
from __future__ import annotations
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities import prune_messages

@workflow.defn(name="PruneMessagesWorkflow")
class PruneMessagesWorkflow:
    @workflow.run
    async def run(self) -> int:
        return await workflow.execute_activity(
            prune_messages.PruneMessagesActivities.prune_messages,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
```

For reconcile_stripe:
- Name: `ReconcileStripeWorkflow`
- Activity ref: `reconcile_stripe.ReconcileStripeActivities.reconcile`
- Timeout: 300s (network)

For reconcile_ledger:
- Name: `ReconcileLedgerWorkflow`
- Activity ref: `reconcile_ledger.ReconcileLedgerActivities.reconcile`
- Timeout: 120s

**File 7 — `temporal/schedules.py`:** Use the spike-d template verbatim:

```python
from __future__ import annotations
import logging
from datetime import timedelta

from temporalio.client import (
    Client, Schedule, ScheduleSpec, ScheduleIntervalSpec, ScheduleActionStartWorkflow,
)
from temporalio.exceptions import RPCError

from .workflows.prune_messages import PruneMessagesWorkflow
from .workflows.reconcile_stripe import ReconcileStripeWorkflow
from .workflows.reconcile_ledger import ReconcileLedgerWorkflow

_log = logging.getLogger("api_server.temporal.schedules")


async def _create_or_update(client: Client, *, schedule_id: str, schedule: Schedule) -> None:
    try:
        await client.create_schedule(schedule_id, schedule)
        _log.info("temporal.schedule.created id=%s", schedule_id)
    except RPCError as e:
        if "already exists" in str(e).lower():
            handle = client.get_schedule_handle(schedule_id)
            await handle.update(lambda _input: schedule)
            _log.info("temporal.schedule.updated id=%s", schedule_id)
        else:
            raise


async def register_schedules(client: Client, task_queue: str) -> None:
    """Idempotent registration of Phase B's 3 schedules. Run once at api_server boot AND worker boot —
    second invocation falls into the update branch instead of crashing (Pitfall 8)."""
    await _create_or_update(client, schedule_id="phase-b-prune-messages-daily", schedule=Schedule(
        action=ScheduleActionStartWorkflow(
            PruneMessagesWorkflow.run,
            id="prune-messages",
            task_queue=task_queue,
        ),
        spec=ScheduleSpec(cron_expressions=["0 3 * * *"]),  # daily 03:00 UTC
    ))
    await _create_or_update(client, schedule_id="phase-b-reconcile-stripe-5min", schedule=Schedule(
        action=ScheduleActionStartWorkflow(
            ReconcileStripeWorkflow.run,
            id="reconcile-stripe",
            task_queue=task_queue,
        ),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=5))]),
    ))
    await _create_or_update(client, schedule_id="phase-b-reconcile-ledger-nightly", schedule=Schedule(
        action=ScheduleActionStartWorkflow(
            ReconcileLedgerWorkflow.run,
            id="reconcile-ledger",
            task_queue=task_queue,
        ),
        spec=ScheduleSpec(cron_expressions=["30 4 * * *"]),  # nightly 04:30 UTC (after prune)
    ))
```
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run python -c "from api_server.temporal.workflows import prune_messages, reconcile_stripe, reconcile_ledger; from api_server.temporal.schedules import register_schedules; print('imports ok')"</automated>
  </verify>
  <done>
- All 7 files exist + import cleanly.
- Each workflow file has @workflow.defn(name="...") + @workflow.run.
- Each activity file has @activity.defn(name="...") + class-bound shape mirroring record_usage.py.
- schedules.py exposes register_schedules.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: worker.py + main.py registration + integration tests for all 3 workflows + idempotent registration</name>
  <files>api_server/src/api_server/temporal/worker.py, api_server/src/api_server/main.py, api_server/tests/temporal/test_prune_messages_workflow.py, api_server/tests/temporal/test_reconcile_stripe_workflow.py, api_server/tests/temporal/test_reconcile_ledger_workflow.py, api_server/tests/temporal/test_schedules_idempotent.py</files>
  <read_first>
    - api_server/src/api_server/temporal/worker.py (FULL — current Worker constructor + activity instantiation block)
    - api_server/src/api_server/main.py (FULL — current lifespan + Temporal client connect)
    - api_server/tests/temporal/test_dispatch_message_workflow.py (FULL — WorkflowEnvironment.start_time_skipping pattern; class-bound activity registration)
    - api_server/tests/_spikes/spike_d_temporal_schedule.py (Wave 0 evidence)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_prune_messages_deletes_messages_older_than_tier_retention
    - test_prune_messages_keeps_ultra_user_messages_at_one_year
    - test_reconcile_stripe_picks_up_missed_event_and_applies_via_handler
    - test_reconcile_stripe_skips_already_processed_events
    - test_reconcile_ledger_emits_sentry_capture_message_when_drift_detected
    - test_reconcile_ledger_repairs_cache_to_match_ledger_truth
    - test_reconcile_ledger_no_drift_no_sentry
    - test_register_schedules_first_call_creates_all_three
    - test_register_schedules_second_call_updates_without_error (Pitfall 8 fix proof)
  </behavior>
  <action>
**File 1 — `api_server/src/api_server/temporal/worker.py`:** Modify in 3 places:

(a) Imports (top):
```python
from .activities.prune_messages import PruneMessagesActivities
from .activities.reconcile_stripe import ReconcileStripeActivities
from .activities.reconcile_ledger import ReconcileLedgerActivities
from .workflows.prune_messages import PruneMessagesWorkflow
from .workflows.reconcile_stripe import ReconcileStripeWorkflow
from .workflows.reconcile_ledger import ReconcileLedgerWorkflow
from .schedules import register_schedules
```

(b) Class-bound activity instantiation block (around lines 175-192). Add:
```python
prune_acts = PruneMessagesActivities(db_pool=db_pool)
# Stripe client construction needs settings.stripe_api_key — read from settings same way Phase 31 does
stripe_client_for_reconcile = stripe.StripeClient(settings.stripe_api_key)
reconcile_stripe_acts = ReconcileStripeActivities(db_pool=db_pool, stripe_client=stripe_client_for_reconcile)
reconcile_ledger_acts = ReconcileLedgerActivities(db_pool=db_pool)
```

(c) `Worker(...)` constructor (around lines 222-242):
```python
worker = Worker(
    client,
    task_queue=settings.temporal_task_queue,
    workflows=[
        DispatchMessageWorkflow,
        BackfillOpenRouterCostWorkflow,
        PruneMessagesWorkflow,             # NEW
        ReconcileStripeWorkflow,           # NEW
        ReconcileLedgerWorkflow,           # NEW
    ],
    activities=[
        # ...existing entries...
        debit_acts.debit_balance,
        backfill_acts.backfill,
        prune_acts.prune_messages,         # NEW
        reconcile_stripe_acts.reconcile,   # NEW
        reconcile_ledger_acts.reconcile,   # NEW
    ],
    max_concurrent_activities=10,
    max_activities_per_second=5,
)
```

(d) After `client = await make_client(settings)` succeeds, BEFORE `await worker.run()`:
```python
await register_schedules(client, settings.temporal_task_queue)
```

**File 2 — `api_server/src/api_server/main.py`:** Add a redundant `register_schedules` call in `lifespan` after the Temporal client connect. The redundancy is intentional — it ensures schedules exist even if the worker boots later. The helper is idempotent (Pitfall 8 fix in schedules.py).

```python
# After app.state.temporal_client connection succeeds:
from .temporal.schedules import register_schedules
try:
    await register_schedules(app.state.temporal_client, settings.temporal_task_queue)
except Exception as e:
    _log.warning("temporal.schedule_register_failed_in_api_server fallback_to_worker error=%s", e)
```

The api_server-side registration uses a try/except so failure doesn't crash boot — the worker's registration is the canonical path.

**File 3 — `api_server/tests/temporal/test_prune_messages_workflow.py`:** Mirror `tests/temporal/test_dispatch_message_workflow.py`:
- WorkflowEnvironment.start_time_skipping
- Postgres testcontainer + asyncpg pool
- Apply migration 014
- Seed users (free, pro, ultra) + inapp_messages with various ages (1d, 5d, 8d, 31d, 100d, 365d)
- Run PruneMessagesWorkflow via `env.client.execute_workflow(PruneMessagesWorkflow.run, ...)`
- Assert: free user's 8d/31d/100d/365d messages are deleted; pro user's 31d/100d/365d are deleted; ultra user keeps all messages.

**File 4 — `api_server/tests/temporal/test_reconcile_stripe_workflow.py`:** Mock the StripeClient.events.list to return a list of fake events including one whose id is NOT in stripe_webhook_events. Run ReconcileStripeWorkflow. Assert: the missed event was applied (a row appears in stripe_webhook_events; if checkout.session.completed, a credit_transactions row was inserted).

**File 5 — `api_server/tests/temporal/test_reconcile_ledger_workflow.py`:**
- test_no_drift_no_sentry: seed user with balance=100; ledger SUM=100; run workflow; assert sentry_sdk.capture_message NOT called (mock it).
- test_drift_emits_sentry_and_repairs: seed user with balance=100 in cache but ledger SUM=50; run workflow; assert sentry_sdk.capture_message called with "drift" message; assert balance_cents now equals 50.

**File 6 — `api_server/tests/temporal/test_schedules_idempotent.py`:** Use real Temporal cluster (deploy stack must be up — guard with a skip if not reachable). Call `register_schedules(...)` twice. Assert no exception. Assert the 3 schedule handles exist via `client.list_schedules()`. Cleanup: delete the schedules at end.
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/temporal/test_prune_messages_workflow.py tests/temporal/test_reconcile_stripe_workflow.py tests/temporal/test_reconcile_ledger_workflow.py tests/temporal/test_schedules_idempotent.py -x</automated>
  </verify>
  <done>
- All 9 workflow + idempotency tests pass.
- `grep -c 'register_schedules' api_server/src/api_server/temporal/worker.py` ≥ 1.
- `grep -c 'PruneMessagesWorkflow\|ReconcileStripeWorkflow\|ReconcileLedgerWorkflow' api_server/src/api_server/temporal/worker.py` = 3 (in workflows= list).
- `grep -c 'register_schedules' api_server/src/api_server/main.py` ≥ 1.
- Existing dispatch_message_workflow tests still pass (regression gate).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Temporal worker → Stripe API (reconcile_stripe) | outbound; stripe_client constructed from settings.stripe_api_key inside the worker process |
| Temporal worker → Postgres | atomic ledger updates inside conn.transaction(); same patterns as the activity in Plan 08 |
| Temporal worker → Sentry | drift events emit capture_message at error level |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-DRIFT | Tampering | activities/reconcile_ledger.py | mitigate | nightly recompute + Sentry alert + auto-repair to truth; D-17 ledger-as-truth invariant maintained |
| T-B-MISS | Repudiation | activities/reconcile_stripe.py | mitigate | 5-min poller queries Stripe directly; idempotency via stripe_webhook_events UNIQUE prevents double-apply if webhook eventually arrives |
| T-B-SCH | DoS | temporal/schedules.py | mitigate | try/RPCError/update fallback prevents crash-loop on second worker boot (Pitfall 8); spike-d (Wave 0) proved this |
| T-B-PRUNE | Tampering | activities/prune_messages.py | mitigate | DELETE filtered by tier-and-cutoff; user_id remains scoped to the user's own messages via the JOIN; ultra users never lose data |
| T-B-LK | InfoDisclosure | reconcile_stripe payload column | mitigate | str(event) is captured into stripe_webhook_events.payload; if Stripe events ever start including PAN data we'd want to redact — for v1, the events we listen to (D-14) don't carry card details |
</threat_model>

<verification>
- 9 workflow + idempotency tests pass against real testcontainers + Temporal WorkflowEnvironment.
- Schedules survive worker restart (idempotency test confirms).
- Drift detection emits Sentry capture_message + auto-repairs cache.
</verification>

<success_criteria>
- `cd api_server && uv run pytest tests/temporal/ -x` all green (regression for existing dispatch_message workflow tests included).
- Manual smoke (deploy stack up): `docker compose -f deploy/docker-compose.prod.yml restart temporal-worker` → check `docker compose logs temporal-worker | grep schedule.created` shows the 3 schedules registered (or `schedule.updated` on second boot).
- `tctl schedule describe phase-b-prune-messages-daily` (or via Temporal Web UI) confirms each schedule exists.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-09-SUMMARY.md` documenting the 3 workflows + the schedule registration helper + Sentry drift wiring.
</output>
