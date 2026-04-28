---
phase: 22c-oauth-google
plan: 09
subsystem: testing
tags: [oauth, integration-test, cross-user-isolation, manual-smoke, phase-exit-gate, r8-belt-and-suspenders]

# Dependency graph
requires:
  - phase: 22c-oauth-google
    provides: "plan 22c-06 — alembic 006 purge + require_user wired across 4 route files (the change under test)"
  - phase: 22c-oauth-google
    provides: "plan 22c-07 + 22c-08 — frontend login/dashboard/proxy.ts (the surfaces exercised by the manual smoke)"
provides:
  - "api_server/tests/auth/test_cross_user_isolation.py — 2-user cross-isolation integration test (require_user proves zero leakage at GET /v1/agents)"
  - "R8 belt-and-suspenders: 8-table COUNT=0 pre-assertion at test start (proves migration 006 ran during conftest init)"
  - "test/22c-manual-smoke.md — 6-scenario human checklist for D-22c-TEST-02 phase-exit gate"
  - "Phase 22c CLOSED: STATE.md updated + ROADMAP.md 22c-09 [x] flipped"
affects: [22c.1-ux-gap-closure, future-phases-relying-on-real-user-id]

# Tech tracking
tech-stack:
  added: []  # no new deps — exercised the existing test stack
  patterns:
    - "Phase-exit gate combines automated (cross-user isolation) + manual (browser OAuth consent) — D-22c-TEST-02"
    - "Belt-and-suspenders pre-assertion: integration test asserts 8-table COUNT=0 at start to catch any silent skip of migration 006 (R8 Layer 3)"
    - "Inline plan-gap fixes during smoke (Dockerfile drift + missing httpx + frontend host redirect) committed as 22c-09 — surface gaps rather than hide them"

key-files:
  created:
    - api_server/tests/auth/test_cross_user_isolation.py
    - test/22c-manual-smoke.md
    - .planning/phases/22c-oauth-google/22c-09-SUMMARY.md
  modified:
    - api_server/pyproject.toml  # httpx promoted to runtime deps
    - tools/Dockerfile.api        # authlib + itsdangerous + httpx added to pip install chain
    - api_server/src/api_server/config.py  # AP_FRONTEND_BASE_URL added
    - api_server/src/api_server/routes/auth.py  # redirects prefixed with frontend_base_url
    - api_server/tests/auth/test_google_callback.py  # assertion updated for absolute URL
    - api_server/tests/auth/test_github_callback.py  # assertion updated for absolute URL
    - .planning/STATE.md
    - .planning/ROADMAP.md

key-decisions:
  - "Manual smoke gate is human-action (not human-verify); auto_advance=true does NOT auto-approve. Wave 5 closure waited on real user PASS report."
  - "Three plan gaps surfaced by smoke (Dockerfile authlib+itsdangerous, missing httpx, OAuth callback resolves to API host) all fixed inline as 22c-09 commits — surfaces issues rather than hiding them in 22c.1."
  - "OAuth callback redirect bug fixed via AP_FRONTEND_BASE_URL env (default http://localhost:3000) prefix — minimal change, works dev + prod, no proxy reroute needed."
  - "Three out-of-scope UX findings (Alex Chen on /playground, /#playground fragment, Persistent+Telegram default + conditional fields) NOT expanded into 22c — logged as 22c.1 candidates per AMD-02 (OAuth-identity-only scope discipline)."

patterns-established:
  - "Phase-exit gate pattern: automated test + manual checklist file + checkpoint:human-verify task — generalizable to future phases that touch real user-facing flows."
  - "When the smoke gate uncovers a plan gap, fix in-scope under the gate's plan number rather than rolling forward — keeps the phase atomic in git history."

requirements-completed: [SPEC-AC-cross-user-isolation, SPEC-AC-manual-smoke-google, SPEC-AC-manual-smoke-github, D-22c-TEST-02, R8-belt-and-suspenders]

# Metrics
duration: ~6h (across 2 sessions due to Docker daemon hang + machine restart)
completed: 2026-04-28
---

# Phase 22c-09: Cross-user isolation + manual smoke gate Summary

