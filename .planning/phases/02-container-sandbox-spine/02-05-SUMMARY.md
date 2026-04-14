---
phase: 02-container-sandbox-spine
plan: 05
subsystem: api/internal/session (HTTP + bridge) + api/internal/server + api/cmd/server
tags: [http-handlers, chat-bridge, session-api, ses-01, ses-04, cht-01, w3-fix]
requires:
  - "Plan 02-01 ap-base image (/run/ap FIFOs + /run/secrets bind-mount target + gosu drop)"
  - "Plan 02-02 docker.BuildContainerName + RunOptions sandbox plumbing"
  - "Plan 02-03 image tags ap-picoclaw:v0.1.0-c7461f9 and ap-hermes:v0.1.0-5621fc4"
  - "Plan 02-04 session.Store / SecretWriter / DevEnvSource / DefaultSandbox / recipes.AllRecipes / docker.Runner.ExecWithStdin"
  - "Phase 1 middleware.AuthMiddleware + middleware.GetUserID (Plan 01-01)"
provides:
  - "session.Bridge with SendMessage routing ChatIOFIFO ↔ ChatIOExec"
  - "session.ErrTimeout (bridge timeout, mapped to HTTP 504 by handler)"
  - "session.RunnerExec interface (bridge dependency, satisfied by *docker.Runner)"
  - "session.Handler with POST /api/sessions, POST /api/sessions/:id/message, DELETE /api/sessions/:id"
  - "session.SessionStore, session.SecretProvisioner, session.ContainerRunner interfaces (handler-side mockability)"
  - "server.WithSessionHandler functional option"
  - "main.go wiring: session.Store + SecretWriter + Bridge + Handler constructed once at startup"
affects:
  - "Plan 02-06 smoke test: calls the three endpoints end-to-end to prove the phase hypothesis"
  - "Phase 5 reconciliation + Temporal swap: the HTTP shape stays stable; internals swap from sync runner calls to workflow signals"
  - "Phase 4 recipe catalog expansion: Bridge already dispatches by mode, new recipes slot in without bridge changes"
tech-stack:
  added: []
  patterns:
    - "Narrow-interface mockability: SessionStore / SecretProvisioner / ContainerRunner accept in-package mocks so handler_test.go skips embedded-postgres"
    - "Stdin-piped FIFO write (`sh -c 'cat >> /run/ap/chat.in'` + ExecWithStdin) so user text never reaches a shell argv position"
    - "slices.Clone(execCmd) then append(_, text) — user message becomes a single argv element passed directly to dockerd"
    - "Best-effort idempotent delete chain: Stop → Remove → Cleanup → UpdateStatus, each logged on error, none short-circuit"
    - "userFromCtx delegates to middleware.GetUserID (W3 fix — does not re-implement context lookup)"
    - "W3 compile-time guard: `var _ SessionStore = (*Store)(nil)` and `var _ SecretProvisioner = (*SecretWriter)(nil)` catch interface drift at build time"
key-files:
  created:
    - api/internal/session/bridge.go
    - api/internal/session/bridge_test.go
    - api/internal/session/handler.go
    - api/internal/session/handler_test.go
    - .planning/phases/02-container-sandbox-spine/deferred-items.md
  modified:
    - api/internal/server/server.go
    - api/cmd/server/main.go
decisions:
  - "Handler consumes narrow interfaces (SessionStore / SecretProvisioner / ContainerRunner) rather than concrete types so unit tests never need embedded-postgres; production wires concrete *Store / *SecretWriter / *docker.Runner"
  - "Bridge.fifoMode polls chat.out every 25ms bounded by recipe.ChatIO.ResponseTimeout via an outer context timeout; no long-poll read on the FIFO"
  - "ANSI stripping is a hand-rolled CSI-letter terminator (covers `\\x1b[<params><letter>` form); full ECMA-48 parsing deferred to Phase 4 if new recipes need OSC/DCS"
  - "main.go skips session wiring entirely when docker.NewRunner fails, mirroring the TEMPORAL_HOST-empty degrade pattern — keeps `go run` against laptops without Docker working"
  - "W3 fix: userFromCtx in handler.go:340 calls middleware.GetUserID(c) — the handler never touches c.Get(\"user_id\") directly"
metrics:
  duration: "~20 minutes"
  completed: 2026-04-14
  tasks_completed: 2
  commits: 4
---

