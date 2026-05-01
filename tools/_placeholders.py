"""Phase 22c.3.1 Plan 01 Task 1 — placeholder substitution helper.

Lifted from api_server/tests/e2e/_helpers.py:40-58 per D-14. Recursive
substitution of ``${VAR}``, ``$VAR``, ``{key}`` shapes across str/list/dict.

RED state: stub raises NotImplementedError so the unit tests in
tools/tests/test_placeholders.py fail with a clear marker (not ImportError).
Task 1 GREEN replaces the stub with the verbatim port from _helpers.py.
"""
from __future__ import annotations

from typing import Any


def render_placeholders(value: Any, substitutions: dict[str, str]):  # noqa: D401
    """Stub — Task 1 GREEN replaces with verbatim port from _helpers.py."""
    raise NotImplementedError(
        "tools._placeholders.render_placeholders — Task 1 GREEN required"
    )


__all__ = ["render_placeholders"]
