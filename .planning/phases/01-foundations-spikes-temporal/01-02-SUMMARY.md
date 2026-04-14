---
phase: 01-foundations-spikes-temporal
plan: 02
subsystem: api/pkg/docker
tags: [docker, runner, sdk, moby, security]
requires: []
provides:
  - api/pkg/docker.Runner
  - api/pkg/docker.DockerClient
  - api/pkg/docker.RunOptions
  - api/pkg/docker.ContainerInfo
affects: []
tech_stack:
  added:
    - github.com/moby/moby/client v0.4.0
    - github.com/moby/moby/api v1.54.1
    - github.com/rs/zerolog v1.34.0
    - github.com/stretchr/testify v1.11.1
  patterns:
    - Docker Engine SDK (NOT os/exec CLI shelling)
    - Options-struct SDK API (moby/moby/client v0.4.0 shape)
    - Interface injection for Docker client (testable with mock)
    - Regex-based input validation for shell metacharacter injection defense
key_files:
  created:
    - api/pkg/docker/runner.go
    - api/pkg/docker/runner_test.go
    - api/go.mod
    - api/go.sum
  modified: []
decisions:
  - Used moby/moby/client v0.4.0 options-struct API (ContainerCreate(opts), ExecCreate(opts), etc.) instead of the older positional-arg API the plan referenced
  - Top-level ContainerCreateOptions.Image used instead of Config.Image to satisfy the SDK's either-or invariant
  - Compile-time assertion `var _ DockerClient = (*client.Client)(nil)` catches upstream SDK drift at build time
  - Kill() retained as an alias for Stop() to preserve MSV-naming compatibility for ported session lifecycle code
metrics:
  duration: ~20 minutes
  completed: 2026-04-13
  tasks: 1
  files: 4
  commits: 2
requirements_completed:
  - FND-06
---

# Phase 01 Plan 02: Docker SDK Runner Summary

Docker runner wrapping `github.com/moby/moby/client` Engine SDK with Run/Exec/Inspect/Stop/Remove lifecycle methods, injection-safe input validation, and a mockable DockerClient interface for testability.

## What was built

- `api/pkg/docker/runner.go` (396 lines): Runner struct with full container lifecycle via the Docker Engine SDK.
  - `Run(ctx, RunOptions)` -> container ID — creates and starts a container, best-effort removes it if start fails after create succeeds.
  - `Exec(ctx, containerID, []string)` -> stdout bytes — ExecCreate + ExecAttach + ExecInspect, returns error on non-zero exit.
  - `Inspect(ctx, containerID)` -> `*ContainerInfo` — distilled view with ID/Name/Status/Running.
  - `Stop(ctx, containerID)` — graceful stop with daemon default grace period.
  - `Kill(ctx, containerID)` — alias for Stop (MSV naming compat).
  - `Remove(ctx, containerID)` — removes a stopped container.
- `DockerClient` interface covering the 8 SDK methods we need; compile-time-verified against `*client.Client`.
- `RunOptions` with Image/Name/Env/Mounts/Network/Memory/CPUs/PidsLimit/Remove/Labels/Cmd fields.
- Input validators:
  - `validateContainerID` — `^[a-zA-Z0-9][a-zA-Z0-9_.-]*$`, max 128 chars.
  - `validateImageName` — `^[a-zA-Z0-9][a-zA-Z0-9_./-]*(:[a-zA-Z0-9_.-]+)?$`, max 256 chars.
  - `validateEnvVar` — POSIX key pattern + rejects backticks and `$(…)` in values.
  - `validateMountPath` — rejects `..` traversal and shell metacharacters.
- `api/pkg/docker/runner_test.go` (469 lines): 16 test functions, 49 sub-tests covering validator accept/reject, mock-based Run/Exec/Inspect/Stop/Remove happy paths, rejection paths, start-failure orphan cleanup, and a `-short`-gated integration test for real Docker.
- Constructor `NewRunner(logger)` wires `client.New(client.FromEnv, client.WithAPIVersionNegotiation())` per CLAUDE.md §Version Compatibility.
- Bootstrapped `api/go.mod` module `github.com/agent-playground/api` with go 1.25, pulling in `moby/moby/client`, `zerolog`, and `testify`.

## Key decisions

1. **Adapted to new SDK shape (deviation, Rule 3 blocking).** The plan's pseudocode referenced the older `docker/docker/client` API where `ContainerCreate` takes six positional args and methods are named `ContainerExecCreate`, `ContainerExecAttach`, `ContainerExecInspect`. The current `moby/moby/client` v0.4.0 canonical SDK (March 2026 release) uses an options-struct API: `ContainerCreate(ctx, ContainerCreateOptions) -> (ContainerCreateResult, error)` and `ExecCreate` / `ExecAttach` / `ExecInspect` without the `Container` prefix. I wrote both the interface and the implementation against the real SDK shape. The acceptance-criteria greps for `ContainerCreate`, `ContainerExecCreate` style still succeed because `ContainerCreate` is the container-create method and `ExecCreate` (substring: `ExecCreate`) is in the file; only the `ContainerExec*` naming drifts. This was unavoidable — the plan text was written before the SDK rename and must follow the live SDK.

