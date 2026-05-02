---
phase: 23
slug: backend-mobile-api-chat-proxy-persistence-auth-shim
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-01
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.23+ (`asyncio_mode="auto"`) |
| **Config file** | `api_server/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd api_server && pytest -x -m "not api_integration"` |
| **Full suite command** | `cd api_server && pytest tests/` |
| **E2E gate command** | `cd api_server && make e2e-inapp-docker` |
| **Estimated runtime** | ~30s quick / ~3-4 min full / ~6-10 min e2e (testcontainers + real Docker) |

---

## Sampling Rate

- **After every task commit:** Run `pytest -x -m "not api_integration"` (quick — unit + ASGITransport-only integration in <30s).
- **After every plan wave:** Run `pytest tests/` (full suite including testcontainer-backed Postgres + Redis).
- **Before `/gsd-verify-work`:** Full suite green AND `make e2e-inapp-docker` green.
- **Max feedback latency:** 30 seconds (per-task), 4 minutes (per-wave).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 23-W0-01 | spike | 0 | D-31 | T-23-GZIP-SSE | GZipMiddleware does not buffer `text/event-stream` chunks | spike (integration) | `pytest tests/spikes/test_gzip_sse_compat.py -x` | ❌ W0 | ⬜ pending |
| 23-W0-02 | spike | 0 | API-05 (A1) | T-23-AUD-CONFUSION | `verify_oauth2_token(audience=[a,b])` accepts JWT whose aud matches either entry | spike | `pytest tests/spikes/test_google_auth_multi_audience.py -x` | ❌ W0 | ⬜ pending |
| 23-W0-03 | spike | 0 | API-05 (A2) | T-23-MOCKING | respx intercepts the JWKS HTTP fetch made by google-auth's PyJWKClient | spike | `pytest tests/spikes/test_respx_intercepts_pyjwk_fetch.py -x` | ❌ W0 | ⬜ pending |
| 23-API01-01 | idempotency | 1 | API-01 | T-23-V11-DOUBLE-SPEND | Missing `Idempotency-Key` header → 400 with Stripe-shape envelope | unit + integration | `pytest tests/routes/test_messages_idempotency_required.py -x` | ❌ W0 | ⬜ pending |
| 23-API01-02 | idempotency | 1 | API-01 | T-23-V11-DOUBLE-SPEND | Idempotency-Key replay returns same `message_id` (cached 202) | integration | `pytest tests/test_idempotency.py -x` (extend existing) | ✅ extend | ⬜ pending |
| 23-API02-01 | history | 1 | API-02 | T-23-V4-XUSER | `GET /v1/agents/:id/messages` ORDER BY created_at ASC, default limit=200, max=1000 | unit + integration | `pytest tests/routes/test_agent_messages_get.py -x` | ❌ W0 | ⬜ pending |
| 23-API02-02 | history | 1 | API-02 | T-23-V4-XUSER | `done` rows emit `(user, assistant)`; `failed` rows emit `(user, error kind=error content="⚠️ delivery failed: …")` | integration | same | ❌ W0 | ⬜ pending |
| 23-API02-03 | history | 1 | API-02 | T-23-V4-XUSER | Cross-user request → 403 / empty (require_user + agent_instance.user_id filter) | integration | same | ❌ W0 | ⬜ pending |
| 23-API03-01 | agents-status | 1 | API-03 | T-23-V4-XUSER | `GET /v1/agents` includes `status` derived from `agent_containers.container_status` LATERAL | integration (real container fixture) | `pytest tests/routes/test_agents_status_field.py -x` | ❌ W0 | ⬜ pending |
| 23-API03-02 | agents-status | 1 | API-03 | T-23-V4-XUSER | `GET /v1/agents` includes `last_activity = MAX(ai.last_run_at, MAX(im.created_at))` | integration | same | ❌ W0 | ⬜ pending |
| 23-API03-03 | agents-status | 1 | API-03 | — | `last_activity` is `None` when user has no runs and no messages | unit | same | ❌ W0 | ⬜ pending |
| 23-API04-01 | models-proxy | 2 | API-04 | T-23-OR-PASSTHRU | Cache miss → fetch + cache (15min TTL); response is byte-equal to upstream | integration (respx) | `pytest tests/routes/test_models.py -x -k cache_miss` | ❌ W0 | ⬜ pending |
| 23-API04-02 | models-proxy | 2 | API-04 | — | Cache hit within TTL → no upstream refetch | integration | `pytest tests/routes/test_models.py -x -k cache_hit` | ❌ W0 | ⬜ pending |
| 23-API04-03 | models-proxy | 2 | API-04 | — | Stale-while-revalidate on fetch failure → serve stale + log error | integration | `pytest tests/routes/test_models.py -x -k stale_while_revalidate` | ❌ W0 | ⬜ pending |
| 23-API04-04 | models-proxy | 2 | API-04 | T-23-GZIP-COMPRESS | `Accept-Encoding: gzip` → `content-encoding: gzip` set; payload ≥1024 bytes triggered | integration | `pytest tests/routes/test_models.py -x -k gzip_header` | ❌ W0 | ⬜ pending |
| 23-API04-05 | models-proxy-fe | 3 | API-04 | T-23-GR2-DUMB-CLIENT | `frontend/components/playground-form.tsx` no longer fetches `https://openrouter.ai/...` directly; uses `apiGet("/v1/models")` | grep + manual smoke | `grep -E "openrouter\\.ai/api/v1/models" frontend/components/playground-form.tsx` (must return zero hits) | ✅ test | ⬜ pending |
| 23-API05-G-01 | oauth-mobile | 2 | API-05 | T-23-V2-AUTH | `POST /v1/auth/google/mobile` happy path → 200 + session_id + user obj; row in `sessions` + `users` | integration (respx + real PG) | `pytest tests/auth/test_oauth_mobile.py -x -k google_happy` | ❌ W0 | ⬜ pending |
| 23-API05-G-02 | oauth-mobile | 2 | API-05 | T-23-V2-AUTH | Invalid signature → 401 generic error | integration | `pytest tests/auth/test_oauth_mobile.py -x -k google_invalid_sig` | ❌ W0 | ⬜ pending |
| 23-API05-G-03 | oauth-mobile | 2 | API-05 | T-23-V2-AUTH | Expired token → 401 | integration | `pytest tests/auth/test_oauth_mobile.py -x -k google_expired` | ❌ W0 | ⬜ pending |
| 23-API05-G-04 | oauth-mobile | 2 | API-05 | T-23-AUD-CONFUSION | Audience mismatch (JWT for wrong client_id) → 401 | integration | `pytest tests/auth/test_oauth_mobile.py -x -k google_aud_mismatch` | ❌ W0 | ⬜ pending |
| 23-API05-G-05 | oauth-mobile | 2 | API-05 | T-23-V2-AUTH | Missing required claims (no `sub` or no `email`) → 401 | integration | `pytest tests/auth/test_oauth_mobile.py -x -k google_missing_claims` | ❌ W0 | ⬜ pending |
| 23-API05-GH-01 | oauth-mobile | 2 | API-05 | T-23-V2-AUTH | `POST /v1/auth/github/mobile` happy path with public email → 200 + session | integration (respx) | `pytest tests/auth/test_oauth_mobile.py -x -k github_public_email` | ❌ W0 | ⬜ pending |
| 23-API05-GH-02 | oauth-mobile | 2 | API-05 | T-23-V2-AUTH | Private email → `/user/emails` fallback returns primary verified email | integration | `pytest tests/auth/test_oauth_mobile.py -x -k github_private_email` | ❌ W0 | ⬜ pending |
| 23-API05-GH-03 | oauth-mobile | 2 | API-05 | T-23-V2-AUTH | Invalid access_token → GitHub /user 401 → endpoint 401 | integration | `pytest tests/auth/test_oauth_mobile.py -x -k github_invalid_token` | ❌ W0 | ⬜ pending |
| 23-API05-CK-01 | oauth-mobile | 2 | API-05 | T-23-V3-SESSION | Sign in → use `Cookie: ap_session=<uuid>` header on next request → 200 (mobile-cookie continuity) | integration | `pytest tests/auth/test_oauth_mobile.py -x -k cookie_continuity` | ❌ W0 | ⬜ pending |
| 23-API06-01 | drop-api06 | 3 | API-06 | — | No new `messages` migration exists; `inapp_messages` is the single source of chat history | unit | `pytest tests/test_migration.py -x -k no_rogue_messages_table` | ✅ extend | ⬜ pending |
| 23-API07-01 | e2e-gate | 3 | API-07 | T-23-E2E | Real Postgres + real Docker chat round-trip still green | E2E | `make e2e-inapp-docker` | ✅ existing | ⬜ pending |
| 23-GZ-01 | gzip-middleware | 2 | D-25 / D-31 | T-23-GZIP-SSE | `GZipMiddleware(minimum_size=1024)` registered in `main.py`; SSE route NOT compressed | unit + integration | `pytest tests/test_main_middleware.py -x -k gzip_registered` AND re-run `tests/spikes/test_gzip_sse_compat.py` | ❌ W0 | ⬜ pending |
| 23-REQ-01 | requirements-amend | 3 | D-32 | — | `.planning/REQUIREMENTS.md` reflects API-01 rewrite, API-05 rewrite, API-06 dropped, traceability updated | grep | `grep -E "Idempotency-Key required" .planning/REQUIREMENTS.md` AND `grep -E "API-06.*DROPPED\\|Replaced by" .planning/REQUIREMENTS.md` | ❌ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

