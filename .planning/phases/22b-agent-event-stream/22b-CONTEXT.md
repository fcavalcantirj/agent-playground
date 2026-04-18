---
phase: 22b
name: agent-event-stream
milestone: v0.2
status: Ready for planning (after spikes)
gathered: 2026-04-18
revised: 2026-04-18 (post-spike-01a pivot — direct_interface added)
supersedes: .planning/phases/22b-agent-event-stream/CONTEXT.md (pre-discussion brief)
blocks: Phase 22 SC-03 exit gate
blocked_by: Spike 06 (direct_interface per recipe) + Spikes 02-05 (log-watcher infra) must land before /gsd-plan-phase. Spikes 01b-01e (per-recipe reply_sent regex) are required for Gate B but not load-bearing for architecture.
---

# Phase 22b — Agent Event Stream — Context

<domain>
## Phase Boundary

Build **two complementary observation paths** for every running `agent_container`, each solving a different facet of Phase 22-07's SC-03 gate:

**Primary path — `direct_interface` (automatable SC-03 Gate A):**
Every recipe declares how to programmatically invoke the agent directly — via `docker exec <cid> <agent-cli>` or an in-container HTTP server. The test harness hits this surface, sends a prompt, reads the reply, asserts. **No Telegram involved.** Matches MSV's `forward_to_agent.go` pattern — MSV pods expose `/v1/chat/completions` on localhost; MSV never relied on Telegram round-trip for e2e.

**Secondary path — `agent_events` stream (Gate B + observability):**
The API server watches each container's log output (Docker SDK `logs(follow=True, stream=True)`), regex-matches canonical event lines (`reply_sent`, `reply_failed`, `agent_ready`, `agent_error`), writes typed rows to a new `agent_events` table, and exposes them via long-poll `GET /v1/agents/:id/events?since_seq=N&timeout_s=30`. Used for: (a) verifying Telegram delivery after a bot→self `sendMessage` probe, (b) frontend observability of running agents, (c) future MTProto-based user-impersonation harness.

**Why the pivot:** Spike 01a (2026-04-18) proved Telegram Bot API cannot impersonate a user — `sendMessage` with a bot token sends AS the bot. SC-03 as originally defined ("user deploys → bot receives inbound DM → agent replies") cannot be automated via the Bot API at all. Real user→bot input requires MTProto (Client API) with a separate Telegram user account — deferred. Meanwhile, every recipe in the current catalog already exposes a direct programmatic surface (proven: `hermes chat -q -Q`, documented: `picoclaw agent -m`, `nullclaw agent -m | gateway`, `nanobot agent | serve`, `openclaw` `/v1/chat/completions`). That's the SC-03 automation path.

The test harness (`test/lib/telegram_harness.py` + `test/e2e_channels_v0_2.sh`) gains two subcommands: `send-direct-and-read` (primary) and `send-telegram-and-watch-events` (secondary). SC-03's 15/15 gate becomes passable via Gate A for agent correctness + Gate B for delivery + Gate C for manual user-in-the-loop (once per release, not per commit).

**In scope (22b):** (1) migration `004_agent_events`, (2) log-watcher registry, (3) long-poll events endpoint, (4) per-recipe `channels.telegram.event_log_regex` (5 regexes), (5) **per-recipe `direct_interface` block (5 recipes)**, (6) harness rewrite with both primary and secondary subcommands, (7) retroactive SC-03 run (Gate A full pass, Gate B full pass; Gate C manual).

**Out of scope (deferred):** frontend event viewer, rich kinds (`llm_call`, `token_usage`), cross-channel support (Discord/Slack), agent-side HTTP emission from inside the agent, MTProto user-impersonation harness.

</domain>

<decisions>
## Implementation Decisions

### Event source & ingest

- **D-01 — Ingest model:** **Docker logs scrape.** The API watches `docker logs -f <container_id>` per running agent; per-recipe regex in `channels.telegram.event_log_regex.*` matches canonical log lines and produces `agent_events` rows. Zero agent-side patches — fits every current and future recipe without touching upstream. Brittleness cost (log format drift) mitigated by empirically-captured regex + a `verified_cells`-style entry per recipe.
- **D-02 — Log transport:** **Docker SDK `logs(follow=True, stream=True)`.** Iterator-based; clean teardown when `docker rm -f` ends the iterator. Bridged into asyncio via `asyncio.to_thread`. Matches the existing `runner_bridge` style (which already imports the runner module for `run_cell_persistent` / `stop_persistent` / `exec_in_persistent`). Requires adding `docker` package to `api_server/pyproject.toml`.
- **D-03 — Parse strategy:** **Every log line through the recipe's `event_log_regex` dict.** Each line tested against every regex; only matches produce rows. Unmatched lines discarded immediately. Postgres write rate is bounded by *match rate*, not *log rate* (critical for nanobot cold-boot flood — thousands of lines/second).
- **D-04 — Regex location:** **Additive v0.2 field** — `channels.telegram.event_log_regex: {reply_sent: "...", reply_failed: "...", agent_error: "..."}`. Recipe-level, per-channel. Same discipline as `ready_log_regex` + `verified_cells[]`. `agent_ready` reuses the existing `persistent.spec.ready_log_regex` — **single source of truth** for readiness (see D-14).

