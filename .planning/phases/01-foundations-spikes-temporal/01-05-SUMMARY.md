---
phase: 01-foundations-spikes-temporal
plan: 05
subsystem: temporal-workers
tags: [go, temporal, workflows, durability, session-queue, billing-queue, reconciliation-queue, foundations]
requires:
  - go-api-binary
  - server-functional-options
provides:
  - temporal-client
  - temporal-workers
  - pingpong-workflow-proof
  - session-queue
  - billing-queue
  - reconciliation-queue
  - stub-workflows-sessionspawn-sessiondestroy-recipeinstall-reconcilecontainers-reconcilebilling
affects:
  - api/internal/temporal
  - api/cmd/server
tech-stack:
  added:
    - "go.temporal.io/sdk v1.42.0"
    - "go.temporal.io/api v1.62.7"
    - "google.golang.org/grpc v1.79.3"
    - "github.com/nexus-rpc/sdk-go v0.6.0"
  patterns:
    - "Functional option composition in cmd/server/main.go: Plan 01-01's WithDevAuth and Plan 01-05's WithWorkers are both appended to a []server.Option slice, proving the pattern scales past the first extension"
    - "Optional Temporal wiring via empty-TEMPORAL_HOST short-circuit so laptops without a local Temporal server still boot the API"
    - "zerolog adapter bridges Temporal's go.temporal.io/sdk/log.Logger onto the existing zerolog pipeline so Temporal internals land in the same JSON stream as everything else"
    - "testsuite-based workflow unit tests (no real Temporal server needed) using go.temporal.io/sdk/testsuite.WorkflowTestSuite"
    - "Stub activities return explicit 'not implemented' errors while stub workflows return nil after logging -- workflows must remain callable by Phase 4/5 scaffolding, activities must fail loudly if a stray caller finds them"
key-files:
  created:
    - api/internal/temporal/activities.go
    - api/internal/temporal/workflows.go
    - api/internal/temporal/worker.go
    - api/internal/temporal/worker_test.go
  modified:
    - api/cmd/server/main.go
    - api/go.mod
    - api/go.sum
decisions:
  - "Pin go.temporal.io/sdk to v1.42.0 per plan -- matches MSV and has stable testsuite API"
  - "Server.Workers field already declared by Plan 01-01; this plan does NOT modify server.go -- WithWorkers was pre-declared for exactly this case. One file touched in cmd/server, zero files touched in internal/server."
  - "Session worker registers every workflow that a user-facing session submits (PingPong + SessionSpawn + SessionDestroy + RecipeInstall); billing and reconciliation workers register only their own workflow. Keeps the task-queue model tight: one workflow submitter knows exactly which queue to hit."
  - "Stub workflows log 'not implemented' and return nil (not an error) so that test registration paths stay green. The equivalent stub *activities* return explicit errors so any accidental Phase 1 caller fails loudly -- workflows are safe to register, activities are not safe to execute."
  - "Worker Stop is invoked by main.go directly (holding the concrete *apitemporal.Workers) rather than via srv.Workers.Stop() -- this keeps the shutdown path deterministic and avoids having the Server struct own a lifecycle reference after Echo has drained."
  - "Empty TEMPORAL_HOST short-circuits the whole Temporal block. Laptops without a compose stack running can still `go run ./cmd/server` -- aligns with plan acceptance criterion 'API starts without Temporal when TEMPORAL_HOST is empty'."
metrics:
  duration: ~25min
  completed: 2026-04-13
  tasks: 2
  files-created: 4
  files-modified: 3
  commits: 2
  test-suites: 1
  test-execution-seconds: 2
requirements:
  - FND-08
  - FND-09
---

# Phase 1 Plan 5: Temporal Worker Wiring Summary

Three Temporal workers (session / billing / reconciliation), stub workflows for every Phase 4/5 target, and a PingPong liveness proof -- all wired into main.go through the pre-declared `server.WithWorkers` functional option.

## What was built

