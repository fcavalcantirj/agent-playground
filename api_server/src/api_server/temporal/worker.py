"""Phase 28 — Temporal worker process.

Mirrors MSV ``messaging/cmd/worker/main.go:288-327`` in shape (Go-portable
Python per CONTEXT D-09). Runs as ``python -m api_server.temporal.worker``
via the ``deploy-temporal-worker-1`` container in
``deploy/docker-compose.prod.yml``.

Responsibilities:

1. Configure structured logging (same chain as the api_server).
2. Open the process-wide asyncpg pool, redis client, shared
   ``httpx.AsyncClient`` (bot HTTP), and ``InappRecipeIndex`` — same
   shape as ``main.lifespan`` so the worker's activities have identical
   dependency surface to the legacy dispatcher's
   ``state.{db,bot_http_client,recipe_index}``.
3. Connect to Temporal with an outer 5×5s retry loop (RESEARCH §7 R5)
   so a slow-booting cluster (compose ``temporal: service_healthy``
   gate not yet flipped) doesn't crash-loop the container.
4. Construct the ``Worker`` with:

   - ``DispatchMessageWorkflow`` registered.
   - 7 activities registered:
     * ReadinessActivities.check_container_ready (bound)
     * ForwardActivities.forward_to_agent      (bound)
     * RecordUsageActivities.record_usage      (bound)
     * MarkActivities.mark_message_done        (bound)
     * MarkFailedActivities.mark_message_failed (bound)
     * emit_inapp_outbound                      (standalone no-op)
     * debit_balance                            (standalone D-22 no-op)
   - ``max_concurrent_activities=10``, ``max_activities_per_second=5``
     (mirrors MSV).

5. SIGTERM / SIGINT graceful drain via ``Worker.shutdown()``.

Environment (read via ``Settings``):

- ``DATABASE_URL`` (asyncpg pool)
- ``AP_REDIS_URL`` (redis ping at boot — fail-loud)
- ``AP_RECIPES_DIR`` (InappRecipeIndex)
- ``AP_DOCKER_NETWORK`` (container-IP lookup)
- ``AP_TEMPORAL_HOST`` / ``AP_TEMPORAL_NAMESPACE`` / ``AP_TEMPORAL_TASK_QUEUE``

The worker container's compose definition (deploy/docker-compose.prod.yml)
already wires all of these via ``env_file: .env.prod`` + the explicit
``environment:`` block.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import AsyncExitStack

import docker
import httpx
import redis.asyncio as redis_async
import stripe
from temporalio.worker import Worker

from ..config import get_settings
from ..db import close_pool, create_pool
from ..log import configure_logging
from ..services.inapp_recipe_index import InappRecipeIndex
from ..services.proxy_byok_cache import ProxyBYOKCache
from .activities.backfill_openrouter_cost import BackfillOpenRouterCostActivities
from .activities.check_container_ready import ReadinessActivities
from .activities.debit_balance import DebitBalanceActivities
from .activities.emit_inapp_outbound import emit_inapp_outbound
from .activities.forward_to_agent import ForwardActivities
from .activities.mark_message_done import MarkActivities
from .activities.mark_message_failed import MarkFailedActivities
from .activities.prune_messages import PruneMessagesActivities
from .activities.reconcile_ledger import ReconcileLedgerActivities
from .activities.reconcile_stripe import ReconcileStripeActivities
from .activities.record_usage import RecordUsageActivities
from .client import make_client
from .schedules import register_schedules
from .workflows.backfill_openrouter_cost import BackfillOpenRouterCostWorkflow
from .workflows.dispatch_message import DispatchMessageWorkflow
from .workflows.prune_messages import PruneMessagesWorkflow
from .workflows.reconcile_ledger import ReconcileLedgerWorkflow
from .workflows.reconcile_stripe import ReconcileStripeWorkflow


async def main() -> None:
    """Boot the worker, register workflow + 7 activities, run until signal."""
    settings = get_settings()
    configure_logging(settings.env)
    # configure_logging() sets up structlog; stdlib `logging` (used by
    # this module + the activities + the temporalio SDK itself) needs a
    # separate basicConfig so log records reach stdout. The api_server
    # process gets this for free because uvicorn configures the root
    # logger; the worker has no uvicorn so we configure it explicitly.
    # Plain text format (no JSON) keeps the worker logs grep-friendly
    # the same way `docker logs deploy-api_server-1` is.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("api_server.temporal.worker")
    log.info(
        "phase28.worker.boot",
        extra={
            "task_queue": settings.temporal_task_queue,
            "namespace": settings.temporal_namespace,
            "host": settings.temporal_host,
            "recipes_dir": str(settings.recipes_dir),
            "docker_network": settings.docker_network_name,
        },
    )

    async with AsyncExitStack() as stack:
        # 1. asyncpg pool — fail-loud on connect (mirrors api_server lifespan).
        db_pool = await create_pool(settings.database_url)
        stack.push_async_callback(close_pool, db_pool)
        log.info("phase28.worker.db_pool_ready")

        # 2. Redis client — fail-loud on PING (mirrors api_server lifespan).
        #    Activities don't currently publish directly (the outbox pump
        #    in api_server owns Redis fan-out); the client is constructed
        #    here as a defensive pre-flight so a misconfigured AP_REDIS_URL
        #    surfaces at worker boot, not on first message dispatch.
        redis_client = redis_async.from_url(
            settings.redis_url,
            decode_responses=False,
            max_connections=20,
        )
        await redis_client.ping()
        stack.push_async_callback(redis_client.aclose)
        log.info("phase28.worker.redis_ping_ok")

        # 3. Shared httpx.AsyncClient for the bot HTTP forward (D-12).
        #    600s read timeout matches the legacy dispatcher's BOT_TIMEOUT_SECONDS;
        #    forward_to_agent overrides per-call via inp.bot_timeout_seconds.
        bot_http = httpx.AsyncClient(
            timeout=httpx.Timeout(600.0, connect=5.0),
            limits=httpx.Limits(
                max_connections=50, max_keepalive_connections=20
            ),
        )
        stack.push_async_callback(bot_http.aclose)

        # 3b. Phase 29 Plan 07 — proxy_upstream_client (AMD-05) for the
        #     BackfillOpenRouterCostActivities GET to /api/v1/generation.
        #     SEPARATE from bot_http above — this client targets upstream
        #     LLM providers, not bots. Per-request 10s timeout in the
        #     activity overrides the client default.
        proxy_upstream_http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(
                max_connections=20, max_keepalive_connections=10
            ),
        )
        stack.push_async_callback(proxy_upstream_http.aclose)

        # 3c. Phase 29 Plan 05 — ProxyBYOKCache for the backfill activity
        #     to look up the per-deploy BYOK key via
        #     ``(user_id, agent_instance_id) -> (provider, decrypted_key)``.
        #     Rehydrate from agent_containers WHERE container_status='running'
        #     AND provider_key_enc IS NOT NULL — restart resilience per D-02.
        byok_cache = ProxyBYOKCache(db_pool=db_pool)
        _byok_loaded = await byok_cache.rehydrate_from_db()
        log.info(
            "phase29.worker.proxy_byok_cache_rehydrated",
            extra={"count": _byok_loaded},
        )

        # 4. Docker client + InappRecipeIndex (recipe lookup + container IP).
        #    docker.from_env() reads DOCKER_HOST / unix socket; the compose
        #    service mounts /var/run/docker.sock so this works inside the
        #    worker container.
        docker_client = docker.from_env()
        stack.callback(docker_client.close)
        recipe_index = InappRecipeIndex(
            recipes_dir=settings.recipes_dir,
            docker_client=docker_client,
            network_name=settings.docker_network_name,
        )

        # 5. Class-bound activity instances. Each activity reuses the
        #    same db_pool to share connection pool capacity across all 5
        #    activity calls in a single workflow run.
        ready_acts = ReadinessActivities(db_pool=db_pool)
        forward_acts = ForwardActivities(
            db_pool=db_pool,
            bot_http_client=bot_http,
            recipe_index=recipe_index,
        )
        usage_acts = RecordUsageActivities(db_pool=db_pool)
        mark_acts = MarkActivities(db_pool=db_pool)
        mark_failed_acts = MarkFailedActivities(db_pool=db_pool)
        # Phase B Plan B-stripe-08 — class-bound debit_balance with the
        # process-wide asyncpg pool injected (the standalone D-22 stub
        # previously held this slot; Phase B replaces the body with the
        # real ledger-as-truth debit and the class lets us inject db_pool).
        debit_acts = DebitBalanceActivities(db_pool=db_pool)
        # Phase 29 Plan 07 — class-bound backfill activity. Uses the
        # process-wide proxy_upstream_http (AMD-05) and the rehydrated
        # ProxyBYOKCache so the activity can read the per-deploy BYOK
        # key without re-decrypting per call.
        backfill_acts = BackfillOpenRouterCostActivities(
            db_pool=db_pool,
            upstream_client=proxy_upstream_http,
            byok_cache=byok_cache,
        )
        # Phase B Plan B-stripe-09 — three scheduled-workflow activities.
        # Each owns one cron-driven workflow; class-bound so the worker can
        # inject the process-wide asyncpg pool (and the StripeClient for
        # the reconcile-stripe activity).
        prune_acts = PruneMessagesActivities(db_pool=db_pool)
        # Construct a process-wide stripe.StripeClient for the
        # reconcile-stripe activity. The api_server lifespan already
        # builds one via services.stripe_client.build_stripe_client; we
        # mirror the construction shape here so the worker has its own
        # client (separate process, no shared state with api_server).
        stripe_client_for_reconcile = stripe.StripeClient(
            settings.stripe_api_key,
        )
        reconcile_stripe_acts = ReconcileStripeActivities(
            db_pool=db_pool,
            stripe_client=stripe_client_for_reconcile,
        )
        reconcile_ledger_acts = ReconcileLedgerActivities(db_pool=db_pool)

        # 6. Connect to Temporal with outer 5×5s retry (RESEARCH §7 R5).
        #    The compose ``depends_on: temporal: service_healthy`` gate
        #    means Temporal IS reachable when this container starts, but
        #    "reachable" != "ready to accept worker registrations" — the
        #    cluster needs a few extra seconds after the gRPC port opens
        #    to finish namespace bootstrap. The retry budget covers it.
        client = None
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                client = await make_client(settings)
                break
            except Exception as e:  # noqa: BLE001 — broad on purpose
                last_error = e
                log.warning(
                    "phase28.worker.connect.retry",
                    extra={"attempt": attempt + 1, "error": str(e)},
                )
                if attempt < 4:
                    await asyncio.sleep(5.0)
        if client is None:
            log.error(
                "phase28.worker.connect.exhausted",
                extra={"error": str(last_error) if last_error else "unknown"},
            )
            raise RuntimeError("temporal connect retries exhausted") from last_error
        log.info("phase28.worker.connected")

        # 7. Build the Worker.
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[
                DispatchMessageWorkflow,
                BackfillOpenRouterCostWorkflow,    # Phase 29 Plan 07
                PruneMessagesWorkflow,              # Phase B Plan B-stripe-09
                ReconcileStripeWorkflow,            # Phase B Plan B-stripe-09
                ReconcileLedgerWorkflow,            # Phase B Plan B-stripe-09
            ],
            activities=[
                ready_acts.check_container_ready,
                forward_acts.forward_to_agent,
                usage_acts.record_usage,
                emit_inapp_outbound,            # standalone no-op
                mark_acts.mark_message_done,
                mark_failed_acts.mark_message_failed,
                debit_acts.debit_balance,       # Phase B class-bound (Plan B-stripe-08)
                backfill_acts.backfill,         # Phase 29 Plan 07
                prune_acts.prune_messages,            # Phase B Plan B-stripe-09
                reconcile_stripe_acts.reconcile,      # Phase B Plan B-stripe-09
                reconcile_ledger_acts.reconcile,      # Phase B Plan B-stripe-09
            ],
            max_concurrent_activities=10,
            max_activities_per_second=5,
        )
        log.info("phase28.worker.registered")

        # 7b. Phase B Plan B-stripe-09 — register the 3 cron schedules.
        # Idempotent: a second worker boot updates instead of crashing
        # (Pitfall 8; spike-d-proven typed ScheduleAlreadyRunningError
        # path). Runs AFTER the worker is built but BEFORE worker.run()
        # so the schedules exist in Temporal before the cron tick fires.
        # Failure here is fail-loud: schedule registration is part of
        # the worker's contract, not best-effort.
        await register_schedules(client, settings.temporal_task_queue)
        log.info(
            "phase_b.worker.schedules_registered",
            extra={"task_queue": settings.temporal_task_queue},
        )

        # 8. SIGTERM / SIGINT graceful drain.
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _shutdown() -> None:
            log.info("phase28.worker.shutdown_signal")
            stop_event.set()

        loop.add_signal_handler(signal.SIGTERM, _shutdown)
        loop.add_signal_handler(signal.SIGINT, _shutdown)

        # 9. Run until either the worker exits on its own (rare — a
        #    server-side cancel) or the stop_event fires (typical —
        #    container SIGTERM). Then call Worker.shutdown() to drain
        #    any in-flight activities cleanly.
        run_task = asyncio.create_task(worker.run(), name="temporal-worker-run")
        stop_task = asyncio.create_task(stop_event.wait(), name="temporal-worker-stop")
        log.info("phase28.worker.running")
        done, pending = await asyncio.wait(
            {run_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            log.info("phase28.worker.shutdown_begin")
            await worker.shutdown()
            run_task.cancel()
            try:
                await run_task
            except (asyncio.CancelledError, Exception):
                pass
        else:
            stop_task.cancel()
        log.info("phase28.worker.exited_clean")


if __name__ == "__main__":
    asyncio.run(main())
