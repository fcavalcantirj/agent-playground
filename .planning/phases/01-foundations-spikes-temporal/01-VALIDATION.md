---
phase: 1
slug: foundations-spikes-temporal
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-13
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Go testing + testify v1.11.1 |
| **Config file** | None needed (Go built-in) |
| **Quick run command** | `cd api && go test ./... -short -count=1` |
| **Full suite command** | `cd api && go test ./... -count=1 -race` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd api && go test ./... -short -count=1`
- **After every plan wave:** Run `cd api && go test ./... -count=1 -race`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | FND-03 | T-1-01 | HMAC cookie signing | unit | `go test ./internal/handler/ -run TestHealth -count=1` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | FND-05 | — | N/A | integration | `go test ./pkg/migrate/ -run TestMigrator -count=1` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | FND-06 | T-1-03 | Arg validation blocks injection | unit | `go test ./pkg/docker/ -run TestRunner -count=1` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | FND-08 | — | N/A | integration | `go test ./internal/temporal/ -run TestPingPong -count=1` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | FND-10 | — | N/A | integration | `go test ./pkg/migrate/ -run TestBaseline -count=1` | ❌ W0 | ⬜ pending |
| TBD | — | — | FND-01 | — | userns-remap enabled | manual | SSH to host, `docker info` | N/A | ⬜ pending |
| TBD | — | — | FND-02 | — | loopback-only bind | manual | `pg_isready`, `redis-cli ping` | N/A | ⬜ pending |
| TBD | — | — | FND-04 | — | N/A | manual | `cd web && pnpm build && pnpm start` + visual check | N/A | ⬜ pending |
| TBD | — | — | FND-07 | — | N/A | manual | File exists: `.planning/research/SPIKE-REPORT.md` | N/A | ⬜ pending |
| TBD | — | — | FND-09 | — | N/A | manual | `temporal operator namespace list` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `api/internal/handler/health_test.go` — covers FND-03
- [ ] `api/pkg/migrate/migrate_test.go` — covers FND-05, FND-10
- [ ] `api/pkg/docker/runner_test.go` — covers FND-06
- [ ] `api/internal/temporal/worker_test.go` — covers FND-08
- [ ] `api/internal/middleware/auth_test.go` — covers dev-cookie auth (D-09)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hetzner host provisioned with Docker + userns-remap | FND-01 | Requires SSH to production host | SSH in, run `docker info`, verify `userns-remap` in security options |
| Postgres + Redis loopback services | FND-02 | Requires host-level verification | `pg_isready -h 127.0.0.1`, `redis-cli -h 127.0.0.1 ping` |
| Mobile-first landing page renders correctly | FND-04 | Visual/responsive check | Build + start Next.js, open on phone viewport, verify touch targets |
| Spike report committed | FND-07 | Empirical research deliverable | Check file exists at `.planning/research/SPIKE-REPORT.md` |
| Temporal namespace + queues observable | FND-09 | Requires running Temporal + CLI | `temporal operator namespace list`, check Web UI at :8233 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
