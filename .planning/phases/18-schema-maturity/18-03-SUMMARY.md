---
phase: 18-schema-maturity
plan: 03
subsystem: spec
tags: [docs, spec, narrative, versioning-seam, annotations, license, maintainer, v0.1.1]

requires:
  - phase: 18-schema-maturity
    plan: 02
    provides: "v0.1.1 JSON Schema shape (oneOf/$defs seam, category extraction, 7 annotations sites, bounds hardening, WR-05 close-out, optional license/maintainer) — the authoritative contract the markdown must now describe"
provides:
  - "docs/RECIPE-SCHEMA.md narrative at v0.1.1 — end-to-end readable description of the shape landed in Plan 02"
  - "§10.1 Versioning seam section — oneOf/$defs.v0_1 discriminator + $defs.category extraction rationale"
  - "§11 Annotations escape valve section — 7 reserve sites documented + build.observed soft-deprecation note"
  - "'JSON Schema is authoritative' precedence rule — stated verbatim in the header paragraph"
  - "metadata.license + metadata.maintainer documented as optional-today-required-later for phase 19+"
  - "Out-of-scope section refreshed with Phase 18 deferrals (capability advertisement, runtime.limits, GPU, known_issues collapse, richer cells, required license/maintainer)"
affects: [phase-19-api-foundation, phase-17-doc-runner-sync-check]

tech-stack:
  added: []
  patterns:
    - "Narrative spec + authoritative JSON Schema split (narrative here, wire-format there, schema wins on conflict)"
    - "Decision-ID footnoting (D-01..D-09) in narrative — every addition cites the CONTEXT decision it reflects"
    - "Escape-valve section pattern — document the 7 annotations reserve sites in one place so schema-wide extensibility is discoverable from the doc alone"

key-files:
  created: []
  modified:
    - docs/RECIPE-SCHEMA.md

key-decisions:
  - "Threaded edits through existing §1-§10 rather than reorganizing — preserves reader muscle memory and keeps the diff scoped to narrative additions, not restructuring."
  - "Placed §10.1 Versioning seam AFTER §10 Out of scope rather than earlier so the strict deferral list is immediately visible, with the 'here's the seam that unblocks those future agents' explanation following it. The seam section is also where $defs.category extraction is explained — one place covers both D-01 and D-02."
  - "§11 Annotations escape valve placed at the end (not inline with §3-§7) so the 7 sites are catalogued once rather than repeated at each section. Each major section gets a single 'see §11' pointer instead of duplicating the annotations explanation five times."
  - "Did NOT rename section anchors except §10 (v0.1 → v0.1.1) — preserves existing inbound links from PLAN docs and phase 17's future doc-runner-sync-check reference patterns."

patterns-established:
  - "Minor-version narrative sync pattern: H1 bump + version-policy blockquote + precedence rule + per-section threading + new subsections only for wholly-new concepts (versioning seam, annotations escape valve)"
  - "Deferral pattern: CONTEXT.md's 'Out of scope (explicitly deferred)' list maps 1:1 to the markdown §10 bulleted list — reviewer can diff the two in future phases to confirm sync"

requirements-completed: [D-11]

duration: ~3min
completed: 2026-04-16
---

# Phase 18 Plan 03: Markdown Spec Sync to v0.1.1 Summary

**Synced `docs/RECIPE-SCHEMA.md` narrative to match the v0.1.1 JSON Schema landed in Plan 02. Added the 'JSON Schema is authoritative' precedence rule, a new §10.1 Versioning seam section documenting the oneOf/$defs.v0_1 discriminator + $defs.category extraction, a new §11 Annotations escape valve section catalogueing the 7 reserve sites, bounds documentation on all 4 tightened fields (source.ref pattern, name maxLength, 3 timeout maxima, owner_uid uid_t range), the WR-05 known_incompatible_cells.verdict enum close-out, and license + maintainer as optional-today-required-later. Refreshed §10 Out of scope with the 6 Phase 18 deferrals. No schema, runner, or recipe edits — pure narrative sync.**

