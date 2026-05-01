"""Wave 0 — Phase 22c.3.1 Plan 01 Task 1 RED tests for tools/run_recipe.py
::run_cell_persistent (channel-aware override + activation_env overlay +
pre_start_commands loop with cidfile cleanup).

Real Docker integration tests (golden rule #1). Each test boots a real recipe
container via tools.run_recipe.run_cell_persistent and asserts on observable
container state (docker ps, docker inspect, etc.).

These tests start RED (RuntimeError — run_cell_persistent does not yet accept
activation_substitutions kwarg + does not run pre_start_commands) and turn
GREEN once Task 1 lands the extension.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.api_integration


def test_red_smoke():
    """Sanity stub so pytest can collect the file before Task 1 RED commit."""
    pytest.fail("RED — Task 1 RED commit will replace this with real tests")
