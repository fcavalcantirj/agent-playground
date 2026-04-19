---
phase: 22c
slug: oauth-google
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-19
---

# Phase 22c — Validation Strategy

> Per-phase validation contract. 8 SPEC requirements (R1..R8) map to curl / psql / grep / pytest / manual assertions.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (backend) + Node type-check + manual browser smoke |
| **Config file** | `api_server/pyproject.toml` (pytest) + `frontend/package.json` (type-check) |
| **Quick run command** | `cd api_server && uv run pytest tests/auth/ -x` |
| **Full suite command** | `cd api_server && uv run pytest -x` + `cd frontend && pnpm typecheck && pnpm build` |
| **Estimated runtime** | ~45s quick; ~3–5min full |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/auth/ -x` (scoped)
- **After every plan wave:** Run full backend pytest + frontend build
- **Before verification gate (SPEC acceptance criteria):** Full suite green + manual browser smoke (D-22c-TEST-02)
- **Max feedback latency:** ~45s scoped; ~5min full suite

---

## Per-Requirement Verification Map

All 8 SPEC requirements (R1..R8) plus the 4 CONTEXT amendments (AMD-01..07) and Wave 0 spikes (D-22c-TEST-03).

| REQ | Wave | What it proves | Test Type | Automated Command |
|-----|------|----------------|-----------|-------------------|
| **SPIKE-A** (D-22c-TEST-03) | 0 | respx intercepts authlib's httpx call to Google token endpoint | integration | `uv run pytest tests/spikes/test_respx_authlib.py -x` |
| **SPIKE-B** (D-22c-TEST-03) | 0 | TRUNCATE CASCADE on 8-table FK graph works; `alembic_version` preserved | integration | `uv run pytest tests/spikes/test_truncate_cascade.py -x` |
| **R1** (Google authorize) | 1 | `GET /v1/auth/google` returns 302 with Google URL + state cookie | integration | `uv run pytest tests/auth/test_google_authorize.py::test_302_with_state -x` |
| **R1** (curl smoke) | 1 | `curl -sI http://localhost:8000/v1/auth/google` returns 302 | manual curl | `curl -sI http://localhost:8000/v1/auth/google \| grep -E "^(HTTP/1.1 302\|Location: https://accounts.google.com/\|Set-Cookie: ap_oauth_state=)"` |
| **R1** (GitHub authorize — AMD-01) | 1 | `GET /v1/auth/github` returns 302 with GitHub URL + state cookie | integration | `uv run pytest tests/auth/test_github_authorize.py::test_302_with_state -x` |
| **R2** (Google callback success) | 1 | callback upserts user, mints session, sets cookie, redirects to /dashboard | integration | `uv run pytest tests/auth/test_google_callback.py::test_full_flow_respx -x` |
| **R2** (Google callback state mismatch) | 1 | callback with bad state returns 400 | integration | `uv run pytest tests/auth/test_google_callback.py::test_state_mismatch -x` |
| **R2** (GitHub callback success + /user/emails fallback) | 1 | GitHub callback: token → /user → /user/emails when email null → picks primary+verified | integration | `uv run pytest tests/auth/test_github_callback.py::test_full_flow_emails_fallback -x` |
| **R3** (SessionMiddleware resolves user_id) | 1 | middleware reads `ap_session`, looks up PG, sets `request.state.user_id` | integration | `uv run pytest tests/middleware/test_session_middleware.py -x` |
| **R3** (ANONYMOUS_USER_ID removed from routes) | 2 | zero hits of constant in route handlers | grep | `! grep -rn "ANONYMOUS_USER_ID" api_server/src/api_server/routes/ api_server/src/api_server/middleware/` |
| **R3** (constant deleted — AMD-03/D-22c-MIG-06) | 2 | `ANONYMOUS_USER_ID` no longer exported from constants.py | grep | `! grep -n "ANONYMOUS_USER_ID" api_server/src/api_server/constants.py` |
| **R4** (/v1/users/me authenticated) | 1 | with cookie: 200 + real email | integration | `uv run pytest tests/routes/test_users_me.py::test_200_with_session -x` |
| **R4** (/v1/users/me anonymous) | 1 | without cookie: 401 + Stripe-envelope `{error: {code: "unauthorized"}}` | integration | `uv run pytest tests/routes/test_users_me.py::test_401_no_session -x` |
| **R5** (/v1/auth/logout) | 1 | deletes sessions row, clears cookie, returns 204 | integration | `uv run pytest tests/auth/test_logout.py::test_204_and_invalidates -x` |
| **R6** (login page no setTimeout) | 2 | zero `setTimeout` occurrences | grep | `! grep -c "setTimeout" frontend/app/login/page.tsx \| grep -v "^0$"` |
| **R6** (Google button starts real flow) | 2 | button's onClick navigates to `/api/v1/auth/google` | grep | `grep -q "window.location.href.*\/api\/v1\/auth\/google" frontend/app/login/page.tsx` |
| **R7** (layout no Alex Chen) | 2 | zero `Alex Chen` occurrences | grep | `! grep -q "Alex Chen" frontend/app/dashboard/layout.tsx frontend/components/navbar.tsx` |
| **R7** (layout fetches /v1/users/me) | 2 | navbar/layout calls `apiGet('/api/v1/users/me')` | grep | `grep -q "apiGet.*users\/me" frontend/components/navbar.tsx frontend/app/dashboard/layout.tsx` |
| **R8** (migration 006 truncates all tables — AMD-04) | 2 | post-migration all 8 data tables have COUNT=0 | psql | `for t in agent_events runs agent_containers agent_instances idempotency_keys rate_limit_counters sessions users; do psql "$AP_DATABASE_URL" -tAc "SELECT COUNT(*) FROM $t" \| grep -q "^0$" \|\| exit 1; done` |
| **R8** (alembic_version preserved) | 2 | `alembic_version` table survives migration 006 with revision "006" | psql | `psql "$AP_DATABASE_URL" -tAc "SELECT version_num FROM alembic_version" \| grep -q "^006"` |
| **AMD-05** (respx is dev dep) | 0 | respx in pyproject dev deps | grep | `grep -q "respx" api_server/pyproject.toml` |
| **AMD-06** (proxy.ts exists) | 2 | `frontend/proxy.ts` file present + no stale `frontend/middleware.ts` | file+grep | `test -f frontend/proxy.ts && ! test -f frontend/middleware.ts` |
| **AMD-07** (AP_OAUTH_STATE_SECRET wired) | 1 | env var present in config.py Pydantic settings | grep | `grep -q "ap_oauth_state_secret" api_server/src/api_server/config.py` |
| **AMD-07** (prod fail-loud) | 1 | boot with `AP_ENV=prod` and missing secret exits non-zero | integration | `uv run pytest tests/config/test_oauth_state_secret_fail_loud.py -x` |
| **CSRF** (SPEC acceptance — state mismatch) | 1 | callback with mismatched state returns 400 | integration | same as R2 state-mismatch case |
| **Cross-user isolation** (SPEC acceptance) | 1 | 2 different Google users each see only their own agents | integration | `uv run pytest tests/auth/test_cross_user_isolation.py -x` |
| **Cookie redaction in logs** (CONTEXT §Established Patterns) | 1 | `ap_session` + `ap_oauth_state` values masked in log output | integration | `uv run pytest tests/middleware/test_log_redact_cookies.py -x` |
| **last_seen_at per-worker throttle** (D-22c-MIG-05) | 1 | in-memory dict throttles UPDATEs at 60s; 2 rapid requests in same worker → 1 PG UPDATE | integration | `uv run pytest tests/middleware/test_last_seen_throttle.py -x` |
| **Idempotency middleware user_id wiring** (D-22c-AUTH-04) | 2 | idempotency reads `request.state.user_id`; no ANONYMOUS_USER_ID import | grep+integration | `! grep -q "ANONYMOUS_USER_ID" api_server/src/api_server/middleware/idempotency.py` + `uv run pytest tests/middleware/test_idempotency_user_id.py -x` |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — filled during execution.*

