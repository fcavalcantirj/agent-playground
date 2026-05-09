---
phase: B-stripe
plan: 06
type: execute
wave: 3
depends_on: [B-stripe-02]
files_modified:
  - api_server/src/api_server/routes/billing_webhook.py
  - api_server/src/api_server/main.py
  - api_server/tests/_fixtures/sign_webhook.py
  - api_server/tests/_fixtures/stripe_webhooks/checkout_session_completed.json
  - api_server/tests/_fixtures/stripe_webhooks/customer_subscription_created.json
  - api_server/tests/_fixtures/stripe_webhooks/customer_subscription_updated.json
  - api_server/tests/_fixtures/stripe_webhooks/customer_subscription_deleted.json
  - api_server/tests/_fixtures/stripe_webhooks/invoice_paid.json
  - api_server/tests/_fixtures/stripe_webhooks/invoice_payment_failed.json
  - api_server/tests/_fixtures/stripe_webhooks/charge_refunded.json
  - api_server/tests/routes/test_billing_webhook.py
autonomous: true
gap_closure: false
requirements_addressed:
  - D-04 (webhook is sole writer of users.tier)
  - D-14 (7-event matrix as amended by AMD-05; payment_intent.succeeded EXCLUDED)
  - D-15 (Pro→Free downgrade — subscription.deleted flips tier + auto-pauses 4 oldest agents)
  - D-16 (charge.refunded inserts negative ledger row)
  - D-17 (idempotency table same-tx with side-effect; ledger-as-truth rebuild)
  - D-22 (signed-fixture test substrate; AMD-02)
  - D-26 (tier_change audit row in credit_transactions)
  - AMD-04 (StripeClient.construct_event service pattern)
  - AMD-05 (no payment_intent.succeeded handler — single-event listening for credit packs)
  - BIL-02 (stripe_event_id UNIQUE + first-action-in-tx idempotency)
  - BIL-03 (signature verify + 5-min timestamp tolerance — SDK-provided)
must_haves:
  truths:
    - "POST /v1/billing/webhook is a public route (no require_user) and returns 400 on missing/invalid Stripe-Signature"
    - "Webhook handler uses StripeClient.construct_event (service pattern AMD-04), NOT module-level stripe.Webhook.construct_event"
    - "Idempotency: stripe_webhook_events.stripe_event_id UNIQUE; duplicate event id returns 200 immediately, side-effect skipped"
    - "checkout.session.completed inserts a credit_transactions topup row + rebuilds balance + flips tier='ultra' for the user (D-04 + D-26)"
    - "customer.subscription.created flips users.tier to 'pro' + records tier_change audit row"
    - "customer.subscription.updated handles cancel_at_period_end=true by storing the flag (no immediate tier flip)"
    - "customer.subscription.deleted flips users.tier to 'free' + auto-pauses 4 oldest non-paused agents (D-15)"
    - "charge.refunded inserts a negative-amount ledger row (kind='refund') + balance recomputes"
    - "invoice.paid is acknowledged-without-side-effect (audit log only)"
    - "invoice.payment_failed is acknowledged-without-side-effect (Stripe Smart Retries handle the rest)"
    - "payment_intent.succeeded is NOT in the event matrix (AMD-05) — handler explicitly does NOT branch on it"
    - "All 7 event types are covered by signed-fixture integration tests"
  artifacts:
    - path: "api_server/src/api_server/routes/billing_webhook.py"
      provides: "POST /v1/billing/webhook with signature verify + idempotency + 7-event branch"
      exports: ["router"]
    - path: "api_server/tests/_fixtures/sign_webhook.py"
      provides: "Hand-rolled HMAC sign helper (AMD-02 — stripe-mock has no webhook simulation)"
      exports: ["sign_webhook_payload"]
    - path: "api_server/tests/_fixtures/stripe_webhooks/"
      provides: "7 signed-fixture JSON payloads"
      contains: "id"
  key_links:
    - from: "billing_webhook.py"
      to: "stripe_webhook_events table"
      via: "INSERT ON CONFLICT (stripe_event_id) DO NOTHING in same tx as side-effect"
      pattern: "ON CONFLICT \\(stripe_event_id\\)"
    - from: "billing_webhook.py"
      to: "services/ledger.py::credit_user / record_tier_change"
      via: "function call inside async with conn.transaction() block"
      pattern: "credit_user|record_tier_change"
