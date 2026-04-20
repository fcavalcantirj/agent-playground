"""AccessLogMiddleware — allowlist-based structured access log.

RESEARCH.md Pattern 5. Emits one structlog record per request carrying ONLY:
``method``, ``path``, ``status``, ``duration_ms``, and an allowlisted subset
of headers.

Sensitive headers (Authz, Cookie, X-Api-Key, X-Forwarded-For, Proxy-Authz),
along with the request body and response body, are ABSENT from the record
by construction. They are not members of ``_LOG_HEADERS`` and the middleware
never reads the body streams.

Plan 19-06 artifact (BYOK-leak defense). Phase 19 CONTEXT.md D-02 mandates
that the header carrying the BYOK provider key is NEVER logged — the
allowlist below achieves that by construction (the header name is simply
not in the set, so it is never read or emitted).

Cookie redaction (Phase 22c):
    The allowlist pattern already blocks raw Cookie / Set-Cookie headers
    because they are not in ``_LOG_HEADERS``. This prevents the following
    Phase 22c cookies from ever being logged:
    * ``ap_session`` — server-side session id (22c SessionMiddleware)
    * ``ap_oauth_state`` — authlib CSRF state cookie (Starlette SessionMiddleware)
    No positive change required for 22c; this note exists so future grep-auditors
    can verify the path without re-deriving the allowlist semantics.
"""
from __future__ import annotations

import time

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Headers the access log IS allowed to emit. Anything else is dropped.
# The five names below are the ONLY lowercased header keys ever read; every
# other header is ignored entirely.
_LOG_HEADERS = {
    "user-agent",
    "content-length",
    "content-type",
    "accept",
    "x-request-id",
}


class AccessLogMiddleware:
    """ASGI middleware that logs one record per HTTP request.

    The record is built from ``scope`` only — the request body is never read,
    and the response body is never captured. Only the response status code is
    intercepted via a ``send`` wrapper.
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        self.log = structlog.get_logger("access")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        t0 = time.monotonic()
        status_holder = {"status": 0}

        async def send_wrapper(msg: Message) -> None:
            if msg["type"] == "http.response.start":
                status_holder["status"] = msg["status"]
            await send(msg)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            headers: dict[str, str] = {}
            for name, value in scope.get("headers", []):
                k = name.decode("latin-1").lower()
                if k in _LOG_HEADERS:
                    headers[k] = value.decode("latin-1", errors="replace")
            self.log.info(
                "access",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_holder["status"],
                duration_ms=int((time.monotonic() - t0) * 1000),
                headers=headers,
                # Only allowlisted header keys are included in `headers`.
                # Request body and response body are not captured anywhere.
            )