---

## Wave 0 Requirements

Wave 0 (spikes + test scaffolding) runs BEFORE any downstream wave. Per golden rule 5 + D-22c-TEST-03, downstream waves do NOT execute against a red spike.

- [ ] `api_server/pyproject.toml` — add `respx` to dev deps (AMD-05)
- [ ] `api_server/pyproject.toml` — confirm `authlib` added (net-new prod dep)
- [ ] `api_server/tests/spikes/test_respx_authlib.py` — SPIKE-A (respx × authlib interop)
- [ ] `api_server/tests/spikes/test_truncate_cascade.py` — SPIKE-B (TRUNCATE CASCADE 8-table graph)
- [ ] `api_server/tests/conftest.py` — shared fixtures: testcontainers PG, respx router factory, session-cookie helper
- [ ] `api_server/tests/auth/` directory scaffold — empty test files for every REQ/AMD row above
- [ ] `api_server/tests/middleware/` directory scaffold — session middleware, log redaction, last_seen throttle tests
- [ ] `.planning/phases/22c-oauth-google/spike-evidence/` directory — captures spike output (pytest logs + psql before/after row counts)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end Google button click lands on /dashboard with real email | SPEC acceptance #2 | Real Google consent screen cannot be scripted safely | 1) Run local stack. 2) Visit `http://localhost:3000/login`. 3) Click "Sign in with Google". 4) Consent. 5) Assert redirect to /dashboard + email shown in navbar matches Gmail account. |
| End-to-end GitHub button click lands on /dashboard with real email | AMD-01 + SPEC acceptance #2 extended | Same as above, GitHub variant | Same flow with "Sign in with GitHub". Verify `/user/emails` fallback if GitHub primary email is private. |
| Mobile responsive OAuth flow | not in SPEC | Browser automation overkill for v1 | Optional smoke on phone; not a gate. |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 spikes (A + B) passed before Wave 1 executes
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s scoped, < 5min full
- [ ] `nyquist_compliant: true` set in frontmatter at execution time

**Approval:** pending
