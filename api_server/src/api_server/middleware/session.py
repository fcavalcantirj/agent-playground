"""Session resolution middleware — Phase 22c.

Converts the opaque ``ap_session`` HTTP cookie into
``request.state.user_id : UUID | None`` for every request. Route handlers
downstream either call ``auth/deps.py::require_user`` (protected paths)
or read ``request.state.user_id`` directly.

Behavior matrix:
  * No ``ap_session`` cookie: request.state.user_id = None
  * Cookie present, session valid (not revoked, not expired): UUID
  * Cookie present, session invalid: None
  * Cookie present, PG outage: None + log.exception (fail-closed)

Additionally performs a throttled ``sessions.last_seen_at`` update per
D-22c-MIG-05. Throttle cache is a per-worker in-memory dict on
``app.state.session_last_seen: dict[UUID, datetime]``. Redis was
considered and deferred — see CONTEXT.md §D-22c-MIG-05 + RESEARCH §Pitfall 7.

Placement (per D-22c-AUTH-01):
    CorrelationId -> AccessLog -> StarletteSession -> OurSession -> RateLimit -> Idempotency
The actual ``app.add_middleware()`` wiring lives in plan 22c-05's main.py patch.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    import asyncpg

_log = logging.getLogger("api_server.session")

SESSION_COOKIE_NAME = "ap_session"
LAST_SEEN_THROTTLE = timedelta(seconds=60)
_LAST_SEEN_CACHE_SOFT_CAP = 10_000  # LRU eviction threshold per D-22c-MIG-05


class SessionMiddleware:
    """Resolves ``request.state.user_id`` from the ``ap_session`` cookie."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_cookie = _extract_cookie(scope, SESSION_COOKIE_NAME)
        session_uuid = _coerce_uuid(raw_cookie) if raw_cookie else None
        user_id: UUID | None = None

        if session_uuid is not None:
            asgi_app = scope["app"]
            try:
                async with asgi_app.state.db.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT user_id, last_seen_at "
                        "FROM sessions "
                        "WHERE id = $1 "
                        "  AND revoked_at IS NULL "
                        "  AND expires_at > NOW()",
                        session_uuid,
                    )
                    if row is not None:
                        user_id = row["user_id"]
                        await _maybe_touch_last_seen(
                            asgi_app, conn,
                            session_id=session_uuid,
                            current_last_seen=row["last_seen_at"],
                        )
            except Exception:
                _log.exception(
                    "session resolution failed; treating as anonymous"
                )
                user_id = None

        scope.setdefault("state", {})["user_id"] = user_id
        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_cookie(scope: Scope, name: str) -> str | None:
    """Minimal Cookie header parser — returns the first value matching ``name`` or None."""
    for h_name, h_val in scope.get("headers", []):
        if h_name == b"cookie":
            for piece in h_val.decode("latin-1", errors="ignore").split(";"):
                k, _, v = piece.strip().partition("=")
                if k == name and v:
                    return v
    return None


def _coerce_uuid(value: str) -> UUID | None:
    """Coerce cookie string to UUID; return None for malformed input."""
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        return None


async def _maybe_touch_last_seen(
    asgi_app,
    conn: "asyncpg.Connection",
    *,
    session_id: UUID,
    current_last_seen: datetime,
) -> None:
    """Per-worker 60s throttle on sessions.last_seen_at UPDATE (D-22c-MIG-05)."""
    cache = _get_or_init_cache(asgi_app)
    now = datetime.now(timezone.utc)
    last_updated = cache.get(session_id)
    if last_updated is not None and (now - last_updated) < LAST_SEEN_THROTTLE:
        return  # Throttled — skip the UPDATE

    await conn.execute(
        "UPDATE sessions SET last_seen_at = NOW() WHERE id = $1",
        session_id,
    )
    cache[session_id] = now
    _maybe_evict(cache)


def _get_or_init_cache(asgi_app):
    """Lazy-init the per-worker last_seen dict on app.state."""
    cache = getattr(asgi_app.state, "session_last_seen", None)
    if cache is None:
        cache = {}
        asgi_app.state.session_last_seen = cache
    return cache


def _maybe_evict(cache) -> None:
    """Soft LRU: drop oldest 10% by timestamp when cache exceeds cap."""
    if len(cache) <= _LAST_SEEN_CACHE_SOFT_CAP:
        return
    drop_n = max(1, _LAST_SEEN_CACHE_SOFT_CAP // 10)
    victims = sorted(cache.items(), key=lambda kv: kv[1])[:drop_n]
    for sid, _ts in victims:
        cache.pop(sid, None)
