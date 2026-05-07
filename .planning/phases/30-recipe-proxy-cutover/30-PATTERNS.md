# Phase 30: Recipe proxy cutover (5 recipes) — Pattern Map

**Mapped:** 2026-05-06
**Files analyzed:** 1 NEW + 12 MODIFIED = 13 total
**Analogs found:** 13 / 13

Phase 30 is **YAML edits + small proxy enhancement + per-recipe e2e validation**. No new architectural surface. Every modified file has a tight precedent — usually directly from Phase 29 — and the analog is always concrete. The "primary analog" for this whole phase is `recipes/nanobot.yaml` (the cutover template) plus `.planning/phases/29-llm-egress-proxy/29-PATTERNS.md` (the analog conventions all per-recipe plans inherit).

## File Classification

### NEW files

| New file | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `api_server/tests/spikes/test_phase30_01_anthropic_proxy_real.py` | test (PROBE-VAL-ANTHROPIC) | spike (real-money streaming + DB read-back) | `api_server/tests/spikes/test_phase29_probe_val_13_anthropic_sse.py` (real-money Anthropic streaming, `pytest.mark.spike`, artifact write to `.planning/.../spikes/PROBE-VAL-NN.md`) + `api_server/tests/e2e/test_phase29_acceptance.py` Gate 01 (live-deploy DB row read-back) | exact (combine the two) |

### MODIFIED files — proxy enhancement (Plan 30-00)

| Modified file | Role | Data Flow | Existing pattern to extend |
|---|---|---|---|
| `api_server/src/api_server/services/usage_recorder.py` | service (parser + DB write) | transform (dict → ParsedUsage) | extend `ParsedUsage` dataclass (line 63-78) with `inline_cost_usd: float \| None = None`; extend `_parse_openai_compat` (line 108-166) to read `usage.cost`; extend `_parse_anthropic_native` (line 183-235) — leave `inline_cost_usd=None` (Anthropic never returns cost; D-10) |
| `api_server/src/api_server/services/stream_parser.py` | service (byte-level SSE parser) | streaming transform | extend `_scan_openai` (line 163-170) — capture `usage.cost` last-wins (rides existing usage block); extend `finalize` openai branch (line 238-262) to write `inline_cost_usd` into ParsedUsage; extend `finalize` non-streaming JSON fallback (line 217-237) — `_parse_openai_compat` already handles it after recorder edit |
| `api_server/src/api_server/routes/llm_proxy.py` | route (proxy hot path) | streaming + DB write | extend `_record_usage_from_parsed` (line 123-225) — replace cost_usd computation block (line 161-187) with provider-gated `if provider == "openrouter" and parsed.inline_cost_usd is not None: cost_usd = Decimal(str(parsed.inline_cost_usd)); else: <existing cost_weights computation>` |

### MODIFIED files — recipe flips (Plans 30-02..30-06)

| Modified file | Role | Data Flow | Existing pattern to extend |
|---|---|---|---|
| `recipes/openclaw.yaml` | recipe (YAML) | config | one-line `via_proxy: true` add to `runtime:` block (line 33). Anthropic SDK reads `ANTHROPIC_BASE_URL` natively; `tools/run_recipe.py::_build_via_proxy_overrides` already injects it. NO heredoc edit. |
| `recipes/nullclaw.yaml` | recipe (YAML) | config | `runtime.via_proxy: true` add + 1 sh-default substitution at line 468 — replace `"base_url":"https://openrouter.ai/api/v1"` with `"base_url":"${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"`. Identical pattern to `recipes/nanobot.yaml:463`. |
| `recipes/picoclaw.yaml` | recipe (YAML) | config | `runtime.via_proxy: true` add + 2 sh-default substitutions at lines 105 + 213 — replace `"api_base":"https://openrouter.ai/api/v1"` with `"api_base":"${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"` in BOTH heredocs (one-shot + persistent.spec.argv). nanobot already proves alpine `/bin/sh` heredoc-eval works. |
| `recipes/zeroclaw.yaml` | recipe (YAML) | config | **inspection-required (Wave 0).** Distroless image — no `/bin/sh`. Plan 30-05 Wave 0 task: probe `zeroclaw config set --help` for a base-url-equivalent field. Likely add a 5th `pre_start_command` invoking `zeroclaw config set ... ${AP_PROXY_BASE_URL}`; do NOT reach for an sh-heredoc (Pitfall 4). Then add `runtime.via_proxy: true`. |
| `recipes/hermes.yaml` | recipe (YAML) | config | **inspection-required (Wave 0).** `hermes_cli/runtime_provider.py:463-469` defaults to OpenRouter. Plan 30-06 Wave 0 task: probe `docker run --rm --entrypoint hermes ap-recipe-hermes:latest chat --help` for `--base-url`. Fallback order: (a) CLI flag → invoke.spec.argv; (b) `OPENAI_BASE_URL` env (already injected via `_build_via_proxy_overrides`); (c) write into `/opt/data/.env` directly (warning `no_touch_env_file` is the workaround surface — Pitfall 5). Then add `runtime.via_proxy: true`. |

