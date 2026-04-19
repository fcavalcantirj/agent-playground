---
phase: 22b
plan: 08
subsystem: agent-event-stream / Wave-5 Gap-2 closure (SC-03 Gate B mechanism redesign)
tags: [api, fastapi, dev-only-route, sysadmin-auth, defense-in-depth, long-poll, signal-wake, real-pg-testcontainers, harness, e2e, gate-b, sc-03, gap-closure, deviation-rule-3, autonomous-true, tdd-true, spike-B]
one_liner: "POST /v1/agents/:id/events/inject-test-event (sysadmin-Bearer-only, AP_ENV != prod-only) writes a real reply_sent row via insert_agent_event() then signal.set()s the long-poll wake; 8 testcontainer-backed integration tests PASS; agent_harness send-injected-test-event-and-watch subcommand + e2e_channels_v0_2.sh Gate B rewire close SC-03 Gate B 5/5 alongside Gate A 15/15 (full SC-03 Gate A+B exit gate green for the first time, 2026-04-19 live run)."
requires:
  - Plan 22b-04 (lifecycle wiring: app.state.event_poll_signals dict + log-watcher registry; agent_lifecycle:494 watcher spawn pattern using container_row_id as agent_id slot)
  - Plan 22b-05 (GET /v1/agents/:id/events long-poll + AP_SYSADMIN_TOKEN auth + _err/_project helpers + URL-key-is-container-row-id convention)
  - Plan 22b-06 (agent_harness.py existing scaffolding; cmd_send_telegram_and_watch_events as the structural analog for the new subcommand; e2e_channels_v0_2.sh Gate B step structure)
  - Plan 22b-07 (Gap 1 closure: openclaw direct_interface fix → 12/15 → 15/15 Gate A baseline; e2e script always-inject channel inputs deviation; container_row_id surfaced in /start response)
  - Spike B 2026-04-19 (URL key contract: /v1/agents/{agent_id}/events* uses agent_containers.id, NOT agent_instances.id; insert_agent_event returns int seq, NOT dict; long-poll wake works in-process when both inject + long-poll URLs share the same key)
provides:
  - "api_server/src/api_server/routes/agent_events.py: POST /v1/agents/:id/events/inject-test-event handler exposed via separate inject_router (defense gate #1: not the same router as GET so main.py can env-conditionally include) + InjectTestEventBody (extra=forbid Pydantic body schema) + handler steps Bearer-parse → AP_SYSADMIN_TOKEN env-var match (defense gate #2; 404 not 403 — opaque) → kind whitelist → SELECT agent_containers WHERE id=$1 (URL-key-is-container-row-id) → insert_agent_event (real DB INSERT + advisory-lock seq alloc) → _get_poll_signal(state, agent_id).set() (in-process wake) → response with seq+container_row_id+correlation_id=test:+orig+ts"
  - "api_server/src/api_server/main.py: env-conditional include_router(inject_router) — only registered when settings.env != prod (T-22b-08-01 mitigation); structured log-line phase22b.inject_test_event.route_registered emits when included"
  - "api_server/tests/test_events_inject_test_event.py: 8 integration tests on real PG via testcontainers (no mocks; golden rule 1) covering full defense matrix (prod-404, sysadmin-200, missing-Bearer-401, wrong-Bearer-404-opaque, AP_SYSADMIN_TOKEN-unset-404, no-running-container-404, end-to-end signal-wake within 1s, double-inject seq advance); inline fixtures (sysadmin_env, dev_app_and_client, prod_app_and_client, seed_agent_instance, seed_running_container) — same per-test-file pattern as test_events_long_poll.py / test_events_auth.py"
  - "test/lib/agent_harness.py: cmd_send_injected_test_event_and_watch (third subcommand) — POST /inject-test-event then long-poll for the matching reply_sent event with correlation_id=test:+orig; legacy cmd_send_telegram_and_watch_events PRESERVED for AP_USE_LEGACY_GATE_B opt-in / prod fallback"
  - "test/e2e_channels_v0_2.sh: Gate B step rewired — extracts container_row_id from /start response (Spike B B2 — the events-router URL key is container_row_id), defaults to send-injected-test-event-and-watch, falls back to send-telegram-and-watch-events when AP_USE_LEGACY_GATE_B=1 set OR new subcommand unavailable (prod scenarios)"
  - "deploy/docker-compose.local.yml: AP_ENV=dev override (Rule 3 deviation; required to expose the inject route on a developer laptop running the prod-shaped compose stack)"
  - "e2e-report.json: live PASS-run capture (15/15 Gate A + 5/5 Gate B; full per-recipe wall times + per-Gate-B test correlation_id matches embedded in the JSON)"
