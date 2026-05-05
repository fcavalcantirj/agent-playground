"""Phase 28 — Temporal-backed message dispatch.

This package owns the workflow + activities + worker entry point that
replaces ``services/inapp_dispatcher.py`` (CONTEXT D-06). It mirrors
MSV's ``messaging/`` package shape (CONTEXT D-09 — Go-portable Python).

Subpackages:

- :mod:`api_server.temporal.client` — ``make_client(settings)`` factory
  consumed by both the api_server lifespan (Plan 28-06) and the worker
  process (Plan 28-04).
- :mod:`api_server.temporal.workflows` — workflow definitions
  (currently ``DispatchMessageWorkflow``); strict determinism rules
  apply (no httpx/asyncpg/redis/docker imports in workflow files).
- :mod:`api_server.temporal.activities` — activity implementations.
  Plan 03 ships NotImplementedError stubs; Plan 04 fills the bodies.
- :mod:`api_server.temporal.worker` — worker process entry point
  (``python -m api_server.temporal.worker``). Lands in Plan 28-04.

The package depends on ``temporalio>=1.27.0,<1.28`` (pinned by Plan 02).
"""
