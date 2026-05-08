"""Rate-limit middleware (Plan 19-05; extended Plan 22c.3-08 for chat).

Replaces the Plan 19-02 pass-through stub with a real ASGI body that:

- Maps (method, path) → bucket per CONTEXT.md §D-05 + §D-42:
  ``POST /v1/runs`` → 10/min, ``POST /v1/lint`` → 120/min,
  ``POST /v1/agents/:id/messages`` → 4/min (D-42, chat),
  ``GET /v1/*`` → 300/min. All other paths pass through
  unconditionally (health probes, docs, OpenAPI, root).
- Derives the subject (IP or user) per the XFF-trust policy —
  ``AP_TRUSTED_PROXY=true`` is required before we trust
  ``X-Forwarded-For``; otherwise we use ``scope["client"]``'s peer
  IP (T-19-05-01: the threat is an attacker spoofing XFF to bypass
  the per-IP limit).
- Calls :func:`services.rate_limit.check_and_increment` on the app's
  asyncpg pool. On cap exceeded, emits a Stripe-shape error envelope
  with status 429 + ``Retry-After`` header (SC-09).

**Fail-open on backend error:** a Postgres outage causes the middleware
to log and fall through to the handler rather than lock everyone out.
The alternative (fail-closed) would turn a transient infra hiccup into
a user-visible outage — deliberate tradeoff documented in the plan's
threat register (T-19-05-06).

Class name + ``__init__`` signature unchanged from Plan 19-02 so
``main.py`` stays wired (Wave 3 file-ownership contract).
"""
from __future__ import annotations

import json
import logging
import re

from starlette.types import ASGIApp, Receive, Scope, Send

from ..models.errors import ErrorCode, make_error_envelope
from ..services.rate_limit import check_and_increment

_log = logging.getLogger("api_server.rate_limit")

# Phase 22c.3-08: chat path predicate. Capture group 1 is the agent UUID
# (a string here — we don't validate UUID-ness; the rate-limit subject
# composition treats it as opaque). The path-shape gate AND the
# composite-subject derivation share this regex.
_AGENT_MESSAGES_PATTERN = re.compile(r"^/v1/agents/([^/]+)/messages$")

# Phase 31 H3 (D-01, D-02): the seven auth route entry points covered by
# the new `auth` rate-limit bucket. The dict maps (method, path) → stable
# short alias used in composite-subject derivation; a path rename
# (e.g. /v1/auth → /api/v2/auth) shouldn't invalidate counter rows.
# `_AUTH_ROUTES` is the membership frozenset derived from the dict's keys
# so a route added to one structure cannot drift from the other (WR-05).
# Source-of-truth lines in routes/auth.py: 138, 157, 222, 237, 378, 449, 542.
_AUTH_ROUTE_KEYS: dict[tuple[str, str], str] = {
    ("POST", "/v1/auth/google/mobile"):   "google_mobile",
    ("POST", "/v1/auth/github/mobile"):   "github_mobile",
    ("POST", "/v1/auth/logout"):          "logout",
    ("GET",  "/v1/auth/google"):          "google_redirect",
    ("GET",  "/v1/auth/google/callback"): "google_callback",
    ("GET",  "/v1/auth/github"):          "github_redirect",
    ("GET",  "/v1/auth/github/callback"): "github_callback",
}
_AUTH_ROUTES: frozenset[tuple[str, str]] = frozenset(_AUTH_ROUTE_KEYS.keys())

# (limit, window_seconds) per bucket — locked in CONTEXT.md §D-05 + §D-42.
_LIMITS: dict[str, tuple[int, int]] = {
    "runs": (10, 60),    # POST /v1/runs
    "lint": (120, 60),   # POST /v1/lint
    "get":  (300, 60),   # GET /v1/*
    "chat": (4, 60),     # POST /v1/agents/:id/messages — D-42
    "auth": (5, 60),     # Phase 31 D-04 — auth POSTs + OAuth GET callbacks; per-route via _AUTH_ROUTES
}


def _bucket_for(scope: Scope) -> str | None:
    """Return the bucket name for a request, or ``None`` to pass through.

    Health probes, docs, OpenAPI, and the root path are NOT rate-limited
    — LB probes must always succeed and docs are read-mostly. Anything
    under ``/v1/`` that is NOT one of the POST endpoints falls into the
    ``get`` bucket regardless of HTTP verb, so a future HEAD/OPTIONS
    request to a GET endpoint is still bounded.
    """
    method = scope.get("method", "")
    path = scope.get("path", "")
    if method == "POST" and path == "/v1/runs":
        return "runs"
    if method == "POST" and path == "/v1/lint":
        return "lint"
    # Phase 22c.3-08 (D-42): POST /v1/agents/<uuid>/messages → chat bucket.
    # The composite-subject derivation in __call__ ensures per-agent
    # quotas don't share a bucket (Pitfall 7).
    if method == "POST" and _AGENT_MESSAGES_PATTERN.match(path):
        return "chat"
    # Phase 31 H3 (D-01): auth route → auth bucket. Tuple-membership
    # check; precedence is BEFORE the generic GET branch so the OAuth
    # callbacks (/v1/auth/google/callback, /v1/auth/github/callback) get
    # the auth bucket's tighter ceiling (5/min) instead of the get
    # bucket's 300/min.
    if (method, path) in _AUTH_ROUTES:
        return "auth"
    # Any GET under /v1 is the "get" bucket. POSTs we didn't map above
    # are NOT rate-limited (there aren't any in Phase 19 — all v1 POSTs
    # are explicitly mapped above).
    if method == "GET" and path.startswith("/v1/"):
        return "get"
    return None