---

<objective>
The single most load-bearing surface in Phase B. Stripe → AP webhook delivery + idempotency + tier mutation. Sole writer of `users.tier` (D-04). Single transaction wraps idempotency-row + side-effect (Pitfall 2). 7-event matrix per D-14-as-amended (AMD-05 drops payment_intent.succeeded).

Purpose: Webhook handler is the heart of the Stripe contract. Tier flips, credit grants, refund revocations, downgrade auto-pause — all flow through this route.
Output: routes/billing_webhook.py, 7 signed fixtures, integration tests covering signature verification, idempotency, and each event branch.
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
@.planning/phases/B-stripe-paywall/B-stripe-02-SUMMARY.md
@api_server/src/api_server/routes/llm_proxy.py
@api_server/src/api_server/services/ledger.py
@api_server/src/api_server/services/stripe_client.py
@api_server/src/api_server/main.py
@api_server/tests/_spikes/spike_a_webhook_signature.py
@api_server/tests/_spikes/sign_webhook.py

<interfaces>
From api_server/src/api_server/services/ledger.py (Wave 1):
```python
async def credit_user(conn, *, user_id, kind, amount_cents, reference_id, reference_type) -> int  # returns new balance_cents
async def record_tier_change(conn, *, user_id, from_tier, to_tier, stripe_event_id) -> None
```

From Wave 0 spike-a (api_server/tests/_spikes/sign_webhook.py):
```python
def sign_webhook_payload(payload_bytes: bytes, secret: str, ts: int | None = None) -> str
```

From AMD-04 (StripeClient v15):
```python
client = stripe.StripeClient(api_key)
event = client.construct_event(payload_bytes, sig_header, secret)  # raises stripe.SignatureVerificationError
```

Stripe webhook event types (D-14 as amended):
- checkout.session.completed       → topup credit grant + tier flip if first
- customer.subscription.created    → tier='pro'
- customer.subscription.updated    → store cancel_at_period_end + period_end (no tier flip)
- customer.subscription.deleted    → tier='free' + auto-pause 4 oldest agents
- invoice.paid                     → ack (audit log only; no DB change)
- invoice.payment_failed           → ack (Stripe Smart Retries handle the rest)
- charge.refunded                  → ledger refund row (kind='refund', amount=-original)
- payment_intent.succeeded         → EXPLICITLY NOT HANDLED (AMD-05 — redundant with checkout.session.completed)

agent_containers table (existing — for D-15 auto-pause):
- columns include: id, user_id, status, created_at
- status enum currently includes 'running' / 'stopped' / 'failed' / etc — confirm via grep before adding 'auto_paused'

users table (Wave 1 migration 014 added):
- tier (text, CHECK in 'free'/'pro'/'ultra'); stripe_customer_id (text NULL); refund_writeoff_cents (bigint NOT NULL DEFAULT 0)
- subscription metadata: NEW columns may be needed — see Action below

