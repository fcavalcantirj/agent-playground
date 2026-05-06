# PROBE-VAL-03

## PROBE-VAL-03: OpenRouter post-hoc /generation latency

- model: `anthropic/claude-haiku-4-5`
- iterations: 5
- poll interval: 0.5s, max wait: 60.0s

### Per-iteration measurements

- iter 1: latency: 9.662s, total_cost: 5.8e-05
- iter 2: latency: 11.522s, total_cost: 5.8e-05
- iter 3: latency: 9.042s, total_cost: 5.8e-05
- iter 4: latency: 13.551s, total_cost: 5.8e-05
- iter 5: latency: 10.504s, total_cost: 5.8e-05

### Percentiles
- p50: 10.504s
- p95: 13.551s
- p99: 13.551s

### `data.total_cost` field shape (verbatim)
```json
{
  "total_cost": 5.8e-05,
  "type": "float",
  "tokens_prompt": 1,
  "tokens_completion": 8,
  "native_tokens_prompt": 8,
  "native_tokens_completion": 10
}
```

### Assumption A1 — same BYOK key reads its own generation
- 5/5 iterations succeeded with the original key.
- A1 verdict: **PASS**

### Verdict reasoning
- p95 latency <= 5.0s (original plan gate): **False** (p95=13.551s)
- p95 latency <= 60s (lookup-works gate): **True** (p95=13.551s)
- data.total_cost is Decimal-castable: **True** (5/5 samples castable)
- A1 holds (same BYOK reads its own generation): **True**

### Proposed AMD-08+ amendment (deviation surfaced for human review)
- 29-RESEARCH.md §OpenRouter Post-Hoc Backfill currently bakes `await asyncio.sleep(2.0)` + retries at [0.0, 2.0, 5.0]s (9s ceiling). Empirical p95=13.551s exceeds that ceiling.
- Recommended: bump initial sleep to ~5.0s and extend retries to [0.0, 10.0, 20.0, 30.0]s (65s ceiling) — covers measured p99=13.551s with headroom while keeping the activity bounded. Run as a Temporal activity (not inline in the request path) so the multi-second wait does not block other work.
- Owner of the change: Plan 29-06 (backfill activity) when it runs; the spike here just records the deviation.
- Tail-latency variance is real: iter range [9.0s, 13.6s] across 5 samples — OpenRouter's /generation endpoint is eventually-consistent, not transactional.

VERDICT: PASS