def _subject_from_scope(scope: Scope, trusted_proxy: bool) -> str:
    """Return the rate-limit subject (user or IP) for the request.

    Phase 22c-06: the user-scoped subject takes precedence when
    ``SessionMiddleware`` (plan 22c-04) has resolved a UUID into
    ``scope['state']['user_id']``. Format is ``user:<uuid>`` so the
    rate-limit counter row is distinct from any IP-scoped row for the
    same peer. The UUID itself is never returned to the caller and
    never logged — it only lives inside the counter key.

    Falls back to the pre-22c IP-based resolution for anonymous
    requests. When ``trusted_proxy=True`` (Caddy in front in prod), the
    first IP in ``X-Forwarded-For`` is used — Caddy appends the real
    client IP to the head of the list. When ``trusted_proxy=False``
    (default), XFF is IGNORED entirely: an attacker can send any value
    they want in that header and the server must not trust it
    (T-19-05-01).

    When no peer IP is available (e.g. unix-socket client), returns
    ``"unknown"`` so all such requests share a single bucket —
    preferable to letting the rate limiter silently skip the check.
    """
    # Phase 22c-06: user-scoped rate limit takes precedence when
    # SessionMiddleware has resolved a UUID. Clean two-line extraction
    # mirrors the form used in middleware/idempotency.py — no opaque
    # getattr+lambda chains.
    state = scope.get("state") or {}
    user_id = state.get("user_id")
    if user_id is not None:
        return f"user:{user_id}"

    if trusted_proxy:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                first = value.decode(errors="ignore").split(",")[0].strip()
                if first:
                    return first
                break
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    """ASGI middleware enforcing per-(subject, bucket) fixed-window limits.

    Class name + signature match the Plan 19-02 stub exactly so the
    existing ``app.add_middleware(RateLimitMiddleware)`` wiring in
    ``main.create_app()`` works unchanged.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        # Lifespan / websocket / other non-HTTP messages pass through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        bucket = _bucket_for(scope)
        if bucket is None:
            await self.app(scope, receive, send)
            return
        limit, window_s = _LIMITS[bucket]

        # Settings + DB pool live on app.state — populated by the lifespan
        # in main.create_app(). The cast is safe: this middleware is never
        # exercised outside a fully-constructed FastAPI app.
        app = scope["app"]
        trusted = bool(getattr(app.state.settings, "trusted_proxy", False))
        subject = _subject_from_scope(scope, trusted)

        # Phase 22c.3-08 (D-42; Pitfall 7 mitigation): for the chat bucket,
        # mix the agent_id from the URL into the subject so each (user,
        # agent) pair gets its own counter row. Without this, a user
        # posting to agent A would exhaust the same bucket they would
        # use for agent B — empirically rejected by
        # ``test_chat_rate_limit_per_agent``.
        if bucket == "chat":
            match = _AGENT_MESSAGES_PATTERN.match(scope.get("path", ""))
            agent_id_str = match.group(1) if match else ""
            if agent_id_str:
                subject = f"chat:{subject}:{agent_id_str}"

        # Phase 31 H3 (D-02): auth bucket gets per-route counters via
        # composite subject `auth:<ip>:<route_key>`. Stable aliases
        # decouple the counter row from path strings — a future rename
        # of /v1/auth/google/mobile to /api/auth/google/mobile would NOT
        # invalidate the existing counter rows.
        if bucket == "auth":
            route_key = _AUTH_ROUTE_KEYS.get(
                (scope.get("method", ""), scope.get("path", "")),
                "unknown",
            )
            subject = f"auth:{subject}:{route_key}"

        try:
            async with app.state.db.acquire() as conn:
                allowed, retry_after = await check_and_increment(
                    conn, subject, bucket, limit, window_s,
                )
        except Exception:
            # Fail-open: a rate-limit backend failure shouldn't cascade
            # into a site-wide outage. Log and pass through.
            _log.exception("rate_limit backend error; failing open")
            await self.app(scope, receive, send)
            return

        if allowed:
            await self.app(scope, receive, send)
            return

        # Over limit — emit a Stripe-shape 429 envelope with Retry-After.
        body = json.dumps(
            make_error_envelope(
                ErrorCode.RATE_LIMITED,
                f"rate limit exceeded for bucket {bucket!r}",
                param=bucket,
            )
        ).encode()
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"retry-after", str(retry_after).encode()),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
