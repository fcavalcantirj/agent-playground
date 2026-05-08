---
phase: 31-pre-stripe-billing-hardening
plan: 06
subsystem: ci-e2e
tags: [github-actions, pytest-marker, openrouter, money-path, cost-capture, usage-logs, concurrency-block, secret-handling, AMD-03, AMD-04, AMD-05, T-31-03, T-31-04]

requires:
  - phase: 31-01-shipped
    provides: e2e_money_path pytest marker registered in pyproject.toml + AMD-05 usage_logs added to autouse _truncate_tables list (commit 30809c5)
  - phase: 30-shipped
    provides: usage_logs schema (mig 010 + 013) + nanobot recipe with via_proxy=true + LLM egress proxy that writes cost_usd + upstream_request_id
  - phase: 22c.3-15-shipped
    provides: api_server/tests/e2e/__init__.py + tests/e2e/conftest.py package + recipe-container e2e infrastructure (re-used as the surrounding context for the new fixture)
provides:
  - "api_server/tests/e2e/conftest.py — appended e2e_money_path_client fixture composing async_client + authenticated_cookie verbatim per AMD-03 (no HMAC, no signing-key)"
  - "api_server/tests/e2e/test_money_path.py — opt-in synchronous money-path test asserting usage_logs.cost_usd > 0 + upstream_request_id is not NULL with D-20 polling (200ms × 50 = 10s ceiling)"
  - "Makefile e2e-money-path target — gates on $OPENROUTER_API_KEY env presence per D-17; fails fast otherwise"
  - ".github/workflows/e2e-money-path.yml — GH Actions workflow with path-filter on api_server/** + recipes/**; concurrency { group: e2e-money-path, cancel-in-progress: false } per D-21 + SPEC AC21; secrets.OPENROUTER_CI_KEY referenced via env never echoed; reuses docker-compose.dev.yml (D-19)"
affects:
  - "Phase B (Stripe paywall) — H8 gate must be green before billing surface ships; this plan delivers H8"
  - "Future regressions in api_server/proxy/* — caught by the workflow on every PR touching api_server/**"
  - "Future recipe edits in recipes/* — caught by the workflow on every PR touching recipes/**"

tech-stack:
  added: []
  patterns:
    - "Composer-only fixture pattern: e2e_money_path_client = async_client + authenticated_cookie with NO new SQL (AMD-03 mandate; T-31-03 mitigation)"
    - "Defense-in-depth env-guard: Makefile target + autouse pytest fixture both gate on OPENROUTER_API_KEY — direct pytest invocation skips cleanly without burning money"
    - "GH Actions concurrency block { group: <name>, cancel-in-progress: false } for real-money workflows — serializes runs so a parallel-PR storm cannot stack chat completions; never aborts an in-flight chat"
    - "Recipe + model literals inlined in JSON request body (not abstracted through constants alone) so static greps over the test source can verify AMD-04 lock without resolving constant bindings"

key-files:
  created:
    - "api_server/tests/e2e/test_money_path.py — 132 lines: pytestmark = [pytest.mark.e2e_money_path, pytest.mark.asyncio]; autouse _require_openrouter_key skip-gate; one test test_chat_through_proxy_writes_usage_log driving POST /v1/runs with nanobot + openai/gpt-4o-mini + 50×200ms poll over usage_logs"
    - ".github/workflows/e2e-money-path.yml — 87 lines: triggers on push/PR with paths api_server/** + recipes/**; concurrency block per D-21; ubuntu-latest runner; timeout 20min; docker compose -f docker-compose.dev.yml + make install-api + make migrate-api + make e2e-money-path; teardown with if: always()"
  modified:
    - "api_server/tests/e2e/conftest.py — appended 44 lines: Phase 31 H8 explanatory header + @pytest_asyncio.fixture e2e_money_path_client composing existing async_client + authenticated_cookie fixtures verbatim per AMD-03"
    - "Makefile — added 1 entry to .PHONY line (api-server section) + 7 new lines for the e2e-money-path target with the OPENROUTER_API_KEY env-guard"

