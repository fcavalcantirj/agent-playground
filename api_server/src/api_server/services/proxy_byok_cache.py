"""ProxyBYOKCache — in-process {(user_id, agent_instance_id) -> (provider, key)}
custody cache. Source: ``agent_containers.provider_key_enc`` BYTEA column
(D-02, migration 013), decrypted via ``crypto.age_cipher.decrypt_channel_config``.

Restart resilience (D-02 — the load-bearing requirement). Lifespan
startup calls :meth:`rehydrate_from_db` which:

    1. Queries ``agent_containers WHERE container_status='running'
       AND provider_key_enc IS NOT NULL``.
    2. Decrypts each row's ``provider_key_enc`` via the per-user KEK
       primitive that ``encrypt_channel_config`` used at deploy time
       (PROBE-VAL-07 verified the round-trip + cross-user isolation).
    3. Populates the in-process cache BEFORE the proxy router accepts
       traffic.

Hot-path lookup (Plan 29-04 ``routes/llm_proxy.py:255``):
``app.state.proxy_byok_cache.get(user_id, agent_instance_id)`` returns
``(provider, decrypted_key)`` or ``(None, None)`` on miss. Mirrors the
ProxyIPMap shape — single ``asyncio.Lock`` guards the dict against
concurrent writes (set / invalidate / rehydrate) while concurrent gets
see consistent snapshots.

via_proxy gate scope (D-04 cadence invariant): only recipes with
``runtime.via_proxy=true`` populate this cache via :meth:`set` from
``start_agent``. Legacy recipes (4 of 5 v0.2 recipes) have
``provider_key_enc IS NULL`` and are filtered out by the rehydrate
WHERE clause — they pay zero validation latency, zero encryption
overhead, zero cache footprint.

T-29-01 / Acceptance Gate 6 (BYOK-key-never-logged invariant):
:meth:`rehydrate_from_db` logs decrypt failures with ONLY the
``agent_instance_id`` in extras. The encrypted ciphertext bytes and
the eventual decrypted key are NEVER written to the log record.
Test 8 in ``tests/services/test_proxy_byok_cache.py`` verifies the
invariant via ``caplog`` capture.

MSV mirror: ``api/pkg/anthropicproxy/proxy.go:116-117, 332-360`` —
same in-process key cache + atomic refresh shape, AP key is
``(user_id, agent_instance_id)`` instead of MSV's ``telegramID``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from ..crypto.age_cipher import decrypt_channel_config

_log = logging.getLogger("api_server.proxy_byok_cache")


class ProxyBYOKCache:
    """In-process custody cache for decrypted BYOK keys.

    Internal dict maps ``(user_id, agent_instance_id)`` to
    ``(provider, decrypted_key)``. The cache is mutated under
    :attr:`_lock` so concurrent rehydrate / set / invalidate calls
    do not race; concurrent :meth:`get` callers always see a
    consistent snapshot.
    """

    def __init__(self, db_pool: Any) -> None:
        self._db_pool = db_pool
        self._lock = asyncio.Lock()
        self._cache: dict[tuple[UUID, UUID], tuple[str, str]] = {}

    async def rehydrate_from_db(self) -> int:
        """Re-populate the cache from running rows on lifespan startup.

        Returns the count of successfully-decrypted rows. Decrypt
        failures (corrupt ciphertext, master-key mismatch, missing
        ``key`` field in the JSON blob) are LOGGED with only the
        ``agent_instance_id`` in extras and SKIPPED — a single bad
        row must not crash the whole rehydrate.

        Per CONTEXT D-02: only via_proxy=true recipes write to
        ``provider_key_enc``, so the WHERE filter naturally scopes
        to those rows. Legacy recipes (provider_key_enc IS NULL)
        are silently excluded.
        """
        async with self._db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, agent_instance_id, upstream_provider,
                       provider_key_enc
                FROM agent_containers
                WHERE container_status = 'running'
                  AND provider_key_enc IS NOT NULL
                """
            )

        loaded = 0
        for row in rows:
            agent_instance_id = row["agent_instance_id"]
            try:
                blob = decrypt_channel_config(
                    row["user_id"], bytes(row["provider_key_enc"]),
                )
                key = blob["key"]
                provider = row["upstream_provider"]
            except Exception:
                # T-29-01 invariant: log carries ONLY the row id, never
                # the ciphertext bytes nor the eventual decrypted key.
                # Test 8 in test_proxy_byok_cache.py asserts this.
                _log.exception(
                    "proxy_byok_cache.rehydrate_failed_row",
                    extra={
                        "agent_instance_id": str(agent_instance_id),
                    },
                )
                continue

            async with self._lock:
                self._cache[(row["user_id"], agent_instance_id)] = (
                    provider, key,
                )
            loaded += 1

        return loaded

    async def get(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
    ) -> tuple[str | None, str | None]:
        """Look up by ``(user_id, agent_instance_id)``.

        Returns ``(provider, decrypted_key)`` on hit or ``(None, None)``
        on miss. Hot-path: called once per proxy request from
        ``routes/llm_proxy.py``.
        """
        async with self._lock:
            entry = self._cache.get((user_id, agent_instance_id))
        if entry is None:
            return (None, None)
        return entry

    async def set(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        provider: str,
        decrypted_key: str,
    ) -> None:
        """Insert or replace an entry.

        Called by ``routes/agent_lifecycle.py::start_agent`` after a
        successful BYOK validation + agent_containers row insert
        (Task 3) — but ONLY when ``recipe.runtime.via_proxy=true``.
        Legacy recipes never call this method.
        """
        async with self._lock:
            self._cache[(user_id, agent_instance_id)] = (
                provider, decrypted_key,
            )

    async def invalidate(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
    ) -> None:
        """Remove an entry. No-op on miss.

        Called when an agent_container is stopped or deleted; keeps the
        cache from holding decrypted keys past their useful life.
        """
        async with self._lock:
            self._cache.pop((user_id, agent_instance_id), None)


__all__ = ["ProxyBYOKCache"]
