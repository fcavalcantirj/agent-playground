---
phase: 18-schema-maturity
reviewed: 2026-04-16T20:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - tools/ap.recipe.schema.json
  - tools/tests/test_schema_selfcheck.py
  - docs/RECIPE-SCHEMA.md
findings:
  critical: 0
  warning: 4
  info: 5
  total: 9
status: issues_found
---

# Phase 18: Code Review Report

**Reviewed:** 2026-04-16T20:00:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Phase 18 delivers the D-01..D-11 maturity pass cleanly at the structural level:

- `$defs.v0_1` extraction is correct, reachable from the root `oneOf`, and the `$defs.category` factoring is referenced from exactly the two cell shapes the context calls out (verified_cells + known_incompatible_cells).
- The schema validates against draft-2020-12 meta-schema (confirmed by calling `Draft202012Validator.check_schema` directly on the committed file).
- All 5 committed recipes lint clean against the new schema. Bounds (`name` maxLength 64, `owner_uid` full uid_t, `timeout_s` tiers, `ref` allowlist) all admit the real-world values in the 5-recipe matrix.
- The WR-05 gap (D-03) is closed: `known_incompatible_cells[].verdict` is now the closed enum `{PASS, FAIL}` and a deliberate `TYPO` value is rejected.
- The 7 `annotations` escape-valves land on the exact subschemas listed in D-08 (build, runtime, invoke, smoke, metadata, verified_cells[], known_incompatible_cells[]).

However, there are **9 findings** below the critical bar that should be addressed before the schema is used as the Phase 19 API contract. The headline items:

- **WR-01**: The `oneOf: [v0_1]` wrapper collapses every inner validation error into a single opaque "not valid under any of the given schemas" top-level message, turning every lint failure into a hunt for the real problem. This is a UX regression specifically caused by the D-01 refactor — the pre-D-01 schema produced targeted errors.
- **WR-02**: `metadata.maintainer.name` is NOT required by the schema, contrary to what the spec narrative implies; an empty `{}` maintainer block lints clean.
- **WR-03**: `metadata.recon_date` pattern accepts impossible calendar dates like `2026-13-45` (pre-existing, but the schema is now explicitly the source of truth).
- **WR-04**: The D-10.2 self-check test (`test_defs_are_well_formed_and_reachable`) has a silent-vacuous escape hatch that the file's own docstring warned about — it should be tightened now that `$defs` is actually populated, otherwise a future schema change that deletes all of `$defs` will silently re-green the test.

The info-level items capture spec/schema drift (e.g. `source.repo` has no URL enforcement), verb-field coupling asymmetry, and a handful of self-check gaps.

None of these block the 5-recipe regression gate, but they matter for the "API contract for Phase 19" framing in the context doc.

## Warnings

### WR-01: `oneOf: [ v0_1 ]` swallows inner error messages — all errors report as top-level "not valid under any of the given schemas"

**File:** `tools/ap.recipe.schema.json:7-9`
**Issue:** The root was refactored from a single shape to `"oneOf": [ { "$ref": "#/$defs/v0_1" } ]` per D-01. Functionally correct and the extension point is well designed. But because the `oneOf` has exactly one branch, draft-2020-12 validators report a `oneOf` failure at the root rather than the specific child error. Confirmed empirically — for every malformed recipe tried (malicious `source.ref`, negative `owner_uid`, empty `source_citations[]`, missing `source` for `upstream_dockerfile` mode, missing `base_url`), the ONLY error returned was the full recipe object followed by `"is not valid under any of the given schemas"`. The inner, actionable error is suppressed.

This is a measurable regression in operator UX versus the pre-D-01 schema: `lint_recipe` used to return `metadata.source_citations: [] should be non-empty`; now it returns the entire recipe dict embedded in one `(root):` error. For the schema's role as the Phase 19 API contract, the diagnostic is load-bearing, not cosmetic.

There are two standard fixes:

