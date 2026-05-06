# Phase 30: Migrate remaining recipes to egress proxy — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-06
**Phase:** 30-recipe-proxy-cutover
**Areas discussed:** Scope, Sequencing, Spike depth, Phase shape, Cost capture (added during exploration), Wrap-up

---

## Gray-Area Selection (multi-select)

| Option | Description | Selected |
|--------|-------------|----------|
| Scope & cleanup | 4 vs 5 recipes; Phase 29 follow-ups inclusion | ✓ |
| Cutover sequencing & risk path | same-shape-first vs anthropic-first | ✓ |
| Per-recipe spike depth | full PROBE-VAL vs nanobot pattern-match vs new-shape-only | ✓ |
| Phase shape & atomicity | single phase / decimal sub-phases / single plan | ✓ |

**User's choice:** all 4 (free-text confirm: "all gray areas")

---

## Scope

### Q1: What's in Phase 30 scope?

| Option | Description | Selected |
|--------|-------------|----------|
| 5 recipes, no follow-ups | Flip 5; defer transient-unknown + mobile chip | ✓ |
| 5 recipes + transient-unknown dedup | Flip 5 + fix dispatcher's parallel write | |
| 5 recipes + Gate 5 chip + dedup | Full closure of Phase 29 deferred items | |
| 4 openrouter recipes only | Defer openclaw (anthropic) to Phase 31 | |

**User's choice:** 5 recipes, no follow-ups

### Q2: picoclaw inclusion?

| Option | Description | Selected |
|--------|-------------|----------|
| Include picoclaw in Phase 30 | Treat config.json::api_base as heredoc-eval variant | ✓ |
| Defer picoclaw to Phase 31 | Different plumbing pattern | |
| Spike picoclaw first; decide based on result | Conditional inclusion | |

**User's choice:** Include picoclaw in Phase 30

---

## Cutover sequencing

### Q1: Cutover order for the 5 recipes?

| Option | Description | Selected |
|--------|-------------|----------|
| openclaw first, then 4 openrouter | Fail-fast on highest-risk shape | ✓ |
| nullclaw first, ascending complexity | Validate pattern transfer cheaply | |
| hermes first per existing handoff | User's pre-/clear note (turned out to be misread) | |
| Stars-desc per project rule | Apply stars rule to migration order | |

**User's choice:** openclaw first

### Q2: Dedicated anthropic spike?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, dedicated Wave 0 spike | PROBE-VAL-ANTHROPIC before openclaw flip | ✓ |
| No, fold spike into openclaw plan | smoke test IS the spike | |
| Spike + openclaw in same wave | Saves a wave, loses fail-fast separation | |

**User's choice:** Dedicated Wave 0 spike

---

## Per-recipe spike depth

### Q1: Spike depth for the 4 openrouter recipes?

| Option | Description | Selected |
|--------|-------------|----------|
| One spike per recipe | ~$0.04 total; catches stack quirks | ✓ |
| Smoke-only per recipe | Trust nanobot pattern, no pre-flip spike | |
| Spike only Rust+Zig | Skip Python recipes (hermes, picoclaw) | |
| One combined sweep spike | tools/run_recipe.py --all-cells | |

**User's choice:** One spike per recipe

### Q2: Order within openrouter group?

| Option | Description | Selected |
|--------|-------------|----------|
| nullclaw → zeroclaw → picoclaw → hermes | Ascending complexity | ✓ |
| Stars-desc (zeroclaw → hermes → ...) | Apply project stars rule | |
| picoclaw first (schema variant) | Heredoc-eval inside JSON heredoc | |
| Order doesn't matter — Claude's discretion | Let planner choose | |

**User's choice:** nullclaw → zeroclaw → picoclaw → hermes

---

## Phase shape & atomicity

### Q1: How to bundle the 5 recipe migrations?

