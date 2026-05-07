---
phase: 30-recipe-proxy-cutover
status: researched
created: 2026-05-06
updated: 2026-05-06
---

# Phase 30 — Recipe proxy cutover (5 recipes) — RESEARCH

**Researched:** 2026-05-06
**Domain:** YAML substitution + small proxy cost-capture extension + per-recipe e2e validation through `make e2e-inapp-docker`. NOT a new architectural surface — this phase rides Phase 29's proxy + dispatch + custody plumbing.
**Confidence:** HIGH on all 5 recipe surfaces (every base-URL location empirically located in CONTEXT verification round + re-verified here); HIGH on cost-capture shape (OpenRouter docs reverified live); HIGH on anthropic SSE shape (Anthropic docs explicit cumulative warning); MEDIUM on hermes/zeroclaw inspection deliverables (genuine spike-time work — see Open Questions).

## Summary

Phase 30 flips `runtime.via_proxy: true` on the **5 remaining recipes** (openclaw, nullclaw, picoclaw, zeroclaw, hermes — order per D-03/D-06). Phase 29 already shipped the load-bearing surface: the proxy at `POST /v1/llm/forward/{path:path}`, the BYOK custody flow gated on `via_proxy_flag` in `routes/agent_lifecycle.py:348`, the `_build_via_proxy_overrides` env-injection dispatch in `tools/run_recipe.py:1007`, the `proxy_dispatcher.py::PROVIDERS` table covering all 3 providers. Nanobot proves the path end-to-end (Phase 29 Gate 1 PASS at `e6040d7`).

Five flips, classified by mechanical effort:

| Recipe | Effort | Surface |
|---|---|---|
| **nullclaw** | mechanical | `recipes/nullclaw.yaml:468` — 1 sh-default substitution in heredoc |
| **picoclaw** | mechanical | `recipes/picoclaw.yaml:105 + :213` — 2 sh-default substitutions in heredocs |
| **openclaw** | mechanical | `recipes/openclaw.yaml` — flag flip only; `tools/run_recipe.py::_build_via_proxy_overrides` already injects `ANTHROPIC_BASE_URL` |
| **zeroclaw** | inspection | base_url written by `zeroclaw onboard --provider openrouter` — not in YAML; needs CLI/source inspection to find the modification surface |
| **hermes** | inspection | hermes CLI / config — `process_env.base_url: null` means hermes defaults internally; needs CLI/source inspection for the override path |

Plus two dependency plans:
- **30-00 (proxy enhancement)** — extends `StreamUsageParser._scan_openai` + `_parse_openai_compat` + `ParsedUsage` to read OpenRouter's inline `usage.cost` field and persist it as `usage_logs.cost_usd` (D-09). Source-of-truth simplification + Phase B markup vehicle, NOT an active-bug fix (CONTEXT's empirical evidence shows current cost_weights computation matches `/v1/generation` to the cent when `ap_multiplier=1.0` and `cache_read` is captured).
- **30-01 (anthropic SSE spike)** — real-money <$0.01 PROBE-VAL through real Anthropic to validate the proxy's `sse_format='anthropic'` branch end-to-end (Phase 29 only has synthetic SSE coverage for it).

Plus regression-guard evolution per-flip and one final cutover-verification plan (30-07).

**Primary recommendation:** Plans 30-00 and 30-01 ship before any recipe flip. Then mechanical flips (30-02 openclaw → 30-03 nullclaw → 30-04 picoclaw) ship in any order with their own e2e smokes. Then inspection flips (30-05 zeroclaw → 30-06 hermes), each with its own Wave-0 inspection task that resolves the modification surface. Then 30-07 verifies all 6 recipes are on the proxy, with regression guard rewritten to `test_all_recipes_have_via_proxy_true`.

## User Constraints (from CONTEXT.md)

### Locked Decisions

> Copied from `30-CONTEXT.md`. The planner MUST honor every D-XX item exactly.