1. **Preferred**: keep the body inline at the root for v0.1 and only introduce the `oneOf` wrapper *when v0.2 lands*. The D-01 seam can be staged — a single-branch `oneOf` buys nothing over a direct `$ref` today and costs diagnostics.
2. **Alternative**: keep the `oneOf` but switch the runner's error formatter to descend into `context` errors so the inner message surfaces. The `jsonschema` library exposes `e.context` for exactly this case; a short walk of the context tree gives back specific messages.

**Fix (option 1 — preferred; mechanical and does not break the D-01 seam contract):**
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://agentplayground.dev/schemas/ap.recipe.v0.1.json",
  "title": "Agent Playground Recipe — ap.recipe/v0.1.1",
  "$ref": "#/$defs/v0_1",
  "$defs": { "category": { ... }, "v0_1": { ... } }
}
```
A direct `$ref` at the root is semantically equivalent to a single-branch `oneOf` but preserves inner error messages. When v0.2 lands, flip `$ref` to `oneOf: [ {$ref: v0_1}, {$ref: v0_2} ]`. The D-01 goal ("future v0.2 wire-compat without a schema-file break") is fully preserved — changing `$ref` → `oneOf` is a one-line edit.

**Fix (option 2 — if the `oneOf` is kept by preference):** in `tools/run_recipe.py:142-146`, descend into each error's `.context` chain when the path is `(root)` and the schema keyword is `oneOf`, surfacing the most specific child errors instead. Add a regression test under `tools/tests/test_lint.py` asserting that a recipe with an empty `source_citations[]` produces a message containing `metadata.source_citations` on the path, not `(root)`.

### WR-02: `metadata.maintainer` accepts empty object `{}` — `name` is not enforced, contradicting the spec narrative

**File:** `tools/ap.recipe.schema.json:494-509`
**Issue:** D-09 added `metadata.maintainer` as an optional `{name, url}` object with `additionalProperties: false`. But the `maintainer` subschema has no `"required"` array, so `{}` lints clean, as does `{"url": "https://x"}` with no name. Spec text at `docs/RECIPE-SCHEMA.md:237` says:

> `metadata.maintainer` | object `{ name, url? }` | ... `name` is a string (maintainer handle or full name).

The narrative reads as "name required, url optional" — the schema does not enforce it. When D-09 flips to required in a later phase, the inner `name` field should already be required so that a present-but-empty `maintainer` block is rejected; otherwise the phase-19+ "flip to required" change is actually two changes (presence + inner shape) and easy to get wrong.

**Fix:**
```json
"maintainer": {
  "type": "object",
  "additionalProperties": false,
  "required": ["name"],
  "properties": {
    "name": { "type": "string", "minLength": 1, "description": "Maintainer name or handle." },
    "url":  { "type": "string", "format": "uri", "description": "Maintainer homepage or contact URL." }
  },
  "description": "Optional in v0.1.1; required before external contribution lands (phase 19+)."
}
```
None of the 5 committed recipes set `maintainer`, so adding `required: [name]` inside it is a strictly additive tightening that does not break the regression gate.

### WR-03: `metadata.recon_date` pattern admits impossible calendar dates (e.g. `2026-13-45`)

**File:** `tools/ap.recipe.schema.json:473-476`
**Issue:** The pattern `^\d{4}-\d{2}-\d{2}$` is a shape check, not a calendar check. `2026-13-45` passes lint. Pre-existing, but Phase 18 is the moment the schema is being declared the "authoritative API contract"; this is now documented imprecision rather than a quiet bug.

The proper draft-2020-12 tool for dates is the `format: date` keyword (RFC 3339 full-date). Note that `format` in draft-2020-12 is an annotation by default — `Draft202012Validator` with format assertion enabled (`format_checker=FormatChecker()`) turns it into a real check. The runner does not currently enable the format checker, so even `format: date` would pass the `2026-13-45` case unless it also enables `format_checker`.

**Fix (schema side — documents intent):**
```json
"recon_date": {
  "type": "string",
  "format": "date",
  "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
  "description": "When the recipe was researched (RFC 3339 full-date: YYYY-MM-DD)."
}
```
**Fix (runner side — makes `format: date` enforceable):** in `tools/run_recipe.py:137`, pass a `FormatChecker()`:
```python
from jsonschema import Draft202012Validator, FormatChecker
validator = Draft202012Validator(schema, format_checker=FormatChecker())
```
With both edits, `2026-13-45` is rejected; `2026-04-15` (all 5 committed recipes) continues to pass.

### WR-04: `test_defs_are_well_formed_and_reachable` has a silent-vacuous escape that the file's own docstring acknowledges — now that `$defs` is populated, the guard should become load-bearing

**File:** `tools/tests/test_schema_selfcheck.py:86-91`
**Issue:** The test's `if not defs: return` branch was deliberate for the TDD-RED window before Plan 02 shipped `$defs.v0_1` + `$defs.category`. The phase-shipping state is: `$defs` is populated, the test is supposed to be load-bearing. But as written, if any future schema change removes `$defs` (or every entry), this test silently re-greens to vacuous pass, which defeats the D-10.2 intent.

This is flagged as a warning rather than info because the docstring (lines 17-21) explicitly describes the escape as "vacuously true today... becomes load-bearing once Plan 02 adds `$defs.v0_1` + `$defs.category`" — the phase has now shipped Plan 02, so the test should be tightened at the same checkpoint it was expected to tighten.

**Fix:** replace the silent early return with a positive assertion that `$defs` contains at least the names the schema claims (`v0_1` and `category`), since those are the two D-01/D-02 outputs the phase is gating on:
```python
def test_defs_are_well_formed_and_reachable():
    schema = json.loads(SCHEMA_PATH.read_text())
    defs = schema.get("$defs", {})
    assert isinstance(defs, dict) and defs, (
        "$defs must exist and be non-empty after Phase 18 D-01/D-02 land"
    )
    # Phase 18 guarantees these two names exist; a future phase may add more.
    for required in ("v0_1", "category"):
        assert required in defs, f"$defs/{required} missing — D-0{'1' if required=='v0_1' else '2'} regressed"
    # ... (existing well-formedness + reachability loops follow unchanged)
