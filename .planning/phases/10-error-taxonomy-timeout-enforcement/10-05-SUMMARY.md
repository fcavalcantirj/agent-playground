---
phase: 10-error-taxonomy-timeout-enforcement
plan: 05
subsystem: testing
tags: [pytest, testing, taxonomy, mock-subprocess, fixtures, cidfile, docker-kill, redaction]

# Dependency graph
requires:
  - phase: 10-error-taxonomy-timeout-enforcement
    provides: "Plan 10-04 runner taxonomy — Category(str, Enum) + Verdict dataclass + ensure_image/run_cell/preflight_docker/emit_verdict_line on which these tests assert behavior"
  - phase: 10-error-taxonomy-timeout-enforcement
    provides: "Plan 10-03 schema tightening — lint_recipe errors used in TestLintFailCategory"
  - phase: 09-spec-lint-test-harness-foundations
    provides: "pytest harness + conftest fixture pattern (yaml_rt, schema, mock_subprocess, minimal_valid_recipe) on which the three new fixtures layer"
provides:
  - "tools/tests/test_categories.py — 14 test classes / 32 tests covering all 9 live categories (PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL, PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL, INFRA_FAIL) + Enum shape + Verdict shape + Cidfile lifecycle + Emit format + Redaction"
  - "mock_subprocess_timeout fixture (conftest.py) — TimeoutExpired injection + optional recorded invocation list for reap-path assertions"
  - "mock_subprocess_dispatch fixture (conftest.py) — per-argv-prefix return-code dispatcher for driving BUILD_FAIL / PULL_FAIL / CLONE_FAIL / INVOKE_FAIL paths"
  - "fake_cidfile fixture (conftest.py) — pre-populates /tmp/ap-cid-<uuid>.cid on disk and patches run_recipe.Path so run_cell's cidfile construction resolves to a known-content file"
  - "W5 D-03 maturity gate: TestCidfileLifecycle::test_docker_kill_invoked_on_timeout asserts `docker kill <cid>` AND `docker rm -f <cid>` fire with the exact CID from the cidfile when TimeoutExpired raises"
  - "API-key redaction regression (TestInvokeFailCategory::test_invoke_fail_redacts_api_key) — asserts raw secret value appears in neither verdict.detail nor details.stderr_tail"
affects:
  - "11-linux-host-owner-uid-correctness (INVOKE_FAIL test shape reusable for uid-mismatch test fixtures)"
  - "15-stochasticity-multi-run-determinism (Category.STOCHASTIC reserved slot already covered by TestCategoryEnum; phase 15 lights up emission)"
  - "16-dead-verb-coverage-fake-agent-fixture (mock_subprocess_dispatch is the canonical shape for fake-agent test drivers)"
  - "17-doc-runner-sync-check (TestCategoryEnum::test_enum_ordering is the source of truth for doc/code sync validation)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "conftest factory-fixture pattern — @pytest.fixture returns a _configure() callable so tests parameterize the mock from inside the test body"
    - "monkeypatch-scoped subprocess.run injection — each factory uses monkeypatch.setattr(subprocess, 'run', fake_run) so fakes auto-unwind at test end (no global leak)"
    - "Path-ctor interception for /tmp/ap-cid-* — patch run_recipe.Path (not pathlib.Path globally) to redirect ONLY the cidfile path while every other Path construction stays real"
    - "recorded-invocations list pattern — fixture closes over a list that the fake accumulates into on every non-docker-run call; tests assert reap-path membership (docker kill / docker rm -f)"
    - "one-class-per-category test module — 9 TestXxxCategory classes + 5 shared-concern classes (Enum, Verdict, CidfileLifecycle, EmitFormat, Redaction); each class is a readable audit unit for the D-01 taxonomy"
    - "fully-mocked test budget — 32 tests in 0.89s wall time with zero live Docker / zero network (lint test is the only slow one at ~0.87s due to jsonschema validator init)"

key-files:
  created:
    - "tools/tests/test_categories.py (+564 lines; 14 classes / 32 tests covering the 9-live-category taxonomy + Enum/Verdict/Cidfile/Emit/Redaction concerns)"
  modified:
    - "tools/tests/conftest.py (+123 lines; three new fixture factories mock_subprocess_timeout / mock_subprocess_dispatch / fake_cidfile — existing 5 fixtures unchanged)"

