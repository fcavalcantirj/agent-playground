"""Phase 29 Plan 08 Task 2 — recipes/nanobot.yaml flipped to via_proxy: true.

Coverage:

  Test 1 — nanobot has runtime.via_proxy: true.
  Test 2 — ONLY nanobot has via_proxy: true. Regression guard against
           Phase 30's recipe-flip leaking into Phase 29.
  Test 3 — nanobot.channels.inapp.contract == "openai_compat" (sanity:
           the proxy's openai SSE format applies).
  Test 4 — nanobot.runtime.process_env.api_key == "OPENROUTER_API_KEY"
           (sanity: Plan 08 Task 1's runner dispatch routes through the
           OpenAI-SDK shape).
  Test 5 — RecipeSummary.via_proxy is True for nanobot end-to-end via
           recipes_loader.to_summary.

Pure YAML reads — no Postgres, no Docker. No pytestmark needed.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from ruamel.yaml import YAML


REPO_ROOT = Path(__file__).resolve().parents[3]
RECIPES_DIR = REPO_ROOT / "recipes"


def _load(name: str) -> dict:
    y = YAML(typ="rt")
    with open(RECIPES_DIR / f"{name}.yaml") as f:
        return dict(y.load(f))


# ---------------------------------------------------------------------------
# Test 1 — nanobot has via_proxy: true
# ---------------------------------------------------------------------------


def test_nanobot_runtime_via_proxy_is_true() -> None:
    recipe = _load("nanobot")
    assert recipe["runtime"]["via_proxy"] is True, (
        "Phase 29 Plan 08 cutover invariant — runtime.via_proxy must be true"
    )


# ---------------------------------------------------------------------------
# Test 2 — ONLY nanobot has via_proxy: true (regression guard)
# ---------------------------------------------------------------------------


# All 6 recipe filenames in repo/recipes/. nanobot is the cutover; the
# other 5 MUST stay on the legacy non-proxy path until Phase 30.
_OTHER_RECIPES = ["hermes", "openclaw", "zeroclaw", "nullclaw", "picoclaw"]


@pytest.mark.parametrize("recipe_name", _OTHER_RECIPES)
def test_only_nanobot_has_via_proxy_true(recipe_name: str) -> None:
    """Regression guard — Phase 30 work cannot leak into Phase 29."""
    recipe = _load(recipe_name)
    runtime = recipe.get("runtime") or {}
    assert runtime.get("via_proxy", False) is False, (
        f"recipe {recipe_name!r} unexpectedly has via_proxy: true — "
        f"Phase 29 only flips nanobot; Phase 30 flips the others."
    )


def test_only_one_recipe_yaml_has_via_proxy_true() -> None:
    """Combined assertion: across all *.yaml files in recipes/, exactly
    one (nanobot) carries via_proxy: true."""
    flipped_count = 0
    for path in RECIPES_DIR.glob("*.yaml"):
        text = path.read_text()
        if "via_proxy: true" in text:
            flipped_count += 1
    assert flipped_count == 1, (
        f"expected exactly 1 recipe with via_proxy: true, got {flipped_count}"
    )


# ---------------------------------------------------------------------------
# Test 3 — nanobot.channels.inapp.contract is openai_compat
# ---------------------------------------------------------------------------


def test_nanobot_inapp_contract_is_openai_compat() -> None:
    recipe = _load("nanobot")
    assert recipe["channels"]["inapp"]["contract"] == "openai_compat", (
        "the proxy's openai SSE format is the contract for nanobot inapp"
    )


# ---------------------------------------------------------------------------
# Test 4 — nanobot.runtime.process_env.api_key is OPENROUTER_API_KEY
# ---------------------------------------------------------------------------


def test_nanobot_process_env_api_key_is_openrouter() -> None:
    recipe = _load("nanobot")
    assert recipe["runtime"]["process_env"]["api_key"] == "OPENROUTER_API_KEY", (
        "Plan 08 Task 1's runner dispatch routes OPENROUTER_API_KEY → "
        "OPENAI_BASE_URL injection. Other env-var values would change the "
        "injection shape — keep nanobot on OPENROUTER_API_KEY in Phase 29."
    )


# ---------------------------------------------------------------------------
# Test 5 — RecipeSummary.via_proxy=True end-to-end
# ---------------------------------------------------------------------------


def test_nanobot_recipe_summary_surfaces_via_proxy_true() -> None:
    """Load nanobot via recipes_loader.to_summary and assert the surfaced
    via_proxy field is True. Closes the recipe → loader → API contract."""
    from api_server.services.recipes_loader import load_recipe, to_summary

    recipe = load_recipe(RECIPES_DIR / "nanobot.yaml")
    summary = to_summary(recipe)
    assert summary.name == "nanobot"
    assert summary.via_proxy is True


# ---------------------------------------------------------------------------
# Bonus — AMD-09: api_base placeholder substitution lives in BOTH heredocs
# ---------------------------------------------------------------------------


def test_nanobot_api_base_uses_proxy_url_default_form_in_both_heredocs() -> None:
    """AMD-09 — both nanobot config-file heredocs (gateway path for
    channels.telegram + serve path for channels.inapp) substitute the
    proxy URL via sh-default form so via_proxy=true uses the runner-
    injected AP_PROXY_BASE_URL and via_proxy=false falls back to the
    upstream URL (legacy path preserved)."""
    text = (RECIPES_DIR / "nanobot.yaml").read_text()
    pattern = '"api_base": "${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"'
    occurrences = text.count(pattern)
    assert occurrences == 2, (
        f"expected exactly 2 sh-default api_base substitutions in "
        f"nanobot.yaml (gateway heredoc + serve heredoc), got {occurrences}"
    )
    # Defense-in-depth — the original literal MUST be gone.
    assert '"api_base": "https://openrouter.ai/api/v1"' not in text, (
        "the literal upstream URL leaked back into nanobot.yaml — "
        "should be sh-defaulted via AP_PROXY_BASE_URL"
    )