```
This keeps the generic well-formedness/reachability rules intact but pins the minimum contract. The 5-recipe regression test (D-10.3) is not affected.

## Info

### IN-01: `source.repo` is `type: string` with no pattern or `format: uri` — "HTTPS clone URL" narrative is not enforced

**File:** `tools/ap.recipe.schema.json:66-69`
**Issue:** `source.repo` accepts any string, including `"not-a-url"`. Spec at `docs/RECIPE-SCHEMA.md:55` says "HTTPS clone URL." Not a safety issue (the runner passes this to `git clone` which will fail loudly on malformed URLs), but the schema-as-contract should catch obvious typos at lint time.

**Fix:** add a weak pattern matching `https://host/...` since the spec is already opinionated about HTTPS:
```json
"repo": {
  "type": "string",
  "format": "uri",
  "pattern": "^https://[^\\s]+$",
  "description": "HTTPS clone URL."
}
```
All 5 committed recipes' `source.repo` values (`https://github.com/...`) pass this pattern.

### IN-02: Verb/field coupling is enforced one-way only — a recipe can set `needle` under `pass_if: response_regex` and it will lint clean while being silently ignored

**File:** `tools/ap.recipe.schema.json:518-578` (the `allOf` if/then chain)
**Issue:** The current `allOf` enforces these rules:
- `response_contains_string` ⇒ `needle` required
- `response_not_contains` ⇒ `needle` required
- `response_regex` ⇒ `regex` required
- `upstream_dockerfile` ⇒ `source.repo + source.ref` required
- `image_pull` ⇒ `image` required

But the inverse is not enforced. A recipe with `pass_if: response_regex, needle: "foo", regex: "^bar"` lints clean — `needle` is silently dropped by the runner. Same for `pass_if: exit_zero, needle: "zzz"` and `pass_if: response_contains_name, regex: "..."`. This is the same kind of silent-typo gap that WR-05 (D-03) closed for `verdict`.

**Fix (two options):**