| Option | Description | Selected |
|--------|-------------|----------|
| Single Phase 30, one plan per recipe | ~6 plans, atomic per flip | ✓ |
| Decimal sub-phases (30.1, 30.2, ...) | 5 sub-phases, independent merging | |
| Single plan with tasks-per-recipe | One PR, biggest blast radius | |
| Two phases: 30 = openclaw, 31 = openrouter | Split highest-risk recipe into its own phase | |

**User's choice:** Single Phase 30, one plan per recipe

### Q2: Regression guard evolution?

| Option | Description | Selected |
|--------|-------------|----------|
| Update per-flip; final state asserts 6/6 | Each plan's TDD update edits the assertion | ✓ |
| Replace once at end of phase | Skip/xfail through phase, replace in final plan | |
| Drop the guard, replace with positive constraint | test_no_recipe_has_legacy_byok_provisioning | |

**User's choice:** Update per-flip; final state asserts 6/6

---

## Cost capture (added during exploration)

### Q1: cost_weights coverage hard prerequisite per recipe?

**Initial question framed around:** "openclaw uses anthropic/claude-haiku-4.5 — anthropic has NO post-hoc cost API, so cost_weights is the ONLY path."

**User's response (free-text):** "wait. you can stop and do tests. but, im almost sure that all inference, specially when flag to return json like, we can track token usage and costs. (check msv now for the proxy). we do via anthropic on msv, and, openrouter, HAS API FOR THAT; read; [4 OpenRouter doc URLs]"

**Action taken:** Halted decision-locking, fetched all 4 OpenRouter docs + MSV's billing calculator. Findings:

1. OpenRouter returns `usage.cost` and `usage.cost_details.upstream_inference_cost` automatically in every response (last SSE chunk for streams, top-level for non-streaming). No flags needed; `usage:{include:true}` is deprecated.
2. The proxy's `_scan_openai` reads `prompt_tokens`/`completion_tokens` but skips `cost`. This is why nanobot's row needed post-hoc backfill ($0.00112305 → $0.00039345).
3. MSV's billing calculator uses a price-table approach (`api/pkg/billing/calculator.go` — 60 lines, weighted sum × multiplier), confirming the pattern AP's Phase 27 `cost_weights` already implements.
4. Anthropic does NOT return cost in responses (token counts only).

### Q2: Include the proxy enhancement?

| Option | Description | Selected |
|--------|-------------|----------|
| Include in Phase 30 as Plan 30-00 | Read OpenRouter inline cost; small proxy enhancement | ✓ |
| Phase 30 = recipe flips only; proxy fix is Phase 30.5 | Strict scope | |
| Proxy fix first as Phase 30.0, then recipe flips | Promote to own decimal phase | |

**User's choice:** Include in Phase 30 as Plan 30-00

### Q3: openclaw (anthropic) cost path — first attempt

**User's response (free-text):** "wait. nope. lets study. always a correct way. https://docs.openclaw.ai/concepts/usage-tracking, https://docs.openclaw.ai/reference/token-use#token-use-and-costs, https://docs.openclaw.ai/reference/api-usage-costs"

**Action taken:** Fetched all 3 OpenClaw docs. Findings:

1. OpenClaw confirms: "Anthropic still does not expose a per-message dollar estimate that OpenClaw can show in /usage full" — empirical confirmation Anthropic has no cost-in-response.
2. OpenClaw uses a price table: `models.providers.<provider>.models[].cost` with USD-per-1M-tokens for input/output/cacheRead/cacheWrite — same shape as AP's `cost_weights`.
3. OpenClaw's two-tier model (provider-level usage endpoints + caller-level `/usage` commands) is at the agent level, orthogonal to AP's HTTP-layer proxy.

### Q3 (re-asked): openclaw cost path locked?

| Option | Description | Selected |
|--------|-------------|----------|
| cost_weights table (validated by OpenClaw pattern) | Same shape OpenClaw uses; populate before flip | ✓ |
| cost_weights + extend table to support cache_read/cache_write | Migration adds 2 cols for prompt-caching accuracy | |
| Return cost_usd=NULL for anthropic until users supply weights | Lazy; loses 'always show $' guarantee | |

