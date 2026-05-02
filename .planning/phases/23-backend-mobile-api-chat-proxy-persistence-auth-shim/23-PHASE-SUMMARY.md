---
phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
type: phase-summary
status: SHIPPED
milestone: v0.3-mobile-mvp
plans_shipped: 9  # 23-01..23-09
waves: 4         # Wave 0 spikes + Wave 1 routes + Wave 2 OAuth/models + Wave 3 frontend migration / requirements amendments / phase-exit gate
requirements_completed:
  - API-01  # Idempotency-Key REQUIRED on POST /v1/agents/:id/messages
  - API-02  # GET /v1/agents/:id/messages chat-history
  - API-03  # status + last_activity on GET /v1/agents
  - API-04  # GET /v1/models OpenRouter passthrough
  - API-05  # POST /v1/auth/{google,github}/mobile credential exchange
  - API-07  # Integration tests against real Postgres + real Docker
requirements_dropped:
  - API-06  # ~~migrations create messages table~~ DROPPED — Phase 23 D-01 reuses inapp_messages
amendments_applied:
  - D-32  # REQUIREMENTS.md API-01/05 rewrites + API-06 strikethrough + traceability rows
opens_for:
  - 24-flutter-foundation  # Mobile MVP next phase per ROADMAP
completed: 2026-05-02
---

# Phase 23 — Backend Mobile API (Chat Proxy + Persistence + Auth Shim) Phase Summary

**SHIPPED 2026-05-02. 9 plans, 4 waves, 7 API-* requirements completed (API-06 dropped per D-01), Phase-exit gate green: pytest 336 passed + make e2e-inapp-docker 5/5 PASS, no Phase 22c.3.1 substrate regressions.**

## What Phase 23 delivered