key-decisions:
  - "Task 1 committed as `feat` (not RED→GREEN) — fixtures are factory callables with no standalone behavior to RED-fail against; the fixture gate is Task 2's consumer tests (where RED would mean 'fixtures missing AttributeError'). Commit sequence: feat(10-05) fixtures, then test(10-05) category tests."
  - "Task 2 committed as `test` — all 32 tests pass against Plan 10-04's existing run_recipe.py surface. These are regression/coverage gates over already-implemented behavior; no implementation changed in Plan 05, so a literal TDD RED wasn't applicable. The authoritative RED→GREEN for the runner rewrite lived in Plan 10-04 (commits 7784457 RED + d7efc52 GREEN)."
  - "Preserved plan's fake_cidfile design: patch run_recipe.Path (not pathlib.Path globally). run_cell imports Path via `from pathlib import Path` — so the symbol `Path` in run_recipe's namespace is what it resolves; patching that redirects cidfile construction without breaking any other Path consumer in any module."
  - "Used `output=` (not `stdout=`) kwarg on subprocess.TimeoutExpired in mock_subprocess_timeout — matches the real signature (Plan 10-04 caught this same typo in its own RED phase). This prevents the cidfile reap test from raising TypeError instead of exercising TimeoutExpired."
  - "TestLintFailCategory kept intentionally minimal (one test) — the 9-case LINT_FAIL emission matrix (missing-name, missing-build-mode, wrong-api-version, etc.) lives in the pre-existing tests/test_lint.py and tests/broken_recipes/ fixtures; duplicating it here would be redundant. The Plan 05 requirement is that the category emission code path has >=1 fixture — that bar is cleared."

patterns-established:
  - "Taxonomy test file layout: one class per live category + one class per shared primitive (Enum / Verdict / Cidfile / EmitFormat / Redaction) — future phases adding new categories (e.g., Category.STOCHASTIC emission in phase 15) slot in a new TestStochasticCategory class with the same pattern"
  - "Factory-fixture with recorded-invocations list: mock_subprocess_timeout returns the list so the test body can assert post-hoc that `docker kill` / `docker rm -f` fired. Cleaner than a separate spy fixture and preserves the single-source-of-truth for the subprocess mock"
  - "W5 gate idiom: when a plan requires 'X *actually* happens when Y fires', write a test that both (a) sets up the precondition on disk (fake_cidfile) AND (b) captures the side-effect (recorded invocations). Assert on both endpoints — the precondition content and the side-effect payload"

requirements-completed: [D-01, D-02, D-03]

# Metrics
duration: 14min
started: 2026-04-16T21:15:00Z
completed: 2026-04-16T21:29:00Z
---

# Phase 10 Plan 05: Taxonomy Regression Tests Summary

**Every live category in the 9-value D-01 taxonomy is now producible by >=1 pytest fixture; W5's test_docker_kill_invoked_on_timeout asserts the load-bearing D-03 promise that `docker kill <cid>` + `docker rm -f <cid>` actually fire when a populated cidfile meets TimeoutExpired.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-04-16T21:15:00Z
- **Completed:** 2026-04-16T21:29:00Z
- **Tasks:** 2 (Task 1 fixtures + Task 2 test module)
- **Files modified:** 2 (conftest.py extended + test_categories.py created)

## Accomplishments

- **9/9 live categories covered.** Each of PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL, PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL, INFRA_FAIL has >=1 test method exercising the code path that emits it.
- **W5 kill-path gate landed.** TestCidfileLifecycle::test_docker_kill_invoked_on_timeout pre-populates a cidfile with a known CID, injects TimeoutExpired, and asserts the recorded subprocess invocations include `["docker", "kill", "fake-cid-abc123"]` AND `["docker", "rm", "-f", "fake-cid-abc123"]`. Without this, a regression that hides the kill call behind a dead branch would pass CI silently.
- **Three new conftest fixtures shipped.** `mock_subprocess_timeout` (TimeoutExpired injector + optional recorded-call list), `mock_subprocess_dispatch` (per-argv-prefix rc dispatcher), `fake_cidfile` (disk-populated cidfile + run_recipe.Path patch). All three use monkeypatch so auto-unwind at test end.
- **API-key redaction regression asserted.** TestInvokeFailCategory::test_invoke_fail_redacts_api_key leaks a realistic `OPENROUTER_API_KEY=sk-secret-abc123` pattern through subprocess stderr and asserts the raw secret appears in NEITHER `verdict.detail` NOR `details["stderr_tail"]` — covers the V7/V8 Security Domain mitigations end-to-end.
- **Cidfile-leak regression asserted.** TestCidfileLifecycle::test_no_stale_cidfiles_after_success snapshots /tmp before and after a successful run_cell invocation and fails if any `ap-cid-*.cid` leaks through.
- **Test budget held.** 32 new tests run in 0.89s; slowest test is TestLintFailCategory at 0.87s (Draft202012Validator init cost). Full pytest suite (121 tests: 89 existing + 32 new) completes in 1.34s. Zero live Docker, zero network.
- **Zero regression.** All 89 pre-existing tests continue to pass. No run_recipe.py edits were needed to reconcile with Plan 10-04's contract — every category emission behaved exactly as Plan 04's SUMMARY claimed.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend conftest with timeout/dispatch/cidfile fixtures** — `400db78` (feat)
2. **Task 2: Add taxonomy regression tests (9 live categories + W5 kill-path gate)** — `cf9c547` (test)

