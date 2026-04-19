---
phase: 22b-agent-event-stream
verified: 2026-04-19T03:00:00Z
status: gaps_found
score: 14/17 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps:
  - truth: "openclaw direct_interface invocation works against the persistent gateway-mode container"
    status: failed
    reason: "openclaw recipe declares direct_interface kind=http_chat_completions on port 18000 (sourced from MSV forward_to_agent.go), but the persistent /v1/agents/:id/start runs `openclaw gateway` which exposes only the channel-router port 18789 — not 18000 inference HTTP. Additionally the openclaw `agent --local` CLI requires an auth setup the gateway didn't perform. The openrouter plugin path is also upstream-blocked. Gate run #2 produced 0/3 PASS for openclaw Gate A — entire Gate A score is 12/15 instead of the claimed 15/15."
    artifacts:
      - path: "recipes/openclaw.yaml"
        issue: "direct_interface block declares port 18000 + http_chat_completions kind that does not match the running container topology"
      - path: "test/e2e_channels_v0_2.sh"
        issue: "MATRIX gained `skip_smoke` flag (commit bdd4f49) to keep the openclaw lane alive but openclaw still ASSERT_FAILs on Gate A"
    missing:
      - "Working openclaw direct_interface that targets the gateway port (18789) and the openclaw component reachable through it, OR"
      - "Recipe-level decision to switch openclaw direct_interface to docker_exec_cli (e.g. `openclaw infer model run --local`) with whatever auth pre-step the persistent container already performs, OR"
      - "Formal documentation of openclaw as permanently excluded from Gate A automation (Gate C only) with the recipe carrying a `direct_interface_excluded: <reason>` annotation"

  - truth: "Gate B verifies that a real Telegram delivery produced a reply_sent event in agent_events (5/5 recipes)"
    status: failed
    reason: "Gate run #2 returned 0/5 Gate B PASS. Root cause is a design flaw, not an infrastructure bug: the harness's `send-telegram-and-watch-events` subcommand uses bot-self sendMessage to inject a probe, but every recipe ships `channels.telegram.allowFrom: [tg:152099202]` (only the human user's chat ID is permitted). The bot's own outbound messages never trigger the agent, so no reply_sent events flow. The harness comment itself acknowledges 'This does NOT prove a user→bot round-trip — that's Gate C.' Gate B was implemented as a proxy that requires Gate C to actually validate end-to-end."
    artifacts:
      - path: "test/lib/agent_harness.py"
        issue: "Lines 109-111 explicitly document that bot-self sendMessage cannot prove user→bot round-trip — meaning Gate B's mechanism is structurally inadequate for its own success criterion"
      - path: "e2e-report.json"
        issue: "All 5 Gate B entries return verdict=FAIL with error='no matching reply_sent event in window'"
      - path: "recipes/*.yaml channels.telegram.allowFrom"
        issue: "Every recipe filters bot-self messages — Gate B's mechanism cannot pass without disabling the security guard or impersonating a real user"
    missing:
      - "Gate B redesign that does NOT depend on bot-self impersonation (e.g. MTProto user-impersonation harness or a recipe-side pair-mode that whitelists the bot for the duration of the probe), OR"
      - "Formal demotion of Gate B to 'Gate C only' status — i.e. SC-03 success criterion drops the 5/5 Gate B requirement and relies on Gate A + Gate C exclusively. This matches D-18a's 'Gate C is permanent part of SC-03 story, not a transient gap' framing."

  - truth: "Recipe lint schema validates the new direct_interface and event_log_regex fields"
    status: failed
    reason: "Plan 22b-06 added `direct_interface` (top-level) and `event_log_regex` (under channels.telegram) to all 5 recipes, but the canonical recipe schemas at `agents/schemas/recipe.schema.json` and `api/internal/recipes/schema/recipe.schema.json` do not declare either field. Strict-mode lint (additionalProperties=false or equivalent) on these recipes will fail. The user prompt explicitly notes `test_lint.py::test_lint_valid_recipe` fails."
    artifacts:
      - path: "agents/schemas/recipe.schema.json"
        issue: "Does not declare direct_interface or event_log_regex; recipes are now ahead of the schema contract"
      - path: "api/internal/recipes/schema/recipe.schema.json"
        issue: "Same — Go-side recipe schema is stale relative to recipe YAML"
      - path: "tools/tests/test_lint.py"
        issue: "minimal_valid_recipe fixture or schema validator rejects the new fields per user-reported failure"
    missing:
      - "Schema extension(s) declaring direct_interface (with kind enum {docker_exec_cli, http_chat_completions} + spec subschema) and channels.telegram.event_log_regex (4 keys: reply_sent, reply_failed, agent_ready, agent_error)"
      - "Updated test_lint test fixtures to validate that real recipes pass the strict schema"

