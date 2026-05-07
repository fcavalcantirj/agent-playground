---
phase: 30
slug: recipe-proxy-cutover
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-06
---

# Phase 30 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (api_server tests) + Make-driven dockerized e2e harness |
| **Config file** | `api_server/pyproject.toml`, `Makefile` |
| **Quick run command** | `cd api_server && uv run pytest tests/services/test_stream_parser.py tests/services/test_usage_recorder.py -x` |
| **Full suite command** | `cd api_server && uv run pytest tests/ -x` |
| **E2E command** | `make e2e-inapp-docker RECIPE=<name>` (per-recipe smoke; runs the dockerized harness — required on macOS, see CLAUDE.md) |
| **Estimated runtime** | ~30s (quick), ~5min (full suite), ~2-4min per e2e smoke |

---

## Sampling Rate

- **After every task commit:** Run quick command (services tests only) — covers stream_parser + usage_recorder regressions
- **After every plan wave:** Run full pytest suite
- **After every recipe flip plan (30-02..30-06):** `make e2e-inapp-docker RECIPE=<flipped>` MUST PASS before next plan starts; gate is real-money <$0.01
- **Before Plan 30-07 verification:** full pytest suite + e2e for ALL 6 recipes (smoke matrix) must be green
- **Max feedback latency:** 30s (unit), 4min (e2e per recipe)

---

## Per-Task Verification Map