affects:
  - "SC-03-GATE-B — gap 2 closed; mechanism redesigned from bot-self sendMessage (filtered by allowFrom) to sysadmin-only synthetic injection that exercises the same long-poll → INSERT → signal-wake → handler-fetch chain"
  - "SC-03 phase exit gate — Gate A 15/15 + Gate B 5/5 simultaneously PASS for the first time. Plans 22b-07 closed Gate A; 22b-09 closed lint; 22b-08 closes Gate B. The phase exit gate is now empirically green."
  - "Phase 22b/v0.2 milestone exit gate — the only remaining work to declare 22b done is the orchestrators STATE.md/ROADMAP.md update (delegated to the parent agent per the worktree merge protocol)."
  - "Local developer workflow — running bash test/e2e_channels_v0_2.sh against a local prod-shaped stack now requires AP_ENV=dev override (already in docker-compose.local.yml so it is automatic); the prod Hetzner deploy is unchanged (AP_ENV stays prod via docker-compose.prod.yml)"
tech-stack:
  added: []   # No new deps — handler reuses existing fastapi + pydantic + asyncpg primitives
  patterns:
    - "Two-router conditional include: defining inject_router as a SEPARATE APIRouter (not extending the existing GET-route router) lets main.py env-conditionally include only the dev-only one. Pattern is more durable than `if env != prod: route.add(...)` style because router definitions stay declarative + side-effect-free."
    - "Defense-in-depth two-gate authorization: gate #1 is route-not-registered-in-prod (FastAPI 404 fallback), gate #2 is AP_SYSADMIN_TOKEN env-var match in handler (404 not 403 — opaque). Either gate alone is enough; both together is golden-rule-1 belt-and-suspenders. Tests cover BOTH paths (prod-404 + sysadmin-token-unset-404)."
    - "Spike-B-derived URL-key contract enforcement: ALL events-router endpoints (GET + new POST) treat URL agent_id as agent_containers.id (container_row_id), NOT agent_instances.id. Step 4 of the inject handler does direct SELECT on agent_containers by PK; the seed_running_container fixture returns container_row_id FIRST in its (uuid, uuid) tuple to make the contract impossible to mis-use."
    - "Opaque-404 surface for sysadmin probes: a wrong-Bearer or absent-AP_SYSADMIN_TOKEN response is 404 AGENT_NOT_FOUND with the SAME shape as a route-not-registered 404. A probing attacker cannot distinguish 'route does not exist' from 'route exists but you do not have access' (T-22b-08-02)."
    - "Synthetic-event marker via correlation_id prefix: the inject handler prepends test: to the user-supplied correlation_id before INSERT. Future cleanup query is one-liner: DELETE FROM agent_events WHERE correlation_id LIKE 'test:%'."
    - "TDD discipline (RED → GREEN): the 8-test integration suite was committed BEFORE the route implementation; initial run showed 6/8 FAIL (route 404) + 2/8 accidental PASS (prod-404 + sysadmin-unset-404 via FastAPI default 404). Post-GREEN all 8 PASS for the right reason — the conditional include + the env-var gate now own those branches structurally."
    - "Real-PG testcontainers integration over mocks: handler uses real insert_agent_event (advisory-lock seq alloc, JSON encoding, real INSERT) and real _get_poll_signal.set() — same code path the watcher uses in production. test_inject_test_event_wakes_long_poll_within_1s asserts an end-to-end concurrent long-poll wakes within 3s of an inject. Golden rule 1 holds end-to-end."
    - "Live empirical verification (Task 2 Part C): bash test/e2e_channels_v0_2.sh against the live local stack — Gate A 15/15 + Gate B 5/5 PASS captured in committed e2e-report.json, with per-Gate-B correlation_id round-trip verified inline. Golden rule 5 satisfied."