deferred:
  - truth: "Real user→bot round-trip validation for SC-03"
    addressed_in: "Gate C (per-release manual checklist)"
    evidence: "test/sc03-gate-c.md exists and documents the manual user-in-the-loop checklist; D-18a explicitly defines Gate C as the per-release manual gate (not a per-commit blocker). Phase 22b CONTEXT D-18a: 'Gate A + Gate B green; Gate C is a release-time checklist, not a per-commit gate.' MTProto user-impersonation harness is explicitly DEFERRED per <deferred>."
human_verification:
  - test: "Run the Gate C manual checklist at test/sc03-gate-c.md against all 5 recipes"
    expected: "Each recipe receives a real user DM, agent replies, sign-off recorded"
    why_human: "Telegram Bot API cannot impersonate users; per-release human-in-the-loop validation is the documented path (CONTEXT D-18a, deferred MTProto)"
  - test: "Decide governance for openclaw — exclude permanently from Gate A or pursue gateway-mode direct_interface fix in 22b.1"
    expected: "User chooses path; planner consumes choice into 22b.1 PLAN"
    why_human: "Architectural decision about scope: include openclaw in automated SC-03 or treat it as Gate-C-only"
  - test: "Decide Gate B scope — redesign without bot-self or formally demote to Gate-C-only"
    expected: "User chooses path; planner consumes choice into 22b.1 PLAN"
    why_human: "Gate B's mechanism is structurally inadequate; remediation requires a scope decision (MTProto vs allowlist relaxation vs gate retirement)"
---

# Phase 22b: agent-event-stream Verification Report

