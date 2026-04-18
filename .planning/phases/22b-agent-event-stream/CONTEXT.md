---
phase: 22b
name: agent-event-stream
milestone: v0.2
status: queued (not yet discussed or planned)
created: 2026-04-18
blocks: Phase 22 SC-03 exit gate
blocked_by: none (Phase 22a backend + frontend already shipped)
---

# Phase 22b — Agent Event Stream

## Why this exists

Phase 22-07 attempted to validate Telegram round-trips by having a Python
harness poll Telegram's `getUpdates`. That conflicts with the hermes /
openclaw / etc. containers which also use `getUpdates` to receive inbound
messages (Telegram's API allows only one consumer at a time). Full writeup:
`.planning/phases/22-channels-v0.2/22-SC03-DESIGN-FLAW.md`.

## What to build

An observable event stream for every running agent_container. The API
server watches each container's log output, parses structured events (the
canonical ones: `reply_sent`, `reply_failed`, `agent_ready`, `agent_error`),
writes rows to Postgres, and exposes them via `GET /v1/agents/:id/events`.

The e2e test harness (Phase 22-07 Task 1) is then rewritten to poll the
API instead of Telegram.

## Shape (pre-discuss; subject to change)

### New Postgres table (migration `004_agent_events`)

```
CREATE TABLE agent_events (
  id BIGSERIAL PRIMARY KEY,
  agent_container_id UUID NOT NULL REFERENCES agent_containers(id) ON DELETE CASCADE,
  seq BIGINT NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  kind TEXT NOT NULL,           -- 'reply_sent' | 'reply_failed' | 'agent_ready' | 'agent_error' | ...
  payload JSONB NOT NULL,
  correlation_id TEXT,          -- matches text body patterns like "ping hermes r1 HHMMSS" etc.
  UNIQUE (agent_container_id, seq)
);
CREATE INDEX agent_events_by_agent_since ON agent_events (agent_container_id, ts DESC);
```

### New runner_bridge concern

A background task per running agent: `asyncio.create_task(_watch_logs(container_id, agent_id))`
that streams `docker logs -f` via the docker SDK, feeds each line through
a recipe-specific parser, and upserts rows. Canceled on stop.

### Recipe schema v0.2 add

```yaml
channels:
  telegram:
    event_log_regex:
      reply_sent: "pattern that matches the container's 'bot replied X to chat Y' line"
      reply_failed: "..."
```

(Empirical, per-recipe, same discipline as `verified_cells`. Five regexes
to discover — cheap.)

### New API route

```
GET /v1/agents/:id/events?since_seq=N&kinds=reply_sent,reply_failed
  -> {events: [{seq, ts, kind, payload, correlation_id}], next_seq: N+1}
```

Long-poll friendly (30s server hold if `since_seq >= latest`).

### Harness rewrite

`test/lib/telegram_harness.py` drops `getUpdates` entirely. New flow:
1. Harness sends DM via `sendMessage` only (single call, no polling).
2. Harness polls `GET /v1/agents/:id/events?since_seq=<baseline>&kinds=reply_sent`.
3. PASS when an event arrives whose `correlation_id` matches the sent text
   AND `ts > send_time`, within timeout.

`test/e2e_channels_v0_2.sh` updates the step 4 block to use the new harness
subcommand; no other MATRIX changes.

## Why this is robust

- No getUpdates consumers fight: hermes/openclaw own Telegram polling
  exclusively; our API is the sole observer via docker logs.
- Durable: a reply that landed during a 500ms harness gap is still in
  Postgres waiting to be read.
- Works for every current and future recipe — regex per recipe, not a
  per-recipe hook.
- CLAUDE.md Rule 2 compliant: dumb harness, intelligence in the API.
- Reuses Phase 22 substrate: `agent_containers`, `runner_bridge` patterns,
  `run_store` CRUD conventions.

## What to spike before planning (Golden Rule 5)

1. **Per-recipe log line format** — send a test message to each running
   recipe container and capture the exact "reply sent" log line. Regex
   captured in the recipe file under `channels.telegram.event_log_regex`.
2. **Docker SDK `logs(follow=True)` backpressure** — confirm it doesn't
   block on a recipe that's emitting thousands of lines/second during a
   cold-boot skill sync.
3. **Graceful log-watcher teardown** — when a container is `docker rm -f`'d,
   the log stream should end cleanly without leaking the asyncio task.
4. **Postgres write batching** — one INSERT per log line or buffered?
   Measure under a flood (nanobot's boot output).
5. **Ordering guarantees** — `seq` assignment under concurrent writes for
   the same agent (unlikely, but spike the edge).

## Exit gate (proposed)

- Migration `004_agent_events` applied, round-trip (upgrade/downgrade/upgrade) clean.
- `GET /v1/agents/:id/events` returns events within 2s of a container
  emitting a matched log line.
- Harness round-trip proven against hermes, picoclaw, nullclaw, nanobot,
  openclaw — 1/1 PASS each, then the 15/15 stability gate from 22-07.
- No dangling docker log-watcher tasks after container stop.

## Scope estimate

- 1 migration (small, mirrors `003_agent_containers`)
- 1 new API route + 1 background watcher task
- Recipe schema additive field (follows v0.2 precedent)
- Harness rewrite (smaller — just poll HTTP instead of Telegram)
- 5 recipe-level regex additions

Realistic plan count: 3-4 plans across 2 waves. Single-day phase with
discuss + plan + execute cycle.

## Resume path

1. `/clear`
2. `/gsd-discuss-phase 22b-agent-event-stream` — pick up from this
   CONTEXT.md; confirm the architecture above or challenge it.
3. `/gsd-plan-phase 22b-agent-event-stream`
4. `/gsd-execute-phase 22b-agent-event-stream`
5. Once complete, rerun `bash test/e2e_channels_v0_2.sh` — this closes
   the SC-03 gate and lets Phase 22 be marked DONE.
