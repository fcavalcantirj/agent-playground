---
status: complete
phase: 09-spec-lint-test-harness-foundations
source: [09-01-SUMMARY.md, 09-02-SUMMARY.md, 09-03-SUMMARY.md, 09-04-SUMMARY.md]
started: 2026-04-16T00:00:00Z
updated: 2026-04-16T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. End-to-end — make check
expected: `make check` runs lint-recipes (all 5 recipes print green PASS) then pytest (48 passed in ~1s), exits 0
result: pass

### 2. Lint exit code contract — broken recipe returns 2 (not 1)
expected: `python3 tools/run_recipe.py --lint tools/tests/broken_recipes/missing_api_version.yaml` prints red FAIL with schema error citing apiVersion, exits with code 2 (distinct from runtime exit 1)
result: pass
notes: |
  First run surfaced duplicate error messages (root cause: redundant `required` arrays in
  two `allOf` branches restating top-level required fields; vacuous-if fired both branches
  when `build.mode` was absent). Investigation confirmed by 4 independent agents
  (spec analyst, empirical prober, archaeologist, adversarial skeptic). Three schema
  improvements shipped as hardening: (1) stripped redundant required from upstream_dockerfile
  branch, (2) stripped redundant required from image_pull branch, (3) guarded all 5 `if`
  clauses with `required` so they only fire when gating keys are actually present.
  Test harness gained a `len(errors) == len(set(errors))` assertion that caught bug #2
  immediately after being added.

### 3. All 5 recipes bumped to ap.recipe/v0.1
expected: `grep -l "apiVersion: ap.recipe/v0.1" recipes/*.yaml` returns all 5 files (hermes, openclaw, picoclaw, nullclaw, nanobot)
result: pass

### 4. Python package is pip-installable
expected: `pip install -e "tools/[dev]"` completes successfully and installs jsonschema, ruamel.yaml, pytest into the active environment
result: pass

### 5. CI workflow exists with correct wiring
expected: `.github/workflows/test-recipes.yml` exists, triggers on push/PR to main with paths filter (tools/**, recipes/**, docs/RECIPE-SCHEMA.md), uses Python 3.12, runs `make install-tools && make check`
result: pass

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0

## Gaps

[none — 3 schema quality improvements shipped during verification as hardening, all 48 tests green]