**Phase Goal:** Replace the Phase 22a getUpdates-based SC-03 gate with a durable agent event stream — `agent_events` table + watcher + `GET /v1/agents/:id/events` long-poll + harness rewrite that uses the event stream instead of Telegram getUpdates. Must unblock SC-03.
**Verified:** 2026-04-19T03:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 1  | docker-py 7.x dependency installed and importable in api_server | VERIFIED | `api_server/pyproject.toml` lists `docker>=7.0,<8`; commit 2d63b35 added it to Dockerfile too |
| 2  | 5 spike-derived event-log fixtures committed under api_server/tests/fixtures/event_log_samples/ | VERIFIED | All 5 files exist with byte counts in 22b-01 SUMMARY |
| 3  | conftest exposes docker_client + running_alpine_container + event_log_samples_dir fixtures | VERIFIED | `pytest --fixtures` confirms all 3 collected (22b-01 V5) |
| 4  | openclaw `/start` with anthropic model injects ANTHROPIC_API_KEY (not OPENROUTER) | VERIFIED | `_resolve_api_key_var` + `_detect_provider` in agent_lifecycle.py; 10 unit tests PASS (22b-01) |
| 5  | Migration 004_agent_events creates agent_events table with CHECK + UNIQUE + CASCADE FK | VERIFIED | `004_agent_events.py` exists with all DDL; 4 schema tests PASS (22b-02) |
| 6  | Per-kind Pydantic payloads (4 classes) reject extra fields (D-06 — no reply_text/body) | VERIFIED | `models/events.py` has 4 classes with `ConfigDict(extra='forbid')`; 10 payload tests PASS (22b-02) |
| 7  | event_store insert_agent_event uses pg_advisory_xact_lock for gap-free per-agent seqs | VERIFIED | `event_store.py` uses advisory lock; spike-05 reproducer (4 writers × 50 rows) PASS in 0.72s |
| 8  | event_store insert_agent_events_batch achieves ≥5x speedup vs per-row | VERIFIED | spike-04 reproducer PASS (originally measured 12.4x) |
| 9  | fetch_events_after_seq binds kinds via $3::text[] (V13 — never interpolated) | VERIFIED | grep returns 0 string interpolation; 4 store tests PASS (22b-02) |
| 10 | watcher_service exposes EventSource Protocol + 3 concrete classes + run_watcher | VERIFIED | All 4 classes + run_watcher present; 12-16 integration tests PASS (22b-03) |
| 11 | _select_source dispatches on recipe.channels.<channel>.event_source_fallback.kind (D-23) | VERIFIED | watcher_service.py implements 3-way dispatch; default = DockerLogsStreamSource |
| 12 | Lifespan re-attach spawns watchers for container_status='running' rows on API boot (D-11) | VERIFIED | main.py implements re-attach with Docker-existence probe + mark_stopped degradation; 2 reattach tests PASS (22b-04) |
| 13 | POST /v1/agents/:id/start spawns run_watcher AFTER write_agent_container_running | VERIFIED | agent_lifecycle.py line 490 `asyncio.create_task(run_watcher(...))` after Step 8; ordering proof in 22b-04 SUMMARY |
| 14 | POST /v1/agents/:id/stop drains watcher BEFORE execute_persistent_stop (spike-03 ordering) | VERIFIED | line 593 `_wstop.set()` precedes line 607 `execute_persistent_stop()` |
| 15 | GET /v1/agents/:id/events long-poll route with Bearer + sysadmin bypass + 429 + V13 kinds | VERIFIED | agent_events.py 244 lines; 16 tests PASS (10 auth + 6 contract); long-poll wall-times 1.02s timeout, 0.52s signal-wake |
| 16 | All 5 recipes declare direct_interface block per D-21 mapping | VERIFIED (partial — see Truth 17) | `grep -c "^direct_interface:"` returns 1 for each of hermes/picoclaw/nullclaw/nanobot/openclaw |
| 17 | SC-03 Gate A 15/15 + Gate B 5/5 PASS — phase exit gate | FAILED | Gate run #2 (e2e-report.json): Gate A **12/15** (openclaw 0/3), Gate B **0/5** (bot-self design flaw). See gaps section. |
| 18 | Recipe lint schema validates new direct_interface + event_log_regex fields | FAILED | agents/schemas/recipe.schema.json does NOT declare these fields; user-reported test_lint.py failure confirms |
| 19 | Hermes recipe gains event_log_regex block (was missing — spike-01a captured the canonical sequence) | VERIFIED | hermes.yaml channels.telegram.event_log_regex has 4 keys (reply_sent, inbound_message, response_ready, agent_error) per 22b-06 SUMMARY |
| 20 | Legacy test/lib/telegram_harness.py send-and-wait subcommand is deleted (D-18) | VERIFIED | telegram_harness.py is now a 60-line deprecation shim returning exit 3 with actionable error |
| 21 | test/sc03-gate-c.md documents manual user-in-the-loop checklist (Gate C) | VERIFIED | File exists, 6568 bytes |

**Score:** 17/20 truths verified (3 failed: openclaw Gate A, Gate B mechanism, lint schema)

