---
phase: 02-container-sandbox-spine
plan: 04
subsystem: api/internal/session + api/internal/recipes + api/pkg/migrate
tags: [foundations, sessions-migration, recipes, sandbox-defaults, byok, pgxpool, ses-01, ses-04, dev-byok]
requires:
  - "Plan 02-01 ap-base image (/run/secrets target dir, /run/ap FIFOs, gosu drop)"
  - "Plan 02-02 docker.RunOptions sandbox fields (CapDrop, NoNewPrivs, ReadOnlyRootfs, Tmpfs, Runtime, SeccompProfile, CapAdd)"
  - "Plan 02-03 image tags ap-picoclaw:v0.1.0-c7461f9 and ap-hermes:v0.1.0-5621fc4 (literal string contract)"
  - "Phase 1 pkg/migrate embedded SQL migrator + users table FK target"
  - "Phase 1 pkg/docker Runner.Exec pattern (ExecCreate → ExecAttach → ExecInspect) for ExecWithStdin to mirror"
provides:
  - "sessions table (migration 002) + partial unique index for one-active-per-user"
  - "internal/recipes.AllRecipes catalog with picoclaw + hermes entries"
  - "internal/recipes.ChatIOMode (ChatIOFIFO, ChatIOExec) + ChatIO + ResourceOverrides + Recipe + Get(name)"
  - "internal/session.DefaultSandbox() hardened docker.RunOptions baseline"
  - "internal/session.DevEnvSource + SecretSource interface + ErrSecretMissing"
  - "internal/session.SecretWriter with Provision / Cleanup / BindMountSpec (Pitfall 6 perms)"
  - "internal/session.Store with Create / Get / UpdateStatus / UpdateContainer and ErrConflictActive translation of pg error 23505"
  - "pkg/docker.Runner.ExecWithStdin(ctx, cid, cmd, io.Reader) for the Plan 05 FIFO chat bridge"
affects:
  - "Plan 02-05 HTTP handler: imports recipes.Get, session.NewStore, session.NewDevEnvSource, session.NewSecretWriter, session.DefaultSandbox, runner.ExecWithStdin (no further code changes to plan 04 needed)"
  - "Plan 02-06 smoke test: sessions table present, recipes importable, secret writer produces correct file modes"
  - "Phase 5 reconciliation loop: can SELECT FROM sessions and rebuild container name via docker.BuildContainerName"
  - "Phase 4 recipe catalog expansion: recipes package is the insertion point"
tech-stack:
  added:
    - "github.com/jackc/pgx/v5/pgconn (already transitively present) — used for typed pg error code inspection"
  patterns:
    - "Hardcoded catalog as map[string]*Recipe with typed ChatIOMode constants for bridge-strategy dispatch"
    - "SecretSource interface + per-provider implementations (DevEnvSource in Phase 2, KMS source in Phase 3+)"
    - "Host secret dir 0700 / file 0644 chain for Docker userns-remap compatibility (Pitfall 6)"
    - "pgconn.PgError + errors.As translation of Postgres SQLSTATE 23505 → domain ErrConflictActive"
    - "Split ExecWithStdin from Exec so the FIFO chat bridge path is additive and non-invasive to existing Exec callers"
key-files:
  created:
    - api/pkg/migrate/sql/002_sessions.sql
    - api/internal/recipes/recipes.go
    - api/internal/recipes/recipes_test.go
    - api/internal/session/defaults.go
    - api/internal/session/defaults_test.go
    - api/internal/session/secrets.go
    - api/internal/session/secrets_test.go
    - api/internal/session/store.go
  modified:
    - api/pkg/docker/runner.go
    - api/pkg/docker/runner_test.go
