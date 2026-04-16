#!/usr/bin/env python3
"""ONE-SHOT migration: add {category, detail} to every cell across the 5
committed recipes per D-04. Idempotent via setdefault. Commit the result,
then delete this script.

Usage: python3 scripts/migrate_recipes_phase10.py
(run from repo root)
"""
from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

# ruamel YAML configuration — MUST be byte-identical to tools/run_recipe.py
# lines 27-39 so that the round-trip write-back preserves every byte not
# touched by the migration (test_roundtrip.py asserts byte-identity).
_yaml = YAML(typ="rt")
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)


def _represent_none(dumper, _data):
    return dumper.represent_scalar("tag:yaml.org,2002:null", "null")


_yaml.representer.add_representer(type(None), _represent_none)


def migrate(recipe_path: Path) -> None:
    """Add category+detail to every verified_cells[] and known_incompatible_cells[]
    entry in recipe_path, applying the D-04 STOCHASTIC→ASSERT_FAIL mapping to
    the single hermes × gemini-2.5-flash cell. Idempotent: second run is a no-op.
    """
    data = _yaml.load(recipe_path.read_text())
    smoke = data.get("smoke", {}) or {}

    # verified_cells[]: every cell in the 5 committed recipes is currently
    # verdict=PASS, so category=PASS and detail="". The OR branch is defensive
    # in case a future migration re-runs against a recipe that already has a
    # non-PASS verified cell.
    for cell in smoke.get("verified_cells", []) or []:
        if cell.get("verdict") == "PASS":
            cell.setdefault("category", "PASS")
        else:
            cell.setdefault("category", "ASSERT_FAIL")
        cell.setdefault("detail", "")

    # known_incompatible_cells[]: two branches per D-04.
    #   - STOCHASTIC cell (only hermes × gemini-2.5-flash today): remap
    #     verdict→FAIL, category=ASSERT_FAIL (temporary — Phase 15 restores
    #     true STOCHASTIC semantics), detail="flapping verdict — see notes".
    #   - Typical FAIL cell (e.g. openclaw × gpt-4o-mini): category=ASSERT_FAIL,
    #     detail derived from the first sentence of notes (truncated to 120
    #     chars) so we surface a human-readable reason without re-logging the
    #     full notes block.
    for cell in smoke.get("known_incompatible_cells", []) or []:
        if cell.get("verdict") == "STOCHASTIC":
            cell["verdict"] = "FAIL"
            cell.setdefault("category", "ASSERT_FAIL")
            cell.setdefault("detail", "flapping verdict — see notes")
        else:
            cell.setdefault("category", "ASSERT_FAIL")
            notes = cell.get("notes", "") or ""
            derived = notes.split(".", 1)[0].strip()[:120] if notes else ""
            cell.setdefault("detail", derived)

    with recipe_path.open("w") as f:
        _yaml.dump(data, f)


if __name__ == "__main__":
    for p in sorted(Path("recipes").glob("*.yaml")):
        print(f"migrating {p.name}")
        migrate(p)