### MODIFIED files — regression-guard evolution (across Plans 30-02..30-07)

| Modified file | Role | Data Flow | Existing pattern to extend |
|---|---|---|---|
| `api_server/tests/recipes/test_nanobot_via_proxy.py` | test (recipe invariant) | unit (YAML read) | per-flip TDD: shrink `_OTHER_RECIPES` list (line 55) by removing each flipped recipe's name; update `test_only_one_recipe_yaml_has_via_proxy_true` (line 69-79) count from `1` to `flipped_count_so_far`. Plan 30-07: rewrite as `test_all_recipes_have_via_proxy_true` (positive assertion across all 6) + rename file to `test_phase30_via_proxy_invariant.py` (RESEARCH Open Question 5 recommendation). |
| `api_server/tests/services/test_stream_parser.py` | test | unit (parser) | extend with `test_d09_inline_cost_extracted` — `_sse_chunk` helper (line 32-36) is reusable; copy structure of `test_openai_final_chunk_last_wins` (line 44-60); after the `parser.feed(...)` calls, assert `out.inline_cost_usd` is the float from the seeded `usage.cost` field |
| `api_server/tests/services/test_usage_recorder.py` | test | unit (parser) | extend with `test_d09_nonstreaming_inline_cost` — copy structure of `test_parse_openai_compat_openai_shape` (line 94+); add `usage.cost` to the seeded response dict; assert returned ParsedUsage has `inline_cost_usd` populated |
| `api_server/tests/routes/test_llm_proxy.py` | test | integration (route + DB) | extend with `test_d09_inline_cost_persisted` — copy structure of "Test 1 happy-path openrouter stream" (line 12-15); seed upstream SSE with a `usage.cost` field via respx; query `usage_logs.cost_usd` and assert it equals the seeded inline cost (NOT the cost_weights result) |

---

## Pattern Assignments

### `api_server/tests/spikes/test_phase30_01_anthropic_proxy_real.py` (NEW — Plan 30-01)

**Primary analog:** `api_server/tests/spikes/test_phase29_probe_val_13_anthropic_sse.py` (real-money Anthropic streaming + artifact write)
**Secondary analog:** `api_server/tests/e2e/test_phase29_acceptance.py::test_gate_01_*` (live-deploy DB row read-back via `usage_logs` SELECT)
**Convention:** name `test_phase30_<probe-id>_<short-name>.py` matches Phase 29's `test_phase29_probe_val_NN_*.py` shape (29-PATTERNS.md "Spike scripts").

**Pytest markers** (copy from `test_phase29_probe_val_13_anthropic_sse.py:35`):
```python
pytestmark = [pytest.mark.spike, pytest.mark.api_integration]
```

**Artifact path pattern** (copy from `test_phase29_probe_val_13_anthropic_sse.py:37-44`):
```python
ARTIFACT_DIR = (
    Path(__file__).resolve().parents[3]
    / ".planning"
    / "phases"
    / "30-recipe-proxy-cutover"
    / "spikes"
)
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-ANTHROPIC.md"
```

**Real-money skip-gate pattern** (copy from `test_phase29_probe_val_13_anthropic_sse.py:65-68`):
```python
def test_proxy_sse_anthropic_real_e2e() -> None:
    an_key = os.getenv("ANTHROPIC_API_KEY")
    if not an_key:
        pytest.skip("ANTHROPIC_API_KEY required (source .env first)")
```

**Cost_weights pre-check pattern** (D-10 — assert row exists BEFORE making upstream call; mirrors Plan 30-01 Task 0):
```python
# (1) cost_weights pre-check — abort early if missing
async with db_pool.acquire() as conn:
    row = await conn.fetchrow(
        "SELECT * FROM cost_weights WHERE provider='anthropic' "
        "AND model='anthropic/claude-haiku-4.5'"
    )
assert row is not None, (
    "Plan 30-01 prerequisite — cost_weights row for "
    "anthropic/claude-haiku-4.5 must exist before spike runs"
)
```

**Streaming POST pattern** (copy from `test_phase29_probe_val_13_anthropic_sse.py:92-133` — the `httpx.Client.stream` + `iter_lines` shape; ADAPT URL to proxy + auth header to placeholder):
```python
URL = "http://api_server:8000/v1/llm/forward/v1/messages"  # NOT direct anthropic
body = {
    "model": "claude-haiku-4-5",
    "max_tokens": 50,  # ~$0.0003 per A6
    "stream": True,
    "messages": [{"role": "user", "content": "Reply with: ok-30-01"}],
}
headers = {
    "Authorization": f"Bearer ap-proxy-{token}",  # placeholder, NOT real key
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json",
}
```

