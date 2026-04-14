---
phase: 02-container-sandbox-spine
plan: 06
subsystem: scripts + api/internal/session (integration tests) + .env.example
tags: [smoke-test, integration-test, hypothesis-proof, byok, ses-01, ses-04, cht-01, checkpoint-pending]
requires:
  - "Plan 02-01 ap-base image + Makefile build-ap-base target"
  - "Plan 02-03 ap-picoclaw:v0.1.0-c7461f9 + ap-hermes:v0.1.0-5621fc4 recipe overlays + build-picoclaw / build-hermes Makefile targets"
  - "Plan 02-04 session.Store + ErrConflictActive + partial unique index on 002_sessions.sql"
  - "Plan 02-05 session HTTP handlers (POST / POST / DELETE /api/sessions*) behind dev cookie auth"
  - "Phase 1 /api/dev/login dev auth stub + embedded-postgres test harness pattern (pkg/migrate/migrate_test.go)"
provides:
  - "scripts/smoke-e2e.sh: end-to-end orchestration script that proves the Phase 2 hypothesis end-to-end for a given recipe (picoclaw|hermes)"
  - "api/internal/session/integration_test.go: real-Postgres integration tests for the one-active-per-user invariant (build tag `integration`)"
  - ".env.example: AP_DEV_BYOK_KEY entry with the Phase 2 → Phase 3 hand-off comment"
affects:
  - "make smoke-test target (from Plan 02-01 Makefile) now has something to shell out to"
  - "Phase 5 Temporal swap: the smoke test is the phase-over-phase regression signal — HTTP contract is frozen and this script must keep passing as internals change"
  - "Phase 2 signoff: the live smoke test run + human eyeball of the curl output IS the demo"
tech-stack:
  added: []
  patterns:
    - "SKIPPED-on-unset-env CI pattern: script exits 0 with a clear message when AP_DEV_BYOK_KEY is not present, keeping no-key CI lanes green without touching any skip matrix"
    - "Trap-cleanup chain: in-flight DELETE for the captured session id, force-kill the API process, force-remove any leaked playground-* containers, remove tmp cookie/log files — all idempotent, all run on EXIT/INT/TERM"
    - "Embedded-postgres helper per test file (startEmbeddedPostgres) mirroring pkg/migrate/migrate_test.go rather than extracting to testutil (deferred to Phase 5 when multiple packages need it)"
    - "Integration build tag gate: `//go:build integration` isolates slow/real-DB tests from the default `go test ./...` fast path"
key-files:
  created:
    - scripts/smoke-e2e.sh
    - api/internal/session/integration_test.go
    - .planning/phases/02-container-sandbox-spine/02-06-SUMMARY.md
  modified:
    - .env.example
decisions:
  - "Smoke test accepts ONE argument (agent name) and is invoked twice by `make smoke-test` — simpler than a multi-agent loop inside bash and lets a human run just picoclaw or just hermes when debugging one"
  - "Trap cleanup issues a best-effort DELETE on the captured session id before killing the API process so the teardown path itself is exercised on mid-test failure — catches a class of bugs where the script succeeds but the handler's delete chain is broken"
  - "Embedded-postgres helper duplicated rather than extracted to a shared testutil package because Phase 2 is the only caller; extraction belongs in Phase 5 when reconciliation + workflow tests also need it (YAGNI)"
  - "Model ID defaults to claude-sonnet-4-5 via the AP_SMOKE_MODEL env override — script authoring cannot predict model deprecation dates, so the env hook lets the human checkpoint use whatever Anthropic accepts at run time"
  - "Integration test does NOT spin up the server + handler; it tests session.Store directly. The smoke test (Task 1) is the end-to-end handler coverage; integration_test.go is just the DB-layer invariant proof"
  - "Script deliberately reads AP_DEV_BYOK_KEY only as an existence gate (via `[[ -z ... ]]`) and passes it through to the Go process via env — the script never echoes the key value, and the $API_LOG tmp file is removed on exit (T-02-01 mitigation)"
metrics:
  duration: "~25 minutes wall-clock (autonomous portions)"
  completed: 2026-04-14
  tasks_completed: 2
  tasks_total: 3
  commits: 2
  checkpoint_pending: true
---

# Phase 02 Plan 06: Hypothesis-Proof Smoke Test Summary

Lands the phase's hypothesis-proof scaffolding: an end-to-end smoke test
script (`scripts/smoke-e2e.sh`), a real-Postgres integration test for the
one-active-per-user invariant, and a documented `.env.example` entry for
the dev BYOK key. The autonomous portions are green. The third task —
the human-verification checkpoint where a real Anthropic key is exported
and a human eyeballs the agent's reply — is **pending** because it
requires a live Anthropic API key, Docker daemon, and human approval per
CONTEXT D-34. See §Checkpoint at the bottom.

