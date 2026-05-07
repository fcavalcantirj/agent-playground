---
phase: 30
plan: "00"
subsystem: api-server / proxy / cost-capture
tags:
  - cost-capture
  - openrouter
  - proxy
  - d-09
  - pitfall-1
  - tdd
dependency-graph:
  requires:
    - "Phase 29 (LLM egress proxy + StreamUsageParser + _record_usage_from_parsed)"
    - "cost_weights table (already populated for openrouter/openai/anthropic models)"
  provides:
    - "ParsedUsage.inline_cost_usd: float | None — OpenRouter response.usage.cost surface"
    - "Provider-gated inline-cost branch in _record_usage_from_parsed (openrouter only)"
  affects:
    - "Plans 30-03 / 30-04 / 30-05 / 30-06 (openrouter recipe smokes assert inline path)"
    - "Plan 29-07 backfill activity (now defense-in-depth; previously the only authoritative-cost path)"
    - "AppBar USD ticker + per-agent breakdown (cost_usd is unchanged shape; openrouter rows now sourced from canonical inline cost)"
tech-stack:
  added: []
  patterns:
    - "Provider-gated cost-source dispatch with structural-invariant grep gate (B-02)"
    - "Defensive cast for upstream-supplied numeric (float-then-Decimal-string for precision)"
    - "TDD with two-step RED→GREEN per task; commits separated"
key-files:
  created:
    - ".planning/phases/30-recipe-proxy-cutover/deferred-items.md"
    - ".planning/phases/30-recipe-proxy-cutover/cost-budget.txt"
  modified:
    - "api_server/src/api_server/services/usage_recorder.py"
    - "api_server/src/api_server/services/stream_parser.py"
    - "api_server/src/api_server/routes/llm_proxy.py"
    - "api_server/tests/services/test_stream_parser.py"
    - "api_server/tests/services/test_usage_recorder.py"
    - "api_server/tests/routes/test_llm_proxy.py"
    - "tools/Dockerfile.test-runner"
decisions:
  - "Extended ParsedUsage with `inline_cost_usd: float | None = None` at end of dataclass (preserves frozen-by-position equality)."
  - "Provider gate is literal `provider == \"openrouter\"` joined by `and` to `parsed.inline_cost_usd is not None` on the same `if`-branch (B-02 structural invariant; verified by grep + by Pitfall 1 exclusivity Test 4)."
  - "Defensive cast `float(inline_cost) if inline_cost is not None else None` handles JSON-number, JSON-string, missing shapes (RESEARCH A5)."
  - "Persistence uses `Decimal(str(parsed.inline_cost_usd))` to avoid float→Decimal precision loss (numeric(14,8) target column)."
  - "_parse_anthropic_native deliberately untouched — D-10: Anthropic schema has no `cost` field; default-None covers it."
  - "Plan 29-07 backfill activity remains as defense-in-depth; not retired in Plan 30-00."
metrics:
  duration_minutes: 12
  completed: "2026-05-07"
  tasks_completed: 3
  tests_added: 8
  source_files_modified: 3
  test_files_modified: 3
  infra_files_modified: 1
  commits: 5
---

# Phase 30 Plan 00: Proxy Reads OpenRouter Inline `usage.cost` Summary

OpenRouter response inline `usage.cost` (USD) now flows from upstream → `StreamUsageParser` / `_parse_openai_compat` → `ParsedUsage.inline_cost_usd` → provider-gated branch in `_record_usage_from_parsed` → `usage_logs.cost_usd` for `provider == "openrouter"` rows; cost_weights remains the fallback for anthropic, openai-direct, and openrouter-without-inline-cost rows.

## Objective Achieved

Plan 30-00 extended the proxy's usage-parser surface to capture OpenRouter's inline `cost` field and persist it directly as `usage_logs.cost_usd` for openrouter rows. The inline path is provider-gated (literal `provider == "openrouter"`) so non-openrouter providers — even hypothetical future schemas that ship `usage.cost` with different semantics — never silently shift AP's cost_usd. cost_weights remains the trusted source for non-openrouter rows AND the fallback for any openrouter row whose upstream response unexpectedly omits `usage.cost`. Backward compat is full: every existing call site sees `inline_cost_usd=None` until the upstream actually populates the field.

## Implementation

### Task 1 — ParsedUsage extension + parser unit tests (TDD)

