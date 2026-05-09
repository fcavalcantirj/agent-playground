---
phase: B-stripe
plan: 08
type: execute
wave: 4
depends_on: [B-stripe-02, B-stripe-04]
files_modified:
  - api_server/src/api_server/temporal/activities/debit_balance.py
  - api_server/src/api_server/temporal/worker.py
  - api_server/src/api_server/routes/llm_proxy.py
  - api_server/tests/temporal/test_debit_balance_activity.py
  - api_server/tests/routes/test_llm_proxy_402.py
autonomous: true
gap_closure: false
requirements_addressed:
  - D-12 (pre-flight 402 — tier='ultra' AND balance < 1)
  - D-13 (debit only on success)
  - D-17 (atomic ledger debit + balance rebuild same-tx; idempotent on UNIQUE)
  - D-22 (Decimal-as-string contract preserved per Phase 28 D-22 lock)
  - MET-07 (pre-authorized token budget — D-12 floor estimation)
must_haves:
  truths:
    - "debit_balance activity body replaced; @activity.defn(name='debit_balance') decorator + signature byte-identical to Phase 28 contract"
    - "Activity returns Decimal-as-string ('0' for non-ultra / failure / no-usage cases; '0.000123' for actual debits)"
    - "When tier='ultra' AND usage_logs.status='success' AND cost_usd>0, ledger row inserted + balance recomputed in same DB tx"
    - "Activity is idempotent on UNIQUE(reference_id, reference_type) — Temporal retry produces no double-debit"
    - "llm_proxy.py inserts a pre-flight 402 check between section 2 (BYOK cache resolve) and section 3 (body mutation)"
    - "Pre-flight 402 fires only when tier='ultra' AND balance_cents < 1 (predicate also catches negative balances per D-16 + Pitfall 6)"
    - "Pre-flight 402 uses ErrorCode.INSUFFICIENT_BALANCE"
    - "dispatch_message.py call site is byte-identical (Phase 28 D-22 lock honored)"
  artifacts:
    - path: "api_server/src/api_server/temporal/activities/debit_balance.py"
      provides: "Phase B body — class-bound DebitBalanceActivities with ledger-as-truth implementation"
      contains: "class DebitBalanceActivities"
    - path: "api_server/src/api_server/routes/llm_proxy.py"
      provides: "Pre-flight 402 block at section 2.5"
      contains: "INSUFFICIENT_BALANCE"
  key_links:
    - from: "temporal/activities/debit_balance.py"
      to: "services/ledger.py::debit_user"
      via: "function call inside conn.transaction()"
      pattern: "from \\.\\.\\.services\\.ledger import debit_user|from .*services.ledger"
    - from: "temporal/worker.py"
      to: "DebitBalanceActivities class"
      via: "class instantiation with db_pool injection + register debit_acts.debit_balance in activities list"
      pattern: "debit_acts\\.debit_balance"
---

<objective>
Two narrowly-scoped api_server modifications that together close the Phase B billing loop: (1) replace `debit_balance` activity body with the real ledger-as-truth implementation; (2) insert pre-flight 402 in `llm_proxy.py`. Both are byte-additive at their integration points — Phase 28's `dispatch_message.py` call site is sealed.

Purpose: Without these two changes, ultra users would accumulate `usage_logs` rows but their balance would never debit, AND they could keep making LLM calls past balance=0.
Output: Replaced activity body + class-bound rewrite for db_pool injection; pre-flight 402 block in llm_proxy.py; integration tests for both.
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
@api_server/src/api_server/temporal/activities/debit_balance.py
@api_server/src/api_server/temporal/activities/record_usage.py
@api_server/src/api_server/temporal/workflows/dispatch_message.py
@api_server/src/api_server/temporal/worker.py
@api_server/src/api_server/routes/llm_proxy.py
@api_server/src/api_server/services/ledger.py

<interfaces>
From api_server/src/api_server/temporal/activities/debit_balance.py (current — Phase 28 stub):
```python
@activity.defn(name="debit_balance")
async def debit_balance(inp: DispatchMessageInput) -> str:
    return "0"  # Phase B replaces this body
```