decisions:
  - "sessions table is distinct from Phase 1 agents table (Open Question 1 resolved per CONTEXT D-26) — agents = saved configuration, sessions = runtime instance"
  - "Phase 2 enforces one-active-session via a single Postgres partial unique index; Phase 5 will add Redis SETNX on top for race resolution"
  - "Recipe ResourceOverrides exposes ONLY Memory/CPUs/PidsLimit; security knobs (CapDrop, ReadOnlyRootfs, NoNewPrivs) are NOT overridable per recipe — T-02-02 mitigation"
  - "DevEnvSource is restricted to anthropic_key in Phase 2; adding more providers belongs to Phase 4+"
  - "SecretWriter.BindMountSpec always returns a path under DefaultSecretBaseDir (/tmp/ap/secrets), NOT w.BaseDir — tests override BaseDir for isolation, production bind-mounts go through the real path"
  - "ExecWithStdin is a new method, not a modification of Exec, so existing Exec callers see zero behavioral change"
  - "Store.Get returns (nil, nil) on pgx.ErrNoRows — 404 translation is a handler-layer concern, not a storage-layer one"
metrics:
  duration: "~18 minutes wall-clock"
  completed: 2026-04-14
  tasks_completed: 2
  commits: 6
---

# Phase 02 Plan 04: Session Foundations Summary

Landed the foundations half of the original Plan 04 (splitted 04 = foundations, 05 = API surface per W1 checker): 10 files across sessions migration, recipes Go catalog, hardened sandbox defaults, dev BYOK secret writer + source, pgxpool-backed session store, and a new `Runner.ExecWithStdin` method. No HTTP handlers. No architectural deviations. 6 commits, green unit tests, `go build ./...` and `go vet ./...` clean.

## Tasks Completed

### Task 1: Sessions migration + recipes Go package + sandbox defaults

- **Files:** `api/pkg/migrate/sql/002_sessions.sql`, `api/internal/recipes/recipes.go`, `api/internal/recipes/recipes_test.go`, `api/internal/session/defaults.go`, `api/internal/session/defaults_test.go`
- **Commits:** `2cd7058` (RED recipes) → `79c5592` (GREEN recipes + migration) → `ead81a4` (DefaultSandbox)
- **Approach:** TDD RED→GREEN for both recipes and defaults. 5 new recipes tests + 2 new session-defaults tests, all green.

### Task 2: Session store + dev BYOK secret writer + ExecWithStdin runner method

- **Files:** `api/internal/session/store.go`, `api/internal/session/secrets.go`, `api/internal/session/secrets_test.go`, `api/pkg/docker/runner.go`, `api/pkg/docker/runner_test.go`
- **Commits:** `bb52d9d` (RED ExecWithStdin) → `d08c322` (GREEN ExecWithStdin) → `2e7804a` (store + secrets GREEN)
- **Approach:** TDD RED→GREEN for secrets + ExecWithStdin. Store has no unit tests per plan direction (integration test is Plan 06 against a real DB).

