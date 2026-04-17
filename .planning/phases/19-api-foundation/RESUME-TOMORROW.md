---
phase: 19-api-foundation
status: paused_at_human_verify
paused_at: 2026-04-17T03:15:00Z
resume_on: 2026-04-18
plan_open: 19-07
task_open: Task 3 (Hetzner SSH deploy + TLS verify + TS client compile)
---

# Phase 19 — Resume Tomorrow

Phase is **6.5/7 shipped**. Everything local is green. Only the live Hetzner push + TLS verify + TypeScript client compile remains. All artifacts exist on disk and are committed.

## What's already shipped (2026-04-16 → 2026-04-17)

| Plan | Title                                         | Commits                                                  |
|------|-----------------------------------------------|----------------------------------------------------------|
| 19-01 | Alembic + 5 tables + seeded anonymous user    | `5c14be9` `5275d08` `d8a4971` `d4a009c`                  |
| 19-06 | BYOK leak defense + correlation-id middleware | `027ffec` `a0222de` `486d1cf` `a613eed`                  |
| 19-02 | FastAPI skeleton + /healthz + /readyz         | `14632e7` `f244634` `77ad0d0`                            |
| 19-03 | /v1/schemas + /v1/recipes + /v1/lint          | `5a48b7b` `689dcbd` `196ebc3`                            |
| 19-04 | POST /v1/runs + GET /v1/runs/{id}             | `667a303` `93fcaa3` `eaa3d1d`                            |
| 19-05 | Postgres rate-limit + idempotency             | `f8b5005` `1c4ba36` `cf2cdde`                            |
| 19-07 | Hetzner deploy artifacts + local smoke        | `1832efd` `fbf6f31` `1b7acbb` `0bf9e71` (Task 3 pending) |

**Local validation evidence (2026-04-17):**
- `pytest -q -m 'not api_integration'` → 14 pass
- `pytest -q -m api_integration` (live Postgres 17 via testcontainers + docker probe, excl. test_migration) → 27 pass
- `pytest -q -m api_integration tests/test_migration.py` (venv on PATH) → 8 pass
- Manual curl smoke against `uvicorn` + scratch Postgres 17 on :15432: `/healthz`, `/readyz`, `/v1/schemas`, `/v1/recipes`, `/v1/lint` (happy + malformed), `POST /v1/runs` (real runner → `verdict:FAIL category:INVOKE_FAIL`, run persisted, `agent_instances` upserted)
- Rate-limit probe: 10 × 200 → 11th `429` + `retry-after: 32`
- Idempotency replay: same `Idempotency-Key` → same `run_id`, no duplicate `runs` row
- **BYOK leak audit:** `grep FAKEKEY /tmp/uvicorn-smoke.log` = **0 hits**

## What remains — Plan 19-07 Task 3 (human-gated)

Per `19-07-SUMMARY.md` §"How to Verify", execute these 7 steps against the real Hetzner box + `api.agentplayground.dev`:

1. `dig +short api.agentplayground.dev` — must resolve to the Hetzner IPv4
2. `ssh $HETZNER_HOST -- docker version` — must be 27+
3. On the box: `git pull && cd deploy && bash deploy.sh` — expect `[deploy] ok — api_server /healthz responding`
4. `curl -vI https://api.agentplayground.dev 2>&1 | grep -E "subject:.*agentplayground"` — expect Let's Encrypt cert line
5. `bash test/smoke-api.sh --live` or `make smoke-api-live` — expect `smoke: PASS (API_BASE=https://api.agentplayground.dev)`
6. *(optional, costs cents)* `OPENROUTER_API_KEY=or-real bash test/smoke-api.sh --live` — SC-05 + SC-06 pass with real BYOK
7. `API_BASE=https://api.agentplayground.dev make generate-ts-client` — expect `TS client valid` (SC-13, Phase 20 handoff)

Then paste **"approved"** to let the chain run: `gsd-code-review 19` → `gsd-verifier` → `update_roadmap` → phase complete → transition to Phase 19.5 / 20 / 21 planning.

## Known carryover (don't fix without an explicit ask)

`api_server/tests/test_migration.py` shells out to `alembic` directly instead of `python -m alembic`. Fails when the venv's `alembic` binary is not on `PATH`. Plans 19-02 and 19-04 worked around it by using `python -m alembic` in their own conftest/tests. This one test still has the issue. Harmless to `make test-api-live` because the Makefile activates the venv.

## Paste-ready kickoff for tomorrow

```text
/gsd-progress

# Then, after confirming state:
/gsd-execute-phase 19 --wave 4

# When the executor re-enters the 19-07 human-verify checkpoint,
# run the 7 operator steps above against the real Hetzner box,
# then paste "approved" to advance to code-review → verify → complete.
```

Memory pointer: `memory/project_phase_19_deploy_handoff.md`.
