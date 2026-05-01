"""Wave 0 — Phase 22c.3.1 Plan 01 Task 1 RED tests for tools/_placeholders.py.

Pure-unit tests for the substitution helper. No subprocess, no docker, no network.
Lifted-from-_helpers.py shape verbatim per D-14 + D-12..D-15.

These tests start RED (NotImplementedError or ImportError) and turn GREEN once
Task 1 lands the helper at tools/_placeholders.py.
"""
from __future__ import annotations


def test_placeholder_smoke():
    """Sanity stub so pytest can collect the file before Task 1 RED commit."""
    pass
