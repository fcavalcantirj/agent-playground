---
phase: 2
slug: container-sandbox-spine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-14
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | go test (backend); no frontend in Phase 2 |
| **Config file** | api/go.mod (module), no extra test config |
| **Quick run command** | `cd api && go test ./pkg/docker/... ./internal/recipes/... ./internal/sessions/...` |
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

> Populated by planner from RESEARCH.md `## Validation Architecture` section. Every PLAN.md task maps to a row here before execution.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | SBX-01 | — | ap-base runs as unprivileged UID with tini PID 1 | integration | `go test ./internal/smoketest -run TestApBaseBoot` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SBX-03 | — | RunOptions fields wire through to HostConfig | unit | `go test ./pkg/docker -run TestRunOptionsHostConfig` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SBX-05 | — | No privileged flag, no docker socket bind accepted | unit | `go test ./pkg/docker -run TestRunnerRejectsPrivileged` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SBX-09 | — | `playground-<user>-<session>` derivable from DB row | unit | `go test ./pkg/docker -run TestContainerName` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SES-01 (partial) | — | POST /api/sessions spawns container via runner.go | integration | `go test ./internal/sessions -run TestCreateSessionE2E` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SES-04 (partial) | — | DELETE /api/sessions/:id tears down cleanly | integration | `go test ./internal/sessions -run TestDeleteSession` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CHT-01 (partial) | — | POST /api/sessions/:id/message round-trips via FIFO | integration | `go test ./internal/sessions -run TestMessageRoundTrip` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | dev-BYOK | — | `AP_DEV_BYOK_KEY` lands in container at `/run/secrets/anthropic_key` mode 0644 | integration | `go test ./internal/sessions -run TestBYOKInjection` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | recipes (picoclaw) | — | `ap-picoclaw` image tag present after `make build-recipes` | integration | `go test ./internal/recipes -run TestPicoclawRecipeBuild -tags=integration` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | recipes (Hermes) | — | `ap-hermes` image tag present after `make build-recipes` | integration | `go test ./internal/recipes -run TestHermesRecipeBuild -tags=integration` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | Hypothesis proof | — | End-to-end curl smoke test passes for both agents, zero dangling containers | e2e | `scripts/smoke-e2e.sh picoclaw && scripts/smoke-e2e.sh hermes` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `api/pkg/docker/runner_test.go` — fixtures for HostConfig mapping tests
- [ ] `api/pkg/docker/runner_name_test.go` — container-name validator fixtures
- [ ] `api/internal/sessions/sessions_test.go` — in-process handler tests
- [ ] `api/internal/sessions/e2e_test.go` — integration tier with real dockerd (behind `-tags=integration`)
- [ ] `api/internal/recipes/recipes_test.go` — recipe struct tests
- [ ] `scripts/smoke-e2e.sh` — curl-driven end-to-end smoke (Hypothesis proof)
- [ ] `Makefile` target `build-recipes` — pre-builds ap-picoclaw and ap-hermes images

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ttyd reaches shell window through a real docker exec | SBX-01 | Requires interactive terminal; not reliably automatable in CI | `docker exec -it playground-u1-s1 tmux attach -t main` — confirm both `chat` and `shell` windows exist |
| Real Anthropic round-trip via BYOK | Hypothesis proof | Requires a live API key and costs credits | Set `AP_DEV_BYOK_KEY` to a valid key, run `scripts/smoke-e2e.sh picoclaw`, confirm response text is non-empty |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s for unit tier, < 5min for integration tier
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
