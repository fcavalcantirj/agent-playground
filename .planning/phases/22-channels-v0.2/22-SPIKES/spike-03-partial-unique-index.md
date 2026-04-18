# Spike 03 — Postgres partial unique index + UniqueViolation mapping

**Date:** 2026-04-18
**Plan affected:** 22-02 (migration), 22-05 (endpoint catches UniqueViolation → 409)
**Verdict:** PASS

## Probe

Against `deploy-postgres-1` (Postgres 17-alpine):

```sql
CREATE TABLE spike_agent_containers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_instance_id uuid NOT NULL,
  container_id text NOT NULL,
  container_status text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX spike_one_running_per_agent
  ON spike_agent_containers(agent_instance_id)
  WHERE container_status = 'running';
```

## Test 1 — second concurrent running row blocked

- INSERT cont1 running → OK
- INSERT cont2 running for same agent → **ERROR: duplicate key value violates unique constraint "spike_one_running_per_agent"**
- DETAIL includes `Key (agent_instance_id)=(<uuid>) already exists.`

## Test 2 — stop-then-start OK

- UPDATE cont1 → stopped
- INSERT cont2 running → OK (partial index no longer sees the stopped row)
- Resulting state: `cont1 stopped, cont2 running`

## Verdict: PASS

- Partial unique index enforces "one running container per agent" atomically in the DB layer
- Error has a stable `constraint_name` ("spike_one_running_per_agent") that asyncpg's `UniqueViolationError.constraint_name` will expose
- No race window — two concurrent inserts serialized by the index itself

## Plan citation

Plan 22-02 Task 1: `CREATE UNIQUE INDEX ... WHERE container_status = 'running'` — verbatim from this spike.
Plan 22-05 Task 2: catch `asyncpg.exceptions.UniqueViolationError` and branch on `.constraint_name == 'agent_containers_one_running_per_agent'` → 409 AGENT_ALREADY_RUNNING.

No plan delta required.
