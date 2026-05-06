# Phase 30: Migrate remaining recipes to egress proxy — Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 30 flips `runtime.via_proxy: true` on the **5 recipes** Phase 29 didn't cover (hermes, openclaw, zeroclaw, nullclaw, picoclaw), so every coding-agent deploy routes through the egress proxy and writes a `usage_logs` row with non-zero tokens + cost_usd. nanobot is already on the proxy (Phase 29 cutover). After Phase 30, **all 6 recipes** are via_proxy:true.

A small proxy enhancement ships first (Plan 30-00) so the proxy reads OpenRouter's inline `usage.cost` field directly. **Note (post-verification 2026-05-06):** the proxy's existing `cost_weights` computation IS empirically accurate today for typical traffic (matches `/v1/generation` to the cent when `ap_multiplier=1.0` and cache_read tokens are captured). D-09 is therefore source-of-truth simplification + Phase B prep, not an active-bug fix — see `<verification_evidence>` below.

**In scope:** 5 YAML flips, 5 per-recipe spikes (real-money, ~$0.05 total), 1 anthropic-shape proxy spike (real-money <$0.01), 1 proxy enhancement (read OpenRouter inline cost), per-flip regression-guard updates, a final cutover-verification plan.

**Out of scope (deferred):** Phase 29 follow-ups (transient `status='unknown'` row dedup from inapp_dispatcher's parallel write; mobile `bot_timeout` chip rendering from Phase 29 Gate 5); OpenRouter `user` field pass-through (Phase B prerequisite); --workers 1 cap removal (Phase 29 follow-up). **NOT** out of scope despite earlier framing: cost_weights schema extension — verified the schema **already** has `cache_read_per_1m_usd` + `cache_creation_per_1m_usd`. No migration needed.

</domain>

<decisions>
## Implementation Decisions

### Scope

- **D-01:** Phase 30 ships **5 recipe flips** — hermes, openclaw, zeroclaw, nullclaw, picoclaw — to `runtime.via_proxy: true`. Phase 29's deferred cosmetic items (transient unknown-row dedup, mobile bot_timeout chip) explicitly **NOT** in scope; route them as separate work after Phase 30 lands.
- **D-02:** **picoclaw is included** in Phase 30. Its `config.json::model_list[0].api_base` is baked at container start via the same sh-heredoc evaluation nanobot uses for `${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}`. The runner already evaluates the heredoc; no runner extension needed (validated empirically by the per-recipe spike — D-05).

### Sequencing

- **D-03:** **openclaw flips first** (anthropic-shape — fail-fast on the proxy's only un-tested provider path). Then 4 openrouter recipes in this order: **nullclaw → zeroclaw → picoclaw → hermes** (ascending complexity within the proven shape).
- **D-04:** **Plan 30-01 = dedicated PROBE-VAL-ANTHROPIC spike** before openclaw YAML flip. Real-money streaming `POST /v1/messages` to anthropic/claude-haiku-4.5 through the proxy, asserts: (a) `usage_logs` row with `status='success'`; (b) AMD-07 cumulative-tokens last-wins applied (assert `[5,12,17] → 17` regression); (c) `cost_usd > 0` from cost_weights. Real cost <$0.01.

### Spike depth

- **D-05:** **One pre-flip spike per openrouter recipe** (4 spikes, ~$0.04 real-money total). Each spike: `docker run` with `AP_PROXY_BASE_URL` injected, real OpenRouter call, assert `usage_logs` row + non-zero cost_usd. Catches stack-specific env-var quirks early — Rust (zeroclaw) and Zig (nullclaw) are the highest risk for not honoring `OPENAI_BASE_URL` semantics.
- **D-06:** Order within openrouter group: **nullclaw → zeroclaw → picoclaw → hermes**. Rationale: Zig 8 MB → Rust → Python+config-json variant → Python heaviest. Smallest/fastest first to surface env-var quirks; biggest last (hermes 5.2 GB image, slowest iteration).

### Phase shape

- **D-07:** **Single Phase 30, one plan per recipe** (~7 plans total). Layout:
  - `30-00`: proxy enhancement — read OpenRouter inline `cost` (D-09)
  - `30-01`: PROBE-VAL-ANTHROPIC spike (D-04)
  - `30-02`: openclaw YAML flip + e2e smoke
  - `30-03`: nullclaw spike + flip + smoke
  - `30-04`: zeroclaw spike + flip + smoke
  - `30-05`: picoclaw spike + flip + smoke (heredoc-eval substitution validation)
  - `30-06`: hermes spike + flip + smoke
  - `30-07`: cutover verification + regression-guard rewrite (D-08)

  Each plan ships atomically (own SUMMARY, own commit). Per-recipe rollback via `git revert <plan-tail>`.
- **D-08:** **Regression guard updates per-flip.** Each plan's TDD update edits `test_only_nanobot_has_via_proxy` (or its successor) to add the flipped recipe to the asserted set. Plan 30-07 finalizes by replacing it with `test_all_recipes_have_via_proxy` asserting all 6 (nanobot + the 5 new) have `runtime.via_proxy: true`.

### Cost capture

- **D-09:** **Plan 30-00 = proxy reads OpenRouter inline `cost`.** OpenRouter returns `usage.cost` (and `usage.cost_details.upstream_inference_cost`) automatically in every response — last SSE chunk for streams, top-level for non-streaming. Modify `StreamUsageParser._scan_openai` (`api_server/src/api_server/services/stream_parser.py:163-170`) and `_parse_openai_compat` (`usage_recorder.py`) to capture `cost`; extend `ParsedUsage` with optional `inline_cost_usd: float | None`. When present, persist directly as `usage_logs.cost_usd`; when absent, fall back to existing `cost_weights` lookup. Eliminates the ~3x cost_weights overestimate window proven on nanobot's first row ($0.00112305 → $0.00039345 after backfill). Plan 29-07 post-hoc backfill activity becomes vestigial for openrouter rows but is **kept as defense-in-depth**.
- **D-10:** **openclaw cost path = cost_weights table only.** Anthropic does **not** return cost in responses (confirmed empirically: OpenRouter docs `/usage-accounting` + OpenClaw docs `/reference/api-usage-costs` both state Anthropic exposes only token counts). OpenClaw itself solves this with a USD-per-1M-tokens price table — the same shape as AP's Phase 27 `cost_weights`. Plan 30-01 spike's first test asserts `cost_weights` has a row covering `anthropic/claude-haiku-4.5` (and any other openclaw `verified_cells[]` model); populate before flip if missing. **No cost_weights schema extension** (cache_read/cache_write columns) in Phase 30 — cache pricing accuracy deferred.

### Out-of-scope follow-ups (locked decisions, deferred)

- **D-11:** OpenRouter `user: <id>` request-body pass-through is a **Phase B prerequisite**, not Phase 30 scope. Today AP is BYOK-only and OpenRouter attributes correctly via the BYOK key owner; AP-platform-billed (Phase B) is when sub-user analytics matter.
- **D-12:** **Trust Phase 29's BYOK custody flow** for cache pre-warming. Per-recipe first deploy populates that recipe's `provider_key_enc` row — no explicit pre-warm step needed in any per-recipe plan. The spike's deploy IS the cache populate.

### Claude's Discretion

- Spike implementation pattern (script under `tools/` vs `api_server/tests/spikes/`) — match Phase 29 PATTERNS.md convention.
- ParsedUsage field naming for the new inline cost (e.g. `inline_cost_usd` vs `provider_cost_usd`).
- Smoke test invocation — match nanobot's existing pattern from Plan 29-09.
- Plan 30-07 verification doc shape — mirror 29-VERIFICATION.md.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 29 — load-bearing precedent

- `.planning/phases/29-llm-egress-proxy/29-CONTEXT.md` — 19 D-XX + 7 AMD-XX (especially AMD-06 dispatch rule, AMD-07 cumulative-tokens last-wins, AMD-09 substitution pattern, AMD-12 placeholder swap)
- `.planning/phases/29-llm-egress-proxy/29-RESEARCH.md` — provider dispatch table (anthropic vs openai vs openrouter SSE shapes), AMD-07 cumulative-usage rule
- `.planning/phases/29-llm-egress-proxy/29-VERIFICATION.md` — 7 acceptance gates (Gate 1/2/4/7 mechanical templates), 6 hotfixes (7a04177→e6040d7) showing realistic failure modes
- `.planning/phases/29-llm-egress-proxy/29-PATTERNS.md` — file analog map; `tools/` spike script convention; cache-pattern mirroring inapp_recipe_index

### Recipes (the 5 cutover targets + nanobot reference)

- `recipes/nanobot.yaml` — TEMPLATE: `runtime.via_proxy: true` + `${AP_PROXY_BASE_URL:-...}` heredoc-eval pattern (lines 40-77)
- `recipes/hermes.yaml` — openrouter, Python/uv, 5.2 GB; `runtime.process_env.api_key=OPENROUTER_API_KEY`
- `recipes/openclaw.yaml` — **anthropic-direct**, Node/TS, ~5 GB; `runtime.process_env.api_key=ANTHROPIC_API_KEY`; only anthropic-shape recipe in the catalog
- `recipes/zeroclaw.yaml` — openrouter, Rust, env-var honoring is a per-recipe spike risk
- `recipes/nullclaw.yaml` — openrouter, Zig, 8 MB; smallest image, fastest spike turnaround
- `recipes/picoclaw.yaml` — openrouter, Python; api_base baked into config.json via sh-heredoc

### Proxy implementation surface (modification sites — VERIFIED PATHS)

- `api_server/src/api_server/services/stream_parser.py` — `_scan_openai` lines 163-170 + `finalize` lines 207-272 (D-09 modification site for streaming; ParsedUsage construction)
- `api_server/src/api_server/services/usage_recorder.py` — `_parse_openai_compat` lines 138-166 (D-09 modification site for non-streaming JSON; reads `prompt_tokens`/`completion_tokens` only — confirmed it does NOT read `usage.cost`); `ParsedUsage` dataclass lines 63-78 (extend with optional `inline_cost_usd`); `_compute_cost` line 270 (cost_weights lookup; honors all 4 token classes including cache_read/cache_creation)
- `api_server/src/api_server/services/proxy_dispatcher.py` — `PROVIDERS` table (3 providers configured: openrouter/openai/anthropic) + `ENV_TO_PROVIDER` line 56 (3-key map: OPENROUTER_API_KEY→openrouter, ANTHROPIC_API_KEY→anthropic, OPENAI_API_KEY→openai)
- `api_server/src/api_server/services/proxy_byok_cache.py` — Phase 29 in-process Postgres-backed cache (D-12 trust path)
- `api_server/src/api_server/services/inapp_substitutions.py` — `build_activation_substitutions(via_proxy=True)` placeholder swap (AMD-12)
- `api_server/src/api_server/services/recipes_loader.py` — `runtime.via_proxy` field surface
- `api_server/src/api_server/routes/agent_lifecycle.py` line 348 — BYOK custody block (validate + encrypt + persist + cache + provider_key_enc write) gated on `via_proxy_flag` (Phase 29 D-02b; mechanically guarantees Gate 7 — D-12). Calls `build_activation_substitutions(via_proxy=via_proxy_flag)` at line 498
- `tools/run_recipe.py` lines 978-1042 — `_build_via_proxy_overrides` and `_PROXY_BASE_URL_ENV_BY_API_KEY` map. **This is where AMD-06 dispatch actually lives** for the standalone runner. Maps `OPENROUTER_API_KEY`→`OPENAI_BASE_URL`, `OPENAI_API_KEY`→`OPENAI_BASE_URL`, `ANTHROPIC_API_KEY`→`ANTHROPIC_BASE_URL`. The api_server-side equivalent is `services/proxy_dispatcher.py::ENV_TO_PROVIDER` (mirrored, kept in sync)
- `api_server/src/api_server/temporal/activities/backfill_openrouter_cost.py` line 146 — `UPDATE usage_logs SET cost_usd = $1 WHERE id = $2`. **Overwrites unconditionally** when `/v1/generation` returns 200 — empirically verified. This means inline cost_weights computation is the **first** value, then OpenRouter's authoritative `total_cost` overwrites
- `api_server/src/api_server/temporal/workflows/backfill_openrouter_cost.py` — workflow that schedules the activity (Plan 29-07)

### External docs (empirically verified)

- https://openrouter.ai/docs/guides/administration/usage-accounting.md — confirms `cost` returned in every response (last SSE chunk for streams); `usage:{include:true}` is deprecated/no-op (D-09 source)
- https://openrouter.ai/docs/guides/administration/user-tracking.md — `user: <id>` body field, deferred to Phase B (D-11)
- https://openrouter.ai/docs/guides/features/input-output-logging.md — admin/observability feature, NOT a cost path (verified non-relevant)
- https://docs.openclaw.ai/concepts/usage-tracking — OpenClaw's two-tier model (provider-level + caller-level)
- https://docs.openclaw.ai/reference/api-usage-costs — confirms "Anthropic still does not expose a per-message dollar estimate" (D-10 source)
- https://docs.openclaw.ai/reference/token-use — OpenClaw's price-table shape: `models.providers.<provider>.models[].cost` USD per 1M tokens for input/output/cacheRead/cacheWrite (validates Phase 27 cost_weights pattern; D-10)

### MSV reference (industry pattern)

- `meusecretariovirtual/api/pkg/billing/calculator.go` — token-weighted poken cost calculator (`(in*WeightIn + out*WeightOut + BaseCost) * modelMultiplier`); same price-table shape AP uses; validates D-10

### Project rules

- `CLAUDE.md` §"End-to-end tests on macOS" — all e2e validation runs via `make e2e-inapp-docker`, not native uvicorn (proxy IP-map only resolves on the bridge network); applies to every per-recipe smoke
- `memory/feedback_test_everything_before_planning.md` — golden rule #5; the cost-tracking investigation just demonstrated this rule (user push-back forced empirical verification before locking)
- `memory/feedback_root_cause_first.md` — the D-09 finding (proxy never read inline cost) is a root-cause example; estimating from cost_weights when authoritative cost was in the response body
- `memory/feedback_dumb_client_no_mocks.md` — clients NEVER compute cost; api_server returns cost_usd ready-to-render
- `memory/feedback_no_mocks_no_stubs.md` — every per-recipe spike hits real OpenRouter / real Anthropic; no mocks for the cutover gate

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **AMD-09 substitution pattern** — `${AP_PROXY_BASE_URL:-https://...}` in `recipes/nanobot.yaml` is sh-evaluated at container start (heredoc context). Reuse for hermes/zeroclaw/nullclaw/picoclaw via the same `api_base` field substitution. Mechanically already-working through `tools/run_recipe.py::substitute_argv` and the inapp recipe index.
- **AMD-06 dispatch logic** — `tools/run_recipe.py:1007` (`_build_via_proxy_overrides`) inspects `runtime.process_env.api_key` and selects OPENAI_BASE_URL vs ANTHROPIC_BASE_URL injection; the api_server-side mirror is `services/proxy_dispatcher.py::ENV_TO_PROVIDER`. Works for any recipe with `via_proxy: true`. **Closed enum** — only OPENROUTER_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY are recognized; raises ValueError on anything else. No new dispatch code needed for Phase 30; existing dispatch already covers all 5 cutover targets.
- **`StreamUsageParser`** — Phase 29's byte-level SSE parser. D-09 extends `_scan_openai` to also capture `usage.cost`; existing buffering / chunked-byte plumbing is unchanged.
- **`ParsedUsage` dataclass** (`usage_recorder.py`) — frozen-shape value object the proxy persists. Extend with `inline_cost_usd: float | None`; `usage_logs.cost_usd` write-site (`routes/llm_proxy.py`) prefers `inline_cost_usd` when not None, else falls back to existing cost_weights lookup.
- **Plan 29-05's `via_proxy` gate** — entire BYOK custody block (validate + encrypt + persist + cache) wraps in `if getattr(recipe.runtime, 'via_proxy', False):`. Gate 7 (no `provider_key_enc` on legacy deploys) is **mechanically guaranteed** for every recipe Phase 30 flips, no per-recipe work required.
- **`make e2e-inapp-docker`** — dockerized harness joining the bridge network. Every per-recipe smoke runs through this, never native uvicorn.

### Established Patterns

- **Spike-then-flip cadence** — Plan 29-01 ran 15 PROBE-VAL spikes before any code shipped; same pattern per Phase 30 plan: each `30-0X` plan starts with the recipe's pre-flip spike (Wave 0 of that plan), then YAML flip, then e2e smoke.
- **Test-first-rollout** — Phase 29's `test_only_nanobot_has_via_proxy` (singleton-set assertion) is the precedent; D-08 evolves it per-flip.
- **Hotfix-tolerant plan structure** — Phase 29 needed 6 hotfixes after main plans shipped (`7a04177`→`e6040d7`). Phase 30 plans should leave room for similar post-flip hotfixes per recipe; the per-recipe spike de-risks but doesn't eliminate them.

### Integration Points

- **Plan 30-00 (proxy fix)** lands first: must not regress nanobot's existing usage capture. Test gate: re-run nanobot e2e through `make e2e-inapp-docker` after 30-00; assert `inline_cost_usd` populated with OpenRouter's `cost` field (non-zero).
- **Cost_weights table** must cover `anthropic/claude-haiku-4.5` (openclaw spike) before Plan 30-01 fires. Plan 30-01 Task 0 = `SELECT * FROM cost_weights WHERE model_id='anthropic/claude-haiku-4.5'`; if empty, populate from Anthropic's published pricing.
- **Per-recipe spike scripts** under `tools/` (PATTERNS.md convention) or `api_server/tests/spikes/`. Each is a small one-shot Python script that `docker run`s the recipe with `AP_PROXY_BASE_URL` injected and asserts the resulting `usage_logs` row.

</code_context>

<specifics>
## Specific Ideas

- **Cost-fidelity reality (refined post-verification 2026-05-06):** Phase 29 verification originally framed nanobot row 1 as `$0.00112305 (cost_weights inline) → $0.00039345 (post-hoc backfill)`. The current empirical state is more nuanced: cost_weights TODAY produces `$0.00039345` directly when cache_read is captured (`5111 input - 4992 cached + 4992 cached × $0.075/1M + 119 fresh × $0.15/1M + 2 output × $0.60/1M = $0.00039345`, exact). Either backfill normalized the original row, or the original `$0.00112305` was a transient cost_weights-without-cache-aware computation that's since been fixed. **D-09's strict "3x overestimate" framing is partially refuted**: cost_weights is accurate today when (a) row carries cache_read tokens AND (b) ap_multiplier=1.0. D-09 still has merit as **source-of-truth alignment** (OR's `cost` field is canonical) and **Phase B prep** (multiplier applies to OR's actual cost, not our estimate), but it's not fixing a current bug — it's eliminating a maintenance surface (cost_weights row maintenance for openrouter models).
- **OpenClaw docs are the validation source for D-10**, not just speculation. Quote: "Anthropic still does not expose a per-message dollar estimate that OpenClaw can show in /usage full" — same constraint AP faces.
- **MSV's calculator** (`api/pkg/billing/calculator.go`) is a 60-line proof that the price-table approach is the right shape for cost computation when the upstream doesn't return cost; AP's Phase 27 `cost_weights` already implements the same pattern.
- **The 6-hotfix tail of Phase 29** is the realistic shape of "cutover work" — plans don't ship complete; expect each per-recipe flip to surface 0-2 hotfixes (BYOK leak, env-var quirk, JSON shape edge case).
- **cost_weights schema is already 4-class** (input + output + cache_read + cache_creation + ap_multiplier). My earlier "no schema extension" claim in D-10 was based on a false premise that the schema only had input/output. Verified empirically — see `<verification_evidence>` below. **No migration needed for any cost-pricing accuracy in Phase 30.**

</specifics>

<verification_evidence>
## Empirical Verification Pass — 2026-05-06

This section documents what was checked AGAINST live state vs. assumed during the discuss session. Two user push-backs ("you can stop and do tests"; "I gave you links to study dude. do tests. verify b4.") forced this round.

### Verified facts (live infra + code reads)

| Claim | Method | Result |
|---|---|---|
| `cost_weights` schema | `\d cost_weights` on `deploy-postgres-1` | 8 cols incl. `input_per_1m_usd`, `output_per_1m_usd`, **`cache_read_per_1m_usd`** (nullable), **`cache_creation_per_1m_usd`** (nullable), `ap_multiplier` (default 1.0). PK = (provider, model). |
| `cost_weights` rows | `SELECT * FROM cost_weights ORDER BY model` | 8 rows. Coverage: openrouter+anthropic forms of `claude-haiku-4.5`/`claude-haiku-4-5`/`claude-sonnet-4.5`/`claude-sonnet-4-5`; openrouter+openai forms of `gpt-4o-mini`; openrouter `xiaomi/mimo-v2.5`, `minimax/minimax-m2.5:free`. **MISSING**: `google/gemini-2.5-flash` (referenced by `recipes/hermes.yaml:152`) and any model in `recipes/zeroclaw.yaml::verified_cells` beyond `anthropic/claude-haiku-4.5`. |
| `usage_logs` schema | `\d usage_logs` | 20 cols incl. `cost_usd numeric(14,8)`, `cache_read_tokens`, `cache_creation_tokens`, `proxy_latency_ms`, `upstream_latency_ms`. Status check constraint allows `success/error/unknown/failed`. Timestamp col is `created_at` (NOT `recorded_at`). |
| Recent successful proxy rows | `SELECT ... FROM usage_logs WHERE status='success' ORDER BY created_at DESC LIMIT 3` | 3 rows, all `provider=openrouter`, `model=openai/gpt-4o-mini`. Latest at 22:24:00 has `cost_usd=$0.00039345`, `cache_read=4992` — matches manual cost_weights computation EXACTLY. |
| `_parse_openai_compat` reads `cost`? | Read `usage_recorder.py:138-166` | NO. Only reads `prompt_tokens`/`completion_tokens`/`cache_read_input_tokens`/`prompt_tokens_details.cached_tokens`/`cache_creation_input_tokens`. The `cost` field in OpenRouter's response is silently dropped. |
| `_compute_cost` source-of-truth | Read `usage_recorder.py:270-292` | Reads `cost_weights` for (provider, model) and computes USD from 4 token classes × per-1M-usd × `ap_multiplier`. No inline-cost path. |
| Phase 29-07 backfill activity | Read `temporal/activities/backfill_openrouter_cost.py:143-148` | Reads `data["total_cost"]` from `/api/v1/generation`, `UPDATE usage_logs SET cost_usd = $1` **unconditionally** when 200. Will overwrite cost_weights value. |
| `agent_lifecycle.py` location | `find ... -name agent_lifecycle*` | At `routes/agent_lifecycle.py` (NOT top-level — my earlier path was wrong). Line 348 = `if via_proxy_flag:` BYOK custody gate; line 498 = `build_activation_substitutions(via_proxy=via_proxy_flag)` call. |
| AMD-06 dispatch location | `grep via_proxy in services/inapp_recipe_index.py` | NO matches. **Dispatch lives in `tools/run_recipe.py:1007-1042`** (`_build_via_proxy_overrides`). The api_server-side mirror is `services/proxy_dispatcher.py::ENV_TO_PROVIDER` (line 56). |
| `tools/run_recipe.py` env map | Read lines 995-1003 | `OPENROUTER_API_KEY → OPENAI_BASE_URL`; `OPENAI_API_KEY → OPENAI_BASE_URL`; `ANTHROPIC_API_KEY → ANTHROPIC_BASE_URL`. Closed enum, ValueError on miss. |
| `proxy_dispatcher.py::PROVIDERS` | Read lines 26-51 | 3 providers: `openrouter` (`Bearer`, sse=openai, `HTTP-Referer`+`X-Title` headers); `openai` (`Bearer`, sse=openai); `anthropic` (`x-api-key`, sse=anthropic, `anthropic-version: 2023-06-01`). |
| OpenRouter inline cost | `webfetch /docs/guides/administration/usage-accounting.md` | `usage.cost` returned automatically per request; last SSE chunk for streams. `usage:{include:true}` deprecated/no-op. `cost_details.upstream_inference_cost` only on BYOK. |
| OpenRouter input-output-logging | `webfetch /docs/guides/features/input-output-logging.md` | Admin/observability feature, NOT cost path. Irrelevant to Phase 30. |
| OpenRouter user-tracking | `webfetch /docs/guides/administration/user-tracking.md` | `user: <id>` body field; metadata only; deferred to Phase B (D-11). |
| OpenRouter structured-outputs | `webfetch /docs/guides/features/structured-outputs.md` | Response-format feature (JSON Schema validation); does NOT change usage/cost block. Irrelevant to Phase 30. |
| OpenClaw usage-tracking | `webfetch /docs.openclaw.ai/concepts/usage-tracking` | Two-tier model: provider-level + caller-level. Provider-level uses upstream usage endpoints. |
| OpenClaw api-usage-costs | `webfetch /docs.openclaw.ai/reference/api-usage-costs` | "Anthropic still does not expose a per-message dollar estimate that OpenClaw can show in /usage full" — D-10 source. |
| OpenClaw token-use | `webfetch /docs.openclaw.ai/reference/token-use` | Price table: `models.providers.<provider>.models[].cost` USD per 1M tokens for input/output/cacheRead/cacheWrite. **Same shape as AP's cost_weights — validates the pattern.** |
| Recipe `verified_cells[]` models | `grep "model:" recipes/*.yaml` | hermes: anthropic/claude-haiku-4.5, openai/gpt-4o-mini, **google/gemini-2.5-flash (NOT in cost_weights)**. zeroclaw: anthropic/claude-haiku-4.5. nullclaw: anthropic/claude-haiku-4.5, openrouter/anthropic/claude-haiku-4.5. picoclaw: openai/gpt-4o-mini, anthropic/claude-haiku-4.5. openclaw: anthropic/claude-haiku-4.5, anthropic/claude-haiku-4-5, anthropic/claude-sonnet-4.5, openai/gpt-4o-mini. |

### Findings that contradicted my discuss-session claims

1. **D-10 motivation was wrong** — I implied cost_weights schema lacked cache columns. It already has `cache_read_per_1m_usd` + `cache_creation_per_1m_usd` (both nullable, properly populated for anthropic/claude-haiku models). Decision (cost_weights only, no schema work) is still correct, but the framing in the deferred section ("schema extension deferred") needs walking back.
2. **D-09 motivation softened** — the "3x overestimate window" was real for the original Phase 29 row, but is empirically NOT present today. cost_weights with cache-aware computation produces exact values matching `/v1/generation` (when ap_multiplier=1.0). D-09 remains valuable but as **source-of-truth simplification + Phase B prep**, not an active-bug fix.
3. **AMD-06 dispatch location wrong** — claimed in CONTEXT to be in `inapp_recipe_index.py`. Empirically lives in `tools/run_recipe.py:1007` + `services/proxy_dispatcher.py:56`. Path corrected above.
4. **agent_lifecycle.py path wrong** — claimed top-level. Actual: `routes/agent_lifecycle.py`. Path corrected above.
5. **Hermes verified_cells coverage gap** — `google/gemini-2.5-flash` is NOT in cost_weights. Plan 30-06 (hermes flip) needs a cost_weights row populated before flip if smoke uses that cell.

### Genuine plan-time spike work (NOT verified in discuss; correctly punted to PROBE-VAL)

These are the legitimate unknowns the per-recipe spikes (D-04, D-05) exist to resolve. **Do NOT lock these decisions before research/plan phase.**

| Item | Owns it | Why empirically unknown |
|---|---|---|
| Does each of hermes/zeroclaw/nullclaw/picoclaw honor `OPENAI_BASE_URL` env? | D-05 spikes (Plans 30-03..30-06 Wave 0) | Each agent's stack reads env differently. Rust/Zig especially — no precedent. |
| Does openclaw honor `ANTHROPIC_BASE_URL`? | D-04 spike (Plan 30-01) | Anthropic SDK does honor it; openclaw's wrapper might override. |
| Does picoclaw's `${AP_PROXY_BASE_URL:-...}` actually shell-expand inside its `cat <<EOF ... EOF` JSON heredoc? | D-05 picoclaw spike (Plan 30-05 Wave 0) | nanobot uses the same pattern but its heredoc may have different quoting. picoclaw's alpine `/bin/sh` (busybox/ash) is also a different shell than nanobot's. |
| AMD-07 anthropic cumulative-tokens parser, end-to-end through proxy with REAL Anthropic | D-04 spike (Plan 30-01) | Phase 29 Plan 04 unit-tests cover the parser shape with synthetic SSE. No real-traffic e2e to date. |
| Does the dispatcher's parallel `usage_logs` write race produce a `status='unknown'` row when proxy writes `success`, OR does the proxy now win the write? | Out of scope per D-01 | Phase 29 Open follow-up. Cosmetic; defer. |

</verification_evidence>

<deferred>
## Deferred Ideas

### Out of Phase 30 (locked-decision deferrals)

- **Transient `unknown` row dedup** — inapp_dispatcher's parallel `usage_logs` write produces a transient `status='unknown'` row alongside the proxy's canonical `status='success'`. Cosmetic; route as Phase 30.5 / a separate cleanup phase after all 6 recipes are on the proxy.
- **Mobile `bot_timeout` chip** — Phase 29 Gate 5 deferred to "Phase 30 user testing". DB-layer fail-closed semantic is already PASS (`tests/routes/test_llm_proxy.py::test_d15_4xx_records_failed_row`). Mobile chip rendering is a Phase 30 follow-up at user discretion.
- **cost_weights schema extension** — ~~adding `cache_read` and `cache_write` columns~~. **Already present** (verified 2026-05-06): `cache_read_per_1m_usd` + `cache_creation_per_1m_usd` in cost_weights. No schema migration needed. The remaining concern is per-row coverage for new models (e.g. `google/gemini-2.5-flash` — see verification evidence).
- **OpenRouter `user: <id>` field pass-through** — Phase B (platform-billed credits) prerequisite. Not useful while AP is BYOK-only.
- **Plan 29-07 post-hoc backfill activity** — becomes vestigial for openrouter rows once D-09 ships (inline cost replaces the need to fetch `/api/v1/generation`). Keep as defense-in-depth in Phase 30; consider retirement in a later cleanup phase.
- **`--workers 1` cap on api_server** — Phase 29 hotfix `f98c040` capped to single worker because proxy state (BYOK cache, IP map) is in-process. Multi-worker requires Redis or PG LISTEN/NOTIFY for state fan-out. Phase 29 follow-up, not Phase 30.
- **cost_weights row population for `google/gemini-2.5-flash`** — required for hermes verified_cells[2]. Populate as part of Plan 30-06 spike if the spike actually exercises that cell; otherwise defer to a cost-coverage hardening phase.

### Reviewed Todos (not folded)

None — todo backlog query returned 0 pending items.

</deferred>

---

*Phase: 30-recipe-proxy-cutover*
*Context gathered: 2026-05-06*
