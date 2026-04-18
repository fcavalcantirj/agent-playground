---
spike: 05
name: seq-ordering-concurrent-writers
validates: "Given 4 concurrent writer tasks racing on the SAME agent_container_id (pathological violation of the single-writer-per-container invariant), when each executes a pg_advisory_xact_lock + MAX(seq)+1 + INSERT transaction, then all writes succeed serialized, final per-agent seq is gap-free 1..N, no UniqueViolations, no deadlocks"
verdict: PASS
related: [spike-04]
tags: [postgres, concurrency, advisory-lock, invariant]
---

# Spike 05 — seq ordering under concurrent writers

## How I ran it

Same harness as spike 04. Spawned 4 concurrent `asyncio` tasks all racing on ONE `agent_container_id`. Each writer does 50 INSERT transactions, giving 200 total. Each transaction:

```python
async with conn.transaction():
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1::text))", str(agent_id))
    row = await conn.fetchrow(
        "SELECT COALESCE(MAX(seq),0)+1 AS next_seq FROM events WHERE agent_container_id=$1",
        agent_id)
    await conn.execute(
        "INSERT INTO events (agent_container_id, seq, kind, payload, correlation_id) VALUES ($1, $2, $3, $4::jsonb, $5)",
        agent_id, row['next_seq'], 'reply_sent', '{...}', f"w{wid}-{i}")
```

Tracked per-writer counters: `successes`, `unique_violations`, `deadlocks`.

## Results

```
wall_s: 0.13
writer 0: {'successes': 50, 'unique_violations': 0, 'deadlocks': 0}
writer 1: {'successes': 50, 'unique_violations': 0, 'deadlocks': 0}
writer 2: {'successes': 50, 'unique_violations': 0, 'deadlocks': 0}
writer 3: {'successes': 50, 'unique_violations': 0, 'deadlocks': 0}

final row count: 200
gap-free? True
unique violations: 0
deadlocks: 0
```

## Verdict: PASS

Advisory locks fully serialize the 4-writer race — every write succeeds with a unique seq, result is gap-free `1..200`, zero UniqueViolations, zero deadlocks. Wall time 130ms for 200 serialized inserts ≈ 0.65ms per serialized txn.

## Interpretation

1. **Single-writer invariant (D-10) is defense-in-depth, not load-bearing for correctness.** Even if the app-state registry were violated and 4 watcher tasks raced on one container, the DB layer serializes them cleanly via advisory lock. D-10's registry is there for efficiency (no racing on app-state lookups) and for cancellation discipline, not because the DB can't handle it.
2. **Advisory locks scale per-agent independently.** `hashtext(agent_id::text)` gives a unique integer per agent; Postgres's advisory-lock table is keyed on the integer. Different agents use different entries; no cross-agent contention.
3. **FOR UPDATE is NOT needed.** Combined with spike 04's "FOR UPDATE with aggregate not allowed" finding, advisory locks are strictly better: correct AND compatible with `MAX(seq)+1`.

## Impact on CONTEXT.md D-16

Revise D-16 from:
> `SELECT COALESCE(MAX(seq),0)+1 FROM agent_events WHERE agent_container_id=$1 FOR UPDATE`

To:
> `SELECT pg_advisory_xact_lock(hashtext($1::text))` then `SELECT COALESCE(MAX(seq),0)+1 FROM agent_events WHERE agent_container_id=$1`

Full amendment landed in CONTEXT.md alongside this spike.

## Related

- Spike 04 (batching throughput) — same table, shared reproducer
- D-10 (app.state.log_watchers registry) — validated as defense-in-depth, not load-bearing
- D-16 (seq allocation) — needs revision per this finding
