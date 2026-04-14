# Phase 2 — Planning Session Log

**Date:** 2026-04-14
**Command:** `/gsd-plan-phase 2`
**Outcome:** 6 plans, 5 waves, ready to execute
**Purpose of this file:** Resume context after `/clear` without losing why things ended up the way they did.

---

## What this session produced

- `02-RESEARCH.md` — committed in `6c620f5`
- `02-VALIDATION.md` — committed in `63ed504`, then backfilled in `c704439`
- `02-01-PLAN.md` through `02-06-PLAN.md` — the 6 plans
- `02-CONTEXT.md` — annotated with D-19 Python 3.13 correction and deferred-list DONE markers
- `.planning/ROADMAP.md` — SC-4 Python 3.11 → 3.13 fix; Phase 2 plan list updated
- `.planning/STATE.md` — status flipped to "Ready to execute", plan count 6

## Wave structure (final)

| Wave | Plans | Build |
|------|-------|-------|
| 1 | 02-01, 02-02 | `ap-base` image · `runner.go` sandbox fields + naming helper |
| 2 | 02-03 | Recipe overlays (`ap-picoclaw` FIFO, `ap-hermes` Python 3.13 single-query) |
| 3 | 02-04 | Sessions migration · recipes pkg · `DefaultSandbox` · `SecretWriter` (dev BYOK) · `ExecWithStdin` |
| 4 | 02-05 | Bridge · handlers · `server.go` · `main.go` wiring |
| 5 | 02-06 | `scripts/smoke-e2e.sh` · integration tests · human-verify checkpoint |

## Key decisions / corrections made during this session

1. **Python 3.13, not 3.11.** CONTEXT D-19 originally said 3.11; research verified Hermes upstream Dockerfile uses `uv:0.11.6-python3.13-trixie`. All plans, ROADMAP SC-4, and CONTEXT now say 3.13.

2. **Hermes channel-daemons disable is a no-op.** CONTEXT D-21 assumed a YAML key to disable daemons. Research showed daemons are activated by a separate `hermes gateway` subcommand — we simply never invoke it. `cli-config.yaml` only needs `model.provider: anthropic`, `terminal.backend: local`, `platform_toolsets.cli: [hermes-cli]`.

3. **Hermes chat bridge is `hermes chat -q "<msg>"`.** CONTEXT D-23 deliberated between PTY screen-scrape / MCP / hypothetical CLI flag. Research confirmed `hermes chat -q` exists as a real non-interactive subcommand in `cli.py`. Hermes bridge = `docker exec` one-shot, no FIFO needed for Hermes. picoclaw still uses the FIFO path.

4. **Sessions table stays separate from Phase 1's `agents` table.** CONTEXT D-26 called for a new `sessions` table. Plan 04 keeps them distinct: `agents` = saved configuration, `sessions` = runtime instance. Migration `002_sessions.sql` documents the rationale in a SQL comment.

5. **Plan 04 split into 04 (foundations) + 05 (API surface).** Original Plan 04 touched 16 files in 3 tasks — above the 15-file blocker threshold. Checker W1 forced a split; old Plan 05 (smoke test) was renumbered to Plan 06.

6. **Wave cascade corrected on iteration 2.** After the split, Plan 04 depended on both Plan 02 (Wave 1) and Plan 03 (Wave 2), so Plan 04 had to be Wave 3. Plan 05 cascaded to Wave 4, Plan 06 to Wave 5. Fixed in commit `c704439`.

## Pitfalls baked into plans (do not regress during execution)

- **Pitfall 2 (FIFO blocking writes):** Plan 01 entrypoint.sh holds FIFOs open with `exec 3<>` BEFORE launching the agent. Grep gate in acceptance criteria.
- **Pitfall 6 (userns-remap perms):** Plan 04 `SecretWriter` creates `/tmp/ap/secrets/<id>` mode 0700, file `anthropic_key` mode 0644. Grep gate enforces both modes.
- **Pitfall 7 (read-only rootfs needs pre-created mount targets):** Plan 01 Dockerfile pre-creates `/run/secrets` and `/run/ap` BEFORE read-only rootfs is applied. Grep gate in acceptance criteria.
- **`ReadonlyRootfs`, not `ReadOnlyRootfs`.** Docker SDK spelling is single-R, no separator. Plan 02 uses the correct spelling; do not "fix" it to camelCase.
- **`userFromCtx` must use `middleware.GetUserID`.** Plan 05 Task 2 `<read_first>` forces reading `api/internal/middleware/auth.go` first. The handler must delegate to `middleware.GetUserID`, not guess at a context key.

## Open flags for execution (informational)

- **Plan 04 at 10-file boundary:** exactly 10 files across 2 tasks. Still within scope. Both tasks are clean RED→GREEN cycles.
- **picoclaw FIFO stdout format fallback:** Plan 06 checkpoint task documents that if FIFO bridge is brittle, the executor switches picoclaw recipe to `ChatIOExec` (`picoclaw agent -m`) — same code path as Hermes. Flagged as Open Question 4 in RESEARCH.
- **Hetzner `dockremap` base UID range:** assumed 100000 (Docker default). Verify on the host before executing Plan 01 Task 2 if the operator changed it.

## What was verified PASSING by the plan-checker (iteration 2)

- Requirement coverage: all 11 IDs mapped (SBX-01/02/03/05/09, SES-01/04, CHT-01, dev-BYOK, picoclaw recipe, hermes recipe)
- Every plan has `<threat_model>` covering T-02-01 through T-02-05+
- Every task has `<read_first>` and grep-verifiable `<acceptance_criteria>`
- `must_haves` cover all 5 ROADMAP success criteria
- Dependency graph acyclic
- CLAUDE.md compliance (Go 1.25 / Echo v4 / pgx v5 / moby/moby/client / no gorilla / no GORM / no Alpine for Python recipes)

## Next command

```bash
/gsd-execute-phase 2
```

Recommend `/clear` first to reset context. Everything needed to resume is in STATE.md, ROADMAP.md, CONTEXT.md, RESEARCH.md, VALIDATION.md, and the 6 PLAN files.