# Phase 02 Plan 05: Session HTTP Handlers + Chat Bridge Summary

Landed the visible API layer for the phase's hypothesis proof: three HTTP
handlers (`POST /api/sessions`, `POST /api/sessions/:id/message`, `DELETE
/api/sessions/:id`) plus the chat bridge that dispatches to either the
FIFO path (picoclaw) or the per-message docker exec path (Hermes) based
on the recipe's `ChatIO.Mode`. Wired into `server.New` via the
functional-options pattern (`server.WithSessionHandler`) and constructed
once at startup in `cmd/server/main.go`. Plan 06 calls these endpoints
end-to-end; Phase 5 swaps the synchronous internals for Temporal
workflows without touching the HTTP shape.

## HTTP Contract

### `POST /api/sessions`

**Request:**
```json
{ "recipe": "picoclaw", "model_provider": "anthropic", "model_id": "claude-3-5-sonnet" }
```

**Responses:**

| Code | When |
|------|------|
| 201 Created | Session row inserted, secrets provisioned, container running. Body: `{"id": "<uuid>", "status": "running", "container_id": "<docker id>"}` |
| 400 Bad Request | Missing/empty required fields, unknown recipe, or provider not supported by recipe |
| 401 Unauthorized | No auth cookie / `middleware.GetUserID` returns error |
| 409 Conflict | `Store.Create` returned `ErrConflictActive` (partial unique index fired — user already has an active session) |
| 500 Internal Server Error | Store / runner / update failure after the session row was created (best-effort rollback: cleanup secrets + mark failed) |
| 503 Service Unavailable | `SecretWriter.Provision` returned `ErrSecretMissing` (e.g. `AP_DEV_BYOK_KEY` unset) |

### `POST /api/sessions/:id/message`

**Request:**
```json
{ "text": "hello there" }
```

**Responses:**

| Code | When |
|------|------|
| 200 OK | `Bridge.SendMessage` returned a reply. Body: `{"text": "<agent reply>"}` |
| 400 Bad Request | Invalid UUID, empty text, or bad JSON |
| 401 Unauthorized | Missing / bad auth |
| 403 Forbidden | Session belongs to a different user (ownership check) |
| 404 Not Found | `Store.Get` returned nil |
| 409 Conflict | Session status != "running" or container_id is nil/empty |
| 413 Payload Too Large | `len(text) > 16384` (maxMessageLen guard) |
| 502 Bad Gateway | Bridge returned a non-timeout error |
| 504 Gateway Timeout | Bridge returned `ErrTimeout` (bridge wraps context with `recipe.ChatIO.ResponseTimeout`) |

### `DELETE /api/sessions/:id`

**Responses:**

| Code | When |
|------|------|
| 200 OK | Best-effort cleanup chain completed. Body: `{"status": "stopped"}` |
| 400 Bad Request | Invalid UUID |
| 401 Unauthorized | Missing / bad auth |
| 403 Forbidden | Session belongs to a different user |
| 404 Not Found | No such session row |
| 500 Internal Server Error | `UpdateStatus(stopped)` failed after the container was torn down |

Delete is idempotent with respect to missing containers / missing secret
dirs — individual steps log and continue so a half-destroyed session can
always be driven fully to `stopped`.

## Wiring Chain

```
cmd/server/main.go
    ├─ docker.NewRunner(logger)                           [skip session wiring if Docker daemon absent]
    ├─ session.NewDevEnvSource()                          [reads AP_DEV_BYOK_KEY]
    ├─ session.NewSecretWriter(secretSource)              [SecretWriter at DefaultSecretBaseDir]
    ├─ session.NewStore(db.Pool)                          [pgxpool-backed Store]
    ├─ session.NewBridge(runner)                          [Bridge with RunnerExec adapter]
    ├─ session.NewHandler(store, runner, writer, bridge, logger)
    └─ server.WithSessionHandler(sessHandler)             [appended to server.New opts]
        │
        ▼
internal/server/server.go  (New)
    └─ if s.sessionHandler != nil { s.sessionHandler.Register(authed) }
        │
        ▼
internal/session/handler.go  (Register)
    ├─ POST   /api/sessions              → h.create
    ├─ POST   /api/sessions/:id/message  → h.message
    └─ DELETE /api/sessions/:id          → h.delete
```