From api_server/src/api_server/temporal/workflows/dispatch_message.py (Phase 28 D-22 — DO NOT modify):
```python
charged = await workflow.execute_activity(
    debit_balance.debit_balance,
    inp,
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=RetryPolicy(maximum_attempts=1),
)
```

From api_server/src/api_server/temporal/activities/record_usage.py (template for class-bound activity):
```python
class RecordUsageActivities:
    def __init__(self, *, db_pool):
        self.db_pool = db_pool
    @activity.defn(name="record_usage")
    async def record_usage(self, inp): ...
```

From api_server/src/api_server/services/ledger.py (Wave 1):
```python
async def debit_user(conn, *, user_id, cost_cents, reference_id, reference_type) -> Decimal
```

From api_server/src/api_server/routes/llm_proxy.py:
- Section 1, 2 around lines 274-305 — BYOK cache resolution
- Section 3 around lines 306-322 — body mutation + upstream forward
- Insertion point: between sections 2 and 3
- _err helper at lines 77-82
- request.app.state.db is the asyncpg pool
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: temporal/activities/debit_balance.py — replace body + class-bound rewrite + worker registration</name>
  <files>api_server/src/api_server/temporal/activities/debit_balance.py, api_server/src/api_server/temporal/worker.py, api_server/tests/temporal/test_debit_balance_activity.py</files>
  <read_first>
    - api_server/src/api_server/temporal/activities/debit_balance.py (FULL — current Phase 28 stub)
    - api_server/src/api_server/temporal/activities/record_usage.py (FULL — class-bound template)
    - api_server/src/api_server/temporal/worker.py (FULL — current activity registration order; add debit_acts instantiation alongside record_acts)
    - api_server/src/api_server/temporal/workflows/dispatch_message.py:190-205 (FORBIDDEN to modify — Phase 28 D-22 lock)
    - api_server/src/api_server/services/ledger.py (debit_user signature)
    - api_server/tests/temporal/test_backfill_openrouter_cost_activity.py (test pattern for class-bound activity + Postgres testcontainer + WorkflowEnvironment)
    - api_server/tests/_spikes/spike_b_debit_activity_contract.py (Wave 0 evidence — UniqueViolationError idempotency proven)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_returns_zero_for_free_tier
    - test_returns_zero_for_pro_tier
    - test_returns_zero_when_usage_logs_status_is_failed
    - test_returns_zero_when_usage_logs_cost_usd_is_null
    - test_returns_zero_when_no_usage_logs_row_for_message
    - test_inserts_negative_amount_ledger_row_for_ultra_with_successful_usage
    - test_rebuilds_balance_cache_from_ledger_sum
    - test_idempotent_on_temporal_retry (run twice; assert one ledger row, returns same Decimal)
    - test_call_site_byte_identity_in_dispatch_message_workflow_unchanged (grep test against dispatch_message.py)
  </behavior>
  <action>
**File 1 — `api_server/src/api_server/temporal/activities/debit_balance.py`:** Replace entire file:

```python
"""Phase B body for debit_balance activity.

Contract preserved from Phase 28 D-22:
  - @activity.defn(name="debit_balance") — name kwarg byte-identical
  - signature: async def debit_balance(self, inp) -> str
  - returns Decimal-as-string ("0" / "0.000034") because Temporal JSON serializer can't
    handle Decimal directly; recover losslessly via Decimal(str(...)).

Behavior (D-12 + D-13 + D-17):
  - Read users.tier; if not 'ultra', return "0" (BYOK tiers don't debit).
  - Read usage_logs row for inp.message_id + inp.user_id; if status != 'success' or
    cost_usd is null/zero, return "0" (debit only on success).
  - cost_cents = int(cost_usd * 100) — cost_usd already has ap_multiplier baked in
    at proxy time (llm_proxy.py:178-203 — Phase 29 path).
  - Atomic INSERT into credit_transactions + UPDATE credit_balances in same tx.
  - Idempotent on UNIQUE(reference_id=usage_log.id, reference_type='usage_log')
    so Temporal retry produces no double-debit.
"""
from __future__ import annotations
import logging
from decimal import Decimal
from typing import Any

from temporalio import activity

_log = logging.getLogger("api_server.temporal.debit_balance")


class DebitBalanceActivities:
    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="debit_balance")
    async def debit_balance(self, inp: Any) -> str:
        """Phase B body. Returns Decimal-as-string per Phase 28 D-22 contract."""
        from ...services.ledger import debit_user

        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                tier = await conn.fetchval(
                    "SELECT tier FROM users WHERE id = $1::uuid", inp.user_id,
                )
                if tier != "ultra":
                    return "0"

                row = await conn.fetchrow(
                    """
                    SELECT id, cost_usd, status FROM usage_logs
                    WHERE message_id = $1::uuid AND user_id = $2::uuid
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    inp.message_id, inp.user_id,
                )
                if row is None or row["status"] != "success" or not row["cost_usd"]:
                    return "0"

                cost_cents = int(
                    (Decimal(str(row["cost_usd"])) * Decimal(100)).quantize(Decimal("1"))
                )
                if cost_cents <= 0:
                    return "0"

                charged = await debit_user(
                    conn,
                    user_id=row["user_id"] if "user_id" in row else inp.user_id,
                    cost_cents=cost_cents,
                    reference_id=str(row["id"]),
                    reference_type="usage_log",
                )
                _log.info(
                    "debit_balance.applied user_id=%s message_id=%s cents=%s",
                    inp.user_id, inp.message_id, cost_cents,
                )
                return str(charged)


# ----- Backward-compatibility shim for the workflow's `debit_balance.debit_balance` reference -----
# The Phase 28 dispatch_message.py workflow imports this module and calls
#   debit_balance.debit_balance
# (the standalone module-level function) via execute_activity.
#
# Activity registration is now class-bound (worker.py instantiates DebitBalanceActivities
# and passes the bound method into the worker's activities= list).
# The workflow refers to it by activity name ("debit_balance") via Temporal's name-based dispatch
# — it does NOT need the standalone function to still exist.
#
# However, dispatch_message.py uses `debit_balance.debit_balance` as the static-typed
# activity reference for `execute_activity(...)`. Temporal's Python SDK accepts EITHER:
#   (a) a function reference (used to extract the registered name), OR
#   (b) a string name.
# The class-bound method is fine for (a) — the workflow imports
#   `from ..activities.debit_balance import DebitBalanceActivities`
# and uses `DebitBalanceActivities.debit_balance` via the SDK's class-method type hint.
#
# Phase 28 D-22 says the call site is sealed. Re-read workflows/dispatch_message.py:190-205
# to verify the exact reference. If it imports `debit_balance.debit_balance` (the function),
# we keep that import path working by adding a module-level alias:

debit_balance = DebitBalanceActivities.debit_balance  # type: ignore[assignment]
# This preserves `debit_balance.debit_balance` referencing semantics for the workflow.
```

**Important:** Re-read `workflows/dispatch_message.py:190-205` and confirm the exact reference. If the workflow uses `debit_balance.debit_balance(inp)` via `execute_activity(debit_balance.debit_balance, ...)`, the module alias above preserves the binding. If for some reason it uses string activity name `"debit_balance"`, the class-bound `@activity.defn(name="debit_balance")` is sufficient.

**File 2 — `api_server/src/api_server/temporal/worker.py` modification:** Locate the existing class-bound activity instantiation block (around lines 175-192). Add:

```python
from .activities.debit_balance import DebitBalanceActivities
...
debit_acts = DebitBalanceActivities(db_pool=db_pool)
```

In the `Worker(...)` constructor's `activities=` list, REPLACE any existing standalone `debit_balance` reference (e.g. `debit_balance.debit_balance`) with `debit_acts.debit_balance`. Keep the rest of the activities list unchanged.

