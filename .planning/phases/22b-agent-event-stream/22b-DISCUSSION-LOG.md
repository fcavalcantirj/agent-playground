# Phase 22b: agent-event-stream — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `22b-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-04-18
**Phase:** 22b-agent-event-stream
**Areas discussed:** Event source & ingest, Event schema & privacy, Delivery & watcher lifecycle, Spike gate & scope, Auth, seq semantics, agent_ready emission, Retention + connection limits

---

## Event source & ingest

| Option | Description | Selected |
|--------|-------------|----------|
| Docker logs scrape | Watch docker logs -f per container; per-recipe regex matches canonical log lines; zero agent-side patches | ✓ |
| Agent-side HTTP emit | Fork every agent to POST events; robust but 5 upstream patches to maintain | |
| Hybrid | Logs now, emit later for rich events | |

**User's choice:** Docker logs scrape. Initially asked for explanation of the detection problem; confirmed the choice after seeing the three options broken down.

| Option | Description | Selected |
|--------|-------------|----------|
| Docker SDK logs(follow=True) | Iterator-based; clean teardown on docker rm -f; asyncio.to_thread bridge | ✓ |
| subprocess docker logs -f | Simpler dep; explicit SIGTERM on teardown | |
| You decide | Spike both if close | |

**User's choice:** Docker SDK logs(follow=True).

| Option | Description | Selected |
|--------|-------------|----------|
| Every log line through regex map | Each line tested; only matches produce rows; unmatched discarded | ✓ |
| Buffered batch match | Accumulate in memory, regex in batches; delays event availability | |
| Keep full log tail AND parse | Persist every line as log_line kind alongside matches; Postgres flood risk | |

**User's choice:** Every log line through regex map.

| Option | Description | Selected |
|--------|-------------|----------|
| Additive v0.2 field on channels.telegram | channels.telegram.event_log_regex — same discipline as ready_log_regex + verified_cells | ✓ |
| Top-level events: block (cross-channel) | Future-proof for Discord/Slack; more upfront schema work | |
| Hardcoded in runner per recipe | Fast to ship; violates 'recipe is source of truth' | |

**User's choice:** Additive v0.2 field on channels.telegram.

---

## Event schema & privacy

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed 4 kinds for 22b | reply_sent, reply_failed, agent_ready, agent_error. CHECK constraint enforces | ✓ |
| Open TEXT, no constraint | Recipe-defined kinds without migrations; fuzzier filtering | |
| Fixed 4 + reserved recipe_* namespace | Small core + extension prefix | |

**User's choice:** Fixed 4 for 22b.

| Option | Description | Selected |
|--------|-------------|----------|
| Metadata only, no reply text | {chat_id, length_chars, captured_at}. BYOK discipline — no bodies in Postgres | ✓ |
| Metadata + redacted text | First N chars with value redaction; wider attack surface on DB leak | |
| Full text, short TTL | Most useful for debugging; hardest BYOK justification | |

**User's choice:** Metadata only, no reply text.

| Option | Description | Selected |
|--------|-------------|----------|
| Send-side UUID token in outbound text | Harness embeds UUID in ping; regex capture group extracts echoed id from log; PASS if cid matches + ts > send_time | ✓ |
| Timestamp window only | No correlation id; accept any reply_sent in 30s window; racy | |
| Agent-emitted message_id | Per-recipe gray area; not all agents log it | |

**User's choice:** Send-side UUID token. Each recipe's event_log_regex MUST include a named capture group for the echoed id.

| Option | Description | Selected |
|--------|-------------|----------|
| Typed-per-kind Pydantic | Per-kind payload models in models/events.py; validated on INSERT + API response | ✓ |
| Free-form JSONB, spec in docs | No validation; faster to ship | |
| Free-form with extra='allow' | Pydantic defined but non-blocking | |

**User's choice:** Typed-per-kind Pydantic.

---

## Delivery & watcher lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| Long-poll with since_seq | Server holds up to 30s on asyncio.Event; returns as soon as rows land | ✓ |
| Short-poll only | Client retries every 1s; chattier | |
| SSE stream | Server pushes newline-delimited JSON; more plumbing than needed | |
| WebSocket | Overkill for harness; cheap frontend live-feed later | |

**User's choice:** Long-poll with since_seq. Initially asked for clarification on the two-flow architecture (Docker → API continuous push vs Harness → API request/response pull); confirmed after the ASCII flow diagram explanation.

| Option | Description | Selected |
|--------|-------------|----------|
| Registry in app.state | app.state.log_watchers: dict[container_row_id, asyncio.Task]; mirrors image_tag_locks | ✓ |
| Detached asyncio.create_task | Simpler; can't cancel on demand | |
| Dedicated supervisor coroutine | Holds all sub-tasks; natural place for crash recovery | |

**User's choice:** Registry in app.state.

| Option | Description | Selected |
|--------|-------------|----------|
| Re-attach on startup | Lifespan hook queries running rows, spawns watcher per; events emitted during downtime are LOST (documented acceptable gap) | ✓ |
| Mark stopped + require manual restart | Simpler; invalidates in-flight sessions | |
| Re-attach + replay from Postgres | Redundant when docker logs is the only event source | |

**User's choice:** Re-attach on startup.

| Option | Description | Selected |
|--------|-------------|----------|
| Buffered INSERT + bounded queue | asyncio.Queue(500); 100-row batches every 100ms; unmatched lines never enter queue | ✓ |
| Per-line INSERT, no batching | Simpler; fine when match rate is low | |
| Drop-tail when full | Bounded queue, visible data loss | |