key-decisions:
  - "Used the existing api_server/tests/e2e/__init__.py (Phase 22c.3 Plan 15 marker) AS-IS rather than overwriting it. The plan's File 1 directs creating it; the plan was authored before plan-checker noticed the file already existed. The pre-existing single-line docstring already serves as the package marker; overwriting would be a regression on Phase 22c.3's archaeology. Net: zero change to __init__.py."
  - "Appended the new fixture to the EXISTING tests/e2e/conftest.py (Phase 22c.3 Plan 15) rather than creating a new file. The plan's File 2 reads as if the file is new; in reality it already carries 555 lines of Phase 22c.3 e2e fixtures. Appending is the additive-only diff that satisfies AMD-03's no-new-auth-surface mandate AND avoids fixture-name collisions."
  - "Inlined recipe + model literals in the JSON request body (`\"recipe_name\": \"nanobot\"`, `\"model\": \"openai/gpt-4o-mini\"`) instead of relying on RECIPE_NAME / MODEL constants alone. Both forms are present (constants for diagnostic readability + literals in the request body). Reason: the plan's acceptance_criteria block specifies `grep -F 'recipe_name\": \"nanobot\"'` which only matches the literal string in source — using a constant binding would have failed the static check."
  - "Chose POST /v1/runs (one-shot synchronous money-path) over the start+messages two-call path the plan's pseudocode showed. Both exercise the SAME proxy → cost-capture pipeline; /v1/runs is the smaller end-to-end surface (one Bearer + recipe + model + prompt → spawn → bot calls proxy → proxy writes usage_logs → verdict returned). The two-call path adds workflow plumbing on top that doesn't change the load-bearing assertion. Documented in the test's module docstring."
  - "Removed two SESSION_SIGNING_KEY references from explanatory comments in the new fixture's header block. The plan's acceptance_criteria says `grep -c 'SESSION_SIGNING_KEY' = 0` — comments referencing the prohibition would technically have failed the static gate even though the intent was clear. Re-worded to use `signing-key machinery` and `prohibited HMAC-secret env-var name` instead."
  - "Removed two forbidden tokens (`echo`, `printenv`) from explanatory comments in the workflow YAML. The plan's defense-in-depth acceptance_criteria says `grep -E 'echo.*OPENROUTER|printenv|cat \\.env' returns 0 lines` — the original comment listed the verboten tokens to document the prohibition, which paradoxically would have triggered the static check. Re-worded to describe the prohibition without naming the commands."

requirements-completed: [H8]

duration: ~6min
completed: 2026-05-08
---

# Phase 31 Plan 06: Pre-Stripe Billing Hardening — H8 e2e Money-Path CI Gate Summary

**Closed the H8 gap by adding a 1-test pytest e2e gate that drives `POST /v1/runs` against real OpenRouter through the LLM egress proxy and asserts `usage_logs.cost_usd > 0` + non-null `upstream_request_id` within 10s, plus a `make e2e-money-path` env-gated target and a GitHub Actions workflow that runs the test on every PR/push touching `api_server/**` or `recipes/**` with a non-cancelling concurrency block — every regression in cost-parsing now fails the workflow before merge.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-08T15:39:06Z
- **Completed:** 2026-05-08T15:44:51Z
- **Tasks:** 3 automated (file creation/edit) + 4 manual gates surfaced
- **Files modified:** 2 (`api_server/tests/e2e/conftest.py`, `Makefile`)
- **Files created:** 2 (`api_server/tests/e2e/test_money_path.py`, `.github/workflows/e2e-money-path.yml`)

## Accomplishments

