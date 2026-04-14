---
phase: 2
slug: container-sandbox-spine
status: draft
nyquist_compliant: true
wave_0_complete: inline
created: 2026-04-14
revised: 2026-04-14
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | go test (backend); no frontend in Phase 2 |
| **Config file** | api/go.mod (module), no extra test config |
| **Quick run command** | `cd api && go test ./pkg/docker/... ./internal/recipes/... ./internal/session/...` |
| **Full suite command** | `cd api && go test ./... -tags=integration` |
| **Estimated runtime** | ~30s quick / ~5min full (includes container spawn smoke tests) |

---

## Sampling Rate

- **After every task commit:** Run quick command (unit tests for touched package)
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green, including the end-to-end curl smoke test for BOTH picoclaw and Hermes
- **Max feedback latency:** 30 seconds for unit tier, 5 minutes for integration tier

---

## Per-Task Verification Map

> Populated by planner from RESEARCH.md `## Validation Architecture` section. Every PLAN.md task maps to a row here before execution. **Wave 0 test files are created INLINE by the respective tasks (RED→GREEN within each task) — there is no separate Wave 0 plan.**

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-T1 | 02-01 | 1 | SBX-01 | T-02-02, T-02-03 | ap-base Dockerfile builds; tini PID 1; agent uid 10000; tmux + ttyd + secret target dir present | integration | `docker build -t ap-base:v0.1.0 deploy/ap-base/ && docker images ap-base:v0.1.0` | inline | ⬜ pending |
| 02-01-T2 | 02-01 | 1 | SBX-01, SBX-05 | T-02-02, T-02-04 | entrypoint.sh drops via gosu, pre-opens FIFOs (Pitfall 2), starts ttyd on loopback | integration | `bash -n deploy/ap-base/entrypoint.sh && docker run --rm --read-only --tmpfs /tmp --tmpfs /run ap-base:v0.1.0` | inline | ⬜ pending |
| 02-01-T3 | 02-01 | 1 | SBX-01 | — | `make build-ap-base` target works; deploy/ap-base/README.md documents pattern | integration | `make -n build-ap-base && make build-ap-base` | inline | ⬜ pending |
| 02-02-T1 | 02-02 | 1 | SBX-02, SBX-03, SBX-05 | T-02-02, T-02-02b | RunOptions sandbox fields plumb through to HostConfig with verified spellings; no Privileged field | unit | `cd api && go test ./pkg/docker/ -count=1 -run TestRunOptions` | inline | ⬜ pending |
| 02-02-T2 | 02-02 | 1 | SBX-09 | T-02-09 | `playground-<user>-<session>` builder + parser + IsPlaygroundContainerName helpers | unit | `cd api && go test ./pkg/docker/ -count=1 -run 'TestBuildContainerName\|TestParseContainerName\|TestIsPlayground'` | inline | ⬜ pending |
| 02-03-T1 | 02-03 | 2 | SBX-01, picoclaw recipe | T-02-03 | ap-picoclaw image builds from pinned SHA; FROMs ap-base; `picoclaw --version` runs in container | integration | `make build-picoclaw && docker run --rm ap-picoclaw:v0.1.0-c7461f9 picoclaw --version` | inline | ⬜ pending |
| 02-03-T2 | 02-03 | 2 | SBX-01, hermes recipe | T-02-03b, T-02-08 | ap-hermes image builds from pinned SHA on Python 3.13; FROMs ap-base; `hermes --help` runs in container | integration | `make build-hermes && docker run --rm ap-hermes:v0.1.0-5621fc4 hermes --help` | inline | ⬜ pending |
| 02-04-T1 | 02-04 | 3 | SES-01 (partial), SES-04 (partial) | — | sessions migration applies; recipes.AllRecipes contains picoclaw + hermes; DefaultSandbox returns hardened posture | unit | `cd api && go test ./internal/recipes/ -count=1 && go test ./internal/session/ -count=1 -run TestDefaultSandbox` | inline | ⬜ pending |
| 02-04-T2 | 02-04 | 3 | dev-BYOK | T-02-01, T-02-11 | SecretWriter writes 0644 in 0700 dir (Pitfall 6); DevEnvSource reads AP_DEV_BYOK_KEY; runner.ExecWithStdin extends Exec | unit | `cd api && go test ./internal/session/ -count=1 -run TestSecret && go test ./pkg/docker/ -count=1 -run TestRunner_ExecWithStdin` | inline | ⬜ pending |
| 02-05-T1 | 02-05 | 4 | CHT-01 (partial) | T-02-04, T-02-04b | Bridge dispatches FIFO vs exec; argv composition uses []string with no shell interp; ANSI stripping for Hermes; timeout maps to ErrTimeout | unit | `cd api && go test ./internal/session/ -count=1 -run TestBridge` | inline | ⬜ pending |
| 02-05-T2 | 02-05 | 4 | SES-01 (partial), SES-04 (partial), CHT-01 (partial) | T-02-02, T-02-05, T-02-11, T-02-13 | Three handlers behind auth; create returns 201/400/401/409/503; delete cleans secrets; userFromCtx delegates to middleware.GetUserID (W3 fix) | unit | `cd api && go test ./internal/session/ -count=1 -run TestHandler && go test ./... -count=1` | inline | ⬜ pending |
| 02-06-T1 | 02-06 | 5 | Hypothesis proof | T-02-01, T-02-05, T-02-12, T-02-13 | scripts/smoke-e2e.sh runs end-to-end against picoclaw OR hermes; exits 0 in SKIPPED mode without AP_DEV_BYOK_KEY | e2e | `bash -n scripts/smoke-e2e.sh && bash scripts/smoke-e2e.sh picoclaw` | inline | ⬜ pending |
| 02-06-T2 | 02-06 | 5 | SES-01, SES-04 | — | TestSessionLifecycle_OneActivePerUser + AfterStopAllowsNew + DistinctUsersConcurrent against real Postgres (build tag `integration`) | integration | `cd api && go test -tags=integration ./internal/session/ -count=1 -run TestSessionLifecycle` | inline | ⬜ pending |
| 02-06-T3 | 02-06 | 5 | Hypothesis proof | — | Human verification: run `make smoke-test` with real AP_DEV_BYOK_KEY, eyeball both picoclaw and Hermes responses, confirm zero dangling containers + zero leaked secret dirs | manual | (checkpoint:human-verify) | inline | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

