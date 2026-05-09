"""Phase B Wave 0 spike A — Stripe webhook signature round-trip.

Proves three load-bearing claims for Wave 1 webhook implementation:

1. ``stripe.StripeClient(api_key).construct_event(payload, signature, secret)``
   accepts a hand-rolled fixture signed via ``sign_webhook_payload`` (AMD-02 +
   AMD-04). Returns a parsed ``Event`` with ``event.id`` + ``event.type``.

2. A tampered payload (one byte mutated after signing) raises
   ``stripe.SignatureVerificationError``. Constant-time HMAC comparison.

3. A stale timestamp (``ts = now - 600s``) raises
   ``stripe.SignatureVerificationError``. Stripe SDK enforces a 5-minute
   tolerance window by default.

Run via::

    cd api_server && uv run python tests/_spikes/spike_a_webhook_signature.py

Exit code 0 + ``PASS spike-a`` on stdout signals success.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Make the sign_webhook helper importable when running as a script (not pytest).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import stripe  # noqa: E402

from sign_webhook import sign_webhook_payload  # noqa: E402


SECRET = "whsec_spike_secret"


def _build_payload() -> bytes:
    """A minimal but Stripe-shaped checkout.session.completed event."""
    event = {
        "id": "evt_spike_a_test_001",
        "object": "event",
        "type": "checkout.session.completed",
        "api_version": "2025-03-31.basil",
        "created": int(time.time()),
        "data": {
            "object": {
                "id": "cs_test_spike_a_001",
                "object": "checkout.session",
                "amount_total": 500,
                "currency": "usd",
                "customer": "cus_test_spike_a_001",
                "metadata": {
                    "ap_user_id": "00000000-0000-0000-0000-000000000001",
                    "pack_id": "pack_5usd",
                    "credit_cents": "500",
                },
                "mode": "payment",
                "payment_status": "paid",
                "status": "complete",
            },
        },
        "livemode": False,
    }
    return json.dumps(event, separators=(",", ":")).encode()


def main() -> int:
    print(f"stripe SDK version: {stripe.VERSION}")
    if not stripe.VERSION.startswith("15."):
        print(f"FAIL spike-a: expected stripe SDK v15.x, got {stripe.VERSION}")
        return 1

    payload = _build_payload()
    sig = sign_webhook_payload(payload, SECRET)

    # AMD-04: use the StripeClient service pattern (NOT module-level
    # stripe.Webhook.construct_event). Construct with a dummy api_key — the
    # construct_event path doesn't make outbound calls.
    client = stripe.StripeClient("sk_test_dummy_for_spike_a")

    # ---- (a) happy path -------------------------------------------------
    event = client.construct_event(payload, sig, SECRET)
    assert event.id == "evt_spike_a_test_001", f"unexpected event.id={event.id!r}"
    assert event.type == "checkout.session.completed", (
        f"unexpected event.type={event.type!r}"
    )
    # The session-level metadata carries pack_id (AMD-05 — this is why we
    # listen to checkout.session.completed and NOT payment_intent.succeeded).
    # StripeObject in v15 SDK uses attribute access; nested StripeObjects
    # like `metadata` propagate the same pattern (`obj.metadata.pack_id`).
    session_obj = event.data.object
    pack_id = session_obj.metadata.pack_id
    assert pack_id == "pack_5usd", (
        f"expected pack_id='pack_5usd', got {pack_id!r}"
    )
    print(f"  (a) happy path:  event parsed; metadata.pack_id={pack_id!r}")

    # ---- (b) tampered payload -------------------------------------------
    tampered = payload.replace(b'"amount_total":500', b'"amount_total":999')
    try:
        client.construct_event(tampered, sig, SECRET)
    except stripe.SignatureVerificationError as e:
        print(f"  (b) tampered:    SignatureVerificationError raised ({e!s:.80s})")
    else:
        print("FAIL spike-a (b): tampered payload did NOT raise")
        return 1

    # ---- (c) stale timestamp --------------------------------------------
    stale_ts = int(time.time()) - 600  # 10 minutes ago, well outside 5-min tol.
    stale_sig = sign_webhook_payload(payload, SECRET, ts=stale_ts)
    try:
        client.construct_event(payload, stale_sig, SECRET)
    except stripe.SignatureVerificationError as e:
        print(f"  (c) stale ts:    SignatureVerificationError raised ({e!s:.80s})")
    else:
        print("FAIL spike-a (c): stale timestamp did NOT raise")
        return 1

    print("PASS spike-a")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
