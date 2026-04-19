"""Phase 22b-01 Task 3 — openclaw env-var-by-provider contract.

Unit tests for :func:`_resolve_api_key_var` and :func:`_detect_provider`.

Asserts the 4 branches that matter for Phase 22b Gate A:

1. ``anthropic/claude-haiku-4.5`` on an openclaw-shaped recipe (with
   ``api_key_by_provider``) → ``ANTHROPIC_API_KEY``.
2. ``openrouter/anthropic/claude-haiku-4.5`` → ``OPENROUTER_API_KEY``.
3. Deep-path ``anthropic/x/y/z`` → ``ANTHROPIC_API_KEY`` (prefix match).
4. Recipe WITHOUT ``api_key_by_provider`` → falls back to legacy
   ``api_key`` (``OPENROUTER_API_KEY``) regardless of model provider.

Also covers the supporting heuristic branches in :func:`_detect_provider`
(empty model, unrecognized vendor prefix, empty supported list).

These are pure-unit tests — no DB, no Docker, no HTTP. They guard the
RESEARCH.md §Openclaw /start Env-Var Gap contract so a future edit can't
silently misroute a bearer token to the wrong env var.
"""
from __future__ import annotations

from api_server.routes.agent_lifecycle import (
    _detect_provider,
    _resolve_api_key_var,
)


# ---------------------------------------------------------------------------
# Recipe fixtures
# ---------------------------------------------------------------------------


def _openclaw_shaped_recipe() -> dict:
    """Recipe with both legacy ``api_key`` AND ``api_key_by_provider``."""
    return {
        "runtime": {
            "process_env": {
                "api_key": "OPENROUTER_API_KEY",
                "api_key_by_provider": {
                    "anthropic": "ANTHROPIC_API_KEY",
                    "openrouter": "OPENROUTER_API_KEY",
                },
            }
        }
    }


def _legacy_recipe() -> dict:
    """Recipe without ``api_key_by_provider`` — mirrors hermes/picoclaw shape."""
    return {
        "runtime": {
            "process_env": {
                "api_key": "OPENROUTER_API_KEY",
            }
        }
    }


# ---------------------------------------------------------------------------
# _resolve_api_key_var — 4 load-bearing branches per PLAN §Part C
# ---------------------------------------------------------------------------


def test_anthropic_model_maps_to_anthropic_api_key():
    """Branch 1: anthropic/claude-... → ANTHROPIC_API_KEY."""
    recipe = _openclaw_shaped_recipe()
    assert (
        _resolve_api_key_var(recipe, "anthropic/claude-haiku-4.5")
        == "ANTHROPIC_API_KEY"
    )


def test_openrouter_prefixed_model_maps_to_openrouter_api_key():
    """Branch 2: openrouter/anthropic/... → OPENROUTER_API_KEY."""
    recipe = _openclaw_shaped_recipe()
    assert (
        _resolve_api_key_var(recipe, "openrouter/anthropic/claude-haiku-4.5")
        == "OPENROUTER_API_KEY"
    )


def test_deep_path_anthropic_model_maps_to_anthropic_api_key():
    """Branch 3: deep-path ``anthropic/x/y/z`` still detects anthropic
    because the prefix match consumes only the FIRST path segment."""
    recipe = _openclaw_shaped_recipe()
    assert (
        _resolve_api_key_var(recipe, "anthropic/x/y/z") == "ANTHROPIC_API_KEY"
    )


def test_recipe_without_by_provider_falls_back_to_legacy_api_key():
    """Branch 4: no ``api_key_by_provider`` → legacy ``api_key`` regardless
    of the model provider. Backward compatibility for hermes / picoclaw /
    nullclaw / nanobot — none of which declare a provider map in v0.2."""
    recipe_no_map = _legacy_recipe()
    # anthropic model still falls through to the legacy key
    assert (
        _resolve_api_key_var(recipe_no_map, "anthropic/claude")
        == "OPENROUTER_API_KEY"
    )
    # openrouter model also hits the legacy key
    assert (
        _resolve_api_key_var(recipe_no_map, "openrouter/x/y")
        == "OPENROUTER_API_KEY"
    )


# ---------------------------------------------------------------------------
# _resolve_api_key_var — edge cases
# ---------------------------------------------------------------------------


def test_resolve_returns_none_when_process_env_missing():
    """Recipe without runtime or process_env — helper returns None and the
    caller (start_agent) surfaces 500 INTERNAL."""
    assert _resolve_api_key_var({}, "anthropic/claude") is None
    assert _resolve_api_key_var({"runtime": {}}, "anthropic/claude") is None


def test_resolve_with_by_provider_but_missing_provider_falls_back():
    """api_key_by_provider is declared but the detected provider isn't in
    it (e.g. google/gemini on a recipe that only maps anthropic/openrouter).
    The helper falls back to the legacy ``api_key`` value so the flow
    never crashes at dispatch time."""
    recipe = _openclaw_shaped_recipe()
    # google/... detected as "google"; not in the by_provider map.
    assert (
        _resolve_api_key_var(recipe, "google/gemini-2.5")
        == "OPENROUTER_API_KEY"
    )


# ---------------------------------------------------------------------------
# _detect_provider — heuristic branches
# ---------------------------------------------------------------------------


def test_detect_provider_empty_model_uses_provider_compat():
    """Empty / None model → provider_compat.supported[0]."""
    recipe = {"provider_compat": {"supported": ["anthropic", "openrouter"]}}
    assert _detect_provider(None, recipe) == "anthropic"
    assert _detect_provider("", recipe) == "anthropic"


def test_detect_provider_empty_model_empty_supported_defaults_to_openrouter():
    """Empty model AND no provider_compat → safe default ``openrouter``."""
    assert _detect_provider(None, {}) == "openrouter"
    assert _detect_provider("", {"provider_compat": {"supported": []}}) == "openrouter"


def test_detect_provider_unrecognized_prefix_uses_provider_compat():
    """A bare ``<vendor>/<model>`` with an unknown vendor prefix falls
    through to provider_compat.supported[0] (typical OpenRouter model id
    shape — e.g. ``mistralai/mixtral-8x7b`` on a recipe that only tested
    via OpenRouter)."""
    recipe = {"provider_compat": {"supported": ["openrouter"]}}
    assert _detect_provider("mistralai/mixtral-8x7b", recipe) == "openrouter"


def test_detect_provider_recognized_prefixes():
    """The 4 well-known vendor prefixes each map to themselves."""
    empty_recipe: dict = {}
    assert _detect_provider("anthropic/claude-haiku-4.5", empty_recipe) == "anthropic"
    assert _detect_provider("openai/gpt-4o-mini", empty_recipe) == "openai"
    assert _detect_provider("openrouter/x/y", empty_recipe) == "openrouter"
    assert _detect_provider("google/gemini-2.5", empty_recipe) == "google"
