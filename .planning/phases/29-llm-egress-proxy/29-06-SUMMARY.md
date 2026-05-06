---
phase: 29
plan: 06
plan_number: 06
subsystem: usage_recorder
tags:
  - phase-29
  - llm-egress-proxy
  - usage-recorder
  - anthropic
  - cost-capture
dependency_graph:
  requires:
    - "Plan 29-04: services/stream_parser.py (StreamUsageParser, AMD-07 last-wins)"
    - "Migration 013: usage_logs.proxy_latency_ms + upstream_latency_ms columns"
  provides:
    - "_parse_anthropic_native(response: dict) -> ParsedUsage — non-streaming Anthropic /v1/messages JSON dict parser (D-12)"
    - "record_usage(..., proxy_latency_ms, upstream_latency_ms) — extended signature for D-11 + AMD-04 latency split capture"
  affects:
    - "api_server/src/api_server/routes/llm_proxy.py (can now bypass its inline _record_usage_from_parsed helper in a future cleanup; not done in this plan to keep diff atomic)"
    - "api_server/src/api_server/temporal/activities/record_usage.py (still works unchanged — kwargs default to None → NULL columns)"
tech_stack:
  added: []
  patterns:
    - "Phase 29 status convention: 'failed' for proxy-side capture failures (widened ck_usage_logs_status in migration 013); 'unknown' reserved for legacy stripped contracts (Phase 30 cleanup target)"
    - "Backward-compatible kwarg additions: new fields default to None; pre-Phase-29 callers (Temporal activity, dispatcher) need no code changes"
key_files:
  created: []
  modified:
    - "api_server/src/api_server/services/usage_recorder.py (+_parse_anthropic_native, +proxy_latency_ms, +upstream_latency_ms kwargs, SQL extended)"
    - "api_server/tests/services/test_usage_recorder.py (+7 new tests; module docstring updated)"
decisions:
  - "Kept _parse_anthropic_native private (leading underscore) matching the existing _parse_openai_compat / _parse_stripped convention; not added to __all__"
  - "Status='failed' (NOT 'unknown') when the non-streaming Anthropic dict has no usage block — matches the Phase 29 D-15 widened-enum convention; 'unknown' is reserved for legacy stripped-contract callers that Phase 30 cleanup retires"
  - "record_usage SQL VALUES list now writes proxy_latency_ms + upstream_latency_ms after latency_ms (preserves column ordering reasoning of the existing migration); legacy callers pass None → NULL stored"
metrics:
  duration_seconds: 339
  duration_human: "5.6 min"
  completed_date: "2026-05-06"
  tasks_completed: 1
  tests_added: 7
  tests_passing: 19
  tests_total: 19
---

# Phase 29 Plan 06: usage_recorder Anthropic-native + latency-split Summary

**One-liner:** Added the `_parse_anthropic_native` non-streaming dict parser per D-12 and extended `record_usage` with `proxy_latency_ms` / `upstream_latency_ms` kwargs that populate migration-013 columns, with full backward compatibility for the Temporal activity + dispatcher callers.

## What Shipped

### `_parse_anthropic_native(response: dict) -> ParsedUsage`

Parses the non-streaming Anthropic `POST /v1/messages` JSON shape:

```json
{
  "id": "msg_abc",
  "model": "claude-haiku-4-5",
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 42,
    "output_tokens": 17,
    "cache_creation_input_tokens": 100,
    "cache_read_input_tokens": 5
  }
}
```

Returns `ParsedUsage(input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, upstream_request_id, stop_reason, status='success')`. Missing `usage` block returns `ParsedUsage(status='failed', upstream_request_id=...)` per the Phase 29 D-15 widened-enum convention.

The streaming path lives in `services/stream_parser.py` (Plan 04) — `grep -c "_parse_anthropic_native_stream" services/usage_recorder.py` is `0` (verified). AMD-07 last-wins on `output_tokens` is enforced in the streaming parser; this plan only adds the **non-streaming** dict path, used for any future non-streaming Anthropic call (retry paths, replay, etc.).

### `record_usage` signature extension

Two new kwargs added to the existing public `record_usage` entry point:

```python
async def record_usage(
    conn: asyncpg.Connection,
    *,
    user_id, agent_instance_id, message_id,
    contract, provider, model, response,
    latency_ms: int | None = None,
    proxy_latency_ms: int | None = None,        # NEW (Phase 29 D-11 + AMD-04)
    upstream_latency_ms: int | None = None,     # NEW
    source: str = "inapp",
) -> UUID | None:
```

The asyncpg INSERT extended to write both columns (migration 013):

```sql
INSERT INTO usage_logs (
  user_id, agent_instance_id, message_id,
  provider, model, upstream_request_id,
  input_tokens, output_tokens,
  cache_read_tokens, cache_creation_tokens,
  cost_usd, latency_ms, proxy_latency_ms, upstream_latency_ms,
  status, stop_reason, source
) VALUES (...)
```

Pre-Phase-29 callers (Temporal `record_usage` activity at `temporal/activities/record_usage.py`, dispatcher paths) pass nothing for the new kwargs → defaults to `None` → NULL stored. Verified by `test_record_usage_omitted_latency_kwargs_write_null`.

