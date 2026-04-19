---
phase: 22c-oauth-google
plan: 09
type: execute
wave: 5
depends_on: [22c-06, 22c-07, 22c-08]
files_modified:
  - api_server/tests/auth/test_cross_user_isolation.py
  - test/22c-manual-smoke.md
  - .planning/STATE.md
autonomous: false
requirements: [SPEC-AC-cross-user-isolation, SPEC-AC-manual-smoke-google, SPEC-AC-manual-smoke-github, D-22c-TEST-02, R8-belt-and-suspenders]
must_haves:
  truths:
    - "Integration test test_cross_user_isolation.py proves 2 separate OAuth users each see only their own agents via GET /v1/agents"
    - "Task 1 includes a PRE-ASSERTION that all 8 data tables are empty at test start — proves migration 006 ran during conftest init (belt-and-suspenders per BLOCKER-4 Option C)"
    - "Manual smoke checklist exists at test/22c-manual-smoke.md covering the 2 browser flows (Google + GitHub) + 4 edge cases (access_denied, state_mismatch, logout, dashboard gate)"
    - "STATE.md updated to reflect Phase 22c completion with resume anchor pointing at the next phase"
    - "Manual smoke gate (D-22c-TEST-02) PASS confirmed by the human operator before this plan closes"
  artifacts:
    - path: "api_server/tests/auth/test_cross_user_isolation.py"
      provides: "2-user cross-isolation integration test + pre-assertion 8-table empty gate"
    - path: "test/22c-manual-smoke.md"
      provides: "Human smoke checklist for the Phase 22c exit gate"
    - path: ".planning/STATE.md"
      provides: "Updated project state with 22c complete + resume anchor"
  key_links:
    - from: "test_cross_user_isolation"
      to: "Zero cross-user leakage at /v1/agents"
      via: "authenticated_cookie fixture + second_authenticated_cookie"
      pattern: "seed 2 distinct users + assert disjoint agent lists"
    - from: "Task 1 pre-assertion"
      to: "R8 belt-and-suspenders (migration 006 ran)"
      via: "SELECT COUNT(*) from each of 8 data tables at test start before any seed"
      pattern: "assert count == 0.*alembic migration 006"
    - from: "22c-manual-smoke.md"
      to: "SPEC acceptance criteria"
      via: "Human clicks through 6 scenarios; all must PASS"
---

<objective>
Close Phase 22c with two gates:

1. **Automated — cross-user isolation integration test + R8 belt-and-suspenders pre-assertion.** Two distinct OAuth users seed via testcontainers PG. Each issues `GET /v1/agents`. Each must see ONLY their own agents (zero cross-user leakage). This is the SPEC acceptance criterion "Integration test: 2 different Google users sign in -> each GET /v1/agents returns ONLY their own agents". Any failure here indicates the require_user migration in plan 22c-06 missed a code path. **Additionally, per BLOCKER-4 Option C, the test opens with a pre-assertion that all 8 data tables are empty at session start — proving migration 006 ran via conftest's `alembic upgrade head` AND caught anything that silently skipped it.**

2. **Manual — human smoke checklist for the Phase 22c exit gate (D-22c-TEST-02).** A checklist markdown in `test/22c-manual-smoke.md` lists 6 scenarios the human operator steps through in a browser. Phase 22c does NOT close until the human signs off with a "PASS" summary for all 6. This plan is `autonomous: false` — it has a `checkpoint:human-verify` task.

After both gates PASS, update `.planning/STATE.md` to reflect Phase 22c completion + the resume anchor for the next planned phase.