**Inline creation (no separate Wave 0 plan):** Each task that needs a test file creates that file as the first step of its own RED→GREEN cycle. The test file is committed in the same task as the production code it gates. This is consistent with how Phase 1 handled Wave 0.

Test files created inline by Phase 2 tasks:
- `api/pkg/docker/runner_test.go` (extended) — Plan 02 Task 1 (sandbox field tests) + Plan 04 Task 2 (ExecWithStdin test)
- `api/pkg/docker/naming_test.go` — Plan 02 Task 2
- `api/internal/recipes/recipes_test.go` — Plan 04 Task 1
- `api/internal/session/defaults_test.go` — Plan 04 Task 1
- `api/internal/session/secrets_test.go` — Plan 04 Task 2
- `api/internal/session/bridge_test.go` — Plan 05 Task 1
- `api/internal/session/handler_test.go` — Plan 05 Task 2
- `api/internal/session/integration_test.go` — Plan 06 Task 2
- `scripts/smoke-e2e.sh` — Plan 06 Task 1
- `Makefile` target `build-recipes` — Plan 01 Task 3

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ttyd reaches shell window through a real docker exec | SBX-01 | Requires interactive terminal; not reliably automatable in CI | `docker exec -it playground-u1-s1 tmux attach -t ap` — confirm both `chat` and `shell` windows exist (chat may be absent if AP_AGENT_CMD empty, e.g. Hermes) |
| Real Anthropic round-trip via BYOK | Hypothesis proof | Requires a live API key and costs credits | Set `AP_DEV_BYOK_KEY` to a valid key, run `scripts/smoke-e2e.sh picoclaw` and `scripts/smoke-e2e.sh hermes`, confirm response text is non-empty for both |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covered inline by respective tasks (no separate Wave 0 plan)
- [x] No watch-mode flags
- [x] Feedback latency < 30s for unit tier, < 5min for integration tier
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready (revised 2026-04-14 to back-fill task IDs after Plan 04 split into 04+05 and old Plan 05 → 06)