## Tasks Completed

### Task 1: scripts/smoke-e2e.sh + .env.example — `1de10b2`

**Files:** `scripts/smoke-e2e.sh` (new, 0755), `.env.example` (modified)

**Script shape:**

```
usage: ./scripts/smoke-e2e.sh <picoclaw|hermes>

Steps:
 1. Argument allow-list (picoclaw|hermes only; T-02-12 mitigation)
 2. SKIPPED exit 0 if AP_DEV_BYOK_KEY is unset
 3. Verify / start docker-compose.dev.yml (postgres + redis)
 4. Verify / build ap-base:v0.1.0 and ap-<agent> images
 5. Kill any stale process on :8080, then `go run ./cmd/server/` in BG
 6. Wait up to 60s for /healthz (early-exit if API crashed)
 7. POST /api/dev/login → capture ap_session cookie
 8. POST /api/sessions {recipe, anthropic, claude-sonnet-4-5} → 201 + id
 9. POST /api/sessions/:id/message {text: "...five words..."} → 200 + non-empty
10. DELETE /api/sessions/:id → 200 + "stopped"
11. Assert docker ps -a --filter name=playground- is empty
12. Assert /tmp/ap/secrets/<session_id> is gone
13. trap cleanup on EXIT/INT/TERM: mid-flight DELETE, kill API,
    force-remove leaked containers, delete tmp files, tail API log on fail
```

**Contract checks (acceptance grep gates, all PASS):**

| Gate | Actual |
|------|--------|
| `bash -n scripts/smoke-e2e.sh` exit | 0 |
| `test -x scripts/smoke-e2e.sh` | OK |
| `grep -c AP_DEV_BYOK_KEY scripts/smoke-e2e.sh` | 6 (≥2 required) |
| `grep -c 'POST.*api/sessions' scripts/smoke-e2e.sh` | 6 (≥1 required) |
| `grep -cE 'api/sessions.*message' scripts/smoke-e2e.sh` | 4 (≥1 required) |
| `grep -c 'DELETE.*api/sessions' scripts/smoke-e2e.sh` | 3 (≥1 required) |
| `grep -c playground- scripts/smoke-e2e.sh` | 5 (≥1 required) |
| `grep -c SKIPPED scripts/smoke-e2e.sh` | 2 (≥1 required) |
| `grep -c /tmp/ap/secrets scripts/smoke-e2e.sh` | 3 (≥1 required) |
| `grep -c 'trap cleanup' scripts/smoke-e2e.sh` | 2 (≥1 required) |
| `grep -c AP_DEV_BYOK_KEY .env.example` | 1 (≥1 required) |

**Live dry-run (SKIPPED path):**

```
$ unset AP_DEV_BYOK_KEY; bash scripts/smoke-e2e.sh picoclaw
SKIPPED: AP_DEV_BYOK_KEY not set (export a real Anthropic API key to run the live smoke test)
$ echo $?
0
```

**Bad-agent rejection:**

```
$ bash scripts/smoke-e2e.sh wrongname
error: unknown agent 'wrongname' (expected picoclaw or hermes)
$ echo $?
2
```

**.env.example addition** documents the Phase 2 → Phase 3 hand-off with
two paragraphs: (a) Phase 2 reads this via `session.NewDevEnvSource`,
(b) Phase 3 replaces the env source with the encrypted pgcrypto vault
but the delivery chain (host file → bind mount → tmpfs → entrypoint
reader → agent env) stays identical.

### Task 2: Integration tests for one-active-per-user — `ba269c8`

**File:** `api/internal/session/integration_test.go` (new, `//go:build integration`)

**Helper:** `startEmbeddedPostgres(t)` — ephemeral port, temp
runtime/data/binaries dirs, `migrate.Run(ctx, pool, logger)` to plant
001_baseline.sql + 002_sessions.sql, `t.Cleanup` chain tears down the
postgres process. Mirrors `pkg/migrate/migrate_test.go` pattern exactly
(port-grab-then-close trick to avoid parallel-test collisions).

**FK helper:** `mustCreateUser(t, pool)` inserts a minimal row into the
`users` table (`provider='integration-test'`, `provider_sub`=uuid,
`email`=uuid@example.test) so `sessions.user_id` FK is satisfied.

**Three tests (all PASS against real PG 18.3 via embedded-postgres):**

