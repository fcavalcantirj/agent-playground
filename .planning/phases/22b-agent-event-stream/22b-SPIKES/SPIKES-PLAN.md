# Phase 22b — Spike Plan

**Purpose:** resolve every gray area from 22b-CONTEXT.md before the planner consumes the file. Per Golden Rule #5.

**Status:** All 10 spikes executed with verdict. 8 PASS, 2 PASS_WITH_FLAG (nullclaw + openclaw use `event_source_fallback` instead of docker-logs-scrape). Architecture gate + Gate B both complete.

---

## Probe matrix

| # | Gray area | Validates | Status |
|---|---|---|---|
| 01a | Per-recipe reply_sent log format — **hermes** | regex authorable from real log lines | ✅ **PASS w/ pivot** (spike-01a-hermes.md) |
| 01b | Per-recipe reply_sent log format — **picoclaw** | same | ✅ **PASS** (spike-01b-picoclaw.md) |
| 01c | Per-recipe reply_sent log format — **nullclaw** | same | ⚠ **PASS_WITH_FLAG** (spike-01c-nullclaw.md — docker_exec_poll fallback) |
| 01d | Per-recipe reply_sent log format — **nanobot** | same | ✅ **PASS** (spike-01d-nanobot.md) |
| 01e | Per-recipe reply_sent log format — **openclaw** | same + wildcard allowlist, direct docker run bypass | ⚠ **PASS_WITH_FLAG** (spike-01e-openclaw.md — file_tail_in_container fallback on session JSONL) |
| 02 | Docker SDK logs(follow=True) backpressure under flood | no priority inversion; drop path fires cleanly | ✅ **PASS** (spike-02-docker-sdk-backpressure.md) |
| 03 | Graceful watcher teardown on docker rm -f | iterator ends cleanly; no dangling asyncio tasks | ✅ **PASS** (spike-03-watcher-teardown.md) |
| 04 | Postgres write batching under flood | chosen batch size + throughput verdict | ✅ **PASS — 12.4x speedup** (spike-04-postgres-batching.md) |
| 05 | seq ordering under concurrent writes | 4-way race serializes; gap-free; no UV/deadlock | ✅ **PASS** (spike-05-seq-ordering.md) |
| 06 | Per-recipe direct_interface | each recipe's CLI/HTTP surface for programmatic invocation | ✅ **PASS 4/4** (spike-06-direct-interface.md) |

---

## Key findings

- **Golden finding (spike 01a):** every recipe has a direct programmatic surface beyond Telegram. `hermes chat -q -Q`, `picoclaw agent -m`, `nullclaw agent -m | gateway`, `nanobot agent | serve`, `openclaw` via `/v1/chat/completions` (MSV pattern). SC-03 agent-correctness becomes automatable via these surfaces.
- **Gotcha (spike 01a):** Telegram Bot API `sendMessage` sends AS the bot. There is NO user-impersonation primitive. Bot-API-automated user→bot DMs are impossible; MTProto (Client API) with a second Telegram user account is required for real Telegram round-trip automation. **Blocks spikes 01b-01e from automation** — they now need human-in-loop DM typing.
- **Architecture pivot (spike 01a):** direct_interface is primary SC-03 path; log-scrape + long-poll is secondary observability substrate. Documented in CONTEXT.md D-19..D-22.
- **Spike 02:** docker SDK `logs(follow=True)` iterator has NO priority inversion — container kept writing 20k lines/8s under full-drop backpressure. RSS/FD delta 0 KB/0 FDs. Drop-path fires cleanly.
- **Spike 03:** `docker rm -f` causes clean iterator end in <270ms, no `Task.cancel()` needed, zero dangling asyncio tasks.
- **Spike 04:** batched INSERT (100/txn) delivers **12.4× speedup** over per-row (25,722/s vs 2,076/s). Well above the >2× bar.
- **Spike 05:** `pg_advisory_xact_lock(hashtext(agent_id::text))` serializes 4-way concurrent writers on one agent_container → 0 UniqueViolations, 0 deadlocks, gap-free seqs. **This revises D-16** — advisory lock replaces `FOR UPDATE` because Postgres rejects FOR UPDATE with aggregates.
- **Spike 06:** all 4 remaining recipes (picoclaw/nullclaw/nanobot/openclaw) invoked their CLI via existing `modes.smoke.argv`; agent produced real `filtered_payload` text with exit_code 0. Direct interface PROVEN for 5/5 recipes.

---

## Execution order — history

- **Pre-01a:** hermes → picoclaw → nullclaw → nanobot → openclaw (original spike 1 only)
- **Post-01a pivot:** re-open CONTEXT.md with direct_interface (done) → spike 06 → spikes 02-05 → spikes 01b-01e
- **Actual execution (2026-04-18):**
  0. ✅ CONTEXT.md revised with D-19..D-22 and revised D-16/D-18
  1. ✅ Spike 06 — direct_interface proven 4/4 remaining recipes (via smoke)
  2. ✅ Spike 02 — backpressure PASS
  3. ✅ Spike 03 — teardown PASS
  4. ✅ Spike 04 — batching PASS 12.4×
  5. ✅ Spike 05 — seq ordering PASS under adversarial 4-way race
  6. ✅ Spike 01b (picoclaw) — structured reply event captured with bonus `response_text`
  7. ⚠ Spike 01c (nullclaw) — FLAG: docker logs barren; needs `event_source_fallback` via docker exec poll
  8. ✅ Spike 01d (nanobot) — rich ISO-timestamped log format captured
  9. ⚠ Spike 01e (openclaw) — PASS_WITH_FLAG: session JSONL is authoritative (`file_tail_in_container` fallback); round-trip captured with correlation id echoed in bot reply

## Architecture-blocking gate — COMPLETE ✅

All 6 architecture-blocking spikes (01a, 02, 03, 04, 05, 06) have PASSed. `/gsd-plan-phase 22b-agent-event-stream` is unblocked per CONTEXT.md §Spike exit condition.

## Gate-B status — COMPLETE ✅

- **3 of 5 recipes use docker-logs-scrape:** hermes (01a), picoclaw (01b), nanobot (01d) — `event_log_regex` populated in each recipe YAML.
- **2 of 5 recipes use `event_source_fallback`:** nullclaw (01c → `docker_exec_poll` on `nullclaw history show --json`), openclaw (01e → `file_tail_in_container` on session JSONL at `/home/node/.openclaw/agents/main/sessions/<session_id>.jsonl`).
- **All 5 recipes have a working path** for capturing reply_sent events. Watcher service must support three source kinds: `docker_logs_stream`, `docker_exec_poll`, `file_tail_in_container`.

## 2nd-order architecture findings (feed back to CONTEXT.md)

- **D-01 revision needed:** docker logs is primary source, but recipes MAY declare `event_source_fallback` for alternative paths. **40% of the catalog uses a fallback** — this is architecturally required, not edge case. Propose D-23: `event_source_fallback` is a first-class recipe field; watcher supports enum kinds `docker_logs_stream | docker_exec_poll | file_tail_in_container`.
- **D-19 (direct_interface) openclaw row validated** — spike 06 smoke PASSed (Anthropic direct).
- **Openclaw recipe has a SEPARATE gap** (not spike-01e scope): the `/v1/agents/:id/start` handler injects bearer as `OPENROUTER_API_KEY` env regardless of provider. For Anthropic-direct openclaw, the env var must be `ANTHROPIC_API_KEY`. Spike 01e unblocked by bypassing `/start` via direct `docker run`. Proper fix: recipe `process_env.api_key` should support per-provider branch, or the runner should read the recipe's `provider_compat` + model prefix to pick the right env name.

---