stripe_webhook_events table (Wave 1):
- id (uuid pk); stripe_event_id (text UNIQUE); event_type (text); payload (text); created_at
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: routes/billing_webhook.py — signature verify + idempotency + 7-event branch</name>
  <files>api_server/src/api_server/routes/billing_webhook.py, api_server/tests/_fixtures/sign_webhook.py, api_server/tests/_fixtures/stripe_webhooks/checkout_session_completed.json, api_server/tests/_fixtures/stripe_webhooks/customer_subscription_created.json, api_server/tests/_fixtures/stripe_webhooks/customer_subscription_updated.json, api_server/tests/_fixtures/stripe_webhooks/customer_subscription_deleted.json, api_server/tests/_fixtures/stripe_webhooks/invoice_paid.json, api_server/tests/_fixtures/stripe_webhooks/invoice_payment_failed.json, api_server/tests/_fixtures/stripe_webhooks/charge_refunded.json, api_server/tests/routes/test_billing_webhook.py, api_server/src/api_server/main.py</files>
  <read_first>
    - api_server/src/api_server/routes/llm_proxy.py:265-340 (raw await request.body() pattern + app.state lookups + _err helper)
    - .planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md (Pattern 1 full template; Pitfalls 1, 2, 3)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"routes/billing_webhook.py" — full template)
    - api_server/src/api_server/services/ledger.py (Wave 1 — credit_user, record_tier_change signatures)
    - api_server/tests/_spikes/spike_a_webhook_signature.py (Wave 0 — proves StripeClient.construct_event works)
    - MSV /Users/fcavalcanti/dev/meusecretariovirtual/api/internal/service/payment.go (lines 576-725 — branch-on-event-type idiom)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_missing_signature_returns_400
    - test_bad_signature_returns_400_with_stripe_webhook_invalid_code
    - test_stale_timestamp_returns_400 (>= 5 min old)
    - test_duplicate_event_id_returns_200_no_double_side_effect
    - test_checkout_session_completed_inserts_topup_row_and_flips_tier_to_ultra
    - test_subscription_created_flips_tier_to_pro
    - test_subscription_updated_with_cancel_at_period_end_does_NOT_flip_tier
    - test_subscription_deleted_flips_tier_to_free_and_pauses_4_oldest_agents
    - test_subscription_deleted_with_3_agents_pauses_zero (since cap=1 and 3 agents stay alive on free? — verify per D-15 wording)
    - test_charge_refunded_inserts_negative_ledger_row
    - test_invoice_paid_is_ack_no_side_effect (no DB change beyond stripe_webhook_events insert)
    - test_invoice_payment_failed_is_ack_no_side_effect
    - test_payment_intent_succeeded_is_NOT_handled_returns_200_ack (AMD-05 — incoming event still acked but NO side-effect)
    - test_unknown_event_type_returns_200_ack
    - test_side_effect_failure_rolls_back_idempotency_row (force a synthetic exception in credit_user; assert no row in stripe_webhook_events)
  </behavior>
  <action>
**File 1 — `api_server/tests/_fixtures/sign_webhook.py`:** Copy `api_server/tests/_spikes/sign_webhook.py` from Wave 0 verbatim. (Or move the Wave 0 file here; the spike copy can be removed once Wave 0 evidence is committed to history.)

**File 2..8 — `api_server/tests/_fixtures/stripe_webhooks/*.json`:** 7 minimal payload fixtures. Each is a real Stripe-shape JSON envelope (`{"id": "evt_test_...", "object": "event", "type": "<event-type>", "data": {"object": {...}}, "created": <unix-ts>}`). Use a deterministic `evt_test_<eventtype>_001` style ID per fixture so tests can replay them. Key data fields per fixture:

- `checkout_session_completed.json`: data.object has `id="cs_test_001"`, `customer="cus_test_user_a"`, `amount_total=2500`, `metadata={"ap_user_id":"<UUID>","pack_id":"pack_25","credit_cents":"2500"}`, `mode="payment"`, `payment_status="paid"`.
- `customer_subscription_created.json`: data.object has `id="sub_test_001"`, `customer="cus_test_user_a"`, `status="active"`, `metadata={"ap_user_id":"<UUID>"}`, `cancel_at_period_end=false`, `current_period_end=<future-unix>`.
- `customer_subscription_updated.json`: same shape but `cancel_at_period_end=true`.
- `customer_subscription_deleted.json`: same shape but `status="canceled"`.
- `invoice_paid.json`: data.object has `id="in_test_001"`, `customer="cus_test_user_a"`, `status="paid"`.
- `invoice_payment_failed.json`: same but `status="open"` and `attempt_count=1`.
- `charge_refunded.json`: data.object has `id="ch_test_001"`, `customer="cus_test_user_a"`, `amount_refunded=2500`, `refunded=true`, plus a synthetic `metadata.ap_user_id` AND a `payment_intent` field tying back to the original Checkout (so the handler can find the related charge).

Where `<UUID>` appears in the JSON, leave it as a literal placeholder string `__AP_USER_ID__` and the test harness substitutes the seeded UUID at runtime.

**File 9 — `api_server/src/api_server/routes/billing_webhook.py`:** Full new file.