key-files:
  created:
    - .planning/phases/22b-agent-event-stream/22b-08-SUMMARY.md
    - api_server/tests/test_events_inject_test_event.py
  modified:
    - api_server/src/api_server/routes/agent_events.py
    - api_server/src/api_server/main.py
    - test/lib/agent_harness.py
    - test/e2e_channels_v0_2.sh
    - deploy/docker-compose.local.yml
    - e2e-report.json
key-decisions:
  - "Path B (test-injection endpoint) over Path A (allowFrom relaxation) and Path C (formal Gate B demotion). Path A is a security regression — even gated behind AP_ENV=dev, it teaches the recipe schema that allowFrom can be bypassed at test time. Path C loses the long-poll integration coverage. Path B preserves real DB INSERT + real signal-wake + real long-poll cycle (golden rule 1 holds end-to-end) — only the trigger origin is synthetic, which is honest about what is being tested. Gate C remains the per-release manual gate for the FULL real-user-to-bot chain."
  - "Two-router architecture (inject_router separate from existing router) over single-router-with-decorator-condition. Conditional include in main.py is declarative, route definitions are side-effect-free, and prod-mode 404 happens at the FastAPI router-resolution layer (not inside any handler)."
  - "Defense-in-depth gate stack: prod returns 404 (route not registered) AND handler requires Bearer == AP_SYSADMIN_TOKEN env value (404 if either gate fails). Either gate alone is enough; both together survives a hypothetical future bug where a refactor accidentally registers the route in prod (the env-var gate then catches it) OR accidentally exposes the env-var (the conditional registration then catches it)."
  - "Opaque-404 surface for wrong-Bearer instead of 403 with reason. A 403 with error.message=Bearer mismatch would tell a probing attacker the route exists. A 404 with error.code=AGENT_NOT_FOUND is indistinguishable from a route-not-registered FastAPI 404. Mitigates T-22b-08-02 information-disclosure."
  - "Synthesize ts via datetime.now(timezone.utc) in the handler instead of SELECT-ing it back from Postgres. insert_agent_event returns the seq as a plain int, NOT a row dict (Spike B B1). Skipping the SELECT-back saves a round-trip; the synthesized ts is within microseconds of the actual Postgres now() because the INSERT is on a same-connection same-host transaction."
  - "URL-key contract enforced from the test fixture upward: seed_running_container returns (container_row_id, agent_instance_id) — container_row_id FIRST — so a destructure typo would fail loudly. The fixture's docstring + the field-order convention together prevent the same Spike B B2 mistake from recurring."
  - "AP_USE_LEGACY_GATE_B escape hatch in e2e_channels_v0_2.sh preserves the bot-self path for AP_ENV=prod scenarios (where the inject route is invisible) and explicit opt-in (e.g. someone debugging the legacy path's allowFrom interaction). Without the escape hatch the script would have NO Gate B option in prod."
  - "AP_ENV=dev override applied in docker-compose.local.yml (Rule 3 deviation), NOT in deploy/.env.prod or any committed env file. Per CLAUDE.md NEVER CHANGE .ENV WITHOUT EXPLICIT USER ASK, the env-file path was forbidden. The local-only docker-compose override file is the right place — it already carries user: root and host port mapping for dev-laptop scenarios."
patterns-established:
  - "Pattern: For any future dev-only route, use a SEPARATE APIRouter + env-conditional include_router in main.py. Decorator-level conditionals OR runtime 404-from-handler are both worse: the conditional include is structurally enforced + visible in the openapi.json diff between dev and prod builds."
  - "Pattern: For sysadmin-only routes, the auth gate is Bearer == os.environ.get(AP_SYSADMIN_TOKEN_ENV) with empty-string fallback. The empty-string fallback short-circuits when the env var is unset, preventing 'any Bearer matches empty token' bypass."
  - "Pattern: When a handler URL key has a contractual identity (e.g. this UUID is agent_containers.id, not agent_instances.id), document it in the handler comment AND in the test fixture docstring AND enforce it via fixture field ordering (return container_row_id FIRST so destructure typos are loud). Three layers of defense against the silent-wrong-key class of bug."
  - "Pattern: Test for the right reason. Some tests will PASS by accident pre-implementation (e.g. test_inject_test_event_prod_returns_404 PASSes against a missing route via FastAPI default 404). Re-running them post-implementation should still PASS, but for the right reason (the conditional include now owns the branch). Avoid deleting accidental-PASS tests during the RED → GREEN transition."
