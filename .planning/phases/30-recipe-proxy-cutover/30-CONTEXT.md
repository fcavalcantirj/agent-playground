# Phase 30: Migrate remaining recipes to egress proxy — Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 30 flips `runtime.via_proxy: true` on the **5 recipes** Phase 29 didn't cover (hermes, openclaw, zeroclaw, nullclaw, picoclaw), so every coding-agent deploy routes through the egress proxy and writes a `usage_logs` row with non-zero tokens + cost_usd. nanobot is already on the proxy (Phase 29 cutover). After Phase 30, **all 6 recipes** are via_proxy:true.

A small proxy enhancement ships first (Plan 30-00) so cost capture is empirically accurate for openrouter recipes — the proxy currently estimates cost from `cost_weights` (~3x off until post-hoc backfill catches up); reading OpenRouter's inline `usage.cost` eliminates that window.

**In scope:** 5 YAML flips, 5 per-recipe spikes (real-money, ~$0.05 total), 1 anthropic-shape proxy spike (real-money <$0.01), 1 proxy enhancement (read OpenRouter inline cost), per-flip regression-guard updates, a final cutover-verification plan.

**Out of scope (deferred):** Phase 29 follow-ups (transient `status='unknown'` row dedup from inapp_dispatcher's parallel write; mobile `bot_timeout` chip rendering from Phase 29 Gate 5); cost_weights schema extension for cache_read/cache_write categories; OpenRouter `user` field pass-through (Phase B prerequisite); --workers 1 cap removal (Phase 29 follow-up).

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

### Proxy implementation surface (modification sites)

- `api_server/src/api_server/services/stream_parser.py` — `_scan_openai` lines 163-170 + `finalize` lines 207-272 (D-09 modification site; ParsedUsage construction)
- `api_server/src/api_server/services/usage_recorder.py` — `_parse_openai_compat` (D-09 modification site for non-streaming JSON path); `ParsedUsage` dataclass (extend with optional `inline_cost_usd`)
- `api_server/src/api_server/services/proxy_dispatcher.py` — provider routing dispatch on `runtime.process_env.api_key` (AMD-06)
- `api_server/src/api_server/services/proxy_byok_cache.py` — Phase 29 in-process Postgres-backed cache (D-12 trust path)
- `api_server/src/api_server/services/inapp_substitutions.py` — `build_activation_substitutions(via_proxy=True)` placeholder swap (AMD-12)
- `api_server/src/api_server/services/inapp_recipe_index.py` — env injection dispatch on via_proxy (AMD-06)
- `api_server/src/api_server/services/recipes_loader.py` — `runtime.via_proxy` field surface
- `api_server/src/api_server/agent_lifecycle.py` — BYOK custody block, gated on `recipe.runtime.via_proxy=True` (Plan 29-05; mechanically guarantees Gate 7 — D-12)

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
- **AMD-06 dispatch logic** — `inapp_recipe_index.py` already inspects `runtime.process_env.api_key` and selects OPENAI_BASE_URL vs ANTHROPIC_BASE_URL injection; works for any recipe with `via_proxy: true`. No new dispatch code needed for Phase 30.
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

- **Cost-fidelity proof point on nanobot row 1:** $0.00112305 (cost_weights inline estimate) vs $0.00039345 (`/api/v1/generation` post-hoc actual). The 3x overestimate is the load-bearing motivation for D-09.
- **OpenClaw docs are the validation source for D-10**, not just speculation. Quote: "Anthropic still does not expose a per-message dollar estimate that OpenClaw can show in /usage full" — same constraint AP faces.
- **MSV's calculator** (`api/pkg/billing/calculator.go`) is a 60-line proof that the price-table approach is the right shape for cost computation when the upstream doesn't return cost; AP's Phase 27 `cost_weights` already implements the same pattern.
- **The 6-hotfix tail of Phase 29** is the realistic shape of "cutover work" — plans don't ship complete; expect each per-recipe flip to surface 0-2 hotfixes (BYOK leak, env-var quirk, JSON shape edge case).

</specifics>

<deferred>
## Deferred Ideas

### Out of Phase 30 (locked-decision deferrals)

- **Transient `unknown` row dedup** — inapp_dispatcher's parallel `usage_logs` write produces a transient `status='unknown'` row alongside the proxy's canonical `status='success'`. Cosmetic; route as Phase 30.5 / a separate cleanup phase after all 6 recipes are on the proxy.
- **Mobile `bot_timeout` chip** — Phase 29 Gate 5 deferred to "Phase 30 user testing". DB-layer fail-closed semantic is already PASS (`tests/routes/test_llm_proxy.py::test_d15_4xx_records_failed_row`). Mobile chip rendering is a Phase 30 follow-up at user discretion.
- **cost_weights schema extension** — adding `cache_read` and `cache_write` columns. Anthropic prompt caching makes cache_read tokens 90% cheaper than fresh input; openclaw uses caching aggressively. Without these columns, openclaw cost is structurally inflated. Defer to Phase 30.5 or cost-fidelity hardening phase.
- **OpenRouter `user: <id>` field pass-through** — Phase B (platform-billed credits) prerequisite. Not useful while AP is BYOK-only.
- **Plan 29-07 post-hoc backfill activity** — becomes vestigial for openrouter rows once D-09 ships (inline cost replaces the need to fetch `/api/v1/generation`). Keep as defense-in-depth in Phase 30; consider retirement in a later cleanup phase.
- **`--workers 1` cap on api_server** — Phase 29 hotfix `f98c040` capped to single worker because proxy state (BYOK cache, IP map) is in-process. Multi-worker requires Redis or PG LISTEN/NOTIFY for state fan-out. Phase 29 follow-up, not Phase 30.

### Reviewed Todos (not folded)

None — todo backlog query returned 0 pending items.

</deferred>

---

*Phase: 30-recipe-proxy-cutover*
*Context gathered: 2026-05-06*