```
=== RUN   TestSessionLifecycle_OneActivePerUser
--- PASS: TestSessionLifecycle_OneActivePerUser (9.56s)
=== RUN   TestSessionLifecycle_AfterStopAllowsNew
--- PASS: TestSessionLifecycle_AfterStopAllowsNew (10.76s)
=== RUN   TestSessionLifecycle_DistinctUsersConcurrent
--- PASS: TestSessionLifecycle_DistinctUsersConcurrent (10.16s)
PASS
ok  github.com/agentplayground/api/internal/session  30.800s
```

| Test | Invariant |
|------|-----------|
| `TestSessionLifecycle_OneActivePerUser` | Second `Store.Create` for the same user while the first is `status='pending'` returns `session.ErrConflictActive` (translated from Postgres SQLSTATE 23505 by store.go) |
| `TestSessionLifecycle_AfterStopAllowsNew` | After `UpdateStatus(id, StatusStopped)`, a subsequent `Create` for the same user succeeds with a fresh id (partial index only covers pending/provisioning/running) |
| `TestSessionLifecycle_DistinctUsersConcurrent` | Two distinct user_ids each hold one active session simultaneously (index is per-user, not global) |

**Build-tag gate verified:**
- `go test -count=1 -run '^$' ./internal/session/` → `ok [no tests to run]` (default run excludes the file)
- `go test -tags=integration -count=1 ./internal/session/` → runs the three tests

## Sessions Table Invariant — End-to-End Verified

The partial unique index from `002_sessions.sql`:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_one_active_per_user
    ON sessions(user_id)
    WHERE status IN ('pending', 'provisioning', 'running');
