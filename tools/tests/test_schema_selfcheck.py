"""Phase 18 D-10: self-validation gate.

Three tests that pin the schema as both a valid JSON Schema and the contract
the 5 committed recipes live under:

  1. `test_schema_validates_against_draft_2020_12_meta_schema` — the schema
     file itself validates against JSON Schema draft-2020-12.
  2. `test_defs_are_well_formed_and_reachable` — IF `$defs` is declared (it is
     introduced by Plan 02 for D-01 v0_1 + D-02 category) THEN every `$defs/*`
     subschema is well-formed (declares a shape keyword) AND reachable
     (referenced by some `$ref`). Vacuously true before Plan 02 lands.
  3. `test_all_committed_recipes_validate_against_schema` — every recipe under
     `recipes/*.yaml` lints clean. Restates the regression gate of
     `test_recipe_regression.py` at the self-check layer so a reader of this
     file sees the entire D-10 contract in one place.

TDD shape note: the plan originally called for Test 2 to RED today and GREEN
after Plan 02. Per the executor directive (parallel_execution override), the
test is instead written as an always-correct conditional — it passes vacuously
today (no `$defs` on disk) and becomes load-bearing once Plan 02 adds
`$defs.v0_1` + `$defs.category`. Cleaner than xfail + strict=False.

Ref: `.planning/phases/18-schema-maturity/18-CONTEXT.md` §D-10.
"""
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

# Match tools/tests/conftest.py's sys.path insertion so run_recipe imports.
sys.path.insert(0, str(Path(__file__).parent.parent))
from run_recipe import load_recipe, lint_recipe  # noqa: E402

SCHEMA_PATH = Path(__file__).parent.parent / "ap.recipe.schema.json"
RECIPE_DIR = Path(__file__).parent.parent.parent / "recipes"
RECIPE_FILES = sorted(RECIPE_DIR.glob("*.yaml"))

# JSON Schema keywords that count as "shape" — a `$defs/*` subschema that
# declares at least one of these is considered well-formed for D-10.2. See
# draft-2020-12 keyword list; `$ref` is included because a subschema may
# simply alias another definition.
_SHAPE_KEYWORDS = {"type", "oneOf", "$ref", "enum", "const", "allOf", "anyOf"}


def _collect_refs(node, out):
    """Recursively collect every `$ref` value in the schema tree.

    Pure JSON structure traversal — walks dicts and lists only, no dynamic
    imports, no `eval`. Per T-18-01 threat register, the schema is trusted
    repo content but the walker is still side-effect-free by construction.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            out.add(ref)
        for v in node.values():
            _collect_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_refs(v, out)


def test_schema_validates_against_draft_2020_12_meta_schema():
    """D-10.1: the schema file itself is a valid draft-2020-12 JSON Schema.

    `Draft202012Validator.check_schema` raises `jsonschema.SchemaError` on any
    violation of the meta-schema; success is silent. This keeps the schema
    file honest regardless of what Plan 02 (`$defs` refactor) does.
    """
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)


def test_defs_are_well_formed_and_reachable():
    """D-10.2: `$defs/*` well-formedness + reachability.

    Conditional contract: IF `$defs` is present AND non-empty, THEN every
    entry must be a JSON object declaring at least one shape keyword AND
    every entry name must appear in some `#/$defs/<name>` `$ref` in the
    schema tree. Vacuously true when `$defs` is absent (the state before
    Plan 02 lands) and load-bearing after Plan 02 introduces
    `$defs.v0_1` + `$defs.category`.
    """
    schema = json.loads(SCHEMA_PATH.read_text())
    defs = schema.get("$defs")
    # Post-Plan-02: $defs is load-bearing. The original vacuous guard
    # (`if not defs: return`) is gone — $defs MUST contain `v0_1` (D-01)
    # and `category` (D-02). Restating as positive contract so a future
    # accidental $defs deletion is caught.
    assert isinstance(defs, dict) and defs, (
        f"$defs must be a non-empty JSON object post-Plan-02; got {defs!r}"
    )
    required_defs = {"v0_1", "category"}
    missing = required_defs - set(defs.keys())
    assert not missing, (
        f"$defs missing required entries after Plan 02: {sorted(missing)}"
    )

    # Well-formedness: each entry is a dict and declares a shape keyword.
    for name, subschema in defs.items():
        assert isinstance(subschema, dict), (
            f"$defs/{name} must be a JSON object, "
            f"got {type(subschema).__name__}"
        )
        declared = _SHAPE_KEYWORDS.intersection(subschema.keys())
        assert declared, (
            f"$defs/{name} must declare at least one shape keyword "
            f"({sorted(_SHAPE_KEYWORDS)}); got keys {sorted(subschema.keys())}"
        )

    # Reachability: every entry name must be referenced somewhere in the
    # schema tree via `#/$defs/<name>`.
    refs = set()
    _collect_refs(schema, refs)
    reachable = {
        r.split("/")[-1]
        for r in refs
        if r.startswith("#/$defs/")
    }
    unreachable = set(defs.keys()) - reachable
    assert not unreachable, (
        f"Unreachable $defs (not referenced by any $ref): {sorted(unreachable)}"
    )


@pytest.mark.parametrize(
    "recipe_path",
    RECIPE_FILES,
    ids=lambda p: p.stem,
)
def test_all_committed_recipes_validate_against_schema(recipe_path):
    """D-10.3: every recipe in `recipes/*.yaml` lints clean.

    Intentionally duplicates `test_recipe_regression.py` — Phase 18 D-10
    requires this check live inside the self-check module so the full D-10
    contract is legible in one file. When a future schema change tightens a
    rule, this file fires the same alarm as the stand-alone regression test.
    """
    recipe = load_recipe(recipe_path)
    errors = lint_recipe(recipe)
    assert errors == [], f"Lint errors in {recipe_path.name}: {errors}"