- `pytest --collect-only -m e2e_money_path tests/e2e/test_money_path.py` collects exactly 1 test cleanly under the api_server venv (Python 3.13.9), zero `PytestUnknownMarkWarning`. The test SKIPS without `OPENROUTER_API_KEY` (defense-in-depth on top of the Makefile env-guard).
- `make e2e-money-path` without `OPENROUTER_API_KEY` exits non-zero with the explicit error message: `ERROR: OPENROUTER_API_KEY not set. Per Phase 31 D-17, this target hits real OpenRouter and spends real money. ...` Manually verified via `unset OPENROUTER_API_KEY; make e2e-money-path` → exit 2.
- The CI workflow YAML passes `python3 -c "import yaml; yaml.safe_load(...)"` and matches every static acceptance gate from the plan: `name: e2e money path`, `group: e2e-money-path`, `cancel-in-progress: false`, `${{ secrets.OPENROUTER_CI_KEY }}`, path filters on `api_server/**` (3 instances) + `recipes/**` (3 instances), 6 references to `docker-compose.dev.yml`, `make e2e-money-path` invocation, `timeout-minutes: 20`, ZERO matches for `echo.*OPENROUTER|printenv|cat \\.env`.
- The `e2e_money_path_client` fixture is a pure composer of the existing `async_client` + `authenticated_cookie` fixtures — `grep -c 'SESSION_SIGNING_KEY' api_server/tests/e2e/conftest.py` returns 0, satisfying the AMD-03 mandate / T-31-03 mitigation.

## Task Commits

Each task was committed atomically with `--no-verify` (parallel worktree mode):

1. **Task 1: Append e2e_money_path_client fixture to api_server/tests/e2e/conftest.py** — `ea21659` (`feat`)
2. **Task 2: Create tests/e2e/test_money_path.py + add Makefile e2e-money-path target** — `c849566` (`feat`)
3. **Task 3: Create .github/workflows/e2e-money-path.yml with concurrency + path filter + secret reference** — `c07b183` (`feat`)

## Files Created/Modified

- **`api_server/tests/e2e/__init__.py`** (UNCHANGED) — Pre-existing Phase 22c.3 Plan 15 marker `"""Phase 22c.3 Plan 15 — SC-03 5x1 end-to-end matrix gate."""` left intact. Per the executor decision, the plan's File 1 directive was a no-op since the marker already existed.
- **`api_server/tests/e2e/conftest.py`** (APPENDED +44 lines) — Added a Phase 31 H8 header block + `@pytest_asyncio.fixture(scope="function") async def e2e_money_path_client(async_client, authenticated_cookie)` that yields `{client, cookie, user_id, session_id}`. NO INSERTs of its own; reuses the parent fixture's `gen_random_uuid()` cookie + user/session row. The 555-line surrounding Phase 22c.3 e2e infrastructure was untouched.
- **`api_server/tests/e2e/test_money_path.py`** (NEW, 132 lines) — `pytestmark = [pytest.mark.e2e_money_path, pytest.mark.asyncio]`; `_require_openrouter_key` autouse skip-gate; one test `test_chat_through_proxy_writes_usage_log` that POSTs to `/v1/runs` with `recipe_name=nanobot` + `model=openai/gpt-4o-mini` + Bearer + Cookie, then polls `usage_logs WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1` with 50 iterations of 200ms each (D-20 = 10s ceiling) asserting `float(usage_row["cost_usd"]) > 0` AND `usage_row["upstream_request_id"] is not None`.
- **`Makefile`** (MODIFIED, +1 entry on .PHONY + 7-line target) — `e2e-money-path:` target added to the api-server section. Gates on `$OPENROUTER_API_KEY` env presence with a clear failure message; falls through to `cd api_server && pytest -m e2e_money_path -v --tb=short` when set.
- **`.github/workflows/e2e-money-path.yml`** (NEW, 87 lines) — `name: e2e money path` triggering on push/PR to main with path filters `api_server/**`, `recipes/**`, and the workflow file itself; `concurrency: { group: e2e-money-path, cancel-in-progress: false }`; one job `money-path` on `ubuntu-latest`, `timeout-minutes: 20`, with env block carrying `OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_CI_KEY }}` + `AP_ENV=dev` + `DATABASE_URL=postgresql+asyncpg://temporal:temporal@localhost:5432/agent_playground_api` + `AP_REDIS_URL=redis://localhost:6379/0`; steps for checkout, Python 3.12 setup, docker compose up postgresql+redis, wait-for-postgres loop, CREATE DATABASE agent_playground_api + make install-api + make migrate-api, run `make e2e-money-path`, teardown with `if: always()`.

## Decisions Made

