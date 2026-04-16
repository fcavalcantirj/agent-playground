---
phase: 18-schema-maturity
verified: 2026-04-16T23:00:00Z
status: passed
score: 11/11
overrides_applied: 0
---

# Phase 18: Schema Maturity v0.1.1 — Verification Report

**Phase Goal:** Close concrete gaps in `tools/ap.recipe.schema.json` + `docs/RECIPE-SCHEMA.md` to make the recipe spec mature enough to serve as the API contract for Phase 19. No wire-format break — all 5 committed recipes continue to lint-pass unchanged.
**Verified:** 2026-04-16T23:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification.

---

## Goal Achievement

### Observable Truths (D-01 through D-11)

| # | Decision | Truth | Status | Evidence |
|---|----------|-------|--------|----------|
| 1 | D-01 | `$defs.v0_1` wraps the full body; root discriminates via `$ref` (WR-01 fix applied — NOT oneOf with single branch) | VERIFIED | Schema line 7: `"$ref": "#/$defs/v0_1"`. Schema `$comment` line 8 explicitly documents why `$ref` is used instead of `oneOf`: "WR-01 — oneOf with a single branch collapses inner errors into an opaque top-level message". `$defs.v0_1` holds `type`, `required`, `additionalProperties`, `properties`, `allOf`. |
| 2 | D-02 | `$defs.category` holds the 11-value enum; referenced from both `verified_cells.items.category` AND `known_incompatible_cells.items.category` | VERIFIED | `grep -c '#/$defs/category'` = 2. Python check confirmed `verified_cells.items.properties.category == {"$ref": "#/$defs/category"}` and `known_incompatible_cells.items.properties.category == {"$ref": "#/$defs/category"}`. |
| 3 | D-03 | `known_incompatible_cells.items.verdict` is `enum: ["PASS", "FAIL"]` (WR-05 closed) | VERIFIED | Schema confirms: `{"type": "string", "enum": ["PASS", "FAIL"], "description": "Documented verdict."}`. Hermes's single `known_incompatible_cells` entry uses `verdict: "FAIL"` — accepted by the enum, regression gate green. |
| 4 | D-04 | `source.ref` has `pattern: ^[a-zA-Z0-9._/-]{1,255}$` | VERIFIED | Schema `source.ref.pattern` = `"^[a-zA-Z0-9._/-]{1,255}$"`. All 5 recipe refs pass: `main` (4 recipes), `19142810edfd2d3dbe947692732b868d57b9a18e` (hermes). |
| 5 | D-05 | `name` has `maxLength: 64` | VERIFIED | Schema `name.maxLength = 64` confirmed. All 5 names are 8 chars or fewer. |
| 6 | D-06 | `smoke.timeout_s` max 3600, `build.timeout_s` max 10800, `build.clone_timeout_s` max 1800, `minimum: 1` preserved | VERIFIED | `smoke.timeout_s.maximum = 3600`, `build.timeout_s.maximum = 10800`, `build.clone_timeout_s.maximum = 1800`. All three have `minimum: 1`. |
| 7 | D-07 | `volumes[].owner_uid` has `minimum: 0, maximum: 4294967295` (full `uid_t` range) | VERIFIED | `owner_uid.minimum = 0, owner_uid.maximum = 4294967295`. Description notes values > 65535 typically indicate userns-remap. |
| 8 | D-08 | `annotations` open-object on exactly 7 subschemas: build, runtime, invoke, smoke, metadata, verified_cells.items, known_incompatible_cells.items | VERIFIED | All 7 sites confirmed with `additionalProperties: true`. None added to any `required` array. Parent `additionalProperties: false` preserved everywhere else. |
| 9 | D-09 | `metadata.license` (string) and `metadata.maintainer` (object with `required: ["name"]`) added as OPTIONAL; NOT in `metadata.required` | VERIFIED | `license` is `{type: string}`. `maintainer` has `required: ["name"]` inside the object (WR-02 fix applied), `additionalProperties: false`. `metadata.required` = `["recon_date", "recon_by", "source_citations"]` — unchanged. |
| 10 | D-10 | `tools/tests/test_schema_selfcheck.py` exists with 3 tests: meta-schema validation, `$defs` well-formedness+reachability (load-bearing after Plan 02), 5-recipe regression | VERIFIED | File is 144 lines. Contains `Draft202012Validator`, `check_schema`, `$defs`, reachability walk, `RECIPE_FILES`. All 7 pytest cells pass: `7 passed in 0.96s`. Test 2 now load-bearing (asserts `v0_1` and `category` must be present). |
| 11 | D-11 | `docs/RECIPE-SCHEMA.md` narrative updated to v0.1.1: oneOf seam explained in §10.1, annotations in §11, bounds documented, license/maintainer advisory, JSON Schema is authoritative | VERIFIED | H1 says `ap.recipe/v0.1.1`. Precedence rule present. New §10.1 Versioning seam. New §11 Annotations escape valve. All bound documentation present (3600, 10800, 1800, 4294967295, allowlist pattern, maxLength 64). |