**Phase 22c (oauth-google) closed: real OAuth identity replaces ANONYMOUS_USER_ID, cross-user isolation proven, both Google and GitHub flows verified end-to-end in browser by the human operator.**

## Performance

- **Duration:** ~6h elapsed (active work; spans pause-resume cycle for machine restart)
- **Started:** 2026-04-19 (Task 1 commit 323312c)
- **Completed:** 2026-04-28 (smoke PASS reported by user; close-out commits)
- **Tasks:** 4 (T1 automated test, T2 checklist, T3 manual gate, T4 close-out)
- **Files modified:** 10 (3 created, 7 modified) + 5 commits worth of plan-gap fixes

## Accomplishments

- **Cross-user isolation proven** — test_cross_user_isolation.py passes in 4.60s; two distinct OAuth users (one Google, one GitHub) each see only their own agents at GET /v1/agents.
- **R8 belt-and-suspenders intact** — 8-table COUNT=0 pre-assertion at test start guarantees migration 006 ran via conftest's `alembic upgrade head`, catching any silent skip.
- **All 4 browser smoke scenarios PASS** — Google happy path, GitHub happy path, access_denied, and logout invalidation confirmed by the human operator after the OAuth callback host bug was fixed.
- **3 plan gaps surfaced + fixed inline** — Dockerfile drift (authlib+itsdangerous, httpx) and OAuth callback host (`localhost:8000/dashboard` 404) all caught by the smoke gate exactly as the gate is designed to.

## Task Commits

1. **Task 1: cross-user isolation test + R8 pre-assertion** — `323312c` (test)
2. **Task 2: manual smoke checklist file** — `ecca249` (docs)
3. **Task 3: manual smoke gate (human action)** — PASS reported 2026-04-28; no commit (verification step)
4. **Task 4: STATE + SUMMARY + ROADMAP close-out** — pending (this commit)

### Plan-gap fixes committed during the smoke gate

5. **Dockerfile authlib + itsdangerous** — `4f7d8b0` (fix)
6. **WIP pause for Docker daemon hang** — `c27bddd` (wip)
7. **Dockerfile + pyproject httpx promotion to runtime** — `fdf3924` (fix)
8. **OAuth callback redirects to frontend host** — `f9a7df9` (fix)

## Files Created/Modified

