# Phase 30 — Deferred Items

Tracking issues discovered during execution that are out of scope for the
plan that surfaced them.

## D-30-DEF-01 — e2e harness `_handle_row` import broken since Phase 28 — **RESOLVED 2026-05-06 (commit `3b7596a`)**

**Discovered during:** Plan 30-00 Task 3 (nanobot e2e regression gate)
**Severity:** Blocking for any plan that requires `make e2e-inapp-docker`
**Root cause:** Phase 28 commit `6feb361` deleted
`api_server/src/api_server/services/inapp_dispatcher::_handle_row` and
`dispatcher_loop` (Temporal `DispatchMessageWorkflow` cutover, D-06), but
`api_server/tests/e2e/_helpers.py:402` still imports `_handle_row`. The
e2e harness was broken at fixture-setup time from Phase 28 ship until
the fix below.
**Plan 30-00 workaround (historical):** Used the 4 D-09 integration tests in
`tests/routes/test_llm_proxy.py` (real PG via testcontainers, real
respx-mocked OpenRouter SSE) as the regression evidence. These cover the
exact code path Plan 30-00 modifies (`_record_usage_from_parsed`) and
empirically prove cost_usd is sourced correctly across
openrouter+inline / openrouter+fallback / anthropic / openai-direct.
The unit-test side (38/38 PASS in `tests/services/`) covers the parser
extension. The recipe-invariant tests (11/11 PASS in
`tests/recipes/test_nanobot_via_proxy.py`) cover the YAML side.
**Resolution (2026-05-06, commit `3b7596a`):** Rewrote
`drive_dispatcher_once` to drive each Phase 28 activity in
`DispatchMessageWorkflow.run` order via
`temporalio.testing.ActivityEnvironment` — no real Temporal server, no
mocks. Each activity runs its real body against the real test infra
(asyncpg pool, httpx bot client, docker-aware recipe_index). Pattern
lifted from `tests/temporal/test_forward_to_agent_activity.py`.
Signature preserved so the matrix test required no edits.
**Verification:** `make e2e-inapp-docker` 4/5 PASS (hermes, nanobot,
nullclaw, zeroclaw); openclaw FAIL is recipe-level (container
`ready_log_regex` 240s timeout, CONTEXT.md AC-03 known issue —
upstream OpenRouter→Anthropic plugin chain), NOT a harness issue.
Phase 30 Wave 2 unblocked.

## D-30-DEF-02 — Test-runner Dockerfile missing `temporalio` (FIXED inline)

**Discovered during:** Plan 30-00 Task 3 (running e2e harness)
**Severity:** Blocking for ANY dockerized test invocation
**Fix applied:** Plan 30-00 added `'temporalio>=1.27.0,<1.28'` to
`tools/Dockerfile.test-runner` (Rule 3 — blocking issue). Image rebuilt;
verified no longer raises `ModuleNotFoundError: No module named 'temporalio'`.
**Note:** This was a Phase 28 follow-up never landed. The fix here is
inline because it was the BLOCKING issue (couldn't even reach the harness
proper). The deeper helpers.py rot (D-30-DEF-01) is a different, larger
issue still deferred.