**User's choice:** Buffered INSERT + bounded queue.

---

## Spike gate & scope

| Option | Description | Selected |
|--------|-------------|----------|
| All 5 spikes mandatory | (1) per-recipe regex, (2) docker SDK backpressure, (3) watcher teardown, (4) Postgres batching, (5) seq ordering. Matches 22-SPIKES/ discipline | ✓ |
| 3 mandatory + 2 inline | Must-spike: regex, teardown, ordering; inline: backpressure + batching | |
| Just regex-per-recipe | Violates Rule 5 — runner_bridge doesn't follow docker logs today | |

**User's choice:** All 5 mandatory.

| Option | Description | Selected |
|--------|-------------|----------|
| Live container + DM + grep | docker run, sendMessage, inspect docker logs, author regex, paste into recipe YAML | ✓ |
| Source-dive each agent | Read agent source to find log format | |
| Both — source-dive + live-verify | Upper-bound effort | |

**User's choice:** Live container + DM + grep.

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal for SC-03 only | Migration + watcher + endpoint + regex + harness rewrite + 15/15 PASS gate. Deferred: frontend UI, rich kinds, cross-channel, agent-side emit | ✓ |
| Minimal + frontend event viewer | Adds ~1 wave; doesn't unblock SC-03 | |
| Fuller observability story | 2× scope; slows SC-03 unblock | |

**User's choice:** Minimal for SC-03 only.

| Option | Description | Selected |
|--------|-------------|----------|
| Replace getUpdates path, keep sendMessage | New send-and-wait-api subcommand; legacy kept for non-API cases | ✓ |
| New harness file, delete old | Greenfield event_harness.py | |
| Two harnesses coexist | Both side by side; flag-driven | |

**User's choice:** Replace getUpdates path, keep sendMessage.

---

## Auth on /v1/agents/:id/events

| Option | Description | Selected |
|--------|-------------|----------|
| Bearer+ownership OR AP_SYSADMIN_TOKEN | Normal: Bearer→user_id, check agent.user_id match. Sysadmin: token matches AP_SYSADMIN_TOKEN env → skip check | ✓ |
| Bearer+ownership, no sysadmin backdoor | No backdoor; harness breaks when multi-user ships | |
| Sysadmin token is ONLY path in 22b | Smallest surface; multi-user auth is later phase | |

**User's choice:** Bearer + ownership OR AP_SYSADMIN_TOKEN. User explicitly proposed this shape ("bearer token + ownership OR sysadmin token") in an Other note.

---

## seq ordering + monotonicity

| Option | Description | Selected |
|--------|-------------|----------|
| Per-agent BIGSERIAL (gap-free) | MAX(seq)+1 FOR UPDATE per-agent; UNIQUE(agent_container_id, seq); single-writer-per-container = no race | ✓ |
| Global BIGSERIAL | Single counter; simplest INSERT; harness cursor is wider | |
| Per-agent, gap-allowed | Failed INSERTs leave holes; breaks 'seq=N means N events' invariant | |

**User's choice:** Per-agent BIGSERIAL (gap-free). Initially admitted blind on the concept; confirmed after explanation of the flow (baseline → send → long-poll → match correlation_id) and the three tradeoffs.

---

## agent_ready emission path

| Option | Description | Selected |
|--------|-------------|----------|
| Watcher matches ready_log_regex | Recipe's persistent.spec.ready_log_regex IS the definition of agent_ready; single source of truth | ✓ |
| /start handler emits directly | Handler INSERTs after successful runner call; watcher never sees it | |
| Both — handler AND watcher | Duplicate rows; harness has to dedupe | |

**User's choice:** Watcher matches ready_log_regex.

---

## Retention + connection limits

| Option | Description | Selected |
|--------|-------------|----------|
| TTL = agent_container lifetime + 7d | ON DELETE CASCADE in 22b; purge-job for stopped-after-7d is later phase | ✓ |
| Keep forever | Postgres grows unbounded | |
| Cap at 10k rows per agent_container | Hard cap; protects Postgres under pathological flood | |

**User's choice:** TTL = agent_container lifetime + 7d.

| Option | Description | Selected |
|--------|-------------|----------|
| 1 per (caller, agent_id) via asyncio.Lock | app.state.event_poll_locks; second caller 429s with CONCURRENT_POLL_LIMIT | ✓ |
| Global Semaphore(50) | Bound total long-polls across all agents | |
| No limit | Rely on FastAPI worker pool + timeout | |

**User's choice:** 1 per (caller, agent_id) via asyncio.Lock.

---

## Claude's Discretion

- Retry/backoff tuning inside the log-watcher task on transient `docker logs(follow=True)` iterator errors
- Pydantic validation style: model_validator vs __post_init__
- Exact Postgres index names
- Handling of re-attach when container_id no longer exists in Docker

## Deferred Ideas

- Rich kinds (llm_call, token_usage, pair_code_issued, webhook_inbound) — observability v2
- Cross-channel support (Discord, Slack, WhatsApp, Matrix, Signal) — matches 22-CONTEXT.md out-of-scope boundary
- Agent-side HTTP emission — for events that don't hit stdout
- Frontend event viewer panel — out of scope for 22b
- TTL purge job for stopped-after-7d — post-MVP
- WebSocket/SSE live-feed — until a frontend need makes long-poll insufficient
- App-level multi-tenant rate limits on /events — fold in only if abuse is observed
