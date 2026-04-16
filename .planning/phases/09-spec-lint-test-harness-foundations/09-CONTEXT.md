# Phase 9: Spec lint + test harness foundations - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the recipe runner a trustworthy, testable tool that catches structural errors before Docker is ever invoked. After Phase 9 ships: no invalid recipe reaches Docker (lint gate), every `pass_if` verb is independently tested without an LLM (mocked fixtures), YAML round-trip is proven lossless, and all downstream phases (10–17) can add features with confidence because the test harness exists.

This is the **gate phase** — Phases 10–17 all depend on the foundation laid here.

**Deliverables:**
1. `ap.recipe.schema.json` — v0.1 JSON Schema with cross-field invariants
2. `--lint` subcommand + `--lint-all` + mandatory pre-step in every run
3. `pytest` suite — pass_if verbs, lint negatives, ruamel round-trip, recipe regression
4. `pyproject.toml` + Makefile targets + minimal GitHub Actions CI

</domain>

<decisions>
## Implementation Decisions

### Schema source of truth
- **D-01:** JSON Schema (`ap.recipe.schema.json`) hand-written to match `docs/RECIPE-SCHEMA.md` field tables. Not auto-generated — Phase 17 (doc-runner sync check) enforces alignment.
- **D-02:** Schema uses JSON Schema conditionals (if/then) for cross-field invariants (e.g., `pass_if: response_contains_string` ⇒ `smoke.needle` required). Lint catches everything in one pass.
- **D-03:** `additionalProperties: false` everywhere — strict schema, rejects unknown keys. Catches typos.
- **D-04:** v0 apiVersion support dropped entirely. Schema validates `ap.recipe/v0.1` only. Remove v0 compat code from runner. All 5 committed recipes already declare v0.1.

### Schema file location
- **D-05:** Schema lives at `tools/ap.recipe.schema.json`, co-located with the runner that consumes it. The runner owns the schema.

### Lint integration
- **D-06:** Lint is a subcommand in `run_recipe.py`: `run_recipe.py --lint <recipe>` validates and exits. Also `--lint-all` walks `recipes/` and lints everything.
- **D-07:** Lint runs automatically as a mandatory pre-step before every `run_recipe.py` invocation. `--no-lint` flag to bypass.
- **D-08:** Lint output is human-readable colored text with clear error messages. No `--json` flag in Phase 9 (add later if needed).
- **D-09:** Exit codes: 0 = PASS, 1 = runtime FAIL, 2 = LINT_FAIL. Distinct from runtime failures. Phase 10 formalizes this into the verdict taxonomy.
- **D-10:** `make lint-recipes` target exposed for CI, calls `run_recipe.py --lint-all`.

### Test harness
- **D-11:** All three test pillars in scope: (1) pass_if verb unit tests with mocked docker output, (2) ≥10 lint negative tests with broken recipe fragments, (3) ruamel round-trip tests over all 5 committed recipes.
- **D-12:** Docker mocking via `pytest monkeypatch` on `subprocess.run` — returns canned stdout/exit_code per test case. No real Docker in unit tests.
- **D-13:** Broken recipe fragments live in `tools/tests/broken_recipes/` directory — dedicated YAML files, each targeting a specific schema violation.
- **D-14:** Parametrized regression test over `recipes/*.yaml` — each committed recipe must pass lint. Catches regressions when schema evolves.
- **D-15:** Test suite must complete in <10 seconds total. No Docker, no network, no LLM calls.

### Runner refactoring
- **D-16:** Minimal extraction for testability: extract `evaluate_pass_if()`, `load_recipe()`, and the lint function into importable functions (no globals). Keep the rest of the 579-line script as-is. Tests import the extracted functions.

### Python packaging
- **D-17:** `tools/pyproject.toml` — modern Python packaging. Runtime deps: `ruamel.yaml`, `jsonschema`. Dev deps in `[project.optional-dependencies]`: `pytest`.
- **D-18:** Tests live at `tools/tests/`. All Python under `tools/`.
- **D-19:** Minimum Python version: >=3.10 in pyproject.toml (dev machine has 3.10.10), CI enforces 3.12+. Relaxed from original 3.12+ per user approval 2026-04-15.
- **D-20:** Makefile targets: `make install-tools` (pip install -e tools/[dev]), `make test` (pytest tools/tests/), `make lint-recipes` (run_recipe.py --lint-all), `make check` (lint-recipes + test chained).

