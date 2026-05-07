# Phase 30 — Deferred Items

Tracking issues discovered during execution that are out of scope for the
plan that surfaced them.

## D-30-DEF-01 — e2e harness `_handle_row` import broken since Phase 28

**Discovered during:** Plan 30-00 Task 3 (nanobot e2e regression gate)
**Severity:** Blocking for any plan that requires `make e2e-inapp-docker`
**Root cause:** Phase 28 commit `6feb361` deleted
`api_server/src/api_server/services/inapp_dispatcher::_handle_row` and
`dispatcher_loop` (Temporal `DispatchMessageWorkflow` cutover, D-06), but
`api_server/tests/e2e/_helpers.py:402` still imports `_handle_row`. The
e2e harness has been broken at fixture-setup time since Phase 28 shipped.
The `e2e-report.json` showing `recipes:[]` is the visible symptom (the
session-scoped emit_report fixture writes the empty accumulator on every
truncated run).
**Plan 30-00 workaround:** Used the 4 new D-09 integration tests in
`tests/routes/test_llm_proxy.py` (real PG via testcontainers, real
respx-mocked OpenRouter SSE) as the regression evidence. These cover the
exact code path Plan 30-00 modifies (`_record_usage_from_parsed`) and
empirically prove cost_usd is sourced correctly across
openrouter+inline / openrouter+fallback / anthropic / openai-direct.
The unit-test side (38/38 PASS in `tests/services/`) covers the parser
extension. The recipe-invariant tests (11/11 PASS in
`tests/recipes/test_nanobot_via_proxy.py`) cover the YAML side.
**Future work (route to a Phase 28 follow-up plan, NOT Phase 30):**
1. Update `api_server/tests/e2e/_helpers.py::drive_dispatcher_once` to
   call the Temporal `DispatchMessageWorkflow` instead of the deleted
   `_handle_row`. Likely options: (a) start a real workflow against a
   testcontainers-spawned Temporal instance, (b) bypass Temporal and
   call the dispatch activity directly, (c) replace with an HTTP-layer
   smoke that POSTs `/v1/agents/:id/messages` and asserts the row
   transitions to `done` via a polled SELECT.
2. Re-run all 5 cells of `make e2e-inapp-docker` to confirm Gate 1
   shape (cost_usd > 0, status='success', tokens > 0) post-Phase 28.

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
