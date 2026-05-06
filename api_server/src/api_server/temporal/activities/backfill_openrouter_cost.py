"""Phase 29 Plan 07 — backfill_openrouter_cost activity (D-03 + D-10 + AMD-08).

Class-bound Temporal activity that fires ~5s after a successful OpenRouter
stream closes, polls ``GET https://openrouter.ai/api/v1/generation?id=<id>``
until OpenRouter's eventually-consistent ledger settles, and UPDATEs
``usage_logs.cost_usd`` with the canonical USD value reported by
OpenRouter.

PROBE-VAL-03 (2026-05-06) measured the empirical settle latency on
``anthropic/claude-haiku-4-5`` across 5 iterations:

    p50 = 10.5s, p95 = 13.6s, p99 = 27.2s

Per AMD-08 the activity sleeps 5.0s before the first GET (covers the p25
of the settle distribution — earlier lookups return 404) and retries on
404 with backoff ``[0.0, 10.0, 20.0, 30.0]`` for a 65s ceiling, which
covers the empirical p99 with headroom while staying bounded.

The activity reads the per-deploy BYOK key from ``app.state.proxy_byok_cache``
(Plan 29-05) — Assumption A1 from RESEARCH (the same key that minted the
generation can read its own ``/v1/generation`` row); PROBE-VAL-03 verified
5/5 iterations.

The shape mirrors ``forward_to_agent`` lines 73-92 + 239-251 verbatim:
class-bound activity for the bound-method registration discipline plus
a module-level fail-loud placeholder so a misconfigured worker is
detected at first invocation rather than silently passing.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from temporalio import activity

_log = logging.getLogger("api_server.backfill_openrouter_cost")


@dataclass
class BackfillOpenRouterCostInput:
    """Inputs the proxy hands to ``client.start_workflow``.

    All fields are primitive-typed so Temporal JSON serialization is safe;
    UUIDs are stringified at the proxy boundary and re-parsed inside the
    activity body.
    """

    usage_log_id: str           # UUID stringified — usage_logs.id PK
    generation_id: str          # X-Generation-Id captured at proxy time
    user_id: str                # UUID stringified — for BYOK cache lookup
    agent_instance_id: str      # UUID stringified — for BYOK cache lookup


class BackfillOpenRouterCostActivities:
    """Class-bound holder for the backfill activity.

    The worker (``temporal/worker.py``) instantiates this once with the
    process-wide asyncpg pool, the shared ``proxy_upstream_client``
    (AMD-05 — separate from ``bot_http_client``), and the
    ``ProxyBYOKCache`` (Plan 29-05); then registers
    ``self.backfill`` on the Worker's activities list.
    """

    def __init__(
        self,
        *,
        db_pool: Any,
        upstream_client: httpx.AsyncClient,
        byok_cache: Any,
    ) -> None:
        self.db_pool = db_pool
        self.upstream_client = upstream_client
        self.byok_cache = byok_cache

    @activity.defn(name="backfill_openrouter_cost")
    async def backfill(self, inp: BackfillOpenRouterCostInput) -> None:
        """Fetch ``/api/v1/generation``, UPDATE ``usage_logs.cost_usd``.

        Failure modes:

        - Cache miss (BYOK key gone) → log + return; the row keeps the
          proxy's inline cost-weights estimate.
        - Network error every attempt → log + return; row unchanged.
        - 4xx other than 404 → log + return; row unchanged (a 401 here
          means the BYOK key changed between proxy time and backfill
          time, no point retrying).
        - 200 → UPDATE the row + return.

        The activity NEVER raises; the Temporal workflow's outer retry
        policy is purely defensive (the body's own ``[0, 10, 20, 30]``
        budget covers OpenRouter's eventual-consistency window). A
        backfill failure is best-effort by design — the proxy's inline
        cost-weights estimate is the user-visible value if backfill
        fails, and that's a tolerable degradation.
        """
        # PROBE-VAL-03 settle delay (AMD-08; was 2.0s before empirical
        # measurement showed p25 of OpenRouter's /generation latency
        # already exceeds 5s for ~25% of requests).
        await asyncio.sleep(5.0)

        user_id = UUID(inp.user_id)
        agent_instance_id = UUID(inp.agent_instance_id)
        usage_log_id = UUID(inp.usage_log_id)

        provider, key = await self.byok_cache.get(user_id, agent_instance_id)
        if not key:
            activity.logger.warning(
                "backfill.no_byok_key",
                extra={"agent_instance_id": str(agent_instance_id)},
            )
            return

        # AMD-08 budget — covers PROBE-VAL-03 p99=27.2s with headroom.
        for retry_idx, backoff_s in enumerate(
            [0.0, 10.0, 20.0, 30.0]
        ):
            if backoff_s > 0:
                await asyncio.sleep(backoff_s)
            try:
                resp = await self.upstream_client.get(
                    f"https://openrouter.ai/api/v1/generation?id={inp.generation_id}",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=10.0,
                )
            except httpx.HTTPError:
                activity.logger.exception(
                    "backfill.network_error",
                    extra={
                        "usage_log_id": str(usage_log_id),
                        "retry_idx": retry_idx,
                    },
                )
                if retry_idx < 3:
                    continue
                return
            if resp.status_code == 200:
                data = resp.json()["data"]
                cost_usd = Decimal(str(data["total_cost"]))
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE usage_logs SET cost_usd = $1 WHERE id = $2",
                        cost_usd, usage_log_id,
                    )
                activity.logger.info(
                    "backfill.applied",
                    extra={
                        "usage_log_id": str(usage_log_id),
                        "cost_usd": str(cost_usd),
                    },
                )
                return
            if resp.status_code == 404 and retry_idx < 3:
                continue
            activity.logger.warning(
                "backfill.gave_up",
                extra={
                    "status": resp.status_code,
                    "usage_log_id": str(usage_log_id),
                },
            )
            return


@activity.defn(name="backfill_openrouter_cost")
async def backfill_openrouter_cost(inp: BackfillOpenRouterCostInput) -> None:
    """Module-level placeholder — fail-loud import path.

    Workers register :meth:`BackfillOpenRouterCostActivities.backfill`
    (the bound method); this top-level function fails loudly so a
    misconfigured worker is detected immediately rather than silently
    passing. Mirror of ``forward_to_agent.py`` lines 239-251.
    """
    raise NotImplementedError(
        "Workers register BackfillOpenRouterCostActivities.backfill "
        "(bound method); the module-level function is an import-path "
        "placeholder only."
    )


__all__ = [
    "BackfillOpenRouterCostActivities",
    "BackfillOpenRouterCostInput",
    "backfill_openrouter_cost",
]
