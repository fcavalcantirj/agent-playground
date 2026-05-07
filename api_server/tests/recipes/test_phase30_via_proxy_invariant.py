"""Phase 30 cutover invariant — every recipe routes through the proxy.

Replaces the shrinking-_OTHER_RECIPES shape (incrementally flipped in Plans
30-02..30-06) with a positive parametrized assertion across the full
flipped set. Per D-08 finalization.

picoclaw is INCLUDED in _ALL_RECIPES because its static-YAML flip shipped in
Plan 30-04. picoclaw has no e2e harness cell — its harness extension was
DEFERRED on 2026-04-30 per Phase 22c.3 user direction. The static-YAML
invariant here is authoritative for picoclaw; e2e validation for the other
5 recipes happened via per-recipe deploy-stack smokes during Plans
30-02..30-06 (see .planning/phases/30-recipe-proxy-cutover/30-VERIFICATION.md
for the per-recipe usage_logs evidence).
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


_ALL_RECIPES = [
    "nanobot",
    "openclaw",
    "nullclaw",
    "picoclaw",
    "zeroclaw",
    "hermes",
    # Phase 30 followup — QwenPaw added 2026-05-07 with the new
    # agentscope_runtime contract adapter.
    "qwenpaw",
]


@pytest.mark.parametrize("recipe_name", _ALL_RECIPES)
def test_all_recipes_have_via_proxy_true(recipe_name: str) -> None:
    """Phase 30 cutover invariant — every recipe routes through the proxy."""
    recipe = _load(recipe_name)
    runtime = recipe.get("runtime") or {}
    assert runtime.get("via_proxy") is True, (
        f"recipe {recipe_name!r} missing via_proxy: true after Phase 30"
    )


def test_all_recipes_flipped_count() -> None:
    """Combined assertion — exactly len(_ALL_RECIPES) recipes carry via_proxy: true."""
    flipped_count = sum(
        1 for path in RECIPES_DIR.glob("*.yaml")
        if "via_proxy: true" in path.read_text()
    )
    assert flipped_count == len(_ALL_RECIPES), (
        f"expected {len(_ALL_RECIPES)} recipes with via_proxy: true, got {flipped_count}"
    )
