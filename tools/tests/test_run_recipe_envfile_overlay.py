"""Wave 0 — Phase 22c.3.1 Plan 01 Task 1 RED tests for env-file overlay (D-24).

Pure-unit tests for tools/run_recipe.py::_build_env_file_content. No subprocess,
no docker. Imports the helper directly. Per B-6 fix: the helper is module-level
and unit-testable without monkey-patching subprocess.

These tests start RED (ImportError — _build_env_file_content does not yet exist
at tools/run_recipe.py) and turn GREEN once Task 1 lands the helper.
"""
from __future__ import annotations


def test_overlay_smoke():
    """Sanity stub so pytest can collect the file before Task 1 RED commit."""
    pass
