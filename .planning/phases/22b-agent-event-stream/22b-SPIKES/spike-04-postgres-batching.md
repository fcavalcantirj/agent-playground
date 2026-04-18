---
spike: 04
name: postgres-write-batching
validates: "Given 5 agents × 200 matched event rows inserted concurrently, then batched INSERT (100 rows per transaction) outperforms per-row INSERT by >2x with no UniqueViolations, no deadlocks, and per-agent seqs remaining gap-free 1..N"
verdict: PASS
related: [spike-05]
tags: [postgres, asyncpg, batching, throughput]
---

# Spike 04 — Postgres write batching

## How I ran it

`/tmp/22b-spike04_05.py` — asyncpg against `deploy-postgres-1` (inside the `deploy` docker network, run via `docker exec deploy-api_server-1 python3 /tmp/22b-spike04_05.py`). Created an ad-hoc `spike_agent_events_probe` table mirroring the proposed `agent_events` shape (BIGSERIAL PK, UUID agent_container_id, BIGINT seq, JSONB payload, UNIQUE(agent_container_id, seq)).

Two passes:
1. **Per-row INSERT** — one transaction per row, `pg_advisory_xact_lock(hashtext(agent_id::text))` + `MAX(seq)+1` read + INSERT. 5 agents × 200 rows = 1000 total, concurrent via `asyncio.gather`.
2. **Batched INSERT(100)** — one transaction per 100-row batch. Advisory lock once, `MAX(seq)+1` once, `conn.executemany(...)` for the batch.

## Results

```
per-row:       1000 rows in 0.48s → 2076 rows/s
batched(100):  1000 rows in 0.04s → 25722 rows/s
speedup:       12.4x
```

Per-agent seqs: all 5 agents had gap-free `seq 1..200` after both passes.

## Verdict: PASS (and exceeds the >2x bar by 6x)

12× speedup is comfortably inside the "batched > per-row" expectation. D-12's bounded queue + batched INSERT consumer design is validated.

## Planner notes

1. **Advisory lock replaces `FOR UPDATE`.** `FOR UPDATE` with `MAX(seq)` is not allowed in Postgres (`FeatureNotSupportedError: FOR UPDATE is not allowed with aggregate functions`). `pg_advisory_xact_lock(hashtext($1::text))` gives the same single-writer-per-agent semantic WITHOUT the aggregate-lock conflict. **D-16 in CONTEXT.md must be revised** — see CONTEXT.md update alongside this spike. The lock is transaction-scoped (auto-released on commit/rollback); no cleanup needed.
2. **Batch size of 100 is the right order of magnitude.** Per-row at 2k/s is fine for normal traffic (reply_sent events are per-human-DM, << 1/s per agent). Batched at 25k/s gives ~12× headroom for burst windows (e.g. retroactive re-attach catching up on missed events after API restart). D-12's "100 rows or 100ms window" is a good heuristic.
3. **No deadlocks observed.** Advisory locks are hashed on the agent_container_id — different agents use different locks — so concurrent per-agent writes never contend across agents. Within one agent, the single-writer invariant (D-10 app.state registry) prevents contention in the happy path; pathological multi-writer is covered by spike 05.
4. **asyncpg's `executemany` for the batch INSERT** is the cleanest API. Each row's values are a tuple; asyncpg handles parameter binding server-side with prepared statements.
5. **Pool.close() timeout needed.** asyncpg's Pool.close() can hang if any connection is in a bad state. Wrap in `asyncio.wait_for(pool.close(), timeout=5.0)` with a TimeoutError handler — applies to the watcher's cleanup in the `/stop` handler too if it holds a pool connection.

## Reproducer notes

- Full script: `/tmp/22b-spike04_05.py` (local, not committed).
- DSN: `postgres://ap:<pw>@postgres:5432/agent_playground_api` (runs inside the api_server container).

## Related

- Spike 05 (seq ordering under concurrent writers) — same table, complementary test
