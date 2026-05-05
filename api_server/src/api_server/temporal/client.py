"""Temporal client factory.

Single entry point for both consumers:

1. The api_server FastAPI lifespan (Plan 28-06) — opens one client at
   startup, stashes it on ``app.state.temporal_client``, and the
   ``POST /v1/agents/:id/messages`` route handler calls
   ``client.start_workflow(DispatchMessageWorkflow.run, ...)`` against it.
2. The worker process (Plan 28-04) — ``python -m api_server.temporal.worker``
   opens its own client and passes it to ``temporalio.worker.Worker``.

CONTEXT references: D-01 (self-hosted Temporal via compose),
D-03 (single namespace ``default``).

Settings driving the connect call (from Plan 28-02):

- ``settings.temporal_host``      → e.g. ``temporal:7233`` (compose DNS)
                                      or ``localhost:7233`` (host venv path).
- ``settings.temporal_namespace`` → e.g. ``default``.

NO retry loop in this factory. The connect call raises
``RPCError`` / ``OSError`` on network failure; Plan 28-04's worker.py
wraps ``make_client`` with an outer 5×5s backoff loop because the
worker process must wait for the cluster to reach healthy on cold-start.
The api_server lifespan calls ``make_client`` at startup AFTER the
``temporal: service_healthy`` depends_on gate (Plan 28-02), so it
doesn't need its own retry.
"""
from __future__ import annotations

from temporalio.client import Client

from ..config import Settings


async def make_client(settings: Settings) -> Client:
    """Connect to Temporal frontend and return the live ``Client``.

    Single ``await``, no retry. Caller owns retry policy if it needs one.
    """
    return await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
