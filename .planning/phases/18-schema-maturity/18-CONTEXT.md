---
phase: 18-schema-maturity
status: ready_for_planning
gathered: 2026-04-16
source: 4-agent confirmation synthesis (schema-critique agent) + prior Phase 10 review
---

# Phase 18: Schema Maturity v0.1.1 — Context

## Phase Boundary

Close concrete gaps in `tools/ap.recipe.schema.json` + `docs/RECIPE-SCHEMA.md` to make the recipe spec mature enough to serve as the API contract for Phase 19. **No wire-format break.** All 5 committed recipes (`hermes`, `openclaw`, `picoclaw`, `nullclaw`, `nanobot`) must continue to pass lint unchanged after this phase. Current `apiVersion: ap.recipe/v0.1` value stays — this is a v0.1.1 tightening, not a v0.2 bump.

## Implementation Decisions (locked)

### D-01: Versioning evolution mechanism
- **IN scope:** Refactor schema to use `oneOf` with `apiVersion` discriminator structure, even though only v0.1 is defined today. Shape the seam so v0.2 (future Phase 13 / SHA-pinning) can land without a schema-file break.
- Specifically: replace `"apiVersion": {"const": "ap.recipe/v0.1"}` with a `oneOf: [{$ref: "#/$defs/v0_1"}]` discriminator on the top-level `apiVersion` field.
- `$defs/v0_1` holds the current full body (all required/properties/allOf rules).
- The JSON Schema file validates itself against the draft-2020-12 meta-schema in CI.

### D-02: Category enum factoring
- Extract the 11-value category enum (currently duplicated inline in `verified_cells.items.category` AND `known_incompatible_cells.items.category`) to `$defs.category`.
- Both cell types reference `$ref: "#/$defs/category"`.
- No behavioral change; diff should be mechanical.

### D-03: Fix `known_incompatible_cells[].verdict` enum
- Currently `"type": "string"` (unconstrained). Change to `"enum": ["PASS", "FAIL"]` matching `verified_cells[].verdict`.
- Was flagged as WR-05 in `10-REVIEW.md`. Typos currently pass lint silently.
- **Verification:** the one hermes `known_incompatible_cells[0]` row with `verdict: "FAIL"` (post-Phase 10 STOCHASTIC→FAIL remap) must still lint clean.

### D-04: `source.ref` allowlist pattern (not denylist)
- Add `"pattern": "^[a-zA-Z0-9._/-]{1,255}$"` to `source.ref`.
- Allowlist, not denylist — a denylist of shell-injection chars cannot defend against `git fetch`'s accepted `--upload-pack=<cmd>` option-as-value attacks; an allowlist of plain ref characters does.
- Verified against all 5 current recipes' `source.ref` values — none break.

### D-05: `name` length bound
- Add `"maxLength": 64` + keep existing `"pattern": "^[a-z0-9_-]+$"`.
- Used as image-tag suffix (`ap-recipe-<name>`); Docker tag limit is 128 chars, leaving headroom for prefix.

### D-06: `timeout_s` field bounds — differentiated
- `smoke.timeout_s`: `maximum: 3600` (1h — smoke should not run longer than a human attention span).
- `build.timeout_s`: `maximum: 10800` (3h — hermes + openclaw cold builds routinely exceed 15min; schema must accommodate).
- `build.clone_timeout_s`: `maximum: 1800` (30min — large repos).
- `minimum: 1` on all (already present).

### D-07: `volumes[].owner_uid` bound correction
- Previous proposal capped at 65535 — WRONG. Linux `uid_t` is 32-bit unsigned; userns-remapped containers routinely use UIDs ≥ 100000.
- Set `minimum: 0, maximum: 4294967295` (full `uid_t` range).
- Document in spec that values > 65535 typically indicate userns-remap.

### D-08: Extensibility escape valve (`annotations` reserve points)
- Add `"annotations": {"type": "object", "additionalProperties": true}` as optional sibling on each of: `build`, `runtime`, `invoke`, `smoke`, `metadata`, AND inside `verified_cells[].items` AND `known_incompatible_cells[].items`.
- Pattern: strict known shape + explicit extension point. Matches OpenAPI `x-*`, Kubernetes `annotations`, MCP `meta`.
- Without this, every recon observation (`build.observed` today) fights the schema's `additionalProperties: false`.
- `build.observed` itself stays (back-compat) but docs note it is deprecated in favor of `build.annotations` for new recipes.

### D-09: `metadata.license` + `metadata.maintainer` — ADDED but OPTIONAL in v0.1.1
- Both fields added to schema as optional (NOT required) for backward compat with existing 5 recipes.
- Spec documents them as "required before external contribution lands" (phase 19+).
- Optional-today-required-later is the mature pattern; prevents the 5 existing recipes from becoming invalid.
- `license`: `{"type": "string"}` — SPDX identifier convention documented in spec.
- `maintainer`: `{"type": "object", "properties": {"name": {"type": "string"}, "url": {"type": "string", "format": "uri"}}, "additionalProperties": false}`.