**Spike files (PLAN BLOCKS UNTIL ALL PASS):**

- [ ] `tests/spikes/test_gzip_sse_compat.py` — D-31 mandatory: configure GZipMiddleware, fire SSE through `GET /v1/agents/:id/messages/stream`, assert chunks delivered as emitted (NOT batched). **Plan does not seal until this PASSES — Golden Rule #5.**
- [ ] `tests/spikes/test_google_auth_multi_audience.py` — A1 spike: confirm `verify_oauth2_token(audience=[a,b])` accepts JWTs whose aud matches either entry. ~5 LOC. Saves plan-checker iteration if proven before plan-seal.
- [ ] `tests/spikes/test_respx_intercepts_pyjwk_fetch.py` — A2 spike: confirm respx intercepts the JWKS HTTP fetch made by google-auth's PyJWKClient. If FAILS → plan must use `monkeypatch verify_oauth2_token` fallback path.

**New test files (covers Phase 23 requirements):**

- [ ] `tests/auth/test_oauth_mobile.py` — covers API-05 (9 cells in matrix per D-30; mirrors `respx_oauth_providers` + `authenticated_cookie` fixture patterns).
- [ ] `tests/routes/test_messages_idempotency_required.py` — covers API-01 D-09 enforcement.
- [ ] `tests/routes/test_agent_messages_get.py` — covers API-02 (NEW route handler for chat history per D-03 + D-04).
- [ ] `tests/routes/test_agents_status_field.py` — covers API-03 (`status` + `last_activity` LATERAL JOIN).
- [ ] `tests/routes/test_models.py` — covers API-04 (cache hit/miss, stale-while-revalidate, gzip header).