requirements-completed:
  - SC-03-GATE-B
metrics:
  duration_seconds: 1695
  duration_human: "~28m"
  tasks_completed_autonomously: 2
  tasks_committed_atomically: 5
  files_created: 2
  files_modified: 6
  commits: 5
  integration_tests_added: 8
  integration_tests_passing: 8
  prior_22b_test_regression_count: 0
  live_e2e_runs: 2
  gate_a_rounds_pass: 15
  gate_a_rounds_total: 15
  gate_b_rounds_pass: 5
  gate_b_rounds_total: 5
  gate_b_correlation_id_round_trips_verified: 5
  signal_wake_latency_ms: 440
  containers_leaked: 0
  completed: "2026-04-19"
---

# Phase 22b Plan 08: Gap 2 Closure — SC-03 Gate B Mechanism Redesign Summary

**Objective:** Close Gap 2 from `22b-VERIFICATION.md` (the bot-self
`sendMessage` path used by `cmd_send_telegram_and_watch_events` is
filtered by every recipe's `channels.telegram.allowFrom: [tg:152099202]`,
so no `reply_sent` event flows — Gate B 0/5) by introducing a sysadmin-
only test-injection endpoint that writes a real `agent_events` row
through the same `insert_agent_event` + `_get_poll_signal.set()` chain
the production watcher uses, then rewiring the harness + e2e script to
exercise it.

**Outcome:** Gap 2 CLOSED. Live full e2e run produced **SC-03 Gate A
15/15 PASS + Gate B 5/5 PASS** — the complete SC-03 exit gate green for
the first time, captured in committed `e2e-report.json`.

---

## Tasks Completed

| Task    | Name                                                                  | Commit    | Files                                                                                                |
| ------- | --------------------------------------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------- |
| 1-RED   | 8 failing integration tests for inject-test-event                     | `ea2093f` | `api_server/tests/test_events_inject_test_event.py` (NEW; 441 lines)                                 |
| 1-GREEN | Inject route + conditional include + 8 PASSING tests                  | `aecf3cb` | `api_server/src/api_server/routes/agent_events.py` (+218); `api_server/src/api_server/main.py` (+14) |
| 2-A+B   | agent_harness send-injected-test-event-and-watch + e2e Gate B rewire  | `74f50d8` | `test/lib/agent_harness.py` (+170); `test/e2e_channels_v0_2.sh` (+34/-12)                            |
| 2C-fix  | docker-compose.local.yml AP_ENV=dev override (Rule 3 deviation)       | `437dec4` | `deploy/docker-compose.local.yml` (+8)                                                               |
| 2C-cap  | Capture e2e-report.json from live SC-03 PASS run                      | `a3dad39` | `e2e-report.json` (+240/-14)                                                                         |

---

## Diffs (Highlights)

### `api_server/src/api_server/routes/agent_events.py` — new POST handler

```python
inject_router = APIRouter()


class InjectTestEventBody(BaseModel):
    model_config = {"extra": "forbid"}
    kind: str = Field(default="reply_sent", ...)
    correlation_id: str = Field(..., min_length=1, max_length=64, ...)
    chat_id: str = Field(..., min_length=1, max_length=64, ...)
    length_chars: int = Field(default=12, ge=0, le=10000, ...)


@inject_router.post(
    "/agents/{agent_id}/events/inject-test-event", status_code=200
)
async def inject_test_event(request, agent_id, body, authorization):
    # Step 1 — Bearer parse → 401
    # Step 2 — sysadmin gate (404 opaque on miss / unset)
    # Step 3 — kind whitelist → 400
    # Step 4 — Spike B B2: SELECT agent_containers WHERE id=$1 (URL key
    #          IS container_row_id, NOT agent_instance_id)
    # Step 5 — build payload {chat_id, length_chars, captured_at}
    # Step 6 — insert_agent_event (real INSERT, advisory-lock seq alloc;
    #          returns int, NOT dict — Spike B B1)
    # Step 7 — _get_poll_signal(state, agent_id).set() — wakes any concurrent
    #          long-poll on the SAME URL key
    # Step 8 — return {agent_id, agent_container_id, seq, kind,
    #          correlation_id="test:"+orig, ts, test_event:True}
```