| Step | What | Where | Commit |
|------|------|-------|--------|
| RED  | 4 failing tests | `tests/services/test_stream_parser.py`, `tests/services/test_usage_recorder.py` | `f351ddb` |
| GREEN| Field + extraction in 2 parsers | `services/usage_recorder.py`, `services/stream_parser.py` | `734562e` |

**ParsedUsage extension** (services/usage_recorder.py:79-86): Field added at end of dataclass with default `None`. Comment block documents D-09 + D-10 + Pitfall 1.

**`_parse_openai_compat`** (services/usage_recorder.py:168-182): Reads `usage.get("cost")` via defensive cast and threads `inline_cost_usd` into the ParsedUsage return.

**`finalize` openai-streaming branch** (services/stream_parser.py:255-271): Same defensive cast pattern; rides the existing `_final_usage` last-wins capture (which already covered `cost` for free since it ships inside the same usage dict).

**`_parse_anthropic_native` + finalize anthropic-streaming branch** — deliberately untouched per D-10. The dataclass default `None` covers them. Test 4 pins this invariant so a future reviewer can't accidentally add `usage.get("cost")` to the Anthropic path (which would be wrong — Anthropic returns no cost).

### Task 2 — Provider-gated cost branch in routes (TDD)

| Step | What | Where | Commit |
|------|------|-------|--------|
| RED  | 4 integration tests (1 actually RED, 3 pre-passing) | `tests/routes/test_llm_proxy.py` | `818bee2` |
| GREEN| Provider-gated dispatch | `routes/llm_proxy.py` | `292625b` |

**`_record_usage_from_parsed`** (routes/llm_proxy.py:158-203): The cost block now branches on `provider == "openrouter" and parsed.inline_cost_usd is not None`. When BOTH true: `cost_usd = Decimal(str(parsed.inline_cost_usd))`. When EITHER false: existing cost_weights computation runs (preserved unchanged).

**B-02 structural invariant verified by grep:**
```
174-                if (
175-                    provider == "openrouter"
176:                    and parsed.inline_cost_usd is not None
177-                ):
178-                    # D-09 inline path — OpenRouter's authoritative USD.
179-                    cost_usd = Decimal(str(parsed.inline_cost_usd))
```
The two predicates live on the SAME `if`-branch joined by `and`, NOT on separate branches that could both fire. `grep -n -B2 'parsed.inline_cost_usd is not None' | grep -q 'provider == "openrouter"'` confirms this.

### Task 3 — Regression gate (BLOCKED on pre-existing infra rot; alternative used)

| Step | What | Result | Commit |
|------|------|--------|--------|
| Pre-flight | Kill stale nanobot containers | clean | — |
| Run | `pytest -k nanobot` via dockerized harness | **BLOCKED** | — |
| Diagnose | Two pre-existing infra rots surfaced | docs + dockerfile fix | `3a3e6aa` |

**What blocked Task 3 verify**:
1. **Test-runner image lacked `temporalio`** — Phase 28 added the dep to `api_server/pyproject.toml` but `tools/Dockerfile.test-runner` was never updated. Fixed inline (Rule 3) — added `'temporalio>=1.27.0,<1.28'` to the dockerfile, rebuilt the image.
2. **`tests/e2e/_helpers.py:402` imports `_handle_row`** which Phase 28 commit `6feb361` deleted. The dockerized e2e harness has been broken at fixture-setup time since Phase 28 cutover (the visible symptom: `e2e-report.json` shows `recipes:[]` on every run because the report-accumulator never gets a cell to record). This is documented as **D-30-DEF-01** in `deferred-items.md` and routed to a Phase 28 follow-up.

**Alternative regression evidence** (used in lieu of the broken e2e harness):

| Test layer | File | Count | Result |
|---|---|---|---|
| Parser unit | `tests/services/test_stream_parser.py` | 17 (incl. 2 new D-09) | 17/17 PASS |
| Recorder unit | `tests/services/test_usage_recorder.py` | 21 (incl. 2 new D-09) | 21/21 PASS |
| Proxy route integration (real PG, respx) | `tests/routes/test_llm_proxy.py` | 15 (incl. 4 new D-09) | 15/15 PASS |
| Recipe YAML invariant | `tests/recipes/test_nanobot_via_proxy.py` | 11 | 11/11 PASS |
| **Total** | | **64** | **64/64 PASS** |