```

...now has three real-DB tests exercising its exact behavior: fires on
duplicate-active, clears on stop, scopes per-user. Phase 5's reconciliation
loop and Temporal workflow signaling can trust the invariant without
re-deriving it.

## Deviations from Plan

### None (Rules 1-3)

Plan executed exactly as written for the two autonomous tasks. No
auto-fixes needed. No Rule 4 architectural decisions surfaced.

### Minor implementation notes (not deviations)

1. **Model id default:** The plan suggested `claude-sonnet-4-6` or
   `claude-3-5-sonnet-latest` with a flag to pick whatever the API
   accepts at smoke-test time. Implementation uses `claude-sonnet-4-5`
   as the default (verified via console.anthropic.com available models
   as of 2026-04-14) but exposes the `AP_SMOKE_MODEL` env override so
   the human running the checkpoint can swap it without editing the
   script. This matches the plan's intent exactly — "not hardcode a
   model that's been deprecated."

2. **Seq instead of brace range:** `for i in $(seq 1 60); do` instead of
   `for i in {1..30}; do` — functionally equivalent but brace expansion
   is not POSIX and some sh-compat contexts (e.g. `sh scripts/smoke-e2e.sh`
   via a wrapper) would silently treat it as literal. Seq is safer and
   the timeout was bumped from 30s to 60s so a cold `go run ./cmd/server/`
   compile has room on the first run.

3. **Belt-and-suspenders in trap cleanup:** The trap runs DELETE on the
   captured session id BEFORE killing the API, then force-removes any
   leaked `playground-*` containers AFTER killing the API. This is
   slightly more defensive than the plan snippet (which only did the
   force-remove) and catches a class of bugs where the script succeeds
   through step 5/6 but fails in step 7, leaving a container up. The
   DELETE exercise is the teardown path we actually care about.

4. **Script reads cookie jar via curl -c/-b, not custom cookie parsing:**
   Standard curl-native pattern. The only check is `grep -q ap_session`
   on the cookie jar to fail fast if dev auth changed the cookie name.

## Threat Flags

None new. Plan 06 adds no new trust boundaries:

- `scripts/smoke-e2e.sh` runs on the developer's local machine against
  their own docker daemon and their own Anthropic account. No network
  surface beyond what Plan 05 already exposed.
- The integration test runs against an ephemeral in-process Postgres
  bound to `127.0.0.1:<ephemeral port>` — no external exposure.
- The script deliberately does NOT echo `$AP_DEV_BYOK_KEY` anywhere; the
  only mention is `[[ -z "${AP_DEV_BYOK_KEY:-}" ]]` (existence gate) and
  `AP_DEV_BYOK_KEY="${AP_DEV_BYOK_KEY}" \` (env passthrough). `$API_LOG`
  is deleted on exit regardless of success/failure. T-02-01 mitigation
  preserved.
- `$AGENT` is validated against a literal `picoclaw|hermes` allow-list
  before any docker invocation. T-02-12 mitigation preserved.

## Known Stubs

None. Both delivered files are complete and functional.

## Open Follow-ups

1. **Task 3 human-verify checkpoint (pending):** a human must export
   `AP_DEV_BYOK_KEY`, run `make smoke-test`, and eyeball the picoclaw
   and hermes agent responses for plausibility. See §Checkpoint below.
2. **Spike 4 (gVisor on Hetzner):** still pending per STATE.md
   §"Pending Todos" — not a Phase 2 blocker, only gates Phase 7.5 + 8.
3. **Pre-existing TestMigrator_Idempotent failure** (documented in
   `deferred-items.md`): not Plan 06's job to fix. The new integration
   test is build-tag-gated and does not interact with that failure.

## Checkpoint

**Task 3 type:** `checkpoint:human-verify` (gate=blocking, per plan).

**Reason not auto-approved:** This plan is marked `autonomous: false`
and the verification step requires (a) a live Anthropic API key the
executor does not possess and (b) a human reading the agent's reply
text to confirm it is plausibly a real LLM output versus error cruft
per CONTEXT D-34.

**What the human must do:**

```bash
export AP_DEV_BYOK_KEY=<your real Anthropic API key>
cd /Users/fcavalcanti/dev/agent-playground   # or the worktree checkout
make smoke-test
```

**`make smoke-test` will run (in order):**

1. `bash scripts/smoke-e2e.sh picoclaw`
2. `bash scripts/smoke-e2e.sh hermes`

**Pass criteria — confirm ALL of:**

- [ ] picoclaw smoke test exited 0 with a visible "AGENT RESPONSE"
      block containing a non-empty plausibly-real LLM reply
- [ ] hermes smoke test exited 0 with the same
- [ ] `docker ps -a --filter name=playground-` returns nothing
- [ ] `ls /tmp/ap/secrets/ 2>/dev/null` returns nothing
- [ ] No "error", "exception", or "traceback" strings in the response text
      (the script's internal guard covers this but a human should still
      eyeball for subtler failure modes like prompt-echo or tool-use
      error wrappers)

**Likely failure modes to watch for** (from 02-RESEARCH §Common Pitfalls):

| Symptom | Fix direction |
|---------|--------------|
| picoclaw FIFO bridge returns `"picoclaw> "` prompt cruft instead of the assistant reply | Fall back: switch picoclaw from ChatIOFIFO to ChatIOExec with `["picoclaw","agent","-m"]` in `api/internal/recipes/recipes.go`, re-run |
| Hermes returns `"requires interactive terminal"` | Fix: change `bridge.execMode` to allocate a TTY via the Docker SDK exec config (research Pitfall 3 + Hermes `hermes_cli/main.py _require_tty()`) |
| Dangling container after delete | Investigate handler.delete `runner.Stop` / `runner.Remove` ordering; check the API log tail the script prints on failure |
| Secret dir leaked | Investigate handler.delete cleanup ordering (should be: Stop → Remove → secrets.Cleanup → UpdateStatus) |
| Cold-start Hermes >120s | Recipe's `ResponseTimeout` is 120s; if the first message trips this, bump recipe timeout or pre-warm in entrypoint |

**Resume signal the human should provide:** "approved — both agents
respond" (marks Phase 2 hypothesis-proven) OR "failure: <symptom>" with
the failure mode observed, so a follow-up fix plan can be spawned.

## Commits

| Hash | Type | Message |
|------|------|---------|
| `1de10b2` | feat | feat(02-06): smoke-e2e.sh hypothesis-proof test + AP_DEV_BYOK_KEY env example |
| `ba269c8` | test | test(02-06): session integration tests for one-active invariant |

## Self-Check

- `scripts/smoke-e2e.sh` — FOUND
- `scripts/smoke-e2e.sh` — EXECUTABLE (0755)
- `bash -n scripts/smoke-e2e.sh` — exits 0
- SKIPPED path verified (unset AP_DEV_BYOK_KEY → exit 0 with message)
- Bad-agent rejection verified (exit 2 with error message)
- `.env.example` — MODIFIED with AP_DEV_BYOK_KEY block
- `api/internal/session/integration_test.go` — FOUND
- Build tag `//go:build integration` present on line 1
- `go build ./...` — exits 0
- `go vet ./...` — exits 0
- `go vet -tags=integration ./internal/session/` — exits 0
- `go test -count=1 -run '^$' ./internal/session/` — ok (build tag excludes the test file from default runs)
- `go test -tags=integration -count=1 -run TestSessionLifecycle -v ./internal/session/` — all 3 tests PASS (real embedded-postgres PG 18.3)
- Commit `1de10b2` — FOUND (`git log --oneline` verified)
- Commit `ba269c8` — FOUND

## Self-Check: PASSED (autonomous portion)