Purpose: Phase-exit gate. CLAUDE.md golden rule 3 ("Ship when the stack works locally end-to-end") is operationalized here.
Output: 1 integration test (with R8 pre-assertion) + 1 human smoke checklist + STATE.md update.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22c-oauth-google/22c-SPEC.md
@.planning/phases/22c-oauth-google/22c-CONTEXT.md
@.planning/phases/22c-oauth-google/22c-VALIDATION.md
@api_server/tests/auth/test_google_callback.py
@api_server/tests/auth/test_logout.py
@api_server/tests/routes/test_users_me.py
@api_server/tests/conftest.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Cross-user isolation integration test + R8 belt-and-suspenders pre-assertion</name>
  <files>api_server/tests/auth/test_cross_user_isolation.py</files>
  <read_first>
    - api_server/tests/conftest.py (authenticated_cookie + second_authenticated_cookie fixtures from plan 22c-05)
    - api_server/tests/test_idempotency.py (pattern for seeding distinct users in one test)
    - api_server/src/api_server/routes/agents.py (post-22c-06 version — uses require_user; GET /v1/agents returns `{"agents": [...]}`)
    - api_server/src/api_server/services/run_store.py (post-22c-06: no more ANONYMOUS_USER_ID re-export; `list_agents(conn, user_id)` is the seam to grep)
    - .planning/phases/22c-oauth-google/22c-VALIDATION.md §Cross-user isolation row (line 68)
    - .planning/phases/22c-oauth-google/22c-SPEC.md §Acceptance Criteria (bullet 11)
    - .planning/phases/22c-oauth-google/spike-evidence/spike-b-truncate-cascade.md (Wave-0 R8 behavioral regression — this test adds a SECOND independent check per BLOCKER-4 Option C)
  </read_first>
  <action>
Create `api_server/tests/auth/test_cross_user_isolation.py`. The test MUST:

**STEP 0 (R8 BELT-AND-SUSPENDERS — BLOCKER-4 Option C):** Before seeding anything, assert that all 8 data tables are empty at the start of the test. This proves that `alembic upgrade head` ran during conftest init AND applied migration 006 correctly. If any table has rows, either (a) migration 006 silently failed / no-op'd, or (b) another test's TRUNCATE fixture didn't run / leaked state.

**STEP 1-6 (Cross-user isolation — SPEC AC-11):** Seed 2 users + 2 sessions + 2 agents, then assert each user sees only their own agents + anonymous → 401.