### Event schema & privacy

- **D-05 — Kinds enumeration:** **Fixed 4** — `reply_sent`, `reply_failed`, `agent_ready`, `agent_error`. Enforced via a `CHECK` constraint on the `kind` column. Additions require a migration; acceptable for SC-03 scope. Frontend + tests can rely on an exhaustive match.
- **D-06 — Reply text storage:** **Metadata only.** `payload` for `reply_sent` stores `{chat_id, length_chars, captured_at}` — **no reply body text**. BYOK discipline: user bot conversations stay on Telegram's servers, never in our Postgres. Harness correlates by `correlation_id` + `ts`, doesn't need the body to prove reply happened. Applies to all 4 kinds: no secrets, no bodies, only structural metadata.
- **D-07 — `correlation_id` semantics:** **Send-side UUID token embedded in outbound text.** Harness generates a short UUID (e.g. `a3f1`), embeds it in the ping text (`"ping hermes r1 a3f1"`). Each recipe's `event_log_regex.reply_sent` MUST include a named capture group (e.g. `(?P<cid>[a-f0-9]{4,})`) that extracts the echoed correlation id from the container's "reply sent" log line. Harness PASS = event whose `correlation_id` matches the sent UUID AND `ts > send_time`. Spike-1 (per-recipe regex capture) must prove every recipe echoes the user's send text in its log line — or the regex falls back to a timestamp-window match with a FLAG in the recipe's `verified_cells[]`.
- **D-08 — `payload` contract:** **Typed-per-kind Pydantic.** Define `ReplySentPayload`, `ReplyFailedPayload`, `AgentReadyPayload`, `AgentErrorPayload` in `api_server/src/api_server/models/events.py`. Validated on INSERT path (reject rows that don't match) and on API response projection. No runtime surprises for consumers.

### Delivery & watcher lifecycle

- **D-09 — Delivery shape:** **Long-poll.** `GET /v1/agents/:id/events?since_seq=N&kinds=reply_sent,reply_failed&timeout_s=30`. Server holds the request open on an `asyncio.Event` (per-agent, stored in `app.state.event_poll_signals[agent_id]`) that the watcher `.set()`s when it inserts a new row. Returns immediately if rows >= `since_seq+1` already exist. Harness: one curl per round-trip, no client-side retry loop. **Intelligence in the API.** SSE / WebSocket deferred — unnecessary for 22b.
- **D-10 — Watcher task registry:** **`app.state.log_watchers: dict[container_row_id, asyncio.Task]`.** Spawned in the `/v1/agents/:id/start` handler after `execute_persistent_start` returns `running`; cancelled in the `/v1/agents/:id/stop` handler before `execute_persistent_stop`. Same shape as existing `app.state.image_tag_locks` + `app.state.run_semaphore` + `app.state.locks_mutex`.
- **D-11 — API restart behavior:** **Re-attach on startup.** FastAPI `lifespan` hook queries `agent_containers WHERE container_status='running'`, spawns a watcher task for each. Events emitted between API crash and re-attach are LOST — documented acceptable gap because Docker holds recent stdout in its in-memory buffer (re-attach typically catches the last few hundred lines). `correlation_id` prevents false-PASS because `reply_sent` with matching id only counts if `ts > send_time`.
- **D-12 — Backpressure strategy:** **Buffered INSERT + bounded queue.** Per-watcher `asyncio.Queue(maxsize=500)`. Regex matcher pushes matched lines; a sibling consumer batches up to 100 matched rows per commit or every 100ms (whichever fires first). Queue full = oldest line drops + one `_log.warning(...)`. Because only matched lines enter the queue, the typical match rate (a few events per minute) makes flooding essentially impossible in practice — but the bound guards against pathological cases (e.g. misauthored regex matches every line).
- **D-13 — Concurrent long-poll cap:** **One long-poll per (caller, agent_id) via `asyncio.Lock`.** `app.state.event_poll_locks: dict[agent_id, asyncio.Lock]`. Second concurrent caller for the same agent gets `429 CONCURRENT_POLL_LIMIT`. Harness and future frontend-live-feed each use one connection per agent — no contention in practice. Prevents "open 1000 long-polls" abuse.

### agent_ready single-source-of-truth

- **D-14 — `agent_ready` emission:** **Watcher matches `persistent.spec.ready_log_regex`.** The log watcher treats the recipe's existing ready regex as the definition of `agent_ready`; when matched it inserts a row. The `/start` handler's synchronous readiness check (used to return HTTP 200 with `boot_wall_s` + `ready_at`) stays as-is — it observes the same log line, but its output is the HTTP response, not a durable event. Single source of truth for the *durable* record; no duplicate rows.

### Auth on GET /v1/agents/:id/events

- **D-15 — Auth posture:** **Bearer + ownership check OR `AP_SYSADMIN_TOKEN` bypass.** Normal path: parse `Authorization: Bearer <token>`, resolve to `user_id`, check `agent.user_id == user_id` → 403 if mismatch. Today all users map to `ANONYMOUS_USER_ID` (Phase 19 MVP seam), so effectively it's presence-of-token + correct `agent_id`. Sysadmin path: if Bearer token equals the `AP_SYSADMIN_TOKEN` env var, ownership check is skipped. Used by the test harness (and eventual ops debugging). Env-var discipline mirrors `AP_CHANNEL_MASTER_KEY` — per-laptop/deploy state, NEVER committed to `.env` files. When multi-user ships post-MVP, the normal path tightens automatically.

### `seq` column semantics

- **D-16 — `seq` allocation:** **Per-agent, gap-free, serialized via advisory lock.** Each INSERT transaction does:

  ```sql
  SELECT pg_advisory_xact_lock(hashtext($1::text));  -- $1 = agent_container_id as text
  SELECT COALESCE(MAX(seq),0)+1 FROM agent_events WHERE agent_container_id = $1;
  INSERT INTO agent_events (agent_container_id, seq, ...) VALUES ($1, <next>, ...);
  ```

  `UNIQUE (agent_container_id, seq)` backstops the serialization. Advisory lock chosen over `FOR UPDATE` because Postgres rejects `FOR UPDATE` combined with aggregate functions (`FeatureNotSupportedError: FOR UPDATE is not allowed with aggregate functions` — empirically confirmed in spike 04). Advisory lock is transaction-scoped (auto-released on commit/rollback), hashed per-agent so cross-agent writes never contend.

  Spike 05 empirically validated: 4 concurrent writers on SAME agent × 50 rows each = 200 writes in 130ms, gap-free, 0 UniqueViolations, 0 deadlocks. Single-writer-per-container (D-10) is defense-in-depth, not load-bearing for correctness.

  Harness's `since_seq` is per-agent-local; survives API restart trivially (`SELECT MAX(seq)` on re-attach). Row-level PK (`id BIGSERIAL`) can still serve as a global monotonic cursor for future cross-agent ops queries.

### Retention & lifecycle

- **D-17 — Retention policy:** `agent_events` rows are `ON DELETE CASCADE` from `agent_containers` (already planned in the CONTEXT.md schema). In 22b ship: no TTL job — rows persist as long as the `agent_containers` row exists. A **future** purge job (post-MVP) will delete rows whose `agent_containers.stopped_at` is > 7 days old. Aligned with 22-CONTEXT.md "ephemeral `--rm` containers" out-of-scope note.

### Direct interface (NEW — spike-01a pivot, 2026-04-18)

Every recipe in the current catalog exposes a direct programmatic surface beyond Telegram. This is the PRIMARY path for SC-03 automation — invoking the agent directly, no Bot API user-impersonation problem. Verified by spike 01a (hermes) + MSV's `forward_to_agent.go` pattern + documented in each recipe's `--help`.

- **D-19 — `direct_interface` additive recipe v0.2 field.** Each recipe declares exactly one primary direct-invocation surface:

  ```yaml
  direct_interface:
    kind: docker_exec_cli | http_chat_completions
    spec: { ... }   # shape depends on kind
  ```

  Additive; recipes without this block get Gate A as manual-only (none of the current 5 fall here).

- **D-20 — `direct_interface.kind` enum.** Two kinds locked for v0.2:

  **`docker_exec_cli`** — harness runs `docker exec <cid> <argv>`; reply is on stdout.

  ```yaml
  direct_interface:
    kind: docker_exec_cli
    spec:
      argv_template: ["hermes", "chat", "-q", "{prompt}", "-Q", "-m", "{model}", "--provider", "openrouter"]
      timeout_s: 60
      stdout_reply: true
      reply_extract_regex: "(?s)(?P<reply>.+?)(?=\\n\\s*session_id:|$)"   # strip trailing session_id
      exit_code_success: 0
  ```

  **`http_chat_completions`** — harness POSTs OpenAI-compatible body to `http://localhost:<port>/v1/chat/completions` inside the container's network (via `docker exec curl ...` or a mapped port). Matches MSV's exact pattern.

  ```yaml
  direct_interface:
    kind: http_chat_completions
    spec:
      port: 8000
      path: /v1/chat/completions
      auth:
        header: Authorization
        value_template: "Bearer {api_key}"
      request_template:
        model: "<recipe>:main"
        messages:
          - { role: user, content: "{prompt}" }
      response_jsonpath: "$.choices[0].message.content"
      timeout_s: 60
  ```

- **D-21 — Per-recipe direct_interface mapping (proposed — spike 06 confirms empirically):**

  | Recipe | kind | argv / URL spec |
  |--------|------|-----------------|
  | hermes | `docker_exec_cli` | `hermes chat -q "{prompt}" -Q -m "{model}" --provider openrouter` ✅ proven |
  | picoclaw | `docker_exec_cli` | `picoclaw agent -m "{prompt}"` (per `--help`) |
  | nullclaw | `docker_exec_cli` | `nullclaw agent -m "{prompt}"` (per `--help`; HTTP alt: `nullclaw gateway`) |
  | nanobot | `http_chat_completions` | `nanobot serve` on port N; OpenAI-compatible (per `--help`) |
  | openclaw | `http_chat_completions` | Port 18000+ `/v1/chat/completions` (per MSV `forward_to_agent.go`) |

- **D-22 — Correlation is trivial for direct_interface.** Harness embeds UUID in `{prompt}` (e.g. `"reply with just: ok-a3f1"`), parses reply from the declared surface, asserts `a3f1` appears in the response. No log-scrape / no watcher buffer / no long-poll needed for Gate A. The `correlation_id` field in the resulting `agent_events.reply_sent` row (secondary path) is still set from the `inbound_message` buffer — but Gate A doesn't depend on it.

### Harness rewrite (revised by D-19..D-22 pivot)

- **D-18 — Two subcommands, composable SC-03 gate.** `test/lib/telegram_harness.py` (renamed internally to `agent_harness.py` if cleaner) exposes:

  **Primary — `send-direct-and-read`** (Gate A, fully automatable): harness invokes the recipe's `direct_interface` via `docker exec` or HTTP POST, reads reply, asserts on correlation id. Used for every `test/e2e_channels_v0_2.sh` round. **No Telegram creds required.**

  **Secondary — `send-telegram-and-watch-events`** (Gate B, partially automatable): harness calls Telegram `sendMessage` (bot → self-chat, legal for Bot API) with a correlation token, long-polls `GET /v1/agents/:id/events?since_seq=N&kinds=reply_sent&timeout_s=10`, verifies a `reply_sent` event with matching `chat_id` is recorded shortly after send. Verifies the Telegram delivery pipeline is wired without needing user-impersonation. **Does NOT verify a real user→bot round-trip.**

  **Deferred — `mtproto-send-and-read`**: full user→bot automation via a second Telegram user account using telethon/pyrogram. Future phase.

  Legacy `send-and-wait` (getUpdates-based) deleted — it was the design-flaw path.

- **D-18a — SC-03 exit gate decomposition:** Gate A (direct_interface round-trip, 5 recipes × 3 rounds, 15/15 PASS via primary harness subcommand) + Gate B (reply_sent events recorded for each recipe after a bot→self sendMessage probe, 5/5 PASS via secondary subcommand) + Gate C (manual user-in-the-loop Telegram round-trip verification, once per release, 1/recipe PASS). Phase 22 exit requires Gate A + Gate B green; Gate C is a release-time checklist, not a per-commit gate.

### Folded Todos

None — no open todos matched Phase 22b scope at discussion time.

### Claude's Discretion

- Exact retry/backoff tuning inside the log-watcher task when `docker logs(follow=True)` iterator raises a transient error.
- Whether to use `pydantic.model_validator` vs explicit `__post_init__` for the per-kind payload validation.
- Naming of the Postgres partial index on `agent_events(agent_container_id, seq)` (`ix_agent_events_agent_seq` or equivalent).
- Exactly how the lifespan re-attach handles a row whose `container_id` no longer exists in Docker (mark stopped, emit `agent_error`, or skip — planner decides based on spike findings).

</decisions>

<spike_gate>
## Spike Gate (Golden Rule 5 — MANDATORY BEFORE `/gsd-plan-phase`)

Every mechanism below must produce a committed artifact under `.planning/phases/22b-agent-event-stream/22b-SPIKES/` with a verdict (`PASS` / `FAIL` / `FLAGGED`) **before** `/gsd-plan-phase 22b-agent-event-stream` is invoked. Matches Phase 22's `22-SPIKES/` discipline. Patterns from other modules are **not** evidence for new mechanisms — Rule 5.

### Spike status after 2026-04-18 execution of spike 01a

- **Spike 01a (hermes reply_sent regex + direct_interface probe):** ✅ `PASS_WITH_PIVOT` — see `22b-SPIKES/spike-01a-hermes.md`. Surfaced the `direct_interface` paradigm, which adds Spike 06 (mandatory) and demotes Spikes 01b-01e from "architecture-blocking" to "required for Gate B only".

### Spike 06 — Per-recipe `direct_interface` surface (NEW, MANDATORY, added by 01a finding)

- For each of picoclaw, nullclaw, nanobot, openclaw (hermes already done via 01a):
  1. Start the image (or `docker run --rm --entrypoint` for one-shot).
  2. Invoke the proposed `direct_interface` per the D-21 mapping (CLI argv OR HTTP POST).
  3. Assert reply comes back as text/JSON with the correlation id present.
  4. Capture exact argv OR exact HTTP request/response shape; paste into recipe YAML under `direct_interface` + a `verified_direct_interface` note (same discipline as `verified_cells`).
- **Exit:** 4 recipes × 1 PASS. If any recipe cannot be driven this way, FLAG + document fallback (Gate A manual-only for that recipe).

### Spike 1 (now 01b-01e) — Per-recipe `reply_sent` log line format (required for Gate B)

**Status:** 01a done (hermes). 01b-01e still required for Telegram delivery verification (Gate B). Not architecture-blocking post-pivot — planner CAN proceed with stub regexes pending 01b-01e, but `/gsd-execute-phase` should not start without them.

- For each of picoclaw, nullclaw, nanobot, openclaw:
  1. `docker run` the image with Telegram creds from `.env.local`.
  2. Trigger a reply by having a human send a DM to the bot (sendMessage from a bot-token is NOT a valid test — it appears as bot-originated, see spike-01a §"Load-bearing finding").
  3. Inspect `docker logs <cid>` for the line emitted when the bot sends its reply.
  4. Author a regex; paste into `channels.telegram.event_log_regex.reply_sent`; add `verified_cells` entry.
- **Exit:** 4 recipes × 1 PASS (or documented FLAG with timestamp-window fallback).

### Spike 2 — Docker SDK `logs(follow=True)` backpressure under flood (mandatory)

- Pick the cold-boot-loudest recipe (nanobot: workspace bootstrap emits thousands of lines in ~18s).
- Attach the proposed log watcher (draft `asyncio.to_thread` + `asyncio.Queue(500)` with no consumer).
- Confirm: (a) the docker iterator does NOT block the container's own stdout buffer even when the queue fills (if it does, we have a priority inversion); (b) the queue-full drop path fires cleanly with a WARN log; (c) no `docker logs` process / file descriptor leaks after teardown.
- **Exit:** PASS verdict with max RSS + queue-drop count under flood.

### Spike 3 — Graceful watcher teardown on `docker rm -f` (mandatory)

- Start a container + its watcher task. Run for 10s.
- `docker rm -f <cid>` from outside the API.
- Confirm: the SDK iterator ends cleanly (no exception → coroutine returns), the watcher task transitions to `done` state within 2s, no hanging asyncio task after `Task.cancel()` is NOT needed (iterator-end is sufficient).
- Repeat with `docker stop` (SIGTERM instead of force-kill).
- **Exit:** PASS verdict; no dangling tasks in `asyncio.all_tasks()`.

### Spike 4 — Postgres write batching (mandatory)

- Simulate the matched-line flood: driver inserts 1000 rows across 5 agents in parallel with the proposed `MAX(seq)+1 FOR UPDATE` allocation.
- Measure: wall time, per-row latency, any deadlocks, any UniqueViolation races.
- Compare batched (100-row commits) vs per-row INSERT.
- **Exit:** PASS verdict with chosen batch size + measured throughput.

### Spike 5 — `seq` ordering under concurrent writes (mandatory)

- Confirm the single-writer-per-container invariant holds: spawn two watcher tasks for the same container_id (pathological; shouldn't happen in the wild), verify one is rejected by app-state registry OR `UNIQUE(agent_container_id, seq)` catches the collision cleanly.
- Validate `FOR UPDATE` locking cost under realistic write patterns.
- **Exit:** PASS verdict + documented invariant + test proving app-state registry rejects duplicate watchers.

### Spike exit condition (revised post-01a)

**Architecture-blocking (must be PASS/FLAG before `/gsd-plan-phase`):**
- Spike 01a ✅ done
- Spike 06 (direct_interface × 4 remaining recipes)
- Spike 02 (docker SDK backpressure)
- Spike 03 (watcher teardown)
- Spike 04 (Postgres batching)
- Spike 05 (seq ordering)

**Execution-blocking (must be PASS/FLAG before `/gsd-execute-phase`, but plan can start):**
- Spikes 01b-01e (per-recipe reply_sent regex for Gate B)

If any spike FAILs, the phase reopens — the spike result changes the design.

</spike_gate>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 22 substrate (what 22b reuses)

- `.planning/phases/22-channels-v0.2/22-CONTEXT.md` — channels v0.2 decisions that 22b builds on
- `.planning/phases/22-channels-v0.2/22-SC03-DESIGN-FLAW.md` — the empirical finding that justifies 22b's entire existence
- `.planning/phases/22-channels-v0.2/22-07-PLAN.md` — the blocked plan whose Task 1-2 outputs (`test/lib/telegram_harness.py`, `test/e2e_channels_v0_2.sh`) are rewritten in 22b
- `.planning/phases/22-channels-v0.2/22-02-PLAN.md` — migration 003 `agent_containers` shape; 22b's migration 004 mirrors it
- `.planning/phases/22-channels-v0.2/22-05-PLAN.md` — `/v1/agents/:id/start` handler shape; 22b extends it to spawn the log-watcher task

### Substrate code (authoritative for patterns)

- `api_server/src/api_server/services/runner_bridge.py` — `execute_persistent_*` helpers; the model for how 22b adds a log-watch helper
- `api_server/src/api_server/services/run_store.py` — CRUD conventions for `agent_containers`; new `agent_events` CRUD mirrors (see §`insert_pending_agent_container`, `write_agent_container_running`, `mark_agent_container_stopped`)
- `api_server/src/api_server/routes/agent_lifecycle.py` — `/start`, `/stop`, `/status`, `/channels/:cid/pair` handlers; 22b's `GET /v1/agents/:id/events` follows the canonical 9-step flow pattern used here
- `api_server/alembic/versions/003_agent_containers.py` — migration style, partial unique indexes, CHECK constraints; 22b's `004_agent_events` follows the same idiom
- `api_server/src/api_server/constants.py` — `ANONYMOUS_USER_ID` (Phase 19 MVP seam) used in D-15 auth
- `tools/run_recipe.py` — current runner; does NOT follow container logs today (confirmed grep). 22b adds the log-following mechanism separately in `runner_bridge` so the runner stays one-shot-focused.

### Recipe schema

- `recipes/hermes.yaml` §`persistent` + §`channels.telegram` — the template for how 22b's new `channels.telegram.event_log_regex` lands (same additive discipline as `ready_log_regex`)
- `recipes/picoclaw.yaml`, `recipes/nullclaw.yaml`, `recipes/nanobot.yaml`, `recipes/openclaw.yaml` — the other four recipes that get the same additive field (one regex per, populated by Spike 1)
- `docs/RECIPE-SCHEMA.md` if it exists at plan time (Phase 03 output) — canonical v0.1/v0.2 schema doc the new field extends

### Golden rules that shape the plan

- `/Users/fcavalcanti/dev/agent-playground/CLAUDE.md` §Golden rules — rules 1, 2, 5 all load-bearing on 22b (no mocks, dumb client, spike before plan)
- `memory/feedback_telegram_getupdates_is_single_consumer.md` — the observation that rules out "fix SC-03 by refining the getUpdates code"
- `memory/feedback_test_everything_before_planning.md` — Rule 5; why <spike_gate> exists
- `memory/feedback_dumb_client_no_mocks.md` — harness stays dumb, API owns event logic
- `memory/feedback_no_mocks_no_stubs.md` — spikes + execute tests hit real Docker + real Postgres

### Test harness (rewrite targets)

- `test/lib/telegram_harness.py` — gains `send-direct-and-read` (Gate A primary) and `send-telegram-and-watch-events` (Gate B secondary) subcommands per D-18. Legacy `send-and-wait` (getUpdates-based) deleted.
- `test/e2e_channels_v0_2.sh` — step 4 calls `send-direct-and-read` for the 15/15 SC-03 Gate A run; optional step 5 calls `send-telegram-and-watch-events` for Gate B; MATRIX unchanged.
- `test/smoke-api.sh` — style guide for the harness (`_pass/_fail/_skip`, `API_BASE`, jq assertions)

### MSV pattern (validation of direct_interface approach)

- `/Users/fcavalcanti/dev/meusecretariovirtual/messaging/activities/forward_to_agent.go` — MSV's canonical "send message to pod's localhost HTTP" pattern. `agentURL := fmt.Sprintf("http://localhost:%d/v1/chat/completions", input.Port)` + OpenAI-compatible body. Justifies D-20's `http_chat_completions` kind and D-21's openclaw/nanobot rows.
- `/Users/fcavalcanti/dev/meusecretariovirtual/messaging/activities/deliver_telegram.go` — MSV's Telegram send path (bot → user chat, valid Bot API usage). Template for Gate B's secondary harness subcommand.
- `/Users/fcavalcanti/dev/meusecretariovirtual/scripts/e2e-lifecycle.sh` — MSV e2e shape. Sends inference directly to pod's localhost HTTP, skips Telegram entirely for automated verification. Validates the overall "direct-interface-first, Telegram as separate plumbing" strategy.
- `/Users/fcavalcanti/dev/meusecretariovirtual/api/pkg/notify/telegram.go` — MSV's Bot API sendMessage wrapper. Bot→user sends are legal (automatable); user→bot is not, via Bot API.

### 22b spike evidence

- `.planning/phases/22b-agent-event-stream/22b-SPIKES/SPIKES-PLAN.md` — phase-scoped probe matrix
- `.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-01a-hermes.md` — hermes reply_sent regex + direct_interface proven + Bot API user-impersonation constraint documented

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`runner_bridge.execute_persistent_*` pattern** — shows how to bridge sync docker operations into async via `asyncio.to_thread` with semaphore + per-tag lock. 22b's log-watch helper borrows the `to_thread` pattern (for the iterator pump); NO image tag-lock needed (log-watch doesn't touch images); NO semaphore needed (watchers are long-lived, not short spikes).
- **`run_store.{insert_pending_agent_container, write_agent_container_running, mark_agent_container_stopped, fetch_running_container_for_agent}`** — CRUD style to replicate for `agent_events`: one function per state transition, asyncpg connection acquired per-call (Pitfall 4 — never hold across long await).
- **`crypto/age_cipher.py`** — NOT used for events (payload stores no secrets per D-06); listed so the planner explicitly knows we are NOT reaching for age here.
- **`models/agents.py`** — per-kind Pydantic response models pattern; 22b adds `models/events.py` following the same import + export discipline.
- **`middleware/correlation_id.py`** — request-scoped correlation IDs. Orthogonal to D-07's event correlation_id (which is send-side, embedded in bot text, extracted from container logs).
- **`ANONYMOUS_USER_ID` constant** — resolves to a stable UUID today; used in D-15.
- **Partial unique index pattern** — `ix_agent_containers_agent_instance_running PARTIAL UNIQUE WHERE status='running'` is the template for enforcing "one watcher per container" via app-state registry + DB-side UNIQUE backstop.

### Established Patterns

- **asyncpg + connection-per-scope** — Pitfall 4 in `agent_lifecycle.py::start_agent` docstring; every long await MUST be outside an `async with pool.acquire()`. 22b's long-poll handler releases the pool connection before awaiting the `asyncio.Event`, re-acquires only to fetch rows.
- **Redaction-everywhere** — `_redact_creds` helper in `agent_lifecycle.py`; every exception string goes through it before landing in the DB or response. Applies to 22b: events never get reply bodies, but any error message that might contain `AP_SYSADMIN_TOKEN` or Bearer tokens must redact.
- **Stripe-shape error envelopes** — `models/errors.py::make_error_envelope` + `_err` builder. 22b's new error codes: `CONCURRENT_POLL_LIMIT` (429), `EVENT_STREAM_UNAVAILABLE` (503 — watcher dead), `AGENT_NOT_FOUND` (existing), `UNAUTHORIZED` (existing).
- **Recipe additive-field discipline** — v0.2 candidate fields live in recipe YAML without breaking v0.1 loaders (recipe_summary projection ignores unknown keys). 22b's `event_log_regex` field lands in `channels.telegram`, not a new top-level section.

### Integration Points

- `/start` handler (`agent_lifecycle.py::start_agent` line 140) — **extends** to spawn the watcher task after `write_agent_container_running` (Step 8) and before returning response (Step 9). Registers task in `app.state.log_watchers`.
- `/stop` handler (`agent_lifecycle.py::stop_agent` line 443) — **extends** to cancel + drain the watcher task before `execute_persistent_stop`. Removes from registry.
- `main.py` lifespan — **extends** startup to re-attach watchers for rows where `container_status='running'`; **extends** shutdown to cancel all watchers.
- `main.py` app.state init — **adds** `log_watchers`, `event_poll_signals`, `event_poll_locks` dicts + their mutex (mirroring `image_tag_locks` + `locks_mutex` pattern).
- `tests/` — new `test_events_*.py` files under the Phase 22 conftest; spike artifacts for Spike 2/3/4/5 become the seed test cases.

</code_context>

<specifics>
## Specific Ideas

- **The harness has two surfaces, not one.** Gate A (`send-direct-and-read`) is short and fast: invoke the recipe's direct_interface, read reply, done. Gate B (`send-telegram-and-watch-events`) is the event-stream path: bot→self sendMessage + long-poll for the reply_sent row. The getUpdates ritual is gone entirely.
- **The Telegram Bot API constraint is permanent.** `sendMessage` with a bot token sends AS the bot — no user-impersonation primitive exists in the Bot API. Real user→bot automation requires MTProto (Client API) with a second Telegram user account; see <deferred>. Gate C (manual human verification once per release) is a permanent part of the SC-03 story, not a transient gap.
- **`AP_SYSADMIN_TOKEN` is per-laptop state**, not a deploy secret. Mirrors `AP_CHANNEL_MASTER_KEY` — exported in shell before `docker compose up`, NEVER committed to `.env*` files (CLAUDE.md: "never modify .env files without explicit user permission").
- **The API is designed so the frontend could subscribe later** — long-poll today, SSE/WebSocket behind the same endpoint later. Response schema stable enough that a future React `useEventStream(agentId)` hook consumes it unchanged.
- **Reply text is deliberately absent** from the event payload. If ops needs to correlate a specific user complaint later, the source of truth is `docker logs <cid>` (still there for running containers) or Telegram's own message history. The API's durable record is structural metadata only.
- **Every recipe already has a direct programmatic surface** — this is the golden observation spike 01a surfaced. The Agent Playground catalog is CLI-first; that's the test automation path. The D-21 mapping exploits what's already there rather than forcing a new convention.

</specifics>

<deferred>
## Deferred Ideas

### Deferred to 22b+1 (observability v2)

- **Rich kinds** — `llm_call` (upstream model + model + tokens in/out), `token_usage` (cumulative per conversation), `pair_code_issued` (openclaw-specific), `webhook_inbound` (future webhook-mode agents). Each needs agent-side emission or a matching log regex; defer until the minimal SC-03 gate is green.
- **Cross-channel support** — `channels.discord.event_log_regex`, `channels.slack.event_log_regex`, `channels.webhook.event_log_regex`. Matches the 22-CONTEXT.md "Discord/Slack/WhatsApp/Matrix/Signal out of scope in v0.2" boundary.
- **Agent-side HTTP emit** — each container POSTs events to `/internal/events`. Needed for events that don't hit the container's own stdout (internal state, config changes, retry loops).
- **Frontend event viewer panel** — a `recent activity` card on the agent detail page streaming from the same endpoint. Out of scope for 22b.
- **TTL/purge job** — periodic task that deletes `agent_events` where the owning `agent_containers.stopped_at` > 7 days. ON DELETE CASCADE covers the delete-container case; purge-job is a separate post-MVP concern.

### Reviewed Todos (not folded)

None — no todos were surfaced as relevant to 22b at discussion time.

### Not part of 22b (would be its own phase)

- **MTProto user-impersonation harness** — telethon or pyrogram auth'd as a throwaway Telegram user account, used to *actually* send DMs user→bot in automated fashion. Would close Gate C's manual step. Requires: dedicated phone number + Telegram api_id/api_hash registration + session-file persistence + careful secret management. Estimated ~1 wave of work; deferred to post-22b once Gates A+B ship and the need is concrete.
- **WebSocket/SSE live-feed** — deferred until a frontend need makes the long-poll shape insufficient.
- **Multi-tenant rate limits at the app level** — current middleware already has per-IP rate limiting; event-specific limits fold in only if abuse is observed.

</deferred>

---

*Phase: 22b-agent-event-stream*
*Context gathered: 2026-04-18*
*Revised: 2026-04-18 post-spike-01a — `direct_interface` primary path added (D-19..D-22), D-18 split into two subcommands, spike gate expanded with spike 06.*
*Pre-planning gate: spike 01a ✅; spike 06 + 02 + 03 + 04 + 05 MUST return PASS or documented FLAG before `/gsd-plan-phase 22b-agent-event-stream`. Spikes 01b-01e (Gate B regex per recipe) required before `/gsd-execute-phase` but not for planning.*
