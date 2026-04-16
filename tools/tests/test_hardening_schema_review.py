"""Hardening tests for Phase 18 code review findings.

WR-01: root-level `oneOf: [single branch]` collapses every inner error into an
       opaque top-level message. Fix: use `$ref` at root today, flip to
       `oneOf` when v0.2 actually exists. Seam (`$defs.v0_1`) is preserved.

WR-02: `maintainer.name` was not required inside the maintainer object, so an
       empty `maintainer: {}` linted clean. Tighten to require `name`.

WR-04: self-check `$defs` test kept an `if not defs: return` vacuous guard
       even after Plan 02 landed. Now that $defs is load-bearing, the guard
       must assert `v0_1` and `category` exist.
"""
import json
from pathlib import Path

import pytest

import run_recipe
from run_recipe import lint_recipe, load_recipe

SCHEMA_PATH = Path(__file__).parent.parent / "ap.recipe.schema.json"


class TestErrorMessageQualityWR01:
    """WR-01: with `oneOf: [single $ref]`, jsonschema collapses inner errors
    to 'is not valid under any of the given schemas'. Using `$ref` directly
    preserves the deepest failing path. Tests assert that error messages name
    the OFFENDING FIELD path, not just '(root)'."""

    def test_invalid_source_ref_names_the_field(self, minimal_valid_recipe):
        """A recipe with a malicious source.ref should fail lint with an
        error that names `source.ref`, not a bare '(root)' message."""
        bad = dict(minimal_valid_recipe)
        bad["source"] = {
            "repo": "https://github.com/x/y",
            "ref": "main; rm -rf /",  # shell-injection attempt
        }
        errors = lint_recipe(bad)
        assert errors, "expected lint errors on malicious ref"
        assert any("source.ref" in e for e in errors), (
            f"expected 'source.ref' in error path, got: {errors}"
        )

    def test_negative_owner_uid_names_the_field(self, minimal_valid_recipe):
        bad = dict(minimal_valid_recipe)
        bad["runtime"] = {
            **minimal_valid_recipe["runtime"],
            "volumes": [
                {
                    "name": "d",
                    "host": "per_session_tmpdir",
                    "container": "/data",
                    "owner_uid": -5,
                }
            ],
        }
        errors = lint_recipe(bad)
        assert errors
        # Path should mention the volume + owner_uid, not just (root).
        assert any("owner_uid" in e for e in errors), (
            f"expected 'owner_uid' in error path, got: {errors}"
        )

    def test_missing_required_top_level_field_named(self, minimal_valid_recipe):
        bad = {k: v for k, v in minimal_valid_recipe.items() if k != "metadata"}
        errors = lint_recipe(bad)
        assert errors
        # At least one error should mention 'metadata' as the missing field.
        joined = " ".join(errors)
        assert "metadata" in joined, (
            f"expected 'metadata' mentioned in error: {errors}"
        )


class TestMaintainerRequiresNameWR02:
    """WR-02: `metadata.maintainer = {}` linted clean. Tightening requires
    `name` inside the maintainer object."""

    def test_empty_maintainer_object_is_rejected(self, minimal_valid_recipe):
        bad = dict(minimal_valid_recipe)
        bad["metadata"] = {**minimal_valid_recipe["metadata"], "maintainer": {}}
        errors = lint_recipe(bad)
        assert errors, "expected lint errors on empty maintainer object"
        assert any("maintainer" in e for e in errors), (
            f"expected 'maintainer' in error path, got: {errors}"
        )

    def test_maintainer_with_name_accepted(self, minimal_valid_recipe):
        good = dict(minimal_valid_recipe)
        good["metadata"] = {
            **minimal_valid_recipe["metadata"],
            "maintainer": {"name": "Felipe"},
        }
        errors = lint_recipe(good)
        assert errors == [], (
            f"maintainer with only name should pass; got: {errors}"
        )

    def test_maintainer_with_url_only_is_rejected(self, minimal_valid_recipe):
        """URL-only is invalid — name is what identifies."""
        bad = dict(minimal_valid_recipe)
        bad["metadata"] = {
            **minimal_valid_recipe["metadata"],
            "maintainer": {"url": "https://example.com"},
        }
        errors = lint_recipe(bad)
        assert errors, "expected lint errors on url-only maintainer"


class TestSelfCheckGuardTightenedWR04:
    """WR-04: `test_defs_are_well_formed_and_reachable` had a vacuous guard.
    Now that Plan 02 has landed, the schema MUST have `$defs.v0_1` and
    `$defs.category`. The self-check test must assert this as a positive
    contract, not a conditional."""

    def test_schema_has_defs_v0_1(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        assert "$defs" in schema, "schema must declare $defs after Plan 02"
        assert "v0_1" in schema["$defs"], (
            "schema must have $defs.v0_1 per D-01"
        )

    def test_schema_has_defs_category(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        assert "$defs" in schema
        assert "category" in schema["$defs"], (
            "schema must have $defs.category per D-02"
        )

    def test_category_is_referenced_from_both_cell_types(self):
        """D-02 reachability: both verified_cells.items.category and
        known_incompatible_cells.items.category must $ref the same $defs."""
        schema = json.loads(SCHEMA_PATH.read_text())
        content = json.dumps(schema)
        # Minimum 2 occurrences of the category $ref (one per cell type).
        count = content.count('"$ref": "#/$defs/category"')
        assert count >= 2, (
            f"expected ≥2 $refs to #/$defs/category; got {count}"
        )
