"""OpenRouter `/api/v1/models` passthrough cache (Phase 23 Plan 05).

Single public coroutine ``get_models_payload(state) -> bytes`` returns the
upstream catalog bytes with the following discipline:

- 15-minute in-process TTL cache on ``state.models_cache`` (D-18).
- ``asyncio.Lock`` (``state.models_cache_lock``) deduplicates concurrent
  first-fetches so a thundering herd produces ONE upstream call (RESEARCH §6).
- Stale-while-revalidate (D-18): on upstream failure with a prior cached
  payload available, serve the stale bytes + log
  ``openrouter_models.serving_stale``. Cold-start failure re-raises so the
  route renders a 503 envelope.
- Passthrough bytes (D-20): the function returns ``r.content`` unmodified —
  no JSON parse, no re-serialize.
- Upstream fetch is unauthenticated (D-19): the OpenRouter catalog is
  public; no auth token is sent.

State contract: callers populate ``state.openrouter_http_client`` (httpx
``AsyncClient``), ``state.models_cache`` (mutable dict), and
``state.models_cache_lock`` (``asyncio.Lock``) at lifespan startup.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

_log = logging.getLogger("api_server.openrouter_models")
_OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
_CACHE_TTL = timedelta(minutes=15)


async def get_models_payload(state) -> bytes:
    """Return cached payload bytes; fetch on miss/stale; SWR on failure.

    Fast-path (no lock): if the cache is fresh, return cached bytes.
    Slow-path: acquire the lock, double-check freshness (another coroutine
    may have refreshed during contention), then fetch upstream.

    On upstream failure (any ``httpx.HTTPError`` — network, timeout, 5xx via
    ``raise_for_status``):
      * if the cache holds a prior payload → serve stale (SWR).
      * otherwise → re-raise so the route renders a 503 envelope.
    """
    cache = state.models_cache
    now = datetime.now(timezone.utc)

    # Fast-path: lock-free TTL check. Safe because dict reads of the two
    # fields are atomic at the GIL/asyncio scheduling boundary; a torn
    # read would only force the slow-path which is correct.
    if cache.get("fetched_at") and (now - cache["fetched_at"]) < _CACHE_TTL:
        return cache["payload"]

    async with state.models_cache_lock:
        # Double-check inside the lock — another coroutine may have just
        # refreshed the cache while this one was awaiting the lock.
        now = datetime.now(timezone.utc)
        if cache.get("fetched_at") and (now - cache["fetched_at"]) < _CACHE_TTL:
            return cache["payload"]

        try:
            r = await state.openrouter_http_client.get(_OPENROUTER_URL)
            r.raise_for_status()
        except httpx.HTTPError:
            _log.exception("openrouter_models.fetch_failed")
            if cache.get("payload"):
                # SWR — serve last known payload, do NOT update fetched_at
                # (so the next request also tries to refresh).
                _log.warning("openrouter_models.serving_stale")
                return cache["payload"]
            raise

        # Success — store raw bytes (D-20 passthrough) + fresh timestamp.
        cache["fetched_at"] = now
        cache["payload"] = r.content
        return cache["payload"]
