# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-11)

**Core value:** Any agent × any model × any user, in one click — agent-agnostic install pipeline is the differentiator that must work.
**Current focus:** Phase 1 — Foundations, Spikes & Temporal

## Current Position

Phase: 1 of 8 (Foundations, Spikes & Temporal)
Plan: 0 of 0 (not planned yet)
Status: Ready to plan
Last activity: 2026-04-11 — Roadmap created, 116 v1 requirements mapped across 8 phases

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: —
- Trend: —

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Init: Temporal is required (overrides research recommendation to drop it); session create/destroy, recipe install, and reconciliation run as Temporal workflows — must be running in Phase 1.
- Init: Go API + Next.js stack mirrors MSV; `pkg/docker/runner.go` is ported verbatim from MSV pattern.
- Init: Hetzner dedicated single-host deployment; no K8s, no cloud-managed containers.
- Init: BYOK is first-class (no asterisks); platform-billed via LiteLLM + Stripe credit ledger.
- Init: gVisor (`runsc`) is mandatory for the Phase 8 bootstrap path; curated recipes may use `runc`.
- Init: Whole platform ships open-source under Apache-2.0; monetization is the hosted service.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1 includes a spike report (FND-07) that resolves four unknowns (HTTPS_PROXY vs BASE_URL behavior per agent, chat_io mode per agent, tmux+pipe latency, gVisor feasibility on Hetzner kernel). Results feed Phase 2 recipe + sandbox decisions.

## Session Continuity

Last session: 2026-04-11
Stopped at: ROADMAP.md + STATE.md created; REQUIREMENTS.md traceability populated. Ready for `/gsd-plan-phase 1`.
Resume file: None
