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
