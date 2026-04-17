"""Rate-limit middleware — STUB.

Plan 19-05 implements the advisory-lock + Postgres sliding-window counter
logic per CONTEXT.md D-05. This file exists ONLY so Plan 19-02 can wire the
middleware into ``main.create_app`` now — Plan 05 then fills the
``__call__`` body without touching ``main.py`` (file-ownership contract for
Wave 3 parallel execution).

Pass-through behavior until Plan 05 lands: every request goes straight to
the inner app with no inspection.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send


class RateLimitMiddleware:
    """ASGI middleware stub — no-op pass-through until Plan 19-05 fills it in."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # TODO(plan 19-05): look up bucket via endpoint path, acquire the
        # per-subject advisory lock, increment the Postgres counter, emit
        # Retry-After + HTTP 429 when the window limit is exceeded.
        await self.app(scope, receive, send)
