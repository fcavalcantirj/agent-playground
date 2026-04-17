---
phase: 19
slug: api-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-16
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `19-RESEARCH.md` §Validation Architecture and `19-CONTEXT.md` §Success Criteria (13 SC items).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio ≥0.23 |
| **Config file** | `api_server/pyproject.toml` → `[tool.pytest.ini_options]` (Wave 0 creates) |
| **Quick run command** | `cd api_server && pytest -q -x -m "not api_integration"` |
| **Full suite command** | `cd api_server && pytest -q` (includes `api_integration` marker) |
| **Integration marker** | `@pytest.mark.api_integration` (parallel to runner's `integration`) |
| **Postgres strategy** | `testcontainers[postgres]` session-scoped fixture, TRUNCATE per test |
| **Live-deploy smoke** | `make smoke-api-live` (curls against deployed Hetzner box) |
| **Runner regression** | `pytest tools/tests/ -q` (must stay green — SC-11) |
| **Estimated runtime** | Quick ~5s · Full (with Postgres container) ~60–90s |

---

## Sampling Rate

- **After every task commit:** Run `cd api_server && pytest -q -x -m "not api_integration"`
- **After every plan wave:** Run `cd api_server && pytest -q` (full suite incl. `api_integration`)
- **Before `/gsd-verify-work`:** Full suite green + `make smoke-api-live` green against the deployed Hetzner box
- **Max feedback latency:** ~5s on quick, ~90s on full wave

---

## Per-Task Verification Map

> Task IDs are written after `/gsd-planner` completes. This table is the planner's checklist — every task must land in a row here with an automated command (or a Wave 0 dependency when the framework to run it doesn't exist yet).

| SC Ref | Behavior | Plan (likely) | Wave | Test Type | Automated Command | File Exists | Status |
|--------|----------|---------------|------|-----------|-------------------|-------------|--------|
| SC-01 | `GET /healthz` from internet returns `{"ok": true}` | 19-07 (deploy) | late | live smoke | `curl -fsS https://api.agentplayground.dev/healthz \| jq -e '.ok == true'` | ❌ W0 (deploy) | ⬜ pending |
| SC-02 | `/readyz` shows postgres+docker true + recipes_count | 19-02 | early | integration | `pytest -q api_server/tests/test_health.py::test_readyz_live` | ❌ W0 | ⬜ pending |
| SC-03 | `/v1/schemas` returns `["ap.recipe/v0.1"]` | 19-03 | mid | unit | `pytest -q api_server/tests/test_schemas.py::test_list_schemas` | ❌ W0 | ⬜ pending |
| SC-04 | `/v1/recipes` returns 5 recipes | 19-03 | mid | unit | `pytest -q api_server/tests/test_recipes.py::test_list_recipes_returns_five` | ❌ W0 | ⬜ pending |
| SC-05 | `POST /v1/runs` happy path PASS verdict | 19-04 | mid | api_integration | `pytest -m api_integration api_server/tests/test_runs.py::test_run_hermes_gpt4o_mini` | ❌ W0 | ⬜ pending |
| SC-06 | Idempotency-Key replays cached verdict, no re-run | 19-05 | mid | api_integration | `pytest -m api_integration api_server/tests/test_idempotency.py::test_same_key_returns_cache` | ❌ W0 | ⬜ pending |
| SC-07 | 50 concurrent runs bounded by semaphore to N | 19-04 | mid | api_integration | `pytest -m api_integration api_server/tests/test_runs.py::test_concurrency_semaphore_caps` | ❌ W0 | ⬜ pending |
| SC-08 | Runs persisted in Postgres | 19-01 / 19-04 | mid | unit + integration | `pytest -q api_server/tests/test_runs.py::test_persist_run_row` | ❌ W0 | ⬜ pending |
| SC-09 | 11th `POST /v1/runs` in 1 min returns 429 + `Retry-After` | 19-05 | mid | unit | `pytest -q api_server/tests/test_rate_limit.py::test_429_after_limit` | ❌ W0 | ⬜ pending |
| SC-10 | `pytest` default + `api_integration` suite all green | 19-all | late | all | `cd api_server && pytest -q` | ❌ W0 (framework) | ⬜ pending |
| SC-11 | Runner's existing 171 tests still pass unchanged | 19-06 (runner widen) | any | regression | `pytest tools/tests/ -q` | ✅ exists; must stay green | ⬜ pending |
| SC-12 | `/docs` 404 in prod, 200 in dev | 19-02 | early | unit | `pytest -q api_server/tests/test_docs_gating.py` | ❌ W0 | ⬜ pending |
| SC-13 | `openapi.json` → `openapi-typescript` produces valid TS | 19-07 | late | manual smoke | `make generate-ts-client` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Threat coverage (from research §Security Domain)