### `api_server/src/api_server/main.py` — env-conditional include

```python
app.include_router(agent_events_route.router, prefix="/v1", tags=["agents"])
# Phase 22b-08: dev-only POST /v1/agents/:id/events/inject-test-event.
# Conditional include keeps the route INVISIBLE in prod (FastAPI 404
# for any path not registered).
if app.state.settings.env != "prod":
    app.include_router(
        agent_events_route.inject_router,
        prefix="/v1",
        tags=["agents", "dev-only"],
    )
    _log.info(
        "phase22b.inject_test_event.route_registered",
        extra={"env": app.state.settings.env},
    )
```

### `test/lib/agent_harness.py` — new subcommand (1 of 3)

```python
def cmd_send_injected_test_event_and_watch(args) -> int:
    corr = uuid.uuid4().hex[:4]
    inject_url = f"{args.api_base}/v1/agents/{args.agent_id}/events/inject-test-event"
    # 1. Pre-query: capture since_seq cursor
    # 2. POST inject body {kind, correlation_id, chat_id, length_chars}
    # 3. Long-poll GET /events?since_seq=N&kinds=reply_sent
    # 4. Verdict=PASS iff response contains reply_sent with
    #    correlation_id == "test:" + corr
```

### `test/e2e_channels_v0_2.sh` — Gate B step rewired

```bash
# Spike B B2: extract container_row_id from /start response (events-router
# URL key); AGENT_ID is agent_instance_id and would NOT wake the signal.
CONTAINER_ROW_ID=$(jq -r '.container_row_id // ""' <<<"$START")
if [[ -z "${AP_USE_LEGACY_GATE_B:-}" ]] && python3 test/lib/agent_harness.py \
     send-injected-test-event-and-watch --help >/dev/null 2>&1; then
  GATE_B_OUT=$(python3 test/lib/agent_harness.py send-injected-test-event-and-watch \
    --api-base "$API_BASE" --agent-id "$CONTAINER_ROW_ID" \
    --bearer "$AP_SYSADMIN_TOKEN" --recipe "$RECIPE" \
    --chat-id "$TELEGRAM_CHAT_ID" --timeout-s 10 ...)
else
  # legacy fallback for AP_ENV=prod or AP_USE_LEGACY_GATE_B=1
  ...
fi
```

---

## Live e2e Result Table

```
SC-03 Gate A: 15 / 15 PASS
SC-03 Gate B:  5 /  5 PASS
Gate C:        manual (test/sc03-gate-c.md; per-release; not run by this script)
```

| Recipe   | Boot (s) | Gate A r1 (cold) | Gate A r2 (warm) | Gate A r3 (warm) | Gate B (s) | Gate B corr | reply_sent.correlation_id |
| -------- | -------- | ---------------- | ---------------- | ---------------- | ---------- | ----------- | ------------------------- |
| hermes   | ~15      | 14.32            | 5.68             | 5.61             | 1.19       | d288        | test:d288                 |
| picoclaw | ~3       | 1.74             | 1.76             | 2.10             | 1.08       | 7221        | test:7221                 |
| nullclaw | ~3       | 2.09             | 3.51             | 1.58             | 1.13       | 979d        | test:979d                 |
| nanobot  | ~30      | 16.45            | 5.88             | 5.13             | 1.11       | 5389        | test:5389                 |
| openclaw | ~131     | 119.04           | 101.22           | 83.03            | 1.79       | cf34        | test:cf34                 |

