---
phase: 29
slug: llm-egress-proxy
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-06
---

# Phase 29 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Drives Nyquist coverage of the 15 PROBE-VAL items in 29-RESEARCH.md and the 7 acceptance gates in 29-CONTEXT.md.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (api_server tests) + Flutter `flutter test` (mobile) + dockerized e2e harness |
| **Config file** | `api_server/pyproject.toml` (pytest section) + `mobile/pubspec.yaml` |
| **Quick run command** | `cd api_server && uv run pytest tests/services/test_proxy_*.py tests/routes/test_llm_proxy.py -x -q` |
| **Full suite command** | `make e2e-inapp-docker` (dockerized harness — REQUIRED, native uvicorn fails on macOS Docker bridge) |
| **Estimated runtime** | quick ~30s · full ~6–8 min |

> **macOS gotcha (CLAUDE.md):** the proxy's IP-map (`request.client.host` → `agent_containers.bridge_ip`) only resolves correctly on Linux Docker. Acceptance tests MUST run inside the dockerized harness, NOT against native uvicorn. This is the same constraint as Phase 22c.3.1 — re-use that `make e2e-inapp-docker` recipe.

---

## Sampling Rate

- **After every task commit:** Run quick command (≤30s feedback)
- **After every plan wave:** Run full suite (`make e2e-inapp-docker`)
- **Before `/gsd-verify-work`:** Full suite green + 7 acceptance gates verified
- **Max feedback latency:** 30s for unit, 480s for e2e

---

## Per-Task Verification Map

> Task IDs allocated per the planner's wave/plan layout (filled after Plan 29-XX commits land). Threat refs from Phase 29 threat model (Plan 29-01 produces).

| Task ID | Plan | Wave | Source D-XX / AMD-XX | Probe Ref | Test Type | Automated Command | File Exists | Status |
|---------|------|------|---------------------|-----------|-----------|-------------------|-------------|--------|
| 29-01-01 | 01 | 0 | spike: macOS bridge | PROBE-VAL-08 | spike | `python tools/spike_streaming_tee.py` | ❌ W0 | ⬜ pending |
| 29-01-02 | 01 | 0 | spike: OpenRouter usage | PROBE-VAL-01 / -02 | spike | `python tools/spike_openrouter_usage.py` | ❌ W0 | ⬜ pending |
| 29-01-03 | 01 | 0 | spike: post-hoc latency | PROBE-VAL-03 | spike | `python tools/spike_openrouter_generation_latency.py` | ❌ W0 | ⬜ pending |
| 29-01-04 | 01 | 0 | spike: Anthropic SSE | PROBE-VAL-13 | spike | `python tools/spike_anthropic_sse.py` | ❌ W0 | ⬜ pending |
| 29-01-05 | 01 | 0 | spike: age-cipher reuse | PROBE-VAL-07 | spike | `cd api_server && uv run pytest tests/spikes/test_age_cipher_provider_key.py` | ❌ W0 | ⬜ pending |
| 29-01-06 | 01 | 0 | spike: idempotency in-flight | PROBE-VAL-06 / -09 + AMD-03 | spike | `cd api_server && uv run pytest tests/spikes/test_idempotency_in_flight.py` | ❌ W0 | ⬜ pending |
| 29-02-01 | 02 | 1 | D-11 + AMD-04 (migration 013) | — | unit | `cd api_server && uv run pytest tests/migrations/test_013_proxy_columns.py` | ❌ W0 | ⬜ pending |
| 29-03-01 | 03 | 1 | D-09 / D-17 dispatcher | — | unit | `cd api_server && uv run pytest tests/services/test_proxy_dispatcher.py` | ❌ W0 | ⬜ pending |
| 29-04-01 | 04 | 2 | D-01 router + D-07 IP-map | — | unit | `cd api_server && uv run pytest tests/routes/test_llm_proxy.py::test_ip_lookup` | ❌ W0 | ⬜ pending |
| 29-04-02 | 04 | 2 | D-14 body mutation | — | unit | `cd api_server && uv run pytest tests/routes/test_llm_proxy.py::test_body_mutation` | ❌ W0 | ⬜ pending |
| 29-04-03 | 04 | 2 | D-03 + AMD-07 streaming parser | PROBE-VAL-13 | unit | `cd api_server && uv run pytest tests/services/test_stream_parser.py` | ❌ W0 | ⬜ pending |
| 29-04-04 | 04 | 2 | D-16 + AMD-02 + AMD-03 idempotency | PROBE-VAL-09 | unit | `cd api_server && uv run pytest tests/routes/test_llm_proxy.py::test_idempotency` | ❌ W0 | ⬜ pending |
| 29-05-01 | 05 | 2 | D-02 + D-02b BYOK | PROBE-VAL-07 / -11 | unit | `cd api_server && uv run pytest tests/services/test_proxy_byok_cache.py tests/services/test_byok_validation.py` | ❌ W0 | ⬜ pending |
| 29-06-01 | 06 | 3 | D-10 record_usage + D-12 anthropic parser | — | unit | `cd api_server && uv run pytest tests/services/test_usage_recorder.py::test_anthropic_native` | ❌ W0 | ⬜ pending |
| 29-07-01 | 07 | 3 | D-03 / D-10 backfill activity | PROBE-VAL-03 | unit | `cd api_server && uv run pytest tests/activities/test_backfill_openrouter_cost.py` | ❌ W0 | ⬜ pending |
| 29-08-01 | 08 | 4 | D-18 + AMD-06 runner via_proxy | — | unit | `cd api_server && uv run pytest tests/runner/test_via_proxy_env_injection.py` | ❌ W0 | ⬜ pending |
| 29-08-02 | 08 | 4 | D-04 nanobot recipe (AMD-01) | PROBE-VAL-05 | unit | `cd api_server && uv run pytest tests/recipes/test_nanobot_via_proxy.py` | ❌ W0 | ⬜ pending |
| 29-09-01 | 09 | 5 | D-19 + AMD-01 cutover script | — | integration | `cd api_server && uv run pytest tests/tools/test_migrate_phase29_nanobot_cutover.py` | ❌ W0 | ⬜ pending |
| 29-09-02 | 09 | 5 | acceptance gates 1–7 | all | e2e | `make e2e-inapp-docker E2E_FILTER=phase29` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> The 15 PROBE-VAL items map onto Wave 0 spikes (29-01-01 through 29-01-06 — each spike covers 2–3 probes; see 29-RESEARCH.md §Validation Architecture for the full mapping). Wave 0 must produce a markdown artifact under `.planning/phases/29-llm-egress-proxy/spikes/PROBE-VAL-NN.md` for EACH of the 15 probes BEFORE Wave 1 starts.

