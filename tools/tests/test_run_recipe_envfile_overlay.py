"""Phase 22c.3.1 Plan 01 Task 1 RED tests for env-file overlay (D-24).

Pure-unit tests for tools/run_recipe.py::_build_env_file_content. No subprocess,
no docker. Imports the helper directly. Per B-6 fix: the helper is module-level
and unit-testable without monkey-patching subprocess.

These tests start RED (ImportError — _build_env_file_content does not yet exist
at tools/run_recipe.py) and turn GREEN once Task 1 lands the helper.
"""
from __future__ import annotations

# tools/ on sys.path is set by tools/tests/conftest.py
from run_recipe import _build_env_file_content


def test_envfile_legacy_only():
    """Just the api_key_var line, no creds, no overlay."""
    out = _build_env_file_content(
        "OPENROUTER_API_KEY", "sk-xx", [], [], {}, None,
    )
    assert out == "OPENROUTER_API_KEY=sk-xx\n"


def test_envfile_with_required_inputs():
    """Required inputs in declared order, prefix_required honored."""
    required_inputs = [{"env": "FOO"}, {"env": "BAR"}]
    out = _build_env_file_content(
        "OPENROUTER_API_KEY", "sk-xx",
        required_inputs, [],
        {"FOO": "1", "BAR": "2"},
        None,
    )
    expected = "OPENROUTER_API_KEY=sk-xx\nFOO=1\nBAR=2\n"
    assert out == expected


def test_envfile_activation_env_overlay_wins():
    """D-24: activation_env value beats legacy api_key value (last line wins).

    Same key OPENROUTER_API_KEY appears in BOTH the legacy api_key_var line
    AND in rendered_activation_env. The env-file content must end with the
    activation_env value (later line wins per docker --env-file semantics).
    """
    out = _build_env_file_content(
        "OPENROUTER_API_KEY", "value-1",
        [], [],
        {},
        {"OPENROUTER_API_KEY": "value-2"},
    )
    # Last line is the overlay
    assert out.endswith("OPENROUTER_API_KEY=value-2\n")
    # Both lines present (no dedup)
    assert "OPENROUTER_API_KEY=value-1\n" in out
    assert "OPENROUTER_API_KEY=value-2\n" in out


def test_envfile_activation_env_renders_placeholders():
    """Caller passes ALREADY-rendered rendered_activation_env.

    The rendering happens upstream in run_cell_persistent step C.3 (via
    render_placeholders). _build_env_file_content just composes the lines.
    """
    out = _build_env_file_content(
        "OPENROUTER_API_KEY", "sk-xx",
        [], [],
        {},
        {"INAPP_AUTH_TOKEN": "abc123"},
    )
    assert "INAPP_AUTH_TOKEN=abc123\n" in out
    assert out.startswith("OPENROUTER_API_KEY=sk-xx\n")


def test_envfile_no_overlay_when_override_absent():
    """rendered_activation_env=None → no extra lines appear (D-27 fall-through)."""
    out = _build_env_file_content(
        "OPENROUTER_API_KEY", "sk-xx",
        [{"env": "FOO"}], [],
        {"FOO": "1"},
        None,
    )
    # Only legacy + cred lines; nothing else
    assert out == "OPENROUTER_API_KEY=sk-xx\nFOO=1\n"