All 5 Gate B `reply_sent_event.correlation_id` values match the harness's
generated `test:<corr>` prefix verbatim — the rows are real DB INSERTs
that travelled the long-poll → INSERT → signal-wake → handler-fetch chain
end-to-end. (Prior to 22b-08 the bot-self path produced 0 events because
allowFrom filtered the bot's own outbound messages.)

---

## Test Suite Result

```
api_server/tests/test_events_inject_test_event.py:
  test_inject_test_event_prod_returns_404               PASSED
  test_inject_test_event_sysadmin_happy_path            PASSED
  test_inject_test_event_missing_bearer_401             PASSED
  test_inject_test_event_wrong_bearer_404_opaque        PASSED
  test_inject_test_event_sysadmin_token_unset_404       PASSED
  test_inject_test_event_no_running_container_404       PASSED
  test_inject_test_event_wakes_long_poll_within_1s      PASSED  (~440ms wake)
  test_inject_test_event_double_inject_advances_seq     PASSED
  ============================== 8 passed in 6.30s ==============================

No regression in prior 22b event tests:
  test_events_long_poll.py + test_events_auth.py + test_events_lifespan_reattach.py
  + test_events_lifecycle_spawn_on_start.py + test_events_lifecycle_cancel_on_stop.py
  ===================================== 22 passed in 20.37s =====================================

  test_events_store.py + test_events_seq_concurrency.py + test_events_batching_perf.py
  ===================================== 16 passed (+ 10 unrelated DeprecationWarnings) =====================================
```

---

## Cleanup Proof

```
$ docker ps --filter "name=ap-recipe" --format '{{.ID}}'
(empty)
```

The e2e script's `cleanup` trap (`POST /v1/agents/$ACTIVE_AGENT_ID/stop`)
ran successfully on EXIT for all 5 recipes — no container leak.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] AP_ENV=dev override added to docker-compose.local.yml**

- **Found during:** Task 2 Part C live verification preflight — `curl /openapi.json`
  returned no `inject-test-event` path even though Task 1 GREEN tests passed
  against testcontainers.
- **Root cause investigation:**
  1. `docker exec deploy-api_server-1 env | grep AP_ENV` showed `AP_ENV=prod`
     — inherited from `deploy/docker-compose.prod.yml` line that hardcodes
     `AP_ENV: prod` for the api_server service.
  2. The conditional include in main.py uses `app.state.settings.env != "prod"`,
     so the inject_router was correctly NOT registered in prod-mode.
  3. The plan's preflight explicitly requires AP_ENV=dev:
     `test "$(curl ... /openapi.json | jq | grep -c 'inject-test-event' ...)" >= 1`
  4. CLAUDE.md forbids modifying `.env` files without explicit user permission;
     `docker-compose.local.yml` is NOT a `.env` file but a compose-override
     intended for local-laptop scenarios (already carries `user: root` and
     host-port mapping for the same purpose).
- **Fix (compose-override-only):** Add `environment: AP_ENV: dev` to the
  api_server service in `deploy/docker-compose.local.yml` with an inline
  comment explaining the rationale + production-safety guarantee.
- **Verification:** `docker compose ... up -d --force-recreate api_server` →
  `docker exec deploy-api_server-1 env | grep ^AP_ENV=` returns `AP_ENV=dev`,
  and `curl /openapi.json | jq '.paths | keys[]' | grep inject` returns
  `/v1/agents/{agent_id}/events/inject-test-event`.
- **Files modified:** `deploy/docker-compose.local.yml`
- **Commit:** `437dec4`
- **Why this is the right fix:** The override is local-only, opt-in (only
  applies when the local compose file is layered in), and aligned with the
  file's existing purpose. Production remains untouched.

**Total deviations:** 1 auto-fixed (Rule 3 — Blocking environmental gap).

---

## Auth Gates

None — all required env vars (`AP_CHANNEL_MASTER_KEY`, `AP_SYSADMIN_TOKEN`,
`POSTGRES_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`) were already present from prior
22b plans (set in `deploy/.env.prod` + `.env.local`).

---

## Honest Scope Limits

1. **Gate C (manual real-user→bot Telegram round-trip) NOT addressed.**
   Gate C remains the per-release manual checklist at `test/sc03-gate-c.md`.
   The `direct_interface` (Gate A) + `inject-test-event` (Gate B) paths
   together exercise everything BUT the real user→bot ingestion via the
   Bot API filter chain — that's structurally untestable without MTProto
   user-impersonation (deferred per CONTEXT D-18a).

