---
phase: 18-schema-maturity
plan: 02
subsystem: schema
tags: [json-schema, defs, oneOf, ref, enum, bounds, annotations, versioning-seam, wr-05]

requires:
  - phase: 18-schema-maturity
    plan: 01
    provides: "test_schema_selfcheck.py conditional Test 2 — vacuously passes pre-refactor, activates the moment `$defs` is introduced with at least one entry"
  - phase: 10-error-taxonomy-timeout-enforcement
    provides: "11-value category enum baseline (PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL, PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL, INFRA_FAIL, STOCHASTIC, SKIP) preserved verbatim in the extraction"
provides:
  - "`$defs.v0_1` — wraps the full ap.recipe/v0.1 body, referenced via oneOf discriminator on apiVersion"
  - "`$defs.category` — canonical 11-value enum, referenced from both verified_cells.items.category and known_incompatible_cells.items.category"
  - "oneOf seam on root — v0.2 can land by appending `$defs/v0_2` + a second branch; no wire-format break"
  - "WR-05 closed: known_incompatible_cells[].verdict is now enum [PASS, FAIL]"
  - "Bounds hardening — source.ref allowlist pattern, name maxLength 64, timeout maxima (3600/10800/1800), owner_uid full uid_t range"
  - "annotations open-object escape valve on 7 subschemas — forward-compat for recon fields without weakening additionalProperties:false"
  - "metadata.license + metadata.maintainer — optional in v0.1.1, groundwork for required-at-external-contribution (phase 19+)"
affects: [18-03-spec-sync, phase-19-api-foundation]

tech-stack:
  added: []
  patterns:
    - "JSON Schema oneOf+$ref discriminator as a versioning seam (Kubernetes CRD / OpenAPI idiom)"
    - "$defs extraction for duplicated enums — reference once, change once"
    - "Open-object `annotations` extension point (OpenAPI x-* / Kubernetes annotations pattern) co-existing with strict `additionalProperties: false` parents"
    - "Optional-today-required-later for metadata.license + metadata.maintainer"

key-files:
  created: []
  modified:
    - tools/ap.recipe.schema.json

key-decisions:
  - "Kept `$id` at `https://agentplayground.dev/schemas/ap.recipe.v0.1.json` per CONTEXT 'Claude's Discretion' — nothing functional depends on the filename label; the v0.1.1 bump is semantic and belongs in title/description plus the Plan 03 markdown."
  - "Placed $defs.category before $defs.v0_1 so the category definition is physically earlier in the file than its referencing `$ref` — cosmetic but aids diff readability for future JSON-Schema-aware readers."
  - "annotations escape valve is added as a sibling property, never appended to the parent `required[]` — the parent's strict `additionalProperties: false` is preserved and only the annotations subtree is open."
  - "known_incompatible_cells.verdict enum was set to [PASS, FAIL] in the SAME order as verified_cells.verdict — the hermes recipe's single entry value `FAIL` is accepted unchanged."

patterns-established:
  - "Versioned JSON Schema via $defs + oneOf discriminator — replicate for future wire-level bumps"
  - "Single $defs home for cross-referenced enums — category is the first example; future candidates: pass_if verbs, verdict"
  - "Annotations are declaratively-open-by-design; redaction and privacy are runner-layer responsibilities, not schema-layer"

requirements-completed: [D-01, D-02, D-03, D-04, D-05, D-06, D-07, D-08, D-09]

duration: ~3min
completed: 2026-04-16
---

# Phase 18 Plan 02: Schema Refactor to v0.1.1 Summary

**Refactored `tools/ap.recipe.schema.json` into a versioned-seam shape (root oneOf → `$defs.v0_1`), extracted the 11-value category enum to `$defs.category`, tightened bounds on `source.ref`, `name`, `timeout_s`, `clone_timeout_s`, and `owner_uid`, closed WR-05 on `known_incompatible_cells.verdict`, added the `annotations` open-object escape valve on 7 subschemas, and introduced optional `metadata.license` + `metadata.maintainer` — all in a single additive JSON file change. Zero recipe edits. Zero runner edits. Plan 01's Test 2 flipped from vacuous-pass to load-bearing-pass.**

## Performance