```python
"""Cross-user isolation + R8 belt-and-suspenders — SPEC acceptance criterion 11.

TWO independent concerns in one test:

(A) R8 belt-and-suspenders (BLOCKER-4 Option C from the revision checker):
    Before ANY seed, assert all 8 data tables are empty. This proves the
    session-scoped migrated_pg fixture ran `alembic upgrade head` and landed
    at revision 006_purge_anonymous with all tables cleared. Catches silent
    failures in migration 006's TRUNCATE statement. SPIKE-B (plan 22c-01) is
    the PRIMARY regression; this is the secondary independent check.

(B) Cross-user isolation (SPEC AC-11):
    Two authenticated users; GET /v1/agents must return only each user's own
    agents. Any leak here indicates require_user (plan 22c-06) missed a code
    path.
"""
from __future__ import annotations

import uuid

import asyncpg
import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_two_users_see_only_their_own_agents(
    async_client, migrated_pg
):
    dsn = migrated_pg.get_connection_url(driver="asyncpg")
    conn = await asyncpg.connect(dsn)
    try:
        # ==============================================================
        # STEP 0 — R8 belt-and-suspenders (BLOCKER-4 Option C)
        # ==============================================================
        # Pre-assertion: all 8 data tables empty at test start.
        # If this fails, migration 006 did NOT run (or silently no-op'd),
        # OR a sibling test leaked state. Both are bugs worth catching here.
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert version == "006_purge_anonymous", (
            f"expected HEAD = 006_purge_anonymous (proving migration 006 ran); "
            f"got {version!r}"
        )
        for tbl in (
            "users", "sessions", "agent_instances", "agent_containers",
            "runs", "agent_events", "idempotency_keys", "rate_limit_counters",
        ):
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            assert count == 0, (
                f"pre-seed assertion failed: {tbl} COUNT={count}. "
                f"Either alembic migration 006 did not clear it, or a "
                f"sibling test leaked state through the conftest fixture."
            )

        # ==============================================================
        # STEP 1 — seed two users
        # ==============================================================
        user_a_id = uuid.uuid4()
        user_b_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users (id, display_name, provider, sub, email) VALUES "
            "($1, 'alice', 'google', 'google-alice-sub', 'alice@example.com'),"
            "($2, 'bob',   'google', 'google-bob-sub',   'bob@example.com')",
            user_a_id, user_b_id,
        )

        # ==============================================================
        # STEP 2 — seed two sessions
        # ==============================================================
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        exp = now + timedelta(days=30)
        session_a_id = await conn.fetchval(
            "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
            "VALUES ($1, $2, $3, $2) RETURNING id",
            user_a_id, now, exp,
        )
        session_b_id = await conn.fetchval(
            "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
            "VALUES ($1, $2, $3, $2) RETURNING id",
            user_b_id, now, exp,
        )

        # ==============================================================
        # STEP 3 — seed one agent per user
        # ==============================================================
        agent_a_id = uuid.uuid4()
        agent_b_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model, display_name) "
            "VALUES ($1, $2, 'hermes', 'claude-haiku-4.5', 'alice-agent'),"
            "       ($3, $4, 'hermes', 'claude-haiku-4.5', 'bob-agent')",
            agent_a_id, user_a_id, agent_b_id, user_b_id,
        )
    finally:
        await conn.close()

    # ==============================================================
    # STEP 4 — user A view
    # ==============================================================
    r_a = await async_client.get(
        "/v1/agents",
        headers={"Cookie": f"ap_session={session_a_id}"},
    )
    assert r_a.status_code == 200, r_a.text
    ids_a = {a["id"] for a in r_a.json()["agents"]}
    assert str(agent_a_id) in ids_a, ids_a
    assert str(agent_b_id) not in ids_a, f"leak! bob's agent in alice's view: {ids_a}"

    # ==============================================================
    # STEP 5 — user B view
    # ==============================================================
    r_b = await async_client.get(
        "/v1/agents",
        headers={"Cookie": f"ap_session={session_b_id}"},
    )
    assert r_b.status_code == 200, r_b.text
    ids_b = {a["id"] for a in r_b.json()["agents"]}
    assert str(agent_b_id) in ids_b, ids_b
    assert str(agent_a_id) not in ids_b, f"leak! alice's agent in bob's view: {ids_b}"

    # ==============================================================
    # STEP 6 — anonymous view
    # ==============================================================
    r_anon = await async_client.get("/v1/agents")
    assert r_anon.status_code == 401, r_anon.text
```

Notes for the executor:
- The exact `agent_instances` column set may need adjustment — read `alembic/versions/001_baseline.py` or `002_agent_name_personality.py` for the current NOT-NULL constraints. Fill in any missing required columns with realistic placeholder values.
- If `services/run_store.py::list_agents(conn, user_id)` filters on any field besides `user_id` (e.g., soft-delete flag), the test may need to set those fields too. Grep `list_agents` in the services directory to confirm the query shape before running.
- The test uses the real FastAPI app with the full middleware stack (as wired by plan 22c-05). `async_client` fixture provides the httpx AsyncClient against the app.
- If Step 0 fails because the conftest TRUNCATE fixture ran BEFORE this test and cleared state from a sibling test, that's actually fine — COUNT=0 holds either via migration 006 OR via the TRUNCATE fixture. Both are valid evidence the plumbing works.