### D-10: Self-validation gate
- Add `tools/tests/test_schema_selfcheck.py` with 3 tests:
  1. The schema file itself validates against JSON Schema draft-2020-12 meta-schema.
  2. Each `$defs/*` subschema is well-formed and reachable.
  3. All 5 committed recipes validate against the new schema (regression gate).
- CI-grade gate — not aspirational, must run in default pytest suite.

### D-11: Markdown spec update
- `docs/RECIPE-SCHEMA.md` updated to match: new `oneOf` versioning section, category `$defs` reference, bounds documented, annotations escape valve section, license/maintainer optional-today advisory.
- The markdown spec stays narrative; the JSON Schema is authoritative.

## Out of scope (explicitly deferred)

Per 4-agent critique the following mature-schema items are deferred to later phases — surfaced here so future planners know they are KNOWN gaps, not oversights:

- **Capability advertisement block** (MCP-style `capabilities.{streaming, trajectories, multi_turn}`) — deferred to Phase 22 or later.
- **`runtime.limits`** with token/turn/cost budgets — today smuggled into `argv` (hermes `--max-turns 30`). Deferred to Phase 23.
- **GPU / hardware declaration** (`build.gpu`, `build.cuda`) — first GPU-requiring backlog agent triggers it.
- **Collapse 3 `known_*` arrays → `known_issues[]`** with typed discriminator — shape change, deferred to v0.2 Phase.
- **Richer `verified_cells[]`** with `probe_id`, typed metrics (`tokens_in/out`, `cost_usd`), env fingerprint — deferred to Phase 24.
- **Making `license` + `maintainer` required** — flips optional→required when external contribution lands, not today.

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Prior review
- `.planning/phases/10-error-taxonomy-timeout-enforcement/10-REVIEW.md` — WR-05 (verdict enum gap), other schema findings

### Current state of schema + spec + recipes
- `tools/ap.recipe.schema.json` — JSON Schema to be tightened
- `docs/RECIPE-SCHEMA.md` — narrative spec, must stay in sync
- `recipes/hermes.yaml`, `recipes/openclaw.yaml`, `recipes/picoclaw.yaml`, `recipes/nullclaw.yaml`, `recipes/nanobot.yaml` — the regression gate

### Existing test infrastructure
- `tools/tests/test_lint.py` — schema lint tests
- `tools/tests/test_recipe_regression.py` — 5-recipe regression
- `tools/tests/conftest.py` — fixtures including `minimal_valid_recipe`

### JSON Schema reference
- Draft 2020-12: https://json-schema.org/draft/2020-12
- Kubernetes `oneOf` + discriminator pattern: k8s CRD schemas
- OpenAPI `x-*` extensions pattern: openapi-spec v3.1

## Critical Sequencing Constraint

This phase is a SINGLE schema tightening pass — no migration needed because:
1. All proposed changes are either additive (D-01 `oneOf` wrapping, D-08 annotations, D-09 license/maintainer optional) OR
2. Enum-tightening where all 5 existing recipes already match (D-03 verdict enum, D-04 ref pattern, D-06/D-07 bounds).

**No recipe file needs to change.** This is the Phase 10 "CRITICAL SEQUENCING CONSTRAINT" scheme applied in miniature — the tightened schema must accept all 5 existing recipes unchanged as its regression gate.

## Success Criteria (what must be TRUE after phase)

1. `tools/ap.recipe.schema.json` structure refactored to D-01 through D-09.
2. `docs/RECIPE-SCHEMA.md` narrative updated.
3. `tools/tests/test_schema_selfcheck.py` added — validates schema against meta-schema + all 5 recipes.
4. `pytest -q` (default suite, excludes integration) returns all tests passing.
5. `./tools/run_recipe.py --lint-all` returns PASS on all 5 recipes with zero edits to those files.
6. `grep` count matches expected: `$defs.category` referenced from both cell types, `$defs.v0_1` wraps the body, `annotations` reserve field on ≥5 subschemas.
7. Zero changes to runner code (Python in `tools/run_recipe.py`) — schema-layer only.

## Claude's Discretion

- How to organize `$defs` (flat namespace OK; one-level grouping OK — planner's call).
- Precise wording of the markdown spec updates.
- Whether to bump minor version label in `$id` (`.../ap.recipe.v0.1.1.json`) or keep `.v0.1.json` (planner's call — affects nothing functional).
- Precise regex form for `source.ref` allowlist as long as it accepts all 5 existing refs.

---

*Phase: 18-schema-maturity*
*Context written: 2026-04-16 directly from 4-agent synthesis (no separate research round — the 4-agent critique absorbed that work)*
