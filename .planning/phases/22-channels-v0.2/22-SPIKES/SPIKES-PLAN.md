# Phase 22a — Spike Plan

**Purpose:** resolve every gray area in Phase 22a plans BEFORE the planner's PLAN files become executable. Per Golden Rule #5.

**Status:** 13 probes pending. Each probe runs against real infra, commits an atomic result file (`spike-NN-<slug>.md`) with: command, expected, actual, verdict (PASS/FAIL/SURPRISE), plan impact.

---

## Probe matrix

| # | Gray area | Plan affected | Wave | Probe | Expected |
|---|---|---|---|---|---|
| 01 | pyrage install in ap_server image (Python 3.11 slim) | 22-02 | 1 | `docker exec deploy-api_server-1 sh -c "pip show pyrage \|\| pip install pyrage && python -c 'import pyrage; print(pyrage.__version__)'"` | importable + version string |
| 02 | age round-trip with HKDF per-user KEK + cross-user deny | 22-02 | 1 | standalone Python: encrypt for user A, decrypt with user B's KEK → must raise | decrypt A→A ok; decrypt A→B raises |
| 03 | Postgres partial unique index + UniqueViolation mapping | 22-02 | 1 | migration on local pg + 2 concurrent inserts with status='running' | 2nd raises UniqueViolation with constraint_name exposed |
| 04 | schema v0.2 oneOf branch validates 5 v0.1 recipes AND 5 v0.2-draft recipes | 22-01 | 1 | jsonschema.Draft202012Validator.iter_errors × 5 recipes × 2 branches | all 10 pass |
| 05 | `docker run -d` with sh-entrypoint override — daemon stays up 30s+ | 22-03 | 2 | each of 5 recipes: `docker run -d --name ap-probe-X <image> sh -c "<persistent-argv>"`; `sleep 30; docker ps --filter name=ap-probe-X` | container running for all 5 |
| 06 | ready_log_regex literal patterns match real boot output | 22-03 | 2 | `docker logs <container> \| grep -E "<regex>"` for each of 5 recipes' ready_log_regex | each regex matches ≥1 line |
| 07 | SIGTERM + graceful_shutdown_s — agents drain cleanly | 22-03 | 2 | `docker stop -t 5 <container>`; measure wall | <7s wall for each |
| 08 | env-file 0o600 vs `-e` flag — agent reads token from either | 22-03 | 2 | hermes already proven with env. nanobot probe: write `.env.nanobot` + `--env-file` flag + start gateway, check `channels.telegram enabled` logs | nanobot reads TELEGRAM_BOT_TOKEN from env-file identically |
| 09 | `_import_run_recipe_module` parents[4] in api container | 22-04 | 2 | `docker exec deploy-api_server-1 python -c "from pathlib import Path; print(Path('/app/api_server/src/api_server/services/runner_bridge.py').resolve().parents[4])"` | resolves to `/app` |
| 10 | `docker exec <container> openclaw pairing approve` latency + capture | 22-05 | 3 | fresh openclaw container + fake pair code probe; time wall + capture stdout | <2s wall; stdout contains "Approved" or known error |
| 11 | health endpoints — picoclaw `/ready`, openclaw `/`, nanobot `/health` | 22-05 | 3 | `curl -s http://127.0.0.1:<port><path>` against each running container | 200 OK per-agent or clear failure |
| 12 | `asyncio.to_thread` with fast `docker run -d` (2s vs one-shot's 2min) — tag_lock holds sanely | 22-04 | 2 | pytest-asyncio in api container: 3 concurrent `execute_persistent_start` on same image_tag | all 3 serialize through the lock; no race |
| 13 | `SectionHeader.step: string` renders "2.5" — no CSS break | 22-06 | 4 | local pnpm dev + visual inspect `http://localhost:3000/playground` with prop `step="2.5"` patched temporarily | renders with no layout break |

---

## Execution order

Probes are grouped by what needs what:

**Tier A — standalone / no container required** (fastest, blocks nothing):
- 02 age round-trip
- 03 Postgres partial unique index
- 04 schema v0.2 jsonschema validation

**Tier B — single container boot required** (each probe spins a recipe container):
- 01 pyrage in api_server
- 05 docker run -d persistent boot (5× recipes)
- 06 ready_log_regex per recipe
- 07 SIGTERM graceful per recipe
- 08 env-file flag
- 09 api_server module path
- 11 health endpoints
- 10 docker exec for openclaw

**Tier C — requires existing tier B infra to run**:
- 12 concurrent start lock behavior (needs run_cell_persistent written as a probe)

**Tier D — frontend only**:
- 13 SectionHeader "2.5" render

---

## Exit criteria

- Every probe yields PASS, FAIL, or SURPRISE verdict in a committed artifact
- Probes with FAIL/SURPRISE block their plan until the gotcha is re-specced
- Probes with PASS inject a citation into the matching plan's action block ("evidence: spike-NN-<slug>.md")
- After all probes land, update `22-VERIFICATION.md` with the spike-adjusted verdict

No plan executes until every probe has a verdict.
