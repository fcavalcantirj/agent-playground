---
phase: 19-api-foundation
status: deploy_blocked_pending_phase_20_execution
paused_at: 2026-04-17T03:15:00Z
updated: 2026-04-17T19:00:00Z
resume_on: next-session
plan_open: 19-07
task_open: Task 3 BLOCKED — Phase 20 must ship SC-11 before Hetzner deploy resumes
unblocks_on: Phase 20 Plan 20-05 human-verify gate returns "approved"
---

# Phase 19 — DO NOT DEPLOY YET

**STOP. The Hetzner deploy is still cancelled.** Phase 20 must ship first.

## Latest update (2026-04-17 afternoon)

Phase 20 is now **planned and ready for execution**. Full pipeline ran: CONTEXT → RESEARCH → UI-SPEC → PATTERNS → 5 PLANs → plan-checker REVISE_MINOR → 4 fixes applied.

The next action is **NOT** the Hetzner deploy. The next action is `/gsd-execute-phase 20`.

When Plan 20-05's human-verify SC-11 gate returns `approved`, the Phase 19 Hetzner deploy (the 7 operator steps in `19-07-SUMMARY.md §"How to Verify"`) becomes unblocked.

## Phase 20 artifacts (all committed)

- `.planning/phases/20-frontend-alicerce/20-CONTEXT.md` — 14 locked decisions D-01..D-14, SC-01..SC-11, user-approved ASCII preview
- `.planning/phases/20-frontend-alicerce/20-RESEARCH.md` — 10 focused Q&A, concrete code patterns, 8 pitfalls
- `.planning/phases/20-frontend-alicerce/20-UI-SPEC.md` — shadcn primitives, Tailwind v4 tokens, 30 locked copy strings, 5-state + 6-error ASCII wireframes
- `.planning/phases/20-frontend-alicerce/20-PATTERNS.md` — 6 analogs mapped; `dev-login-form.tsx` is the exact structural analog for `playground-form.tsx`
- `.planning/phases/20-frontend-alicerce/20-01..20-05-PLAN.md` — 5 PLANs in 3 waves, all checker-validated

## Phase 20 wave structure

| Wave | Plans | Files | Notes |
|------|-------|-------|-------|
| 1 | 20-01, 20-02 | Extend `api.ts` + new `api-types.ts`; delete mock tree (agent-configurator + 5 peers + homepage playground section) | Parallel; no file overlap |
| 2 | 20-03, 20-04 | New `playground-form.tsx`; new `run-result-card.tsx` | Parallel after Wave 1; cardRef null-union harmonized |
| 3 | 20-05 | Wire `/playground` page; SUMMARY; STATE update | Sequential; **autonomous: false — human-verify SC-11 smoke gate** |

## Phase 19 deploy kickoff (AFTER Phase 20 SC-11 passes)

Per `19-07-SUMMARY.md §"How to Verify"`, execute these 7 operator steps:

1. `dig +short api.agentplayground.dev` — must resolve to the Hetzner IPv4
2. `ssh $HETZNER_HOST -- docker version` — must be 27+
3. On the box: `git pull && cd deploy && bash deploy.sh` — expect `[deploy] ok — api_server /healthz responding`
4. `curl -vI https://api.agentplayground.dev 2>&1 | grep -E "subject:.*agentplayground"` — expect Let's Encrypt cert line
5. `bash test/smoke-api.sh --live` or `make smoke-api-live` — expect `smoke: PASS`
6. *(optional, costs cents)* `OPENROUTER_API_KEY=or-real bash test/smoke-api.sh --live` — SC-05 + SC-06 pass with real BYOK
7. `API_BASE=https://api.agentplayground.dev make generate-ts-client` — expect `TS client valid`

The commit `cdcc897` landed 5 prod-blocking deploy bug fixes (Dockerfile.api docker.io→docker-cli + GID collision; init-api-db.sh missing `-d`; deploy.sh base64→hex password; compose `--env-file`) — all will propagate via `git pull`.

## Phase 19 carryover (not blocking Phase 20 execution)

`api_server/tests/test_migration.py` shells out to `alembic` directly instead of `python -m alembic`. Fails when the venv's `alembic` binary is not on PATH. Plans 19-02 and 19-04 worked around it in their tests. Harmless to `make test-api-live` because the Makefile activates the venv. Fix in Phase 20.1 or later.

## Paste-ready kickoff for next session

```text
# After /clear, read in this order:
# 1. CLAUDE.md (golden rules at top — #2 is load-bearing)
# 2. .planning/phases/20-frontend-alicerce/20-CONTEXT.md
# 3. .planning/phases/20-frontend-alicerce/20-RESEARCH.md (skim)
# 4. .planning/phases/20-frontend-alicerce/20-UI-SPEC.md (skim copy strings + wireframes)
# 5. .planning/phases/20-frontend-alicerce/20-01-PLAN.md through 20-05-PLAN.md
# 6. .planning/STATE.md
# 7. memory/feedback_dumb_client_no_mocks.md

# Then:
/gsd-execute-phase 20

# When Plan 20-05's human-verify gate surfaces, run the SC-01..SC-10 local smoke:
# - make dev-api-local (terminal 1)
# - make dev-frontend (terminal 2)
# - open http://localhost:3000/playground
# - pick a recipe, type model + BYOK + prompt, click Deploy, see verdict card
# - confirm run persisted in postgres via the SQL command in 20-05-PLAN.md
# Then paste "approved" to advance code-review → verify → update_roadmap.

# After Phase 20 completes (SC-11 passes):
/gsd-execute-phase 19 --wave 4
# Respond to the 19-07 checkpoint with the 7 Hetzner operator steps above.
```

## What NOT to do

- **Do NOT** run `bash deploy/deploy.sh` against Hetzner before Phase 20 SC-11 passes.
- **Do NOT** run `/gsd-execute-phase 19 --wave 4` before Phase 20 SC-11 passes.
- **Do NOT** mark Phase 19 complete in ROADMAP before the deploy step runs.
- **Do NOT** add new client-side catalogs of recipes/models/channels (golden rule #2 — this whole phase exists because of that violation).
- **Do NOT** persist BYOK keys in localStorage or any storage (golden rule follow-through per CONTEXT D-05).

## Pointers

- Memory: `memory/project_phase_19_deploy_handoff.md`, `memory/feedback_dumb_client_no_mocks.md`, `memory/feedback_no_mocks_no_stubs.md`
- Golden rules: `CLAUDE.md` top banner (rules #1..#4)
- Full Phase 19 shipped evidence: `19-07-SUMMARY.md` + commits `5c14be9..0bf9e71`
- Phase 20 execution entry point: `/gsd-execute-phase 20`