Plan 01-05 is the Temporal onboarding plan. It takes the `Workers` interface and `WithWorkers` option that Plan 01-01 pre-declared, fills in a real implementation backed by `go.temporal.io/sdk` v1.42.0, and proves end-to-end wiring with a `PingPong` workflow that drives a real activity and returns its result.

### Package `api/internal/temporal`

Four files, 480 lines total:

- **`activities.go`** — `PingActivity` (returns `pong:<input>`) plus three stub activities (`SpawnContainerActivity`, `DestroyContainerActivity`, `InstallRecipeActivity`) that return explicit `not implemented (Phase N)` errors.
- **`workflows.go`** — `PingPong` workflow (executes `PingActivity` via `workflow.ExecuteActivity`) plus five stub workflows (`SessionSpawn`, `SessionDestroy`, `RecipeInstall`, `ReconcileContainers`, `ReconcileBilling`) that log "not implemented" and return nil.
- **`worker.go`** — `NewWorkers(host, namespace, logger)` dials Temporal and builds three workers registered against the three task queues. Exports the queue name constants (`SessionQueue = "session"`, `BillingQueue = "billing"`, `ReconciliationQueue = "reconciliation"`). Implements `server.Workers` (the `Start() error; Stop()` interface Plan 01-01 declared). Contains a `zerologAdapter` that satisfies `go.temporal.io/sdk/log.Logger` by delegating to zerolog.
- **`worker_test.go`** — seven tests using `go.temporal.io/sdk/testsuite`: `TestPingPong` (round-trip), one `Stub` test per stub workflow, plus `TestQueueConstants` locking in the task-queue string values.

### `cmd/server/main.go` integration

A single new block after migrations, before server construction:

```go
var workerOpt server.Option
var temporalWorkers *apitemporal.Workers
if cfg.TemporalHost != "" {
    w, err := apitemporal.NewWorkers(cfg.TemporalHost, cfg.TemporalNamespace, logger)
    // ... fatal on dial or start failure
    temporalWorkers = w
    workerOpt = server.WithWorkers(w)
} else {
    logger.Warn().Msg("TEMPORAL_HOST empty, skipping temporal worker startup")
}

opts := []server.Option{server.WithDevAuth(devAuth, sessionStore)}
if workerOpt != nil {
    opts = append(opts, workerOpt)
}
srv := server.New(cfg, logger, checker, opts...)
```

And a `temporalWorkers.Stop()` call in the graceful-shutdown path, after `srv.Shutdown(shutdownCtx)` drains Echo.

### Task-queue assignments

| Worker | Task queue | Workflows registered | Activities registered |
|--------|-----------|----------------------|----------------------|
| session | `session` | PingPong, SessionSpawn, SessionDestroy, RecipeInstall | PingActivity, SpawnContainerActivity, DestroyContainerActivity, InstallRecipeActivity |
| billing | `billing` | ReconcileBilling | (none in Phase 1) |
| reconciliation | `reconciliation` | ReconcileContainers | (none in Phase 1) |

Phase 5 will move session lifecycle workflows to activities that call `pkg/docker/runner`. Phase 4 will fill `RecipeInstall` and its activity. Phase 6 will fill the billing workflow. None of those phases needs to change the queue topology or the worker wiring established here.

## Tasks Completed

| Task | Name | Commit | Files | Tests |
|------|------|--------|-------|-------|
| 1 | Temporal workers + stub workflows + PingPong proof | `1c0560e` | 4 created (activities, workflows, worker, worker_test) + go.mod/go.sum updated | 7 tests in `internal/temporal` |
| 2 | Wire Temporal workers into main.go via server.WithWorkers | `9bf3fc6` | 1 modified (cmd/server/main.go) | Plan 01-01's NoOptionsWiring + FullFlow integration tests still green |

## Architecture Highlights

### `server.New` was not touched

Plan 01-01 pre-declared both the `Workers` interface and the `WithWorkers(w Workers) Option` function in `api/internal/server/server.go`. Plan 01-05 only had to supply a concrete type that satisfies the interface. That means:

