---
phase: 29
plan: 08
subsystem: llm-egress-proxy
tags: [runner, recipe, via_proxy, AMD-09, AMD-06, nanobot]
dependency_graph:
  requires:
    - 29-04  # /v1/llm/forward proxy route + ap-proxy-<token> auth
    - 29-05  # BYOK custody (provider_key_enc + ProxyBYOKCache)
  provides:
    - "tools/run_recipe.py::_build_via_proxy_overrides — runner-side env injection"
    - "RecipeSummary.via_proxy — surface flag for UI / planner"
    - "recipes/nanobot.yaml runtime.via_proxy: true — first cutover recipe"
    - "AP_PROXY_BASE_URL sh-default form in nanobot's two config-file heredocs"
  affects:
    - 29-09  # next plan — restart drill, e2e gate
    - 30     # Phase 30 — flip remaining 4 recipes
tech_stack:
  added: []
  patterns:
    - "Closed-enum dispatch on recipe.runtime.process_env.api_key (3 vars; ValueError on unknown)"
    - "Sh-default heredoc form ${VAR:-fallback} for via_proxy=true / via_proxy=false coexistence"
    - "Pure-function env-file builder accepts via_proxy_overrides; D-27 byte-identical preserved"
key_files:
  created:
    - api_server/tests/runner/__init__.py
    - api_server/tests/runner/test_via_proxy_env_injection.py
    - api_server/tests/recipes/__init__.py
    - api_server/tests/recipes/test_nanobot_via_proxy.py
  modified:
    - tools/run_recipe.py                                        # _build_via_proxy_overrides + _build_env_file_content gate + run_cell_persistent wiring
    - tools/ap.recipe.schema.json                                # +via_proxy boolean under v0.2 runtime
    - api_server/src/api_server/services/recipes_loader.py       # to_summary populates via_proxy
    - api_server/src/api_server/models/recipes.py                # RecipeSummary.via_proxy: bool = False
    - recipes/nanobot.yaml                                       # +via_proxy: true; api_base sh-default in both heredocs
decisions:
  - "AMD-09 fix landed: AP_PROXY_BASE_URL injected alongside SDK-conventional BASE_URL env vars so config-file-reading bots (nanobot's ~/.nanobot/config.json) can sh-expand the proxy URL into JSON. PROBE-VAL-05 empirical evidence absorbed."
  - "Closed-enum env-var dispatch (D-09 + D-17): OPENROUTER_API_KEY/OPENAI_API_KEY → OPENAI_BASE_URL+OPENAI_API_KEY shape; ANTHROPIC_API_KEY → ANTHROPIC_BASE_URL+ANTHROPIC_API_KEY shape; unknown → ValueError. No silent fallback."
  - "via_proxy=true requires channel='inapp' (INAPP_AUTH_TOKEN must be present in activation_substitutions). Telegram + via_proxy=true raises RuntimeError fail-loud — Phase 29 only ships nanobot+inapp+proxy."
  - "BYOK key STRIPPED from container env-file when via_proxy=true (api_key_var line omitted). Bot only ever sees the `ap-proxy-<inapp_auth_token>` placeholder, validated upstream by the proxy route against agent_containers."
  - "Schema extension scope-limited: only the v0.2 runtime block gets via_proxy. v0.1 stays untouched — no recipe in the repo uses v0.1 with via_proxy."
  - "Pre-existing 7 lint errors in nanobot.yaml (channels.inapp shape mismatches) are out of scope per phase boundary — added zero new lint errors."
metrics:
  duration: "~2.5 hours"
  completed: 2026-05-06
  tasks_completed: 2
  files_modified: 5
  files_created: 4
  tests_added: 19  # 8 runner + 11 recipe (5 named + 5 parametrized + 1 bonus)
---

# Phase 29 Plan 08: nanobot via_proxy Cutover Summary

The runner now reads `recipe.runtime.via_proxy` and, when true, strips the
real BYOK key from the bot's container env-file and injects the LLM egress
proxy shape (`AP_PROXY_BASE_URL` + `OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL` +
`ap-proxy-<inapp_auth_token>` placeholder). `recipes/nanobot.yaml` flipped
to `via_proxy: true` and both of its config-file heredocs (gateway path for
channels.telegram, serve path for channels.inapp) now substitute the proxy
URL via the sh-default form `${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}`.

## What landed

