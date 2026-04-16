# Phase 10: error-taxonomy-timeout-enforcement — Context

**Gathered:** 2026-04-16
**Status:** Ready for planning
**Source:** Direct elicitation (orchestrator captured 5 locked decisions + roadmap P05 scope)

<domain>
## Phase Boundary

Replace today's single `{verdict: PASS|FAIL}` with a category-aware verdict carrying `{category, detail, verdict}`, and wire real timeout enforcement so that runaway containers are actually killed (not just abandoned by the subprocess).

This is the "framework floor" follow-on to Phase 09 (lint + test harness): 09 made recipes structurally valid, 10 makes failures legible + bounded. Next-downstream consumers — the future Go orchestrator and phases 11-17 — depend on distinguishing `BUILD_FAIL` from `ASSERT_FAIL` from `TIMEOUT`.

Not in scope for this phase:
- `STOCHASTIC` category (reserved placeholder; implemented in phase 15)
- `SKIP` semantics for `known_incompatible_cells` (reserved placeholder; surfaced in later UX phase)
- Rich CLI output formatting (colored tables, etc.) — minimal category-name-next-to-verdict is all this phase ships
- Parallel multi-cell execution — one cell at a time stays the model
</domain>

<decisions>
## Implementation Decisions

### D-01. Category set (frozen, with reserved placeholders)

The 9 live categories shipped in this phase:

| Category | Meaning |
|---|---|
| `PASS` | Recipe ran end-to-end and `pass_if` evaluated true |
| `ASSERT_FAIL` | Runner completed; `pass_if` evaluated false |
| `INVOKE_FAIL` | `docker run` exited non-zero before `pass_if` could be evaluated |
| `BUILD_FAIL` | `docker build` failed (upstream_dockerfile mode) |
| `PULL_FAIL` | `docker pull` failed (image_pull mode) |
| `CLONE_FAIL` | `git clone` / `git checkout` failed before build |
| `TIMEOUT` | Container exceeded `smoke.timeout_s` and was killed |
| `LINT_FAIL` | Recipe failed schema validation (already implemented in phase 09) |
| `INFRA_FAIL` | Docker daemon unavailable, disk full, host-level failure |

Two placeholder enum values reserved for future phases but NOT implemented in phase 10:
- `STOCHASTIC` — multi-run verdict couldn't reach agreement (phase 15)
- `SKIP` — cell listed in `known_incompatible_cells` and was intentionally not run (later phase)

The schema enum MUST include all 11 values now (9 live + 2 placeholders) so future phases don't require schema migration. Categories not yet emitted by the runner are documented with a `# reserved — phase XX` comment in `docs/RECIPE-SCHEMA.md`.

### D-02. Verdict shape (flat, category-primary)

```yaml
# BEFORE (v0.1)
verified_cells:
  - model: anthropic/claude-haiku-4-5
    verdict: PASS
    wall_time_s: 2.42
    notes: "..."

# AFTER (v0.1, phase 10)
verified_cells:
  - model: anthropic/claude-haiku-4-5
    category: PASS
    detail: ""                       # free-form, may be empty when category=PASS
    verdict: PASS                    # kept for backwards compat, derived (PASS iff category==PASS)
    wall_time_s: 2.42
    notes: "..."
```

Rules:
- `category` is the authoritative field; enum validated by schema.
- `verdict` is a derived string: `PASS` when `category == PASS`, `FAIL` otherwise. Schema enum stays `["PASS", "FAIL"]`. Runner writes it; consumers are free to ignore.
- `detail` is free-form, single-line string. Convention: the exact subprocess stderr tail or a one-line summary of why the category fired. Empty string when category=PASS is acceptable.
- Same shape applies to `known_incompatible_cells[]`.

### D-03. Timeout plumbing — enforce with `docker kill`

Three timeout fields in the recipe, one global CLI flag:

| Field | Default | What it bounds |
|---|---|---|
| `smoke.timeout_s` | 180 | Container wall time for a single smoke invocation |
| `build.timeout_s` | 900 | `docker build` wall time |
| `build.clone_timeout_s` | 300 | `git clone` + checkout wall time |
| `--global-timeout` (CLI) | `None` | Ceiling across the entire runner invocation; overrides the above |

Enforcement mechanism (critical — `subprocess.run(timeout=)` alone does NOT kill the container):

1. Launch `docker run` with `--cidfile /tmp/<uuid>.cid` so we know the container ID.
2. Wrap the `subprocess.run()` in a try/except around `TimeoutExpired`.
3. On expiry: read the cidfile, call `docker kill <cid>` (SIGKILL, no grace period), then `docker rm -f <cid>` to reap.
4. Return `{category: TIMEOUT, detail: f"exceeded smoke.timeout_s={timeout_s}s"}`.

Same pattern for `build.timeout_s` (kill the `docker build` process — but Docker daemon will finish its current layer; accept this limitation and document it) and `build.clone_timeout_s` (straightforward `subprocess` kill; no container to reap).

### D-04. Backwards-compat migration of existing `verified_cells[]`