**Score: 11/11 truths verified**

---

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `tools/ap.recipe.schema.json` | VERIFIED | 623 lines. Valid JSON. Root: `$schema`, `$id`, `title` (v0.1.1), `description`, `type: object`, `$ref: #/$defs/v0_1`, `$comment` (WR-01 note), `$defs: {category, v0_1}`. |
| `tools/tests/test_schema_selfcheck.py` | VERIFIED | 144 lines. Contains all 3 tests + `_collect_refs` helper. 7/7 pytest cells pass. |
| `docs/RECIPE-SCHEMA.md` | VERIFIED | 335 lines. H1 bumped to v0.1.1. Version policy blockquote + precedence rule. New §10.1, §11. 8 inline section updates. |

---

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|---------|
| Schema root | `$defs.v0_1` | `$ref: "#/$defs/v0_1"` | WIRED | Line 7 of schema; `$defs.v0_1` exists and is non-empty |
| `verified_cells.items.category` | `$defs.category` | `$ref: "#/$defs/category"` | WIRED | Confirmed via Python assertion |
| `known_incompatible_cells.items.category` | `$defs.category` | `$ref: "#/$defs/category"` | WIRED | Confirmed via Python assertion; grep count = 2 |
| `test_schema_selfcheck.py` | `tools/ap.recipe.schema.json` | `json.load + Draft202012Validator.check_schema` | WIRED | File imports and uses schema path; 7/7 tests pass |
| `test_schema_selfcheck.py` | `recipes/*.yaml` | `parametrize over RECIPE_FILES + lint_recipe` | WIRED | RECIPE_FILES = `sorted(RECIPE_DIR.glob("*.yaml"))` |

---

### D-01 Clarification: `$ref` vs `oneOf` — WR-01 Fix Confirmed

The CONTEXT.md and 18-02-PLAN.md specified `oneOf: [{"$ref": "#/$defs/v0_1"}]`. The implementation uses `"$ref": "#/$defs/v0_1"` at the root instead. This is a correct intentional deviation:

- **Why:** The REVIEW (WR-01) identified that a single-branch `oneOf` collapses all inner validation errors into an opaque top-level message, making lint diagnostics useless for operators. A direct `$ref` at the root is semantically equivalent but preserves deep error paths.
- **Evidence:** Schema `$comment` at line 8 documents this exact reasoning verbatim. The verification task brief explicitly lists "WR-01 fixed: root uses `$ref` not oneOf[single]" as the expected post-fix state.
- **Forward compat preserved:** The `$defs.v0_1` seam is intact. When v0.2 ships, the root `$ref` becomes `oneOf: [{$ref: v0_1}, {$ref: v0_2}]` — one-line change, no wire-format break. D-01's intent is fully achieved.
- **Doc note:** `docs/RECIPE-SCHEMA.md §10.1` still says `oneOf: [{$ref: #/$defs/v0_1}]` in its prose — this is a minor doc-schema drift (the schema is authoritative per the stated precedence rule, so the doc is the bug, not the schema). This is an INFO-level finding noted by IN-05 in the REVIEW.

---

### Regression Gate Results

