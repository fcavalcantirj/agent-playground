"""Shared fixtures for Phase 28 Temporal workflow / activity / route tests.

Two fixtures live here per Plan 28-07 Task 1:

* ``temporal_env`` — per-test ``WorkflowEnvironment.start_time_skipping``.
  NOT session-scoped: each test gets a fresh in-process Temporal Server
  so registered workflow / activity sets cannot leak between tests.
* ``make_dispatch_input`` — factory yielding valid
  ``DispatchMessageInput`` dataclass instances with sane UUID defaults.

The Postgres-backed ``db_pool`` fixture used by activity-level tests is
inherited from ``tests/conftest.py`` (testcontainers Postgres 17,
session-scoped container + per-test TRUNCATE). The respx-mocked HTTP
boundary is per-test inside each activity test body.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def temporal_env():
    """Per-test WorkflowEnvironment with time-skipping. Disposed after test.

    NOT session-scoped — each test gets a fresh in-process Temporal Server
    so registered workflow / activity sets don't leak between cases.

    The ``start_time_skipping()`` factory boots a real Temporal test
    server bundled with the SDK. This is real Temporal — same gRPC,
    same workflow-replay machinery — NOT a mock. CLAUDE.md Golden
    Rule #1 compliant.
    """
    from temporalio.testing import WorkflowEnvironment

    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


@pytest.fixture
def make_dispatch_input():
    """Factory for valid ``DispatchMessageInput`` dataclass instances.

    Returns a callable accepting per-test field overrides; defaults are
    syntactically valid UUIDs and reasonable scalar values so a typical
    test only overrides the field(s) under examination.
    """
    from api_server.temporal.workflows.dispatch_message import DispatchMessageInput

    def _make(**overrides: Any) -> DispatchMessageInput:
        defaults: dict[str, Any] = dict(
            message_id=str(UUID(int=1)),
            user_id=str(UUID(int=2)),
            agent_id=str(UUID(int=3)),
            container_row_id=str(UUID(int=4)),
            container_id="docker-cont-id-deadbeef",
            recipe_name="hermes-test",
            agent_model="anthropic/claude-3.5-sonnet",
            content="hi",
            inapp_auth_token=None,
            bot_timeout_seconds=60.0,
        )
        defaults.update(overrides)
        return DispatchMessageInput(**defaults)

    return _make
