"""Phase 28 — Temporal workflow / activity / route test suite.

Tests under this package use real infrastructure per CLAUDE.md Golden
Rule #1:

* Workflow-level tests use ``temporalio.testing.WorkflowEnvironment.start_time_skipping()``
  which boots an in-process Temporal Server (the SDK ships it). This is
  real Temporal — same gRPC, same workflow-replay machinery — NOT a
  mock.
* Activity-level tests use the shared ``db_pool`` fixture (testcontainers
  Postgres 17) and ``respx`` for HTTP outbound interception. No
  in-memory DB / fake httpx.

Mock activities ARE registered inside workflow-level tests because we
are testing the WORKFLOW's logic, not the activity bodies. Workflow
tests register fake activities decorated with the same
``@activity.defn(name=...)`` so the workflow sees them as real.
"""
