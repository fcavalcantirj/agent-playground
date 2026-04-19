"""Lint positive/negative tests including 12 broken recipe fragments.

Pillar 2 (D-02, D-03, D-04, D-11b): validates that the JSON Schema
catches every targeted violation while accepting valid recipes.
"""
import pytest
from pathlib import Path
from ruamel.yaml import YAML
from run_recipe import lint_recipe

_y = YAML(typ="safe")


class TestLintPositive:
    """Valid recipes must pass lint."""

    def test_minimal_valid_recipe_passes(self, minimal_valid_recipe, schema):
        errors = lint_recipe(minimal_valid_recipe, schema)
        assert errors == [], f"Minimal valid recipe should pass: {errors}"


class TestLintApiVersion:
    """D-04: only ap.recipe/v0.1 accepted."""

    def test_wrong_api_version_rejected(self, broken_recipes_dir, schema):
        recipe = _y.load((broken_recipes_dir / "wrong_api_version.yaml").read_text())
        errors = lint_recipe(recipe, schema)
        assert errors, "v0 apiVersion should be rejected"

    def test_missing_api_version_rejected(self, broken_recipes_dir, schema):
        recipe = _y.load((broken_recipes_dir / "missing_api_version.yaml").read_text())
        errors = lint_recipe(recipe, schema)
        assert errors, "Missing apiVersion should be rejected"


class TestLintAdditionalProperties:
    """D-03: unknown keys rejected."""

    def test_unknown_top_level_key_rejected(self, broken_recipes_dir, schema):
        recipe = _y.load((broken_recipes_dir / "unknown_top_level_key.yaml").read_text())
        errors = lint_recipe(recipe, schema)
        assert errors, "Unknown top-level key should be rejected"
        assert any("additional" in e.lower() or "foo" in e.lower() for e in errors)


class TestLintCrossFieldInvariants:
    """D-02: if/then cross-field constraints."""

    def test_missing_needle_for_contains_string(self, broken_recipes_dir, schema):
        recipe = _y.load((broken_recipes_dir / "missing_needle.yaml").read_text())
        errors = lint_recipe(recipe, schema)
        assert errors, "response_contains_string without needle should fail"

    def test_missing_regex_for_response_regex(self, broken_recipes_dir, schema):
        recipe = _y.load((broken_recipes_dir / "missing_regex.yaml").read_text())
        errors = lint_recipe(recipe, schema)
        assert errors, "response_regex without regex should fail"

    def test_image_pull_without_image(self, broken_recipes_dir, schema):
        recipe = _y.load((broken_recipes_dir / "image_pull_no_image.yaml").read_text())
        errors = lint_recipe(recipe, schema)
        assert errors, "image_pull without build.image should fail"


class TestLintBrokenRecipes:
    """D-11b, D-13: all broken recipe fragments must fail lint."""

    @pytest.fixture
    def all_broken_files(self, broken_recipes_dir):
        return sorted(broken_recipes_dir.glob("*.yaml"))

    def test_at_least_10_broken_recipes_exist(self, all_broken_files):
        assert len(all_broken_files) >= 10, (
            f"Need >=10 broken recipes, got {len(all_broken_files)}"
        )

    @pytest.mark.parametrize(
        "filename",
        [
            "missing_api_version.yaml",
            "wrong_api_version.yaml",
            "missing_name.yaml",
            "invalid_name_chars.yaml",
            "missing_build_mode.yaml",
            "unknown_build_mode.yaml",
            "missing_needle.yaml",
            "missing_regex.yaml",
            "unknown_top_level_key.yaml",
            "missing_smoke_prompt.yaml",
            "missing_verified_cells.yaml",
            "image_pull_no_image.yaml",
        ],
    )
    def test_broken_recipe_fails_lint(self, broken_recipes_dir, schema, filename):
        path = broken_recipes_dir / filename
        assert path.exists(), f"{filename} not found in broken_recipes/"
        recipe = _y.load(path.read_text())
        errors = lint_recipe(recipe, schema)
        assert errors, f"{filename} should fail lint but passed"
        # Each broken fixture targets exactly one violation — overlapping schema
        # clauses (e.g. top-level + allOf branch both requiring the same field)
        # would surface as duplicate messages. Assert message uniqueness to
        # catch that class of schema redundancy.
        assert len(errors) == len(set(errors)), (
            f"{filename} produced duplicate error messages: {errors}"
        )


class TestLintRealRecipes:
    """Regression guard for Phase 22b-09 (Gap 3 closure).

    Asserts that every committed recipe in recipes/*.yaml lints clean
    against tools/ap.recipe.schema.json. Phase 22b-06 added direct_interface
    + event_log_regex to all 5 recipes; Phase 22b-08 (gap closure) carries
    event_source_fallback for nullclaw + openclaw. The schema gained
    direct_interface_block + event_source_fallback $defs (Phase 22b-09).

    A FAIL here means either:
      (a) the schema regressed (a future edit broke an existing field), OR
      (b) a recipe gained a new field the schema doesn't declare yet (the
          recipe needs additive schema work, NOT a relaxed `additionalProperties`).

    The 5 recipes are an explicit list (not a glob) so adding a new recipe
    forces a code review of this test. See conftest.py::real_recipes fixture.
    """

    @pytest.mark.parametrize("recipe_name,recipe_path", [
        ("hermes",   None),
        ("picoclaw", None),
        ("nullclaw", None),
        ("nanobot",  None),
        ("openclaw", None),
    ])
    def test_real_recipe_lints_clean(self, real_recipes, schema, recipe_name, recipe_path):
        # Resolve path from the fixture (parametrize ids are cosmetic; fixture
        # is the source of truth).
        match = next((p for n, p in real_recipes if n == recipe_name), None)
        assert match is not None, f"recipe {recipe_name!r} not in real_recipes fixture"
        recipe = _y.load(match.read_text())
        errors = lint_recipe(recipe, schema)
        assert errors == [], (
            f"Real recipe {recipe_name!r} should lint clean against tools/ap.recipe.schema.json "
            f"but produced {len(errors)} errors:\n  - " + "\n  - ".join(errors[:10])
        )

    def test_all_5_recipes_listed(self, real_recipes):
        """Sanity: catch accidental fixture truncation."""
        names = {n for n, _ in real_recipes}
        assert names == {"hermes", "picoclaw", "nullclaw", "nanobot", "openclaw"}, \
            f"real_recipes fixture missing or extra entries: {names}"

    def test_all_5_recipe_files_exist(self, real_recipes):
        """Sanity: catch accidental file deletion."""
        for name, path in real_recipes:
            assert path.exists(), f"recipe file missing: {name} at {path}"
