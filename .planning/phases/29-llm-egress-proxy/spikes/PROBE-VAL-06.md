# PROBE-VAL-06

## PROBE-VAL-06: idempotency in-flight gap (O-03) + AMD-03 strategy

### Part A — existing primitive (services/idempotency.py)
- two coroutines launched 50ms apart, each simulating a 3s upstream call
- upstream call_count after both resolve: 2
- gap reproduced (call_count > 1 → double-charge): **True**

- gap reproduced — existing primitive double-charges.

### Part B — AMD-03 reserved-row strategy (shadow table)
- two coroutines launched 50ms apart, each simulating a 3s upstream call
- upstream call_count after both resolve: 1
- both coroutines saw the SAME verdict: **True**
- per-coroutine outcomes:
```json
[
  {
    "label": "a",
    "verdict": {
      "label": "a",
      "tokens": 99,
      "winner": true
    }
  },
  {
    "label": "b",
    "verdict": {
      "label": "a",
      "tokens": 99,
      "winner": true
    },
    "replayed": true
  }
]
```
- AMD-03 single-charges — pattern empirically validated.

### Verdict reasoning
- O-03 gap reproduced (existing primitive double-charges): **True**
- AMD-03 single-charges: **True**
- AMD-03 both callers see SAME verdict: **True**

VERDICT: PASS
