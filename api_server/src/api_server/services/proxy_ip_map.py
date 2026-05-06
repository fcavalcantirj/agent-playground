"""ProxyIPMap — in-process {bridge_ip -> (user_id, agent_instance_id, inapp_auth_token)}
cache. Source: agent_containers.bridge_ip column (AMD-04, migration 013).

The proxy router (Phase 29 Plan 04, ``routes/llm_proxy.py``) authenticates
inbound bot calls via a 2-step lookup (D-07 defense-in-depth):

    1. ``request.client.host`` (the bot container's bridge IP) -> this
       cache -> ``(user_id, agent_instance_id, inapp_auth_token)``.
    2. ``Authorization: Bearer ap-proxy-<token>`` matches the cached
       ``inapp_auth_token`` for that bridge IP.

Both checks must agree; a malicious container would need to spoof BOTH
the bridge IP and steal the per-deploy 32-hex inapp_auth_token.

Refresh strategy: 60s polling per CONTEXT D-07. PROBE-VAL-10 confirmed
``client.events()`` works on this platform but the sealed plan picks
60s polling for v1 simplicity. Refresh atomically swaps the entire
internal dict so concurrent ``get()`` callers never see a partial
mid-update view.

Running-only scope (PROBE-VAL-15): the SELECT filters
``container_status='running' AND bridge_ip IS NOT NULL`` so a freshly-
stopped user A's IP can NEVER be mis-attributed to a freshly-started
user B that re-uses the same bridge address — the partial unique index
``ix_agent_containers_bridge_ip_running`` from migration 013 enforces
single-running-row-per-IP at the schema layer.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

_log = logging.getLogger("api_server.proxy_ip_map")

#: Refresh cadence for ``refresh_loop``. 60s per CONTEXT D-07; the
#: planner-sealed value, not a knob. Tests monkey-patch via the
#: ``interval_s`` parameter rather than mutating this constant.
PROXY_IP_REFRESH_INTERVAL_S: float = 60.0


class ProxyIPMap:
    """In-process cache of running-container bridge IPs to caller identity.

    The internal dict maps each bridge IP string to a 3-tuple
    ``(user_id, agent_instance_id, inapp_auth_token)``. The cache is
    rebuilt atomically on every :meth:`refresh` so concurrent
    :meth:`get` callers always see a consistent snapshot.
    """

    def __init__(self, db_pool: Any) -> None:
        self._db_pool = db_pool
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[UUID, UUID, str]] = {}

    async def refresh(self) -> int:
        """Re-read running-container rows + atomically swap the cache.

        Returns the new cache size. The SELECT runs OUTSIDE the lock
        (so concurrent ``get()`` calls aren't blocked on the network
        round-trip); the dict swap happens under the lock and is a
        single reference assignment.
        """
        async with self._db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT bridge_ip, user_id, agent_instance_id, inapp_auth_token
                FROM agent_containers
                WHERE container_status = 'running'
                  AND bridge_ip IS NOT NULL
                  AND inapp_auth_token IS NOT NULL
                """
            )
        new_cache: dict[str, tuple[UUID, UUID, str]] = {
            str(r["bridge_ip"]): (
                r["user_id"],
                r["agent_instance_id"],
                r["inapp_auth_token"],
            )
            for r in rows
        }
        async with self._lock:
            self._cache = new_cache
        return len(new_cache)

    async def get(
        self, bridge_ip: str
    ) -> tuple[UUID, UUID, str] | None:
        """Look up a bridge IP. Returns ``None`` if not in the cache."""
        async with self._lock:
            return self._cache.get(bridge_ip)


async def refresh_loop(
    ip_map: ProxyIPMap,
    stop_event: asyncio.Event,
    interval_s: float = PROXY_IP_REFRESH_INTERVAL_S,
) -> None:
    """Lifespan-managed refresh task. Mirrors :func:`inapp_reaper.reaper_loop`.

    - Calls :meth:`ProxyIPMap.refresh` once per ``interval_s``.
    - On ``stop_event``, returns within the next sleep window
      (``asyncio.wait_for`` interrupts the sleep cleanly).
    - Errors during refresh are logged + swallowed so a transient DB
      hiccup never crashes the loop.

    Plan 29-04 lifespan creates this as an ``asyncio.Task`` and joins
    it via ``app.state.inapp_tasks`` so the existing 5s drain budget
    (main.py shutdown finally block) covers proxy_ip_refresh too.
    """
    while not stop_event.is_set():
        try:
            await ip_map.refresh()
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("proxy_ip_map.refresh_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
            return  # stop_event set during the wait — clean exit.
        except asyncio.TimeoutError:
            # Normal sleep completion — loop continues.
            pass


__all__ = [
    "PROXY_IP_REFRESH_INTERVAL_S",
    "ProxyIPMap",
    "refresh_loop",
]