| Layer | File | Change |
|---|---|---|
| Runner — pure helpers | `tools/run_recipe.py` | `_PROXY_BASE_URL` constant + `_PROXY_BASE_URL_ENV_BY_API_KEY` / `_PROXY_KEY_ENV_BY_API_KEY` dispatch tables + `_build_via_proxy_overrides()` builder + `_build_env_file_content()` extended with `via_proxy_overrides` kwarg (api_key line omitted when set) |
| Runner — wiring | `tools/run_recipe.py::run_cell_persistent` | Reads `recipe.runtime.via_proxy`; when true, derives `via_proxy_overrides` from `api_key_var` + `activation_substitutions["INAPP_AUTH_TOKEN"]`; threads through to BOTH env-file build call sites (gate-open path + legacy path) |
| Schema | `tools/ap.recipe.schema.json` | +`via_proxy: boolean` under v0.2 runtime block |
| Loader | `api_server/src/api_server/services/recipes_loader.py` | `to_summary` populates `via_proxy=bool(runtime.get("via_proxy", False))` |
| Surface | `api_server/src/api_server/models/recipes.py` | `RecipeSummary.via_proxy: bool = False` |
| Recipe — flag | `recipes/nanobot.yaml` runtime block | `+ via_proxy: true` (single line addition + comment block) |
| Recipe — gateway heredoc | `recipes/nanobot.yaml` line 252 | `"api_base": "${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"` |
| Recipe — serve heredoc | `recipes/nanobot.yaml` line 463 | same substitution |

## AMD-09 evidence

Empirical sh-default-form behavior verified inline during execution:

```
$ AP_PROXY_BASE_URL='http://api_server:8000/v1/llm/forward' \
  sh -c 'cat <<JSON
{"api_base": "${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"}
JSON'
{"api_base": "http://api_server:8000/v1/llm/forward"}

$ unset AP_PROXY_BASE_URL && sh -c 'cat <<JSON
{"api_base": "${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"}
JSON'
{"api_base": "https://openrouter.ai/api/v1"}
```

Both branches behave correctly. The unquoted `<<JSON` heredoc enables
sh-expansion; the `:-` parameter-default form gives the via_proxy=false
fallback for free.

## Tests

**8 new tests** in `api_server/tests/runner/test_via_proxy_env_injection.py`:
1. `test_via_proxy_true_openrouter_dispatches_openai_sdk_envs` — closed-enum dispatch + env-file shape (OPENROUTER → OPENAI_BASE_URL+OPENAI_API_KEY+AP_PROXY_BASE_URL; real key stripped)
2. `test_via_proxy_true_anthropic_dispatches_anthropic_sdk_envs` — same for Anthropic shape
3. `test_via_proxy_true_openai_dispatches_openai_sdk_envs` — OpenAI direct provider routes via OpenAI shape
4. `test_via_proxy_true_unknown_env_var_raises_value_error` — closed-enum invariant (D-09 + D-17)
5. `test_via_proxy_false_preserves_legacy_env_file_shape` — D-27 byte-identical for via_proxy=false
6. `test_via_proxy_default_arg_preserves_legacy_env_file_shape` — default-arg behaves identically to None (legacy 5 recipes unaffected)
7. `test_recipe_summary_surfaces_via_proxy_field` — to_summary surfaces the flag (true / false / absent)
8. `test_via_proxy_env_visible_in_running_container_env` (api_integration) — real busybox container; `docker exec env` shows AP_PROXY_BASE_URL + OPENAI_BASE_URL + ap-proxy-<token>; OPENROUTER_API_KEY + literal real key absent

**11 new tests** in `api_server/tests/recipes/test_nanobot_via_proxy.py`:
1. `test_nanobot_runtime_via_proxy_is_true`
2. `test_only_nanobot_has_via_proxy_true[hermes/openclaw/zeroclaw/nullclaw/picoclaw]` — parametrized regression guard (5 cases)
3. `test_only_one_recipe_yaml_has_via_proxy_true` — combined raw-text grep guard
4. `test_nanobot_inapp_contract_is_openai_compat`
5. `test_nanobot_process_env_api_key_is_openrouter`
6. `test_nanobot_recipe_summary_surfaces_via_proxy_true` — end-to-end recipe → loader → summary
7. `test_nanobot_api_base_uses_proxy_url_default_form_in_both_heredocs` — AMD-09 substitution lives in both heredocs (count==2; literal upstream URL absent)

**Regression — 0 failures:**
- `test_run_recipe_telegram_invariant.py` (3 tests) PASS — D-27 invariant holds
- `test_recipes.py` (3 tests) PASS — recipe loader + RecipeSummary surface unaffected
- combined run: **25/25 PASS**

## Acceptance gate evidence

The plan's acceptance criteria mapped to evidence:

- [x] Runner env-build function contains `via_proxy` AND `ap-proxy-` AND `http://api_server:8000/v1/llm/forward` AND `AP_PROXY_BASE_URL` — verified by `grep -n "via_proxy\|ap-proxy-\|AP_PROXY_BASE_URL\|http://api_server:8000/v1/llm/forward" tools/run_recipe.py` (multiple hits in `_build_via_proxy_overrides` + `run_cell_persistent`)
- [x] Dispatch covers OPENROUTER_API_KEY (or OPENAI_API_KEY) AND ANTHROPIC_API_KEY — `_PROXY_BASE_URL_ENV_BY_API_KEY` carries all three keys
- [x] `services/recipes_loader.py` populates `via_proxy=bool(runtime.get("via_proxy", False))` (loader test PASS)
- [x] `api_server/tests/runner/test_via_proxy_env_injection.py` exists with 8 test functions; all PASS
- [x] Regression: `test_run_recipe_telegram_invariant.py` 3/3 PASS — legacy via_proxy=false path unchanged
- [x] `recipes/nanobot.yaml` contains `via_proxy: true`
- [x] `recipes/nanobot.yaml` contains `${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}` (twice — both heredocs)
- [x] No other recipe contains `via_proxy: true` (grep returns 1 file)
- [x] `api_server/tests/recipes/test_nanobot_via_proxy.py` exists with 5+ test functions (11 actual via parametrize); all PASS

## Deviations from Plan

**1. [Rule 2 — Critical functionality] Schema extension for `via_proxy`**
- Found during: Task 2 lint validation
- Issue: `python tools/run_recipe.py --lint recipes/nanobot.yaml` reported a NEW error after adding `via_proxy: true`: `runtime: Additional properties are not allowed ('via_proxy' was unexpected)`. The PLAN did not call out a schema edit, but the schema's `additionalProperties: false` would have rejected the flag in any consumer that gates on lint.
- Fix: added `via_proxy: { type: "boolean", description: ... }` to the v0.2 `runtime` properties block in `tools/ap.recipe.schema.json` (lines 1300+). v0.1 left untouched — no v0.1 recipe uses via_proxy.
- Files modified: `tools/ap.recipe.schema.json`
- Commit: c050796

**2. [Rule 2 — Bonus AMD-09 verification test] Heredoc count assertion**
- Found during: Task 2 plan reading
- Issue: PLAN's acceptance criterion `recipes/nanobot.yaml contains the literal string ${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}` is satisfied by either heredoc — but the PLAN body explicitly says BOTH must be edited (gateway + serve heredocs). A single grep doesn't catch the case where one is updated but the other isn't.
- Fix: added `test_nanobot_api_base_uses_proxy_url_default_form_in_both_heredocs` which asserts `text.count(pattern) == 2` AND that the literal upstream URL is gone (defense-in-depth). The test would have caught a single-heredoc edit.
- Files modified: `api_server/tests/recipes/test_nanobot_via_proxy.py`
- Commit: c050796

No other deviations. The PLAN's core spec landed exactly as written.

## Out-of-scope (not addressed; documented for future phases)

- 7 pre-existing lint failures on `nanobot.yaml` (channels.inapp shape mismatches) — introduced by earlier phases. Phase 32 (schema formalization) will absorb them.
- Phase 30 will flip the remaining 4 recipes (zeroclaw, nullclaw, hermes, openclaw) one by one after per-recipe spike validation. Test 2's parametrized regression guard catches any accidental leak.
- The full nanobot proxy e2e (real OpenRouter call routing through the proxy) is Plan 09's gate; this plan establishes the wiring.

## Self-Check: PASSED

Files created:
- FOUND: `/Users/fcavalcanti/dev/agent-playground/api_server/tests/runner/__init__.py`
- FOUND: `/Users/fcavalcanti/dev/agent-playground/api_server/tests/runner/test_via_proxy_env_injection.py`
- FOUND: `/Users/fcavalcanti/dev/agent-playground/api_server/tests/recipes/__init__.py`
- FOUND: `/Users/fcavalcanti/dev/agent-playground/api_server/tests/recipes/test_nanobot_via_proxy.py`

Commits exist:
- FOUND: `16d0f97` feat(29-08): wire via_proxy env injection into runner (Task 1)
- FOUND: `c050796` feat(29-08): flip recipes/nanobot.yaml to via_proxy: true (Task 2)

19 new tests pass; 0 regressions in `test_run_recipe_telegram_invariant.py` or `test_recipes.py`. Plan 08 SHIPPED.