**AMD-07 cumulative-tokens regression assertion** (copy semantics from `test_phase29_probe_val_13_anthropic_sse.py:194-211 cumulative_evidence_*`):
```python
# AMD-07 regression check — output_tokens is cumulative, not summed.
# claude-haiku-4-5 typical 17-token reply lands as 17 (last-wins),
# NOT 5+12+17=34 (per-delta sum bug). max_tokens=50 caps the total.
assert row["output_tokens"] < 50, (
    "AMD-07 regression — output_tokens > expected indicates "
    "per-delta summing instead of cumulative last-wins"
)
```

**DB row read-back pattern** (copy from `test_phase29_acceptance.py::test_gate_01_*` — Plan 30-01 RESEARCH §"Plan 30-01 spike shape" lines 290-308):
```python
# (4) verify usage_logs row
row = await conn.fetchrow(
    "SELECT * FROM usage_logs WHERE agent_instance_id=$1 "
    "ORDER BY created_at DESC LIMIT 1", agent_instance_id,
)
assert row["status"] == "success"
assert row["input_tokens"] > 0
assert row["output_tokens"] > 0
assert row["cost_usd"] > 0  # from cost_weights (Anthropic doesn't return inline cost)
assert row["provider"] == "anthropic"
assert row["upstream_request_id"].startswith("msg_")  # Anthropic id shape
```

**Redaction pattern** (copy from `test_phase29_probe_val_13_anthropic_sse.py:49-52`):
```python
def _redact(text: str, key: str) -> str:
    if key:
        return text.replace(key, "<REDACTED>")
    return text
```

---

### `api_server/src/api_server/services/usage_recorder.py` (extend ParsedUsage + `_parse_openai_compat`)