**File 3 — `api_server/tests/temporal/test_debit_balance_activity.py`:** Mirror `tests/temporal/test_backfill_openrouter_cost_activity.py`:

- `WorkflowEnvironment.start_time_skipping()` fixture.
- Postgres testcontainer + asyncpg pool.
- Run migration 014 in fixture setup.
- Instantiate `DebitBalanceActivities(db_pool=test_pool)`.
- Use a tiny test workflow that invokes the activity directly:

```python
@workflow.defn(name="TestDebitBalanceWorkflow")
class TestDebitBalanceWorkflow:
    @workflow.run
    async def run(self, inp) -> str:
        return await workflow.execute_activity(
            "debit_balance",                # by name
            inp,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
```

For each behavior: seed users + usage_logs + (where needed) credit_balances rows; execute the test workflow with a synthetic `inp` dataclass; assert the return value AND the post-state DB rows.

For the call-site-byte-identity test (a grep test, not a Temporal test):

```python
def test_dispatch_message_call_site_unchanged():
    src = pathlib.Path("api_server/src/api_server/temporal/workflows/dispatch_message.py").read_text()
    assert "execute_activity(\n        debit_balance.debit_balance" in src or \
           'execute_activity(debit_balance.debit_balance' in src or \
           'execute_activity("debit_balance"' in src
```

Adjust the assertion to match what dispatch_message.py actually contains (re-read the file).
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/temporal/test_debit_balance_activity.py -x</automated>
  </verify>
  <done>
- 9 activity behavior tests + 1 call-site-byte-identity grep test pass.
- `git diff api_server/src/api_server/temporal/workflows/dispatch_message.py` produces no output (file unchanged — Phase 28 D-22 lock honored).
- `grep -c '@activity.defn(name=\"debit_balance\")' api_server/src/api_server/temporal/activities/debit_balance.py` = 1.
- `grep -c 'class DebitBalanceActivities' api_server/src/api_server/temporal/activities/debit_balance.py` = 1.
- `grep -c 'debit_acts = DebitBalanceActivities' api_server/src/api_server/temporal/worker.py` = 1.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: routes/llm_proxy.py — pre-flight 402 block + integration test</name>
  <files>api_server/src/api_server/routes/llm_proxy.py, api_server/tests/routes/test_llm_proxy_402.py</files>
  <read_first>
    - api_server/src/api_server/routes/llm_proxy.py:265-340 (FULL — section 1, 2, 3 numbered comments + _err helper)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"routes/llm_proxy.py MODIFICATION" — exact insertion point)
    - .planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md (Pattern 3)
    - api_server/src/api_server/models/errors.py (ErrorCode.INSUFFICIENT_BALANCE added in Plan 03)
    - api_server/tests/routes/test_llm_proxy.py (existing test pattern + FakeBYOKCache + respx)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_proxy_passes_through_for_free_tier_with_zero_balance (no 402; goes through to upstream)
    - test_proxy_passes_through_for_pro_tier_with_zero_balance (no 402; pro is BYOK)
    - test_proxy_passes_through_for_ultra_tier_with_one_cent_balance (just at the floor)
    - test_proxy_returns_402_INSUFFICIENT_BALANCE_for_ultra_tier_with_zero_balance
    - test_proxy_returns_402_for_ultra_tier_with_negative_balance (catches refunds — D-16 path)
    - test_proxy_402_skips_upstream_call (assert respx mock was NOT called)
  </behavior>
  <action>
**Modification — `api_server/src/api_server/routes/llm_proxy.py`:** Locate sections 2 and 3 (numbered comments). Insert a new section 2.5 between them:

```python
            # ---------- 2.5. Phase B pre-flight 402 (D-12) ----------
            async with request.app.state.db.acquire() as conn:
                tier_row = await conn.fetchrow(
                    """
                    SELECT u.tier, COALESCE(b.balance_cents, 0)::BIGINT AS balance_cents
                    FROM users u
                    LEFT JOIN credit_balances b ON b.user_id = u.id
                    WHERE u.id = $1
                    """,
                    user_id,
                )
            if tier_row and tier_row["tier"] == "ultra" and int(tier_row["balance_cents"]) < 1:
                return _err(
                    402, ErrorCode.INSUFFICIENT_BALANCE,
                    "Out of credits. Top up to continue.",
                )
```