| Plan | Title | Wave | What landed |
|------|-------|------|-------------|
| 23-01 | Wave 0 spikes + setup gate | 0 | 3 spikes (D-31 GZip×SSE compat, A1 google-auth multi-audience, A2 respx-vs-google-auth-transport) + `google-auth` + `starlette` promoted to direct deps + `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS` env-var stanza |
| 23-02 | D-09 Idempotency-Key REQUIRED on POST messages | 1 | `Idempotency-Key` REQUIRED on `POST /v1/agents/:id/messages`; missing/whitespace → 400 INVALID_REQUEST envelope; check fires BEFORE `require_user` per Pitfall 8 |
| 23-03 | GET /v1/agents/:id/messages chat-history | 1 | New route handler emits `(user, assistant)` pairs for `done` rows + `(user, error kind=error)` for `failed` rows; ORDER BY ASC; default limit 200, max 1000 |
| 23-04 | /v1/agents status + last_activity (LATERAL JOIN) | 1 | Two LATERAL JOINs added to `list_agents`: live `agent_containers.container_status` (D-10/D-11) + `GREATEST(ai.last_run_at, MAX(im.created_at))` (D-27) |
| 23-05 | GET /v1/models OpenRouter passthrough | 2 | New `/v1/models` route + service with 15min TTL cache + stale-while-revalidate on upstream failure + GZipMiddleware (text/event-stream excluded per D-31) |
| 23-06 | POST /v1/auth/{google,github}/mobile | 2 | Two mobile-OAuth credential-exchange endpoints; multi-audience Google ID-token verify; GitHub primary-verified-email fallback; ap_session cookie continuity |
| 23-07 | Frontend /v1/models migration | 3 | `frontend/components/playground-form.tsx` no longer fetches openrouter.ai directly; uses `apiGet('/api/v1/models')` (Golden Rule #2 dumb-client; Golden Rule R-2 catalog comes from server) |
| 23-08 | REQUIREMENTS.md D-32 amendment | 3 | API-01 + API-05 rewordings; API-06 strikethrough (DROPPED — replaced by inapp_messages reuse per D-01); Traceability rows updated |
| 23-09 | Phase-exit gate (this plan) | 3 | `pytest tests/` 336 passed + 51 new Phase-23 tests all green; `make e2e-inapp-docker` GATE PASS — 5/5 cells; +1 Rule-3 deviation (test-runner Dockerfile dep gap closed) |

**Total commits in Phase 23 across main + merged worktrees:** 46.

## Phase-exit gate evidence

- `cd api_server && pytest tests/ --ignore=tests/e2e/` → **336 passed / 4 skipped / 9 failed / 1 error in 5m07s** (all 10 not-passing items confirmed PRE-EXISTING by re-running against pre-Phase-23 commit `08ae135` on a `/tmp/baseline-pre23` worktree — the Phase 22c.3.1 SHIPPED memory captured "8 pre-existing failures" baseline; Phase 23 added 51 tests to that baseline, all GREEN).
- `cd api_server && make e2e-inapp-docker` → **GATE PASS — 5/5 cells**. `e2e-report.json` shows `"passed": true` with all 5 recipes (hermes/nanobot/openclaw/nullclaw/zeroclaw) PASS, including the 3-way contract switch (openai_compat ×3, a2a_jsonrpc ×1, zeroclaw_native ×1).
- Phase-23 explicit new-test verification: `pytest tests/spikes/ tests/auth/test_oauth_mobile.py tests/routes/test_messages_idempotency_required.py tests/routes/test_agent_messages_get.py tests/routes/test_agents_status_field.py tests/routes/test_models.py` → **51 passed in 23.65s**.
- No mocks introduced for core substrate (Golden Rule #1) — `git diff 08ae135..HEAD -- tests/ src/ | grep MagicMock` returns zero hits in production source. The respx stubs in `test_oauth_mobile.py` (Google JWKS, GitHub /user) and `test_models.py` (OpenRouter) are upstream HTTP boundaries only, explicitly allowed by Plan 23-09 must_haves.truths #3.

## Wave 0 spike artifacts (preserved as regression tripwires)

- `api_server/tests/spikes/test_gzip_sse_compat.py` — D-31: GZipMiddleware does NOT buffer `text/event-stream` (Starlette ≥0.46 default-excludes the type per PR #2871). Empirically proved via ASGI-event-level inspection (NOT httpx.ASGITransport which would buffer).
- `api_server/tests/spikes/test_google_auth_multi_audience.py` — A1: `verify_oauth2_token(audience=[a,b,c])` accepts JWTs whose `aud` matches ANY list element. Self-signed PEM + `RSASigner` + `google.auth.jwt.encode` are the cryptographically-faithful test seam.
- `api_server/tests/spikes/test_respx_intercepts_pyjwk_fetch.py` — A2: respx does NOT intercept google-auth's `requests`-based transport. Plan 23-06 mobile-OAuth tests therefore use `monkeypatch _fetch_certs` for JWKS-fetch stubbing (not respx).

## D-32 amendments (REQUIREMENTS.md)

| Req | Status | Source-of-truth in REQUIREMENTS.md |
|-----|--------|-----------------------------------|
| API-01 | Pending — amended D-32 | "Idempotency-Key required on POST /v1/agents/:id/messages" (rewrite) |
| API-05 | Pending — amended D-32 | "POST /v1/auth/{google,github}/mobile credential-exchange" (rewrite) |
| API-06 | DROPPED — replaced by inapp_messages reuse per D-01 | Strikethrough preserved; replacement note inline |

## Pointers

- **Resume next:** Phase 24 (Flutter Foundation) — depends on this phase per ROADMAP. The mobile-side scaffolding consumes `/v1/auth/{google,github}/mobile`, `/v1/models`, `/v1/agents` (with status + last_activity), `/v1/agents/:id/messages` GET + POST, and the existing SSE stream.
- **Phase 23 deliverables location:** API source under `api_server/src/api_server/{auth,routes,services}/`; test artifacts under `api_server/tests/{spikes,auth,routes}/`; frontend migration in `frontend/components/playground-form.tsx`; REQUIREMENTS amendments in `.planning/REQUIREMENTS.md`.
- **Phase 22c.3.1 substrate:** preserved unchanged by Phase 23 (5/5 e2e cells PASS); the runner-side inapp wiring + dispatcher 3-way contract switch + persist-before-action invariants all still hold.

## Open follow-up debt (out-of-scope, deferred)

Items in `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/deferred-items.md`:

1. `tests/test_idempotency.py::test_same_key_different_users_isolated` — pre-existing; missing `name` column in seed INSERT. Suggested fix is a 2-line edit; can land in any future maintenance plan.
2. `tests/spikes/test_truncate_cascade.py::test_truncate_cascade_clears_all_tables_preserves_alembic_version` — pre-existing; alembic revision-id drift in spike's hardcoded target.

The 22c.3.1 SUMMARY's "Rule-3 workaround in `pytest_sessionfinish` calls `os._exit`" debt is also still open — pre-existing watcher_service shutdown hang under the dockerized harness; gated on `AP_E2E_DOCKERIZED_HARNESS=1` so the non-dockerized path is unaffected.