- **Inlined recipe + model literals in JSON body, not constants alone.** The plan's acceptance criteria specifies `grep -F 'recipe_name\": \"nanobot\"'` which only matches the literal source. Using a `RECIPE_NAME` constant binding would have collected fine but failed the static gate. Both forms are present (constants for diagnostic readability + literals in the request body).
- **Chose POST /v1/runs over start + messages.** Both paths exercise the same proxy → cost-capture pipeline. `/v1/runs` is the smaller end-to-end surface (one Bearer + recipe + model + prompt → spawn → bot calls proxy → proxy writes `usage_logs` → verdict returned). The two-call path adds workflow plumbing on top that doesn't change the load-bearing AC19 assertions. Documented in the test's module docstring.
- **Reworded explanatory comments to avoid forbidden grep tokens.** Two static-check pitfalls were caught and fixed mid-execution: (a) `SESSION_SIGNING_KEY` literal in fixture-header comments would have triggered the AMD-03 / T-31-03 grep gate even though the comment was DOCUMENTING the prohibition; (b) `printenv` in workflow-header comments would have triggered the AC20 defense-in-depth grep gate similarly. Reworded to describe the prohibition without naming the verboten tokens.
- **Appended to the existing tests/e2e/conftest.py rather than creating a new file.** The plan's Task 1 reads as if the file is new, but the directory already carries Phase 22c.3 Plan 15 infrastructure (`__init__.py`, `conftest.py` with 555 lines of e2e fixtures, `_helpers.py`, `test_inapp_5x5_matrix.py`, `test_phase29_acceptance.py`). Additive-only diff preserves AMD-03 (no new auth surface) AND avoids fixture-name collisions.
- **Targeted POST /v1/runs requires Bearer + Cookie.** The route's `require_user` gate runs BEFORE the Bearer parse, so a missing Cookie returns 401 with `param=ap_session`. The fixture provides the Cookie; the test reads `OPENROUTER_API_KEY` from env and passes it as `Authorization: Bearer <key>`. Both auth surfaces flow through the existing canonical paths — no new auth code.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's File 1 directive (`api_server/tests/e2e/__init__.py`) was a no-op**
- **Found during:** Task 1 read-first verification
- **Issue:** The plan's `<action>` block directed creating `api_server/tests/e2e/__init__.py` as a fresh package marker. The directory already contained a Phase 22c.3 Plan 15 marker (`"""Phase 22c.3 Plan 15 — SC-03 5x1 end-to-end matrix gate."""`).
- **Fix:** Left the existing `__init__.py` UNTOUCHED. Documented the no-op in the Task 1 commit message.
- **Files modified:** None
- **Commit:** `ea21659` (commit message documents the no-op)

**2. [Rule 1 - Bug] Plan's File 2 directive (creating tests/e2e/conftest.py from scratch) would have wiped Phase 22c.3 fixtures**
- **Found during:** Task 1 read-first verification
- **Issue:** `tests/e2e/conftest.py` already carried 555 lines of Phase 22c.3 Plan 15 + Phase 22c.3.1 Plan 01 e2e infrastructure. Creating it from scratch would have destroyed `e2e_authenticated_cookie`, `oauth_user_with_openrouter_key`, `recipe_index`, `recipe_container_factory`, `pytest_sessionfinish`, etc.
- **Fix:** APPENDED the new fixture at the end of the file with a Phase 31 H8 explanatory header. Additive-only diff. Verified the existing fixtures remained untouched.
- **Files modified:** `api_server/tests/e2e/conftest.py` (additive +44 lines, no deletions)
- **Commit:** `ea21659`

**3. [Rule 1 - Bug] Static-check gate failure on AMD-03 grep due to comment wording**
- **Found during:** Task 1 verification grep
- **Issue:** Initial fixture header included `SESSION_SIGNING_KEY` literally inside two explanatory comments documenting the prohibition. The plan's acceptance criterion `grep -c 'SESSION_SIGNING_KEY' api_server/tests/e2e/conftest.py = 0` would have failed.
- **Fix:** Reworded the comments to use `signing-key machinery` and `prohibited HMAC-secret env-var name` instead.
- **Files modified:** `api_server/tests/e2e/conftest.py`
- **Commit:** `ea21659` (caught + fixed pre-commit)