The block:
- Acquires a fresh conn from the pool (does not piggy-back on any existing transaction in this handler — verify via re-read).
- Reads tier + balance via LEFT JOIN.
- Predicate `< 1` covers both 0 and negative balances (D-16 + Pitfall 6).
- Returns 402 immediately when applicable; existing section 3 forwarding is skipped.

**Indentation:** match the existing section comments. Use the existing comment-numbering style.

**Imports:** ErrorCode.INSUFFICIENT_BALANCE was added in Plan 03; ensure it's imported at the top of llm_proxy.py.

**File — `api_server/tests/routes/test_llm_proxy_402.py`:** Postgres testcontainer + async_client + respx. Mirror `tests/routes/test_llm_proxy.py` setup:

- Seed users with various tiers + credit_balances rows.
- POST a fake LLM request body to the existing proxy route (same shape as current proxy tests).
- For each behavior, assert response status_code AND whether the respx mock for the upstream provider was hit (using `respx_mock.calls.call_count`).

For the "passes through to upstream" tests, mock the upstream provider response via respx and assert the response was 200 with the upstream body.

For the 402 tests, do NOT mock the upstream (or mock it to fail loudly); assert the response is 402 AND `respx_mock.calls.call_count == 0`.
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/routes/test_llm_proxy_402.py tests/routes/test_llm_proxy.py -x</automated>
  </verify>
  <done>
- All 6 new 402 tests pass + existing llm_proxy tests still pass (regression gate).
- `grep -c '# ---------- 2.5. Phase B pre-flight' api_server/src/api_server/routes/llm_proxy.py` = 1.
- `grep -c 'INSUFFICIENT_BALANCE' api_server/src/api_server/routes/llm_proxy.py` = 1.
- The 402 test that asserts `respx.calls.call_count == 0` proves upstream is skipped.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Workflow → activity (Temporal) | retried by Temporal; activity must be idempotent |
| llm_proxy → upstream LLM | platform-billed only when tier='ultra' AND balance>=1¢ |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-IDP | Tampering | activities/debit_balance.py | mitigate | UNIQUE(reference_id=usage_log.id, reference_type='usage_log') prevents Temporal-retry double-debit; spike-b proved this round-trip in Wave 0 |
| T-B-NB | Tampering | routes/llm_proxy.py pre-flight 402 | mitigate | predicate `balance_cents < 1` is satisfied by 0 AND any negative value; refund-driven negative balance correctly triggers 402 (D-16) |
| T-B-CONTRACT | Tampering | activities/debit_balance.py + workflows/dispatch_message.py | mitigate | Phase 28 D-22 lock honored — workflow file is byte-unchanged, activity name + signature + return type byte-identical, only body replaced |
| T-B-ZERO | Tampering | activities/debit_balance.py D-13 path | mitigate | failed forward (status != 'success') OR null cost_usd → return "0" before any ledger write; spike-b's no-debit-on-failure case is encoded as a behavior test |
</threat_model>

<verification>
- All 9 activity tests + 6 proxy 402 tests + regression llm_proxy tests pass.
- Phase 28 D-22 contract preserved (grep-test asserts dispatch_message.py byte-unchanged).
- Idempotency on retry verified by behavior test.
</verification>

<success_criteria>
- `cd api_server && uv run pytest tests/temporal/test_debit_balance_activity.py tests/routes/test_llm_proxy_402.py tests/routes/test_llm_proxy.py tests/temporal/test_dispatch_message_workflow.py -x` all green.
- `git diff api_server/src/api_server/temporal/workflows/dispatch_message.py` is empty.
- Manual smoke (with deploy stack + ultra-tier user with balance=0): POST a chat message → response is 402 with code "insufficient_balance".
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-08-SUMMARY.md` listing the 2 modifications + the contract-preservation evidence.
</output>