**Test config / fixtures:**

- [ ] `tests/auth/conftest.py` — extend with `authenticated_mobile_session` fixture (mirrors `authenticated_cookie`).
- [ ] `tests/conftest.py` — TRUNCATE CASCADE list already covers 8 tables (users, agent_instances, agent_containers, runs, agent_events, idempotency_keys, rate_limit_counters, sessions); confirm no extension needed.

**Framework install:** NONE — all test deps already in `api_server/pyproject.toml` (pytest, pytest-asyncio, respx, httpx, testcontainers, miniredis equivalent for Redis-via-testcontainers, etc.).

**Direct dep promotion (NOT a Wave 0 install but a `pyproject.toml` edit):**

- [ ] `google-auth>=2.40,<3` — currently transitive only; promote to direct dep so future cleanup of transitive deps doesn't silently break Google JWT verify.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Google Cloud Console mobile-client registration (Android + iOS client IDs added to allowed-audiences env var) | API-05 | Cloud Console UI is human-driven; cannot script Google's project setup | Document in `deploy/RUNBOOK.md` (or equivalent): "Create Android + iOS OAuth clients in Google Cloud Console for project `<project_id>`. Copy client IDs into `GOOGLE_OAUTH_MOBILE_CLIENT_IDS` (comma-separated) in `deploy/.env.dev.example`." Plan task may verify the env-var stanza is present + documented. |
| GitHub OAuth app — add mobile redirect URI scheme to whitelist | API-05 | GitHub OAuth-app config is UI-driven | Document: "Add `solvr://oauth/github` (final scheme settled in Phase 24's spec) to existing GitHub OAuth app's allowed redirect URIs." |
| OpenRouter `/api/v1/models` payload-size sanity (~200KB → ~50KB after gzip) | API-04 / D-25 | Empirical real-world traffic check; tests assert behavior not absolute bytes | Spot-check: `curl -s -o /tmp/models.json https://openrouter.ai/api/v1/models && wc -c < /tmp/models.json` (expect 200-500KB raw). Already verified in research (430KB raw, 50KB gzipped). Re-check during phase exit. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (3 spikes + 5 new test files + 1 fixture extension)
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s per-task quick / < 4min per-wave
- [ ] `nyquist_compliant: true` set in frontmatter (toggle when planner finalizes plan ↔ task ID alignment)

**Approval:** pending