**User's choice:** cost_weights table (validated by OpenClaw pattern)

---

## Wrap-up

### Q1: OpenRouter `user` tracking field — Phase 30 scope?

| Option | Description | Selected |
|--------|-------------|----------|
| Defer to Phase B | Sub-user analytics is platform-billed prerequisite | ✓ |
| Add to proxy in Phase 30 | Inject `user: ap-<id>` cheap to add now | |
| Add but only for non-BYOK | Decision deferred to Phase B | |

**User's choice:** Defer to Phase B

### Q2: BYOK cache pre-warming — special-case or trust Phase 29?

| Option | Description | Selected |
|--------|-------------|----------|
| Trust Phase 29 flow | First deploy populates cache | ✓ |
| Add explicit cache-warm step per recipe | Defends against first-deploy timing surprises | |

**User's choice:** Trust Phase 29 flow

---

## Claude's Discretion

- Spike implementation pattern (script under `tools/` vs `api_server/tests/spikes/`) — match Phase 29 PATTERNS.md convention.
- ParsedUsage field naming for the new inline cost (e.g. `inline_cost_usd` vs `provider_cost_usd`).
- Smoke test invocation — match nanobot's existing pattern from Plan 29-09.
- Plan 30-07 verification doc shape — mirror 29-VERIFICATION.md.

## Deferred Ideas (mentioned during discussion)

- Transient `unknown` row dedup (Phase 29 follow-up)
- Mobile `bot_timeout` chip rendering (Phase 29 Gate 5)
- cost_weights cache_read/cache_write schema extension
- OpenRouter `user: <id>` pass-through (Phase B)
- Plan 29-07 post-hoc backfill retirement (vestigial after D-09)
- `--workers 1` cap removal (multi-worker via Redis or PG LISTEN/NOTIFY)

## Notes on this session

