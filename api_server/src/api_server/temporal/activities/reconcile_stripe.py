"""Phase B Plan B-stripe-09 — reconcile_stripe activity body (D-Discretion poller).

Backstop for missed Stripe webhooks. Every 5 minutes the
``ReconcileStripeWorkflow`` invokes this activity, which polls
``stripe.events.list`` for ``checkout.session.completed`` events created
in the last 15 minutes (3× the cron period for redundancy), checks each
against ``stripe_webhook_events`` for prior delivery, and applies the
side-effect for any genuinely-missed events via the same handler used
by the live webhook route (``billing_webhook._handle_checkout_completed``).

Idempotency is layered:

  1. ``stripe_webhook_events.stripe_event_id`` UNIQUE — the dedupe-row
     INSERT inside the same transaction as the side-effect. If the
     webhook arrives after the reconcile has already applied (or vice
     versa), the second insert raises ``UniqueViolationError`` and the
     transaction is rolled back; no double-credit.
  2. The reconcile pre-flight ``SELECT 1 FROM stripe_webhook_events
     WHERE stripe_event_id = $1`` skips events already on file BEFORE
     even attempting the side-effect — saves a Postgres tx setup cost
     on the common case (most events do arrive via webhook).

Mirrors the class-bound shape of ``record_usage.RecordUsageActivities``
so the worker injects the process-wide asyncpg pool + the
process-wide ``stripe.StripeClient`` already constructed by the
api_server lifespan (Plan B-stripe-02 ``services/stripe_client.py``).

Per CONTEXT D-Discretion: this is the canonical "missed-webhook
backstop" — Stripe nominally retries failed deliveries on its own
exponential schedule, but a HTTPS-misconfig blip during the retry
window OR a temporary api_server outage past Stripe's retry budget
can drop events permanently. The 5-min reconcile cron makes that
recovery automatic.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import stripe
from temporalio import activity


_log = logging.getLogger("api_server.temporal.reconcile_stripe")


class ReconcileStripeActivities:
    """Class-bound holder for the reconcile-stripe activity."""

    def __init__(
        self,
        *,
        db_pool: Any,
        stripe_client: stripe.StripeClient,
    ) -> None:
        self.db_pool = db_pool
        self.stripe_client = stripe_client

    @activity.defn(name="reconcile_stripe")
    async def reconcile(self) -> int:
        """Apply any missed ``checkout.session.completed`` events.

        Returns the count of events newly applied this run. Zero on the
        common path where every event already arrived via webhook.

        Failure modes:

          * Stripe API error → log + raise; the workflow's retry policy
            (3 attempts) handles transient blips.
          * Per-event side-effect failure → log + skip THIS event;
            continue iterating the rest of the page so one poison row
            doesn't block reconcile of every other event.
          * UniqueViolationError on the dedupe INSERT → expected race
            (webhook landed between our SELECT and our INSERT); skip.
        """
        # Late import to keep the activity module's import surface narrow
        # at worker boot (mirrors record_usage.py's rationale).
        from ...routes.billing_webhook import _handle_checkout_completed

        cutoff = int(
            (datetime.now(timezone.utc) - timedelta(minutes=15)).timestamp()
        )
        try:
            events = self.stripe_client.events.list(
                params={
                    "type": "checkout.session.completed",
                    "created": {"gte": cutoff},
                    "limit": 100,
                },
            )
        except stripe.StripeError:
            _log.exception("reconcile_stripe.list_failed cutoff=%s", cutoff)
            raise

        applied = 0
        for event in events.data:
            event_id = getattr(event, "id", None)
            event_type = getattr(event, "type", None)
            if event_id is None:
                continue
            try:
                async with self.db_pool.acquire() as conn:
                    # Pre-flight: skip events already on file.
                    already = await conn.fetchval(
                        "SELECT 1 FROM stripe_webhook_events "
                        "WHERE stripe_event_id = $1",
                        event_id,
                    )
                    if already is not None:
                        continue
                    # Apply the side-effect inside a transaction shared
                    # with the dedupe-row INSERT. Mirrors the live
                    # webhook handler discipline (Pitfall 2).
                    async with conn.transaction():
                        inserted = await conn.fetchval(
                            """
                            INSERT INTO stripe_webhook_events
                              (stripe_event_id, event_type, payload)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (stripe_event_id) DO NOTHING
                            RETURNING stripe_event_id
                            """,
                            event_id, event_type, str(event),
                        )
                        if inserted is None:
                            # Race: webhook applied this event between
                            # our SELECT and our INSERT. Skip cleanly.
                            continue
                        await _handle_checkout_completed(conn, event)
                        applied += 1
                        _log.info(
                            "reconcile_stripe.applied_missed_event "
                            "id=%s type=%s", event_id, event_type,
                        )
            except Exception:
                # Continue iterating — a poison event must not block the
                # reconcile of every other event in the page.
                _log.exception(
                    "reconcile_stripe.event_apply_failed id=%s", event_id,
                )
        _log.info("reconcile_stripe.run_done applied=%s", applied)
        return applied


@activity.defn(name="reconcile_stripe")
async def reconcile_stripe() -> int:
    """Module-level placeholder — fail-loud import path.

    Workers register :meth:`ReconcileStripeActivities.reconcile` (the
    bound method); this top-level function fails loudly so a
    misconfigured worker is detected immediately rather than silently
    passing.
    """
    raise NotImplementedError(
        "Workers register ReconcileStripeActivities.reconcile "
        "(bound method); the module-level function is an import-path "
        "placeholder only."
    )


__all__ = ["ReconcileStripeActivities", "reconcile_stripe"]