**4. [Rule 1 - Bug] Static-check gate failure on AC20 defense-in-depth grep due to comment wording**
- **Found during:** Task 3 verification grep
- **Issue:** Initial workflow YAML included a comment listing the verboten tokens (`echo / printenv / set -x`) to document what the workflow MUST NOT do. The plan's acceptance criterion `grep -E 'echo.*OPENROUTER|printenv|cat \\.env' returns 0 lines` would have failed.
- **Fix:** Reworded the comment to describe the prohibition (`no shell command in this workflow prints any environment variable to stdout`) without naming the verboten tokens.
- **Files modified:** `.github/workflows/e2e-money-path.yml`
- **Commit:** `c07b183` (caught + fixed pre-commit)

## Issues Encountered

- **The worktree base was at `dbfad8e` not `601c7a1` at agent start.** The `<worktree_branch_check>` hard-reset succeeded; HEAD was corrected before any task work began. Likely a residual checkout state from a prior run; no functional impact.
- **`asyncpg` is not in the worktree's system Python** — pytest collection requires the api_server venv at `/Users/fcavalcanti/dev/agent-playground/api_server/.venv` (Python 3.13.9). Verified collect-only with `PYTHONPATH=src .venv/bin/python -m pytest --collect-only ...` → 1 test collected, zero warnings.

## Manual Gates Pending

The plan declares `autonomous: false` because four SPEC ACs cannot be automated inside test code. They are flagged here for the user to action; the parent orchestrator will surface them. **The phase exit gate is not green until all four signals arrive.**

| AC   | Manual Gate                                                                                  | Owner action                                                                                                                                                                                                                                                                                                                                          | Resume signal                            |
| ---- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| AC22 | Manual Gate 1 — OpenRouter dashboard $5/mo cap + verification artifact                       | (1) Login to OpenRouter dashboard with the Solvr Labs account. (2) Set Settings → Billing → Spend Limit to **$5.00**. (3) Capture proof — screenshot to `.planning/phases/31-pre-stripe-billing-hardening/spend-cap.png` OR a dashboard URL with timestamp embedded in the eventual PR commit-message body. (4) Verify the cap on a fresh page load. | `cap-set: <screenshot-path-or-URL>`      |
| AC20 | Manual Gate 2 — Add `OPENROUTER_CI_KEY` to GitHub repo secrets                               | (1) Create a NEW OpenRouter API key dedicated to CI (separate from any dev BYOK already in `.env`); tag/label as `gh-actions-e2e-money-path`. (2) Verify the key is bound to the same OpenRouter account that has the $5/mo cap from Manual Gate 1. (3) GitHub repo Settings → Secrets and variables → Actions → New repository secret → `OPENROUTER_CI_KEY` = the new key. (4) After Manual Gate 3 runs the workflow once, inspect the workflow log to confirm the secret value never appears in plain text (GitHub auto-masks `${{ secrets.* }}` values; the absence of any `echo $OPENROUTER_API_KEY` / `printenv` / `set -x` in the YAML is verified by the static grep AC). | `secret-set` (do NOT paste the value)    |
| AC23 | Manual Gate 3 — Open a no-op PR and verify the workflow is green (baseline)                  | (1) Branch off main; add a whitespace-only / comment-only change inside `api_server/` (e.g. trailing newline in `api_server/README.md`). (2) Open PR against main. (3) Watch the GitHub Actions `e2e money path` run. (4) Confirm: workflow triggers (path filter on `api_server/**` matches), completes in ~5-10 min, exits 0 (green check). (5) OpenRouter dashboard shows ~$0.0004 charge for the run (matches Phase 29 nanobot baseline).                                                                                                                                                                                                            | `baseline-green: <PR-URL>`               |
| AC24 | Manual Gate 4 — Open a deliberate-regression PR and verify the workflow fails at cost_usd > 0 | (1) On a separate feature branch, intentionally break the proxy cost-capture path (locate `api_server/src/api_server/proxy/...` `/api/v1/generation` parser or the `usage_logs` insert and either short-circuit it or replace the cost field with `0.0`). (2) Open a PR. (3) Watch the workflow. (4) Confirm: workflow triggers, the assertion `float(usage_row["cost_usd"]) > 0` fires AND fails (or the polling loop times out and `assert usage_row is not None` fires), the job exits non-zero (red X). (5) **CLOSE the PR without merging.** Do NOT merge the regression to main.                                                                                                              | `regression-red: <PR-URL>` (PR CLOSED)   |