### CI pipeline
- **D-21:** Minimal GitHub Actions workflow (`.github/workflows/test-recipes.yml`) that runs `make check` on push/PR. Python tooling only — no Go tests, no deploy. Phase 7 expands it.

### Claude's Discretion
- Test directory structure within `tools/tests/` (flat vs nested)
- `conftest.py` fixture design (temp recipe builder, mock subprocess helpers)
- Schema Draft version (2020-12 vs 2019-09)
- Lint output formatting details (colors, indentation)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Recipe specification
- `docs/RECIPE-SCHEMA.md` — Canonical v0.1 spec. The JSON Schema MUST match every field table in this doc.
- `recipes/hermes.yaml` — Reference recipe exercising the most complex features (stdout_filter, known_incompatible_cells)
- `recipes/openclaw.yaml` — Reference recipe with sh-chained multi-command invocation
- `recipes/picoclaw.yaml` — Reference recipe with entrypoint override
- `recipes/nullclaw.yaml` — Reference recipe with two-step agent chaining
- `recipes/nanobot.yaml` — Reference recipe with JSON config heredoc

### Runner implementation
- `tools/run_recipe.py` — The runner to add lint to and extract testable functions from

### Framework maturity plan
- `.planning/FRAMEWORK-MATURITY-ROADMAP.md` — Phase 04 section (maps to our Phase 9) details the exact steal-from-prior-art patterns and exit gate
- `recon/prior-art-research.md` — Prior art research (METR, promptfoo, Inspect AI, SWE-bench, devcontainer, Cog) informing design decisions

### Existing schemas (reference only, not to modify)
- `agents/schemas/recipe.schema.json` — v1 platform schema for the Go loader. Separate concern. Do NOT modify or reuse for v0.1 lint.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tools/run_recipe.py` — 579 lines, contains `evaluate_pass_if()` (5 verbs), `run_cell()`, `ensure_image()`, `writeback_cell()`. These are the extraction targets for D-16.
- `test/smoke-matrix.sh` and `test/drop-in.sh` — existing shell-based test scripts (Gate A/B from Phase 02.5). Not replaced by pytest but coexist.

### Established Patterns
- Runner uses `ruamel.yaml` for YAML round-trip (preserves comments, ordering)
- Runner uses `subprocess.run` for all Docker operations — monkeypatchable
- Runner's `--all-cells` mode already iterates all recipes — `--lint-all` follows the same pattern
- All 5 recipes use `apiVersion: ap.recipe/v0.1`

### Integration Points
- `Makefile` at repo root — add `install-tools`, `test`, `lint-recipes`, `check` targets
- `.github/workflows/` — new `test-recipes.yml` for CI
- `tools/` directory — `pyproject.toml`, `tests/`, `ap.recipe.schema.json` all land here

</code_context>

<specifics>
## Specific Ideas

- User emphasized wanting a "mature specification and runner, validator" — this phase is about rigor, not features.
- The Cog pattern (JSON Schema as artifact, generated once, consumed by lint) is the model. But hand-written, not auto-generated — with Phase 17 as the drift-catch safety net.
- devcontainer anti-pattern explicitly called out in framework roadmap: they have a JSON Schema but the CLI doesn't enforce it. We MUST enforce it via mandatory pre-step.

</specifics>

<deferred>
## Deferred Ideas

- **JSON output from lint** — add `--json` flag when needed (Phase 10 or later)
- **Auto-generation of schema from RECIPE-SCHEMA.md** — considered and rejected for Phase 9. Phase 17 sync test is the alternative.
- **Full runner refactor into modules** — minimal extraction only in Phase 9. Full modularization if needed in later phases.
- **Schema publication to schemastore.org** — future OSS hardening (Phase 7) scope.

</deferred>

---

*Phase: 09-spec-lint-test-harness-foundations*
*Context gathered: 2026-04-15*
