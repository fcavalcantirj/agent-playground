"""Phase 22c.3.1 Plan 01 Task 1 RED tests for tools/_placeholders.py (D-12..D-15).

Pure-unit substitution tests. Lifted-shape from
api_server/tests/e2e/_helpers.py:40-58 — three accepted placeholder shapes
(``${VAR}``, ``$VAR``, ``{key}``), recursive across str/list/dict, missing
keys left alone.
"""
from __future__ import annotations

# tools/ on sys.path is set by tools/tests/conftest.py
from _placeholders import render_placeholders


def test_render_placeholders_dollar_brace_shape():
    """`${VAR}` form — bash-style with braces."""
    assert render_placeholders("hello ${NAME}", {"NAME": "world"}) == "hello world"


def test_render_placeholders_bare_dollar_shape():
    """`$VAR` form — bash-style without braces."""
    assert render_placeholders("$MODEL", {"MODEL": "anthropic/claude-haiku-4-5"}) == "anthropic/claude-haiku-4-5"


def test_render_placeholders_brace_shape():
    """`{key}` form — recipe-template style."""
    assert render_placeholders("{agent_name}.local", {"agent_name": "alice"}) == "alice.local"


def test_render_placeholders_recursive_list():
    """List elements recursed independently."""
    out = render_placeholders(["${A}", "{b}"], {"A": "1", "b": "2"})
    assert out == ["1", "2"]


def test_render_placeholders_recursive_dict():
    """Dict values recursed; keys are not substituted."""
    out = render_placeholders({"k": "${V}"}, {"V": "x"})
    assert out == {"k": "x"}


def test_render_placeholders_unmatched_left_alone():
    """Missing substitution keys leave the placeholder verbatim — no KeyError."""
    out = render_placeholders("${MISSING}", {"OTHER": "v"})
    assert out == "${MISSING}"