## Sessions Table DDL (as deployed)

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipe_name    TEXT NOT NULL,
    model_provider TEXT NOT NULL,
    model_id       TEXT NOT NULL,
    container_id   TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status  ON sessions(status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_one_active_per_user
    ON sessions(user_id)
    WHERE status IN ('pending', 'provisioning', 'running');
```

**Distinct from the Phase 1 `agents` table** — `agents` holds saved per-user configuration (recipe + model + key source); `sessions` holds a single runtime instance (which container is currently up for this user). Phase 4 may later add a nullable `agent_id` FK from sessions → agents once the recipe → agent → session chain is wired, but Phase 2 ships with no FK and hardcoded recipe name strings.

**Open Question 1 resolved:** kept the two tables distinct per CONTEXT D-26. Rationale: their lifecycles and cardinalities differ (many sessions per agent over time, one row per user per active session).

## recipes Package Final Shape

**Types:**

- `type ChatIOMode string` with two constants: `ChatIOFIFO = "stdin_fifo"`, `ChatIOExec = "exec_per_message"`.
- `type ChatIO struct { Mode ChatIOMode; LaunchCmd []string; ExecCmd []string; ResponseTimeout time.Duration }`
- `type ResourceOverrides struct { Memory, CPUs, PidsLimit int64 }` — security knobs deliberately absent
- `type Recipe struct { Name, Image string; ChatIO ChatIO; RequiredSecrets []string; EnvOverrides map[string]string; SupportedProviders []string; ResourceOverrides ResourceOverrides }`

**Catalog:**

| Key | Image | ChatIO Mode | LaunchCmd / ExecCmd | ResourceOverrides | EnvOverrides |
|---|---|---|---|---|---|
| `picoclaw` | `ap-picoclaw:v0.1.0-c7461f9` | FIFO | `[picoclaw, agent, --session, cli:default]` | — | `PICOCLAW_PROVIDER=anthropic` |
| `hermes`   | `ap-hermes:v0.1.0-5621fc4`   | Exec | `[hermes, chat, -q]` (user msg appended at call time) | Memory 2 GiB | `HERMES_INFERENCE_PROVIDER=anthropic`, `HERMES_QUIET=1` |

Both have `RequiredSecrets=[anthropic_key]` and `SupportedProviders=[anthropic]`.

**Lookup:** `func Get(name string) *Recipe` — returns nil if unknown.

**Image-tag contract:** The two tag strings match Plan 02-03's built images exactly (`grep -c 'ap-picoclaw:v0.1.0-c7461f9'` = 1; `grep -c 'ap-hermes:v0.1.0-5621fc4'` = 1).

## DefaultSandbox Field Values

```go
docker.RunOptions{
    ReadOnlyRootfs: true,
    Tmpfs: map[string]string{
        "/tmp": "rw,noexec,nosuid,size=128m",
        "/run": "rw,noexec,nosuid,size=16m",
    },
    CapDrop:    []string{"ALL"},
    CapAdd:     nil,
    NoNewPrivs: true,
    Runtime:    "",            // runc
    Network:    "bridge",
    Memory:     1 << 30,        // 1 GiB
    CPUs:       1_000_000_000,  // 1 vCPU (nanoCPUs)
    PidsLimit:  256,
    Remove:     true,
    // SeccompProfile: "" — Docker default; Phase 7.5 overrides.
}
```

**Security knobs are unconditional.** Recipe `ResourceOverrides` can only tweak Memory / CPUs / PidsLimit — the struct does not even expose CapDrop / ReadOnlyRootfs / NoNewPrivs, so a malicious recipe author cannot loosen the posture. T-02-02 mitigation.

## secrets.go Injection Chain

```
AP_DEV_BYOK_KEY env var (server process)
    ↓ NewDevEnvSource() reads once
DevEnvSource{AnthropicKey: string}
    ↓ SecretWriter.Provision(sessionID, ["anthropic_key"])
host: /tmp/ap/secrets/<session_id>/                    [mode 0700]
      └── anthropic_key                                 [mode 0644]
    ↓ SecretWriter.BindMountSpec(sessionID) returns
      "/tmp/ap/secrets/<session_id>:/run/secrets:ro"
    ↓ Plan 05 handler adds to RunOptions.Mounts
Docker bind-mount (read-only)
    ↓
container: /run/secrets/                                [image dir 0500 from Plan 01 ap-base]
           └── anthropic_key                             [readable by container uid 10000]
    ↓ ap-base entrypoint.sh reads /run/secrets/anthropic_key into AGENT_ENV array
    ↓ launches agent via: env "${AGENT_ENV[@]}" <cmd>
agent process (picoclaw / hermes) with ANTHROPIC_API_KEY in its environment
```

**Pitfall 6 — userns-remap permissions:** the file MUST be 0644 because Docker's userns-remap maps in-container uid 10000 to host uid 110000+. The host kernel sees the container's read coming from a different uid than the API server that wrote the file, so world-readability is required. The enclosing directory is 0700 because only the API server lists it (the container reads the specific file by name via the bind mount, not by directory traversal).

**T-02-01 mitigation:** SecretWriter is the only code path that writes the raw key to disk. The key is never logged (verified: `grep -n "AnthropicKey" api/internal/session/` shows only field declarations and test literals, no `.Msg()` / `.Str()` / `fmt.Print*` calls). The key never ends up in PID 1's environment — ap-base's entrypoint reads the file into a bash array and passes it via `env "${AGENT_ENV[@]}"` to the agent process only (Plan 02-01 SUMMARY verifies this).

## Runner.ExecWithStdin

Extends the existing Exec pattern with `AttachStdin: true` + `io.Copy(conn, stdin)` + type-assert-based CloseWrite. Mirrors the error-handling and validation shape of `Exec` exactly. Used by the Plan 05 FIFO chat bridge to write user messages into `/run/ap/chat.in` inside the running container via `sh -c "cat >> /run/ap/chat.in"`.

Three new tests cover: (1) AttachStdin flag set + stdin bytes flow through the hijacked conn; (2) invalid container ID rejected before SDK call; (3) non-zero exit code returns error.

**Compatibility note:** `net.Pipe()` does NOT implement `CloseWrite` — the type-assert fallback in the implementation is specifically so the test mock works. Production `net.TCPConn` from the Docker daemon DOES implement it.

## Test Count Delta

| Package | Before | After | Delta |
|---|---|---|---|
| `internal/recipes` | 0 | 4 | +4 (1 per recipe + all-require + Get lookup) |
| `internal/session` (defaults) | 0 | 2 | +2 |
| `internal/session` (secrets) | 0 | 6 | +6 |
| `pkg/docker` (ExecWithStdin) | 89* | 92* | +3 |

*`pkg/docker` baseline after Plan 02-02 was 89 PASS entries (per that plan's SUMMARY); Plan 04 adds 3 ExecWithStdin sub-tests.

**Full `go test ./... -count=1 -short`:** all packages green:

```
ok  internal/config
ok  internal/handler
ok  internal/middleware
ok  internal/recipes
ok  internal/server
ok  internal/session
ok  internal/temporal
ok  pkg/docker
ok  pkg/migrate
```

## Deviations from Plan

None. Plan executed exactly as written. No Rule 1/2/3 auto-fixes needed. A few minor implementation-level notes worth flagging to Plan 05:

1. **Secrets file mode syntax:** Go source uses `0o644` / `0o700` (Go 1.13+ octal literal syntax), not the `0644` / `0700` shown in the plan snippet. The plan's acceptance criterion `grep -c '0644' ...` returns 2 (not 1) because both the `os.WriteFile` mode and the redundant `os.Chmod` defense-in-depth call use it. `grep -c '0700'` returns 2 for the same reason. Both ≥ expected.
2. **DevEnvSource only knows `anthropic_key`:** Per plan. Any other name returns ErrSecretMissing. Plan 05 handler should reject session-create for recipes whose RequiredSecrets include unsupported names.
3. **`NewDevEnvSource` reads env at CALL time, not package init.** The plan says "reads at write-time"; the implementation reads at constructor-call time (once, cached in the returned struct). Functionally equivalent for Phase 2 where the server constructs it once at startup. Plan 05 should construct it once in main and pass it into the handler.

## Threat Flags

None. This plan adds no new network-exposed surface — it's purely in-process Go + local filesystem + Postgres writes. The T-02-01 and T-02-02 threats listed in the plan's `<threat_model>` are mitigated as designed.

## Follow-ups for Plan 05

Plan 05 must wire these primitives into three HTTP handlers (`POST /api/sessions`, `GET /api/sessions/:id`, `DELETE /api/sessions/:id`) plus the chat bridge. Specific touchpoints:

1. **Construct once at server init:**
   ```go
   sessionStore := session.NewStore(pgPool)
   secretSource := session.NewDevEnvSource()
   secretWriter := session.NewSecretWriter(secretSource)
   ```
2. **POST /api/sessions flow:**
   - Validate body → look up recipe via `recipes.Get(body.Recipe)` → 404 if nil.
   - Call `sessionStore.Create(ctx, userID, recipe, provider, modelID)` → 409 on ErrConflictActive.
   - `secretWriter.Provision(sess.ID, recipe.RequiredSecrets)` → on error, `secretWriter.Cleanup(sess.ID)` + update status=failed + 422.
   - Compose `opts := session.DefaultSandbox()`, overlay recipe.ResourceOverrides, append `secretWriter.BindMountSpec(sess.ID)` to `opts.Mounts`, set `opts.Name = docker.BuildContainerName(userID, sess.ID)`, set `opts.Image = recipe.Image`, append recipe.EnvOverrides into `opts.Env`.
   - `runner.Run(ctx, opts)` → `sessionStore.UpdateContainer(ctx, sess.ID, containerID, StatusRunning)`.
   - For picoclaw (ChatIOFIFO), the bridge layer uses `runner.ExecWithStdin` against `/run/ap/chat.in`.
   - For hermes (ChatIOExec), the bridge layer uses `runner.Exec` with `recipe.ChatIO.ExecCmd + [userMessage]`.
3. **DELETE /api/sessions/:id flow:** `sess = Get(id)`; ownership check `sess.UserID == userFromCtx` (T-02-11 mitigation — Store.Get deliberately does not enforce this); `runner.Stop` → `runner.Remove`; `secretWriter.Cleanup(sess.ID)`; `sessionStore.UpdateStatus(ctx, sess.ID, StatusStopped)`.
4. **Chat bridge WebSocket:** lives in Plan 05; this plan only provides the primitives.
5. **Integration test for one-active invariant:** Plan 06 runs against a real Postgres. Plan 04 intentionally skipped unit-tests for Store because pgxmock round-tripping would duplicate work that the real DB test in Plan 06 does more credibly.

## Verification

- `cd api && go build ./...` — exits 0
- `cd api && go vet ./...` — exits 0
- `cd api && go test ./... -count=1 -short` — all packages ok
- `cd api && go test ./internal/recipes/ -count=1` — ok
- `cd api && go test ./internal/session/ -count=1` — ok
- `cd api && go test ./pkg/docker/ -count=1 -run TestRunner_ExecWithStdin` — ok
- All plan acceptance criteria grep counts pass (see Task 1 / Task 2 verify blocks in the plan).

## Commits

| Hash | Type | Message |
|---|---|---|
| `2cd7058` | test | test(02-04): add failing tests for recipes package |
| `79c5592` | feat | feat(02-04): hardcoded picoclaw + hermes recipe catalog + sessions migration |
| `ead81a4` | feat | feat(02-04): add DefaultSandbox hardened RunOptions baseline |
| `bb52d9d` | test | test(02-04): add failing tests for runner.ExecWithStdin |
| `d08c322` | feat | feat(02-04): runner.ExecWithStdin for FIFO chat bridge |
| `2e7804a` | feat | feat(02-04): session store + dev BYOK secret writer |

## Self-Check

- `api/pkg/migrate/sql/002_sessions.sql` — FOUND
- `api/internal/recipes/recipes.go` — FOUND
- `api/internal/recipes/recipes_test.go` — FOUND
- `api/internal/session/defaults.go` — FOUND
- `api/internal/session/defaults_test.go` — FOUND
- `api/internal/session/secrets.go` — FOUND
- `api/internal/session/secrets_test.go` — FOUND
- `api/internal/session/store.go` — FOUND
- `api/pkg/docker/runner.go` — MODIFIED (ExecWithStdin added)
- `api/pkg/docker/runner_test.go` — MODIFIED (3 new ExecWithStdin tests)
- Commit `2cd7058` — FOUND (git log verified)
- Commit `79c5592` — FOUND
- Commit `ead81a4` — FOUND
- Commit `bb52d9d` — FOUND
- Commit `d08c322` — FOUND
- Commit `2e7804a` — FOUND

## Self-Check: PASSED