_Note on TDD cadence: Task 1 shipped as a single `feat` commit because pytest fixtures are factory callables with no standalone behavior to RED-fail against; the fixture gate is Task 2's consumer tests. Task 2 shipped as a single `test` commit because all 32 tests PASS against Plan 10-04's already-implemented runner surface — there is no new implementation to RED→GREEN against. The literal TDD RED→GREEN cycle for the runner rewrite lived in Plan 10-04 (commits `7784457` RED + `d7efc52` GREEN); Plan 10-05 adds the regression gates on top of that green baseline._

## Files Created/Modified

- **`tools/tests/test_categories.py`** (new, +564 lines) — 14 test classes, 32 test methods, covers all 9 live categories of the D-01 taxonomy plus Enum shape, Verdict shape, Cidfile lifecycle (including W5 kill-path gate), emit_verdict_line format, and _redact_api_key helper.
- **`tools/tests/conftest.py`** (modified, +123 lines) — three new fixture factories added AFTER the existing `mock_subprocess` fixture (line 52) and BEFORE the `minimal_valid_recipe` fixture (line 55). Existing `yaml_rt` / `schema` / `mock_subprocess` / `minimal_valid_recipe` / `broken_recipes_dir` fixtures untouched.

## Category → Test Mapping

| Category | Test class | Test method(s) | Emission site under test |
|----------|------------|----------------|--------------------------|
| `PASS` | TestPassCategory | test_pass_when_pass_if_true | run_cell rc=0 + pass_if match |
| `ASSERT_FAIL` | TestAssertFailCategory | test_assert_fail_when_pass_if_false | run_cell rc=0 + pass_if miss |
| `INVOKE_FAIL` | TestInvokeFailCategory | test_invoke_fail_when_rc_nonzero, test_invoke_fail_redacts_api_key | run_cell rc!=0 + redaction |
| `BUILD_FAIL` | TestBuildFailCategory | test_build_fail_when_docker_build_rc_nonzero | ensure_image upstream_dockerfile path |
| `PULL_FAIL` | TestPullFailCategory | test_pull_fail_when_docker_pull_rc_nonzero | ensure_image image_pull path |
| `CLONE_FAIL` | TestCloneFailCategory | test_clone_fail_when_git_clone_rc_nonzero | ensure_image pre-build git clone |
| `TIMEOUT` | TestTimeoutCategory | test_timeout_produces_TIMEOUT_verdict | run_cell subprocess.TimeoutExpired |
| `TIMEOUT` (W5 reap) | TestCidfileLifecycle | test_docker_kill_invoked_on_timeout | run_cell kill-path via cidfile content |
| `LINT_FAIL` | TestLintFailCategory | test_lint_fail_on_invalid_recipe | lint_recipe (emission driven by main) |
| `INFRA_FAIL` | TestInfraFailCategory | test_infra_fail_when_docker_version_fails, test_infra_fail_when_docker_version_times_out, test_infra_fail_when_docker_cli_missing, test_no_verdict_when_docker_version_ok | preflight_docker (3 fail paths + happy path) |

Plus shared-concern classes:

| Concern | Test class | Count |
|---------|------------|-------|
| Enum shape (11-value order, reserved STOCHASTIC/SKIP, str subclass) | TestCategoryEnum | 4 |
| Verdict shape (derived verdict, to_cell_dict, frozen) | TestVerdictShape | 5 |
| Cidfile lifecycle (unlinked on timeout, no leak on success, W5 kill-path) | TestCidfileLifecycle | 3 |
| Emit format (green PASS, red non-PASS, no em-dash when empty) | TestEmitFormat | 3 |
| Redaction helper (exact var, empty input, no match, multiple instances) | TestRedaction | 4 |

**Total:** 14 classes / 32 tests / 564 LoC / 0.89s wall time.

## Runtime Benchmark

