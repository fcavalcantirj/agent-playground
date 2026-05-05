# Phase 28: Temporal-backed message dispatch + dispatcher hardening — Context

**Gathered:** 2026-05-05
**Status:** Ready for planning
**Mode:** auto (recommended-option chosen per gray area; user may revise CONTEXT.md before /gsd-plan-phase)

<domain>
## Phase Boundary

Replace the asyncpg-based `inapp_dispatcher` with **Temporal workflows** mirroring MSV's `SendMessageWorkflow` pattern. The phase ships when:

1. A new user message → `DispatchMessageWorkflow` orchestrates: ready-check → forward-to-bot → capture-reply → record-usage → emit-SSE, all atomic and retryable.
2. Activity-internal `[1s, 2s, 4s]` exponential backoff on `container_not_ready` / connection errors closes the intermittent symptom that surfaced in the 2026-05-04 → 2026-05-05 chat-stability investigation.
3. Temporal UI is reachable on `localhost:8088` for dev observability.
4. Phase 27 `UsageTickerWidget` is re-mounted in the AppBar via a Consumer-scoped subscription pattern that survives screen tear-down (the defunct-element race fix yanked at commit `27d3c79`).
5. The legacy `services/inapp_dispatcher.py:_handle_row` async loop + asyncpg savepoint dance is **deleted** — Temporal owns the lifecycle.

**Out of scope (own future phases):**
- Stripe billing / debit activities (Phase B / Phase 29 candidate). The workflow ships with a `record_usage` activity, NOT a `debit_balance` activity. Billing-on-top later is additive.
- Go API rewrite (backlog 999.2 — deferred until v0.3 validates).
- Telegram channel orchestration via Temporal — only `inapp` channel migrates this phase.
- Chat send-button lock + typing-dots TTL (Phase 25 polish — separate UX phase).

</domain>

<decisions>
## Implementation Decisions

### Cluster topology
- **D-01:** **Self-hosted Temporal via docker compose**, not Temporal Cloud. Matches MSV pattern, zero external service dependency, dev-friendly. `temporalio/auto-setup:latest` + `temporalio/ui:latest`, backed by the existing `deploy-postgres-1` (additive — Temporal creates its own databases inside the same Postgres instance). Mounted on `deploy_default` network so api_server + workers reach it via DNS hostname `temporal:7233`.
- **D-02:** Temporal Postgres uses dedicated DB names (`temporal`, `temporal_visibility`) inside `deploy-postgres-1`. Initialized via `auto-setup` image's bootstrap. NOT shared with `agent_playground_api` DB.
- **D-03:** Temporal frontend gRPC on `7233` (internal only, not host-bound). Temporal UI on host port `8088`. Single namespace `default` (matches MSV).

### Worker deployment
- **D-04:** **Worker runs in a separate container** (`deploy-temporal-worker-1`), not in-process with api_server. Independent scaling, independent crash recovery. New service in `deploy/docker-compose.prod.yml`. Uses the same Python image as api_server (shared deps, separate `CMD` invoking `python -m api_server.temporal.worker`).
- **D-05:** Single task queue `ap-messages` for v1. Multi-queue split (e.g. separate `ap-deploy` for agent provisioning workflows) deferred — only message dispatch migrates this phase.

### Migration approach
- **D-06:** **Big-bang swap within this phase**, not gradual coexistence. The asyncpg dispatcher is one file (`services/inapp_dispatcher.py`). The dispatcher loop entry point becomes a `client.start_workflow(...)` call. Old `_handle_row` + savepoint logic is deleted. Reaper logic moves into the workflow (timeout + retry policy own the cleanup). Risk: low — tests cover the migration; rollback is `git revert`.
- **D-07:** Phase 27's `UsageRecorder` (`services/usage_recorder.py`) becomes a **Temporal activity** (`record_usage_activity.py`) that wraps the existing function. The savepoint pattern is removed since Temporal handles transaction semantics differently — record_usage runs in its own activity context.

