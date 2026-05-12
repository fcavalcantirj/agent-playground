"""Magic-link OTP helpers (2026-05-12).

Surface:

* ``generate_otp_code()`` — 6-digit numeric code (`secrets`-backed RNG).
* ``hash_otp_code(code)`` — sha256 hex of the raw code; stored in DB.
* ``send_otp_via_resend(settings, email, code)`` — outbound delivery via
  the Resend HTTP API. In dev (no ``AP_RESEND_API_KEY``) it logs the
  code at WARNING level so local end-to-end tests can read it without
  hitting Resend.
* ``OTP_TTL`` — 10 minutes (D-magic-link). Caller sets ``expires_at =
  now() + OTP_TTL``.
* ``MAX_VERIFY_ATTEMPTS`` — 5 attempts per code before the row is
  considered burned.
* ``REQUEST_COOLDOWN`` — 60 seconds between ``POST /v1/auth/email/request``
  calls for the same email (rate-limit; enforced by the route).

Never store the raw code. Only the sha256 hash. The user receives the
raw code in their inbox; the verify endpoint hashes the submitted code
and looks it up by ``(email, code_hash)``.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings

_log = logging.getLogger("api_server.auth.email_otp")

OTP_TTL = timedelta(minutes=10)
MAX_VERIFY_ATTEMPTS = 5
REQUEST_COOLDOWN = timedelta(seconds=60)


def generate_otp_code() -> str:
    """Return a 6-digit numeric code, zero-padded. Cryptographically random."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    """Return the sha256 hex digest of ``code``. Stable across processes."""
    return hashlib.sha256(code.encode("ascii")).hexdigest()


# Resend HTTP API contract — POST https://api.resend.com/emails
# Body shape: {from, to, subject, html, reply_to?}
# Auth: Authorization: Bearer <api_key>
# We keep the SDK off the dependency graph and call the HTTPS endpoint
# directly via httpx — fewer surface decisions, identical contract.

_RESEND_ENDPOINT = "https://api.resend.com/emails"


def _otp_email_html(code: str) -> str:
    """Return the HTML body for the OTP email.

    Solvr-branded, mobile-friendly, the code is rendered large + monospace.
    Mentions the 10-minute expiry and the "ignore if you didn't request"
    boilerplate that's table-stakes for transactional OTP emails.
    """
    # Inline styles only — every email client reflows; <style> blocks are
    # silently stripped by Gmail / Outlook web. Tabular monospaced numerals
    # for the code so the digit shapes don't shift width.
    return f"""
<!doctype html>
<html>
  <body style="background:#0a0a0a;margin:0;padding:32px;font-family:-apple-system,Helvetica,Arial,sans-serif;color:#eaeaea;">
    <div style="max-width:480px;margin:0 auto;background:#111;border:1px solid #222;border-radius:12px;padding:32px;">
      <div style="font-family:'JetBrains Mono',Menlo,Consolas,monospace;font-weight:600;font-size:18px;color:#9ae6b4;margin-bottom:24px;">
        &gt;_ SOLVR_LABS
      </div>
      <p style="font-size:15px;line-height:1.5;margin:0 0 24px 0;">
        Your sign-in code:
      </p>
      <div style="font-family:'JetBrains Mono',Menlo,Consolas,monospace;font-size:36px;font-weight:700;letter-spacing:8px;color:#fff;background:#000;border:1px solid #333;padding:20px 24px;border-radius:8px;text-align:center;">
        {code}
      </div>
      <p style="font-size:13px;line-height:1.5;margin:24px 0 0 0;color:#a0a0a0;">
        This code expires in 10 minutes. If you didn't request it, you can
        safely ignore this email.
      </p>
    </div>
  </body>
</html>
""".strip()


async def send_otp_via_resend(
    settings: "Settings",
    *,
    email: str,
    code: str,
) -> None:
    """Send the OTP code to ``email`` via Resend.

    In dev (``AP_RESEND_API_KEY`` unset), logs the code at WARNING level
    and returns without making an HTTP call — mirrors the ``OAuth config
    X missing in dev; using placeholder`` discipline so a fresh local
    checkout can exercise the verify flow without Resend credentials.

    In prod (key set), raises ``RuntimeError`` if Resend returns non-2xx.
    The route handler maps that to a 502 envelope so the mobile UI can
    surface "couldn't send code; try again" without leaking provider
    details.
    """
    if not settings.resend_api_key:
        _log.warning(
            "resend.dev_mode email=%s code=%s (no AP_RESEND_API_KEY)",
            email, code,
        )
        return

    # Lazy import — httpx is already in deps, but importing inside the
    # helper keeps unit tests that exercise hash/format paths free of
    # network-stack imports.
    import httpx

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": settings.email_from,
        "to": [email],
        "subject": f"Your Solvr Labs sign-in code: {code}",
        "html": _otp_email_html(code),
        "reply_to": settings.email_reply_to,
    }

    def _post_sync() -> None:
        # httpx.AsyncClient would be cleaner, but we're already inside an
        # async function and the per-call overhead of constructing a fresh
        # AsyncClient is negligible at OTP cadence (≤ 1/email/60s).
        with httpx.Client(timeout=10.0) as client:
            r = client.post(_RESEND_ENDPOINT, headers=headers, json=payload)
            if r.status_code >= 400:
                # Surface a short, non-credential message. Resend's body
                # may include {message, name}; we cap the preview.
                body_preview = (r.text or "")[:200]
                raise RuntimeError(
                    f"resend returned {r.status_code}: {body_preview}",
                )

    await asyncio.to_thread(_post_sync)


__all__ = [
    "OTP_TTL",
    "MAX_VERIFY_ATTEMPTS",
    "REQUEST_COOLDOWN",
    "generate_otp_code",
    "hash_otp_code",
    "send_otp_via_resend",
]