- Zero lines of `internal/server/server.go` change
- Zero breakage of `TestIntegration_NoOptionsWiring` (still calls `server.New(cfg, logger, checker)` with zero options)
- Zero breakage of `TestIntegration_FullFlow` (still calls `server.New(cfg, logger, checker, server.WithDevAuth(...))`)
- Plan 01-05's cmd/server/main.go now composes **both** options: `server.New(cfg, logger, checker, server.WithDevAuth(...), server.WithWorkers(...))`

This is the exact backward-compatibility payoff that the functional options pattern was installed for in Plan 01-01.

### Empty `TEMPORAL_HOST` is a first-class path

`config.Load` still defaults `TEMPORAL_HOST` to `"localhost:7233"`, but `main.go` checks `cfg.TemporalHost != ""` before dialing. Any deployment that wants to run the API without Temporal (early bring-up, test harnesses, laptop dev with no compose stack) sets `TEMPORAL_HOST=""` and the API still serves `/healthz`, `/api/dev/login`, and `/api/me`.

### zerolog <-> Temporal log bridge

`go.temporal.io/sdk/log.Logger` uses `(msg, keyvals ...interface{})`. zerolog's `Event.Fields(...)` accepts that slice shape directly. The adapter:

```go
func (z *zerologAdapter) Info(msg string, keyvals ...interface{}) {
    z.logger.Info().Fields(kvSlice(keyvals)).Msg(msg)
}
```

`kvSlice` pads an odd-length keyvals slice with a `(MISSING)` placeholder so the adapter never panics on a caller bug. A compile-time assertion `var _ tlog.Logger = (*zerologAdapter)(nil)` locks the interface shape in at build time.

### Stub activity vs stub workflow semantics