1. Add inverse `if/then` clauses for each verb. E.g.:
```json
{
  "if": { "properties": { "smoke": { "properties": { "pass_if": { "enum": ["exit_zero", "response_contains_name"] } } } } },
  "then": { "properties": { "smoke": { "not": { "anyOf": [ {"required":["needle"]}, {"required":["regex"]} ] } } } }
}
```
2. Or defer to a v0.2 shape-tightening (smoke discriminator by pass_if) and document under §10 "Out of scope for v0.1.1" as a known gap.

Option 2 is arguably cleaner for v0.1.1; worth an explicit line in the out-of-scope list if it's the chosen path.

### IN-03: `process_env.api_key` and `process_env.provider` accept empty strings (no `minLength: 1`)

**File:** `tools/ap.recipe.schema.json:138-163`
**Issue:** `runtime.provider` (line 138), `runtime.process_env.api_key` (line 147), `volumes[].name` (line 172), `volumes[].host` (line 176), `volumes[].container` (line 180), and several other `type: string` required fields do not set `minLength: 1`. An empty string lints clean for most of them. Most are load-bearing at runtime (e.g. an empty `api_key` name would cause `resolve_api_key` in the runner to fail with a confusing message); catching them at lint time is cheap.

`display_name` and `description` correctly have `minLength: 1`. The gap is elsewhere.

**Fix:** scan all `"type": "string"` entries in required fields and add `"minLength": 1` where the field is load-bearing. At minimum: `runtime.provider`, `runtime.process_env.api_key`, `volumes[].name`, `volumes[].host`, `volumes[].container`, `verified_cells[].model`, `known_incompatible_cells[].model`, `invoke.spec.argv.items` (`minLength: 1` on each argv element — an empty argv entry is almost certainly a bug).

### IN-04: `build.clone_timeout_s` appears in the schema for `upstream_dockerfile` mode but the spec §3.2 `image_pull` table does not list it — narrative asymmetry

**File:** `docs/RECIPE-SCHEMA.md:79-80` and schema `tools/ap.recipe.schema.json:120-125`
**Issue:** `build.clone_timeout_s` is defined at the `build` object level (not under an `if mode == upstream_dockerfile` branch), so the schema technically allows setting it in `image_pull` mode (where there is no clone). The runner ignores it in `image_pull` mode. The spec §3.1 table lists it correctly; §3.2 `image_pull` table omits it (correct narrative), so a reader might assume the schema rejects it there. It does not.

**Fix (preferred):** tighten with an `if/then` that rejects `clone_timeout_s` when `mode == image_pull`:
```json
{
  "if": { "properties": { "build": { "properties": { "mode": { "const": "image_pull" } } } } },
  "then": { "properties": { "build": { "not": { "required": ["clone_timeout_s"] } } } }
}
```
Or: document explicitly in §3.2 that `clone_timeout_s` is accepted-but-ignored in `image_pull` mode.

### IN-05: Schema `$id` URL references `ap.recipe.v0.1.json` but the spec title says `v0.1.1` — minor label drift

**File:** `tools/ap.recipe.schema.json:3-5`
**Issue:** Line 3: `"$id": "https://agentplayground.dev/schemas/ap.recipe.v0.1.json"`. Line 4: `"title": "Agent Playground Recipe — ap.recipe/v0.1.1"`. The `$id` is a logical identifier, not a wire format — but if the schema is to be served at a well-known URL for Phase 19 consumers, the `$id` and title should agree. The context doc at §"Claude's Discretion" explicitly lists this as the planner's call; the chosen value should be consistent across both fields or one should be updated.

Also, §9 of the spec describes the relationship between v0.1 and v0.1.1 as "additive" and states the schema file at `tools/ap.recipe.schema.json` is authoritative — which is true — but a reader trying to resolve the `$id` URL will find "v0.1" in the path while the title is "v0.1.1". Low priority cosmetic cleanup.

**Fix:** pick one:
```json
"$id": "https://agentplayground.dev/schemas/ap.recipe.v0.1.1.json"
```
or downgrade the title to `v0.1` and describe v0.1.1 only in the `description` field. The first is more accurate to the phase framing.

---

_Reviewed: 2026-04-16T20:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