- **Duration:** ~3 min wall-clock (read-context + single Write pass + verification + commit)
- **Started:** 2026-04-16T22:35:53Z
- **Completed:** 2026-04-16T22:38:42Z
- **Tasks:** 1 (of 1 in this plan)
- **Files modified:** 1 modified, 0 created

## Accomplishments

### Structural refactor (D-01, D-02)

- Root shape is now: `$schema`, `$id`, `title` (bumped to v0.1.1), `description`, `type: object`, `oneOf: [{"$ref": "#/$defs/v0_1"}]`, `$defs: {category, v0_1}`.
- `$defs.v0_1` holds the entire prior body verbatim: `type`, `required`, `additionalProperties: false`, `properties`, `allOf` (5 if/then blocks). The apiVersion `const: "ap.recipe/v0.1"` stays inside `v0_1.properties.apiVersion`, which is what makes the oneOf work as a discriminator when v0.2 lands later.
- `$defs.category` holds the 11-value enum once, referenced from both cell sites via `{"$ref": "#/$defs/category"}`. Before: 22 lines of duplicated enum prose in two places. After: one canonical definition.

### WR-05 closed (D-03)

- `$defs.v0_1.properties.smoke.properties.known_incompatible_cells.items.properties.verdict` was previously `{"type": "string"}` (unconstrained — any typo like `"FAL"` or `"pass"` passed silently). Now `{"type": "string", "enum": ["PASS", "FAIL"], "description": "Documented verdict."}` — matches `verified_cells.items.verdict` exactly.
- Regression-gate verified: hermes is the only recipe with a `known_incompatible_cells[]` entry; its verdict value is `"FAIL"`, which is accepted by the tightened enum.

### Bounds hardening (D-04, D-05, D-06, D-07)

- **D-04 `source.ref`** — added `"pattern": "^[a-zA-Z0-9._/-]{1,255}$"` alongside existing type/description. Allowlist defends against `git fetch` option-as-value injection (`--upload-pack=<cmd>` etc.). All 5 existing refs pass: `main` (4 recipes), `19142810edfd2d3dbe947692732b868d57b9a18e` (hermes).
- **D-05 `name`** — added `"maxLength": 64` alongside existing `pattern: "^[a-z0-9_-]+$"`. All 5 names (hermes, openclaw, picoclaw, nullclaw, nanobot) are ≤ 8 chars, well under 64.
- **D-06 timeout bounds** — `smoke.timeout_s.maximum: 3600`, `build.timeout_s.maximum: 10800`, `build.clone_timeout_s.maximum: 1800`. `minimum: 1` preserved on all three. Existing 5 recipes use smoke `timeout_s` values 60/90/90/180/90 — all ≤ 3600. `build.timeout_s` and `build.clone_timeout_s` are absent from all 5 — zero regression risk.
- **D-07 `owner_uid`** — added `"minimum": 0, "maximum": 4294967295` (full Linux uid_t range). Updated description to note values > 65535 typically indicate userns-remap. Existing UIDs: 0, 1000, 10000, 65534 — all in range.

### Annotations escape valve (D-08)

Added `annotations` subschema — `{"type": "object", "additionalProperties": true, "description": "Open extension point ..."}` — as an OPTIONAL sibling property on exactly 7 subschemas:

1. `$defs.v0_1.properties.build.properties.annotations`
2. `$defs.v0_1.properties.runtime.properties.annotations`
3. `$defs.v0_1.properties.invoke.properties.annotations`
4. `$defs.v0_1.properties.smoke.properties.annotations`
5. `$defs.v0_1.properties.metadata.properties.annotations`
6. `$defs.v0_1.properties.smoke.properties.verified_cells.items.properties.annotations`
7. `$defs.v0_1.properties.smoke.properties.known_incompatible_cells.items.properties.annotations`

Nowhere is `annotations` added to any parent's `required[]`. All parent `additionalProperties: false` settings are preserved — the open-ness is scoped to the annotations subtree only. `build.observed` was left intact for back-compat (Plan 03's markdown documents its soft-deprecation in favor of `build.annotations`).

### D-09 license + maintainer (optional)

Added to `$defs.v0_1.properties.metadata.properties`:

- `license`: `{"type": "string", "description": "SPDX identifier convention..."}` — string, free-form but convention-documented.
- `maintainer`: `{"type": "object", "additionalProperties": false, "properties": {"name": {...}, "url": {"format": "uri"}}}` — matches CONTEXT D-09 shape exactly.