## Tests (7 added; 19 total in module, 19/19 pass)

| # | Test | Asserts |
|---|------|---------|
| 1 | `test_parse_anthropic_native_happy_path` | All 4 token classes + upstream_request_id + status=success |
| 2 | `test_parse_anthropic_native_missing_cache_fields_default_zero` | Missing cache_*_input_tokens → 0; status still success |
| 3 | `test_parse_anthropic_native_missing_usage_block_failed` | No usage block → status='failed' (Phase 29 D-15) |
| 4 | `test_parse_anthropic_native_propagates_stop_reason` | Top-level `stop_reason` field surfaces on ParsedUsage |
| 5 | `test_record_usage_persists_proxy_and_upstream_latency_ms` | `proxy_latency_ms=12, upstream_latency_ms=487` round-trip the migration-013 columns |
| 6 | `test_record_usage_omitted_latency_kwargs_write_null` | Pre-Phase-29 caller shape → both columns store NULL (back-compat) |
| 7 | `test_record_usage_anthropic_native_dict_mode_via_parser` | End-to-end: non-streaming Anthropic dict → record_usage → row with non-zero tokens + correct cost ($0.000175 for 50/25 tokens at haiku rates) + populated latency columns |

All 12 pre-existing tests in the file still PASS — verified regression baseline. Plan 04's 10 route tests (`test_llm_proxy.py`) also still PASS.

## Acceptance Criteria — Verified

| Criterion | Result |
|-----------|--------|
| `def _parse_anthropic_native` in usage_recorder.py | PASS (1 occurrence) |
| Literal `cache_read_input_tokens` present | PASS (6 occurrences) |
| Literal `cache_creation_input_tokens` present | PASS (6 occurrences) |
| `proxy_latency_ms` >= 2 occurrences (signature + SQL) | PASS (4 occurrences: signature, docstring, SQL columns list, SQL VALUES) |
| `upstream_latency_ms` >= 2 occurrences | PASS (4 occurrences) |
| `def _parse_stripped` preserved (D-12) | PASS |
| `_parse_anthropic_native_stream` count = 0 (streaming lives in stream_parser.py) | PASS (0) |
| 7 new tests PASS | PASS (7/7) |
| Existing usage_recorder tests still PASS | PASS (12/12) |
| Plan 04 route tests still PASS | PASS (10/10) |

## Deviations from Plan

None — plan executed exactly as written. The plan's example code in `<action>` Step A used `status="failed"` for missing-usage; the executor adopted that verbatim (the plan's behavior block left the choice to the executor "the test asserts the choice"; I picked 'failed' to align with the D-15 Phase 29 status semantic).

One minor enhancement beyond the plan example: `_parse_anthropic_native` preserves `upstream_request_id` even when status='failed' (the response.id is still useful for correlating failed captures with upstream logs). This mirrors `_parse_openai_compat`'s existing behavior at the same code path.

## D-12 + D-15 Invariants Enforced

- **D-12 (non-streaming Anthropic native parser):** added as `_parse_anthropic_native`; the streaming path delegated entirely to `services/stream_parser.py` (Plan 04). No duplication.
- **D-15 (widened status enum):** the new parser uses `status='failed'` on capture failure, matching migration 013's widened `ck_usage_logs_status IN ('success','error','unknown','failed')`. Legacy `status='unknown'` reserved for stripped-contract callers.
- **D-11 (proxy split-latency columns):** `record_usage` writes both columns when called by the proxy route handler (Plan 04's path); legacy callers leave them NULL.
- **AMD-04 (proxy_latency vs upstream_latency split):** the column names + signature kwarg names mirror the migration-013 columns 1:1, no aliasing.
- **AMD-07 (last-wins on output_tokens):** N/A here — that invariant lives in the streaming parser; Plan 06 is the non-streaming dict path which receives the cumulative total in a single `usage` block.

## Files Modified

- `api_server/src/api_server/services/usage_recorder.py` — +66 lines (parser + signature + SQL)
- `api_server/tests/services/test_usage_recorder.py` — +217 lines (7 new tests + updated module docstring)

## Commits

- `902b9df` feat(29-06): add _parse_anthropic_native + extend record_usage signature with proxy/upstream latency kwargs

## Self-Check: PASSED

- File `api_server/src/api_server/services/usage_recorder.py` exists with `def _parse_anthropic_native` and the extended `record_usage` signature — verified via grep
- File `api_server/tests/services/test_usage_recorder.py` contains the 7 new test functions — verified via pytest collection (19 tests total)
- Commit `902b9df` exists in `git log` on the active branch — verified
- All 19 usage_recorder tests PASS; all 10 Plan 04 route tests PASS; no regression in dependent suites

## Deferred Issues

- `tests/spikes/test_phase29_probe_val_08_streaming_tee.py` has an unrelated `aiohttp` import error (collection-time only) — pre-existing in the repo, NOT caused by this plan. Logged for a future tooling cleanup; does not block any Phase 29 ship gate since `aiohttp` is only used inside that one spike file and the runtime path uses `httpx`.