```python
from __future__ import annotations
import logging
from datetime import datetime
from uuid import UUID

import stripe
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from ..models.errors import ErrorCode, make_error_envelope
from ..services.ledger import credit_user, record_tier_change

_log = logging.getLogger("api_server.billing_webhook")
router = APIRouter()

def _err(status: int, code: ErrorCode, msg: str) -> JSONResponse:
    return JSONResponse(make_error_envelope(code, msg), status_code=status)


@router.post("/billing/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    """Public route. Auth via Stripe-Signature HMAC, NOT session cookie. Sole writer of users.tier (D-04)."""
    payload = await request.body()  # MUST be raw bytes — never await request.json() first (Pitfall 1).
    if not stripe_signature:
        return _err(400, ErrorCode.STRIPE_WEBHOOK_INVALID, "missing signature")

    settings = request.app.state.settings
    client: stripe.StripeClient = request.app.state.stripe_client

    try:
        event = client.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret,
        )
    except stripe.SignatureVerificationError:
        _log.warning("billing_webhook.signature_failed sig_prefix=%s", (stripe_signature or "")[:20])
        return _err(400, ErrorCode.STRIPE_WEBHOOK_INVALID, "bad signature")
    except Exception as e:
        _log.exception("billing_webhook.construct_event_unexpected_error")
        return _err(400, ErrorCode.STRIPE_WEBHOOK_INVALID, "could not parse event")

    pool = request.app.state.db
    async with pool.acquire() as conn:
        async with conn.transaction():
            inserted = await conn.fetchval(
                """
                INSERT INTO stripe_webhook_events (stripe_event_id, event_type, payload)
                VALUES ($1, $2, $3)
                ON CONFLICT (stripe_event_id) DO NOTHING
                RETURNING stripe_event_id
                """,
                event.id, event.type, payload.decode(),
            )
            if inserted is None:
                _log.info("billing_webhook.duplicate_event id=%s type=%s", event.id, event.type)
                return JSONResponse({"received": True}, status_code=200)

            # Branch on event type. Side-effect runs in SAME transaction (Pitfall 2).
            if event.type == "checkout.session.completed":
                await _handle_checkout_completed(conn, event)
            elif event.type == "customer.subscription.created":
                await _handle_subscription_created(conn, event)
            elif event.type == "customer.subscription.updated":
                await _handle_subscription_updated(conn, event)
            elif event.type == "customer.subscription.deleted":
                await _handle_subscription_deleted(conn, event)
            elif event.type == "charge.refunded":
                await _handle_charge_refunded(conn, event)
            elif event.type == "invoice.paid":
                _log.info("billing_webhook.invoice_paid_ack id=%s", event.id)  # ack-only
            elif event.type == "invoice.payment_failed":
                _log.info("billing_webhook.invoice_failed_ack id=%s", event.id)  # ack-only
            elif event.type == "payment_intent.succeeded":
                # AMD-05: redundant with checkout.session.completed; ack only.
                _log.info("billing_webhook.payment_intent_ack_no_side_effect id=%s", event.id)
            else:
                _log.info("billing_webhook.unknown_event_ack id=%s type=%s", event.id, event.type)

    return JSONResponse({"received": True}, status_code=200)


# ---------- handlers (each runs inside the caller's transaction) ----------

async def _user_id_for_customer(conn, customer_id: str) -> UUID | None:
    """Resolve users.id by stripe_customer_id; return None if not found."""
    return await conn.fetchval(
        "SELECT id FROM users WHERE stripe_customer_id = $1", customer_id,
    )


async def _handle_checkout_completed(conn, event) -> None:
    """checkout.session.completed → grant credits + (if first) flip tier to ultra."""
    obj = event.data.object
    metadata = obj.get("metadata") or {}
    ap_user_id = metadata.get("ap_user_id")
    pack_id = metadata.get("pack_id")
    credit_cents_str = metadata.get("credit_cents")
    if not (ap_user_id and pack_id and credit_cents_str):
        _log.warning("billing_webhook.checkout_missing_metadata event_id=%s", event.id)
        return
    user_id = UUID(ap_user_id)
    credit_cents = int(credit_cents_str)
    # 1. Credit the ledger (idempotent on UNIQUE(reference_id, reference_type) where reference_id=session.id).
    await credit_user(
        conn, user_id=user_id, kind="topup", amount_cents=credit_cents,
        reference_id=obj.get("id"), reference_type="stripe_checkout_session",
    )
    # 2. Tier flip free→ultra if applicable. Idempotent: re-runs hit the same row update.
    current_tier = await conn.fetchval("SELECT tier FROM users WHERE id = $1 FOR UPDATE", user_id)
    if current_tier in ("free",):
        await conn.execute("UPDATE users SET tier = 'ultra' WHERE id = $1", user_id)
        await record_tier_change(
            conn, user_id=user_id, from_tier=current_tier, to_tier="ultra",
            stripe_event_id=event.id,
        )


async def _handle_subscription_created(conn, event) -> None:
    """customer.subscription.created → tier='pro' for the user."""
    obj = event.data.object
    customer_id = obj.get("customer")
    user_id = await _user_id_for_customer(conn, customer_id)
    if user_id is None:
        _log.warning("billing_webhook.sub_created_user_not_found customer=%s", customer_id)
        return
    current_tier = await conn.fetchval("SELECT tier FROM users WHERE id = $1 FOR UPDATE", user_id)
    if current_tier != "pro":
        await conn.execute("UPDATE users SET tier = 'pro' WHERE id = $1", user_id)
        await record_tier_change(
            conn, user_id=user_id, from_tier=current_tier, to_tier="pro",
            stripe_event_id=event.id,
        )


async def _handle_subscription_updated(conn, event) -> None:
    """customer.subscription.updated → store cancel_at_period_end and period_end. Tier UNCHANGED here."""
    obj = event.data.object
    customer_id = obj.get("customer")
    user_id = await _user_id_for_customer(conn, customer_id)
    if user_id is None:
        return
    cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    period_end_unix = obj.get("current_period_end")
    period_end = datetime.fromtimestamp(period_end_unix) if period_end_unix else None
    # NOTE: Migration 014 does NOT have these subscription-state columns yet. Either:
    #   (a) extend migration 014 to include subscription_cancel_at_period_end + subscription_current_period_end on users
    #   (b) acknowledge with log only and defer to a B.1 patch
    # Decision (per CONTEXT canonical_refs): extend migration 014 in this plan. Add to users:
    #   - subscription_cancel_at_period_end BOOLEAN NOT NULL DEFAULT false
    #   - subscription_current_period_end TIMESTAMPTZ NULL
    # Update Wave 1 migration AND this handler:
    await conn.execute(
        "UPDATE users SET subscription_cancel_at_period_end = $1, subscription_current_period_end = $2 "
        "WHERE id = $3",
        cancel_at_period_end, period_end, user_id,
    )


async def _handle_subscription_deleted(conn, event) -> None:
    """customer.subscription.deleted → tier='free' + auto-pause 4 oldest active non-paused agents (D-15)."""
    obj = event.data.object
    customer_id = obj.get("customer")
    user_id = await _user_id_for_customer(conn, customer_id)
    if user_id is None:
        return
    current_tier = await conn.fetchval("SELECT tier FROM users WHERE id = $1 FOR UPDATE", user_id)
    if current_tier == "free":
        return  # already free
    await conn.execute("UPDATE users SET tier = 'free' WHERE id = $1", user_id)
    await record_tier_change(
        conn, user_id=user_id, from_tier=current_tier, to_tier="free",
        stripe_event_id=event.id,
    )
    # Auto-pause the 4 oldest non-paused, non-stopped agents per D-15.
    # Free tier cap is 1 agent; user keeps the OLDEST 1 active and we pause the next 4 oldest.
    # (If user had 5: keep oldest 1, pause next 4. If user had 3: keep oldest 1, pause 2.)
    await conn.execute(
        """
        UPDATE agent_containers
        SET status = 'auto_paused'
        WHERE id IN (
          SELECT id FROM agent_containers
          WHERE user_id = $1 AND status NOT IN ('stopped', 'failed', 'auto_paused')
          ORDER BY created_at ASC
          OFFSET 1 LIMIT 4
        )
        """,
        user_id,
    )


async def _handle_charge_refunded(conn, event) -> None:
    """charge.refunded → ledger row kind='refund', amount = -delta-since-last-refund (D-16)."""
    obj = event.data.object
    customer_id = obj.get("customer")
    user_id = await _user_id_for_customer(conn, customer_id)
    if user_id is None:
        return
    amount_refunded = int(obj.get("amount_refunded") or 0)
    if amount_refunded <= 0:
        return
    # Compute delta vs prior refund rows for this charge (handles partial refunds — RESEARCH Open Q #6).
    prior_refunded = await conn.fetchval(
        "SELECT COALESCE(SUM(-amount_cents), 0)::BIGINT FROM credit_transactions "
        "WHERE user_id = $1 AND kind = 'refund' AND reference_id = $2",
        user_id, obj.get("id"),
    )
    delta = amount_refunded - int(prior_refunded or 0)
    if delta <= 0:
        return
    await credit_user(
        conn, user_id=user_id, kind="refund", amount_cents=-delta,
        reference_id=f"{obj.get('id')}:{event.id}",  # cumulative-aware key for partial refunds
        reference_type="stripe_refund",
    )
```