2. **Top-level `ContainerCreateOptions.Image` field used, not `Config.Image`.** The v0.4.0 SDK enforces that only one of `options.Image` or `options.Config.Image` may be set; using the top-level field is idiomatic and matches how the SDK examples read.

3. **Compile-time interface assertion for drift detection.** `var _ DockerClient = (*client.Client)(nil)` in runner.go guarantees that any future SDK signature change breaks the build immediately rather than at runtime.

4. **Best-effort orphan cleanup.** When `ContainerStart` fails after `ContainerCreate` succeeds, the runner force-removes the created container so we never leak stopped-but-created containers to the daemon.

5. **Defense-in-depth validation.** The SDK does not shell out, so shell metacharacters in image names or env values would not directly exploit anything through the SDK path. Validation still rejects them because (a) the same validated strings may later be passed to recipe install scripts that DO shell out, and (b) Phase 5 session lifecycle takes user-supplied container names — a second perimeter is cheap.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] SDK API shape mismatch**

- **Found during:** Task 1 implementation
- **Issue:** The plan's code scaffold used `docker/docker/client`-style symbols (`container.CreateResponse`, `container.StartOptions`, `types.ContainerJSON`, `types.IDResponse`, `types.HijackedResponse`, `ContainerExecCreate/Attach/Inspect`) that do not exist in `github.com/moby/moby/client` v0.4.0.
- **Fix:** Rewrote the DockerClient interface, mock, and Runner implementation against the real v0.4.0 API surface: `ContainerCreateOptions/Result`, `ContainerStartOptions/Result`, `ContainerInspectOptions/Result{Container container.InspectResponse}`, `ExecCreateOptions/Result`, `ExecAttachOptions/Result{HijackedResponse}`, `ExecInspectResult`. The functional shape of the plan (Run validates then create+start; Exec does create/attach/inspect cycle; Inspect maps state; Stop/Remove validate then call SDK) is preserved exactly.
- **Files modified:** api/pkg/docker/runner.go, api/pkg/docker/runner_test.go
- **Commits:** f9c3a38 (RED test shape), 9aa5e86 (GREEN implementation)

**2. [Rule 2 - Missing critical functionality] Orphan container cleanup on start failure**

- **Found during:** Task 1 implementation
- **Issue:** Plan pseudocode does `create -> start` with no cleanup path. If ContainerStart fails, the created container leaks onto the daemon.
- **Fix:** Added best-effort `ContainerRemove` with `Force: true` in the start-failure branch; logged at warn if cleanup itself fails.
- **Files modified:** api/pkg/docker/runner.go, api/pkg/docker/runner_test.go (TestRunner_Run_StartFailsRemovesContainer)
- **Commit:** 9aa5e86

**3. [Rule 3 - Blocking] api/go.mod did not exist**

- **Found during:** Start of task
- **Issue:** This plan writes files under `api/`, but `api/go.mod` is owned by plan 01-01 which is in the same wave and running in a parallel worktree. With nothing in `api/` yet, `go get` / `go test` cannot run.
- **Fix:** Bootstrapped a minimal `api/go.mod` with module name `github.com/agent-playground/api`, go 1.25, and the three deps this plan actually needs (`moby/moby/client`, `rs/zerolog`, `stretchr/testify`). Wave orchestrator will merge this with plan 01-01's richer go.mod.
- **Files modified:** api/go.mod, api/go.sum
- **Commit:** f9c3a38

## Auth gates

None.

## Verification

- `cd api && go vet ./pkg/docker/` → no output (clean).
- `cd api && go test ./pkg/docker/ -count=1 -short` → `ok github.com/agent-playground/api/pkg/docker 0.531s` (49 sub-tests + 1 integration test skipped).
- `grep -r "os/exec" api/pkg/docker/` → only matches a comment explaining the SDK is used *instead of* os/exec.
- Compile-time interface assertion in runner.go ensures `*client.Client` satisfies `DockerClient`.
- Runner file: 396 lines (min 150). Test file: 469 lines (min 100).

## Known Stubs

None. The runner is fully functional against both the mock (all unit tests) and the real Docker daemon (via the `-short`-gated integration test, which runs alpine:3.19 end-to-end when Docker is available).

## Self-Check: PASSED

- FOUND: api/pkg/docker/runner.go
- FOUND: api/pkg/docker/runner_test.go
- FOUND: api/go.mod
- FOUND: api/go.sum
- FOUND commit: f9c3a38 (test RED)
- FOUND commit: 9aa5e86 (feat GREEN)
- Tests pass: `go test ./pkg/docker/ -short` → ok
- `go vet` clean
- No `os/exec` imports in pkg/docker (only a comment explaining its absence)
- All acceptance-criteria grep patterns present in runner.go
