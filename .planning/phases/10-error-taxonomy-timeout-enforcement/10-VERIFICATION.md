---
phase: 10-error-taxonomy-timeout-enforcement
verified: 2026-04-16T22:00:00Z
status: passed
score: 9/9
overrides_applied: 0
---

# Phase 10: Error Taxonomy + Timeout Enforcement — Verification Report

**Phase Goal:** Replace single `PASS|FAIL` verdict with category-aware verdicts (`PASS`, `ASSERT_FAIL`, `INVOKE_FAIL`, `BUILD_FAIL`, `PULL_FAIL`, `CLONE_FAIL`, `TIMEOUT`, `LINT_FAIL`, `INFRA_FAIL`) + 2 reserved (`STOCHASTIC`, `SKIP`). Wire `smoke.timeout_s` to `--cidfile` + `docker kill` for true container reaping. Add `build.timeout_s`, `build.clone_timeout_s`, `--global-timeout`. Migrate 5 committed recipes to new shape. Steal from Inspect AI (5-layer timeout) and SWE-bench (`ResolvedStatus` enum).
**Verified:** 2026-04-16T22:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Derived from the phase goal (no success_criteria array in ROADMAP.md):

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Schema defines 11-value category enum (PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL, PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL, INFRA_FAIL, STOCHASTIC, SKIP) on verified_cells and known_incompatible_cells | VERIFIED | `ap.recipe.schema.json` verified_cells.items.properties.category.enum has exactly 11 values in correct order; same enum mirrored on known_incompatible_cells |
| 2 | Schema requires category+detail on every cell (not just accepts) | VERIFIED | `verified_cells.items.required = ["model","verdict","category","detail"]`; same on known_incompatible_cells — confirmed via Python json.load assertion |
| 3 | Schema adds build.timeout_s and build.clone_timeout_s fields | VERIFIED | `build.properties.timeout_s` and `build.properties.clone_timeout_s` both present as optional integers with minimum:1 |
| 4 | Runner exposes Category(str, Enum) + Verdict frozen dataclass importable with correct behavior | VERIFIED | `from run_recipe import Category, Verdict` succeeds; 11 values confirmed; Verdict.verdict derived correctly; frozen raises FrozenInstanceError |
| 5 | run_cell uses --cidfile + docker kill + docker rm -f for true container reaping on timeout | VERIFIED | `run_cell` constructs `cidfile = Path(f"/tmp/ap-cid-{uuid.uuid4().hex}.cid")` and injects `--cidfile={cidfile}` into docker run; TimeoutExpired handler reads cidfile, calls `subprocess.run(["docker", "kill", cid], ...)` + `subprocess.run(["docker", "rm", "-f", cid], ...)`; cidfile unlinked in finally block; 9 cidfile references in run_recipe.py |
| 6 | build.timeout_s and build.clone_timeout_s are consumed by ensure_image; --global-timeout added to CLI | VERIFIED | `ensure_image` reads `build.get("timeout_s", DEFAULT_BUILD_TIMEOUT_S)` and `build.get("clone_timeout_s", DEFAULT_CLONE_TIMEOUT_S)`; `parse_args` has `--global-timeout` option with `dest="global_timeout"`; main() cell loop respects global deadline |
| 7 | All 5 committed recipes migrated to carry category+detail on every cell | VERIFIED | hermes.yaml: 2 verified_cells (category:PASS, detail:'') + 1 known_incompat (category:ASSERT_FAIL, detail:"flapping verdict — see notes", verdict remapped from STOCHASTIC→FAIL); openclaw.yaml, picoclaw.yaml, nullclaw.yaml, nanobot.yaml: all cells have category+detail; `grep "verdict: STOCHASTIC" recipes/*.yaml` returns zero matches |
| 8 | All 5 recipes lint-pass under the tightened schema | VERIFIED | `./tools/run_recipe.py --lint-all` returns PASS for all 5 recipes; 121 tests pass (includes test_lint.py + test_recipe_regression.py) |
| 9 | Taxonomy regression tests: 9 live categories each have ≥1 test fixture + cidfile lifecycle + W5 kill-path gate | VERIFIED | `test_categories.py` has 14 test classes, 32 tests; `TestCidfileLifecycle::test_docker_kill_invoked_on_timeout` PASSES and asserts `docker kill fake-cid-abc123` + `docker rm -f fake-cid-abc123` invocations; full suite 121 passed in 1.16s |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tools/ap.recipe.schema.json` | 11-value category enum on 2 cell types; required arrays tightened; build timeout fields | VERIFIED | Enum correct in both cell blocks; required = ["model","verdict","category","detail"]; build.timeout_s + build.clone_timeout_s present |
| `tools/run_recipe.py` | Category enum, Verdict dataclass, cidfile timeout, preflight, global-timeout | VERIFIED | 1088 lines; Category(str,Enum) with 11 values; Verdict frozen dataclass; cidfile 9 references; --global-timeout; preflight_docker 3 references; _redact_api_key 3 references |
| `recipes/hermes.yaml` | category+detail on all cells; STOCHASTIC→FAIL remapped | VERIFIED | 2 verified_cells + 1 known_incompat all have category+detail; verdict STOCHASTIC removed |
| `recipes/openclaw.yaml` | category+detail on all cells | VERIFIED | verified_cells and known_incompatible_cells have category+detail |
| `recipes/picoclaw.yaml` | category+detail on verified_cells | VERIFIED | category:PASS, detail:'' present |
| `recipes/nullclaw.yaml` | category+detail on verified_cells | VERIFIED | category:PASS, detail:'' present (2 entries, both migrated) |
| `recipes/nanobot.yaml` | category+detail on verified_cells | VERIFIED | category:PASS, detail:'' present |
| `tools/tests/test_categories.py` | 9 live categories + Enum/Verdict/Cidfile/Emit/Redaction test classes; ≥250 lines | VERIFIED | 564 lines; 14 classes; 32 tests; all categories covered; W5 gate present |
| `tools/tests/conftest.py` | mock_subprocess_timeout + mock_subprocess_dispatch + fake_cidfile fixtures added | VERIFIED | All 3 fixtures present (123 lines added); existing fixtures untouched; minimal_valid_recipe updated with category/detail |
| `scripts/migrate_recipes_phase10.py` | One-shot ruamel migration script (retained for audit) | VERIFIED | Exists; idempotent via setdefault; ruamel config byte-identical to run_recipe.py |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `run_cell` in run_recipe.py | docker kill \<cid\> | TimeoutExpired handler reads cidfile content | VERIFIED | Lines 691-695: `subprocess.run(["docker", "kill", cid], ...)` after reading cidfile |
| `run_cell` docker run command | `--cidfile={cidfile}` injection | `docker_cmd` list construction | VERIFIED | Line 638: `f"--cidfile={cidfile}"` in docker_cmd |
| `cidfile` path | `finally` block unlink | `cidfile.unlink(missing_ok=True)` | VERIFIED | Lines 706-709: unlink in finally regardless of success/timeout/fail |
| `preflight_docker()` | `main()` Step 5 call | `infra = preflight_docker()` before lint/load | VERIFIED | Line 938: called before mandatory lint and recipe load |
| `ensure_image()` | `build.timeout_s` / `build.clone_timeout_s` | `build.get("timeout_s", DEFAULT_BUILD_TIMEOUT_S)` | VERIFIED | Lines 486-487: both build timeout fields consumed |
| `parse_args` | `--global-timeout` option | `p.add_argument("--global-timeout", ...)` | VERIFIED | Lines 867-876: argparse option wired; main() cell loop honors global_deadline |
| `TestCidfileLifecycle::test_docker_kill_invoked_on_timeout` | `fake_cidfile` + `mock_subprocess_timeout(record=True)` | asserts recorded includes docker kill cid + docker rm -f cid | VERIFIED | Test PASSES; W5 D-03 maturity gate confirmed |
| `tools/ap.recipe.schema.json` | verified_cells.items.required | `["model","verdict","category","detail"]` | VERIFIED | Confirmed via Python assertion in verification |
| All 5 recipes | tightened schema | lint-all returns PASS for all | VERIFIED | `./tools/run_recipe.py --lint-all` → 5 PASS |

### Data-Flow Trace (Level 4)

Not applicable — this phase produces a CLI tool (run_recipe.py), not a web component with data bindings. Behavioral spot-checks in Step 7b cover the equivalent verification.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Category enum importable with 11 values | `python3 -c "from run_recipe import Category; print(len(list(Category)))"` | 11 | PASS |
| Verdict frozen dataclass works | `python3 -c "from run_recipe import Verdict, Category; v=Verdict(Category.PASS); v.detail='x'"` | FrozenInstanceError raised | PASS |
| --global-timeout argparse wired | `python3 -c "from run_recipe import parse_args; args=parse_args(['--global-timeout=10','x.yaml']); print(args.global_timeout)"` | 10 | PASS |
| --lint on hermes.yaml exits 0 | `./tools/run_recipe.py recipes/hermes.yaml --lint` | "PASS hermes.yaml" | PASS |
| --lint-all on 5 recipes all PASS | `./tools/run_recipe.py --lint-all` | 5 × PASS | PASS |
| Full pytest suite | `cd tools && python3 -m pytest -x -q` | 121 passed in 1.16s | PASS |
| W5 kill-path gate | `pytest tests/test_categories.py::TestCidfileLifecycle::test_docker_kill_invoked_on_timeout -v` | PASSED in 0.01s | PASS |
| API-key redaction | `python3 -c "from run_recipe import _redact_api_key; print(_redact_api_key('FOO=secret bar','FOO'))"` | FOO=\<REDACTED\> bar | PASS |

### Requirements Coverage

The D-01 through D-05 requirements referenced in plan frontmatter are phase-internal requirements defined in `10-CONTEXT.md`, NOT entries in the global `REQUIREMENTS.md`. The global REQUIREMENTS.md uses FND/SBX/AUTH/SEC/REC/SES etc. IDs and maps Phase 10 to none of them — this phase is framework tooling maturity work, not v1 product requirement work. There are no orphaned global requirements for Phase 10.

Phase-internal requirements as declared across plans:

| Requirement | Plans | Description (from 10-CONTEXT.md) | Status |
|-------------|-------|----------------------------------|--------|
| D-01 | 10-01, 10-03, 10-04, 10-05 | Category set (11 values, 9 live + 2 reserved) | SATISFIED — Category(str,Enum) implemented; schema enum matches; test_enum_has_11_values + test_enum_ordering pass |
| D-02 | 10-03, 10-04, 10-05 | Verdict shape (category-primary, detail string, derived verdict field) | SATISFIED — Verdict frozen dataclass implemented; to_cell_dict(); schema required arrays include category+detail |
| D-03 | 10-01, 10-04, 10-05 | Timeout plumbing — --cidfile + docker kill for true reap; build.timeout_s, clone_timeout_s, --global-timeout | SATISFIED — cidfile injection, docker kill reap in finally, build timeout fields consumed, --global-timeout argparse + cell loop |
| D-04 | 10-02 | Backwards-compat migration of 5 recipes with category+detail per cell; STOCHASTIC→FAIL+ASSERT_FAIL mapping | SATISFIED — all 5 recipes migrated; hermes STOCHASTIC remapped; idempotent migration script |
| D-05 | 10-04 | CLI output — emit_verdict_line one-line format, green PASS / red non-PASS | SATISFIED — emit_verdict_line implemented; TestEmitFormat passes (green=\033[32m, red=\033[31m) |

### Anti-Patterns Found

None detected. Scan of key modified files (tools/run_recipe.py, tools/tests/test_categories.py, tools/tests/conftest.py, recipes/*.yaml):

- No TODO/FIXME/placeholder comments in any phase 10 additions
- No `return null` / `return {}` / `return []` stubs
- No hardcoded empty data flowing to user-visible output
- No console.log-only implementations
- `detail: ''` on PASS cells is intentional per D-02 ("empty string is the convention when category=PASS"), not a stub — it flows from the schema to the recipe YAML and is the authoritative value

### Human Verification Required

No human verification items identified. All goal behaviors are programmatically verifiable:

- Category enum shape: verified via Python import and assertion
- Verdict dataclass behavior: verified via unit tests
- cidfile injection + docker kill reap: verified via test_docker_kill_invoked_on_timeout (W5 gate) — monkeypatches subprocess so no live Docker needed
- Lint paths: verified via --lint and --lint-all CLI invocations
- Recipe migration: verified via grep + Python structural assertion
- Schema tightening: verified via Python json.load assertion on required arrays
- Full regression: 121 tests pass

### Gaps Summary

No gaps. All 9 observable truths verified, all artifacts substantive and wired, all key links confirmed. The phase delivered exactly what the goal specified:

1. **Category taxonomy** — 11-value Category(str, Enum) in Python; 11-value enum in JSON Schema on both cell types; schema required arrays tightened.
2. **Verdict shape** — frozen Verdict dataclass with derived verdict property + to_cell_dict(); schema and recipes both carry the new shape.
3. **Timeout enforcement** — cidfile injection into every docker run; TimeoutExpired handler reads cidfile and invokes docker kill + docker rm -f; cidfile unlinked in finally on every code path; build.timeout_s + clone_timeout_s consumed by ensure_image; --global-timeout on CLI.
4. **Recipe migration** — all 5 recipes carry category+detail; hermes STOCHASTIC verdict remapped; idempotent migration script retained for audit.
5. **Taxonomy regression tests** — 14 test classes / 32 tests; all 9 live categories covered by ≥1 fixture; W5 kill-path gate asserts docker kill actually fires.

One note on requirements cross-reference: D-01 through D-05 are phase-internal requirements in 10-CONTEXT.md, not entries in the project's global REQUIREMENTS.md (which uses FND/SBX/AUTH/etc. IDs). No global requirements map to Phase 10. This is consistent with the framework maturity roadmap being a parallel track to the v1 product requirements.

---

_Verified: 2026-04-16T22:00:00Z_
_Verifier: Claude (gsd-verifier)_
