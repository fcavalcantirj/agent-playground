"""Phase B Plan B-stripe-06 — hand-rolled Stripe webhook signature helper (AMD-02).

Promoted verbatim from ``tests/_spikes/sign_webhook.py`` (Wave 0 spike A).
The spike copy stays in place as committed evidence; this file is the
canonical helper that route tests import.

stripe-mock validates outbound request shapes only — it does NOT emit
webhook events (verified via stripe-mock README + Issue #16, open since
2017). Webhook handler signature-verify + idempotency tests use
**hand-rolled signed fixtures**: build a raw JSON payload, compute
``Stripe-Signature`` header as
``t=<unix>,v1=<hmac_sha256(secret, f'{t}.{payload}')>``, POST to the
route.

Stripe's webhook signature scheme (https://docs.stripe.com/webhooks#signatures):

    Stripe-Signature: t=<unix>,v1=<hmac_sha256_hex(secret, f"{t}.{payload}")>

The SDK's ``construct_event`` (AMD-04) parses this header, recomputes
HMAC over ``f"{t}.{raw_payload_bytes.decode()}"`` using the endpoint
secret, compares in constant time, and enforces a 5-minute timestamp
tolerance by default.
"""
from __future__ import annotations

import hashlib
import hmac
import time


def sign_webhook_payload(
    payload_bytes: bytes,
    secret: str,
    ts: int | None = None,
) -> str:
    """Return a Stripe-Signature header value for the given raw payload.

    :param payload_bytes: the raw JSON bytes that will be POSTed verbatim.
        Stripe signs raw bytes; re-serializing JSON before signing or
        before verifying breaks the signature.
    :param secret: the endpoint signing secret (``whsec_...``).
    :param ts: override the timestamp; defaults to ``int(time.time())``.
        Use a stale ``ts`` (e.g. ``int(time.time()) - 600``) to drive the
        SDK's 5-min tolerance branch.
    :returns: a header string of the form ``"t=<unix>,v1=<hexdigest>"``.
    """
    t = ts if ts is not None else int(time.time())
    sig = hmac.new(
        secret.encode(),
        f"{t}.{payload_bytes.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"t={t},v1={sig}"
