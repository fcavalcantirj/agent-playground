"""Parametrized regression test over all committed recipes.

D-14: every recipe in recipes/*.yaml must pass schema validation.
This is the regression gate: when the schema evolves, any recipe
that stops validating will be caught here.
"""
import pytest
from pathlib import Path
from run_recipe import load_recipe, lint_recipe

RECIPE_DIR = Path(__file__).parent.parent.parent / "recipes"
RECIPE_FILES = sorted(RECIPE_DIR.glob("*.yaml"))


@pytest.mark.parametrize(
    "recipe_path",
    RECIPE_FILES,
    ids=lambda p: p.stem,
)
def test_committed_recipe_passes_lint(recipe_path):
    """Every committed recipe must pass schema validation.

    This is the regression gate: when the schema evolves, any recipe
    that stops validating will be caught here.
    """
    recipe = load_recipe(recipe_path)
    errors = lint_recipe(recipe)
    assert errors == [], f"Lint errors in {recipe_path.name}: {errors}"
