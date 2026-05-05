# Phase 28: Temporal-backed message dispatch + dispatcher hardening — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-05
**Phase:** 28-temporal-dispatch
**Mode:** auto (recommended-option chosen for each gray area; user may revise CONTEXT.md before /gsd-plan-phase)
**Areas discussed:** Cluster topology, Worker deployment, Migration approach, Workflow & activity contracts, Activity retry policy, Idempotency, Observability, Mobile re-mount strategy, Phase B billing readiness, Test strategy

---

## Cluster topology

| Option | Description | Selected |
|--------|-------------|----------|
| Self-hosted via docker compose | `temporalio/auto-setup` + `temporalio/ui` on `deploy_default`; reuses existing Postgres | ✓ |
| Temporal Cloud | Managed; zero ops; per-workflow $$ | |
| Self-hosted via Kubernetes | Heavyweight; matches no other AP infra | |

**Selected:** self-hosted via docker compose. **Rationale:** matches MSV pattern verbatim; zero external service dependency; macOS dev-friendly; reuses `deploy-postgres-1` (separate DBs inside same instance).

---

## Worker deployment

| Option | Description | Selected |
|--------|-------------|----------|
| Separate container `deploy-temporal-worker-1` | Independent scaling + crash recovery | ✓ |
| In-process with api_server | Simpler boot; one fewer container | |
| Multiple worker containers per task queue | Premature splitting | |

**Selected:** separate container. **Rationale:** matches MSV; api_server crash doesn't take dispatcher with it; can scale workers without touching api_server.

---

## Migration approach

| Option | Description | Selected |
|--------|-------------|----------|
| Big-bang swap within this phase | Replace `_handle_row` + savepoint logic with `client.start_workflow(...)` | ✓ |
| Gradual coexistence (feature flag) | Run both dispatchers, gate by env var, cutover later | |
| Greenfield workflow with old dispatcher kept for fallback | 2× maintenance | |

**Selected:** big-bang. **Rationale:** the asyncpg dispatcher is one file; clean swap; rollback = `git revert`; tests cover the migration; coexistence adds complexity not value.

---

## Workflow language style

| Option | Description | Selected |
|--------|-------------|----------|
| Go-portable Python (no comprehensions, explicit state) | 1:1 template for backlog 999.2 (Go rewrite) | ✓ |
| Pythonic idioms | Easier read; harder eventual port | |
| Go directly (skip Python) | Out of scope this phase | |

**Selected:** Go-portable Python. **Rationale:** preserves Go-port option in 999.2 backlog with minimal future migration cost; constraints align with Temporal's determinism rules anyway (no `datetime.now()` in workflow body, etc.).

---

## Workflow ID idempotency strategy

| Option | Description | Selected |
|--------|-------------|----------|
| `msg-{message_uuid}` + REJECT_DUPLICATE | Use existing `inapp_messages.id` | ✓ |
| `msg-{user_id}-{unixMillis}` (MSV-shape) | New ID generated server-side | |
| Mobile-side dedup token + workflow ID | Two-layer dedup | |

**Selected:** `msg-{message_uuid}` + REJECT_DUPLICATE. **Rationale:** AP already has Idempotency-Key middleware on `POST /messages` (mobile-side dedup at API layer). Workflow ID handles dispatcher-side. Two layers, clean separation. Reusing the existing message UUID avoids generating a parallel ID.

---

## Activity retry policy (ForwardToAgent)

| Option | Description | Selected |
|--------|-------------|----------|
| MSV verbatim: 3 attempts, `[1s, 2s, 4s]` | Proven in production at MSV | ✓ |
| Tighter: 5 attempts, `[250ms, 500ms, 1s, 2s, 4s]` | Faster recovery for transient `container_not_ready` | |
| Looser: 2 attempts, `[2s, 5s]` | Today's behavior | |

**Selected:** MSV verbatim. **Rationale:** proven, simple, fits the symptom. Container start-up at MSV's scale is the same shape as AP's. No reason to deviate without evidence.

**Caveat:** for `CheckContainerReady` (a separate pre-flight activity) we use a tighter `[250ms, 500ms, 1s, 2s, 4s]` schedule because container readiness oscillates faster than upstream LLM connectivity.

---

## Observability

| Option | Description | Selected |
|--------|-------------|----------|
| Temporal UI (dev) + structlog (prod) | UI for dev pain; logs for ops | ✓ |
| Temporal UI only | Skip log integration | |
| Temporal UI + Loki + Grafana | Heavy; deferred | |

**Selected:** Temporal UI + structlog. **Rationale:** UI solves the dev-time "is the dispatcher stuck or just slow?" question that frustrated us 2026-05-04. structlog is already wired in api_server; workers reuse it. Loki/Grafana deferred to a future observability phase.

---

## Mobile UsageTickerWidget re-mount strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Consumer builder INSIDE AppBar actions | Subscription scoped to Consumer's element; survives screen tear-down | ✓ |
| Direct ConsumerWidget mount + post-frame callback wrap | Widget stays simple; tear-down race patched in build() | |
| Dashboard-only mount (skip Chat) | Avoids the most teardown-prone screen | |

**Selected:** Consumer builder inside AppBar. **Rationale:** isolates the provider subscription's lifecycle; mirrors the pattern Phase 22c.3 MessageStream uses for chat SSE; least invasive to AppBar layout; restores ticker to BOTH Dashboard and Chat as originally intended.

---

## Phase B billing readiness

| Option | Description | Selected |
|--------|-------------|----------|
| Stub DebitBalance activity (no-op now, real impl in Phase B) | Workflow shape stable across phases | ✓ |
| Skip — add DebitBalance during Phase B | Workflow shape changes between phases | |
| Build full Stripe debit now | Out of scope; gates this phase on Stripe migration | |

**Selected:** stub activity. **Rationale:** workflow signature locks now, body fills in later. Phase B doesn't have to revisit the workflow shape. Costs ~5 lines of Python.

---

## Test strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Both: `temporalio.testing` unit + real-Temporal integration | Coverage at both levels | ✓ |
| Unit only with `temporalio.testing.WorkflowEnvironment` | Fast; misses integration bugs | |
| Integration only against deploy stack | Slow; deterministic gaps | |

**Selected:** both. **Rationale:** unit tests catch determinism violations + workflow logic; integration tests catch the activity-Temporal bridge + worker-startup issues. Existing 113+ pytest tests must remain green throughout.

---

## Claude's Discretion

User said "auto mode" / "follow your gut" → Claude picked recommended option for every gray area. The following sub-choices remain at Claude's discretion during planning:

- Naming for activity files inside `temporal/activities/`
- `temporalio` exact version pin
- Worker concurrency settings (initial values mirror MSV's `messaging/cmd/worker/main.go:305-327`)
- Whether to extract `dispatch_message.py` into a `workflows/` subdirectory or keep flat (recommendation: flat for now, refactor when 2nd workflow lands)

## Deferred Ideas

(See CONTEXT.md `<deferred>` section for the full list — all preserved.)

- Stripe billing (Phase B / 29)
- Multi-queue split (`ap-deploy`, `ap-billing`)
- Telegram channel via Temporal
- Workflow signal handlers
- Temporal Schedules (idle reaper, etc.)
- Loki / Grafana
- Worker auto-scaling
- Continue-as-new
- Go API rewrite (999.2)
- Chat send-button lock + typing-dots TTL (Phase 25 polish)
