"""Wave 0 — Phase 22c.3.1 Plan 01 Task 2 RED tests for start_agent route.

Real-Docker route tests (D-21 + golden rule #1). Each test boots create_app()
via the started_api_server fixture (function-scoped, defined in
api_server/tests/conftest.py per B-7 fix), seeds an agent_instances row via
direct DB INSERT, and POSTs to /v1/agents/:id/start. The runner spawns a real
recipe container.

These tests start RED (start_agent does not yet mint INAPP_AUTH_TOKEN, the
runner does not yet thread activation_substitutions, etc.) and turn GREEN
once Task 2 lands the extensions.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.api_integration


def test_red_smoke():
    """Sanity stub so pytest can collect the file before Task 2 RED commit."""
    pytest.fail("RED — Task 2 RED commit will replace this with real tests")