All three routes sit behind the existing Phase 1 `middleware.AuthMiddleware`
because `sessionHandler.Register` is called on the `authed` group built
inside `server.go` after `WithDevAuth` mounts it (guarded by
`s.devAuth != nil && s.sessionProvider != nil`). A test or deploy that
omits `WithDevAuth` will also skip `WithSessionHandler`'s routes — the
same degrade pattern Phase 1 uses for `/api/me`.

## W3 Fix Verification

`userFromCtx` at `api/internal/session/handler.go:340` reads:

```go
func userFromCtx(c echo.Context) (uuid.UUID, bool) {
    id, err := middleware.GetUserID(c)
    if err != nil {
        return uuid.Nil, false
    }
    return id, true
}
```

The handler **never** calls `c.Get("user_id")` directly. This is the
Phase 1 contract — any drift in `middleware.AuthMiddleware`'s context
key automatically propagates to session handlers for free.

Grep gates:

- `grep -c 'middleware.GetUserID' api/internal/session/handler.go` → 3
- `grep -c 'func GetUserID' api/internal/middleware/auth.go` → 1 (Phase 1 contract still present)

## Bridge Dispatch

```
SendMessage(ctx, containerID, recipe, text)
    ├─ ctx wrapped with recipe.ChatIO.ResponseTimeout
    │
    ├─ recipe.ChatIO.Mode == ChatIOExec   (hermes)
    │   ├─ cmd := append(slices.Clone(recipe.ChatIO.ExecCmd), text)
    │   ├─ runner.Exec(ctx, containerID, cmd)
    │   └─ stripANSI(trimmed stdout)                        [hermes TUI is colored]
    │
    └─ recipe.ChatIO.Mode == ChatIOFIFO   (picoclaw)
        ├─ runner.ExecWithStdin(ctx, containerID,
        │       ["sh","-c","cat >> /run/ap/chat.in"],
        │       bytes.NewReader(text+"\n"))                  [text is STDIN, not argv]
        └─ poll runner.Exec(["timeout","5","head","-n","1","/run/ap/chat.out"])
            every 25ms until non-empty or ctx.Done()
```

**T-02-04 / T-02-04b mitigation verified:**

- FIFO path: the user text flows over stdin to `cat`; the shell only
  sees the literal string `cat >> /run/ap/chat.in`. `TestBridge_TextWithShellMetacharacters`
  proves that `"; rm -rf / $(whoami) `id`"` does NOT expand — the mock
  runner captures the literal bytes in the stdin buffer.
- Exec path: the user text becomes argv element `[3]` and the Docker
  SDK passes the `[]string` to dockerd over the HTTP API — there is no
  shell between Go and the container's exec layer. `TestBridge_TextWithShellMetacharacters`
  asserts `call.cmd[3] == malicious` (unchanged bytes).

## Test Count Delta

| File | New Tests |
|------|-----------|
| `api/internal/session/bridge_test.go` | 5 (FIFOMode, ExecMode, Timeout, TextWithShellMetacharacters, StripsANSI) |
| `api/internal/session/handler_test.go` | 9 (CreateSession_Success, _UnknownRecipe, _NoAuth, _OneActive, _MissingSecret, DeleteSession, DeleteSession_OtherUser, Message_Timeout, Message_NotRunning) |

Full test run (`go test ./... -count=1 -short`):

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

All packages green. `go build ./...` and `go vet ./...` both clean.

## Deviations from Plan

### None (Rules 1-3)

Plan executed as written. No auto-fixes needed in the Task 1 / Task 2 code paths.

### Scope boundary note — pre-existing `TestMigrator_Idempotent` failure

Under the full suite (without `-short`), `TestMigrator_Idempotent` in
`api/pkg/migrate/migrate_test.go:116` fails with `expected 1, got 2`.
This is caused by Plan 02-04 adding `002_sessions.sql` — the test's
assertion was pinned to the Phase 1 migration count.

**Verified pre-existing:** I confirmed this by `git stash`-ing Plan 05's
changes and re-running the migrate test on the clean tree at Plan 04's
tip — same failure. NOT caused by Plan 05.

**Scope boundary:** This is out of scope for Plan 05 per the deviation
rules (only auto-fix issues directly caused by current task changes).
Plan 05's success criterion is `go test ./... -short` (which passes);
the failing test has a `testing.Short()` skip guard.