Neither is added to `metadata.required`. The existing `"required": ["recon_date", "recon_by", "source_citations"]` is preserved unchanged. All 5 existing recipes omit both fields and continue to validate.

## Structural Diff Summary

- Root refactored — 2 `$defs` added.
- 7 annotations sites added.
- 1 verdict enum tightened (WR-05).
- 1 ref pattern added (source.ref).
- 1 name maxLength added.
- 3 timeout maxima added (smoke.timeout_s, build.timeout_s, build.clone_timeout_s).
- 2 owner_uid bounds added (minimum 0, maximum 4294967295).
- 2 `$ref` replacements for category (inside each cell type's items.properties.category).
- 2 metadata optional fields added (license, maintainer).
- 1 `oneOf` discriminator seam added at root.

Line count: 562 → 623 (+61 lines, all additive).

## Verification Results

### Plan 01 Test 2 activation (the central correctness claim)

Before Plan 02: `$defs` absent → `test_defs_are_well_formed_and_reachable` returned vacuously (early-return guard).

After Plan 02:
- `$defs` keys: `['category', 'v0_1']` (non-empty, both entries well-formed)
- `v0_1` shape keywords present: `type`, `allOf`
- `category` shape keywords present: `type`, `enum`
- `$ref`s collected from schema tree: `['#/$defs/category', '#/$defs/v0_1']`
- Reachable defs: `{'category', 'v0_1'}`
- Unreachable defs: `∅` (empty — no orphans)

Test 2 now actively enforces the contract on every run.

### Full test suite

- `pytest tools/tests/test_schema_selfcheck.py -v` → 7 passed (1 meta-schema + 1 conditional $defs + 5 recipe parametrized).
- `pytest tools/tests/test_lint.py tools/tests/test_recipe_regression.py tools/tests/test_roundtrip.py -x -q` → 30 passed.
- `pytest tools/tests/ -q` → 162 passed, 2 deselected (Docker integration — environment-gated).

### Regression gate (non-negotiable)

- `python3 tools/run_recipe.py --lint-all` → 5/5 PASS (hermes, nanobot, nullclaw, openclaw, picoclaw), exit code 0.
- `git diff recipes/` → empty (zero recipe edits).
- `git diff tools/run_recipe.py` → empty (zero runner edits).
- `git diff docs/RECIPE-SCHEMA.md` → empty (markdown spec is Plan 03's scope).

### Grep landmarks

- `grep -c '#/\$defs/category' tools/ap.recipe.schema.json` → 2 (verified_cells.items + known_incompatible_cells.items).
- `grep -c '"annotations"' tools/ap.recipe.schema.json` → 7 (the 7 escape-valve sites; description strings reuse the single canonical phrase but do not count because they are string values, not object keys).

## Task Commits

1. **Task 1: Refactor schema — oneOf/defs seam, category extraction, WR-05 verdict enum, source.ref pattern, name maxLength, timeout bounds, owner_uid bounds, annotations on 7 subschemas, license + maintainer optional** — `0f31b79` (feat)

_Single commit — the plan's `<action>` block explicitly called for "ONE editor pass so intermediate states never commit." Done exactly that._

## Files Created/Modified

- `tools/ap.recipe.schema.json` — refactored (623 lines; +527 insertions, −466 deletions per git stat; reflects the structural rearrangement, not net new content).

## Decisions Made

- **`$id` kept at v0.1.json path** (CONTEXT Claude's Discretion). Filename label is cosmetic; the version bump to v0.1.1 lives in `title` + `description` + (Plan 03) markdown spec. This keeps external consumers that pinned the $id URL (none today, but the pattern matters) from breaking on an additive change.
- **`$defs.category` physically before `$defs.v0_1`** in file order. JSON object key order is not semantic in JSON Schema, but human diff readers benefit from seeing the smaller definition first, then the larger one that references it.
- **Single-Write refactor approach.** The plan's `<action>` mandated a single coherent write to avoid committing intermediate states. Implemented via one `Write` tool invocation replacing the whole file, followed by a single commit.

## Deviations from Plan

None.

The plan's `<action>` block was highly prescriptive (exact target shape, step-by-step Step A–Step I) and every decision was locked in CONTEXT D-01..D-09. The refactor matched it byte-for-byte on shape. The one "Claude's Discretion" choice called out in CONTEXT (`$id` filename label) was exercised by keeping the existing URL, which is also what the plan body explicitly advised.

## Issues Encountered

None. JSON parsed first try, all 7 self-check cells passed first try, all 30 pre-existing tests passed first try, all 162 full-suite tests passed first try, `--lint-all` returned 5/5 PASS first try.

## User Setup Required

None — this plan is a pure schema-file edit with no external service, no infrastructure change, and no environment configuration. All verification is pytest-only.

## Next Phase Readiness

- **Plan 03 (markdown spec sync — `docs/RECIPE-SCHEMA.md`)** is unblocked. The authoritative JSON Schema is at v0.1.1 shape; Plan 03's scope is updating the narrative spec to match (new `oneOf` versioning section, category `$defs` reference, bounds, annotations escape valve, license/maintainer optional-today advisory).
- **Phase 19 (API Foundation)** has a stable, auditable, extensible contract to serve — the oneOf seam means v0.2 can land later without breaking the HTTP/JSON wire shape.
- No blockers, no deferred items.

## TDD Gate Compliance

Plan frontmatter declares `type: execute`. The single task is not marked `tdd="true"` — this is a schema refactor, not a TDD cycle. The RED/GREEN gate is owned by Plan 01 (`test_schema_selfcheck.py` exists on disk in test form at `098bc61`, written RED-equivalent by Plan 01). This plan's GREEN transition is embodied in commit `0f31b79` — after this commit, Test 2 in `test_schema_selfcheck.py` activates from vacuous-true to meaningfully-enforcing. Equivalent to the feat-follows-test pattern at the phase level.

## Self-Check: PASSED

- [x] `tools/ap.recipe.schema.json` exists and is valid JSON (623 lines) — verified via `python3 -c "import json; json.load(...)"`.
- [x] Commit `0f31b79` exists on branch — verified via `git rev-parse HEAD` (and git log --oneline).
- [x] Schema has `oneOf: [{"$ref": "#/$defs/v0_1"}]` at root — verified via python structural assertion.
- [x] `$defs.v0_1` holds the body (type, required, additionalProperties, properties, allOf) — verified.
- [x] `$defs.category` holds the 11-value enum in canonical order — verified.
- [x] `#/$defs/category` referenced exactly 2 times (verified_cells + known_incompatible_cells) — verified via grep -c.
- [x] `$defs` reachability check: both entries reachable, zero orphans — verified via `_collect_refs` walk.
- [x] `known_incompatible_cells.items.verdict` has `enum: ["PASS", "FAIL"]` (WR-05 closed) — verified.
- [x] `source.ref.pattern: "^[a-zA-Z0-9._/-]{1,255}$"` — verified.
- [x] `name.maxLength: 64` — verified.
- [x] `smoke.timeout_s.maximum: 3600` — verified.
- [x] `build.timeout_s.maximum: 10800` — verified.
- [x] `build.clone_timeout_s.maximum: 1800` — verified.
- [x] `volumes[].owner_uid.minimum: 0, maximum: 4294967295` — verified.
- [x] `annotations` on exactly 7 sites, each with `type: object` + `additionalProperties: true` — verified via python walk.
- [x] `annotations` NOT in any required array — verified via tree walk.
- [x] `metadata.license` + `metadata.maintainer` present as optional (not in `metadata.required`) — verified.
- [x] Plan 01 Test 2 meaningfully-passing: 7/7 cells in `test_schema_selfcheck.py` green — verified.
- [x] Pre-existing suites green: `test_lint.py` + `test_recipe_regression.py` + `test_roundtrip.py` = 30 passed — verified.
- [x] Full pytest suite green: 162 passed, 2 deselected (Docker integration) — verified.
- [x] Regression gate: `python3 tools/run_recipe.py --lint-all` returns 5/5 PASS, rc=0 — verified.
- [x] `git diff recipes/` empty — verified.
- [x] `git diff tools/run_recipe.py` empty — verified.
- [x] `git diff docs/` empty — verified.

---
*Phase: 18-schema-maturity*
*Plan: 02*
*Completed: 2026-04-16*