**Migration extension (CRITICAL):** Plan 02 wrote migration 014. This plan EXTENDS it with two more columns on `users`:
- `subscription_cancel_at_period_end BOOLEAN NOT NULL DEFAULT false`
- `subscription_current_period_end TIMESTAMPTZ NULL`

**Action:** Re-open `api_server/alembic/versions/014_phase_b_credit_ledger.py` from Wave 1 and add these two columns to `upgrade()` (and their drop_column calls to `downgrade()`). Also extend `tests/test_migration_014_phase_b.py` with assertions for these two columns. (This is a Wave 3 task because the columns are only consumed by the webhook handler in this plan. Doing this here keeps Wave 1 minimally scoped and avoids re-touching migration 014 from a third plan later.)

**File 10 — `api_server/src/api_server/main.py`:** Register the webhook router. After `app.include_router(billing_route.router, ...)` from Plan 03:

```python
from .routes import billing_webhook as billing_webhook_route  # type: ignore[import-not-found]
app.include_router(billing_webhook_route.router, prefix="/v1", tags=["billing"])
```

**File 11 — `api_server/tests/routes/test_billing_webhook.py`:** Postgres testcontainer + async_client. Pattern:

```python
import json
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "_fixtures" / "stripe_webhooks"

def _load_fixture(name: str, ap_user_id: str) -> bytes:
    raw = (FIXTURES / f"{name}.json").read_text()
    raw = raw.replace("__AP_USER_ID__", ap_user_id)
    return raw.encode()

async def _post_signed(async_client, fixture_name, ap_user_id, secret="whsec_test"):
    payload = _load_fixture(fixture_name, ap_user_id)
    sig = sign_webhook_payload(payload, secret)
    return await async_client.post(
        "/v1/billing/webhook", content=payload,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
```