### Workflow & activity contracts
- **D-08:** **Workflow ID = `msg-{message_uuid}`** (the existing `inapp_messages.id`). MSV uses `msg-{telegramID}-{unixMillis}`; AP uses the message's already-existing UUID since each row gets one. `WorkflowIDReusePolicy.REJECT_DUPLICATE` so the same message_id can't kick off two workflows.
- **D-09:** **Workflow language style: Go-portable Python.** No comprehensions in workflow logic, no `datetime.now()` outside activities, no random in workflows. Pure-function workflow body. Mirrors MSV's `send_message.go` shape 1:1 so backlog 999.2 (Go rewrite) has a clean migration template.
- **D-10:** **Workflow shape mirrors MSV `SendMessageWorkflow`** verbatim:
  ```
  CheckContainerReady   → activity, MaxAttempts: 5 with [250ms, 500ms, 1s, 2s, 4s] backoff
  ForwardToAgent        → activity, MaxAttempts: 1 in workflow (activity-internal retry handles transport errors)
  RecordUsage           → activity, MaxAttempts: 3 with 1s backoff (best-effort, doesn't fail workflow)
  EmitInappOutboundEvent → activity, MaxAttempts: 3 (best-effort, doesn't fail workflow)
  MarkMessageDone       → activity, MaxAttempts: 5 with 250ms backoff (load-bearing — must succeed)
  ```
  The dispatcher's current Step 4 (`mark_forwarded`) becomes implicit via Temporal's started-but-not-completed state. No equivalent activity needed.

### Activity retry policy
- **D-11:** **`ForwardToAgent` activity-internal retry: 3 attempts with `[1s, 2s, 4s]` exponential backoff.** Copies MSV's `messaging/activities/forward_to_agent.go:115-146` verbatim. Only retry transport errors (`httpx.ConnectError`, `httpx.ReadTimeout`); HTTP 4xx/5xx fail terminal (no retry). LLM-error patterns in response body (per MSV's pattern matching) — `IsLLMError` flag returned alongside response, workflow handles separately.
- **D-12:** **Activity timeout = (configurable bot timeout) + 30s buffer.** Matches MSV's tier-scoped timeout pattern. AP doesn't have user tiers yet, so a single `BOT_TIMEOUT_SECONDS = 60s` config (env var override) until tiers ship. Buffer ensures the activity-level timeout fires before the workflow-level timeout.
- **D-13:** **Workflow execution timeout: 5 minutes.** Hard cap per message dispatch. Beyond that → workflow fails, message marked `failed` in `inapp_messages`, mobile receives the failure SSE event.

### Idempotency
- **D-14:** **Workflow-ID idempotency only.** No mobile-side dedup token. The existing `Idempotency-Key` middleware on `POST /messages` handles client-side retry dedup at the API layer; workflow uniqueness handles dispatcher-side. Two layers, separate concerns.
- **D-15:** **Activities are idempotent or best-effort.** `RecordUsage` is idempotent at the DB layer (`usage_logs` row PK = uuid generated at insert; no upsert needed). `EmitInappOutboundEvent` is idempotent via `agent_events.seq` per-container-monotonic. `MarkMessageDone` is idempotent (UPDATE ... WHERE status != 'done').

### Observability
- **D-16:** **Temporal UI for dev + structlog (existing) for prod logs.** Temporal UI on `localhost:8088` shows full execution history per workflow including retry counts, activity inputs/outputs (sanitized), failure traces. Prod log integration deferred — Temporal worker can ship logs to existing `structlog` setup later if needed.
- **D-17:** No Loki / Grafana wiring this phase. Temporal UI is enough for the macOS local dev pain points. Prod observability roadmap is its own phase.

### Mobile side — Phase 27 ticker re-mount
- **D-18:** **Re-mount `UsageTickerWidget` using a `Consumer` builder INSIDE the AppBar `actions:` array**, not a direct `ConsumerWidget` mount. This isolates the provider subscription's lifecycle to the Consumer's own Element, which gets disposed cleanly when the AppBar tears down. Mirrors the pattern that `Phase 22c.3` MessageStream uses for the chat screen's SSE listener.
- **D-19:** Re-mount happens on **both Dashboard and Chat AppBars** (same as the original Wave 5 intent). The defunct-element race is solved at the widget level, not by avoiding the mount points.
- **D-20:** Tap-on-ticker behavior unchanged from Wave 3: `byAgent.first.agentId` → push `/agents/:id/usage`. Empty `byAgent` → no-op.
- **D-21:** Trigger #3 (instant ticker refresh on assistant SSE event) remains **deferred**. The lifecycle resume + screen mount triggers (D-32 from Phase 27 — kept) are sufficient. Re-introducing trigger #3 would re-introduce the defunct-element race we just escaped from.

### Phase B billing readiness (deferred but designed for)
- **D-22:** Workflow includes a `DebitBalance` activity stub that's a **no-op in this phase**. The activity exists, accepts the same inputs `RecordUsage` does, returns `Decimal('0')`. Phase B replaces the no-op body with real Stripe credit-balance debit logic — workflow shape doesn't change. This is the "design for the future" without "build the future" pattern.
- **D-23:** Workflow signal handler interface (e.g. `cancel_dispatch`) is NOT implemented this phase. MSV doesn't use signals on SendMessageWorkflow either. Add when a real cancel UX requirement emerges.