**Primary analog:** the existing `ParsedUsage` dataclass (line 63-78) and `_parse_openai_compat` function (line 108-166) are themselves the analog — Phase 30 extends them in place.
**MSV mirror:** none needed (D-09 is AP-specific; OpenRouter's inline cost has no MSV precedent).

**ParsedUsage extension** (RESEARCH §D-09 implementation shape lines 152-178 — direct verbatim addition; field at end of dataclass to preserve frozen-by-position equality semantics):
```python
@dataclass(frozen=True)
class ParsedUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    upstream_request_id: str | None = None
    stop_reason: str | None = None
    status: str = "success"  # 'success' | 'unknown' | 'failed'
    inline_cost_usd: float | None = None  # NEW — D-09. None means "not present;
                                          # fall back to cost_weights computation."
```

**`_parse_openai_compat` extension** (RESEARCH §D-09 lines 165-178 — fold the read in BEFORE the return statement at line 158-166):
```python
# (existing extraction at lines 138-156 unchanged)
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
    inline_cost_usd=inline_cost_usd,  # NEW
)
```

**`_parse_anthropic_native` deliberate-no-op** (D-10 — Anthropic does not return cost; leave the function untouched. The default-None field surfaces correctly without any edit):
```python
# Verbatim — no edit. inline_cost_usd defaults to None per the dataclass default.
return ParsedUsage(
    input_tokens=_int_or_zero(usage.get("input_tokens")),
    ...,
    status="success",
)  # inline_cost_usd auto-defaults to None — D-10 cost_weights fallback fires
```

**Defensive cast pattern** — A5 ASSUMED says `cost` may ship as JSON number or string. The cast `float(inline_cost) if inline_cost is not None else None` handles both shapes; downstream `Decimal(str(inline_cost_usd))` in `routes/llm_proxy.py` re-coerces defensively.

---

### `api_server/src/api_server/services/stream_parser.py` (extend `_scan_openai` + `finalize`)

**Primary analog:** the existing `StreamUsageParser` class (line 63-275) is the analog — Phase 30 extends it in place.
**Phase 29 hotfix-tolerance:** the parser already handles non-streaming JSON fallback (line 217-237) by delegating to `_parse_openai_compat`; the recorder edit above means the fallback path AUTOMATICALLY surfaces inline cost. No edit needed in the JSON fallback branch.

**`_scan_openai` extension** (line 163-170 — RESEARCH §D-09 lines 180-191; the existing `_final_usage = usage` last-wins covers the cost field FOR FREE because cost ships INSIDE the same `usage` dict per OpenRouter docs):
```python
def _scan_openai(self, event: dict[str, Any]) -> None:
    """OpenAI / OpenRouter event extraction. Last-wins on usage."""
    usage = event.get("usage")
    if isinstance(usage, dict):
        self._final_usage = usage  # last-wins (existing — covers cost FOR FREE)
    rid = event.get("id")
    if rid:
        self._upstream_request_id = str(rid)
    # NOTE: cost ships INSIDE usage per OpenRouter docs; no separate
    # scan field needed. The finalize() openai branch reads it.
```

**`finalize` openai-streaming branch extension** (line 238-262 — RESEARCH §D-09 lines 195-205; fold inline_cost extraction in BEFORE the ParsedUsage return):
```python
if self._sse_format == "openai":
    usage = self._final_usage
    if usage is None:
        return ParsedUsage(
            upstream_request_id=self._upstream_request_id,
            status="failed",
        )
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    if cache_read == 0:
        details = usage.get("prompt_tokens_details") or {}
        if isinstance(details, dict):
            cache_read = int(details.get("cached_tokens") or 0)
    cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
    # NEW — D-09 inline cost extraction
    inline_cost = usage.get("cost")
    inline_cost_usd = float(inline_cost) if inline_cost is not None else None
    return ParsedUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        upstream_request_id=self._upstream_request_id,
        status="success" if self._was_complete else "failed",
        inline_cost_usd=inline_cost_usd,  # NEW
    )
```

**`finalize` anthropic-streaming branch — deliberate no-op** (D-10 — Anthropic SSE never carries inline cost; default None applies):
```python
# Anthropic branch (line 263-271) — verbatim, NO edit. inline_cost_usd
# auto-defaults to None per the dataclass default.
```

**Pitfall coverage** (Pitfall 2 from RESEARCH — post-DONE-edge): the existing `_was_complete` sentinel + non-break behavior at `[DONE]` (line 142-147) already handles the case where OpenRouter emits the cost-bearing usage chunk AFTER `[DONE]`. No new handling required.

---

### `api_server/src/api_server/routes/llm_proxy.py` (provider-gated cost branch)

**Primary analog:** the existing `_record_usage_from_parsed` function (line 123-241) — Phase 30 modifies the cost computation block (line 161-187) only.
**Pitfall coverage:** Pitfall 1 from RESEARCH (cross-provider cost-field tampering) is mitigated by gating the inline-cost branch on `provider == "openrouter"`. Open Question 4 in RESEARCH confirms this gate is the right call.

**Provider-gated cost-source dispatch** (RESEARCH §D-09 lines 207-219 — replaces line 161-187):
```python
# Cost: D-09 inline path takes precedence for OpenRouter; cost_weights
# fallback for everyone else (including Anthropic per D-10, OpenAI direct,
# and OpenRouter when inline_cost_usd is unexpectedly None).
cost_usd = Decimal("0")
if parsed.status == "success":
    if provider == "openrouter" and parsed.inline_cost_usd is not None:
        # D-09 — OpenRouter inline cost is the canonical USD
        cost_usd = Decimal(str(parsed.inline_cost_usd))
    elif parsed.input_tokens or parsed.output_tokens:
        # cost_weights fallback (anthropic + any provider that doesn't
        # return inline cost; openrouter when inline missing)
        weights = await conn.fetchrow(
            """
            SELECT input_per_1m_usd, output_per_1m_usd,
                   cache_read_per_1m_usd, cache_creation_per_1m_usd,
                   ap_multiplier
            FROM cost_weights
            WHERE provider = $1 AND model = $2
            """,
            provider, model,
        )
        if weights is not None:
            in_rate = weights["input_per_1m_usd"] or Decimal("0")
            out_rate = weights["output_per_1m_usd"] or Decimal("0")
            cr_rate = weights["cache_read_per_1m_usd"] or Decimal("0")
            cc_rate = weights["cache_creation_per_1m_usd"] or Decimal("0")
            mult = weights["ap_multiplier"] or Decimal("1")
            raw = (
                Decimal(parsed.input_tokens) * in_rate
                + Decimal(parsed.output_tokens) * out_rate
                + Decimal(parsed.cache_read_tokens) * cr_rate
                + Decimal(parsed.cache_creation_tokens) * cc_rate
            ) / Decimal("1000000")
            cost_usd = raw * mult
```

**Plan 29-07 backfill activity remains unchanged** — D-09 docs (deferred section): the post-hoc `/api/v1/generation` backfill stays as defense-in-depth. The activity unconditionally overwrites `usage_logs.cost_usd` when `/generation` returns 200, which means the inline value lands first then the post-hoc value lands ~1-3s later. Per AMD-08 they're empirically equivalent; the overwrite is harmless.

---

### `recipes/openclaw.yaml` (one-line YAML add)

**Primary analog:** `recipes/nanobot.yaml:40-50` (the canonical `runtime: + via_proxy: true` block).

**Edit pattern** (RESEARCH §"One-line YAML add" lines 396-413):
```yaml
# Before — recipes/openclaw.yaml line 33
runtime:
  provider: anthropic
  process_env:
    api_key: ANTHROPIC_API_KEY
    ...

# After (Plan 30-02)
runtime:
  provider: anthropic
  via_proxy: true   # NEW — Phase 30 D-03 — anthropic-shape cutover
  process_env:
    api_key: ANTHROPIC_API_KEY
    ...
```

**Why no heredoc edit:** the Anthropic SDK reads `ANTHROPIC_BASE_URL` natively (verified: A4 in RESEARCH Assumptions Log; documented since Anthropic SDK launch). `tools/run_recipe.py::_build_via_proxy_overrides` (line 1007-1042) already injects `ANTHROPIC_BASE_URL=http://api_server:8000/v1/llm/forward` for any recipe with `process_env.api_key=ANTHROPIC_API_KEY` AND `via_proxy=true`. The YAML flip is mechanically all that's needed.

**Pitfall coverage** (Pitfall 6 — anthropic plugin loader cache): `_build_via_proxy_overrides` returns env vars consumed by `docker run -e` (verified `tools/run_recipe.py:1038-1042`), NOT exec-time injection. Pre-boot env injection guarantees the SDK reads the correct `ANTHROPIC_BASE_URL` before any plugin loader caches it.

---

### `recipes/nullclaw.yaml` (1 sh-default substitution)

**Primary analog:** `recipes/nanobot.yaml:463` — verbatim same pattern, different file/line.

**Edit pattern** (RESEARCH §"Mechanical heredoc substitution" lines 364-372):
```yaml
# Before — recipes/nullclaw.yaml line 468 (excerpt from persistent_argv_override JSON heredoc)
"models":{"providers":{"openrouter":{"api_key":"${OPENROUTER_API_KEY}","base_url":"https://openrouter.ai/api/v1"}}},

# After (Plan 30-03)
"models":{"providers":{"openrouter":{"api_key":"${OPENROUTER_API_KEY}","base_url":"${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"}}},
```

**Plus** the `runtime:` block gets a `via_proxy: true` line — same pattern as openclaw above.

**sh-default substitution rationale** (`recipes/nanobot.yaml:46-49` comment block):
- `${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}` is sh-evaluated at container start
- When `via_proxy=true`: runner injects `AP_PROXY_BASE_URL` → expands to proxy URL
- When `via_proxy=false`: env var is absent → expands to upstream URL (legacy path preserved)
- Heredoc EOF must be UNQUOTED (not `'EOF'`) for sh expansion to fire — `recipes/picoclaw.yaml:124-126` documents this gotcha verbatim

---

### `recipes/picoclaw.yaml` (2 sh-default substitutions)

**Primary analog:** `recipes/nanobot.yaml:252 + :463` — TWO heredoc occurrences (one-shot smoke + persistent.spec.argv) is exactly nanobot's pattern.

**Edit pattern** (RESEARCH §"Mechanical heredoc substitution" lines 374-393):
```yaml
# Before — recipes/picoclaw.yaml line 105 (one-shot invoke) AND line 213 (persistent)
"model_list": [{
  "model_name": "openrouter-default",
  "model": "$MODEL",
  "api_key": "${OPENROUTER_API_KEY}",
  "api_base": "https://openrouter.ai/api/v1"
}]

# After (Plan 30-04 — both occurrences)
"model_list": [{
  "model_name": "openrouter-default",
  "model": "$MODEL",
  "api_key": "${OPENROUTER_API_KEY}",
  "api_base": "${AP_PROXY_BASE_URL:-https://openrouter.ai/api/v1}"
}]
```

**Plus** the `runtime:` block gets a `via_proxy: true` line.

**Validation invariant for the regression-guard test** (mirror `test_nanobot_via_proxy.py::test_nanobot_api_base_uses_proxy_url_default_form_in_both_heredocs`, line 129-146): assert exactly 2 occurrences of the substitution pattern in `picoclaw.yaml`, exactly 0 occurrences of the literal upstream URL. This becomes a per-recipe TDD task in Plan 30-04.

---

### `recipes/zeroclaw.yaml` (inspection-required — Plan 30-05 Wave 0)

**Primary analog:** none mechanically — distroless image breaks the heredoc pattern (Pitfall 4 from RESEARCH). The closest existing analog is `recipes/zeroclaw.yaml`'s own `pre_start_commands` shape (line 196-227) which uses separate `docker run --entrypoint zeroclaw <args>` invocations sharing a named volume.
**Inspection deliverable** (RESEARCH §Open Question 3): `docker run --rm --entrypoint zeroclaw ghcr.io/zeroclaw-labs/zeroclaw:latest config --help` + `zeroclaw config set --help`.

**Likely edit shape — Option A (preferred per RESEARCH):**
```yaml
runtime:
  provider: openrouter
  via_proxy: true   # NEW
  process_env:
    api_key: OPENROUTER_API_KEY
    ...

persistent:
  spec:
    pre_start_commands:
      - [zeroclaw, onboard, --quick, --force, --provider, openrouter, --api-key, "${OPENROUTER_API_KEY}", --model, "$MODEL"]
      - [zeroclaw, config, set, gateway.allow-public-bind, "true"]
      - [zeroclaw, config, set, gateway.require-pairing, "false"]
      # NEW — Phase 30 D-05 inspection deliverable: 5th pre_start_command
      # writes the proxy URL into config.toml. Field name TBD in Wave 0
      # (likely models.openrouter.api_base or gateway.upstream_base_url).
      - [zeroclaw, config, set, "<FIELD>", "${AP_PROXY_BASE_URL}"]
      - [...existing daemon start...]
```

**Likely edit shape — Option B (fallback if `config set` doesn't take a base-URL field):**
- Probe upstream zeroclaw source (`Cargo.toml + src/`) for the env var the OpenRouter client honors. Most Rust HTTP clients honor `OPENROUTER_BASE_URL` or `OPENAI_BASE_URL`. Both already injected by `_build_via_proxy_overrides`.

**Likely edit shape — Option C (last resort):**
- Custom `docker run --entrypoint sh -c` step with `awk`/`sed` to mutate `/zeroclaw-data/.zeroclaw/config.toml` after `onboard`. Not recommended; defer zeroclaw to a follow-up phase (Risk Register row 3).

**Plus regression-guard update** for whichever path is chosen.

---

### `recipes/hermes.yaml` (inspection-required — Plan 30-06 Wave 0)

**Primary analog:** the recipe's own `invoke.spec.argv` (line 84-98) — the inspection task is whether to add a CLI flag there OR an env var to `runtime.process_env`.
**Inspection deliverable** (RESEARCH §Open Question 2): `docker run --rm --entrypoint hermes ap-recipe-hermes:latest chat --help | grep -i 'base\|url\|provider'`.

**Likely edit shape — Option A (CLI flag, preferred per RESEARCH §Pitfall 5):**
```yaml
runtime:
  provider: openrouter
  via_proxy: true   # NEW
  process_env:
    api_key: OPENROUTER_API_KEY
    api_key_fallback: OPENAI_API_KEY
    ...

invoke:
  spec:
    argv:
      - chat
      - -q
      - $PROMPT
      - -Q
      - --provider
      - openrouter
      - -m
      - $MODEL
      - --base-url           # NEW — Plan 30-06 Wave 0 deliverable
      - "${AP_PROXY_BASE_URL}"  # NEW
      - --yolo
      - ...
```

**Likely edit shape — Option B (`OPENAI_BASE_URL` env honor — already injected):**
- If hermes_cli reads `OPENAI_BASE_URL` (since `api_key_fallback: OPENAI_API_KEY` and OpenRouter is OpenAI-compatible), the env-var path is already wired by `_build_via_proxy_overrides`. NO recipe edit beyond the `via_proxy: true` line.

**Likely edit shape — Option C (write into `/opt/data/.env` directly — last resort):**
- The `no_touch_env_file` warning (line 54-62) becomes the workaround surface. Add a `pre_start_command` that writes `OPENAI_BASE_URL=${AP_PROXY_BASE_URL}` into `.env` — `env_loader.py:86-88` will then load it with `override=True`. Pitfall 5: this approach is fragile because the entrypoint may rewrite `.env`. Probe behavior empirically before committing.

**Plus regression-guard update** for whichever path is chosen.

---

### `api_server/tests/recipes/test_nanobot_via_proxy.py` (per-flip evolution + final rewrite)

**Primary analog:** the existing file is itself the analog — Plans 30-02..30-06 incrementally shrink `_OTHER_RECIPES`, Plan 30-07 rewrites.

**Per-flip TDD pattern** (RESEARCH §"Per-flip regression-guard update" lines 419-451):
```python
# After Plan 30-02 (openclaw flipped):
_OTHER_RECIPES = ["hermes", "zeroclaw", "nullclaw", "picoclaw"]
# After Plan 30-03 (nullclaw flipped):
_OTHER_RECIPES = ["hermes", "zeroclaw", "picoclaw"]
# After Plan 30-04 (picoclaw flipped):
_OTHER_RECIPES = ["hermes", "zeroclaw"]
# After Plan 30-05 (zeroclaw flipped):
_OTHER_RECIPES = ["hermes"]
# After Plan 30-06 (hermes flipped):
_OTHER_RECIPES = []  # all flipped — test becomes empty parametrize, skipped
```

**Per-flip count update** (line 69-79 — `test_only_one_recipe_yaml_has_via_proxy_true`):
```python
# After Plan 30-02 (2 flipped):
expected_count = 2
# After Plan 30-03 (3 flipped):
expected_count = 3
# ... etc, ending at 6 in Plan 30-07
```

**Plan 30-07 rewrite** (RESEARCH §lines 432-451 — positive assertion + filename rename per Open Question 5):
```python
# api_server/tests/recipes/test_phase30_via_proxy_invariant.py
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

---

### `api_server/tests/services/test_stream_parser.py` (extend with D-09 test)

**Primary analog:** `test_openai_final_chunk_last_wins` (line 44-60) — extend with a sibling test asserting `inline_cost_usd` extraction.

**Test pattern** (D-09 unit gate per RESEARCH §"Wave 0 Gaps" line 519):
```python
def test_d09_inline_cost_extracted() -> None:
    """OpenRouter inline `cost` field surfaces as ParsedUsage.inline_cost_usd.

    OpenRouter ships `usage.cost` automatically in the last SSE chunk for
    streams (per docs verified 2026-05-06). Phase 30 Plan 30-00 reads it.
    """
    parser = StreamUsageParser(provider="openrouter", sse_format="openai")
    parser.feed(_sse_chunk({"id": "gen-x", "choices": [{"delta": {"content": "hi"}}]}))
    parser.feed(_sse_chunk({
        "id": "gen-x",
        "choices": [],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 17,
            "cost": 0.00039345,  # NEW — D-09 inline cost
        },
    }))
    parser.feed(_sse_chunk("[DONE]"))

    out = parser.finalize()
    assert out.input_tokens == 42
    assert out.output_tokens == 17
    assert out.inline_cost_usd == 0.00039345  # D-09 invariant
    assert out.status == "success"


def test_d09_no_inline_cost_leaves_field_none() -> None:
    """Backward compatibility: missing `cost` field → inline_cost_usd is None."""
    parser = StreamUsageParser(provider="openrouter", sse_format="openai")
    parser.feed(_sse_chunk({
        "id": "gen-y",
        "choices": [],
        "usage": {"prompt_tokens": 11, "completion_tokens": 22},
    }))
    parser.feed(_sse_chunk("[DONE]"))

    out = parser.finalize()
    assert out.inline_cost_usd is None  # falls back to cost_weights
```

---

### `api_server/tests/services/test_usage_recorder.py` (extend with D-09 non-streaming test)

**Primary analog:** `test_parse_openai_compat_openai_shape` (line 94+).

**Test pattern** (D-09 non-streaming gate per RESEARCH §"Wave 0 Gaps" line 519):
```python
def test_d09_nonstreaming_inline_cost() -> None:
    """Non-streaming `response.usage.cost` surfaces as ParsedUsage.inline_cost_usd."""
    response = {
        "id": "gen-abc-123",
        "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        "usage": {
            "prompt_tokens": 14,
            "completion_tokens": 7,
            "cost": 0.00012,  # NEW — D-09 inline cost
        },
    }
    out = usage_recorder._parse_openai_compat(response, provider="openrouter")
    assert out.input_tokens == 14
    assert out.output_tokens == 7
    assert out.inline_cost_usd == 0.00012
    assert out.status == "success"