To be filled by gsd-planner from RESEARCH.md (Validation Architecture section, lines 483+) and the per-plan task tables. Skeleton:

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 30-00-01 | 30-00 | 1 | D-09 | — | OpenRouter inline cost is read into ParsedUsage | unit | `pytest tests/services/test_stream_parser.py::test_openai_inline_cost` | ❌ W0 | ⬜ pending |
| 30-00-02 | 30-00 | 1 | D-09 | — | Non-streaming JSON inline cost is read by `_parse_openai_compat` | unit | `pytest tests/services/test_usage_recorder.py::test_parse_openai_compat_inline_cost` | ❌ W0 | ⬜ pending |
| 30-00-03 | 30-00 | 2 | D-09 | — | inline_cost_usd persists to usage_logs.cost_usd; cost_weights fallback when None | integ | `pytest tests/routes/test_llm_proxy.py::test_inline_cost_persists` | ❌ W0 | ⬜ pending |
| 30-00-04 | 30-00 | 3 | D-09 regression | — | nanobot e2e produces inline_cost_usd > 0 (regression guard for proxy enhancement) | e2e | `make e2e-inapp-docker RECIPE=nanobot` | ✅ existing | ⬜ pending |
| 30-01-01 | 30-01 | 1 | D-04 | — | cost_weights covers `anthropic/claude-haiku-4.5` | sql | SELECT-row check | ✅ existing | ⬜ pending |
| 30-01-02 | 30-01 | 2 | D-04 | — | Anthropic SSE through proxy → usage_logs row with status='success', AMD-07 last-wins applied | spike | `python tools/probe_val_anthropic.py` | ❌ W0 | ⬜ pending |
| 30-02-01 | 30-02 | 1 | D-03 (openclaw flip) | — | `recipes/openclaw.yaml` has `runtime.via_proxy: true` | recipe-test | `pytest tests/recipes/test_via_proxy_state.py::test_openclaw_via_proxy` | ❌ W0 | ⬜ pending |
| 30-02-02 | 30-02 | 2 | D-03, D-08 | — | regression-guard test extended to assert openclaw + nanobot have via_proxy | unit | `pytest tests/recipes/test_via_proxy_state.py` | ❌ W0 | ⬜ pending |
| 30-02-03 | 30-02 | 3 | D-03 e2e | — | openclaw e2e via proxy → usage_logs row, status='success', cost_usd>0 | e2e | `make e2e-inapp-docker RECIPE=openclaw` | ❌ W0 | ⬜ pending |
| 30-03-01 | 30-03 | 1 | D-06 (nullclaw flip) | — | `recipes/nullclaw.yaml:468` substitution applied + via_proxy:true | unit | recipe assertion test | ❌ W0 | ⬜ pending |
| 30-03-02 | 30-03 | 2 | D-06 e2e | — | nullclaw e2e via proxy → usage_logs row | e2e | `make e2e-inapp-docker RECIPE=nullclaw` | ❌ W0 | ⬜ pending |
| 30-04-01 | 30-04 | 1 | D-06 (picoclaw flip) | — | `recipes/picoclaw.yaml:105 + :213` substitutions applied + via_proxy:true | unit | recipe assertion test | ❌ W0 | ⬜ pending |
| 30-04-02 | 30-04 | 2 | D-06 e2e | — | picoclaw e2e via proxy → usage_logs row | e2e | `make e2e-inapp-docker RECIPE=picoclaw` | ❌ W0 | ⬜ pending |
| 30-05-01 | 30-05 | 0 | D-06 (zeroclaw inspection) | — | identify zeroclaw base_url override surface (config CLI / file / env) | manual | `docker run zeroclaw:latest zeroclaw onboard --help` | ❌ W0 | ⬜ pending |
| 30-05-02 | 30-05 | 1 | D-06 (zeroclaw flip) | — | recipe edits applied + via_proxy:true | unit | recipe assertion test | ❌ W0 | ⬜ pending |
| 30-05-03 | 30-05 | 2 | D-06 e2e | — | zeroclaw e2e via proxy → usage_logs row | e2e | `make e2e-inapp-docker RECIPE=zeroclaw` | ❌ W0 | ⬜ pending |
| 30-06-01 | 30-06 | 0 | D-06 (hermes inspection) | — | identify hermes base_url override surface (CLI flag / config / env) | manual | `docker run hermes:latest hermes chat --help` | ❌ W0 | ⬜ pending |
| 30-06-02 | 30-06 | 1 | D-06 (hermes flip) | — | recipe edits applied + via_proxy:true | unit | recipe assertion test | ❌ W0 | ⬜ pending |
| 30-06-03 | 30-06 | 2 | D-06 e2e | — | hermes e2e via proxy → usage_logs row | e2e | `make e2e-inapp-docker RECIPE=hermes` | ❌ W0 | ⬜ pending |
| 30-07-01 | 30-07 | 1 | D-08 | — | `test_all_recipes_have_via_proxy` asserts ALL 6 recipes (nanobot + 5 new) | unit | `pytest tests/recipes/test_via_proxy_state.py::test_all_recipes_have_via_proxy` | ❌ W0 | ⬜ pending |
| 30-07-02 | 30-07 | 2 | cutover gate | — | usage_logs has at least one status='success' row per recipe (last 24h) | sql | SELECT-row check across 6 providers/recipes | ❌ W0 | ⬜ pending |
| 30-07-03 | 30-07 | 3 | cutover gate | — | VERIFICATION.md mirrors 29-VERIFICATION.md format | doc | manual review | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `api_server/tests/services/test_stream_parser.py` — extend with `test_openai_inline_cost` for D-09 (Plan 30-00 Wave 1)
- [ ] `api_server/tests/services/test_usage_recorder.py` — extend with `test_parse_openai_compat_inline_cost` (Plan 30-00 Wave 1)
- [ ] `api_server/tests/routes/test_llm_proxy.py` — extend with `test_inline_cost_persists` (Plan 30-00 Wave 2)
- [ ] `api_server/tests/recipes/test_via_proxy_state.py` — extend regression guard per-flip (Plans 30-02..30-06) and finalize in 30-07
- [ ] `tools/probe_val_anthropic.py` — Plan 30-01 spike script (mirror Phase 29 PROBE-VAL pattern)
- [ ] `Makefile` E2E target — verify `make e2e-inapp-docker RECIPE=<name>` accepts a recipe parameter; if absent, single-line addition (Open Question A1 — RESEARCH.md)
- [ ] cost_weights row coverage check for `anthropic/claude-haiku-4.5` (Plan 30-01 Task 0)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| hermes CLI surface inspection | D-06 (hermes) | One-shot inspection of upstream tool's CLI; not a regression-prone behavior | `docker run --rm $(docker build -q recipes/hermes/) hermes chat --help` and read output for `--base-url` flag presence; if absent, inspect `process_env.base_url` config surface |
| zeroclaw config surface inspection | D-06 (zeroclaw) | One-shot inspection of upstream tool's config writer | `docker run --rm $(docker build -q recipes/zeroclaw/) zeroclaw onboard --help` and read output / source for base_url field |
| Real-money cost-budget tracking | Phase scope | $0.06 budget across 1 spike + 5 e2e smokes; needs human attention to abort if a single test exceeds $0.05 | Track usage_logs.cost_usd sum after each spike/smoke; alert if cumulative > $0.10 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 240s (e2e ceiling)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