2. **AP_USE_LEGACY_GATE_B=1 fallback is structurally a FAIL on the local
   stack.** The legacy `send-telegram-and-watch-events` path uses bot-self
   `sendMessage`; the recipes' `allowFrom` filters the bot out; no
   `reply_sent` row flows. The fallback exists for prod-mode scenarios where
   the inject route is invisible.

3. **Synthetic-event marker is convention not contract.** The `test:`
   correlation_id prefix is a human-friendly cleanup aid; T-22b-08-06 is
   accepted: the contamination volume is bounded by test environment run
   frequency.

4. **Long-poll handler does not filter synthetic events out for normal
   callers.** Future frontend consumers MAY want a `?include_test=false`
   filter; out of scope for 22b. T-22b-08-07 accepted as a documented
   future enhancement.

5. **API recipe-cache restart discipline (inherited from 22b-07):** Carries
   forward; not introduced by this plan.

---

## TDD Gate Compliance

This plan is `type: execute` per frontmatter (gap closure), but Task 1 is
`tdd="true"`. Gate sequence verified:

1. **RED:** commit `ea2093f` — `test(22b-08): add 8 failing integration
   tests ... (RED)` — 6/8 FAIL initially (route doesn't exist), 2/8 PASS
   by accident (FastAPI default 404). Test file alone landed.
2. **GREEN:** commit `aecf3cb` — `feat(22b-08): POST .../inject-test-event
   handler + ... (GREEN)` — handler + main.py change land; all 8 tests now
   PASS for the right reason.
3. **REFACTOR:** none needed; the implementation matches the plan's Step-1-8
   sketch verbatim. No follow-on cleanup commit.

The conventional `test(...)` → `feat(...)` commit pair is present in
`git log --oneline`.

---

## Self-Check: PASSED

All claims verified by direct shell + git probes after the live e2e run.

**Files claimed by plan output spec:**
- `api_server/src/api_server/routes/agent_events.py` POST handler present
  (`grep -c "async def inject_test_event"` returns `1`)
- `api_server/src/api_server/routes/agent_events.py` `inject_router` present
  (`grep -c "inject_router = APIRouter"` returns `1`)
- `api_server/src/api_server/main.py` conditional include present
  (`grep -c "settings.env"` returns `>=1`)
- `api_server/tests/test_events_inject_test_event.py` exists with 8 tests
  (`pytest --co -q | wc -l` returns >=8)
- `test/lib/agent_harness.py` new subcommand present
  (`grep -c "def cmd_send_injected_test_event_and_watch"` returns `1`)
- `test/e2e_channels_v0_2.sh` new subcommand referenced
  (`grep -c "send-injected-test-event-and-watch"` returns `2`)
- `e2e-report.json` fresh capture (15 Gate A PASS + 5 Gate B PASS verified
  via `python3 -c json.load + filter`)

**Commits verified present in `git log --oneline`:**
```
a3dad39 docs(22b-08): capture e2e-report.json from live SC-03 PASS run
437dec4 fix(22b-08): set AP_ENV=dev in docker-compose.local.yml override (Rule 3 deviation)
74f50d8 feat(22b-08): agent_harness send-injected-test-event-and-watch + e2e Gate B rewire
aecf3cb feat(22b-08): POST /v1/agents/:id/events/inject-test-event handler + dev-only conditional include (GREEN)
ea2093f test(22b-08): add 8 failing integration tests for POST /v1/agents/:id/events/inject-test-event (RED)
```

**Live infra verification:**
- `curl http://localhost:8000/openapi.json | jq '.paths | keys[]' | grep inject`
  returns `/v1/agents/{agent_id}/events/inject-test-event`
- `cat e2e-report.json | jq '[.[] | select(.gate=="A" and .verdict=="PASS")] | length'`
  returns `15`
- `cat e2e-report.json | jq '[.[] | select(.gate=="B" and .verdict=="PASS")] | length'`
  returns `5`
- `docker ps --filter "name=ap-recipe" --format '{{.ID}}' | wc -l`
  returns `0` (no leaked containers)

All 5 plan-execution commits present in git log. Self-check PASSED.

---

_Phase 22b Plan 08 — Gap 2 Closure — completed 2026-04-19_