**Logged:** `.planning/phases/02-container-sandbox-spine/deferred-items.md`.
Belongs in a 02-04 follow-up or a Phase 02 cleanup pass — the fix is a
one-line assertion change to `GreaterOrEqual(t, count, 1)` or a
length-of-`EmbeddedMigrations()` check.

## Auth Gates

None. No external auth needed for Plan 05 execution — all tests ran
against in-process Echo + mocks. The HTTP auth gate (cookie-based) is
exercised by `TestHandler_CreateSession_NoAuth` (expects 401 when the
mock middleware sees no `X-Test-Auth` header).

## Known Stubs

None. Every code path in the handler reaches production primitives:
`Store.Create`, `SecretWriter.Provision`, `docker.Runner.Run`, etc.
The handler's interfaces are mockability seams, not placeholders —
production wiring passes the concrete types (verified by the
`var _ SessionStore = (*Store)(nil)` and `var _ SecretProvisioner = (*SecretWriter)(nil)`
compile-time checks in handler.go).

## Threat Flags

None new. Plan 05's code adds HTTP routes but no new trust boundaries
beyond what the plan's `<threat_model>` already covers
(T-02-02 / T-02-04 / T-02-04b / T-02-05 / T-02-11 / T-02-13 — all
mitigated as designed).

Verification: `grep -cE 'AnthropicKey|AP_DEV_BYOK_KEY' api/internal/session/handler.go`
returns 0 (T-02-13: handler never references the raw key field or env
var — the SecretWriter from Plan 04 owns that surface).

## Open Follow-ups for Plan 06

1. **Smoke test drives the full loop:** `scripts/smoke-e2e.sh` (Plan 06)
   will `curl` all three endpoints against a live stack. No further
   code changes to Plan 05 expected.
2. **First-run Hermes cold start:** When Hermes is invoked for the
   first time via ChatIOExec, the `hermes chat -q` command may take
   several seconds to warm up (Playwright + uv venv). The recipe's
   `ResponseTimeout` is 120s — generous, but Plan 06 should confirm
   the first message completes in-budget.
3. **picoclaw FIFO RTT against a real agent:** Spike 3 proved FIFO
   RTT in an empty alpine container. Plan 06 is the first time the
   FIFO path is exercised against a real picoclaw REPL. If chat.out
   reads come back empty, the `timeout 5 head -n 1` probe may need
   tuning — flagged for Plan 06 investigation.
4. **Docker daemon unavailable in CI:** `main.go` degrades gracefully
   when `docker.NewRunner` fails (logs a warning, skips session
   wiring). This is an intentional dev-loop affordance, not a bug.
   Plan 06's smoke test explicitly requires Docker up and will
   error-exit early if the daemon is not reachable.
5. **Phase 5 Temporal swap:** The handler's synchronous
   `runner.Run / UpdateContainer` chain will become a Temporal
   workflow signal in Phase 5. The HTTP contract above is frozen —
   Phase 5 must not change request/response shapes.

## Commits

| Hash | Type | Message |
|------|------|---------|
| `1d00688` | test | test(02-05): add failing tests for chat bridge (FIFO + exec) |
| `d2c12d6` | feat | feat(02-05): chat bridge for ChatIOFIFO + ChatIOExec |
| `ed86eef` | test | test(02-05): add failing tests for session HTTP handlers |
| `42880c5` | feat | feat(02-05): session HTTP handlers + main.go wiring |

## Self-Check

- `api/internal/session/bridge.go` — FOUND
- `api/internal/session/bridge_test.go` — FOUND
- `api/internal/session/handler.go` — FOUND
- `api/internal/session/handler_test.go` — FOUND
- `api/internal/server/server.go` — MODIFIED (WithSessionHandler option + Register call)
- `api/cmd/server/main.go` — MODIFIED (session wiring chain)
- `.planning/phases/02-container-sandbox-spine/deferred-items.md` — FOUND
- Commit `1d00688` — FOUND
- Commit `d2c12d6` — FOUND
- Commit `ed86eef` — FOUND
- Commit `42880c5` — FOUND
- `cd api && go build ./...` — exits 0
- `cd api && go vet ./...` — exits 0
- `cd api && go test ./... -count=1 -short` — exits 0
- `grep -c 'middleware.GetUserID' api/internal/session/handler.go` — 3 (≥1 required, W3 fix)
- All other plan grep gates: verified (see deviations section)

## Self-Check: PASSED