## Performance

- **Duration:** ~3 min wall-clock
- **Started:** 2026-04-16T22:41:57Z
- **Completed:** 2026-04-16T22:45:25Z
- **Tasks:** 1 (of 1 in this plan)
- **Files modified:** 1 modified, 0 created

## Accomplishments

### Section additions (2 new sections)

- **§10.1 Versioning seam** — documents D-01 (oneOf/$defs.v0_1 discriminator pattern) and D-02 ($defs.category extraction). Explains how v0.2 will land additively by appending a second `$defs.v0_2` branch + extending the `oneOf` array — no wire-format break. Names the 11-value category enum in order (PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL, PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL, INFRA_FAIL, STOCHASTIC reserved, SKIP reserved) and notes the $ref pattern from both cell types.
- **§11 Annotations escape valve** — documents D-08. Catalogues the 7 reserve sites (build, runtime, invoke, smoke, metadata, verified_cells.items, known_incompatible_cells.items), explains the `additionalProperties: true` inside annotations vs `additionalProperties: false` outside pattern, cites the OpenAPI x-* / Kubernetes analogs, gives a concrete `build.annotations` YAML example with recon fields, and notes the `build.observed` soft-deprecation for new recipes.

### Section updates (8 threaded updates)

- **§1 Top-level identity** — `apiVersion` row now cross-references §10.1; `name` row documents maxLength 64 with the `ap-recipe-<name>` tag-limit rationale (D-05).
- **§2 source** — `source.ref` row documents the allowlist pattern `^[a-zA-Z0-9._/-]{1,255}$` with the `git fetch --upload-pack=<cmd>` option-as-value attack rationale (D-04).
- **§3 build** — added `timeout_s` (max 10800 / 3h) and `clone_timeout_s` (max 1800 / 30min) rows to the §3.1 upstream_dockerfile table with defaults and ceiling rationale (D-06). Added an annotations-trailer blockquote at end of §3 noting the `observed` → `annotations` soft-deprecation for new recipes.
- **§4 runtime** — `owner_uid` row now documents the `[0, 4294967295]` full Linux uid_t range, the `>65535 = userns-remap` convention, and the 4 values seen in the committed catalog (0, 1000, 10000, 65534) (D-07). Added an annotations-trailer blockquote at end of §4.
- **§5 invoke** — added an annotations-trailer blockquote at end of §5.
- **§6 smoke** — `smoke.timeout_s` row documents the `[1, 3600]` range with the human-attention-span ceiling rationale (D-06). `verified_cells[]` row now names the 4 required keys (model, verdict, category, detail) + cross-references §10.1 for the category enum. `known_incompatible_cells[]` row documents the `verdict ∈ {PASS, FAIL}` enum tightening with the WR-05 silent-typo gap close-out (D-03). Added an annotations-trailer blockquote at end of §6.
- **§7 metadata** — added `license` (SPDX) and `maintainer` ({name, url?}) rows as optional-today-required-later for phase 19+ (D-09). Added an annotations-trailer blockquote at end of §7.
- **§9 Compatibility** — rewritten to explain v0.1.1 is additive over v0.1, accepts both `v0` and `v0.1`/`v0.1.1` apiVersion values, references the `test_schema_selfcheck.py` regression gate from Plan 01/02 (D-10).

### Section refresh (1 enumeration update)

- **§10 Out of scope** — renamed from "v0.1" to "v0.1.1". Preserved the original 8-item list (external_services, interactive setup, trajectory_file, http_post/repl_pty, compound pass_if, non-awk stdout_filter, multi-host). Appended the 6 Phase 18 CONTEXT deferrals: capability advertisement block (Phase 22+), runtime.limits (Phase 23), GPU/CUDA declaration, known_issues[] collapse (v0.2), richer verified_cells[] (Phase 24), required license/maintainer (flips at phase 19+). Closing line now reads "blocked by format until the relevant phase — not a v0.1.1 patch."