```

---

### `api_server/tests/routes/test_llm_proxy.py` (extend with D-09 persistence test)

**Primary analog:** Test 1 (happy-path openrouter stream) at line 12-15 — copy structure, seed `usage.cost` in the SSE, query `usage_logs.cost_usd` and assert.

**Test pattern** (D-09 integration gate per RESEARCH §"Wave 0 Gaps" line 520):
```python
async def test_d09_inline_cost_persisted(...) -> None:
    """OpenRouter stream with usage.cost → usage_logs.cost_usd matches inline,
    NOT the cost_weights computation. Provider-gated (openrouter only)."""
    # ... (same setup as Test 1 — FakeBYOKCache, _seed_user_and_agent, respx route)

    # Seed canned upstream SSE with inline cost
    sse_body = (
        b'data: {"id":"gen-d09","choices":[{"delta":{"content":"hi"}}]}\n\n'
        b'data: {"id":"gen-d09","choices":[],"usage":{"prompt_tokens":100,'
        b'"completion_tokens":50,"cost":0.00042}}\n\n'
        b'data: [DONE]\n\n'
    )
    respx_route.mock(return_value=httpx.Response(200, content=sse_body, ...))

    # ... (proxy POST through async_client)

    # Verify usage_logs row uses inline_cost_usd, NOT cost_weights
    row = await conn.fetchrow(
        "SELECT cost_usd FROM usage_logs WHERE agent_instance_id = $1",
        agent_instance_id,
    )
    assert row["cost_usd"] == Decimal("0.00042000"), (
        "D-09 invariant — OpenRouter inline cost should land directly in "
        "usage_logs.cost_usd; cost_weights fallback should NOT fire when "
        "inline_cost_usd is present"
    )