One-time migration applied to all 5 committed recipes (hermes, openclaw, picoclaw, nullclaw, nanobot) as part of this phase:
- Add `category: PASS` to every existing verified cell (the verdict was `PASS`, so category is `PASS`).
- Add `detail: ""` to every existing verified cell.
- Keep `verdict: PASS` in place (now derived but still valid).
- For `known_incompatible_cells[]`: add `category: ASSERT_FAIL` (since those cells reached the agent but refused the persona) with `detail` copied from the existing `notes` first sentence, OR add `category: STOCHASTIC` when the `notes` explicitly describe flapping (hermes × gemini-2.5-flash is the one known case — but since STOCHASTIC is a reserved placeholder in this phase, temporarily map it to `ASSERT_FAIL` with `detail: "flapping verdict — see notes"` until phase 15 lands).

All 5 recipes MUST still pass lint after the migration.

### D-05. CLI output — minimal, parseable

Runner output today:
```
PASS hermes (anthropic/claude-haiku-4-5) 2.42s
```

Phase 10 output:
```
PASS      hermes (anthropic/claude-haiku-4-5) 2.42s
TIMEOUT   hermes (openai/gpt-4o-mini) 180.00s — exceeded smoke.timeout_s=180s
BUILD_FAIL nullclaw (...) 12.3s — docker build exit 125
```

Format: `<CATEGORY pad 10>  <recipe> (<model>) <wall_time_s>s — <detail>`. No ANSI colors added beyond what phase 09 introduced (green PASS / red everything else). The `--json` flag (from the earlier debt queue, not necessarily shipped in this phase) should emit `{"category": "...", "detail": "...", "verdict": "..."}` when it exists; if it doesn't exist yet, defer it to a follow-up.

### Claude's Discretion
- Internal Python representation: dataclass vs TypedDict vs dict — planner's call.
- Exact fixture count per category for the taxonomy tests — minimum 1 per live category, planner picks.
- Whether to refactor `main()` into sub-functions per category-producing phase (build / pull / clone / invoke / assert). Planner's call — lean toward YES if the current `main()` is long enough to justify it.
- Whether to add a `--timeout-override` CLI flag for ad-hoc testing. Nice-to-have, not required.
- Docker daemon unavailability detection: `docker version` pre-flight vs caught subprocess error. Planner's call.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase dependencies (hard)
- `tools/ap.recipe.schema.json` — JSON Schema that must grow the new fields + enum values
- `tools/run_recipe.py` — the runner; today hardcodes `verdict: PASS/FAIL`, needs to emit categories
- `tools/tests/test_lint.py`, `tools/tests/test_recipe_regression.py`, `tools/tests/test_roundtrip.py` — existing test harness the migrated recipes must still pass
- `recipes/*.yaml` — the 5 committed recipes that need backwards-compat migration (D-04)

### Roadmap + prior phases
- `.planning/FRAMEWORK-MATURITY-ROADMAP.md` §"Phase 05 — Error taxonomy + timeout enforcement" — source scope
- `.planning/phases/09-spec-lint-test-harness-foundations/09-01-SUMMARY.md` — `lint_recipe()` / `load_recipe()` / `evaluate_pass_if()` importable functions this phase extends
- `docs/RECIPE-SCHEMA.md` — must be updated in sync (addressed by phase 17, but this phase should keep it from drifting)

### Steal-from prior art (from roadmap)
- Inspect AI 5-layer limit model (`time_limit`, `working_limit`, `message_limit`, `token_limit`, `cost_limit`): shape of `{category, detail}` is analogous to their `EvalSampleLimit(type, limit, usage)`
- SWE-bench `ResolvedStatus` enum + constants (`APPLY_PATCH_FAIL`, `INSTALL_FAIL`, `TESTS_TIMEOUT`, `TESTS_ERROR`): right granularity reference
</canonical_refs>

<specifics>
## Specific Ideas

- The `--cidfile` pattern is the idiomatic way to reap containers on timeout — see Docker SDK docs. Runner should `tempfile.NamedTemporaryFile(delete=False)` to own the cidfile lifecycle.
- `docker kill` sends SIGKILL by default; that's what we want for TIMEOUT (no grace period — the container already overshot).
- Pre-flight check: the runner can call `docker version` (or `subprocess.run(["docker", "version"], check=False)`) once at startup and return `INFRA_FAIL` if the daemon is unreachable, rather than letting `docker build` fail with a cryptic error.
- Taxonomy tests should live under `tools/tests/test_categories.py` (new file) — one `test_<category>_fires` per live category. Use mocked subprocess return codes (already a pattern in `test_pass_if.py`) to synthesize each failure mode.
- Category migration for the 5 committed recipes: a small `scripts/migrate_recipes_phase10.py` one-shot script is fine, as long as it's run once, committed, then removed. Or an Edit-by-hand approach — whichever the planner picks.
</specifics>

<deferred>
## Deferred Ideas

- `STOCHASTIC` emission (phase 15 — stochasticity / multi-run determinism)
- `SKIP` emission for `known_incompatible_cells[]` (later UX phase)
- `--json` structured output mode (earlier debt item; defer to when it's picked up)
- Colored table output, wide CLI formatting (later UX phase)
- Parallel cell execution with per-cell timeout aggregation (out of scope for the foreseeable)
- Cost-based limits (Inspect AI's `cost_limit`) — requires metering plumbing that belongs with the Go orchestrator, not the recipe runner

---

*Phase: 10-error-taxonomy-timeout-enforcement*
*Context gathered: 2026-04-16 via direct elicitation*
</deferred>