Commit Task 1:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add api_server/tests/auth/test_cross_user_isolation.py
git commit -m "test(22c-09): cross-user isolation + R8 belt-and-suspenders pre-assertion"
```
  </action>
  <verify>
<automated>cd api_server && pytest tests/auth/test_cross_user_isolation.py -x -v -m api_integration</automated>
  </verify>
  <acceptance_criteria>
    - `api_server/tests/auth/test_cross_user_isolation.py` exists
    - `pytest tests/auth/test_cross_user_isolation.py -m api_integration` exits 0
    - Test contains Step 0 pre-assertion: `alembic_version == '006_purge_anonymous'` + all 8 data tables COUNT=0 at start (R8 belt-and-suspenders)
    - Test seeds 2 users + 2 sessions + 2 agents; asserts 3 behaviors (user A view, user B view, anonymous → 401)
    - Commit on main: `test(22c-09): cross-user isolation + R8 belt-and-suspenders pre-assertion`
  </acceptance_criteria>
  <done>Automated cross-user isolation proven. No leakage at /v1/agents. R8 has 3-layer coverage: SPIKE-B (plan 22c-01) + artifact check (22c-06 Task 1) + pre-assertion here.</done>
</task>

<task type="auto">
  <name>Task 2: Write test/22c-manual-smoke.md (human smoke checklist)</name>
  <files>test/22c-manual-smoke.md</files>
  <read_first>
    - test/ directory (check existing smoke-test patterns — `ls test/` before writing; match naming convention of test/sc03-gate-c.md if present)
    - .planning/phases/22c-oauth-google/22c-SPEC.md §Acceptance Criteria (all 12 items; most are already automated; 2 are manual-only)
    - .planning/phases/22c-oauth-google/22c-VALIDATION.md §Manual-Only Verifications table (lines 93-100)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-TEST-02 (one manual smoke per release)
  </read_first>
  <action>
Create `test/22c-manual-smoke.md`. The file is a per-release checklist the operator steps through locally, pasting "PASS" or "FAIL + notes" next to each scenario. Not a CI-runnable script — a human protocol.

Contents:

```markdown
# Phase 22c Manual Smoke — OAuth end-to-end

**Gate:** D-22c-TEST-02 (one manual smoke per release).
**Prerequisite:** local stack running + `AP_ENV=dev` + `deploy/.env.prod` loaded with real Google + GitHub OAuth credentials (test-users mode).
**Run frequency:** once per tagged release; not a per-commit gate.

## Setup

```bash
cd /Users/fcavalcanti/dev/agent-playground

# Ensure DB is at HEAD (should be 006_purge_anonymous)
docker compose --env-file deploy/.env.prod -f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml up -d

# Verify
curl -s http://localhost:8000/healthz   # -> {"ok":true}
psql "$AP_DATABASE_URL" -tAc "SELECT version_num FROM alembic_version"  # -> 006_purge_anonymous

# Frontend dev
cd frontend && pnpm dev   # -> http://localhost:3000
```

## Checklist

### 1. Google happy path  `[ ] PASS / [ ] FAIL`

1. Browse to http://localhost:3000/login
2. Click "Continue with Google"
3. Consent on Google's consent screen (test-user account)
4. Observe the browser land on http://localhost:3000/dashboard
5. Open the navbar avatar dropdown — display name must match your Google profile's name (NOT "Alex Chen")
6. Inspect browser cookies — `ap_session` cookie present with Max-Age near 2592000

Notes: _____

### 2. GitHub happy path  `[ ] PASS / [ ] FAIL`

1. Log out (navbar -> Log out — should return to /login)
2. Click "Continue with GitHub"
3. Authorize on GitHub's consent screen
4. Observe the browser land on http://localhost:3000/dashboard
5. Display name must match your GitHub name or login
6. If your GitHub primary email is private: verify the backend still resolved it via /user/emails fallback (check `psql "$AP_DATABASE_URL" -tAc "SELECT email FROM users WHERE provider='github' LIMIT 1"`)

Notes: _____

### 3. Access denied  `[ ] PASS / [ ] FAIL`

1. Log out. At http://localhost:3000/login click "Continue with Google"
2. On Google's consent screen, click Cancel (or similar "no")
3. Observe the browser land on http://localhost:3000/login?error=access_denied
4. A toast appears: "Sign-in cancelled"