### Header-level additions

- **H1 bumped** from `ap.recipe/v0.1` to `ap.recipe/v0.1.1`.
- **Version policy blockquote** inserted after the opening paragraph — summarizes what's new in v0.1.1 (tightened bounds, annotations escape valve, optional license/maintainer, $defs versioning seam) and states the precedence rule verbatim: "The JSON Schema at `tools/ap.recipe.schema.json` is authoritative. When this markdown and the schema disagree, the schema wins and this document is the bug."
- **File-shape sketch** updated — `metadata: { ..., license?, maintainer? }` and a new trailing line pointing to §11 annotations.

## Structural Diff Summary

- +65 insertions, -14 deletions, net +51 lines (284 → 335).
- 2 new sections (§10.1 Versioning seam, §11 Annotations escape valve).
- 8 sections received inline updates (§1, §2, §3, §4, §5, §6, §7, §9).
- 1 section renamed and extended (§10: v0.1 → v0.1.1 label; 8-item list → 14-item list).
- 5 annotations-trailer blockquotes added (one per major section).
- 0 sections removed. 0 sections reordered. 0 anchors broken.

## Verification Results

### Landmark grep counts (all requirements)

| Landmark                  | Required | Actual |
| ------------------------- | -------- | ------ |
| `v0.1.1` references       | ≥ 3      | 13     |
| `annotations` references  | ≥ 5      | 16     |
| `maintainer` references   | ≥ 2      | 7      |
| `authoritative` references | ≥ 1     | 1      |
| `4294967295` references   | ≥ 1      | 1      |
| `3600` (smoke timeout max) | ≥ 1     | 1      |
| `10800` (build timeout max) | ≥ 1    | 1      |
| `1800` (clone timeout max) | ≥ 1     | 1      |

All 8 landmark checks PASS.

### Out-of-scope deferrals check

Python scan of the "Out of scope" section confirmed all 6 Phase 18 deferrals present: `capabilities`, `runtime.limits`, `GPU`, `known_issues`, `license`, `maintainer`. No missing items.

### Scope guard (no drift outside docs/RECIPE-SCHEMA.md)

```
$ git diff --name-only
docs/RECIPE-SCHEMA.md
```

Single file. `git diff tools/ recipes/` returns empty. Zero collateral changes.

### Regression suite

```
$ cd tools && python3 -m pytest -q
162 passed, 2 deselected in 1.44s
```

Full suite green including the Plan 01 + Plan 02 self-check (7 cells) and the 5-recipe regression test. Markdown edits did not perturb any test — expected since this plan is narrative-only, but the safety-net run confirms it.

## Task Commits

1. **Task 1: Sync RECIPE-SCHEMA.md narrative to v0.1.1 — 2 new sections + 8 section updates + §10 refresh + header policy paragraph** — `fe44c58` (docs)

_Single commit as the plan's `<action>` called for one coherent write pass. Every edit in the 13-step plan action block is reflected in this commit._

## Files Created/Modified

- `docs/RECIPE-SCHEMA.md` — modified (+65 insertions, -14 deletions; 284 → 335 lines).

## Decisions Made

- **§10.1 and §11 placement** — §10.1 immediately after §10 (discoverability: readers who hit the deferral wall see the seam that unblocks the future), §11 at end (catalogue pattern — one place documents all 7 annotations sites). Not interleaved with §3-§7 to avoid five-way repetition.
- **D-ID citations preserved in narrative** — every added bound or enum tightening carries its `(D-N)` footnote. Future maintainers diffing CONTEXT.md ↔ RECIPE-SCHEMA.md can trace each claim to its decision without opening a third file.
- **§9 Compatibility fact correction** — the existing text said "All 5 recipes declare apiVersion: ap.recipe/v0"; the actual committed recipes declare `ap.recipe/v0.1` (per 18-02-SUMMARY and a quick verification). Corrected to `ap.recipe/v0.1` in the rewrite.
- **Annotations trailer blockquote repetition** — chose to add the short "see §11" pointer at the end of each of §3, §4, §5, §6, §7 rather than a single catalog-only mention. Rationale: a recipe author reading §4 (runtime) should not have to scroll to §11 to learn that a runtime.annotations block is legal; the inline trailer gives them the option with minimal prose cost.

