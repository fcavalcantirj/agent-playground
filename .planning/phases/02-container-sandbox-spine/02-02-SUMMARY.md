---
phase: 02-container-sandbox-spine
plan: 02
subsystem: api/pkg/docker
tags: [sandbox, docker-sdk, runoptions, naming, sbx-02, sbx-03, sbx-05, sbx-09]
requires:
  - "Phase 1 pkg/docker/runner.go (RunOptions, HostConfig plumbing, mock DockerClient test pattern)"
  - "github.com/google/uuid v1.6.0 (already in go.mod from Phase 1)"
  - "github.com/moby/moby/api/types/container.HostConfig (ReadonlyRootfs, Tmpfs, CapAdd, CapDrop, SecurityOpt, Runtime fields)"
provides:
  - "RunOptions sandbox knobs (SeccompProfile, ReadOnlyRootfs, Tmpfs, CapDrop, CapAdd, NoNewPrivs, Runtime)"
  - "docker.BuildContainerName / ParseContainerName / IsPlaygroundContainerName helpers"
  - "containerNamePrefix = 'playground-' cross-phase contract"
affects:
  - "Plan 02-03 recipes: can populate sandbox knobs in recipe defaults"
  - "Plan 02-04 session handler: will import docker.BuildContainerName and apply sandbox defaults"
  - "Plan 02-05 smoke tests: can assert playground- prefix on container names"
  - "Phase 5 reconciliation loop: uses IsPlaygroundContainerName to filter docker ps output"
  - "Phase 7.5 hardening: populates SeccompProfile / Runtime with concrete values"
tech-stack:
  added: []
  patterns:
    - "Defense-in-depth SecurityOpt composition (no-new-privileges + seccomp=)"
    - "Reflect-based negative invariant guard for SBX-05 Privileged field"
    - "Deterministic (userID, sessionID) → container name mapping (84-char format)"
    - "Leading-slash tolerance in Parse/Is helpers (Docker Inspect prefixes names with /)"
key-files:
  created:
    - api/pkg/docker/naming.go
    - api/pkg/docker/naming_test.go
  modified:
    - api/pkg/docker/runner.go
    - api/pkg/docker/runner_test.go
decisions:
  - "ReadOnlyRootfs plumbs to single-R HostConfig.ReadonlyRootfs (Docker SDK spelling — verified against moby/moby/api hostconfig.go)"
  - "SecurityOpt is composed (not overwritten) from NoNewPrivs + SeccompProfile so both can coexist"
  - "containerNamePrefix kept at 'playground-' as cross-phase contract — do not change"
  - "RunOptions has NO Privileged field — SBX-05 enforced by reflect-based test"
metrics:
  duration: "~12 minutes"
  completed: 2026-04-14
  tasks_completed: 2
  commits: 4
---

# Phase 02 Plan 02: Sandbox RunOptions + Container Naming Summary

Extended `pkg/docker/runner.go`'s `RunOptions` with 7 new sandbox knobs (SeccompProfile, ReadOnlyRootfs, Tmpfs, CapDrop, CapAdd, NoNewPrivs, Runtime) plumbed through to `container.HostConfig`, and added a deterministic `BuildContainerName`/`ParseContainerName`/`IsPlaygroundContainerName` naming helper used by future Phase 5 reconciliation. Pure code additions, zero new Go module dependencies, test count 49 → 89 (all green). SBX-05 invariant (no `Privileged` field) enforced by a reflect-based test.

## Tasks Completed

### Task 1: RunOptions sandbox fields + HostConfig plumbing

- **Files:** `api/pkg/docker/runner.go`, `api/pkg/docker/runner_test.go`
- **Commits:** `59a1ea8` (RED) → `065a78b` (GREEN)
- **Approach:** TDD RED→GREEN.
  - RED: Added 10 new subtests (`TestRunOptions_Applies*`, `TestRunOptions_ComposesSecurityOpt`, `TestRunOptions_DefaultsAreEmpty`, `TestRunOptions_NoPrivilegedField`) that fail to compile because the fields don't exist.
  - GREEN: Appended 7 fields to `RunOptions` (after existing `Cmd []string`), added the `// --- Phase 2 sandbox fields ---` plumbing block in `Run()` between resource limits and `ContainerCreate`, composing `SecurityOpt` from `NoNewPrivs` + `SeccompProfile`.
- **Test count:** 10 new subtests, all green.

### Task 2: Deterministic container naming helpers

- **Files:** `api/pkg/docker/naming.go` (new), `api/pkg/docker/naming_test.go` (new)
- **Commits:** `c54c4ae` (RED) → `3d3d137` (GREEN)
- **Approach:** TDD RED→GREEN with a 100-iteration property test for the Build/Parse roundtrip.
- **Test count:** 9 new tests (one is a 100-iteration property test), all green.

## Final RunOptions Field List

Existing (Phase 1):

- `Image string`
- `Name string`
- `Env map[string]string`
- `Mounts []string`
- `Network string`  ← already maps to `HostConfig.NetworkMode` (unchanged)
- `Memory int64`
- `CPUs int64`
- `PidsLimit int64`
- `Remove bool`
- `Labels map[string]string`
- `Cmd []string`

New (Plan 02-02):

