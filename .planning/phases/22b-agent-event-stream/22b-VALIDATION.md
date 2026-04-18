---
phase: 22b
slug: agent-event-stream
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 22b — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (api_server) + bash harness (test/) |
| **Config file** | `api_server/pyproject.toml` (pytest config); `test/smoke-api.sh` pattern for e2e |
| **Quick run command** | `cd api_server && pytest -x tests/test_events_*.py tests/test_lifecycle.py -q` |
| **Full suite command** | `cd api_server && pytest -q && bash test/e2e_channels_v0_2.sh` |
| **Estimated runtime** | ~60s (quick) / ~6–8min (full with real Docker+PG via testcontainers) |

Golden Rule 1 applies — tests hit live Postgres 17 via dockertest/testcontainers and real Docker daemon. No mocks for the watcher, event store, or direct_interface invocation.

---

## Sampling Rate

- **After every task commit:** Run `pytest -x tests/test_events_<component>.py -q` (the file owning the task's changes)
- **After every plan wave:** Run quick suite (all 22b `test_events_*.py` + `test_lifecycle.py`)
- **Before `/gsd-verify-work`:** Full suite must be green; SC-03 Gate A 15/15 PASS + Gate B 5/5 PASS
- **Max feedback latency:** 60s for quick, 8min for full

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 22b-0X-YY | — | — | SC-03 Gate A/B | — | — | — | — | ❌ W0 | ⬜ pending |

*Populated by the planner. One row per task. Test file names follow the conventions below.*

**Expected test file map (planner will populate):**

- `api_server/tests/test_events_migration.py` — migration 004 schema, indexes, CHECK constraint (D-05)
- `api_server/tests/test_events_store.py` — `agent_events` CRUD, advisory-lock seq allocation (D-16 / spike 05)
- `api_server/tests/test_events_watcher_docker_logs.py` — `docker_logs_stream` source kind (hermes/picoclaw/nanobot)
- `api_server/tests/test_events_watcher_exec_poll.py` — `docker_exec_poll` source kind (nullclaw)
- `api_server/tests/test_events_watcher_file_tail.py` — `file_tail_in_container` source kind (openclaw)
- `api_server/tests/test_events_watcher_backpressure.py` — spike 02 reproducer (20k-line flood, queue-drop path)
- `api_server/tests/test_events_watcher_teardown.py` — spike 03 reproducer (`docker rm -f` iterator end, no dangling tasks)
- `api_server/tests/test_events_batching_perf.py` — spike 04 reproducer (batched vs per-row, assert ≥ 5× speedup as a guard)
- `api_server/tests/test_events_seq_concurrency.py` — spike 05 reproducer (4-way race, gap-free, 0 UV / 0 deadlocks)
- `api_server/tests/test_events_long_poll.py` — `GET /v1/agents/:id/events` contract (since_seq, kinds filter, timeout_s, 429 concurrent cap D-13)
- `api_server/tests/test_events_auth.py` — bearer + ownership + `AP_SYSADMIN_TOKEN` bypass (D-15)
- `api_server/tests/test_events_lifespan_reattach.py` — D-11 re-attach on startup
- `api_server/tests/test_lifecycle_env_by_provider.py` — openclaw env-var mapping (`ANTHROPIC_API_KEY` vs `OPENROUTER_API_KEY` per provider)
- `test/e2e_channels_v0_2.sh` step 4 — SC-03 Gate A: `send-direct-and-read` × 5 recipes × 3 rounds = 15/15
- `test/e2e_channels_v0_2.sh` step 5 — SC-03 Gate B: `send-telegram-and-watch-events` × 5 recipes = 5/5
- Manual `test/sc03-gate-c.md` checklist — Gate C user-in-the-loop (once per release)

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Add `docker>=7.1` to `api_server/pyproject.toml` (spike 02 validated the exact API)
- [ ] `api_server/tests/conftest.py` — shared fixtures for: `real_db` (PG17 via testcontainers), `real_docker` (docker client from-env), `running_agent_container` factory
- [ ] `api_server/tests/fixtures/event_log_samples/` — captured stdout snippets from spikes 01a-01e (feed the regex parsers)
- [ ] `test/lib/agent_harness.py` skeleton with two subcommand stubs (`send-direct-and-read`, `send-telegram-and-watch-events`)
- [ ] BusyBox `tail -F` line-buffering probe (see Known Landmines — openclaw)

**Existing infrastructure covers:** pytest runner, asyncio test harness, existing dockertest patterns in `api_server/tests/test_lifecycle.py`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SC-03 Gate C — real user→bot Telegram round-trip | SC-03 exit gate | Telegram Bot API cannot impersonate a user (spike 01a finding); MTProto harness is a future phase | `test/sc03-gate-c.md` checklist: for each of 5 recipes, (1) start via `/v1/agents/:id/start`, (2) human DMs bot with a unique token, (3) bot replies within 30s, (4) operator records token + ts + reply |
| Telegram bot→self `sendMessage` Gate B probe | SC-03 Gate B | Gate B is automatable via bot→self (legal Bot API use), but relies on Telegram infra availability | Harness runs `send-telegram-and-watch-events` against a known-good chat_id; if Telegram outages, re-run |

---

## Spike Evidence → Test Fixture Mapping

| Spike | Number | Fixture / Assertion |
|-------|--------|---------------------|
| 01a hermes | PASS_WITH_PIVOT | `fixtures/event_log_samples/hermes_reply_sent.log` — regex assertion |
| 01b picoclaw | PASS | `fixtures/event_log_samples/picoclaw_reply_sent.log` — regex assertion |
| 01c nullclaw | PASS_WITH_FLAG | `fixtures/event_log_samples/nullclaw_history.json` — `docker_exec_poll` parser fixture |
| 01d nanobot | PASS | `fixtures/event_log_samples/nanobot_reply_sent.log` — regex assertion (ISO timestamps) |
| 01e openclaw | PASS_WITH_FLAG | `fixtures/event_log_samples/openclaw_session.jsonl` — `file_tail_in_container` parser fixture |
| 02 backpressure | PASS (20k lines/8s, 0 KB/0 FD leak) | `test_events_watcher_backpressure` — threshold: container writes ≥ 10k lines while queue blocked, 0 FD leak after teardown |
| 03 teardown | PASS (<270ms iterator end) | `test_events_watcher_teardown` — threshold: iterator done within 2s of `docker rm -f`, `asyncio.all_tasks()` delta == 0 |
| 04 batching | PASS (12.4× speedup) | `test_events_batching_perf` — guard: batched ≥ 5× per-row (generous floor of empirical 12.4×) |
| 05 seq ordering | PASS (4-way race, 200 writes/130ms) | `test_events_seq_concurrency` — 4 concurrent writers × 50 rows, assert gap-free, 0 UV, 0 deadlock |
| 06 direct_interface | PASS 4/4 | `test_direct_interface_dispatch` — each recipe's direct_interface block produces expected argv/HTTP call shape |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (docker dep, conftest fixtures, event_log_samples directory, BusyBox probe)
- [ ] No watch-mode flags (all runs are one-shot)
- [ ] Feedback latency < 60s for quick suite, < 8min for full with real infra
- [ ] `nyquist_compliant: true` set in frontmatter after planner populates Per-Task Verification Map

**Approval:** pending