For each test from the `<behavior>` list, seed users + (where needed) stripe_customer_id + agent_containers rows, then POST the fixture, then assert the DB state.

**For the `test_subscription_deleted_flips_tier_to_free_and_pauses_4_oldest_agents` test:** seed 6 agent_containers rows with sequential created_at timestamps. Pre-state: user.tier='pro'. Post-state: user.tier='free' AND `SELECT COUNT(*) FROM agent_containers WHERE user_id = $1 AND status = 'auto_paused'` returns 4 (the agents at offset 1..4 by created_at ASC).

**For the `test_side_effect_failure_rolls_back_idempotency_row` test:** monkeypatch `services.ledger.credit_user` to raise a synthetic exception when called for `kind='topup'`. POST checkout.session.completed. Expect the response to be a 5xx (or actually we have no error handler around the side-effect block — let it propagate as a 500 via FastAPI's default). Then assert `SELECT COUNT(*) FROM stripe_webhook_events WHERE stripe_event_id = $1` returns 0 — because the transaction rolled back.

**For the `agent_containers.status = 'auto_paused'` value:** before this plan lands, confirm the column does NOT have a CHECK constraint that excludes `'auto_paused'`. Run `grep -r "ck_agent_containers_status\|agent_containers.*CHECK" api_server/alembic/`. If a CHECK constraint exists, extend migration 014 with a DROP+REBUILD or use `op.execute("ALTER TABLE agent_containers DROP CONSTRAINT ck_agent_containers_status")` followed by re-creating it with `'auto_paused'` included. If no CHECK constraint exists, no migration change needed.
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/routes/test_billing_webhook.py tests/test_migration_014_phase_b.py -x</automated>
  </verify>
  <done>
- All 15 webhook tests + the 7 migration 014 tests (now including 2 new subscription-state columns) pass.
- `grep -c 'event.type ==' api_server/src/api_server/routes/billing_webhook.py` = 8 branches (7 explicit + the explicit ack for payment_intent.succeeded).
- `grep -c 'payment_intent.succeeded' api_server/src/api_server/routes/billing_webhook.py` = 1 occurrence (the ack-only branch with comment "AMD-05: redundant").
- `ls api_server/tests/_fixtures/stripe_webhooks/*.json | wc -l` = 7.
- `grep -c 'subscription_cancel_at_period_end' api_server/alembic/versions/014_phase_b_credit_ledger.py` ≥ 2 (one in upgrade, one in downgrade).
- agent_containers.status='auto_paused' value either fits the existing CHECK or the CHECK has been extended.
- `cd api_server && curl -X POST -H "Stripe-Signature: garbage" --data '{}' http://localhost:8000/v1/billing/webhook` returns 400.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Stripe → /v1/billing/webhook | public-internet inbound; auth via Stripe-Signature HMAC; rate-limit middleware EXCLUDES this path so Stripe is never throttled |
| webhook → Postgres | all side-effects in one transaction; UNIQUE(stripe_event_id) prevents replay |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-W1 | Spoofing | billing_webhook.py | mitigate | StripeClient.construct_event verifies HMAC-SHA256 + 5-min timestamp tolerance; SignatureVerificationError → 400. Spike-a (Wave 0) proves the round-trip |
| T-B-RPL | Tampering (replay) | billing_webhook.py | mitigate | stripe_webhook_events.stripe_event_id UNIQUE; ON CONFLICT DO NOTHING returns 200 short-circuit. Same-tx with side-effect ensures idempotency |
| T-B-DBL | Tampering (double-credit) | billing_webhook.py | mitigate | AMD-05 — payment_intent.succeeded explicitly NOT branched (ack-only); credit_user uses UNIQUE(reference_id, reference_type) on the ledger row tied to the Stripe checkout session id |
| T-B-CRS | Tampering (rollback) | billing_webhook.py | mitigate | Pitfall 2 fix: INSERT into stripe_webhook_events + side-effect run in ONE async with conn.transaction(); side-effect failure rolls back the dedupe row, Stripe retries cleanly |
| T-B-NEG | Tampering | _handle_charge_refunded | mitigate | partial-refund delta math via cumulative reference_id (`<charge_id>:<event_id>`); UNIQUE prevents double-debit on retry; per-refund-event keys handle partial refunds (Open Q #6) |
| T-B-DEL | Tampering | _handle_subscription_deleted | mitigate | Sole writer of users.tier=free path; auto-pause is scoped via `user_id = $1` and OFFSET 1 LIMIT 4 ASC so we never pause more agents than the spec |
| T-B-LK | InfoDisclosure | billing_webhook.py logging | mitigate | only the signature prefix (first 20 chars) is logged on failure; payload body never logged |
| T-B-DOS | DoS | billing_webhook.py | accept | webhook rate-limit excluded — Stripe is the sole caller. Stripe's own infrastructure protects us; if Stripe goes rogue, we have bigger problems |
</threat_model>

<verification>
- All 15 webhook integration tests + extended migration 014 tests green.
- AMD-05 enforced: payment_intent.succeeded handler exists and is comment-documented as ack-only-no-side-effect.
- Side-effect-rollback test proves the same-tx invariant.
- Auto-pause test proves D-15 4-oldest semantics (with offset 1 to keep the absolute-oldest as the user's surviving free-tier agent).
</verification>

<success_criteria>
- `cd api_server && uv run pytest tests/routes/test_billing_webhook.py tests/test_migration_014_phase_b.py -x` green.
- Manual smoke (with Stripe CLI on host pointed at deploy stack — per CLAUDE.md macOS rule):
  - `stripe trigger checkout.session.completed --override 'checkout_session:metadata.ap_user_id=<your-user-uuid>' --override 'checkout_session:metadata.pack_id=pack_5' --override 'checkout_session:metadata.credit_cents=500'`
  - Confirm `docker compose -f deploy/docker-compose.prod.yml logs api_server | grep billing_webhook` shows the event acked.
  - Confirm balance and tier in DB: `psql -c "SELECT tier, balance_cents FROM users u LEFT JOIN credit_balances b ON b.user_id=u.id WHERE u.id=...;"` shows tier=ultra and balance=500.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-06-SUMMARY.md` documenting the 7-event matrix, the migration extension, and the side-effect-rollback test result.
</output>