## Deviations from Plan

**None.** The plan's `<action>` block was prescriptive with explicit text for 13 edits. Every edit landed as specified. The one point of Claude's discretion (heading anchor preservation) was exercised as the plan advised ("Preserve all existing anchors unless renamed").

## Issues Encountered

None. All 13 edits applied cleanly in sequence. Landmark checks all passed first try. Full pytest green first try. `git diff` scope-guarded to a single file first try.

## User Setup Required

None — pure markdown narrative edit.

## Next Phase Readiness

- **Phase 18 exit gate** — all three plans now complete. Self-check (01), schema refactor (02), spec sync (03).
- **Phase 19 (API Foundation)** — recipe contract is now fully documented in both narrative (this doc) and authoritative JSON (Plan 02's schema). A Go orchestrator or external contributor can read `docs/RECIPE-SCHEMA.md` end-to-end and produce a valid v0.1.1 recipe.
- **Phase 17 (Doc-runner sync check)** — will one day enforce automatically what Plan 03 enforces manually. The precedence rule ("JSON Schema is authoritative") is stated so Phase 17's check knows which side of the sync to treat as ground truth.
- No blockers, no deferred items.

## TDD Gate Compliance

Plan frontmatter declares `type: execute`. The single task is not marked `tdd="true"` — this is a narrative sync, not a behavior change. No RED/GREEN cycle applies. The "test" for this plan's correctness is the landmark-grep + out-of-scope-scan + scope-guard + full-pytest suite documented above — all four PASS.

## Self-Check: PASSED

- [x] `docs/RECIPE-SCHEMA.md` H1 says `ap.recipe/v0.1.1` — verified (line 1).
- [x] Precedence rule ("JSON Schema is authoritative") appears verbatim — verified (line 13, `authoritative` count = 1).
- [x] New §10.1 "Versioning seam" explains oneOf/$defs.v0_1 + $defs.category — verified (lines 312-316).
- [x] New §11 "Annotations escape valve" documents 7 sites + build.observed deprecation — verified (lines 320-335).
- [x] §1 name row mentions maxLength 64 — verified (line 45).
- [x] §1 apiVersion row references §10.1 — verified (line 44).
- [x] §2 source.ref row documents the allowlist pattern — verified.
- [x] §3 build table has `timeout_s` (max 10800) and `clone_timeout_s` (max 1800) — verified.
- [x] §4 volumes.owner_uid row documents `[0, 4294967295]` + userns-remap note — verified.
- [x] §6 smoke.timeout_s documents max 3600 — verified.
- [x] §6 known_incompatible_cells row documents `{PASS, FAIL}` verdict enum — verified.
- [x] §7 metadata table has new optional rows for `license` and `maintainer` — verified.
- [x] §9 Compatibility explicitly states v0.1.1 is additive over v0.1 + references self-check test — verified (line 283).
- [x] §10 Out of scope renamed to v0.1.1 + includes 6 Phase 18 deferrals — verified.
- [x] Commit `fe44c58` exists on branch — verified via `git log --oneline`.
- [x] `git diff --name-only` returns ONLY `docs/RECIPE-SCHEMA.md` — verified.
- [x] `git diff tools/ recipes/` empty — verified.
- [x] Full `pytest -q` green: 162 passed, 2 deselected — verified.

---
*Phase: 18-schema-maturity*
*Plan: 03*
*Completed: 2026-04-16*