```

---

## Shared Patterns

### Authentication

**Source:** `api_server/src/api_server/services/proxy_ip_map.py` (IP-based) + `routes/llm_proxy.py:97-110` (placeholder bearer-token match) — Phase 29 D-07 defense-in-depth.

**Apply to:** Phase 30 changes ride this surface unchanged. The 30-01 spike POSTs to the proxy with `Authorization: Bearer ap-proxy-<token>` — same shape Phase 29 verified.

### Error envelope

**Source:** `api_server/src/api_server/models/errors.py::make_error_envelope` (used by every route).

**Apply to:** No new routes in Phase 30 — pattern unchanged.

### BYOK redaction in logs

**Source:** `routes/agent_lifecycle.py:114-136 _redact_creds`; `_redact` helper in `tools/spike_*.py` and `test_phase29_probe_val_13_anthropic_sse.py:49-52`.

**Apply to:** `tests/spikes/test_phase30_01_anthropic_proxy_real.py` — copy the `_redact(text, key)` helper verbatim. Verified by Phase 29 acceptance gate #6.

### Real-money spike skip-gate

**Source:** `test_phase29_probe_val_13_anthropic_sse.py:65-68` (pytest.skip on missing env var) + `pytest.mark.spike` to exclude from default CI runs.

**Apply to:** `test_phase30_01_anthropic_proxy_real.py` (Plan 30-01) — `@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason=...)` plus `pytestmark = [pytest.mark.spike, pytest.mark.api_integration]`.

### Spike artifact write

**Source:** `test_phase29_probe_val_13_anthropic_sse.py:55-57 _write_artifact` + `ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-NN.md"`.