---

## Wave 0 Requirements

- [ ] `tools/spike_streaming_tee.py` — covers PROBE-VAL-08, -14 (FastAPI StreamingResponse + httpx tee, mid-stream 4xx)
- [ ] `tools/spike_openrouter_usage.py` — covers PROBE-VAL-01, -02 (`stream_options.include_usage` shape + `X-Generation-Id` header presence on success/error/streaming)
- [ ] `tools/spike_openrouter_generation_latency.py` — covers PROBE-VAL-03 (5+ requests, p50/p95/p99 latency to `/api/v1/generation`)
- [ ] `tools/spike_anthropic_sse.py` — covers PROBE-VAL-13 (cumulative-vs-delta `output_tokens` confirmation + `message_start` / `message_delta` shape)
- [ ] `tools/spike_byok_validation.py` — covers PROBE-VAL-04, -11 (auth swap per provider + OpenRouter `/key` 401 reliability)
- [ ] `tools/spike_recipe_base_url_honor.py` — covers PROBE-VAL-05 (each of 5 recipes honors `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` env)
- [ ] `tests/spikes/test_age_cipher_provider_key.py` — covers PROBE-VAL-07 (age-cipher round-trip with `provider_key_enc` column)
- [ ] `tests/spikes/test_idempotency_in_flight.py` — covers PROBE-VAL-06, -09 (concurrent retries + AMD-03 reserved-row pattern)
- [ ] `tests/spikes/test_docker_bridge_refresh.py` — covers PROBE-VAL-10, -15 (60s polling vs `events()` + bridge_ip uniqueness scope)
- [ ] `tests/spikes/test_ap_proxy_placeholder_bearer.py` — covers PROBE-VAL-12 (openai SDK + langchain-openai accept `ap-proxy-*` placeholder)
- [ ] Each spike writes its findings to `.planning/phases/29-llm-egress-proxy/spikes/PROBE-VAL-NN.md` with the empirical numbers and a PASS/FAIL verdict

> **Spike artifacts gate Wave 1.** If ANY of the 15 probes fails, the planner's assumption is invalidated and the plan goes back. This is golden-rule #5 ("test everything; spike gray areas BEFORE planning") applied at execute-time — even though research was already done, the spikes EMPIRICALLY confirm the assumptions before sealing the plan.

---

## Manual-Only Verifications

| Behavior | Acceptance Gate | Why Manual | Test Instructions |
|----------|-----------------|------------|-------------------|
| Mobile Usage screen shows non-zero `$` within 5s of send | Gate 3 (29-CONTEXT.md) | Mobile UI render assertion; flutter_test cannot assert against the real api_server's StreamingResponse SSE chain end-to-end without a fully booted api_server + Postgres + Docker bridge | (1) `make ios DEVICE=<id>` (2) deploy nanobot agent (3) send "hi" in chat (4) within 5s, AppBar Usage chip shows non-zero `$X.XXXXX` (5) tap → drawer shows non-zero token counts |
| BYOK key never appears in any log line | Gate 6 | Log-grepping is automatable but the validation requires the FULL chat round-trip happening (proxy + bot + upstream + record). Easiest as part of the manual e2e verification | After completing the manual chat above: `docker logs api_server 2>&1 \| grep -E "sk-or-\|sk-ant-\|sk-proj-" \|\| echo "PASS"` — must print "PASS" |
| Failure-injection: kill api_server during chat → user sees `bot_timeout` | Gate 5 | Requires SIGKILL to a running container mid-stream; not safe inside automated e2e harness without process-isolation primitives we don't have | (1) Send a long-running chat (2) `docker kill api_server` mid-stream (3) Bot retries land (Temporal `[1s,2s,4s]`) (4) After ~10s, mobile UI shows `bot_timeout` error chip (5) `docker start api_server` (6) Confirm `usage_logs` has NO partial row for the killed request (or has `status='failed'` with cost_usd=0) |

---

## Validation Sign-Off

- [ ] All 18 task verifications mapped to either `<automated>` command or Wave 0 spike artifact
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify (this matrix has at most 1 manual-only per acceptance gate)
- [ ] Wave 0 covers all 15 PROBE-VAL items in 29-RESEARCH.md §Validation Architecture
- [ ] No watch-mode flags (every command is one-shot)
- [ ] Feedback latency: 30s quick · 480s e2e
- [ ] All 7 acceptance gates from 29-CONTEXT.md mapped to either an e2e test or a manual verification
- [ ] `nyquist_compliant: true` set in frontmatter after planner produces task IDs and they are slot into this matrix

**Approval:** pending — flips to approved after Wave 0 spikes land their 15 artifacts and gsd-plan-checker confirms Dimension 8 coverage.