- `api_server/tests/auth/test_cross_user_isolation.py` — Two-user disjoint-agents integration test + 8-table COUNT=0 pre-assertion
- `test/22c-manual-smoke.md` — 6-scenario human smoke checklist (4 OAuth flows + 2 curl-automatable gates)
- `api_server/pyproject.toml` — `httpx>=0.27` promoted from dev to runtime deps
- `tools/Dockerfile.api` — added `authlib`, `itsdangerous`, `httpx` to pip install chain
- `api_server/src/api_server/config.py` — `frontend_base_url` setting (default http://localhost:3000)
- `api_server/src/api_server/routes/auth.py` — `_DASHBOARD_PATH` + `_LOGIN_PATH` constants prefixed with `settings.frontend_base_url` at call site; `_login_redirect_with_error()` now takes settings
- `api_server/tests/auth/test_google_callback.py` — assertion updated to expect `http://localhost:3000/dashboard`
- `api_server/tests/auth/test_github_callback.py` — assertion updated to expect `http://localhost:3000/dashboard`

## Decisions Made

- **Manual smoke is human-action, not human-verify** — auto_advance=true does NOT apply. Waited for explicit user PASS report.
- **3 inline plan-gap fixes stay in 22c-09** — same atomic-phase discipline as `4f7d8b0`. Long-term Dockerfile-reads-pyproject is out of scope.
- **3 UX issues surfaced during smoke (Alex Chen, /#playground, Telegram conditional fields) deferred to 22c.1** — AMD-02 keeps 22c scope to OAuth identity only.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule-1 — Plan gap surfaced by acceptance test] Dockerfile.api drift from pyproject.toml — authlib + itsdangerous missing**
- **Found during:** Task 3 (smoke gate; first rebuild after Phase 22c added authlib + itsdangerous to pyproject.toml)
- **Issue:** `tools/Dockerfile.api` hardcodes its pip install list. Added authlib + itsdangerous to pyproject.toml in Wave 0 but Dockerfile never updated → container crashed at boot with `ModuleNotFoundError: itsdangerous`.
- **Fix:** Added `'authlib>=1.6.11' 'itsdangerous>=2.2.0'` to the Dockerfile pip install chain.
- **Files modified:** tools/Dockerfile.api
- **Verification:** Container booted; `curl http://localhost:8000/healthz` returned `{"ok":true}`.
- **Committed in:** `4f7d8b0`

**2. [Rule-1 — Same gap, second dependency] httpx missing from runtime deps**
- **Found during:** Task 3 second rebuild (after machine reboot for Docker daemon hang)
- **Issue:** authlib's `StarletteOAuth2App` imports `httpx_client` which `import httpx` — but httpx was only declared in `[project.optional-dependencies].dev`. Container booted past `itsdangerous` only to crash with `ModuleNotFoundError: httpx`.
- **Fix:** Promoted `httpx>=0.27` to runtime deps in pyproject.toml; added to Dockerfile pip install chain.
- **Files modified:** api_server/pyproject.toml, tools/Dockerfile.api
- **Verification:** Container booted; `curl -sv http://localhost:8000/v1/auth/google` returned `302` to `accounts.google.com`.
- **Committed in:** `fdf3924`

**3. [Rule-1 — Plan gap, behavior bug] OAuth callback redirected to API host instead of frontend host**
- **Found during:** Task 3 first browser smoke attempt (Scenarios 1+2)
- **Issue:** `RedirectResponse("/dashboard", 302)` uses a relative path. Browser resolves it against the current request origin (`localhost:8000`, the API), landing the user on a 404 instead of `localhost:3000/dashboard`. Same bug affected `_login_redirect_with_error("access_denied")` etc.
- **Fix:** Added `AP_FRONTEND_BASE_URL` setting (default `http://localhost:3000`); refactored `_DASHBOARD_PATH` + `_LOGIN_PATH` constants and prefixed both at every call site; `_login_redirect_with_error()` now takes `settings` first arg. 11 callers updated.
- **Files modified:** api_server/src/api_server/config.py, api_server/src/api_server/routes/auth.py, api_server/tests/auth/test_google_callback.py, api_server/tests/auth/test_github_callback.py
- **Verification:** Browser smoke after rebuild confirmed user lands on `http://localhost:3000/dashboard` with real name + ap_session cookie. Login-error tests still match via substring; dashboard tests updated to absolute URL.
- **Committed in:** `f9a7df9`

---

**Total deviations:** 3 plan-gap fixes (all surfaced by the manual smoke gate exactly as designed)
**Impact on plan:** All 3 are in-scope per the phase-gate doctrine — surfacing > hiding. None expanded the phase scope; UX findings stayed deferred.

## Issues Encountered

- **Docker daemon hung mid-smoke** between commit `4f7d8b0` and the second rebuild → required machine restart → triggered `/gsd-pause-work`. Resumed cleanly via `.planning/HANDOFF.json` after reboot.
- **Multiple stale frontend dev processes** after pause-resume → user requested clean state; `pkill -f "next dev"` + `pkill -f "pnpm dev"` cleaned up; single PID restarted.

## Out-of-Scope Findings (logged for 22c.1)

These surfaced during user-driven smoke but were NOT addressed in 22c per AMD-02:

1. `/playground` page navbar still shows hardcoded "Alex Chen" (pre-existing mock-data leftover)
2. "Launch Playground" CTA links to `/#playground` instead of `/playground` (fragment bug)
3. Step 2.5 defaults to "One-shot smoke"; user wants "Persistent + Telegram" default with conditional Telegram-specific fields per recipe schema
4. Long-term: drive Dockerfile pip install from pyproject.toml (root-cause fix for the drift pattern)

## Phase 22c Exit Status

✅ All 9 plans committed
✅ Cross-user isolation integration test PASS
✅ Manual smoke gate PASS (4 OAuth scenarios + 2 curl-automatable)
✅ R8 3-layer verification intact (SPIKE-B + 22c-06 artifact + 22c-09 pre-assertion)
✅ Real OAuth identity replaces ANONYMOUS_USER_ID system-wide