Notes: _____

### 4. Logout invalidation  `[ ] PASS / [ ] FAIL`

1. Sign in via either provider
2. In browser DevTools -> Application -> Cookies, copy the `ap_session` cookie value
3. Click Log out. Observe return to /login
4. With a curl (manual replay of the copied cookie):
   ```bash
   curl -i --cookie "ap_session=<copied value>" http://localhost:8000/v1/users/me
   ```
   Expected: `HTTP/1.1 401` with Stripe-envelope body `{"error":{"code":"unauthorized",...}}`

Notes: _____

### 5. Dashboard gate  `[ ] PASS / [ ] FAIL`

1. In an incognito window (no cookies), visit http://localhost:3000/dashboard
2. Browser should arrive at http://localhost:3000/login (NOT flashing the dashboard shell first)
3. Also verify the 307 from curl:
   ```bash
   curl -sI http://localhost:3000/dashboard | grep -E "^(HTTP|location)"
   # -> HTTP/1.1 307 Temporary Redirect
   # -> location: /login
   ```

Notes: _____

### 6. Dead-route redirects  `[ ] PASS / [ ] FAIL`

Both of these should redirect:
```bash
curl -sI http://localhost:3000/signup          | grep -E "^(HTTP|location)"
curl -sI http://localhost:3000/forgot-password | grep -E "^(HTTP|location)"
```
Both return HTTP 307 with `location: /login`.

Notes: _____

## Exit gate

If all 6 checkboxes are `[x] PASS`, Phase 22c is complete.

If any checkbox is `[x] FAIL`, file a follow-up task documenting the failure + regression; do not tag a release until remediated.

**Operator:** ________________   **Date:** ________________
```

Commit Task 2:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add test/22c-manual-smoke.md
git commit -m "docs(22c-09): manual smoke checklist for Phase 22c exit gate"
```
  </action>
  <verify>
<automated>test -f test/22c-manual-smoke.md && grep -q "Google happy path" test/22c-manual-smoke.md && grep -q "GitHub happy path" test/22c-manual-smoke.md && grep -q "Dashboard gate" test/22c-manual-smoke.md</automated>
  </verify>
  <acceptance_criteria>
    - `test/22c-manual-smoke.md` exists
    - File contains 6 numbered scenarios (Google, GitHub, Access denied, Logout, Dashboard gate, Dead-route redirects)
    - File contains a "Setup" block with compose + psql + pnpm dev commands
    - File contains an "Exit gate" paragraph
    - Commit on main: `docs(22c-09): manual smoke checklist for Phase 22c exit gate`
  </acceptance_criteria>
  <done>Human smoke checklist ready for the next checkpoint task.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3 (checkpoint): Human operator runs the 22c manual smoke</name>
  <what-built>
    All of Phase 22c is now on disk:
    - Migrations 005 + 006 applied
    - 5 auth routes + /v1/users/me + logout
    - SessionMiddleware + require_user + ANONYMOUS_USER_ID purged from 4 route files + 2 middlewares + run_store re-export
    - 7+2 test files migrated from ANONYMOUS_USER_ID to TEST_USER_ID local seed
    - Frontend login rewrite + dashboard useUser + navbar logout button + proxy.ts gate + /signup + /forgot-password redirects
    - Automated cross-user isolation test (Task 1 of this plan) green with R8 belt-and-suspenders pre-assertion
  </what-built>
  <how-to-verify>
    1. Open `test/22c-manual-smoke.md` in the repo.
    2. Follow the Setup block to bring the local stack up.
    3. Step through all 6 scenarios in the Checklist section, writing PASS/FAIL + notes next to each.
    4. Once complete, paste the checklist results (the 6 PASS/FAIL marks + operator name + date) in the resume-signal response.

    If any scenario FAILS:
    - Do NOT proceed to Task 4 (STATE.md update).
    - Return `## BLOCKER: manual smoke failed scenario <N>` + the failure notes to the orchestrator.
    - Orchestrator will route to `/gsd-plan-phase 22c-oauth-google --gaps` with the failure as input.

    If all 6 scenarios PASS, sign off with "ALL PASS" and Task 4 proceeds.
  </how-to-verify>
  <resume-signal>Type "ALL PASS" to proceed to STATE.md update; or describe failures for gap-closure planning.</resume-signal>