Note: Score is 14/17 for the **must-haves** (excluding the deferred / human-only Gate C). The 3 gaps fail must-haves that have remediation paths.

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Real user→bot round-trip validation | Gate C (per-release manual) | test/sc03-gate-c.md authored; CONTEXT D-18a explicitly designates Gate C as the permanent per-release human gate; MTProto harness deferred per <deferred> section |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `api_server/alembic/versions/004_agent_events.py` | agent_events DDL | VERIFIED | 4611 bytes; CHECK + UNIQUE + CASCADE + descending index all present |
| `api_server/src/api_server/models/events.py` | per-kind Pydantic payloads | VERIFIED | 5334 bytes; 4 payload classes + KIND_TO_PAYLOAD + AgentEvent + AgentEventsResponse |
| `api_server/src/api_server/services/event_store.py` | asyncpg event repo | VERIFIED | 7556 bytes; 3 functions; advisory lock + executemany + V13 binding |
| `api_server/src/api_server/services/watcher_service.py` | multi-source watcher | VERIFIED | 25761 bytes; 4 classes (Protocol + 3 concrete) + run_watcher + _select_source + helpers |
| `api_server/src/api_server/routes/agent_events.py` | long-poll route | VERIFIED | 8521 bytes; GET handler + 9-step flow + 4 pool.acquire() scopes |
| `api_server/src/api_server/main.py` (modified) | lifespan + app.state init + router mount | VERIFIED | 3 dicts + re-attach SQL + shutdown drain + agent_events_route mount all present |
| `api_server/src/api_server/routes/agent_lifecycle.py` (modified) | /start spawn + /stop drain | VERIFIED | line 490 spawn, line 593 drain |
| `api_server/src/api_server/constants.py` (modified) | AP_SYSADMIN_TOKEN_ENV | VERIFIED | 3 references in module |
| `api_server/src/api_server/models/errors.py` (modified) | CONCURRENT_POLL_LIMIT + EVENT_STREAM_UNAVAILABLE | VERIFIED | 2 constants + 2 _CODE_TO_TYPE mappings present |
| `recipes/{hermes,picoclaw,nullclaw,nanobot,openclaw}.yaml` | direct_interface blocks | VERIFIED (presence) / FAILED (correctness) | All 5 have direct_interface; openclaw block targets a non-listening port → 0/3 Gate A PASS |
| `test/lib/agent_harness.py` | 2 subcommands | VERIFIED | 451 lines, send-direct-and-read + send-telegram-and-watch-events both present |
| `test/lib/telegram_harness.py` | deprecation shim | VERIFIED | 60 lines, returns exit 3 on legacy subcommands |
| `test/e2e_channels_v0_2.sh` | Step 4 (Gate A) + Step 5 (Gate B) orchestration | VERIFIED | 12454 bytes; 285 lines |
| `test/sc03-gate-c.md` | manual checklist | VERIFIED | 6568 bytes |
| `e2e-report.json` | gate run output | VERIFIED (existence) / DOCUMENTS FAILURE | 268 lines; 12/15 Gate A + 0/5 Gate B |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| agent_lifecycle.py::start_agent | watcher_service.py::run_watcher | asyncio.create_task(run_watcher(...)) after Step 8 | WIRED | grep returns 1 match at line 490 |
| agent_lifecycle.py::stop_agent | app.state.log_watchers | _wstop.set() + asyncio.wait_for | WIRED | grep returns 1 match at line 593; ordering precedes execute_persistent_stop at 607 |
| main.py::lifespan startup | run_store / agent_containers | SELECT WHERE container_status='running' | WIRED | grep returns 1 match; mark_agent_container_stopped fallback for missing containers (2 matches) |
| agent_events.py::get_events | event_store.py::fetch_events_after_seq | two DB scopes flanking asyncio.wait_for(signal.wait()) | WIRED | 4 pool.acquire() occurrences (1 ownership + 2 fetch + 1 docstring) |
| agent_events.py::get_events | app.state.event_poll_locks | _get_poll_lock + 429 if .locked() | WIRED | CONCURRENT_POLL_LIMIT grep returns 2 matches |
| agent_events.py::get_events | app.state.event_poll_signals | signal.clear() then await signal.wait() | WIRED | clear-before-fetch ordering proof exits 0 |
| main.py | agent_events router | app.include_router prefix='/v1' | WIRED | line 233 |
| agent_harness.py::cmd_send_direct_and_read | recipes/*.yaml::direct_interface | dispatches on kind (docker_exec_cli OR http_chat_completions) | WIRED (4/5) | 4 recipes invocable; openclaw direct_interface targets unreachable port → BROKEN |
| agent_harness.py::cmd_send_telegram_and_watch_events | GET /v1/agents/:id/events | long-polls with AP_SYSADMIN_TOKEN Bearer | WIRED | route hits API; pre-query succeeds; allowFrom guard blocks the bot-self message → no event flows |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| event_store.fetch_events_after_seq | rows | live PG17 agent_events table | YES (verified by 16 long-poll integration tests) | FLOWING |
| watcher_service.run_watcher producer | matched lines | DockerLogsStreamSource (3 recipes) / DockerExecPollSource (nullclaw) / FileTailInContainerSource (openclaw) | YES (12 watcher integration tests against alpine + 4 backpressure/teardown api_integration tests PASS) | FLOWING |
| agent_events.py::get_events response | events array | scope-2 fetch_events_after_seq after signal.wait | YES (test_long_poll_signal_wake measured 0.52s wake + INSERT round-trip) | FLOWING |
| agent_harness send-direct-and-read | reply_text | docker exec subprocess stdout / HTTP response body | YES for hermes/picoclaw/nullclaw/nanobot (gate run shows real reply text); NO for openclaw | HOLLOW_PROP (openclaw only) |
| agent_harness send-telegram-and-watch-events | reply_sent_event | GET /v1/agents/:id/events long-poll | NO (allowFrom guard blocks bot-self trigger; 0/5 events flow) | DISCONNECTED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| All 5 recipes have direct_interface block | `for r in hermes picoclaw nullclaw nanobot openclaw; do grep -c "^direct_interface:" recipes/$r.yaml; done` | 1/1/1/1/1 | PASS |
| event_store imports cleanly | `python -c "from api_server.services.event_store import insert_agent_event, insert_agent_events_batch, fetch_events_after_seq"` | exit 0 | PASS (per 22b-02 V2) |
| models.events imports cleanly | `python -c "from api_server.models.events import VALID_KINDS, KIND_TO_PAYLOAD, AgentEventsResponse"` | exit 0 | PASS (per 22b-02 V2) |
| watcher_service imports cleanly | `python -c "import api_server.services.watcher_service"` | exit 0 | PASS (per 22b-03 V1) |
| /v1/agents/:id/events route registered | `python -c "from api_server.main import create_app; print(any('/agents/' in r.path and '/events' in r.path for r in create_app().routes))"` | True | PASS (per 22b-05 V3) |
| Live SC-03 gate run | `bash test/e2e_channels_v0_2.sh` | 12/15 Gate A + 0/5 Gate B → e2e-report.json | FAIL (intent of phase exit gate) |
| Recipe schema validates real recipes | `pytest tools/tests/test_lint.py::test_lint_valid_recipe` | reported failure by user | FAIL |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| SC-03-GATE-A | 22b-01, 22b-05, 22b-06 | Direct_interface 15/15 PASS via primary harness subcommand | BLOCKED | Gate run shows 12/15; openclaw 0/3 due to gateway-mode/port mismatch |
| SC-03-GATE-B | 22b-01, 22b-02, 22b-03, 22b-04, 22b-05, 22b-06 | reply_sent events recorded for each recipe after bot→self sendMessage probe (5/5) | BLOCKED | Gate run shows 0/5; design flaw: bot-self filtered by allowFrom |
| (Gate C) | 22b-06 | Manual user-in-the-loop verification, once per release | NEEDS HUMAN | test/sc03-gate-c.md exists; per-release execution is human duty |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| recipes/openclaw.yaml | direct_interface block | port 18000 declared but persistent gateway exposes 18789 only | Blocker | openclaw Gate A 0/3 PASS |
| test/lib/agent_harness.py | line 111 | Code comment acknowledges Gate B "does NOT prove a user→bot round-trip" | Blocker (for Gate B) | Gate B mechanism inadequate by its own admission |
| recipes/*.yaml | channels.telegram.allowFrom | Strict allowlist filters bot-self probe; structurally incompatible with Gate B's mechanism | Blocker (for Gate B) | 0/5 reply_sent events |
| test/e2e_channels_v0_2.sh | MATRIX skip_smoke flag | Iteration band-aid (commit bdd4f49) to keep openclaw lane alive | Warning | Hides openclaw failure as "skip" rather than addressing root cause |
| api_server/tools/Dockerfile.api | docker package | Required hardcoded dep ADD post-merge (commit 2d63b35); pyproject ↔ Dockerfile drift | Info | Caught & fixed during gate run |
| recipes/nanobot.yaml | duplicate category:PASS | Pre-existing DI-01 style; surfaced by 22b-04 lifespan eager-load (fixed in 051c1b2) | Info | Already fixed |
| agents/schemas/recipe.schema.json | (no entries for direct_interface / event_log_regex) | Schema lags recipe contract | Blocker | test_lint.py::test_lint_valid_recipe fails |

### Human Verification Required

#### 1. Gate C — Manual user-in-the-loop SC-03 verification

**Test:** Run the checklist at `test/sc03-gate-c.md` against all 5 recipes.
**Expected:** Each recipe receives a real user DM, agent replies via Telegram, sign-off recorded per recipe section.
**Why human:** Telegram Bot API cannot impersonate a user; per-release human-in-the-loop validation is documented as the authoritative path (CONTEXT D-18a). MTProto user-impersonation harness is explicitly DEFERRED.

#### 2. Decide governance for openclaw

**Test:** User chooses one of: (a) plan a 22b.1 sub-phase to make openclaw direct_interface work against gateway-mode (port 18789 + auth pre-step OR docker_exec_cli alternative), (b) document openclaw as permanently excluded from Gate A automation (Gate-C-only), (c) restructure recipe to expose port 18000 from the gateway.
**Expected:** Decision recorded in deferred-items.md or new 22b.1 PLAN.
**Why human:** Architectural scope decision; planner needs explicit user choice.

#### 3. Decide Gate B scope

**Test:** User chooses one of: (a) plan a 22b.1 sub-phase to redesign Gate B without bot-self impersonation (e.g. MTProto harness, per-recipe pair-mode allowlist relaxation, or test-harness-injected fake inbound via internal API), (b) formally demote Gate B to "Gate C only" — drop SC-03's 5/5 Gate B requirement and rely on Gate A + Gate C.
**Expected:** Decision recorded in 22b.1 PLAN or SC-03 success-criteria revision.
**Why human:** Gate B's mechanism is structurally inadequate; remediation requires a scope decision that affects the SC-03 contract. Per the user prompt, the chosen path is "Plan a 22b.1 sub-phase for openclaw + Gate B redesign" — this verification surfaces the decision points the planner consumes.

### Gaps Summary

The Phase 22b infrastructure substrate is **solid and demonstrably working**:

- Migration 004_agent_events lands cleanly; the table receives real rows under spike-04/05 reproducer load (gap-free seqs, ≥5x batching speedup).
- Per-kind Pydantic payloads programmatically enforce D-06 (no reply_text/body) at parse time.
- Multi-source watcher (D-23) handles all 3 source kinds with proven backpressure + teardown discipline.
- Lifespan re-attach + /start spawn + /stop drain are wired with correct ordering (spike-03 preserved).
- Long-poll route ships with full auth matrix (Bearer + sysadmin bypass + per-agent 429 + V13 kinds whitelist + Pitfall-4 two-DB-scope discipline) and 16 integration tests against real PG17.
- 4 of 5 recipe direct_interface invocations work end-to-end against real recipe containers via docker exec (hermes/picoclaw/nullclaw/nanobot — 12/15 Gate A PASS).

The phase **goal "unblock SC-03"** is **not achieved** because the SC-03 exit gate (Gate A 15/15 + Gate B 5/5) shows 12/15 + 0/5. The 3 gaps:

1. **openclaw direct_interface broken** against the persistent gateway-mode container — recipe declares port 18000 + http_chat_completions but gateway exposes only 18789, and `agent --local` requires unsetup auth. Recipe-side iteration (commits 5d73b7f, b672d48, bdd4f49) closed 4 of 5 recipes and added a `skip_smoke` band-aid for openclaw, but the underlying surface mismatch remains.
2. **Gate B mechanism is structurally inadequate** — bot-self sendMessage cannot bypass `channels.telegram.allowFrom`. The harness comment itself acknowledges this is a Gate C concern. Gate B cannot pass without either MTProto user-impersonation (deferred) or a recipe-level allowlist relaxation (security regression).
3. **Recipe lint schema lags the recipe contract** — direct_interface and event_log_regex are not declared in `agents/schemas/recipe.schema.json`; `test_lint.py::test_lint_valid_recipe` fails.

Per the user's explicit direction, these gaps are **planner inputs for sub-phase 22b.1** — the substrate is solid; sub-phase 22b.1 closes the openclaw + Gate B + lint schema items.

---

_Verified: 2026-04-19T03:00:00Z_
_Verifier: Claude (gsd-verifier)_