```
$ pytest tests/test_categories.py -q --durations=5
================================ 32 passed in 0.89s =============================
============================= slowest 5 durations ==============================
0.87s call  tests/test_categories.py::TestLintFailCategory::test_lint_fail_on_invalid_recipe
(4 durations < 0.005s hidden.  Use -vv to show these durations.)
```

- **Total wall time:** 0.89s (budget: <5s). Well within budget.
- **Slowest test:** TestLintFailCategory (0.87s) — almost entirely Draft202012Validator schema initialization inside lint_recipe's first invocation. Not mock-related; cannot be trimmed without caching the validator instance (out of scope for Plan 05).
- **Full suite:** `pytest -q` → 121 passed in 1.34s (89 existing + 32 new).

## W5 Gate Confirmation

`pytest tests/test_categories.py::TestCidfileLifecycle::test_docker_kill_invoked_on_timeout -v`:

```
tests/test_categories.py::TestCidfileLifecycle::test_docker_kill_invoked_on_timeout PASSED [100%]
============================== 1 passed in 0.01s ===============================
```

The test asserts, in sequence:
1. `fake_cidfile(cid="fake-cid-abc123")` writes the CID to disk and returns a Path.
2. `mock_subprocess_timeout(timeout_s=1, record=True)` installs the TimeoutExpired raiser AND a list that accumulates non-docker-run subprocess invocations.
3. `run_cell(...)` hits the docker-run mock, raises TimeoutExpired, enters the finally block, reads the cidfile content, and invokes `subprocess.run(["docker", "kill", "fake-cid-abc123"], ...)` followed by `subprocess.run(["docker", "rm", "-f", "fake-cid-abc123"], ...)`.
4. The returned Verdict is `Verdict(Category.TIMEOUT, "exceeded smoke.timeout_s=1s")` → `verdict.verdict == "FAIL"`.
5. `recorded` contains both `["docker", "kill", "fake-cid-abc123"]` AND `["docker", "rm", "-f", "fake-cid-abc123"]`.
6. The cidfile is unlinked (`cidfile_path.exists() is False`).

All six assertions pass. **D-03's core promise — "on TIMEOUT, the runaway container actually dies" — is now guarded by CI.**

## Plan 04 Contract Confirmation

Every category emission site in Plan 04's SUMMARY held under test scrutiny. **Zero run_recipe.py edits were needed** to reconcile with Plan 05's tests. Specifically:

- Category enum order, values, and reserved slots match TestCategoryEnum expectations exactly.
- Verdict frozen dataclass + derived verdict property + to_cell_dict shape match TestVerdictShape.
- preflight_docker's three failure paths + happy path match TestInfraFailCategory (including the exact detail substrings: "docker version exit 1", "unresponsive", "not in PATH").
- run_cell's PASS / ASSERT_FAIL / INVOKE_FAIL / TIMEOUT branches match per-category tests (including API-key redaction and cidfile-reap-on-timeout).
- ensure_image's BUILD_FAIL / PULL_FAIL / CLONE_FAIL branches match per-category tests.
- emit_verdict_line's green-PASS / red-non-PASS / em-dash-detail format matches TestEmitFormat.
- _redact_api_key's four edge cases (exact var, empty input, no match, multi-instance) match TestRedaction.

No implementation changes. Plan 04 shipped with the contract already airtight.

## Decisions Made