These exercise the exact code path Plan 30-00 modifies (`_record_usage_from_parsed`, both parsers, ParsedUsage) with real Postgres via testcontainers and respx-mocked OpenRouter SSE responses (per CLAUDE.md golden rule #1, no mocks for the substrate; respx mocks only the upstream HTTP boundary). Tests 3+4 in `test_llm_proxy.py` inject phantom `cost` fields on anthropic + openai-direct streams and assert cost_weights still wins — empirically proving the provider-gate is exclusive.

## Behavior Specification

### Inline cost present (provider=openrouter)

```python
# upstream SSE chunk
{"id":"gen-x","choices":[],"usage":{"prompt_tokens":100,"completion_tokens":50,"cost":0.00042}}

# ParsedUsage from parser
ParsedUsage(input_tokens=100, output_tokens=50, inline_cost_usd=0.00042, status="success", ...)

# usage_logs row
cost_usd = Decimal("0.00042000")  # D-09 inline path; cost_weights NOT consulted
```

### Inline cost absent (provider=openrouter)

```python
# upstream SSE chunk (no cost field)
{"id":"gen-y","choices":[],"usage":{"prompt_tokens":100,"completion_tokens":50}}

# ParsedUsage from parser
ParsedUsage(input_tokens=100, output_tokens=50, inline_cost_usd=None, status="success", ...)

# usage_logs row
# cost_weights for openrouter/openai/gpt-4o-mini: $0.15/$0.60 per 1M
cost_usd = Decimal("0.00004500")  # cost_weights fallback fires
```

### Provider != openrouter (anthropic / openai-direct)

Even if the upstream ever shipped a phantom `cost` field, the gate
`provider == "openrouter"` blocks the inline path — cost_weights is the
only source. Empirically proven by Test 3 (anthropic) + Test 4
(openai-direct).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Added `temporalio` to test-runner Dockerfile**
- **Found during:** Task 3 (running dockerized e2e harness)
- **Issue:** `tools/Dockerfile.test-runner` lacked `temporalio` dep that Phase 28 added to `api_server/pyproject.toml`. Every dockerized test run aborted with `ModuleNotFoundError: No module named 'temporalio'` during conftest fixture setup.
- **Fix:** Added `'temporalio>=1.27.0,<1.28'` (matching pyproject.toml pin) to the dev-deps install line in the dockerfile. Rebuilt image.
- **Files modified:** `tools/Dockerfile.test-runner`
- **Commit:** `3a3e6aa`
- **Why Rule 3:** Without this, NO dockerized test could run on this machine — full blocking.

**2. [Rule 3 — Test fixture bug] Fixed model-name mismatch in Test 3**
- **Found during:** Task 2 (running RED tests)
- **Issue:** `test_d09_anthropic_does_not_use_inline_path` initially sent `model: anthropic/claude-haiku-4-5` in the request body, but the cost_weights row is keyed `(provider='anthropic', model='claude-haiku-4-5')` (no `anthropic/` prefix; that prefix is the OpenRouter-canonical shape). Result: cost_weights miss → cost_usd=0 → assertion failure.
- **Fix:** Sent bare `claude-haiku-4-5` in the test body; comment explains the convention.
- **Files modified:** `api_server/tests/routes/test_llm_proxy.py`
- **Commit:** included in `818bee2` (RED commit, since test was edited before its first GREEN run)

### Deferred Issues (NOT auto-fixed — out of scope)

**1. [D-30-DEF-01] Pre-existing e2e harness rot — `_helpers.py` imports deleted `_handle_row`**
- **Discovered during:** Task 3 (running dockerized e2e harness)
- **Severity:** Blocks every `make e2e-inapp-docker` invocation
- **Root cause:** Phase 28 commit `6feb361` deleted
  `services/inapp_dispatcher::_handle_row` + `dispatcher_loop` (Temporal
  cutover, D-06), but `tests/e2e/_helpers.py:402` still imports it. The
  e2e harness has been broken since Phase 28 shipped; the visible symptom
  is `e2e-report.json` shows `recipes:[]` on every run.
- **Why deferred:** Pre-existing rot; SCOPE BOUNDARY says only auto-fix
  issues directly caused by current task. Fixing the helpers requires
  rewriting `drive_dispatcher_once` to drive the Temporal
  `DispatchMessageWorkflow` instead of the deleted `_handle_row` —
  significant work that belongs in a Phase 28 follow-up plan.
- **Logged at:** `.planning/phases/30-recipe-proxy-cutover/deferred-items.md`
- **Path forward:** Phase 28 follow-up updates `_helpers.drive_dispatcher_once`
  to either (a) start a real workflow against testcontainers Temporal,
  (b) call the dispatch activity directly, or (c) replace with an
  HTTP-layer smoke that POSTs `/v1/agents/:id/messages` and polls.

## Authentication Gates

None — Plan 30-00 is a code change with no auth surface and no upstream
real-money calls.

## Threat Surface Verified

T-30-00-01 (upstream tampering with `usage.cost`) — mitigated by the
literal `provider == "openrouter"` gate. Tests 3+4 (`test_d09_anthropic_
does_not_use_inline_path`, `test_d09_openai_direct_does_not_use_inline_
path`) inject phantom `cost: 9.99` on non-openrouter streams and assert
cost_weights still wins — empirical proof of provider-gate exclusivity
beyond a structural grep alone.

T-30-00-02 (OpenRouter itself lies in inline cost) — accepted; defense-
in-depth via Plan 29-07's `/api/v1/generation` post-hoc backfill activity
(unchanged by Plan 30-00; remains in `temporal/activities/backfill_
openrouter_cost.py`).

T-30-00-04 (parser crash on malformed cost) — defensive cast handles
JSON-number, JSON-string, missing shapes; Test 2 (`test_d09_no_inline_
cost_leaves_field_none`) covers the missing-field path.

## Self-Check: PASSED

**Files verified to exist (post-edit):**
- `FOUND: api_server/src/api_server/services/usage_recorder.py` (contains `inline_cost_usd: float | None = None`, `usage.get("cost")`)
- `FOUND: api_server/src/api_server/services/stream_parser.py` (contains `inline_cost_usd=inline_cost_usd`)
- `FOUND: api_server/src/api_server/routes/llm_proxy.py` (contains `provider == "openrouter"` AND `Decimal(str(parsed.inline_cost_usd))` AND `FROM cost_weights`)
- `FOUND: api_server/tests/services/test_stream_parser.py` (contains `test_d09_inline_cost_extracted`, `test_d09_no_inline_cost_leaves_field_none`)
- `FOUND: api_server/tests/services/test_usage_recorder.py` (contains `test_d09_nonstreaming_inline_cost`, `test_d09_anthropic_native_leaves_inline_cost_none`)
- `FOUND: api_server/tests/routes/test_llm_proxy.py` (contains `test_d09_inline_cost_persisted`, `test_d09_no_inline_falls_back_to_cost_weights`, `test_d09_anthropic_does_not_use_inline_path`, `test_d09_openai_direct_does_not_use_inline_path`)
- `FOUND: tools/Dockerfile.test-runner` (contains `'temporalio>=1.27.0,<1.28'`)
- `FOUND: .planning/phases/30-recipe-proxy-cutover/deferred-items.md`
- `FOUND: .planning/phases/30-recipe-proxy-cutover/cost-budget.txt`

**Commits verified:**
- `FOUND: f351ddb` — `test(30-00): add failing tests for D-09 inline cost extraction`
- `FOUND: 734562e` — `feat(30-00): extend ParsedUsage + parsers with inline_cost_usd (D-09)`
- `FOUND: 818bee2` — `test(30-00): add D-09 provider-gated integration tests`
- `FOUND: 292625b` — `feat(30-00): provider-gated inline cost branch (D-09 + Pitfall 1)`
- `FOUND: 3a3e6aa` — `chore(30-00): unblock dockerized test-runner; document deferred e2e rot`

**Acceptance criteria verified:**
- [x] ParsedUsage carries `inline_cost_usd: float | None = None` (grep PASS)
- [x] `_parse_openai_compat` reads `usage.get("cost")` (grep PASS)
- [x] `StreamUsageParser.finalize` openai-branch reads `usage.get("cost")` (grep PASS)
- [x] `_parse_anthropic_native` does NOT contain `usage.get("cost")` (grep PASS — 0 matches in that function)
- [x] Provider-gate structural invariant: `provider == "openrouter"` and `inline_cost_usd is not None` on the same `if`-branch joined by `and` (B-02 PASS)
- [x] `Decimal(str(parsed.inline_cost_usd))` appears exactly once (grep PASS — 1 match)
- [x] `FROM cost_weights` query block preserved (grep PASS — 1 match)
- [x] All 8 new tests PASS (4 unit + 4 integration)
- [x] All prior tests PASS (no regression — 56 prior tests still green; 64 total)
- [ ] nanobot e2e PASS via `make e2e-inapp-docker` — **DEFERRED** (D-30-DEF-01); regression evidence supplied via 64/64 unit + integration + recipe-invariant tests instead