| Gate | Command | Result |
|------|---------|--------|
| All 5 recipes lint PASS | `python3 tools/run_recipe.py --lint-all` | 5/5 PASS (hermes, nanobot, nullclaw, openclaw, picoclaw), rc=0 |
| Full pytest suite green | `python3 -m pytest tools/tests/ -q` | 171 passed, 2 deselected (Docker integration gated) |
| Self-check green | `python3 -m pytest tools/tests/test_schema_selfcheck.py -v` | 7 passed |
| Zero recipe edits | `git diff recipes/` | Empty — no recipe file touched |
| Zero runner edits | `git diff tools/run_recipe.py` | Empty — no runner code touched |

---

### Data-Flow Trace (Level 4)

Not applicable — phase produces schema, tests, and documentation (no dynamic data-rendering components).

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Schema parses as valid JSON | `python3 -c "import json; json.load(open('tools/ap.recipe.schema.json'))"` | Exit 0, no error | PASS |
| Meta-schema validation | `pytest test_schema_validates_against_draft_2020_12_meta_schema` | PASSED | PASS |
| `$defs` well-formedness and reachability | `pytest test_defs_are_well_formed_and_reachable` | PASSED (load-bearing: v0_1 and category asserted) | PASS |
| 5-recipe regression gate | `pytest test_all_committed_recipes_validate_against_schema[*]` | 5/5 PASSED | PASS |
| All 5 recipes pass lint-all | `python3 tools/run_recipe.py --lint-all` | 5/5 PASS | PASS |

---

### Requirements Coverage

The D-01 through D-11 identifiers are phase-internal implementation decisions (CONTEXT.md) not tracked as named IDs in REQUIREMENTS.md (which uses FND-xx, REC-xx etc. for the platform roadmap). All 11 decisions are verified complete above.

| Decision | Plans | Status | Evidence |
|----------|-------|--------|---------|
| D-01 Schema versioning seam | 18-02 | SATISFIED | `$defs.v0_1` + `$ref` at root (WR-01 fix) |
| D-02 Category `$defs` extraction | 18-02 | SATISFIED | `$defs.category` referenced from 2 sites |
| D-03 `verdict` enum (WR-05) | 18-02 | SATISFIED | `enum: ["PASS", "FAIL"]` on known_incompatible_cells |
| D-04 `source.ref` pattern | 18-02 | SATISFIED | Pattern `^[a-zA-Z0-9._/-]{1,255}$` present |
| D-05 `name` maxLength | 18-02 | SATISFIED | `maxLength: 64` |
| D-06 Differentiated timeout bounds | 18-02 | SATISFIED | 3600/10800/1800 maxima, min 1 preserved |
| D-07 `owner_uid` full uid_t | 18-02 | SATISFIED | `[0, 4294967295]` |
| D-08 Annotations escape valve | 18-02 | SATISFIED | 7 sites, `additionalProperties: true` |
| D-09 Optional license+maintainer | 18-02 | SATISFIED | Both optional, `maintainer.required: ["name"]` |
| D-10 Self-validation gate | 18-01 | SATISFIED | `test_schema_selfcheck.py`, 7/7 cells green |
| D-11 Narrative spec update | 18-03 | SATISFIED | RECIPE-SCHEMA.md at v0.1.1, all landmarks present |

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `docs/RECIPE-SCHEMA.md:314` | §10.1 says `oneOf: [{$ref: #/$defs/v0_1}]` but schema uses `$ref` directly | Info | Doc-schema drift. The schema's own precedence rule ("schema wins, doc is the bug") applies. Does not affect validation behavior. Forward-compat seam is intact in both. |

No blockers found. No stubs. No placeholder implementations.

---

### Human Verification Required

None. All checks are automated and deterministic:
- Schema structural assertions confirmed via Python
- Test suite confirmed via pytest
- Lint gate confirmed via `--lint-all`
- Git diff regression gate confirmed

---

## Gaps Summary

No gaps. All 11 decisions are verified in the committed codebase. The regression gate is non-negotiable and confirmed: 171 tests pass, 5 recipes lint-pass unchanged, zero edits to recipes or runner.

The only INFO-level finding is the doc-schema drift in §10.1 (says `oneOf`, schema uses `$ref`). This is pre-acknowledged — the schema's own header states "JSON Schema is authoritative; when this markdown and the schema disagree, the schema wins and this document is the bug." Phase 17 (doc-runner sync check) will enforce this automatically. Not a gap for Phase 18.

---

_Verified: 2026-04-16T23:00:00Z_
_Verifier: Claude (gsd-verifier)_
