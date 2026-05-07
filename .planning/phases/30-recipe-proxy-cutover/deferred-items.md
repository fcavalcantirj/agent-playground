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

## D-30-DEF-03 — nullclaw is structurally non-proxiable (config schema sealed) — DEFERRED

**Discovered during:** Plan 30-03 Task 2 (live deploy-stack smoke).
**Severity:** Plan 30-03 cannot complete cleanly. Plan 30-03 commits
`f7bcd6a` (RED) + `5f2b03b` (GREEN) reverted in `c633b46` + `ccefd10`.

**Empirical evidence (2026-05-07 in-isolation probes against `ap-recipe-nullclaw:latest`):**

1. `nullclaw config set models.providers.<any>.base_url <url>` returns
   `AccessDenied` for every named provider (openrouter, openai, anthropic,
   azure, gemini, vertex, deepseek, groq, z.ai, glm, together-ai,
   fireworks-ai, mistral, xai, …). Same response for adding custom
   providers.
2. Writing `models.providers.openrouter.base_url` directly into
   `config.json` on disk: nullclaw's loader silently strips the field at
   parse time. `nullclaw config show` reflects only the default
   `models.providers.openrouter: {}` regardless of disk content. `api_key`
   IS retained on the openrouter provider; `base_url` is not.
3. Live-stack sniff test (Plan 30-03 executor, 2026-05-07): with a real
   OpenRouter key + base_url pointed at a sniff-server on the deploy
   bridge, nullclaw replied OK and the sniff server received ZERO
   requests — outbound HTTP went directly to `openrouter.ai`. Definitive.

**Conclusion:** nullclaw is a sealed-config recipe by design. The `base_url`
override is intentionally not exposed for known providers. Phase 30's
"flip via heredoc substitution" model cannot work for nullclaw without
either (a) an upstream patch to expose `base_url`, (b) a sidecar that
intercepts at network/DNS level (heavy substrate addition), or (c) a fork.

**Routing:** Park nullclaw on its legacy direct-to-OpenRouter path. Phase 30
ships with **5 of 6 recipes** going through the proxy: nanobot, openclaw,
hermes, zeroclaw, picoclaw. nullclaw is `BLOCKED(provider-sealed)` and
revisited only when one of the resolution paths (a/b/c above) becomes
desirable enough to justify the work.

**Carry-forward fact for Plan 30-07:** the regression-guard rewrite must
NOT include nullclaw in the asserted set. `_ALL_RECIPES` should be
`{nanobot, openclaw, hermes, zeroclaw, picoclaw}`; nullclaw is in
`_OTHER_RECIPES` (the un-flipped set) permanently for this phase.

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