</task>

<task type="auto">
  <name>Task 4: Update STATE.md with Phase 22c completion + next-phase resume anchor</name>
  <files>.planning/STATE.md</files>
  <read_first>
    - .planning/STATE.md (whole file — follow the existing resume-anchor format used for 22b completion at lines 32-62)
    - .planning/ROADMAP.md (lines for Phase 21 SSE Streaming Upgrade + Phase 22 series — what is the next phase after 22c? Likely 22c.1 GitHub-only items or Phase 21 SSE; confirm with ROADMAP)
    - .planning/phases/22c-oauth-google/22c-01-SUMMARY.md through 22c-08-SUMMARY.md (all SUMMARYs from the earlier plans — each plan's SUMMARY.md is authoritative for what landed)
    - .planning/audit/ACTION-LIST.md (line 108 is the OAuth anchor — now resolved; confirm the next-most-pressing unblocked item)
  </read_first>
  <action>
Update `.planning/STATE.md` to reflect Phase 22c completion. Preserve every section below the current "Current Position" block that is still relevant.

At the TOP of the file (after the YAML frontmatter block), update:

1. **`status:` field** in the YAML frontmatter: set to `"Phase 22c complete — OAuth (Google + GitHub) live; ANONYMOUS_USER_ID purged"`.
2. **`stopped_at:` field**: set to today's date + brief note.
3. **`last_updated:`**: bump to the current ISO timestamp.
4. **`progress.completed_phases`**: increment by 1 if applicable.
5. **`progress.completed_plans`**: increment by the 9 plans of Phase 22c (01..09).

In the body, REPLACE the "Current Position" section (currently shows "Phase 22c (oauth-google) — SPEC'd, ready for /gsd-discuss-phase") with a new resume anchor:

```markdown
## Current Position

**Phase 22c (oauth-google) COMPLETE** at commit `<latest>` — OAuth (Google + GitHub) live; ANONYMOUS_USER_ID constant deleted; cross-user isolation proven; manual smoke gate PASS per `test/22c-manual-smoke.md` on <date>.

### Stack of completed work this session

| Phase / Task | Status | What landed |
|---|---|---|
| Phase 22c-01 (Wave 0 spikes) | COMPLETE | respx × authlib + 8-table TRUNCATE CASCADE regression both green |
| Phase 22c-02 (migration 005) | COMPLETE | sessions table + users.{sub,avatar_url,last_login_at} + UNIQUE(provider,sub) partial index |
| Phase 22c-03 (config + oauth.py) | COMPLETE | authlib registry + 7 Pydantic fields + AP_OAUTH_STATE_SECRET |
| Phase 22c-04 (SessionMiddleware) | COMPLETE | request.state.user_id resolution + 60s last_seen throttle |
| Phase 22c-05 (auth routes) | COMPLETE | 5 OAuth routes + /v1/users/me + logout + main.py wiring |
| Phase 22c-06 (purge + cleanup) | COMPLETE | migration 006 + ANONYMOUS_USER_ID deleted from constants + run_store + 4 routes + 9 tests |
| Phase 22c-07 (frontend login+dashboard) | COMPLETE | real OAuth buttons + useUser hook + navbar logout |
| Phase 22c-08 (proxy.ts + redirects) | COMPLETE | Next 16 edge gate + /signup + /forgot-password -> /login |
| Phase 22c-09 (close-out) | COMPLETE | cross-user isolation test + R8 belt-and-suspenders + manual smoke gate PASS |

### 📍 RESUME ANCHOR — READ AFTER /clear

**The next command is:**
```
/gsd-<next>-phase <next-phase>
```

(planner: look at `.planning/audit/ACTION-LIST.md` post-OAuth-unblock and insert the actual next phase name + command here)

**Read on resume (after /clear):**

1. `memory/MEMORY.md`
2. `.planning/audit/ACTION-LIST.md` — the dashboard sub-pages are now unblocked
3. `.planning/phases/22c-oauth-google/22c-09-SUMMARY.md`
4. This file (STATE.md)
```

Preserve the "Live infra state" + "Local dev stack restart" blocks below, updating only the agent count ("59 agents in agent_instances" -> "0 agents (migration 006 purged all dev mock data)").

Preserve the "Open backlog" block, moving 22c.1 (GitHub OAuth) off the list since it landed in 22c via AMD-01.

Commit:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add .planning/STATE.md
git commit -m "docs(22c): Phase 22c complete — STATE.md resume anchor updated"
```
  </action>
  <verify>
<automated>grep -q "Phase 22c (oauth-google) COMPLETE" .planning/STATE.md && grep -q "AMD-01" .planning/STATE.md || grep -q "ANONYMOUS_USER_ID" .planning/STATE.md</automated>
  </verify>
  <acceptance_criteria>
    - STATE.md frontmatter `status` field mentions Phase 22c complete
    - Current Position section rewritten to reflect Phase 22c closure
    - 9-plan stack table lands in STATE.md
    - Resume anchor updated for the next phase
    - 59-agents note adjusted to reflect the post-006 reality (0 agents)
    - 22c.1 (GitHub OAuth) removed from Open backlog (it landed in-phase per AMD-01)
    - Commit on main: `docs(22c): Phase 22c complete — STATE.md resume anchor updated`
  </acceptance_criteria>
  <done>Phase 22c formally closed. STATE.md is ready for the next /clear + resume cycle.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Cross-user test -> PG | Direct asyncpg inserts bypass the OAuth flow — this is INTENTIONAL for the test. Production code paths are exercised by the routes-layer integration test suite (plan 22c-05). |
| Human operator -> manual smoke | A human drives the browser flow using real Google + GitHub credentials. Real tokens touch real providers. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22c-29 | Elevation of privilege | Test-only seed inserts production credentials | accept | Test fixture uses testcontainers PG — fully ephemeral; no prod DB touched. Seed rows use placeholder emails (alice@example.com, bob@example.com). |
| T-22c-30 | Information disclosure | Manual smoke checklist logs OAuth client secrets | mitigate | Checklist uses only the authorize URL + cookies; NEVER prompts the operator to copy/paste a client_secret. Operator uses the values already in `deploy/.env.prod` (gitignored). |
</threat_model>

<verification>
```bash
cd api_server && pytest tests/auth/test_cross_user_isolation.py -m api_integration
# Human opens test/22c-manual-smoke.md and confirms ALL 6 scenarios PASS
```
</verification>

<success_criteria>
- `test_cross_user_isolation` green with Step 0 pre-assertion (R8 belt-and-suspenders)
- `test/22c-manual-smoke.md` committed
- Human operator marks ALL PASS on the manual smoke (checkpoint task)
- `.planning/STATE.md` updated with Phase 22c closure + resume anchor for the next phase
- 2-3 commits on main depending on how Tasks 1/2/4 are squashed
</success_criteria>

<output>
After completion, create `.planning/phases/22c-oauth-google/22c-09-SUMMARY.md` with:
- Cross-user isolation test result
- R8 pre-assertion result (alembic_version + 8-table COUNT=0)
- Manual smoke checklist summary (6 PASS marks)
- Final commit hashes for Phase 22c (grep `git log` for the phase)
- Next-phase pointer (based on ROADMAP + ACTION-LIST.md)
- Any regressions or follow-ups discovered during manual smoke that should be tracked
</output>
</output>