Every threat listed below must map to at least one automated test or documented accepted-risk. Planner adds test rows when plans bind to these threats.

| Threat | STRIDE | Mitigation | Test Hook |
|--------|--------|------------|-----------|
| BYOK key leak via logs | Info disclosure | Log allowlist middleware | `tests/test_log_redaction.py::test_authorization_header_not_logged` |
| BYOK key leak via `ps`/`/proc/cmdline` | Info disclosure | Runner already uses `--env-file` | regression in runner tests (SC-11) |
| Idempotency-Key cross-user collision | Tampering | UNIQUE `(user_id, key)` | `tests/test_idempotency.py::test_same_key_different_users_isolated` |
| Idempotency-Key reuse with different body | Forgery | `request_body_hash` → 422 | `tests/test_idempotency.py::test_body_mismatch_returns_422` |
| YAML bomb on `POST /v1/lint` | DoS | 256 KB body cap | `tests/test_lint.py::test_oversize_body_rejected` |
| SSRF via `recipe_name` | SSRF | Reject inline YAML; allowlist names | `tests/test_runs.py::test_inline_yaml_rejected` |
| Postgres SQL injection | Tampering | asyncpg parameterized queries only | `tests/test_runs.py::test_recipe_name_injection_is_safe` |
| Rate-limit bypass via `X-Forwarded-For` spoofing | Repudiation | Trust Caddy only; fallback to peer IP | `tests/test_rate_limit.py::test_spoofed_xff_ignored_when_no_trusted_proxy` |
| `git clone` option-as-value injection | Command injection | Phase 18 `source.ref` allowlist | runner regression (SC-11) |
| Docker socket escape | EoP | **Accepted trust boundary (D-08)** — documented, not mitigated in phase 19 | Documented risk in `deploy/README.md`; Phase 22+ moves to Sysbox |

---

## Wave 0 Requirements

Greenfield — `api_server/` does not exist yet. Wave 0 is large and load-bearing.

- [ ] `api_server/pyproject.toml` — FastAPI, asyncpg, alembic, pydantic v2, structlog, asgi-correlation-id, python-ulid, uvicorn, testcontainers[postgres], pytest, pytest-asyncio, httpx (all versions per 19-RESEARCH.md)
- [ ] `api_server/src/api_server/__init__.py`
- [ ] `api_server/src/api_server/main.py` — FastAPI app factory with lifespan (pool init + teardown)
- [ ] `api_server/tests/conftest.py` — testcontainers Postgres session fixture, TRUNCATE per-test fixture, `async_client` fixture (httpx AsyncClient + ASGI transport), recipe-dir fixture pointing at `recipes/`
- [ ] `api_server/alembic.ini`, `api_server/alembic/env.py`, `api_server/alembic/versions/001_baseline.py` — async template, 5-table baseline
- [ ] `api_server/Makefile` or root `Makefile` additions: `make api-dev`, `make api-test`, `make smoke-api-live`, `make generate-ts-client`
- [ ] CI additions (if any CI exists) — unit job runs `pytest -q -m "not api_integration"`; integration job runs `pytest -m api_integration` with a Postgres service

*Runner test infra (`tools/tests/`) stays untouched — SC-11 is a regression gate, not a Wave 0 item.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live TLS cert issued by Let's Encrypt | SC-01 / deploy | Can't automate ACME from CI without a real public DNS record | `curl -vI https://api.agentplayground.dev 2>&1 \| grep -E "subject:.*agentplayground"` after Caddy boot |
| Caddy reverse proxy actually routes to api_server container | SC-01/02 | Docker compose network state is environmental | `docker compose -f deploy/docker-compose.prod.yml logs caddy api_server` + curl `/healthz` |
| `openapi.json` → generated TypeScript client compiles | SC-13 | Requires Node tooling; not enforced in Python CI job | `npx openapi-typescript https://api.agentplayground.dev/openapi.json -o /tmp/client.ts && npx tsc --noEmit /tmp/client.ts` |
| Docker socket mount privilege documented | D-08 trust boundary | Risk is accepted, not mitigated — needs human-read doc | Reviewer reads `deploy/README.md` § "Trust Boundary: Docker Socket" |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (bootstrap api_server/ from zero)
- [ ] No watch-mode flags (pytest, not `pytest --watch`)
- [ ] Feedback latency < 90s on full suite
- [ ] `nyquist_compliant: true` set in frontmatter after planner fills Per-Task Verification Map with task IDs

**Approval:** pending
