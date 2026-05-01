"""Phase 22c.3.1 Plan 01 Task 1 — placeholder substitution helper.

Lifted from api_server/tests/e2e/_helpers.py:40-58 per D-14. Recursive
substitution of ``${VAR}``, ``$VAR``, ``{key}`` shapes across str/list/dict.

Per D-15 the substitution order is ``${VAR}`` → ``$VAR`` → ``{key}`` per-key,
which matches the reference implementation in _helpers.py — three replacement
passes per (k, v) pair, applied longest-form first so ``${VAR}`` consumes
both braces before ``$VAR`` can match the bare prefix.
"""
from __future__ import annotations

from typing import Any


def render_placeholders(value: Any, substitutions: dict[str, str]):
    """Recursively substitute ``${VAR}``, ``$VAR``, ``{key}`` shapes.

    For str: applies all three replacement shapes for every key in
    substitutions; missing keys leave the placeholder untouched (no
    KeyError). For list / dict: recurses element-wise (dict KEYS are
    not substituted, only values). Other types pass through unchanged.

    Verbatim port of api_server/tests/e2e/_helpers.py::render_placeholders.
    """
    if isinstance(value, str):
        out = value
        for k, v in substitutions.items():
            v = str(v)
            out = (
                out
                .replace(f"${{{k}}}", v)
                .replace(f"${k}", v)
                .replace(f"{{{k}}}", v)
            )
        return out
    if isinstance(value, list):
        return [render_placeholders(x, substitutions) for x in value]
    if isinstance(value, dict):
        return {k: render_placeholders(v, substitutions) for k, v in value.items()}
    return value


__all__ = ["render_placeholders"]