**Apply to:** `test_phase30_01_anthropic_proxy_real.py` — write to `.planning/phases/30-recipe-proxy-cutover/spikes/PROBE-VAL-ANTHROPIC.md`. Phase 30 directory needs creating; first plan to ship under `30-recipe-proxy-cutover/` does it.

### YAML edit invariant assertion

**Source:** `tests/recipes/test_nanobot_via_proxy.py::test_nanobot_api_base_uses_proxy_url_default_form_in_both_heredocs` (line 129-146).

**Apply to:** Each per-recipe TDD task asserts BOTH (a) the substitution pattern appears N times in the file (1 for nullclaw, 2 for picoclaw), AND (b) the literal upstream URL does NOT appear (defense-in-depth). Plus `runtime.via_proxy is True` + `RecipeSummary.via_proxy is True` end-to-end through `recipes_loader.to_summary` (line 113-121 of the existing test, copied per recipe).

### E2E harness invocation

**Source:** `api_server/Makefile::e2e-inapp-docker` (line 45-78) — dockerized harness that joins the docker default `bridge` network so `request.client.host` resolves to the recipe container's bridge IP. Required on macOS (CLAUDE.md "End-to-end tests on macOS").

**Apply to:** every per-recipe smoke (Plans 30-02..30-06). The harness already supports the 5 listed recipe names hardcoded at line 5+47 (`hermes nanobot openclaw nullclaw zeroclaw`). picoclaw is currently NOT in the matrix list — Plan 30-04 may need to extend the for-loop to include `picoclaw` if its image isn't already prebuilt by other targets. **Open Question A1 in RESEARCH:** Plan 30-02's first task verifies whether the harness has a recipe-name parameter or runs all 5; the existing test_inapp_5x5_matrix.py iterates the full matrix.