- `SeccompProfile string` → `HostConfig.SecurityOpt` (`seccomp=<path>`)
- `ReadOnlyRootfs bool` → `HostConfig.ReadonlyRootfs` (note single-R Docker spelling)
- `Tmpfs map[string]string` → `HostConfig.Tmpfs`
- `CapDrop []string` → `HostConfig.CapDrop`
- `CapAdd []string` → `HostConfig.CapAdd`
- `NoNewPrivs bool` → `HostConfig.SecurityOpt` (`no-new-privileges:true`)
- `Runtime string` → `HostConfig.Runtime`

Absent (SBX-05 invariant):

- `Privileged` — NEVER added; enforced by `TestRunOptions_NoPrivilegedField` reflect check.

## Verified HostConfig Field-Name Spellings

| RunOptions | HostConfig target | Docker SDK spelling |
|---|---|---|
| `ReadOnlyRootfs` | `ReadonlyRootfs` | single lowercase R, no separator |
| `Tmpfs` | `Tmpfs` | `map[string]string` target→opts |
| `CapDrop` | `CapDrop` | `strslice.StrSlice` (accepts `[]string`) |
| `CapAdd` | `CapAdd` | `strslice.StrSlice` |
| `NoNewPrivs` | `SecurityOpt += "no-new-privileges:true"` | string slice entry |
| `SeccompProfile` | `SecurityOpt += "seccomp="+path` | string slice entry |
| `Runtime` | `Runtime` | `""` means runc default |

## Naming Format — Cross-Phase Contract

```
playground-<user_uuid>-<session_uuid>
```

- Total length: 84 chars (`playground-` 11 + uuid 36 + `-` 1 + uuid 36)
- Well under `maxContainerIDLen = 128` (Phase 1 validator).
- `BuildContainerName` output passes `validateContainerID` (verified by `TestBuildContainerName_PassesValidator`).
- `ParseContainerName` and `IsPlaygroundContainerName` both tolerate a leading `/` (Docker Inspect prefix).
- Cross-phase consumers: Plan 04 session handler import, Plan 05 smoke test assertion, Phase 5 reconciliation filter, Phase 7.5 hardening path.

## Test Count

| Stage | Total PASS entries (parents + subtests) |
|---|---|
| Phase 1 baseline | 49 |
| Plan 02-02 RED (Task 1, compile failure) | 49 (test-side compile error) |
| Plan 02-02 GREEN (Task 1) | 69 (+10 new RunOptions subtests + counts) |
| Plan 02-02 GREEN (Task 2) | 89 (+9 naming tests, one 100-iteration property test) |

Exact parent-test PASS count at end of plan: **38 parent tests**, **89 total PASS entries** reported by `go test -v`.

## Deviations from Plan

None — plan executed exactly as written. No Rule 1/2/3 auto-fixes needed.

## Verification Results

- `cd api && go build ./...` — exits 0
- `cd api && go test ./pkg/docker/ -count=1 -short` — exits 0 (ok 0.518s)
- `cd api && go vet ./pkg/docker/...` — exits 0
- `grep -c 'Privileged' api/pkg/docker/runner.go` — returns 0 (SBX-05 invariant satisfied)
- `grep -c 'SeccompProfile string' api/pkg/docker/runner.go` — 1
- `grep -c 'ReadOnlyRootfs bool' api/pkg/docker/runner.go` — 1
- `grep -c 'Tmpfs map\[string\]string' api/pkg/docker/runner.go` — 1
- `grep -c 'CapDrop \[\]string' api/pkg/docker/runner.go` — 1
- `grep -c 'CapAdd \[\]string' api/pkg/docker/runner.go` — 1
- `grep -c 'NoNewPrivs bool' api/pkg/docker/runner.go` — 1
- `grep -c 'Runtime string' api/pkg/docker/runner.go` — 1
- `grep -c 'hostCfg.ReadonlyRootfs = opts.ReadOnlyRootfs' api/pkg/docker/runner.go` — 1
- `grep -c 'no-new-privileges:true' api/pkg/docker/runner.go` — 1
- `grep -c '"seccomp="' api/pkg/docker/runner.go` — 1
- `naming.go` contains `const containerNamePrefix = "playground-"`, `func BuildContainerName`, `func ParseContainerName`, `func IsPlaygroundContainerName` — all 1
- Integration test `TestDockerIntegration_RunInspectStopRemove` remains skipped under `-short` (requires Docker daemon); unchanged.

## Known Stubs

None. All fields are additive knobs intended to be populated by future plans (Plan 04 session handler, Plan 02-03 recipes, Phase 7.5 hardening); the plan explicitly designs these as "knobs" to be filled in later waves. This is not a stub — it's the planned interface surface.

## Commits

| Hash | Type | Message |
|---|---|---|
| `59a1ea8` | test | test(02-02): add failing tests for new RunOptions sandbox fields |
| `065a78b` | feat | feat(02-02): plumb sandbox fields from RunOptions to HostConfig |
| `c54c4ae` | test | test(02-02): add failing tests for container naming helpers |
| `3d3d137` | feat | feat(02-02): add deterministic container naming helpers |

## Self-Check: PASSED

- `api/pkg/docker/runner.go` — modified, contains all 7 sandbox fields and plumbing (FOUND)
- `api/pkg/docker/runner_test.go` — contains 10 new `TestRunOptions_*` subtests (FOUND)
- `api/pkg/docker/naming.go` — created, contains 3 helpers + prefix constant (FOUND)
- `api/pkg/docker/naming_test.go` — created, contains 8 test functions incl. 100-iteration property test (FOUND)
- Commit `59a1ea8` — FOUND
- Commit `065a78b` — FOUND
- Commit `c54c4ae` — FOUND
- Commit `3d3d137` — FOUND