- **Task 1 as single `feat` commit (not RED→GREEN).** A pytest fixture factory is not a testable unit on its own — its behavior is only observable through consumer tests. The literal TDD RED would be "Task 2 tests AttributeError because fixtures missing" which is implicit in a monorepo test commit ordering. Choosing a clean `feat` commit for the fixture add makes the git log more honest about what actually landed.
- **Task 2 as single `test` commit.** All 32 tests pass against Plan 10-04's existing run_recipe.py. Plan 05 does not change any implementation code; it adds regression gates over already-implemented behavior. The commit type `test(10-05)` accurately reflects this (Conventional Commits: "adding or updating tests").
- **Kept fake_cidfile patching run_recipe.Path, not pathlib.Path globally.** run_cell imports Path via `from pathlib import Path` at module load, so the symbol it uses is bound in run_recipe's namespace. Patching run_recipe.Path redirects ONLY run_cell's cidfile construction; patching pathlib.Path globally would break every other module in the same test. This is the canonical Python monkeypatch-at-the-consumer-namespace idiom.
- **TestLintFailCategory kept to a single test (not 9 — one per broken_recipes/*.yaml fixture).** The broad LINT_FAIL emission matrix already lives in tests/test_lint.py with 12 fixtures in tests/broken_recipes/. The Plan 05 requirement is "every live category has >=1 test fixture that exercises the code path producing it" — one test clears that bar. Duplicating 12 broken recipes here would be redundant without adding coverage.
- **Used `output=""` (not `stdout=""`) in mock_subprocess_timeout's TimeoutExpired raise.** The real kwarg is `output`; Plan 10-04 caught the same typo in its RED phase (see Plan 04 SUMMARY deviation #1). Starting Plan 05 with the correct kwarg avoids repeating that mistake in the fixture itself, which would silently break TestTimeoutCategory + the W5 gate if every category test raised TypeError before exercising the TIMEOUT path.

## Deviations from Plan

None — plan executed exactly as written. Every test class, method, and fixture listed in Task 1 and Task 2 behaviors was implemented as specified. No auto-fixes needed (Plan 10-04's implementation was already correct against all the test expectations).

## Issues Encountered

None. The fixture additions to conftest landed on the first edit; all 32 tests passed on the first pytest run.

## Threat Surface Scan

No new security-relevant surface. Per plan's `<threat_model>`:

- **T-10-11 (Information Disclosure: test accidentally uses real api_key_val):** Mitigated. Every test uses literal `"fake-key"` or `"sk-secret-abc123"`. No `os.environ` reads, no `.env` loads.
- **T-10-12 (Availability: test pollution from stale /tmp state):** Mitigated. TestBuildFailCategory + TestCloneFailCategory both use `shutil.rmtree(fake_clone, ignore_errors=True)` in setup or try/finally.
- **T-10-13 (Tampering: monkeypatch leaks):** Mitigated. All three new fixtures use `monkeypatch.setattr(...)` exclusively; pytest auto-unwinds at test end.

No new network endpoints, no new file-access patterns, no schema changes.

## Self-Check: PASSED

Verification performed after SUMMARY.md write:

- **Task commits exist on disk:**
  - `400db78` — `git log --oneline` shows `feat(10-05): extend conftest with timeout/dispatch/cidfile fixtures` ✓
  - `cf9c547` — `test(10-05): add taxonomy regression tests — 9 live categories + W5 kill-path gate` ✓
- **Files created/modified exist:**
  - `tools/tests/test_categories.py` — FOUND (564 lines) ✓
  - `tools/tests/conftest.py` — MODIFIED (+123 lines; 3 new fixtures) ✓
- **Plan verification commands all PASS:**
  - `python3 -c "import ast; ast.parse(open('tests/test_categories.py').read())"` → 0 ✓
  - `python3 -c "import ast; ast.parse(open('tests/conftest.py').read())"` → 0 ✓
  - `pytest tests/test_categories.py -x -q` → 32 passed in 0.89s ✓
  - `pytest tests/test_categories.py -q --durations=5` → slowest 0.87s, under 5s budget ✓
  - `pytest tests/test_categories.py::TestCidfileLifecycle::test_docker_kill_invoked_on_timeout -v` → PASSED ✓
  - `pytest -q` (full suite) → 121 passed in 1.34s ✓
- **Grep thresholds all met:**
  - `class Test` count in test_categories.py = 14 (plan >=12) ✓
  - `test_docker_kill_invoked_on_timeout` count = 1 (plan >=1) ✓
  - `Category.` references in test_categories.py = 30 (plan >=30) ✓
  - fixture names in conftest.py = 5 (3 new fixtures named twice each; plan >=3 distinct names) ✓

## Next Phase Readiness

- **P05 roadmap exit gate is passed.** "Each taxonomy branch producible by >=1 test fixture" — achieved; 9/9 live categories have green tests, plus shared-concern coverage (Enum / Verdict / Cidfile / Emit / Redaction).
- **W5 D-03 maturity gate is passed.** The kill-path regression guards the canonical "runaway container actually dies" promise that D-03 exists to make.
- **Plan 10 scope is complete** pending only the phase-level SUMMARY / STATE roll-up (handled by the orchestrator, not this executor).
- **Phase 15 (stochasticity) can slot in Category.STOCHASTIC emission** without touching the test module structure: add a `TestStochasticCategory` class next to the existing 9 category classes; the Enum tests already accept STOCHASTIC as a reserved value, so nothing else needs to change.
- **Phase 16 (dead-verb-coverage-fake-agent-fixture)** has a ready-made `mock_subprocess_dispatch` fixture to build fake-agent drivers on top of.
- **Phase 17 (doc-runner-sync-check)** has `TestCategoryEnum::test_enum_ordering` as the pure source of truth for the 11-value taxonomy order that docs must match.
- **No blockers.** 121 tests green; 5 committed recipes still lint clean.

---
*Phase: 10-error-taxonomy-timeout-enforcement*
*Completed: 2026-04-16*