### Test strategy
- **D-24:** **Both unit tests (Temporal test environment) and integration tests (real Temporal via deploy stack).** Unit tests use `temporalio.testing.WorkflowEnvironment` for deterministic workflow assertions. Integration tests start an actual `deploy-temporal-1` container via the existing testcontainers harness (or via `make e2e-inapp-docker` extended) and exercise full workflow lifecycle.
- **D-25:** Existing 113+ pytest tests remain green throughout migration. The dispatcher swap is the riskiest part; integration tests must cover at minimum: happy path round-trip, container_not_ready transient, bot_timeout terminal, RecordUsage activity failure (must not fail workflow), MarkMessageDone failure (must fail workflow).

### Claude's Discretion
- Naming for activity files inside `api_server/src/api_server/temporal/activities/` — Claude picks (snake_case, one file per activity).
- `pyproject.toml` exact `temporalio` version pin — Claude picks (latest stable; lock with uv).
- Worker concurrency settings (`max_concurrent_activities`, etc.) — Claude picks initial values mirroring MSV's `messaging/cmd/worker/main.go:305-327` (10 concurrent activities, 5/sec throttle).
- Whether to extract `dispatch_message.py` into `workflows/` subdirectory or keep flat — Claude picks (flat for now, refactor when 2nd workflow lands).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### MSV reference implementation (THE primary source — verbatim patterns to copy)
- `/Users/fcavalcanti/dev/meusecretariovirtual/messaging/workflows/send_message.go` lines 16-198 — workflow shape, retry config, best-effort cleanup pattern
- `/Users/fcavalcanti/dev/meusecretariovirtual/messaging/activities/forward_to_agent.go` lines 64-196 — connection-retry activity, exponential backoff `[1s, 2s, 4s]`, transport-vs-HTTP error distinction
- `/Users/fcavalcanti/dev/meusecretariovirtual/messaging/cmd/worker/main.go` lines 288-327 — worker setup, Temporal client connection, task-queue registration
- `/Users/fcavalcanti/dev/meusecretariovirtual/infra/docker-compose.yml` lines 86-109 — Temporal + Temporal UI compose service shape
- `/Users/fcavalcanti/dev/meusecretariovirtual/specs/TEMPORAL-INFRA-PLAN.md` — MSV's lessons-learned + decision log around Temporal infra (read for failure modes / gotchas)

### AP existing code (the surface this phase replaces)
- `api_server/src/api_server/services/inapp_dispatcher.py` — full file. The `_handle_row` async function + asyncpg savepoint dance is replaced by `DispatchMessageWorkflow`. Keep the bot-call logic but extract into the activity.
- `api_server/src/api_server/services/inapp_recipe_index.py` — `get_container_ip` stays; activity calls it through the index. `_network_name` config also stays.
- `api_server/src/api_server/services/usage_recorder.py` — `record_usage` becomes the body of `record_usage_activity`. Drop the savepoint wrapper inside.
- `api_server/src/api_server/services/inapp_messages_store.py` — DB CRUD seam. `mark_forwarded` becomes implicit via Temporal state; `mark_done` becomes an activity; `mark_failed` becomes an activity invoked from workflow's `except` arms.

### AP infrastructure
- `deploy/docker-compose.prod.yml` — add `temporal` + `temporal-ui` + `temporal-worker` services on `deploy_default` network
- `deploy/docker-compose.local.yml` — local-dev override for any port-publish overrides
- `Makefile` (top-level) — `dev-api-local` target may need `temporal` service in its compose-up sequence

### AP mobile (re-mount target)
- `mobile/lib/features/usage/usage_ticker_widget.dart` — the widget being re-mounted with the Consumer-scoped pattern
- `mobile/lib/features/dashboard/dashboard_screen.dart` line 95 (post-yank, pre-remount) — the mount site
- `mobile/lib/features/chat/chat_screen.dart` line 159 (post-yank, pre-remount) — the second mount site
- `mobile/lib/features/chat/chat_providers.dart` — for reference on Riverpod listener-during-teardown patterns; the SSE invalidate hook there is intentionally deferred (D-21)

### Phase 27 carryover
- `.planning/phases/27-byok-usage-visibility/27-CONTEXT.md` — D-32 (the 3 ticker refresh triggers) — trigger #3 stays deferred per D-21 above
- Memory: `project_phase_27_session_close.md` — the full context of why the ticker was unmounted