- User intervened twice mid-discussion to halt assumption-locking and force empirical verification (per `feedback_test_everything_before_planning.md` golden rule #5). First intervention: cost-tracking generally; second: OpenClaw docs specifically. Both surfaced load-bearing decisions (D-09, D-10) that would have been wrong if locked from intuition.
- `feedback_root_cause_first.md` rule applied: D-09 is a root-cause fix (proxy never read inline cost) for a symptom (cost_weights overestimate window) that Phase 29's post-hoc backfill was masking.

---

## Post-CONTEXT Verification Round — 2026-05-06

After CONTEXT.md was committed at `a29d045`, user pushed back a third time: "annotate all, really, please. plus, DID YOU REMOVED ALL DOUBTS NOW, PRIOR TO PLAN/EXECUTE?" — invoking golden rule #5 a third time, this time AFTER decisions were locked.

Honest answer at that point was **no** — multiple D-XX decisions had been locked from intuition without empirical verification. A second verification round was performed (live Postgres queries via `deploy-postgres-1` + code reads on real paths + targeted webfetches). Findings annotated in CONTEXT.md `<verification_evidence>` section.

**Concrete corrections to CONTEXT.md from this round:**

1. agent_lifecycle.py path: claimed top-level → actually `routes/agent_lifecycle.py`
2. AMD-06 dispatch location: claimed `inapp_recipe_index.py` → actually `tools/run_recipe.py:1007` + `services/proxy_dispatcher.py:56`
3. cost_weights schema claim: implied 2-col (input/output) → actually 6-col incl. cache_read/cache_creation/ap_multiplier (no migration needed in Phase 30; D-10 conclusion holds, motivation walked back)
4. D-09 motivation: "3x overestimate active bug" → "source-of-truth simplification + Phase B prep" (cost_weights is empirically accurate today when ap_multiplier=1.0 and cache_read captured)
5. Hermes verified_cells coverage gap: `google/gemini-2.5-flash` is NOT in cost_weights. Plan 30-06 needs to populate before flip if smoke uses that cell.

**Plan-time spike work that was correctly NOT locked at discuss:**

| Item | Owns it | Status |
|------|---------|--------|
| Does each openrouter recipe honor OPENAI_BASE_URL? | D-05 spikes | UNKNOWN — empirical resolution by spike |
| Does openclaw honor ANTHROPIC_BASE_URL? | D-04 spike | UNKNOWN — empirical resolution by spike |
| Does picoclaw heredoc-eval $AP_PROXY_BASE_URL inside JSON heredoc on alpine /bin/sh? | D-05 picoclaw spike | UNKNOWN — empirical resolution by spike |
| AMD-07 anthropic parser e2e through proxy with REAL Anthropic | D-04 spike | UNKNOWN — synthetic SSE coverage exists, no real-traffic test |
| Dispatcher's parallel `usage_logs` race | Out of scope | Phase 29 follow-up; deferred per D-01 |

These remaining unknowns are LEGITIMATE plan-time spike work — the per-recipe spikes (D-05) and openclaw spike (D-04) exist precisely to resolve them. They are NOT discuss-time gaps.

---

## Reframe Round — 2026-05-06 (post-verification follow-on)

User pushed back a fourth time, this time on the framing of the spike work itself: *"all this time, all models, we used openrouter. why ask this now?? all this time we made it work how?"*

The framing in the previous round was wrong. **The recipes already make successful HTTP calls** to their providers today (verified_cells PASS). The proxy doesn't change agent env-var-reading; it changes the URL the **recipe** writes into the agent's config (heredoc) or CLI flag.

Empirical recipe inspection (`grep "api_base\|base_url\|openrouter.ai\|api.openai\|api.anthropic" recipes/*.yaml`) revealed:

| Recipe | Where base URL hardcoded | Real Phase 30 work |
|---|---|---|
| nullclaw | `recipes/nullclaw.yaml:468` config heredoc | Mechanical edit — same as nanobot. NO SPIKE. |
| picoclaw | `recipes/picoclaw.yaml:105 + :213` JSON heredocs | Mechanical edit — same as nanobot. NO SPIKE. |
| hermes | `process_env.base_url: null` (defaults to openrouter.ai internally) | CLI inspection (`hermes chat --help`) — no real traffic. |
| zeroclaw | `process_env.base_url: null` (set by `zeroclaw onboard`) | Config inspection — no real traffic. |
| openclaw | Anthropic SDK reads `ANTHROPIC_BASE_URL` (already injected) | YAML flip only; proxy spike (D-04) validates proxy side. |

**Corrections applied to CONTEXT.md:**

1. D-05 reframed: "4 pre-flip real-money spikes" → "0 pre-flip real-money spikes for openrouter recipes" (mechanical edits + local inspection)
2. D-06 order revised: nullclaw → picoclaw → zeroclaw → hermes (mechanical first)
3. D-07 plan layout: 30-03/30-04 are mechanical (nullclaw/picoclaw); 30-05/30-06 carry inspection burden (zeroclaw/hermes); 30-02 is openclaw flip + smoke
4. Phase 30 real-money commitment: $0.05 (4 openrouter spikes + 1 anthropic spike) → ~$0.06 (1 anthropic spike + 5 per-flip e2e smokes)
5. `<verification_evidence>` "Genuine plan-time spike work" table replaced with the corrected per-recipe matrix above

**Lesson for Claude (reinforcement of golden rule #5):** When a feature works in production today, the unknown for "modify it" is NOT "does the underlying mechanism work" — it's "does the modification preserve the working mechanism." Asking "does hermes honor OPENAI_BASE_URL" was a category error: hermes doesn't touch OPENAI_BASE_URL today, it touches its own configured base_url. The Phase 30 question is "where does each recipe configure base_url today, and how do I substitute it." That's an inspection question, not a probe question.