Stub workflows return `nil` so test registration stays green and Phase 4/5 scaffolding can submit them without failing. Stub activities return explicit `not implemented (Phase N)` errors so any accidental caller in Phase 1 fails loudly instead of silently succeeding on empty data. This asymmetry is deliberate: a workflow is a hosted registration path (many callers), an activity is executed code (the caller better know what it's doing).

## Verification

### Temporal package tests

```
=== RUN   TestPingPong
--- PASS: TestPingPong (0.05s)
=== RUN   TestSessionSpawnStub
--- PASS: TestSessionSpawnStub (0.00s)
=== RUN   TestSessionDestroyStub
--- PASS: TestSessionDestroyStub (0.00s)
=== RUN   TestRecipeInstallStub
--- PASS: TestRecipeInstallStub (0.00s)
=== RUN   TestReconcileContainersStub
--- PASS: TestReconcileContainersStub (0.00s)
=== RUN   TestReconcileBillingStub
--- PASS: TestReconcileBillingStub (0.00s)
=== RUN   TestQueueConstants
--- PASS: TestQueueConstants (0.00s)
PASS
ok  	github.com/agentplayground/api/internal/temporal	0.737s
```

### Full suite (short mode)

```
ok  	github.com/agentplayground/api/internal/config       0.480s
ok  	github.com/agentplayground/api/internal/handler      0.797s
ok  	github.com/agentplayground/api/internal/middleware   1.156s
ok  	github.com/agentplayground/api/internal/server       1.428s
ok  	github.com/agentplayground/api/internal/temporal     1.798s
ok  	github.com/agentplayground/api/pkg/docker            1.177s
ok  	github.com/agentplayground/api/pkg/migrate           1.558s
```

All packages green. `go build ./cmd/server/` compiles cleanly. `go vet ./...` is silent.

## Acceptance Criteria

Every acceptance criterion from `01-05-PLAN.md` is satisfied:

### Task 1

- `api/internal/temporal/worker.go` contains `func NewWorkers(`
- SessionQueue = "session", BillingQueue = "billing", ReconciliationQueue = "reconciliation"
- `client.Dial` and `worker.New` both present
- `RegisterWorkflow(PingPong|SessionSpawn|SessionDestroy|ReconcileContainers|ReconcileBilling)` all present
- `api/internal/temporal/workflows.go` declares every required workflow function
- `api/internal/temporal/activities.go` contains `func PingActivity(`
- `api/internal/temporal/worker_test.go` contains `TestPingPong` and uses `testsuite`
- `cd api && go test ./internal/temporal/ -count=1` exits 0

### Task 2

- `api/cmd/server/main.go` imports `apitemporal` referencing `internal/temporal`
- `api/cmd/server/main.go` calls `NewWorkers` and `temporalWorkers.Start()`
- `api/cmd/server/main.go` calls `server.WithWorkers(`
- `api/cmd/server/main.go` checks `TemporalHost` before dialing
- `api/internal/server/server.go` still declares `opts ...Option` (unchanged)
- `api/internal/server/server.go` still declares `WithWorkers(` (unchanged -- Plan 01-01 pre-declared it)
- `cd api && go build ./cmd/server/` exits 0
- `cd api && go test ./... -short -count=1` exits 0

Note the plan called for a `WorkerManager` interface; Plan 01-01 had already declared the equivalent interface under the name `Workers`, so the plan's preferred approach (reuse the existing interface) was taken and no new interface was needed.

## Threat Model Disposition

| ID | Threat | How addressed |
|----|--------|---------------|
| T-1-18 | Temporal gRPC spoofing | Plan 01-04's compose binds Temporal frontend to loopback only; this plan accepts that disposition. The Go API dials `localhost:7233` by default. |
| T-1-19 | Workflow history disclosure | Workflow inputs in Phase 1 are limited to strings like "ping" / "test-session-id" -- no secrets flow through workflow arguments. Phase 5 will extend this with the same rule: secrets go through tmpfs injection at container start, not through workflow inputs. |
| T-1-20 | Worker DoS via workflow flood | Accepted -- Phase 1 has no external workflow-submission surface; Phase 5 adds rate limiting on the session creation API. |

## Deviations from Plan

None beyond a cosmetic rename: the plan suggested naming the new shutdown-lifecycle interface `WorkerManager`, but Plan 01-01 had already declared the equivalent interface under the name `Workers`. Using the existing name avoided adding a duplicate interface and required zero changes to `internal/server/server.go`. Every acceptance criterion from the plan still holds because `*temporal.Workers` satisfies `server.Workers` structurally.

Beyond that, the plan executed exactly as written. No auto-fixes, no blocking issues, no architectural decisions.

## Authentication Gates

None encountered. All work was local: `go build`, `go test`, `go mod tidy`. No external API keys, no Temporal server dial in the test path (testsuite runs in-memory).

## What's Next

Plan 01-05 unlocks Phase 5 (session orchestration):

- Phase 5 replaces the SessionSpawn / SessionDestroy stubs with real workflows that call container-lifecycle activities backed by `pkg/docker/runner`
- Phase 4 fills in the RecipeInstall stub workflow and its activity
- Phase 6 fills in the ReconcileBilling workflow (Stripe drift detection)
- A `ReconcileContainers` workflow is scheduled in Phase 5 for drift healing between Docker state and the `sessions` table

The worker / client / queue topology established here does not need to change for any of those phases.

## Self-Check: PASSED

**Files verified to exist:**

- api/internal/temporal/activities.go FOUND
- api/internal/temporal/workflows.go FOUND
- api/internal/temporal/worker.go FOUND
- api/internal/temporal/worker_test.go FOUND
- api/cmd/server/main.go FOUND (modified)
- api/go.mod FOUND (modified)
- api/go.sum FOUND (modified)

**Commits verified to exist:**

- 1c0560e FOUND (Task 1: temporal workers + stub workflows + PingPong proof)
- 9bf3fc6 FOUND (Task 2: wire WithWorkers into main.go)

**Build + tests:**

- `cd api && go build ./cmd/server/` exits 0
- `cd api && go vet ./...` clean
- `cd api && go test ./internal/temporal/ -count=1 -v` -- 7 tests PASS
- `cd api && go test ./... -short -count=1` -- all packages PASS