### Backlog cross-references
- `.planning/ROADMAP.md` — Phase 999.2 (Go API rewrite) for the "Go-portable Python" rationale (D-09)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`UsageRecorder` (`services/usage_recorder.py`)**: drop-in body for the `record_usage_activity`. Ship as-is minus the savepoint context manager.
- **`InappRecipeIndex` (`services/inapp_recipe_index.py`)**: already wired in api_server lifespan. Activity grabs `state.recipe_index` from the Temporal worker's bound app state.
- **`structlog` logging setup** in `api_server/main.py` — workers use the same setup. Adds `workflow_id`, `activity_name`, `attempt` fields to log context.
- **`testcontainers-style` postgres harness** in `tests/conftest.py` — extend to spin up a Temporal cluster for integration tests, OR run integration tests against the deploy stack with `docker compose -f deploy/...` (matches `make e2e-inapp-docker` pattern).
- **Phase 22c.3 `MessagesStream`** in `mobile/lib/core/api/messages_stream.dart` — reference pattern for Riverpod subscriptions that survive screen lifecycle. Same approach for Consumer-scoped ticker.

### Established Patterns
- **3-way contract switch** in `inapp_dispatcher._dispatch_http_localhost` (`openai_compat` / `a2a_jsonrpc` / `zeroclaw_native`): moves into the activity verbatim. The match-statement stays.
- **Stripe-shape error envelope** (`models/errors.py::ErrorCode + make_error_envelope`): unaffected. Activity-level errors propagate through Temporal as `ApplicationError`; the API layer that returns 4xx/5xx is upstream of the workflow.
- **Migration tooling** (`alembic`) — Phase 28 likely doesn't add migrations (no schema change). If it does (e.g. a workflow-id column on `inapp_messages` for traceability), one new migration `011_*` lands.

### Integration Points
- **API entry point** (`routes/agent_messages.py`): `POST /v1/agents/:id/messages` currently inserts into `inapp_messages` and returns 202. Add: after the insert, call `temporal_client.start_workflow(DispatchMessageWorkflow.run, ..., id=f"msg-{row.id}", task_queue="ap-messages")`. Same 202 response, same idempotency-key middleware.
- **Worker boot** (`api_server/temporal/worker.py` — new): mirror api_server's lifespan setup (DB pool, recipe_index, redis, env loading) but expose those to activities via worker-level `data_class_or_dependency_injector` rather than FastAPI's app.state.
- **Compose stack** (`deploy/docker-compose.prod.yml`): adds `temporal` + `temporal-ui` + `temporal-worker` services. `make dev-api-local` covers them via the standard `up -d` flow.

</code_context>

<specifics>
## Specific Ideas

- **Mirror MSV verbatim where reasonable.** The Go→Python translation is mostly mechanical for the workflow shape. Activity bodies are AP-specific but the `defer + retry + log` skeletons port 1:1.
- **Don't reinvent the bot-call.** Keep the existing `_dispatch_http_localhost` 3-way contract switch logic — just move it into the activity. The contract layer is independent of the orchestration layer.
- **The `container_not_ready` retry is the bullseye.** When in doubt during planning, optimize the design around making this case bulletproof. The user's frustration during the 2026-05-04→05 session was almost entirely this symptom.

</specifics>

<deferred>
## Deferred Ideas

- **Stripe billing layer** (Phase B / 29): atomic debit-with-reply. Workflow stub `DebitBalance` exists per D-22; Phase B replaces the body.
- **Multi-queue split** (`ap-deploy`, `ap-billing`): deferred. Single `ap-messages` queue ships v1.
- **Telegram channel via Temporal**: deferred. Only `inapp` channel migrates this phase.
- **Workflow signal handlers** (cancel_dispatch, pause_user): deferred. Add when real UX needs them.
- **Temporal Schedules** (e.g. periodic fleet health check, idle session reaper): deferred. MSV uses Schedules; AP doesn't have a use case yet beyond the current asyncpg-poll-based reaper.
- **Loki / Grafana / structured prod observability**: deferred. Temporal UI covers the dev pain.
- **Worker auto-scaling / horizontal pool**: deferred. Single worker container ships v1.
- **Continue-as-new for long workflows**: deferred. AP message dispatch is sub-minute; no continue-as-new needed.
- **Go API rewrite** (backlog 999.2): deferred until v0.3 validates.
- **Chat send-button lock + typing-dots TTL** (Phase 25 polish): deferred. Separate UX phase.

</deferred>

---

*Phase: 28-temporal-dispatch*
*Context gathered: 2026-05-05 (auto mode — recommended-option chosen for each gray area)*
*User: revise CONTEXT.md before /gsd-plan-phase 28 if any decision diverges from intent*