### Test infra (Postgres + Docker + asyncpg)

**Source:** `api_server/tests/conftest.py` + `api_server/tests/test_migration_011_phase28.py:77-80` (testcontainers `PostgresContainer("postgres:17-alpine")`).

**Apply to:** D-09 Plan 30-00 unit + integration tests + 30-01 spike's DB read-back. All use `pytestmark = pytest.mark.api_integration`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|

(none — every Phase 30 file has a tight precedent, either from Phase 29 or from the existing codebase. The 5 recipe inspection tasks (zeroclaw + hermes) carry empirical-resolution risk, but the substitution pattern itself is exhaustively documented.)

---

## Metadata

**Analog search scope:**
- `recipes/*.yaml` (5 cutover targets + nanobot template)
- `api_server/src/api_server/services/{stream_parser,usage_recorder,proxy_dispatcher}.py`
- `api_server/src/api_server/routes/llm_proxy.py`
- `api_server/tests/recipes/`, `api_server/tests/services/`, `api_server/tests/routes/`, `api_server/tests/spikes/`, `api_server/tests/e2e/`
- `tools/run_recipe.py:978-1042` (AMD-06 dispatch)
- `.planning/phases/29-llm-egress-proxy/29-PATTERNS.md` + `29-CONTEXT.md` + `29-08-PLAN.md` (precedent)
- `api_server/Makefile` (e2e-inapp-docker harness)

**Files scanned:** ~22 (focused reads of analog files only; targeted Reads with offset+limit for >500-line files).

**Pattern extraction date:** 2026-05-06

**Open issues for the planner:**

1. **`picoclaw` image not in `e2e-inapp-docker` matrix.** `api_server/Makefile:5+47` lists `hermes nanobot openclaw nullclaw zeroclaw` (5 recipes); `picoclaw` is NOT there. Plan 30-04 may need to extend the matrix to include picoclaw, OR document why picoclaw runs via a different e2e path (the existing `tests/e2e/test_inapp_5x5_matrix.py` likely needs a 6th cell). Resolve in Plan 30-04 Wave 0 task: read `test_inapp_5x5_matrix.py:60` to see whether the matrix is parametrized over 5 or 6 recipes.

2. **The existing regression-guard test file references `Phase 30` work.** `test_nanobot_via_proxy.py:54-55` says: `# All 6 recipe filenames in repo/recipes/. nanobot is the cutover; the # other 5 MUST stay on the legacy non-proxy path until Phase 30.` — the test was authored anticipating the per-flip evolution. Per-flip TDD modifications match the comment's intent.

3. **`test_phase29_acceptance.py::test_gate_07_legacy_recipes_still_work` (line 153+)** asserts `provider_key_enc IS NULL` for hermes/openclaw/zeroclaw/nullclaw. After Plans 30-02/05/06/03 ship, this gate INVERTS for each flipped recipe — the BYOK custody flow (Phase 29 D-12) populates the column. Plan 30-07 must update this gate (likely delete it, replace with a positive-assertion gate that all 6 recipes' deploys populate `provider_key_enc`). **Add this to Plan 30-07's regression-guard rewrite scope.**