- **D-01 Scope** — 5 recipe flips (hermes, openclaw, zeroclaw, nullclaw, picoclaw). Phase 29 deferred items (transient unknown-row dedup, mobile bot_timeout chip) NOT in scope.
- **D-02 picoclaw included** — config.json `api_base` baked via the same sh-heredoc pattern nanobot uses. No runner extension needed.
- **D-03 Sequencing** — openclaw flips first (anthropic-shape — fail-fast on the proxy's only un-tested provider path). Then 4 openrouter recipes: nullclaw → picoclaw → zeroclaw → hermes.
- **D-04 PROBE-VAL-ANTHROPIC spike** — Plan 30-01 is dedicated. Real-money streaming `POST /v1/messages` to anthropic/claude-haiku-4.5 through proxy. Asserts: usage_logs row `status='success'`, AMD-07 cumulative-tokens last-wins, `cost_usd > 0` from cost_weights. <$0.01.
- **D-05 (REVISED 2026-05-06)** — No real-money pre-flip spikes for openrouter recipes. nullclaw + picoclaw are mechanical heredoc edits identical to nanobot. hermes + zeroclaw need local CLI/config inspection (no real upstream traffic). Per-recipe e2e smoke AFTER flip is the validation gate (real-money but cheap, ~$0.01 each).
- **D-06 Order within openrouter group** — nullclaw → picoclaw → zeroclaw → hermes. Mechanical first; inspection last.
- **D-07 (REVISED)** — Single Phase 30, ~7 plans: 30-00 (proxy enhancement), 30-01 (anthropic spike), 30-02 (openclaw), 30-03 (nullclaw), 30-04 (picoclaw), 30-05 (zeroclaw), 30-06 (hermes), 30-07 (verification). Atomic per-recipe rollback via `git revert <plan-tail>`.
- **D-08 Regression guard** — updates per-flip. Each plan's TDD update edits `test_only_nanobot_has_via_proxy` to add the flipped recipe. Plan 30-07 finalizes by replacing it with `test_all_recipes_have_via_proxy_true` asserting all 6.
- **D-09 Plan 30-00 reads OpenRouter inline `cost`** — `StreamUsageParser._scan_openai` (`stream_parser.py:163-170`) + `_parse_openai_compat` (`usage_recorder.py:138-166`) extract `usage.cost`; `ParsedUsage` extends with optional `inline_cost_usd`; `routes/llm_proxy.py::_record_usage_from_parsed:161` prefers it when not None, falls back to existing cost_weights lookup. Plan 29-07 backfill activity stays as defense-in-depth.
- **D-10 openclaw cost path = cost_weights only** — Anthropic exposes only token counts. cost_weights `anthropic/claude-haiku-4.5` row is REQUIRED before Plan 30-01 fires. **Verified present** in `<verification_evidence>` (CONTEXT.md). No schema extension in Phase 30 (cost_weights is already 4-class with cache_read + cache_creation + ap_multiplier).
- **D-11 OpenRouter `user: <id>` body field** — Phase B prerequisite. NOT scope.
- **D-12 BYOK cache pre-warming** — trust Phase 29 custody flow (line 348 + line 498). No explicit pre-warm step per recipe.

### Claude's Discretion

- Spike implementation pattern (script under `tools/` vs `api_server/tests/spikes/`) — match Phase 29 PATTERNS.md convention. **Recommendation:** put 30-01's spike under `api_server/tests/spikes/test_phase30_01_anthropic_proxy_real.py` (pytest module, `pytest.mark.spike + pytest.mark.api_integration`) — same shape as Phase 29's `test_phase29_*` spikes.
- ParsedUsage field naming for inline cost — **recommendation:** `inline_cost_usd: float | None` (matches CONTEXT's hint; `provider_cost_usd` is also acceptable but `inline_` makes the "comes from response body, not lookup" semantic explicit).
- Smoke test invocation per recipe — match nanobot's existing pattern from Plan 29-09 (the orchestrator-driven `make e2e-inapp-docker` flow that produced the `e6040d7` PASS row).
- Plan 30-07 verification doc shape — mirror `29-VERIFICATION.md`.

### Deferred Ideas (OUT OF SCOPE)

- Transient `status='unknown'` row dedup (inapp_dispatcher's parallel write path).
- Mobile `bot_timeout` chip rendering (Phase 29 Gate 5 deferral).
- cost_weights schema extension — already 4-class (verified live).
- OpenRouter `user: <id>` field pass-through (Phase B prerequisite).
- Plan 29-07 backfill retirement (vestigial after D-09; keep as defense-in-depth).
- `--workers 1` cap removal (Phase 29 follow-up — multi-worker needs Redis or PG LISTEN/NOTIFY).
- cost_weights row population for `google/gemini-2.5-flash` — **Verified non-blocking:** hermes lists this model under `known_incompatible_cells[]` (`hermes.yaml:151-167`), NOT in `verified_cells[]`. The hermes smoke (`prompt: "who are you?"`) runs against the first verified_cell (`anthropic/claude-haiku-4.5` — present in cost_weights), so Plan 30-06 does not need to populate gemini before flip.

## Phase Requirements

> No `phase_req_ids` declared. The phase goal IS the verification target: **all 6 recipes have `runtime.via_proxy: true` AND each recipe's e2e smoke writes a `usage_logs` row with `status='success'`, `total_tokens > 0`, `cost_usd > 0`**. The 5 acceptance gates from this RESEARCH (one per flipped recipe + 2 cross-cutting) drive the phase exit. Plan 30-07 finalizes.

## Project Constraints (from CLAUDE.md)

- **Golden Rule #1 — No mocks/no stubs.** Every per-recipe smoke runs against real OpenRouter (or real Anthropic for openclaw + 30-01). The 30-01 spike asserts `usage_logs` row from a REAL Anthropic call, not a synthetic SSE. The 30-00 proxy enhancement is exercised in 30-02..30-06 against real upstream cost responses, not unit-test fixtures.
- **Golden Rule #2 — Dumb client.** No client touches recipes/usage_logs directly. The mobile usage screen continues reading via `routes/usage.py`. Phase 30 only touches recipes (which the api_server reads server-side) + proxy (server-only) + tests.
- **Golden Rule #3 — Ship when stack works locally end-to-end.** macOS Docker Desktop bridge gotcha applies (CONTEXT canonical_refs §"CLAUDE.md"). Every per-recipe smoke MUST run via `make e2e-inapp-docker`, not native uvicorn. The proxy's IP-map (`request.client.host` → `agent_containers.bridge_ip`) only resolves on the bridge network.
- **Golden Rule #4 — Root cause first.** D-09 IS a root-cause fix (proxy never read inline cost — masked by 29-07's post-hoc backfill). Honors the rule.
- **Golden Rule #5 — Spike gray areas BEFORE planning.** The 4 user-driven verification rounds (CONTEXT 30-DISCUSSION-LOG) collapsed the spike surface from 5 recipes (incorrect framing) to 1 (anthropic e2e). Plans 30-05 (zeroclaw) and 30-06 (hermes) carry inspection-only Wave 0 tasks (no real-money traffic — local `--help` + source read). Plan 30-01's <$0.01 anthropic spike is the only real-money pre-flip work.
- **`feedback_dont_probe_what_prod_proves`** (CONTEXT memory pointer) — recipes already work in production (`verified_cells[]` PASS in every recipe). Phase 30 modifications change ONLY where the recipe writes the base_url; the underlying HTTP-call mechanism is unchanged. No real-money probes needed for that.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| YAML substitution (5 recipes) | Recipe layer | — | Recipes own their config-file/CLI shape; api_server reads them via `recipes_loader.py` |
| Inline `cost` extraction (D-09) | api_server / proxy | — | `services/stream_parser.py` + `services/usage_recorder.py` are the SSE/JSON parser surface; cost persistence is the proxy's `routes/llm_proxy.py:161-187` write site |
| Proxy dispatch (provider URL + auth shape) | api_server / `services/proxy_dispatcher.py` | — | already covers all 3 providers; no extension needed |
| Env injection on `via_proxy=true` | runner (`tools/run_recipe.py`) + api_server (`services/proxy_dispatcher.py::ENV_TO_PROVIDER`) | — | already covers all 3 api_key vars; no extension needed |
| BYOK custody (validate + encrypt + persist + cache) | api_server / `routes/agent_lifecycle.py:348` | `services/proxy_byok_cache.py` | mechanically gated on `via_proxy_flag`; D-12 trust |
| Placeholder swap (real key → `ap-proxy-<token>`) | api_server / `services/inapp_substitutions.py` | — | already gated on `via_proxy=True` (AMD-12 from Phase 29); no per-recipe work |
| Cost persistence (cost_weights or inline) | api_server / `routes/llm_proxy.py::_record_usage_from_parsed` | — | the new D-09 branch lands here; cost_weights fallback unchanged |
| Per-recipe e2e validation | test infra / `make e2e-inapp-docker` | — | dockerized harness joins the bridge network — only path that works on macOS |
| Cross-recipe regression guard | test layer / `tests/recipes/test_nanobot_via_proxy.py` | — | per-flip update; final rewrite in 30-07 |

## Standard Stack (no additions for Phase 30)

The Phase 30 stack is exactly Phase 29's stack. No new libraries, no new schema, no new endpoints. The 30-00 enhancement extends 3 existing files with a small (<50 LOC total) inline-cost field; 30-01 spike adds 1 pytest module under `api_server/tests/spikes/`.

| File | Phase 30 change | Why touched |
|---|---|---|
| `api_server/src/api_server/services/stream_parser.py` | extend `_scan_openai` (line 163-170) to read `event.usage.cost` (last-wins like tokens); add `_inline_cost_usd: float \| None` instance state | streaming path for OpenRouter |
| `api_server/src/api_server/services/usage_recorder.py` | extend `ParsedUsage` (line 63-78) with `inline_cost_usd: float \| None`; extend `_parse_openai_compat` (line 138-166) to read top-level `response.usage.cost` for non-streaming | non-streaming path; nanobot's stream=False path lands here |
| `api_server/src/api_server/routes/llm_proxy.py` | extend `_record_usage_from_parsed` (line 156-188) — `if parsed.inline_cost_usd is not None: cost_usd = Decimal(str(parsed.inline_cost_usd)); else: <existing cost_weights computation>` | the cost_usd write site |
| `recipes/nullclaw.yaml` | line 468 — single substitution | mechanical |
| `recipes/picoclaw.yaml` | lines 105 + 213 — two substitutions | mechanical |
| `recipes/openclaw.yaml` | one-line `via_proxy: true` add to `runtime:` | flag flip only |
| `recipes/hermes.yaml` | TBD — Plan 30-06 Wave 0 inspection task | flag flip + invoke.argv or runtime.process_env edit |
| `recipes/zeroclaw.yaml` | TBD — Plan 30-05 Wave 0 inspection task | flag flip + onboard CLI flag or pre_start_command edit |
| `api_server/tests/recipes/test_nanobot_via_proxy.py` | per-flip add new recipe to the asserted set; 30-07 rewrites to `test_all_recipes_have_via_proxy_true` | regression guard evolution |
| `api_server/tests/spikes/test_phase30_01_anthropic_proxy_real.py` (NEW) | <$0.01 real-money spike | Plan 30-01 |

**No `make` target additions.** Per-recipe smoke runs through `make e2e-inapp-docker` driving an existing test harness with the recipe-name parameterized.

## Architecture Patterns

### Per-recipe modification matrix (load-bearing — read this section before planning)

| Recipe | Provider | Where base_url lives today | Phase 30 edit | Plan |
|---|---|---|---|---|
| **openclaw** | anthropic | Anthropic SDK reads `ANTHROPIC_BASE_URL` env var (documented since SDK launch). `tools/run_recipe.py::_build_via_proxy_overrides` already injects `ANTHROPIC_BASE_URL` for `ANTHROPIC_API_KEY` recipes. | `runtime.via_proxy: true` ONLY — mechanical YAML add. No heredoc edit, no invoke.argv edit. | 30-02 |
| **nullclaw** | openrouter | `recipes/nullclaw.yaml:468` config heredoc hardcodes `"base_url":"https://openrouter.ai/api/v1"` (in the `models.providers.openrouter.base_url` JSON path). | Replace literal with `"${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"` — identical pattern to nanobot lines 252 + 463. | 30-03 |
| **picoclaw** | openrouter | TWO heredoc occurrences: line 105 (one-shot smoke `invoke.spec.argv`'s config.json `model_list[0].api_base`) and line 213 (`persistent.spec.argv`'s config.json `model_list[0].api_base`). | Replace BOTH literals with `"${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"`. nanobot already proves heredoc-eval works on alpine `/bin/sh`. | 30-04 |
| **zeroclaw** | openrouter | `process_env.base_url: null` (line 39). Base URL is set by `zeroclaw onboard --provider openrouter` (line 95-100 invoke + lines 202-220 persistent.pre_start_commands). The `onboard` CLI command writes to `/zeroclaw-data/.zeroclaw/config.toml`. The exact field name + override mechanism is a Wave-0 inspection task. | Likely options (resolved by inspection): (a) `zeroclaw config set <field> $AP_PROXY_BASE_URL` as a 5th `pre_start_command`; OR (b) extend `zeroclaw onboard` argv with a `--api-base` flag if one exists; OR (c) write `config.toml` directly via a sh-heredoc step (but distroless image has no shell — fall back to `zeroclaw config set`). | 30-05 |
| **hermes** | openrouter | `process_env.base_url: null` (line 37). hermes defaults internally to `https://openrouter.ai/api/v1` per `hermes_cli/runtime_provider.py:463-469`. Override path is unknown — needs CLI inspection. The recipe's `invoke.spec.argv` includes `--provider openrouter` (line 89-92) but no `--base-url` flag is documented. | Likely options (resolved by inspection): (a) `--base-url` flag on `hermes chat` if it exists; (b) `OPENAI_BASE_URL` env var (since hermes has `api_key_fallback: OPENAI_API_KEY` and openrouter is OpenAI-compatible — IF hermes_cli reads `OPENAI_BASE_URL`); (c) hermes config file field — the recipe already uses `/opt/data/.env` as the config path (warnings.no_touch_env_file says env override=true overrides process env). Inspection likely finds `OPENROUTER_BASE_URL` env or a config-file knob. | 30-06 |

### Plan ordering rationale

CONTEXT D-03 + D-06 lock the ordering: 30-00 → 30-01 → 30-02 (openclaw) → 30-03 (nullclaw) → 30-04 (picoclaw) → 30-05 (zeroclaw) → 30-06 (hermes) → 30-07 (verification).

| Position | Plan | Why this slot |
|---|---|---|
| 1 | 30-00 | Must merge before any e2e smoke that asserts `cost_usd > 0` from the inline-cost path. The openclaw smoke (30-02) does NOT depend on 30-00 (anthropic doesn't return cost — uses cost_weights anyway), but the openrouter smokes (30-03/04/05/06) all need 30-00 to land first OR the cost_usd assertion will only pass via cost_weights (still acceptable but D-09's value is unrealized). **Recommendation: merge 30-00 BEFORE 30-03 starts.** |
| 2 | 30-01 | Pre-flight for 30-02. The anthropic SSE parser is exercised end-to-end through real Anthropic for the first time. A spike failure here gates the entire openclaw flip. |
| 3 | 30-02 (openclaw) | Fail-fast on the anthropic provider path. If 30-01 PASSED, 30-02 is mechanical (one-line YAML). |
| 4 | 30-03 (nullclaw) | Smallest mechanical edit (one heredoc substitution). Fastest path to ship + smoke. |
| 5 | 30-04 (picoclaw) | Two heredoc substitutions. Also mechanical. |
| 6 | 30-05 (zeroclaw) | Inspection burden begins. Distroless image (no shell) constrains the modification surface. |
| 7 | 30-06 (hermes) | Largest image (5.2 GB), longest cold-start. CLI inspection task. Last per ascending-complexity. |
| 8 | 30-07 | Cross-recipe regression-guard rewrite + 6/6 verification. |

**Hard dependency:** 30-00 MUST merge before any of 30-03..30-06 ship (otherwise inline-cost path is dead code in those plans' smokes). 30-01 MUST PASS before 30-02 ships (gate on anthropic path). All other ordering is preference.

**Soft dependency (regression guard):** D-08 mandates per-flip update. After 30-02 ships, the regression guard becomes "openclaw + nanobot have via_proxy:true; nullclaw/picoclaw/zeroclaw/hermes don't yet." This update is a TDD task INSIDE each per-flip plan — not a separate task.

### D-09 implementation shape (Plan 30-00 surface)

```python
# api_server/src/api_server/services/usage_recorder.py — ParsedUsage extension
@dataclass(frozen=True)
class ParsedUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    upstream_request_id: str | None = None
    stop_reason: str | None = None
    status: str = "success"
    inline_cost_usd: float | None = None  # NEW — D-09. None means "not present;
                                          # fall back to cost_weights computation."

# api_server/src/api_server/services/usage_recorder.py::_parse_openai_compat
# — extend after the cache_creation parse (line 156)
inline_cost = usage.get("cost")
inline_cost_usd = float(inline_cost) if inline_cost is not None else None
return ParsedUsage(
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    cache_read_tokens=cache_read,
    cache_creation_tokens=cache_creation,
    upstream_request_id=_str_or_none(response.get("id")),
    stop_reason=_str_or_none(_first_choice_finish_reason(response)),
    status="success" if (input_tokens or output_tokens) else "unknown",
    inline_cost_usd=inline_cost_usd,
)

# api_server/src/api_server/services/stream_parser.py::_scan_openai
# — extend with last-wins on cost (mirrors the existing usage last-wins)
def _scan_openai(self, event: dict[str, Any]) -> None:
    usage = event.get("usage")
    if isinstance(usage, dict):
        self._final_usage = usage  # last-wins (existing)
    rid = event.get("id")
    if rid:
        self._upstream_request_id = str(rid)
    # NOTE: cost ships INSIDE usage per OpenRouter docs; the
    # ParsedUsage construction in finalize() reads usage["cost"]
    # directly — no separate scan field needed.

# api_server/src/api_server/services/stream_parser.py::finalize
# — in the openai branch (line 238-262), after the existing extraction:
inline_cost = usage.get("cost")
inline_cost_usd = float(inline_cost) if inline_cost is not None else None
return ParsedUsage(
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    cache_read_tokens=cache_read,
    cache_creation_tokens=cache_creation,
    upstream_request_id=self._upstream_request_id,
    status="success" if self._was_complete else "failed",
    inline_cost_usd=inline_cost_usd,
)

# api_server/src/api_server/routes/llm_proxy.py::_record_usage_from_parsed
# — replace cost_usd computation block (line 161-187) with:
cost_usd = Decimal("0")
if parsed.status == "success" and parsed.inline_cost_usd is not None:
    # D-09 — OpenRouter inline cost is the canonical USD
    cost_usd = Decimal(str(parsed.inline_cost_usd))
elif parsed.status == "success" and (parsed.input_tokens or parsed.output_tokens):
    # cost_weights fallback (anthropic + any provider that doesn't return inline cost)
    weights = await conn.fetchrow(...)  # existing query
    if weights is not None:
        # ... existing cost_weights computation ...
        cost_usd = raw * mult
```

[VERIFIED: OpenRouter docs] `usage.cost` ships in the last SSE chunk for streams and at top-level `response.usage.cost` for non-streaming, per `https://openrouter.ai/docs/guides/administration/usage-accounting`. `usage:{include:true}` and `stream_options:{include_usage:true}` are deprecated/no-op — full usage details ship automatically.

[VERIFIED: live deploy-postgres-1 query, CONTEXT verification_evidence] `usage_logs.cost_usd numeric(14,8)` accepts the inline value. No schema change needed.

[VERIFIED: code read of `_scan_openai` lines 163-170] The existing parser captures `usage` last-wins but never inspects `usage.cost`. D-09 adds that read.

### Plan 30-01 spike shape (anthropic SSE end-to-end)

```python
# api_server/tests/spikes/test_phase30_01_anthropic_proxy_real.py
"""PROBE-VAL-ANTHROPIC — real-money <$0.01 spike validating the proxy's
sse_format='anthropic' branch end-to-end through real Anthropic.

Phase 29 unit tests (test_stream_parser.py + test_llm_proxy.py) cover
synthetic anthropic SSE events. This spike sends a real streaming
POST /v1/messages call through the proxy to claude-haiku-4.5, asserts:

  (a) usage_logs row inserted with status='success', input_tokens > 0,
      output_tokens > 0, cost_usd > 0
  (b) AMD-07 cumulative-tokens last-wins applied correctly — assert
      output_tokens equals the cumulative total from the last
      message_delta, NOT a per-event sum
  (c) cost_weights row for anthropic/claude-haiku-4.5 produced cost_usd
      (Anthropic does NOT return cost in responses)
  (d) BYOK custody flow ran — agent_containers row has
      upstream_provider='anthropic' and provider_key_enc IS NOT NULL
"""
import pytest

pytestmark = [pytest.mark.spike, pytest.mark.api_integration]

@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY_REAL"),
    reason="real-money spike — set ANTHROPIC_API_KEY_REAL to run",
)
async def test_proxy_sse_anthropic_real_e2e(...):
    # (1) cost_weights pre-check — abort early if missing
    row = await conn.fetchrow(
        "SELECT * FROM cost_weights WHERE provider='anthropic' "
        "AND model='anthropic/claude-haiku-4.5'"
    )
    assert row is not None, (
        "Plan 30-01 prerequisite — cost_weights row for "
        "anthropic/claude-haiku-4.5 must exist before spike runs"
    )

    # (2) seed a running agent_container with provider_key_enc
    # (use the proxy_byok_cache.set + agent_lifecycle BYOK pattern)
    # ...

    # (3) stream POST /v1/messages through the proxy
    async with proxy_client.stream(
        "POST",
        "http://api_server:8000/v1/llm/forward/v1/messages",
        json={
            "model": "claude-haiku-4-5",
            "max_tokens": 50,
            "stream": True,
            "messages": [{"role": "user", "content": "Reply with: ok-30-01"}],
        },
        headers={
            "Authorization": f"Bearer ap-proxy-{token}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    ) as resp:
        async for chunk in resp.aiter_raw():
            pass  # drain — proxy parses internally

    # (4) verify usage_logs row
    row = await conn.fetchrow(
        "SELECT * FROM usage_logs WHERE agent_instance_id=$1 "
        "ORDER BY created_at DESC LIMIT 1", agent_instance_id,
    )
    assert row["status"] == "success"
    assert row["input_tokens"] > 0
    assert row["output_tokens"] > 0
    assert row["cost_usd"] > 0
    assert row["provider"] == "anthropic"
    assert row["upstream_request_id"].startswith("msg_")  # Anthropic's id shape

    # (5) AMD-07 regression check — output_tokens is cumulative, not summed
    # If we ever regress to summing, claude-haiku-4.5's typical 17-token
    # reply would land as 5+12+17=34 instead of 17.
    assert row["output_tokens"] < 50, (
        "AMD-07 regression — output_tokens > expected indicates "
        "per-delta summing instead of cumulative last-wins"
    )
```

[VERIFIED: Anthropic streaming docs] Per `https://platform.claude.com/docs/en/api/messages-streaming`: "The token counts shown in the `usage` field of the `message_delta` event are *cumulative*." Event flow: `message_start` (carries final input/cache numbers + priming output_tokens=1) → content blocks → `message_delta` (one or more — each carries cumulative output_tokens) → `message_stop`. Phase 29's parser already implements last-wins correctly (`stream_parser.py:200-203`).

### Don't Hand-Roll

| Problem | Don't build | Use |
|---|---|---|
| New env-injection logic for via_proxy | per-recipe `runtime.process_env` extension | Existing `_build_via_proxy_overrides` covers all 3 api_key vars (verified closed-enum `tools/run_recipe.py:1029-1034`) |
| New BYOK cache pre-warm step | per-recipe explicit cache populate | Trust D-12 — Phase 29's custody flow at `routes/agent_lifecycle.py:348` is `if via_proxy_flag:` so every flip mechanically gets the cache write |
| New placeholder swap per recipe | per-recipe `inapp_substitutions` extension | AMD-12 — `build_activation_substitutions(via_proxy=via_proxy_flag)` already gates on the flag (`agent_lifecycle.py:498`) |
| New cost_weights row for openclaw | recipe-side computation | `anthropic/claude-haiku-4.5` row exists (CONTEXT verified) — Plan 30-01 Task 0 asserts presence; doesn't write |
| New regex for OpenRouter `cost` extraction | regex/string-search | JSON parse — `usage["cost"]` is a top-level field per OpenRouter docs |
| New SSE parser | byte-level regex matching | Phase 29's `StreamUsageParser` handles both shapes; D-09 extends 1 field |
| New `make` target for per-recipe smoke | `make smoke-hermes` etc. | Reuse `make e2e-inapp-docker` parameterized by recipe name |

## Common Pitfalls

### Pitfall 1: Inline cost overwrites cost_weights for non-OpenRouter providers
**What goes wrong:** D-09's branch `if parsed.inline_cost_usd is not None: cost_usd = Decimal(str(parsed.inline_cost_usd))` fires on any provider that returns `usage.cost`. If a non-OpenRouter provider ever decides to ship that field with a different semantic, cost_usd silently shifts.
**How to avoid:** Plan 30-00's branch should be conservative — `if provider == "openrouter" AND parsed.inline_cost_usd is not None`. Anthropic explicitly does NOT return cost (per OpenClaw docs + verified by reading `_parse_anthropic_native:218-235`); OpenAI direct does not return cost either; OpenRouter is the only one. Make the provider check explicit.
**Warning signs:** anthropic e2e (Plan 30-01) asserts `cost_usd > 0` from cost_weights; if it suddenly comes from inline_cost_usd, something on Anthropic's side changed.

### Pitfall 2: OpenRouter `cost` chunk arrives AFTER `[DONE]`
**What goes wrong:** RESEARCH for Phase 29 already documented this (Pitfall 2 from 29-RESEARCH): OpenRouter sometimes emits the usage chunk after `[DONE]`. Phase 29's parser handles this by NOT breaking on `[DONE]` (`stream_parser.py:142-147`). For D-09 the same logic applies — the cost field rides the same chunk as the cumulative usage block.
**How to avoid:** Don't introduce an early-exit on `[DONE]` in 30-00. The existing pattern is correct.
**Warning signs:** post-30-00, openrouter e2e smokes show `inline_cost_usd=None` while tokens are populated. Means the parser broke before the cost chunk arrived.

### Pitfall 3: cost_details.upstream_inference_cost is BYOK-only
**What goes wrong:** OpenRouter docs: `cost_details.upstream_inference_cost` only present on BYOK requests. AP IS BYOK so this should always be present, but if a Phase B platform-billed path ever lands, this field disappears for those rows. D-09 reads `usage.cost` (which IS always present) NOT `usage.cost_details.upstream_inference_cost` (BYOK-only). Stay on `usage.cost`.
**How to avoid:** D-09's spec is explicit — `usage.cost`. Don't expand to `cost_details.*` fields.
**Warning signs:** A recipe gains a non-BYOK path and inline_cost_usd suddenly goes None.

### Pitfall 4: zeroclaw's distroless image breaks heredoc patterns
**What goes wrong:** zeroclaw's image is distroless — no `/bin/sh`. The nanobot/picoclaw/nullclaw heredoc pattern doesn't apply. The recipe's persistent block already uses `pre_start_commands` (separate `docker run --entrypoint zeroclaw ...` invocations sharing a named volume) instead. Plan 30-05's edit lives in `pre_start_commands`, not a heredoc.
**How to avoid:** When inspecting zeroclaw, document whether `zeroclaw config set` accepts a `gateway.openrouter.base_url` (or similar field) and add a 5th pre_start_command. Do NOT try to add an sh-heredoc.
**Warning signs:** Plan 30-05 PLAN reaches for a heredoc — wrong pattern.

### Pitfall 5: hermes's `.env` file overrides process env
**What goes wrong:** Per `recipes/hermes.yaml:54-62` warning `no_touch_env_file`, `hermes_cli/env_loader.py:86-88` loads `$HERMES_HOME/.env` with `override=True`. Any value written there silently clobbers process env. If Plan 30-06 reaches for an `OPENAI_BASE_URL` env injection but the entrypoint then loads `.env` and rewrites it, the proxy URL is lost.
**How to avoid:** Plan 30-06's inspection step must check whether hermes_cli reads the base_url from process env or from `.env` (or both). If `.env` wins, the recipe must write the proxy URL into `.env` directly, not just inject as process env. Could also be a CLI flag — preferable since it bypasses the env-loader entirely.
**Warning signs:** Plan 30-06 ships, hermes e2e smoke fails with "connection to api.openai.com refused" or similar — the proxy URL got clobbered by .env reload.

### Pitfall 6: openclaw's anthropic plugin loader runs once at boot
**What goes wrong:** openclaw's `runtime.process_env.api_key=ANTHROPIC_API_KEY` (line 40) and the `tools/run_recipe.py::_build_via_proxy_overrides` injects `ANTHROPIC_BASE_URL=http://api_server:8000/v1/llm/forward` + a placeholder `ANTHROPIC_API_KEY=ap-proxy-<token>` (per `proxy_dispatcher.py::ENV_TO_PROVIDER` mapping). The Anthropic SDK reads `ANTHROPIC_BASE_URL` automatically — but openclaw's plugin loader may cache the resolved URL at boot. If the runner injects post-boot, it's too late.
**How to avoid:** Inject env at `docker run -e` time (before container start), NOT at exec time. Phase 29's runner already does this (`_build_via_proxy_overrides` returns env vars consumed by `docker run`). Verified by reading `tools/run_recipe.py:1038-1042`.
**Warning signs:** openclaw e2e smoke fails with "connection to api.anthropic.com refused" — the SDK didn't pick up the new base_url.

### Pitfall 7: Anthropic returns 400 on `OPENROUTER_API_KEY` placeholder for non-anthropic models
**What goes wrong:** D-09's "openclaw cost path = cost_weights only" assumes openclaw routes only through anthropic. The recipe explicitly has `provider_compat.deferred=[openrouter]` (line 624-625) — openrouter path is upstream-broken (known_quirks). Phase 30 only validates the anthropic path for openclaw. If a future plan re-enables openrouter for openclaw, the cost path would shift to inline.
**How to avoid:** Don't re-enable openclaw's openrouter path in Phase 30 (out of scope). Plan 30-02's smoke uses `anthropic/claude-haiku-4.5` per `verified_cells[0]`.
**Warning signs:** Plan 30-02 PLAN tries to test gpt-4o-mini through openclaw — wrong model for this recipe (known_incompatible_cells).

## Code Examples

### Mechanical heredoc substitution (nullclaw, picoclaw)

```yaml
# Before — recipes/nullclaw.yaml line ~468 (excerpt)
"models":{"providers":{"openrouter":{"api_key":"${OPENROUTER_API_KEY}","base_url":"https://openrouter.ai/api/v1"}}},

# After (Plan 30-03)
"models":{"providers":{"openrouter":{"api_key":"${OPENROUTER_API_KEY}","base_url":"${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"}}},
```

```yaml
# Before — recipes/picoclaw.yaml lines 105 + 213 (excerpt; 2 places)
{
  "model_list": [{
    "model_name": "openrouter-default",
    "model": "$MODEL",
    "api_key": "${OPENROUTER_API_KEY}",
    "api_base": "https://openrouter.ai/api/v1"
  }]
}

# After (Plan 30-04 — both occurrences)
{
  "model_list": [{
    "model_name": "openrouter-default",
    "model": "$MODEL",
    "api_key": "${OPENROUTER_API_KEY}",
    "api_base": "${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"
  }]
}
```

### One-line YAML add (openclaw)

```yaml
# Before — recipes/openclaw.yaml line ~33 (excerpt)
runtime:
  provider: anthropic
  process_env:
    api_key: ANTHROPIC_API_KEY
    ...

# After (Plan 30-02)
runtime:
  provider: anthropic
  via_proxy: true   # NEW
  process_env:
    api_key: ANTHROPIC_API_KEY
    ...
```

The `_build_via_proxy_overrides` dispatch (`tools/run_recipe.py:1007`) reads `runtime.process_env.api_key=ANTHROPIC_API_KEY` and injects `ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY=ap-proxy-<token>`. The Anthropic SDK reads `ANTHROPIC_BASE_URL` natively. No further recipe edits needed.

### Per-flip regression-guard update (per-plan TDD task)

```python
# api_server/tests/recipes/test_nanobot_via_proxy.py — line 55 evolution
# After Plan 30-02 (openclaw flipped):
_OTHER_RECIPES = ["hermes", "zeroclaw", "nullclaw", "picoclaw"]  # openclaw removed
# After Plan 30-03 (nullclaw flipped):
_OTHER_RECIPES = ["hermes", "zeroclaw", "picoclaw"]
# After Plan 30-04 (picoclaw flipped):
_OTHER_RECIPES = ["hermes", "zeroclaw"]
# After Plan 30-05 (zeroclaw flipped):
_OTHER_RECIPES = ["hermes"]
# After Plan 30-06 (hermes flipped):
_OTHER_RECIPES = []  # all flipped — test becomes empty parametrize, skipped

# Plan 30-07 — rewrite to positive assertion:
_ALL_RECIPES = ["nanobot", "openclaw", "nullclaw", "picoclaw", "zeroclaw", "hermes"]

@pytest.mark.parametrize("recipe_name", _ALL_RECIPES)
def test_all_recipes_have_via_proxy_true(recipe_name: str) -> None:
    """Phase 30 cutover invariant — every recipe routes through the proxy."""
    recipe = _load(recipe_name)
    runtime = recipe.get("runtime") or {}
    assert runtime.get("via_proxy") is True, (
        f"recipe {recipe_name!r} missing via_proxy: true after Phase 30"
    )

def test_all_six_recipes_flipped() -> None:
    """Combined assertion — exactly 6 recipes carry via_proxy: true."""
    flipped_count = sum(
        1 for path in RECIPES_DIR.glob("*.yaml")
        if "via_proxy: true" in path.read_text()
    )
    assert flipped_count == 6
```

## Runtime State Inventory

> Phase 30 is a YAML edit + small proxy enhancement. No rename, no schema migration, no env-var rename. The "runtime state inventory" categories collapse to:

| Category | Items found | Action required |
|---|---|---|
| Stored data | `cost_weights` table — required rows: `anthropic/claude-haiku-4.5` (openclaw — VERIFIED present in CONTEXT verification_evidence), `openai/gpt-4o-mini` (picoclaw + nullclaw — VERIFIED present), `anthropic/claude-haiku-4.5` (hermes smoke first verified_cell — VERIFIED present); `usage_logs` schema — VERIFIED 4-class cost columns present | none — verified live; no migration |
| Live service config | None — every recipe's config lives in git (the YAML); no n8n/Datadog/Tailscale equivalents | none |
| OS-registered state | None — recipes are read fresh by api_server on every deploy via `recipes_loader.py` (no Windows Task Scheduler / pm2 / launchd registration) | none |
| Secrets/env vars | `AP_PROXY_BASE_URL` (already canonical from Phase 29 AMD-09 — `tools/run_recipe.py:990`); `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL` (already injected by `_build_via_proxy_overrides`); `INAPP_AUTH_TOKEN` (already minted per-deploy by `routes/agent_lifecycle.py`) | none — every var is already in the canonical lifecycle |
| Build artifacts | None — recipes are not built into images. The recipe YAML is read at `/v1/agents/:id/start` time by api_server. **EXCEPTION:** the 3 modified Python files in 30-00 (`stream_parser.py`, `usage_recorder.py`, `routes/llm_proxy.py`) are inside the `api_server` Docker image. After 30-00 ships, the image must rebuild; existing `make e2e-inapp-docker` rebuilds api_server into the bridge container so this is automatic | rebuild api_server image as part of 30-00 PR (already automatic) |

**Live containers at cutover:** any `agent_containers WHERE container_status='running'` for a flipped recipe BEFORE the flip lands will have stale `via_proxy=False` env (no `ANTHROPIC_BASE_URL` etc.). Phase 29 D-19 wiped nanobot's stale containers. **Equivalent guidance for Phase 30:** each per-flip plan's smoke implicitly creates a fresh deploy; pre-existing dev containers for that recipe should be manually stopped before the smoke. **NOT a blocker** in dev (no production), but worth a TODO line in each plan's pre-conditions section.

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|---|---|---|---|---|
| Docker daemon (live) | Every per-recipe smoke (`make e2e-inapp-docker` joins the bridge) | Assumed available (Phase 29 confirmed) | Docker Desktop 24+ | none — required |
| `make e2e-inapp-docker` target | Per-recipe smoke | Verified used by Phase 29 (`feedback_uniform_transport_5_of_5` memory) | n/a | none — only macOS-supported path |
| OpenRouter API access (real-money) | 30-03/04/05/06 smokes | Available via existing dev BYOK key | n/a | none — golden rule #1 forbids mocks |
| Anthropic API access (real-money) | 30-01 spike + 30-02 smoke | Available via existing dev BYOK key | n/a | none |
| Phase 29's full proxy stack live | All Phase 30 plans | Verified shipped (PHASE-29-EXIT-GATE-PASSED at `e6040d7`) | n/a | rollback to Phase 29 if proxy regresses |
| `cost_weights` row for `anthropic/claude-haiku-4.5` | Plan 30-01 | VERIFIED present (CONTEXT verification_evidence) | n/a | populate from Anthropic public pricing if missing |
| `cost_weights` row for `openai/gpt-4o-mini` | Plan 30-04 (picoclaw smoke) | VERIFIED present | n/a | populate if missing |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|---|---|
| Framework | pytest 8.x + pytest-asyncio (api_server tests); shell harness via `make e2e-inapp-docker` (e2e) |
| Config file | `api_server/pyproject.toml` (pytest config); `Makefile` (e2e target) |
| Quick run command | `cd api_server && uv run pytest tests/recipes/test_nanobot_via_proxy.py -x` (regression guard) + `cd api_server && uv run pytest tests/services/test_stream_parser.py tests/services/test_usage_recorder.py -x` (30-00 unit tests) |
| Full suite command | `make e2e-inapp-docker` (per-recipe e2e) + `cd api_server && uv run pytest -x` (full unit + integration) |

### Phase Requirements → Test Map

| Req | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| 30-00 D-09 | `usage.cost` extracted from OpenRouter inline | unit | `pytest api_server/tests/services/test_stream_parser.py::test_d09_inline_cost_extracted -x` | ❌ Wave 0 (Plan 30-00 Task 1) |
| 30-00 D-09 | non-streaming `response.usage.cost` extracted | unit | `pytest api_server/tests/services/test_usage_recorder.py::test_d09_nonstreaming_inline_cost -x` | ❌ Wave 0 (Plan 30-00 Task 2) |
| 30-00 D-09 | `usage_logs.cost_usd` written from inline when present | integration | `pytest api_server/tests/routes/test_llm_proxy.py::test_d09_inline_cost_persisted -x` | ❌ Wave 0 (Plan 30-00 Task 3) |
| 30-00 nanobot regression | nanobot e2e still PASS post-30-00; `cost_usd` now from inline path | e2e | `make e2e-inapp-docker RECIPE=nanobot` | ✅ existing (Phase 29 Plan 09) |
| 30-01 PROBE-VAL | Anthropic SSE through real proxy → `usage_logs` row | spike | `pytest api_server/tests/spikes/test_phase30_01_anthropic_proxy_real.py -x -m spike` | ❌ Wave 0 |
| 30-01 AMD-07 | cumulative-tokens last-wins (output_tokens NOT summed) | spike (assertion in same test) | (same) | ❌ Wave 0 |
| 30-02 openclaw e2e | openclaw via proxy → `usage_logs` row, `status='success'`, `cost_usd > 0` (cost_weights) | e2e | `make e2e-inapp-docker RECIPE=openclaw` | ✅ harness exists |
| 30-03 nullclaw e2e | nullclaw via proxy → row + cost (inline cost path) | e2e | `make e2e-inapp-docker RECIPE=nullclaw` | ✅ harness exists |
| 30-04 picoclaw e2e | picoclaw via proxy → row + cost (inline cost path) | e2e | `make e2e-inapp-docker RECIPE=picoclaw` | ✅ harness exists |
| 30-05 zeroclaw e2e | zeroclaw via proxy → row + cost (inline cost path) | e2e | `make e2e-inapp-docker RECIPE=zeroclaw` | ✅ harness exists |
| 30-06 hermes e2e | hermes via proxy → row + cost (inline cost path) | e2e | `make e2e-inapp-docker RECIPE=hermes` | ✅ harness exists |
| 30-07 6/6 invariant | all 6 recipes have `via_proxy: true` | unit | `pytest api_server/tests/recipes/test_nanobot_via_proxy.py -x` (renamed in 30-07) | ✅ existing (mutated to all-recipes assertion) |
| 30-07 BYOK custody | provider_key_enc populated for each recipe's deploy | integration (or shell query) | `psql -c "SELECT recipe_name, COUNT(*) FROM agent_containers WHERE provider_key_enc IS NOT NULL GROUP BY recipe_name"` | ✅ verifiable post-deploys |

### Sampling Rate
- **Per task commit:** 30-00 unit tests run on every commit (`pytest api_server/tests/services/test_*parser*.py test_*usage*.py -x`); each per-flip plan runs the targeted recipe e2e smoke.
- **Per wave merge:** `make e2e-inapp-docker RECIPE=<flipped>` for the just-flipped recipe + the regression guard test.
- **Phase gate (30-07):** 6/6 e2e smokes green + regression guard rewritten + invariant assertion green + manual `psql` verification of `provider_key_enc` rows.

### Wave 0 Gaps

- [ ] `api_server/tests/services/test_stream_parser.py` — extend with `test_d09_inline_cost_extracted` (Plan 30-00 Task 1 TDD) — REUSES existing test file
- [ ] `api_server/tests/services/test_usage_recorder.py` — extend with `test_d09_nonstreaming_inline_cost` (Plan 30-00 Task 2 TDD) — REUSES existing test file
- [ ] `api_server/tests/routes/test_llm_proxy.py` — extend with `test_d09_inline_cost_persisted` (Plan 30-00 Task 3 TDD) — REUSES existing test file
- [ ] `api_server/tests/spikes/test_phase30_01_anthropic_proxy_real.py` — NEW file (Plan 30-01)
- [ ] Per-flip TDD update to `api_server/tests/recipes/test_nanobot_via_proxy.py` (each of Plans 30-02..30-06)
- [ ] Plan 30-07: rewrite `test_only_nanobot_has_via_proxy` → `test_all_recipes_have_via_proxy_true`

*Framework install: not needed — pytest infrastructure already proven by Phase 29 + earlier phases.*

## Security Domain

> `security_enforcement` not explicitly set → treated as enabled per gsd-research convention.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | yes | `proxy_ip_map` + `ap-proxy-<token>` bearer (Phase 29) — UNCHANGED in Phase 30 |
| V3 Session Management | no | the proxy is server-to-server (api_server ↔ recipe container), no user session at this layer |
| V4 Access Control | yes | BYOK custody key never exposed to bot env (Phase 29 AMD-12 — UNCHANGED) |
| V5 Input Validation | yes | proxy validates body shape before forwarding upstream (Phase 29 D-14 — UNCHANGED) |
| V6 Cryptography | yes | age_cipher for `provider_key_enc` at rest (Phase 22+ — UNCHANGED) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| BYOK key leak in logs (Phase 29 Gate 6 risk) | Information Disclosure | `_redact_creds` discipline (`routes/agent_lifecycle.py:114-136` — UNCHANGED) — every per-recipe smoke MUST `grep` for `sk-or-v1-*`/`sk-ant-api03-*`/`sk-proj-*` patterns post-flow (Phase 29 Gate 6 procedure). Plan 30-07 verification doc must include this grep |
| Inline cost field tampering by upstream | Tampering | `usage.cost` is read from the response body — if upstream lies, AP records the lie. Mitigation: D-09 only reads `cost`, NOT `cost_details.upstream_inference_cost` (which is a different semantic). cost_weights remains as a defense-in-depth fallback for non-success rows |
| Spike spends real money in CI | Repudiation / Cost | Plan 30-01 spike marker `pytest.mark.spike` excludes from default CI run. Real-money invocation requires explicit `ANTHROPIC_API_KEY_REAL` env var. Plan 30-01 must include the budget assertion: `pytest -m spike` only runs when explicitly requested |

**Phase 30 introduces NO new security surface.** Every Phase 30 change rides Phase 29's already-audited surfaces. The new D-09 inline-cost branch is a single read of a JSON field that's already part of the response body the proxy currently reads.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 30-00 inline-cost path breaks nanobot regression (Phase 29 Gate 1) | LOW | HIGH | 30-00 Task 4 = re-run nanobot e2e smoke through `make e2e-inapp-docker`; assert `cost_usd > 0` AND `inline_cost_usd` populated. Halt phase if regress. |
| 30-01 spike fails (anthropic SSE has unexpected shape) | LOW | HIGH | Spike is the gate for 30-02. Failure means Phase 29's anthropic parser has a real-traffic bug Phase 29's synthetic tests missed. Resolution requires hotfix to `stream_parser.py::_scan_anthropic` BEFORE 30-02 ships. |
| zeroclaw inspection finds no clean override path | MEDIUM | MEDIUM | Most likely fallback: `zeroclaw config set` accepts a base_url-equivalent field. Distroless image guarantees the modification surface is `zeroclaw config set` or the source-level `config.toml` write at `pre_start_commands` step. If neither works, defer zeroclaw to a follow-up phase and ship 4/6 in Phase 30. |
| hermes inspection finds no clean override path | MEDIUM | MEDIUM | Most likely fallback: `OPENAI_BASE_URL` env (since hermes has `api_key_fallback: OPENAI_API_KEY` and `_build_via_proxy_overrides` already sets `OPENAI_BASE_URL` for `OPENROUTER_API_KEY` recipes). If hermes_cli ignores `OPENAI_BASE_URL`, fall back to writing the override into `/opt/data/.env` (warnings.no_touch_env_file says env override=true overrides process env — so writing INTO the file may work). If neither, defer hermes. |
| Per-recipe hotfix tail (mirroring Phase 29's 6 hotfixes) | HIGH | LOW | Phase 29 needed 6 hotfixes after main plans shipped (`7a04177→e6040d7`). Same shape expected for Phase 30 — each recipe may surface 0-2 small fixes (config-format quirk, env-var ordering, JSON-key edge case). Plan 30-07 explicitly leaves room in its budget for this. **Don't mark a per-flip plan COMPLETE until its e2e smoke is green AND the regression guard updates merged.** |
| OpenRouter changes the inline `cost` field shape | LOW | HIGH | OpenRouter's docs (verified 2026-05-06) explicitly state `usage.cost` is current; deprecation of `usage:{include:true}` shipped already (per docs). Mitigation: D-09's read is defensive (`if cost is not None`); cost_weights remains as fallback. |
| `ap_multiplier=1.0` invariant breaks during Phase B prep | LOW | MEDIUM | CONTEXT verification confirmed cost_weights produces exact match when `ap_multiplier=1.0`. Phase B raises this per row. Phase 30 explicitly does NOT touch ap_multiplier. |

## State of the Art

| Old approach | New approach | When changed | Impact |
|---|---|---|---|
| OpenRouter `usage:{include:true}` request body field | `usage` shipped automatically; field is no-op | per OpenRouter docs (current 2026-05-06) | D-09 doesn't need to inject this field — verify Phase 29's body-mutation path (`routes/llm_proxy.py`) doesn't add it (still safe — no-op upstream) |
| Anthropic `message_delta.usage.output_tokens` summed across deltas | last-wins (cumulative) | langchain-js #10249 / agno-agi #6537 fixed similar bugs Q4 2025 | Phase 29 already implements last-wins (`stream_parser.py:200-203`) — no Phase 30 change |

**Deprecated/outdated:**
- Phase 29's RESEARCH.md framing of "openrouter `user: <id>` body field needed for cost attribution" — that's a Phase B requirement (D-11), not a Phase 30 one. AP today uses BYOK so attribution flows through the BYOK key.
- Earlier framing in this phase's first discussion round: "5 pre-flip real-money spikes for openrouter recipes" — wrong; collapsed to "0 pre-flip openrouter spikes + 1 anthropic spike" by user push-back (CONTEXT 30-DISCUSSION-LOG "Reframe Round").

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | `make e2e-inapp-docker` accepts a `RECIPE=<name>` parameter (or has an equivalent recipe-selection mechanism) | Validation Architecture | If not, plans need to define how each recipe smoke is targeted. Phase 29 Plan 09's nanobot smoke is the working precedent — verify by reading the harness before locking. **Recommend Plan 30-02's Wave 0 confirms this** (it's the first Phase 30 e2e smoke). [ASSUMED — unverified in this research session] |
| A2 | hermes accepts a `--base-url` CLI flag OR honors `OPENAI_BASE_URL` env | Per-recipe modification matrix; Pitfall 5 | If neither, Plan 30-06 must write into `/opt/data/.env` directly; warnings.no_touch_env_file becomes the workaround surface. Plan 30-06 Wave 0 inspection task resolves this. [ASSUMED — empirical resolution by inspection] |
| A3 | zeroclaw's `zeroclaw config set` CLI accepts a base-url-equivalent field (e.g. `models.openrouter.api_base` or similar) | Per-recipe modification matrix | If not, the modification surface shifts to direct `config.toml` mutation via `pre_start_commands` (zeroclaw has no shell, so this means a 5th `zeroclaw config set <field>` call OR a custom command). Plan 30-05 Wave 0 inspection resolves. [ASSUMED — empirical resolution by inspection] |
| A4 | Anthropic SDK reads `ANTHROPIC_BASE_URL` env var natively (no recipe-side override needed for openclaw) | Per-recipe modification matrix; Pitfall 6 | Anthropic SDK has documented this since launch (per Phase 29 RESEARCH and Phase 29's existing dispatch in `tools/run_recipe.py:998` mapping `ANTHROPIC_API_KEY → ANTHROPIC_BASE_URL`). High confidence. [VERIFIED via Phase 29 commit `e6040d7` shipping the same dispatch for nanobot's analog path] |
| A5 | OpenRouter's inline `cost` field is a JSON number (not a string) | D-09 implementation shape | If string, `float(inline_cost)` cast handles it. `Decimal(str(...))` in the proxy write site also handles either. Defensive. [ASSUMED — likely number per JSON convention] |
| A6 | Plan 30-01's anthropic spike spend is <$0.01 (50-token max_tokens, single round-trip) | Plan 30-01 spike shape | Anthropic claude-haiku-4-5 pricing (per cost_weights row): input ~$1/1M, output ~$5/1M. 50 input + 50 output = ~$0.0003. Well under $0.01. [VERIFIED via cost_weights values + back-of-envelope arithmetic] |
| A7 | Phase 29's hotfix tail of 6 fixes is representative; Phase 30 may surface 0-2 hotfixes per recipe | Risk register | Phase 29 was greenfield (new proxy + new dispatch + new BYOK custody). Phase 30 is YAML edits riding the proven surface. Lower complexity → lower hotfix count. [ASSUMED — historical extrapolation; Plan 30-07 timeline includes buffer] |

## Open Questions

1. **Does `make e2e-inapp-docker` accept a recipe-name parameter?** (A1) — Resolution: Plan 30-02's first task reads `Makefile` + `tests/lib/agent_harness.py` to identify the recipe-selection mechanism (probably an env var or argparse flag). If absent, Plan 30-02's Wave 0 adds it as a single-line task.

2. **Does hermes accept `--base-url` CLI flag?** (A2) — Resolution: Plan 30-06 Wave 0 task: `docker run --rm --entrypoint hermes ap-recipe-hermes:latest chat --help | grep -i 'base\|url\|provider'`. If yes, plan ships flag-based override. If no, falls back to `OPENAI_BASE_URL` env or `/opt/data/.env` write.

3. **Does `zeroclaw config set` accept a base-url-equivalent field?** (A3) — Resolution: Plan 30-05 Wave 0 task: `docker run --rm --entrypoint zeroclaw ghcr.io/zeroclaw-labs/zeroclaw:latest config --help` and `zeroclaw config set --help`. If a field like `models.openrouter.api_base` exists, plan adds 5th pre_start_command. If no, falls back to direct `.toml` write.

4. **Should Plan 30-00's `inline_cost_usd` branch be provider-gated to `openrouter` only?** — Pitfall 1 above. **Recommendation: YES.** The branch in `routes/llm_proxy.py` should be `if provider == "openrouter" and parsed.inline_cost_usd is not None`. This narrows the surface and prevents accidental cross-provider semantic drift. Plan 30-00 should include this gate in the spec.

5. **Should the regression guard be renamed to `test_phase30_via_proxy_invariant.py` after 30-07?** — Stylistic. The current file is `tests/recipes/test_nanobot_via_proxy.py` which becomes a misnomer once 6/6 are flipped. **Recommendation: rename in 30-07.** `test_phase30_via_proxy_invariant.py` matches the post-cutover semantics.

6. **Does the proxy enforce a per-provider cost-source contract?** — Plan 30-00 implicit requirement: a future audit phase should be able to query "for OpenRouter rows, did cost_usd come from inline or cost_weights?" Today there's no column for that distinction. **Recommendation:** add a single `cost_source` text column (`'inline' | 'cost_weights'`) in a follow-up phase (NOT 30); track as deferred.

## Sources

### Primary (HIGH confidence)
- CONTEXT.md (`.planning/phases/30-recipe-proxy-cutover/30-CONTEXT.md`) — 12 D-XX + verification_evidence section verified live against `deploy-postgres-1` + code reads — 2026-05-06
- 30-DISCUSSION-LOG.md — 4-round verification including Reframe Round; documents the empirical reframe from "5 spikes" → "1 spike"
- `recipes/nanobot.yaml` (lines 252 + 463 — proven AMD-09 pattern; lines 40-50 — `via_proxy: true` reference)
- `recipes/nullclaw.yaml:468` (config heredoc base_url location)
- `recipes/picoclaw.yaml:105 + :213` (two heredoc base_url locations)
- `recipes/openclaw.yaml:33-50` (anthropic provider declaration)
- `recipes/hermes.yaml:34-50, :130-167` (process_env shape + smoke verified_cells; gemini gating)
- `recipes/zeroclaw.yaml:34-95, :196-227` (process_env + persistent.pre_start_commands shape)
- `api_server/src/api_server/services/stream_parser.py` (full file — 276 lines; D-09 modification site)
- `api_server/src/api_server/services/usage_recorder.py:138-166, :270-292, :63-78` (D-09 modification site + ParsedUsage shape + cost computation)
- `api_server/src/api_server/services/proxy_dispatcher.py` (full file — confirmed 3-provider closed enum)
- `api_server/src/api_server/routes/llm_proxy.py:120-242` (cost_usd write site)
- `tools/run_recipe.py:978-1042` (`_build_via_proxy_overrides` dispatch + closed-enum env-var maps)
- `api_server/tests/recipes/test_nanobot_via_proxy.py` (regression guard precedent — D-08 evolution target)
- `.planning/phases/29-llm-egress-proxy/29-VERIFICATION.md` (precedent gate structure + 6-hotfix tail shape)
- `.planning/phases/29-llm-egress-proxy/29-PATTERNS.md` (file analog conventions; spike location convention)
- `.planning/phases/29-llm-egress-proxy/29-RESEARCH.md` (precedent provider dispatch + AMD-07 cumulative-tokens last-wins)
- `git log 7a04177..e6040d7` — 5 hotfix commits with one-liner failure modes
- OpenRouter usage-accounting docs (`https://openrouter.ai/docs/guides/administration/usage-accounting`) — VERIFIED LIVE 2026-05-06
- Anthropic streaming docs (`https://platform.claude.com/docs/en/api/messages-streaming`) — VERIFIED LIVE 2026-05-06; explicit cumulative-warning quote at "## Event types"

### Secondary (MEDIUM confidence)
- CLAUDE.md (golden rules + macOS e2e-docker note) — project rules, used as constraint, not as fact source
- `memory/feedback_dont_probe_what_prod_proves.md` (Phase 30 reframe lesson — collapsed spike count)
- `memory/feedback_test_everything_before_planning.md` (golden rule #5 — applied to D-09 motivation walk-back)
- `.planning/STATE.md` (Phase 29 SHIPPED at PHASE-29-EXIT-GATE-PASSED — confirms prerequisite is in place)

### Tertiary (LOW confidence)
- (none — every claim in this research is either verified live or explicitly tagged ASSUMED in the Assumptions Log)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; every modified file is read in this session
- Architecture: HIGH — the 5 recipe surfaces are individually located + classified; openclaw + nullclaw + picoclaw are mechanically resolved; zeroclaw + hermes have explicit Wave-0 inspection tasks
- Pitfalls: HIGH — 7 pitfalls drawn from CONTEXT verification + Phase 29 hotfix history + OpenRouter/Anthropic docs
- D-09 implementation shape: HIGH — direct code reads of all 3 modification sites; OpenRouter inline-cost shape verified live
- Per-recipe inspection deliverables: MEDIUM — A2 (hermes) and A3 (zeroclaw) are genuine spike-time work; the recommended fallback paths are documented but not pre-validated

**Research date:** 2026-05-06

**Valid until:** 2026-06-05 (30 days — stack is stable; OpenRouter `usage.cost` field is documented current; Anthropic SSE shape is explicit in docs)

## RESEARCH COMPLETE