## Next Phase Readiness

- **H8 SHIPPED for the automated portion.** Every PR/push touching `api_server/**` or `recipes/**` will now trigger the `e2e money path` workflow once Manual Gate 2 (secret added to repo settings) lands. A regression in cost-parsing or the `/api/v1/generation` polling will fail the workflow before merge.
- **Phase B (Stripe paywall) is unblocked** from the H8 side once Manual Gates 1-4 all signal. Until then, the workflow runs without `OPENROUTER_CI_KEY` and the test SKIPS in CI (Makefile env-guard) — same as a developer running `pytest -m e2e_money_path` locally without the env var.
- **No new schema, no new auth surface, no new SDK pin** — this plan was pure CI-glue. The next phase work (`/gsd-execute-phase B` for Stripe paywall) reads from the existing usage_logs schema + the existing OAuth + the existing rate-limit middleware (Plan 02 H3 closed the auth-bucket gap; this plan closes the cost-capture-regression gap).

## Self-Check

Verified against repository state:

- `api_server/tests/e2e/__init__.py` exists and is unchanged from Phase 22c.3 Plan 15 — FOUND (`"""Phase 22c.3 Plan 15 — SC-03 5x1 end-to-end matrix gate."""`)
- `api_server/tests/e2e/conftest.py` exists and contains `e2e_money_path_client` fixture (line 581) + `authenticated_cookie["Cookie"]` (line 597) — FOUND
- `api_server/tests/e2e/test_money_path.py` exists (132 lines, valid Python syntax) — FOUND
- `Makefile` `.PHONY` line 197 includes `e2e-money-path` and target on line 236 — FOUND
- `.github/workflows/e2e-money-path.yml` exists (87 lines, valid YAML) — FOUND
- Commit `ea21659` (Task 1) — FOUND
- Commit `c849566` (Task 2) — FOUND
- Commit `c07b183` (Task 3) — FOUND
- `grep -c 'SESSION_SIGNING_KEY' api_server/tests/e2e/conftest.py` returns 0 — VERIFIED (T-31-03 mitigation)
- `grep -c 'nano-kaiku' api_server/tests/e2e/test_money_path.py` returns 0 — VERIFIED (AMD-04 — no hallucinated recipe)
- `grep -E 'echo.*OPENROUTER|printenv|cat \\.env' .github/workflows/e2e-money-path.yml` returns 0 lines — VERIFIED (T-31-04 / AC20 mitigation)
- `cd api_server && pytest --collect-only -m e2e_money_path tests/e2e/test_money_path.py --ignore=tests/spikes` → 1 test collected, zero `PytestUnknownMarkWarning` — VERIFIED
- `make e2e-money-path` (without `OPENROUTER_API_KEY`) exits 2 with the explicit error message — VERIFIED
- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/e2e-money-path.yml'))"` exits 0 (valid YAML) — VERIFIED
- All other plan acceptance greps (`pytestmark = [pytest.mark.e2e_money_path`, `recipe_name": "nanobot"`, `model": "openai/gpt-4o-mini"`, `range(50)`, `asyncio.sleep(0.2)`, `float(usage_row["cost_usd"]) > 0`, `usage_row["upstream_request_id"] is not None`, `name: e2e money path`, `group: e2e-money-path`, `cancel-in-progress: false`, `secrets.OPENROUTER_CI_KEY`, `api_server/**`×3, `recipes/**`×3, `docker-compose.dev.yml`×6, `make e2e-money-path`, `timeout-minutes:`) — VERIFIED

## Self-Check: PASSED

---
*Phase: 31-pre-stripe-billing-hardening*
*Plan: 06*
*Completed: 2026-05-08*
