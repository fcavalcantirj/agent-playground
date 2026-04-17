"""Idempotency middleware — STUB.

Plan 19-05 implements the Postgres-backed ``check-or-reserve`` flow per
CONTEXT.md D-01. This file exists ONLY so Plan 19-02 can wire the middleware
into ``main.create_app`` now — Plan 05 then fills the ``__call__`` body
without touching ``main.py`` (file-ownership contract for Wave 3 parallel
execution).

Pass-through behavior until Plan 05 lands: every request goes straight to
the inner app with no Idempotency-Key inspection.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send


class IdempotencyMiddleware:
    """ASGI middleware stub — no-op pass-through until Plan 19-05 fills it in."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # TODO(plan 19-05): parse the Idempotency-Key header, hash the body,
        # look up `idempotency_keys (user_id, key)`, short-circuit on cache
        # hit, return 422 on body-hash mismatch (Pitfall 6), otherwise
        # insert + pass through + cache the response on success.
        await self.app(scope, receive, send)
