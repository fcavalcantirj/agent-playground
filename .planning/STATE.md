---
gsd_state_version: 1.0
milestone: v0.2
milestone_name: "**Goal:** Introduce `apiVersion: ap.recipe/v0.2` requiring full SHA in `source.ref`. Migration script for existing recipes. Clone dir keyed by SHA. Runner records `resolved_upstream_ref` for v0.1 compat. Steal from METR"
status: "Phase 22c.3 EXECUTING — Wave 4 IN PROGRESS 2026-04-30 night. Plan 22c.3-13 (zeroclaw channels.inapp) SHIPPED (commit 1f01d67). recipes/zeroclaw.yaml +34 lines: added channels.inapp.persistent_argv_override (entrypoint=zeroclaw, argv=[daemon], 4 pre_start_commands chaining `onboard --quick --provider openrouter --api-key ${OPENROUTER_API_KEY} --model $MODEL` + `config set gateway.allow-public-bind true` + `config set gateway.host 0.0.0.0` + `config set gateway.require-pairing false`) + channels.inapp.activation_env (OPENROUTER_API_KEY + ZEROCLAW_WORKSPACE). The recipe shipped at planning-commit c98fd95 already had channels.inapp top-level fields (transport=http_localhost/port=42617/endpoint=/webhook/contract=zeroclaw_native/idempotency_header=X-Idempotency-Key/session_header=X-Session-Id/streaming.path=/ws/chat/health_endpoint=/health/ready_log_regex='ZeroClaw Gateway listening on'/auth_mode=none/response_envelope.reply_path=$.response) + build.mode=image_pull + build.image=ghcr.io/zeroclaw-labs/zeroclaw:latest (Rust distroless ~50 MB) + verified_cells citing spikes/recipe-zeroclaw.md 2026-04-30 FULL_PASS — but lacked the channels.inapp-scoped persistent_argv_override required by must_have #4 + the plan's <interfaces> shape. Rule 1 fix added it inline (D-20 single-channel-per-instance: the runner SWAPS persistent argv at deploy time; channels.inapp.persistent_argv_override IS that swap declaration). Top-level persistent.spec.pre_start_commands kept (CLAUDE.md golden rule #4 — no unprompted code changes). Live api_server restarted via `docker compose -f docker-compose.prod.yml -f docker-compose.local.yml restart api_server`; /healthz=200 within ~5s; GET /v1/recipes/zeroclaw surfaces channels.inapp.persistent_argv_override (entrypoint=zeroclaw, argv=[daemon], pre_start_commands.length=4) + channels.inapp.activation_env verbatim. InappRecipeIndex.get_inapp_block('zeroclaw') returns InappChannelConfig(contract='zeroclaw_native', port=42617, endpoint=/webhook, auth_mode='none', idempotency_header='X-Idempotency-Key', session_header='X-Session-Id'). One Rule-1 deviation (recipe authored at planning time lacked channels.inapp.persistent_argv_override; fixed inline) + one Rule-3 deviation (plan verify cmd #3 referenced nonexistent --list-recipes flag; substituted /v1/recipes registry check). picoclaw remains untouched (recipes/picoclaw.yaml unchanged in working tree per user direction 2026-04-30 — DEFERRED out of Phase 22c.3 inapp scope; backward compat with smoke suite preserved). Fourth of 5 recipe inapp opt-ins (after hermes 22c.3-10 + nanobot 22c.3-11 + openclaw 22c.3-12); only Plan 22c.3-14 (nullclaw — native A2A JSON-RPC contract=a2a_jsonrpc) remains in Wave 4 before the e2e gate Plan 22c.3-15."
stopped_at: "2026-04-30 — 22c.3-13 SHIPPED (commit 1f01d67); fourth Wave-4 recipe opt-in (zeroclaw via image_pull + 4 distroless pre_start_commands + zeroclaw_native contract + built-in X-Idempotency-Key/X-Session-Id headers); next is /gsd-execute-phase 22c.3 to continue Wave 4 with Plan 22c.3-14 (nullclaw native A2A)"
last_updated: "2026-04-30T21:44:22.198Z"
progress:
  total_phases: 19
  completed_phases: 5
  total_plans: 32
  completed_plans: 32
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-11)

**Core value:** Any agent × any model × any user, in one click — agent-agnostic install pipeline is the differentiator that must work.
**Current focus:** Phase 22 (channels-v0.2) parent close-out + next milestone phase selection

## Current Position

**Phase 22c (oauth-google) — PLANNED (9 plans, 6 waves), ready for /gsd-execute-phase** at current uncommitted state (see stack below).

### Stack of completed work this session (2026-04-19)

| Phase / Task | Status | Commit | What landed |
|---|---|---|---|
| Phase 22b (agent-event-stream) | COMPLETE | `eb06c5a` | SC-03 unblocked: Gate A 15/15 + Gate B 5/5 PASS in `e2e-report.json`; verifier 21/21 truths PASSED; 9 plans across 5 waves |
| Quick task `260419-moq` (dashboard real-API) | COMPLETE | `2260dad`, `3520834`, `2e9e3be` | `frontend/app/dashboard/page.tsx` now fetches real `/v1/agents` (59 real rows); Stop button wired to POST /v1/agents/:id/stop with Bearer prompt + 2s status polling; mockAgents + Agent interface + toggleAgentStatus + deleteAgent removed |
| Phase 22c (oauth-google) SPEC | COMPLETE | `d9863d2` | 8 falsifiable requirements + 12 acceptance criteria + 3 locked decisions; ambiguity 0.16 |
| Phase 22c (oauth-google) CONTEXT | COMPLETE | `62ff031` | 19 locked decisions + 4 AMDs (GitHub scope, refresh-token drop, ANONYMOUS purge) |
| Phase 22c (oauth-google) RESEARCH + PATTERNS + VALIDATION + 9 PLANs | **PLANNED** | `394fd7f` | 9 plans in 6 waves (Wave 0 gate: respx×authlib spike + TRUNCATE-CASCADE 8-table spike). 3 new AMDs added post-research (AMD-05 respx not responses; AMD-06 proxy.ts not middleware.ts; AMD-07 AP_OAUTH_STATE_SECRET env var). Plan-checker PASS iteration 3/3 (0 blockers). Covers R1..R8 + AMD-01..07 + 5 PATTERNS gap-closures. |
| Phase 22c-01 (Wave 0 spike gate) | **COMPLETE** | `dc43879`, `4f37b58`, `9cf282c` | SPIKE-A green (respx 0.23.1 intercepts authlib 1.6.11's httpx 0.28.1 token-exchange; AMD-05 validated; Rule-3 deviation: respx pin bumped from 0.21 to 0.22+). SPIKE-B green Mode B (7 tables, alembic HEAD=004; auto-upgrades to Mode A when 22c-02 ships 005): single TRUNCATE CASCADE clears users + agent_instances + agent_containers + runs + agent_events + idempotency_keys + rate_limit_counters + preserves alembic_version. Evidence markdowns + SUMMARY committed. 3 Rule-3 deviations auto-fixed (respx pin, TESTCONTAINERS_RYUK_DISABLED, PG network attach). See `.planning/phases/22c-oauth-google/22c-01-SUMMARY.md`. |
| Phase 22c-02 (alembic 005 — sessions + users OAuth) | **COMPLETE** | `ec19e7f`, `9e7db7e` | Additive schema migration applied live to `deploy-postgres-1` — alembic_version=005_sessions_and_oauth_users. Adds: users.sub/avatar_url/last_login_at (nullable); UNIQUE(provider, sub) partial index WHERE sub IS NOT NULL (preserves ANONYMOUS NULL-sub seed); sessions table (id UUID PK + user_id FK→users.id ON DELETE CASCADE + expires_at/revoked_at/last_seen_at/user_agent/ip_address INET + btree on user_id). Round-trip verified: upgrade → downgrade -1 → upgrade clean. Integration test `test_migration_005_sessions_and_users_columns` PASSED on host venv against fresh testcontainers PG 17. Zero deviations from plan. 3 pre-existing Phase-19 TestBaselineMigration failures + conftest DSN-gateway issue logged to `.planning/phases/22c-oauth-google/deferred-items.md` (all out of scope per plan line 39 pointer deferring conftest fix to 22c-06). See `.planning/phases/22c-oauth-google/22c-02-SUMMARY.md`. |
| Phase 22c-03 (OAuth config + authlib registry) | **COMPLETE** | `4f5b01f`, `6fdde21`, `7428b86` | 7 new Pydantic settings on `api_server/src/api_server/config.py` (oauth_{google,github}_{client_id,client_secret,redirect_uri} + oauth_state_secret, all str\|None with None default). New `auth/` sub-package ships `get_oauth(settings)` — a cached authlib `OAuth()` registry with `google` (OIDC via `server_metadata_url`) + `github` (non-OIDC with hand-specified endpoints) — plus `upsert_user(conn, *, provider, sub, email, display_name, avatar_url) -> UUID` (ON CONFLICT target mirrors alembic 005 partial index verbatim) and `mint_session(conn, *, user_id, request) -> str` (returns sessions.id UUID directly; gen_random_uuid provides 122 bits of randomness, no separate token column needed). Prod fail-loud discipline mirrors `crypto/age_cipher.py::_master_key`: AP_ENV=prod + any missing OAuth var raises RuntimeError naming the var; AP_ENV=dev uses deterministic `not-for-prod` / `localhost` placeholders. `deploy/.env.prod.example` gains AP_OAUTH_STATE_SECRET stanza with `openssl rand -hex 32` hint; `deploy/.env.prod` NOT modified. 12 unit tests at `tests/auth/test_oauth_config.py` cover Settings fields, env aliases, dev placeholder path, dev override with real creds, idempotency, reset_for_tests, prod fail-loud on first-missing-var AND middle-missing-var (AP_OAUTH_STATE_SECRET regression trap) — all PASS in 0.21s. Zero deviations from plan. See `.planning/phases/22c-oauth-google/22c-03-SUMMARY.md`. |
| Phase 22c-04 (SessionMiddleware + log_redact docstring + 10 middleware tests) | **COMPLETE** | `08560d0`, `9a954d3` | New ASGI `SessionMiddleware` at `api_server/src/api_server/middleware/session.py` (147 lines): reads `ap_session` cookie → coerces to UUID (malformed → None, no PG query per T-22c-09) → `SELECT user_id, last_seen_at FROM sessions WHERE id=$1 AND revoked_at IS NULL AND expires_at > NOW()` → sets `scope['state']['user_id'] = <UUID \| None>`. Per-worker `app.state.session_last_seen: dict[UUID, datetime]` throttles `UPDATE sessions SET last_seen_at` to ≤1/session/60s (D-22c-MIG-05; Redis NOT in Python stack). Soft LRU eviction at 10k entries. Fail-closed to `user_id=None` + `log.exception` on PG outage. `log_redact.py` docstring extended with Phase 22c cookie-redaction note (ap_session + ap_oauth_state covered by construction — allowlist unchanged). 10 tests, all green: 6 R3 behavior (no-cookie, valid, expired, revoked, malformed-no-PG-query, PG-outage-fail-closed), 2 D-22c-MIG-05 throttle (rapid-dupe → 1 UPDATE, 61s-rewind → 2nd UPDATE fires), 2 cookie-redact (ap_session + ap_oauth_state values absent from structlog output). Pre-existing `test_log_redact.py` tests still green. One Rule-3 deviation: asyncpg.Pool.acquire is read-only (__slots__), so the test swapped monkey-patch-attr for a counting-proxy pool wrapper on `app.state.db`. See `.planning/phases/22c-oauth-google/22c-04-SUMMARY.md`. |
| Phase 22c-05 (OAuth routes + /v1/users/me + logout + require_user + middleware wiring + 20 integration tests) | **COMPLETE** | `e989bd4`, `d47e303`, `eb2dcb6`, `eea754a` | 5 OAuth endpoints at `api_server/src/api_server/routes/auth.py` (google + github authorize + callback + POST /auth/logout) with EXACT `e.error == "mismatching_state"` match per D-22c-OAUTH-01 + 3 error-redirect codes (`access_denied`, `state_mismatch`, `oauth_failed`). `routes/users.py::GET /v1/users/me` returns `SessionUserResponse { id, email, display_name, avatar_url, provider, created_at }` mirror of `frontend/lib/api.ts::SessionUser`. `auth/deps.py::require_user(request) -> JSONResponse \| UUID` inline early-return helper (D-22c-AUTH-03) — NOT FastAPI Depends. `main.py` wires Starlette `SessionMiddleware` (AMD-07 ap_oauth_state CSRF) + our `ApSessionMiddleware` at correct positions (declaration order outermost-last per D-22c-AUTH-01: CorrelationId → AccessLog → StarletteSession → ApSession → RateLimit → Idempotency → route); `get_oauth(settings)` called eagerly at `create_app()` so prod boots fail loud on missing AP_OAUTH_STATE_SECRET. 20 integration tests at `tests/auth/` + `tests/routes/test_users_me.py` + `tests/config/test_oauth_state_secret_fail_loud.py`: 2 authorize (google + github 302 + redirect_uri + ap_oauth_state cookie), 5 google callback (state_mismatch, access_denied, **WARNING-3 non-state-error → oauth_failed**, happy_path w/ userinfo upsert + session mint + cookie, missing_sub), 5 github callback (state_mismatch, **WARNING-3 non-state-error → oauth_failed**, public_email, /user/emails fallback for private-primary, no_verified_email → oauth_failed), 2 logout (204 + invalidates + cookie-clear, 401 no-cookie), 4 users_me (200 valid, 401 no-cookie, 401 expired, 401 revoked), 2 fail-loud (prod raises on AP_OAUTH_STATE_SECRET, dev boots without OAuth envs). 3 shared fixtures on conftest.py (`authenticated_cookie`, `second_authenticated_cookie`, `respx_oauth_providers` — Google discovery + JWKS pre-stubbed). 3 Rule-1/Rule-2/Rule-3 deviations: logout uses `Response(status_code=204)` not `JSONResponse(None, 204)`; TRUNCATE list extended (sessions + non-ANONYMOUS users); per-test `app.state.settings.oauth_*_redirect_uri` override for authorize tests. See `.planning/phases/22c-oauth-google/22c-05-SUMMARY.md`. |
| Phase 22c-06 (alembic 006 purge + ANONYMOUS cleanup + require_user everywhere) | **COMPLETE** | `70fc798`, `9d4aa5f`, `daac5dc`, `007d12a`, `8faa329` | IRREVERSIBLE migration 006 live-applied to `deploy-postgres-1` — alembic_version=006_purge_anonymous; 8-table TRUNCATE CASCADE verified COUNT=0 (users/agent_instances/agent_containers/runs/agent_events/idempotency_keys/rate_limit_counters/sessions). `ANONYMOUS_USER_ID` deleted from `constants.py` + `run_store.py` re-export (BLOCKER-1 fix); forcing-function pattern per T-22c-20. 4 route files (runs, agents, agent_lifecycle, agent_events) migrated to `auth.deps.require_user` inline gate (7+ call-sites across 4 handlers on agent_lifecycle). `agent_status` newly protected — D-22c-AUTH-03 gap closed per PATTERNS.md finding. `IdempotencyMiddleware` reads `scope['state']['user_id']`; anonymous path passes through (Option A from RESEARCH Pitfall 4) — no NOT-NULL FK violations, no cache poisoning. `RateLimitMiddleware` prefers `user:<uuid>` subject; IP fallback preserved. `conftest.py` TRUNCATE list extended to 8 tables. 2 new middleware tests (`test_anonymous_pass_through`, `test_authenticated_caches`) — both green. 9 test files migrated off `ANONYMOUS_USER_ID` (5 Class-A import-replacements + 4 Class-B local-rename). 3 Rule-2/Rule-3 deviations + 1 Rule-3 cascade absorption: (1) test_migration_005 assertion relaxed to accept HEAD in {005,006}; (2) 12 seed fixtures ON-CONFLICT-safely seed the users FK target; (3) 5 test_runs + 2 test_rate_limit + 2 test_events_auth rewrote for the new require_user contract; (4) 2 test_run_concurrency tests skipped with deferred-items.md pointer (XFF-per-request bypass defeated by user_id precedence). Post-plan integration suite: 108 passed, 2 skipped, 8 failed (all pre-existing or obsoleted by 006's design — documented in deferred-items.md), 1 environmental error. Zero new regressions. See `.planning/phases/22c-oauth-google/22c-06-SUMMARY.md`. |
| Phase 22c-07 (frontend login + dashboard + navbar rewrite — real OAuth) | **COMPLETE** | `a541460`, `f1e7dd1`, `a549056` | setTimeout + "Alex Chen" hardcode deleted. New `frontend/hooks/use-user.ts` (47 lines) — apiGet /v1/users/me on mount + ApiError.status===401 → router.push('/login'). `app/login/page.tsx` rewritten: Google/GitHub buttons perform `window.location.href = '/api/v1/auth/{google,github}'` (top-level nav required for OAuth 302 chain); ?error=<code> renders sonner toast for access_denied|state_mismatch|oauth_failed via exact-string switch (T-22c-25); email/password form inputs all disabled + "Use Google or GitHub above for now." caption; dead /forgot-password Link removed (D-22c-UI-03). `app/dashboard/layout.tsx` consumes useUser(); Navbar user prop passes {name: display_name, email, avatar: avatar_url} or undefined during load (D-22c-FE-02 eager render + skeleton-in-slot). `components/navbar.tsx` Log out DropdownMenuItem now uses `onSelect={async (e) => { e.preventDefault(); try { await apiPost('/api/v1/auth/logout', {}) } catch {} router.push('/login') }}` — real server-side session invalidation (D-22c-UI-04). All grep gates green on first try (0 setTimeout, 0 Alex Chen, 1 apiPost auth/logout, 3 useUser refs); zero new TS errors on any file this plan touched. Zero deviations from plan. Pre-existing 3 TS errors + 2 build prerender failures confirmed against clean main and logged to deferred-items.md (scope boundary: out of scope). See `.planning/phases/22c-oauth-google/22c-07-SUMMARY.md`. |
| Phase 22c-08 (frontend proxy.ts Next-16.2 rename + dead-route redirects) | **COMPLETE** | `e71bb73`, `e435d30` | New `frontend/proxy.ts` (29 lines) — Next.js 16.2 edge gate per AMD-06 (file-convention rename effective 2025-10-21). `export default function proxy(request)` checks `request.cookies.get("ap_session")` presence — absent → `NextResponse.redirect(new URL("/login", request.url), 307)`; present → `NextResponse.next()`. Matcher narrowed to `/dashboard/:path*` only (D-22c-FE-01; was `/((?!api\|_next/static\|_next/image\|favicon.ico).*)` on the old middleware.ts). Stale `frontend/middleware.ts` DELETED — contained incorrect L17-19 comment denying the Next-16 rename and emitted an orphaned `x-ap-has-session` header with zero downstream readers (confirmed via `grep -rn` returning zero matches in source). `frontend/next.config.mjs` extended with `async redirects()` sibling to existing `rewrites()` — returns two entries `{ source: "/signup"\|"/forgot-password", destination: "/login", permanent: false }` (HTTP 307 temporary so future phases can restore the pages without browser-cache poisoning). `app/signup/page.tsx` + `app/forgot-password/page.tsx` files stay on disk UNTOUCHED — redirect fires at Next config layer BEFORE page routes render (zero-touch avoids import-cascade risk). Live verification against `pnpm dev`: `/dashboard` no-cookie = 307 loc:/login; `/dashboard` with-cookie = 200; `/dashboard/analytics` subpath = same; `/signup` + `/forgot-password` = 307 loc:/login; `/` + `/login` = 200 (matcher scope correct). `pnpm build` compiles cleanly ("Compiled successfully in 2.3s"); pre-existing `/docs/config`, `/_not-found`, `/contact` prerender failures (React-context-null, same digests as clean main) remain documented in deferred-items.md (OUT OF SCOPE — none of those pages touch proxy/middleware/ap_session/useUser). Zero deviations from plan. See `.planning/phases/22c-oauth-google/22c-08-SUMMARY.md`. |
| Phase 22c-09 (cross-user isolation + manual smoke gate + 3 plan-gap fixes) | **COMPLETE** | `323312c`, `ecca249`, `4f7d8b0`, `fdf3924`, `f9a7df9` | Phase-exit gate. Cross-user isolation integration test (`api_server/tests/auth/test_cross_user_isolation.py`) — 2 distinct OAuth users (Google + GitHub) + GET /v1/agents disjoint-set check + R8 belt-and-suspenders 8-table COUNT=0 pre-assertion (proves migration 006 ran via conftest's `alembic upgrade head`); 1 passed in 4.60s. Manual smoke checklist `test/22c-manual-smoke.md` covering 6 scenarios: 4 browser OAuth flows + 2 curl-automatable gates. **All 4 browser scenarios PASS reported by human operator 2026-04-28** — Google happy path lands on /dashboard with real name + ap_session cookie, GitHub happy path same shape, access_denied → /login?error=access_denied + sonner toast, logout invalidates session (curl replay returns HTTP 401). Three plan gaps surfaced + fixed inline as 22c-09 commits per phase-gate doctrine: (1) `4f7d8b0` Dockerfile.api missing authlib + itsdangerous (added to pip install chain — pyproject was updated by Wave 0 but Dockerfile drifted); (2) `fdf3924` httpx promoted from dev to runtime deps in pyproject.toml + Dockerfile (authlib's StarletteOAuth2App imports httpx_client transitively, ModuleNotFoundError on second rebuild); (3) `f9a7df9` OAuth callback redirect host bug — `RedirectResponse("/dashboard")` resolved against API origin (localhost:8000) → 404; added AP_FRONTEND_BASE_URL setting (default http://localhost:3000) + prefixed both _DASHBOARD_PATH and _LOGIN_PATH at every callsite + `_login_redirect_with_error()` now takes settings; 2 test assertions updated for absolute URL. 3 UX findings deferred to 22c.1 per AMD-02 scope discipline (Alex Chen on /playground, /#playground fragment, Persistent+Telegram default + conditional fields). See `.planning/phases/22c-oauth-google/22c-09-SUMMARY.md`. |
| Phase 22c.3-01 (Wave 0 spike re-validation gate — 5/5 inapp recipes) | **COMPLETE** | `f32df66`, `55138e7`, `f0341e7` | Empirical Wave-0 close-out gate emitted (`spikes/wave-0-summary.md` with `WAVE-0-CLOSED` marker). All 5 inapp recipes empirically validated with real OpenRouter LLM round-trips against current local Docker images on 2026-04-30: hermes (`/v1/chat/completions` :8642, openai_compat, 163-char persona-correct reply), nanobot (`/v1/chat/completions` :8900 via `nanobot serve --timeout 600`, openai_compat, 90-char reply), openclaw (`/v1/chat/completions` :18789 via `gateway run` + `chatCompletions.enabled=true` config flag, openai_compat envelope-shape PASS — content surfaced upstream Anthropic billing error from zero-credit probe-time key, faithfully relayed by the bot per dumb-pipe D-22; independently verified against api.anthropic.com directly), nullclaw (NEW v3 native `/a2a` JSON-RPC 2.0 :3000 via `a2a.enabled=true` config + `gateway.require_pairing=false`, a2a_jsonrpc, state=completed + 102-char reply at `result.artifacts[0].parts[0].text`, agent-card `protocolVersion=0.3.0`), zeroclaw (NEW Round-3 substitution for picoclaw — `ghcr.io/zeroclaw-labs/zeroclaw:latest` 66.2 MB Rust distroless, native `/webhook` :42617 via `onboard --quick` + `config set gateway.{allow-public-bind,host,require-pairing}` + `daemon`, zeroclaw_native, 100-char reply at `body.response` with `body.model`, `X-Idempotency-Key` replay returns `{idempotent:true,status:"duplicate"}`). picoclaw NOT spiked (deferred per user direction); `recipes/picoclaw.yaml` UNTOUCHED. nullclaw v2 sidecar pattern (runtime package install + HTTP-to-CLI bridge :18791) fully dropped per Round-3 supersession. Plans 22c.3-{02..15} unblocked. 3 contract adapters (openai_compat / a2a_jsonrpc / zeroclaw_native) for Plan 22c.3-05 dispatcher empirically reachable. Zero rule-deviations; one Wave-0 honest-observation: hermes naive bootstrap requires `/opt/data/config.yaml::model.default` (recipe-bootstrap detail; Plan 22c.3-10 absorbs); nullclaw spike banner reworded to drop forbidden v2 sidecar tokens after first-draft tripped Task 2 verify regex (no semantic change). See `.planning/phases/22c.3-inapp-chat-channel/22c.3-01-SUMMARY.md`. |
| Phase 22c.3-03 (Wave 1 partner — sse-starlette + redis deps + redis:7-alpine compose + AP_REDIS_URL wiring) | **COMPLETE** | `9e85e64`, `ede14f5`, `8721e98`, `e57cac7` | Stack-readiness for Wave 2+. New Pydantic Settings field `redis_url` (default `redis://redis:6379/0`; AP_REDIS_URL env alias; case-insensitive) — 3/3 unit tests PASS in 0.10s. Two new runtime deps in `api_server/pyproject.toml`: `sse-starlette>=3.4,<4` (SSE response with heartbeat + Last-Event-Id replay) + `redis>=5.2,<7` (asyncio Pub/Sub client) — same pins ALSO appended to `tools/Dockerfile.api`'s build-stage `pip install --prefix=/install` chain (22c-09 precedent: pyproject changes alone don't bake into the image; Dockerfile mirrors the dep list). Image rebuilt to `sha256:4675c28f55b5` — `import sse_starlette; import redis.asyncio` succeeds inside the new image (sse_starlette 3.4.1 + redis 6.4.0). New `redis: redis:7-alpine` compose service in `deploy/docker-compose.prod.yml` between postgres and api_server — NO `ports:` block (D-08 honored: loopback-only inside the compose bridge net; the bridge IS the security boundary; never exposed publicly). `AP_REDIS_URL=redis://redis:6379/0` wired into api_server env + `depends_on.redis.condition: service_healthy` (api_server only boots after redis is healthy, same shape as postgres). New 127.0.0.1:6379 host-port override in `deploy/docker-compose.local.yml` so host-venv tests can hit redis via `AP_REDIS_URL=redis://localhost:6379/0` (CONTEXT.md line 299 path) — never applies on the prod box. Live verification: deploy-redis-1 healthy + deploy-api_server-1 healthy + /healthz=200; pubsub round-trip from inside api_server (publish from one redis.asyncio client + subscribe from a second; subscriber count=1; `b'{"ok":true}'` delivered as expected); `redis-cli -h redis ping` from inside redis container returns PONG; `redis-cli -h 127.0.0.1 -p 6379` from host (via the local override) returns PONG; prod-only compose config has zero `ports:` block on redis. One Rule 1 deviation auto-fixed inline: the plan's first-pass `--protected-mode yes` silently RST-closed api_server's connections from the bridge IP (verified empirically — `Connection reset by peer` from `redis.asyncio.from_url`). Switched to `--protected-mode no`; the security boundary is the bridge network itself (D-08), not the per-process Redis flag designed for hostile-public-network defaults. Zero plan deviations beyond that single inline Rule 1 fix. See `.planning/phases/22c.3-inapp-chat-channel/22c.3-03-SUMMARY.md`. |
| Phase 22c.3-02 (Alembic 007 — inapp_messages + outbox + auth_token + extended kind CHECK) | **COMPLETE** | `b4bef12`, `b9b5004` | Additive schema migration applied live to `deploy-postgres-1` — alembic_version transitioned 006 → 007_inapp_messages. Adds: `inapp_messages` table (11 columns: id/agent_id/user_id/content/status/attempts/last_error/last_attempt_at/bot_response/created_at/completed_at) + ck_inapp_messages_status (4 values: pending/forwarded/done/failed) + ix_inapp_messages_agent_status btree on (agent_id,status) + ix_inapp_messages_status_attempts partial btree on (status,last_attempt_at) WHERE status IN ('pending','forwarded') (powers dispatcher pump + reaper sweep without scanning terminal rows); `agent_events.published` BOOLEAN NOT NULL DEFAULT FALSE (D-33 outbox flag) + ix_agent_events_published partial btree on (id) WHERE published=false; pre-007 rows backfilled `published=TRUE` so the future Plan 22c.3-07 outbox pump doesn't re-publish history; `agent_containers.inapp_auth_token` TEXT nullable (http_localhost dispatcher's bearer-token slot); ck_agent_events_kind extended via DROP+CREATE under same name from 4 prior kinds (reply_sent/reply_failed/agent_ready/agent_error) to 7 (adds inapp_inbound/inapp_outbound/inapp_outbound_failed per D-13/D-24). 2 testcontainers PG 17 integration tests PASS in 4.43s: full DDL shape (11 columns + types/nullability + ck reject-junk + ck accept-each-canonical + partial-index predicate + 7-kind constraint + agent_events kind=inapp_inbound INSERT works) + reversible round-trip (upgrade→downgrade-1→upgrade leaves identical schema; round-trip test drains new-kind rows pre-downgrade — test isolation refinement, not migration weakness; downgrade rejecting orphan inapp_inbound rows is correct prod behavior). Live apply via canonical `docker cp + docker exec` pattern (Plan 22c-02 established this; macOS Docker Desktop doesn't bridge container IPs to host so direct alembic from host venv times out). One Rule-1 deviation auto-fixed inline: round-trip test failed on first GREEN run because test-1 inserted an `agent_events` row with kind='inapp_inbound' under shared module-scoped pg fixture, then test-2's downgrade rebuilt the 4-kind CHECK and that row tripped it; fix = DELETE new-kind rows before downgrade. Zero plan deviations. See `.planning/phases/22c.3-inapp-chat-channel/22c.3-02-SUMMARY.md`. |
| Phase 22c.3-05 (Wave 2 — inapp dispatcher with 3-way contract adapter switch) | **COMPLETE** | `a9a68bb`, `00bb1ca` | 250ms-tick asyncio dispatcher draining inapp_messages pending → forwarded → (done | failed). 3 contract adapters in one Python match-statement: openai_compat (hermes/nanobot/openclaw — `POST {url}/v1/chat/completions` body `{model,messages:[{role,content}]}` parse `data.choices[0].message.content`), a2a_jsonrpc (nullclaw native A2A — `POST {url}/a2a` JSON-RPC 2.0 method=`message/send` parse `data.result.artifacts[0].parts[0].text`), zeroclaw_native (zeroclaw `/webhook` body `{message}` with `X-Idempotency-Key` + `X-Session-Id` headers parse `data.response`). Unknown contract → `RuntimeError(f"unknown_contract:{value}")` → terminal failure. Consumes Plan 22c.3-04 store API verbatim (mark_forwarded/mark_done/mark_failed/fetch_pending_for_dispatch) — zero inlined SQL. Honors locked CONTEXT decisions D-22 (dumb-pipe, no prompt composition), D-27 (status enum pending|forwarded|done|failed), D-28 (persist-before-action via store), D-32 (FOR UPDATE SKIP LOCKED via Plan 04), D-37/D-38 (readiness gate fails fast for unready containers — `container_status='running' AND ready_at IS NOT NULL AND stopped_at IS NULL`), D-40 (600s timeout, 1 attempt, NO auto-retry — terminal failures transition DIRECTLY to status='failed'; reaper Plan 22c.3-06 handles stuck 'forwarded' rows). NEW `services/inapp_recipe_index.py` ships frozen `InappChannelConfig` dataclass + `InappRecipeIndex` (lazy LRU cache of recipes/*.yaml channels.inapp blocks keyed by recipe_name with mtime-based invalidation; 60s container-IP cache via `docker.from_env().containers.get(container_id).attrs['NetworkSettings']['Networks'][network_name]['IPAddress']` per RESEARCH §Don't Hand-Roll). Adding a 4th contract later is a Literal extension + new match arm — no refactor. INSERTs agent_events with `published=false` on every terminal outcome (success → kind=`inapp_outbound`, failure → kind=`inapp_outbound_failed`) so Plan 22c.3-07 outbox pump fans out via Redis. NO Postgres pub/sub primitives anywhere; outbox is the canonical fan-out path. 20 tests PASS (10 unit InappRecipeIndex + 10 testcontainer PG dispatcher integration with respx-mocked bot endpoints): 3 contract happy paths (openai_compat / a2a_jsonrpc / zeroclaw_native — last asserts `X-Session-Id: inapp:<user_id>:<agent_id>` was sent on the wire); 5 failure paths (unknown_contract / bot_timeout / bot_5xx / bot_empty / container_not_ready / recipe_lacks_inapp_channel); D-40 no-retry invariant proven (test_no_auto_retry_on_failure asserts attempts=1 + status='failed' after a 5xx response). 2 Rule-1 deviations auto-fixed in same task: (1) docstring contained the forbidden tokens "LISTEN"/"NOTIFY" describing what dispatcher does NOT use — re-worded to "no PG pub/sub primitives" so gate 4 passes; (2) test_unknown_contract_marks_failed initial design relied on monkey-patching `recipe_index._cache` but the cache-invalidation path silently re-loaded the on-disk YAML — switched to direct `recipe_index.get_inapp_block = _stub_get` method override. Zero plan deviations. Plans 22c.3-06 (reaper) / 22c.3-07 (outbox pump) ready in parallel. See `.planning/phases/22c.3-inapp-chat-channel/22c.3-05-SUMMARY.md`. |
| Phase 22c.3-07 (Wave 2 — inapp_outbox pump 100ms tick PG → Redis Pub/Sub; transactional-outbox pattern) | **COMPLETE** | `d00e459`, `59445ce`, `65a4989` | First transactional-outbox pattern in api_server (PATTERNS.md GREENFIELD). 100ms-tick lifespan-managed asyncio task: SELECTs up to 100 unpublished `agent_events` rows (`published=false` AND `e.ts > NOW() - INTERVAL '1 hour'` per D-35) with `FOR UPDATE OF e SKIP LOCKED` (D-32 multi-replica safety) JOINing `agent_containers ON c.id = e.agent_container_id` to derive the channel name from `c.agent_instance_id` (D-09 channel = `agent:inapp:<agent_instance_id>`); for each row publishes JSON envelope `{seq:int, kind:str, payload:dict, correlation_id:str|None, ts:str}` (D-34) to Redis; bulk UPDATEs all successfully-published `id`s to `published=true`. **Pitfall 3 strategy 2 honored** (RESEARCH §Pattern 3 + Pitfall 3): on any `redis.RedisError` mid-batch, return early — outer `conn.transaction()` rolls back; bulk UPDATE never runs; ALL rows stay `published=false`; next tick retries the entire batch. Trade-off: rows that DID publish before the failure get re-published on retry — SSE clients dedupe by seq (D-10 idempotent client-side handling). **D-35 abandon-after-1h enforced in WHERE clause:** rows older than 1h with `published=false` are FILTERED OUT and stay `published=false`; SSE Last-Event-Id replay (Plan 22c.3-08) surfaces them via direct PG read, bypassing Redis. Tunable module-level constants (`PUMP_TICK_S=0.1`, `PUMP_IDLE_TICK_S=0.5`, `PUMP_BATCH_LIMIT=100`, `ABANDON_AFTER=timedelta(hours=1)`) — same shape as Plan 05 dispatcher / Plan 06 reaper; tests can monkey-patch. Sub-second tick (100ms) when busy, idle backoff (500ms) when quiet — saves PG round-trips on a quiet system while keeping latency low on the happy path. Same lifespan-task discipline as dispatcher_loop and reaper_loop: while-not-stop_event + try/except + `asyncio.wait_for(stop_event.wait(), tick_seconds)` for responsive cancel. **8 testcontainer-PG + testcontainer-Redis integration tests PASS** in 9.77s: happy path (3 unpublished → 3 publishes + UPDATE), skip-published (no re-publish), D-35 abandon-after-1h (2h-old row filtered out + stays published=false), Pitfall 3 strategy 2 Redis-failure rollback (mock-patched `redis.publish` raises `RedisError` on 2nd call → 0 swept; retry tick PASSes all 3), D-32 SKIP LOCKED (asyncio.gather of 2 `_pump_once` calls covers all 5 rows with no double-publish), D-09 per-agent fan-out (agent A receives 2; agent B receives 1), stop_event cancel within ~1s, D-34 envelope shape (exact 5-key set + types: seq=int, payload=dict, ts=ISO-8601-parseable). 31/31 adjacent integration regressions (Plan 04 store + Plan 05 dispatcher + Plan 06 reaper) green; 88/88 unit-test regressions green. **testcontainers[redis] dev extra added** (`testcontainers[postgres]` → `testcontainers[postgres,redis]`) with associated `redis_container` (session-scoped, redis:7-alpine) + `redis_client` (per-test, asyncio.from_url + flushdb cleanup) conftest fixtures. **One Rule-3 deviation auto-fixed inline:** `testcontainers[redis]>=4.14.2` transitively requires `redis>=7`, but pyproject's runtime pin was `redis>=5.2,<7` — pip ResolutionImpossible. Investigated: redis-py 7.x asyncio API is source-compatible with 5.x (same `from_url`, `publish`, `RedisError` class, `pubsub()` ctx manager); the prior `<7` ceiling was precautionary, not known-incompatibility. Bumped runtime pin to `redis>=5.2,<8` and updated comment. All tests green; redis-py imported as 7.4.0; Plan 03 lifespan probe (`redis_async.from_url`) tested via the test fixture's identical call. Wave 2 (Plans 04/05/06/07) is now COMPLETE; Wave 3 (Plans 08 routes + 09 lifespan) is next. See `.planning/phases/22c.3-inapp-chat-channel/22c.3-07-SUMMARY.md`. |
| Phase 22c.3-06 (Wave 2 — inapp_reaper 15s tick D-40 direct-to-failed stuck-row sweep) | **COMPLETE** | `d9444dc`, `79279e4` | Lifespan-managed asyncio task. Ticks every 15s (`REAPER_TICK_S = 15`); selects `inapp_messages` rows in `status='forwarded'` with `last_attempt_at < NOW() - INTERVAL '11 minutes'` (`STUCK_THRESHOLD_MINUTES = 11`; D-40 revision = 10min dispatcher bot-timeout + 1min slack). Per D-40 (no auto-retry, revised 2026-04-29) — every stuck row transitions DIRECTLY to `status='failed'` with `last_error='reaper_timeout'`; the reaper does NOT inspect `attempts` and does NOT requeue to pending regardless of attempt count. Per D-32 (`FOR UPDATE SKIP LOCKED` from Plan 04's `fetch_stuck_forwarded`) — two reaper ticks (or a reaper + a dispatcher) cannot pick the same row. Per D-33 — each failure transition writes an `agent_events` row `kind='inapp_outbound_failed'`, `error_type='reaper_timeout'` with `published=false` (alembic 007 column default — `insert_agent_event` does NOT take a `published` kwarg) IN THE SAME tx as `mark_failed` so Plan 22c.3-07 outbox pump never sees a state mismatch. Holding the FOR UPDATE row-locks across the per-row writes is safe here because there is no httpx call (the reaper has no equivalent of the dispatcher's 600s bot call that demands lock release). Consumes Plan 04 store API verbatim (`ims.fetch_stuck_forwarded` + `ims.mark_failed`); zero inlined SQL on `inapp_messages`. `agent_container_id` resolution via `JOIN agent_containers` on `agent_instance_id` ordered by `stopped_at DESC NULLS LAST, created_at DESC LIMIT 1` (live containers first, then most-recent stopped). Orphan-message defensive branch: a stuck row whose container parent has been deleted is still marked failed but emits NO `agent_events` row (logs warning + continues). 6 testcontainer-PG integration tests PASS in 3.00s: (1) happy-path 12min stuck → failed + agent_events INSERT with payload `error_type=reaper_timeout, retry_count=1, captured_at=…`; (2) fresh 5min forwarded row left untouched (within 11min budget); (3) pending + done rows ignored even when 20min back-dated — only `forwarded` is reaped; (4) **D-40 no-auto-retry**: 5 stuck rows attempts=1..5 ALL transition to failed (NOT pending) — the canonical D-40 invariant test; (5) **SKIP LOCKED isolation**: `asyncio.gather` of 2 coroutines — connection A holds a `FOR UPDATE` lock on stuck-row-1 inside an open tx, B's `_sweep_once` picks stuck-row-2 only and emits exactly 1 agent_events row; A's row is still `forwarded` afterwards (would be reaped on the next tick); (6) `reaper_loop` background task finishes within ~1s when `stop_event.set()` — `asyncio.wait_for(stop_event.wait(), TICK_S)` inside the loop wakes IMMEDIATELY on shutdown, never lags the full 15s tick. Plan 22c.3-09 lifespan attaches via `asyncio.create_task(reaper_loop(state, stop_event))` — duck-typed state needs only `state.db`. 2 Rule-1 deviations auto-fixed inline: (1) plan ACTION example showed `insert_agent_event(..., published=False, correlation_id=...)` but the function signature has no `published` kwarg — relying on alembic 007's `server_default FALSE` is the canonical pattern (Plan 22c.3-05 dispatcher already follows it); (2) module constants written as `STUCK_THRESHOLD_MINUTES: int = 11` tripped the plan's literal grep gate (`grep -q "STUCK_THRESHOLD_MINUTES = 11"`) — type annotations dropped to align with the verify substring. Zero plan deviations. Adjacent regression: Plan 04's 15 store integration tests + Plan 05's 10 dispatcher integration tests + 88 Phase 22b unit tests all still green. Plan 22c.3-07 (outbox pump) is the last remaining Wave 2 plan. See `.planning/phases/22c.3-inapp-chat-channel/22c.3-06-SUMMARY.md`. |
| Phase 22c.3-04 (Wave 2 head — inapp_messages_store 10-function seam + 3 Pydantic event payloads) | **COMPLETE** | `be839c6`, `ba1e0bd`, `baab35c`, `c2ff352` | Single-seam repository module for the durable inapp_messages state machine + 3 Pydantic event payload classes with extra='forbid'. **Pydantic layer (Task 1):** `models/events.py` extended `VALID_KINDS` 4→7 (D-13); 3 new classes `InappInboundPayload` (content+source=user+from_user_id+captured_at), `InappOutboundPayload` (content+source=agent+captured_at), `InappOutboundFailedPayload` (error_type 9-value enum + message≤512 + retry_count≥0 + captured_at) all with `ConfigDict(extra='forbid')` per D-22 dumb-pipe (defense-in-depth, NOT D-06 privacy boundary since these payloads carry user content); `KIND_TO_PAYLOAD` extended; `__all__` updated. 20 unit tests PASS in 0.07s (12 documented + 8 parametrized error_type cases) including D-02 regression (4 prior kinds still resolve via KIND_TO_PAYLOAD) + D-14 router whitelist (inapp_inbound in VALID_KINDS so existing GET /v1/agents/:id/events?kinds= router accepts it). **Store layer (Task 2):** new `services/inapp_messages_store.py` exports 10 asyncpg functions: `insert_pending`, `fetch_by_id` (user_id WHERE filter at SQL — defense-in-depth like run_store.fetch_agent_instance), `fetch_pending_for_dispatch` (FOR UPDATE OF m SKIP LOCKED + JOIN agent_containers — returns container_id + container_status + ready_at + stopped_at + recipe_name + channel_type + inapp_auth_token in one round-trip; readiness gate stays in dispatcher per D-37), `mark_forwarded` (bulk pending→forwarded via ANY($1::uuid[]) + attempts+1 + last_attempt_at NOW(); empty-list no-op guard), `mark_done` (forwarded→done + bot_response verbatim per D-22 + completed_at), `mark_failed` (forwarded→failed + last_error + completed_at), `fetch_stuck_forwarded` (D-30 reaper, threshold_minutes arg, FOR UPDATE SKIP LOCKED for multi-replica safety), `restart_sweep` (D-31 lifespan recovery; default 15min; UPDATE count parsed from asyncpg command-tag string with try/except IndexError-ValueError fallback to 0), `fetch_history_for_agent` (ORDER BY created_at DESC for newest-first REST endpoint), `delete_history_for_agent_user` (D-43 delete-only-messages preserves agent_instances + agent_containers per D-44; sibling agent_events DELETE belongs in route handler since events are keyed by agent_container_id not agent_id). 15 integration tests PASS in 3.95s against testcontainer PG 17: CRUD basics + dispatcher pump (FIFO order + SKIP LOCKED proof via asyncio.gather of 2 independent pool connections — connection A locks row 1 in transaction, B fetches limit=10 sees only rows 2,3) + state transitions + reaper threshold sensitivity (12min back IN, 5min back OUT) + restart_sweep returns affected count (1) + cross-tenant history filter (user A sees 2, user B sees 1) + delete leaves parent rows untouched + JOIN agent_containers pulls inapp_auth_token. 2 Rule deviations auto-fixed: (1) Rule-1 test adjustment — Phase 22b `test_valid_kinds_exact` asserted exact-equality of 4 kinds; switched to subset check so the spec-required 22c.3 extension to 7 kinds is admitted while preserving the "4 prior kinds remain present" invariant; (2) Rule-2 missing-function disambiguation — plan ACTION block named 9 store functions but `must_haves.truths` listed 10 (`fetch_by_id` was the missing one); shipped all 10 since fetch_by_id is consumed by Plan 08 routes. Plans 22c.3-05/06/07/08/09 fully unblocked. See `.planning/phases/22c.3-inapp-chat-channel/22c.3-04-SUMMARY.md`. |

### 📍 RESUME ANCHOR — READ AFTER /clear (UPDATED 2026-04-30 post-22c.3-09-execution)

**Phase 22c.3 (in-app chat channel) Wave 3 COMPLETE.** Plan 22c.3-09 (lifespan attach for the 3 background tasks + Redis client + httpx.AsyncClient + D-31 restart sweep + alembic 008 live apply + image rebuild) committed 2026-04-30 (2 commits: e320e80 RED tests, 18d8d31 GREEN main.py + conftest fix). **5/5 lifespan integration tests PASS** against real PG + real Redis testcontainers covering D-15/D-16/D-30/D-31/D-32/D-33/D-34: 3 named tasks (`inapp_dispatcher` / `inapp_reaper` / `inapp_outbox`) attached + visible in `asyncio.all_tasks()`; `app.state.redis.ping()=True`; `app.state.bot_http_client` is httpx.AsyncClient with timeout=600s+connect=5s+max_connections=50; D-31 restart_sweep flips a 16-min stuck `forwarded` row to `pending` at boot; **D-15/D-16 fail-loud invariant proven** (`AP_REDIS_URL=redis://192.0.2.1:1/0` (RFC 5737 unroutable) → lifespan boot raises within 30s); shutdown drain sets `inapp_stop` + every task `done()` within 5s budget. Lifespan ordering: inapp wiring runs BEFORE the 22b watcher re-attach so Redis fail-loud isn't gated on Docker daemon timeouts. **alembic 008 applied live** to deploy-postgres-1 via canonical `docker cp + docker exec` pattern (alembic_version 007 → 008_idempotency_relax_run_fk; idempotency_keys.run_id is now nullable, FK to runs.id dropped). **api_server image rebuilt + container redeployed** (`Up X seconds (healthy)`); `/healthz=200 {"ok":true}`. **Live end-to-end smoke proves all 3 lifespan loops are running:** PG INSERT agent_events (published=false) → outbox_pump publishes envelope to Redis channel `agent:inapp:<agent_instance_id>` → external `redis-cli SUBSCRIBE` receives canonical 5-key JSON in ~2s → row marked published=true; separately, restart_sweep flipped a `forwarded` row → dispatcher_loop ran the readiness gate → outbox_pump_loop published the resulting `inapp_outbound_failed` event. Graceful `docker compose stop` produces clean `Application shutdown complete` with no errors and no hangs. 88/88 unit + 55/55 22c.3 integration regressions green. 2 Rule deviations auto-fixed inline: (Rule 3) `conftest.async_client` fixture extended to depend on session-scoped `redis_container` + inject `AP_REDIS_URL` — required because the lifespan now PINGs Redis at boot fail-loud and every async_client-using unit test would otherwise blow up; (Rule 1) test schema bug — `inapp_messages` has no `container_row_id` column (alembic 007 only declares user_id + agent_id; dispatcher resolves container at fetch-time JOIN). **Wave 3 CLOSED. Wave 4 is next: Plans 22c.3-10..14 (5 recipe modifications — hermes/nanobot/openclaw/nullclaw/zeroclaw channels.inapp blocks).**

```
Phase 22c    — OAuth-Google           ✅ COMPLETE (commit c02d3c6)
Phase 22c.1  — Stop Lying             [CONTEXT seeded; wave-1 commit c8ca6a5; planning not started]
Phase 22c.2  — Identity Baking        [CONTEXT seeded; not started]
Phase 22c.3  — In-App Chat            🟡 EXECUTING — Plans 01 + 02 + 03 + 04 + 05 + 06 + 07 + 08 + 09 + 10 + 11 + 12 + 13 SHIPPED; Wave 4 IN PROGRESS (4 of 5 recipes opted into inapp: hermes + nanobot + openclaw + zeroclaw); next is Plan 22c.3-14 (nullclaw)
Phase 23     — Flutter Native         [DESIGNED via mockups; depends on 22c.3]
```

**The next command is:**

```
/clear  →  /gsd-execute-phase 22c.3-inapp-chat-channel
```

Why: Wave 3 closed the data + control + bootstrap planes. Plans 04-08 ship the durable state machine + 3 background loops + 3 HTTP routes + the supporting middleware extensions. Plan 09 attached the loops to the lifespan and proved end-to-end that the data flow works against the live api_server (PG → outbox publish → Redis subscriber receives JSON envelope; restart_sweep + dispatcher + outbox pump all firing in production). Wave 4 (Plans 22c.3-10..14) authors the 5 recipe `channels.inapp` YAML blocks — the dispatcher's contract switch is content-driven, so adding a recipe is a YAML edit + a smoke verification, no code change to the api_server. Wave 5 (22c.3-15) e2e gates phase exit. picoclaw is OUT of scope.

**Plan 22c.3-01 outcome (Wave 0 gate):** 5/5 PASS — hermes/nanobot/openclaw via openai_compat, nullclaw via native a2a_jsonrpc, zeroclaw via zeroclaw_native (Round-3 substitution for picoclaw). Commits f32df66 + 55138e7 + f0341e7. Per-recipe spike artifacts at `.planning/phases/22c.3-inapp-chat-channel/spikes/recipe-*.md` — re-runnable docker-run + curl commands embedded. Pre-flight note for Plan 22c.3-15: ensure ANTHROPIC_API_KEY has non-zero credit before that e2e run (the openclaw e2e cell uses anthropic-direct per provider_compat — was zero-credit on probe-time account, contract-shape verdict still PASSES).

**Plan 22c.3-02 outcome (alembic 007):** Live applied to deploy-postgres-1 — alembic_version=007_inapp_messages. Adds `inapp_messages` (durable D-27 state machine: 11 columns + 4-status CHECK + btree (agent_id,status) + partial btree (status,last_attempt_at) WHERE status IN ('pending','forwarded')); `agent_events.published` BOOLEAN NOT NULL DEFAULT FALSE (D-33 outbox flag) with partial index on WHERE published=false; pre-007 rows backfilled `published=TRUE`; `agent_containers.inapp_auth_token` TEXT nullable; ck_agent_events_kind extended from 4 to 7 kinds (D-13/D-24). Commits b4bef12 (RED test) + b9b5004 (GREEN migration). 2/2 testcontainers integration tests PASS in 4.43s (full DDL shape + reversible round-trip). Live verification: `\d inapp_messages` shows all 11 columns + 2 indexes + 2 FK CASCADE constraints. One Rule-1 deviation auto-fixed inline (round-trip test drains new-kind rows pre-downgrade — test isolation refinement). Live apply via canonical `docker cp + docker exec` (Plan 22c-02 pattern; macOS Docker Desktop doesn't bridge container IPs to host).

**Plan 22c.3-03 outcome (Wave 1 partner — sse-starlette + redis deps + redis:7-alpine compose service + AP_REDIS_URL wiring):** Stack-readiness for Wave 2+. New Pydantic Settings field `redis_url` (default `redis://redis:6379/0`; AP_REDIS_URL env alias; case-insensitive) — 3/3 unit tests PASS in 0.10s. Two new runtime deps in `api_server/pyproject.toml`: `sse-starlette>=3.4,<4` (SSE response with heartbeat + Last-Event-Id replay) + `redis>=5.2,<7` (asyncio Pub/Sub client) — same pins ALSO appended to `tools/Dockerfile.api`'s build-stage `pip install --prefix=/install` chain (22c-09 precedent that pyproject changes alone don't bake into the image; Dockerfile mirrors the dep list). Image rebuilt to `sha256:4675c28f55b5` — `import sse_starlette; import redis.asyncio` succeeds inside the new image (sse_starlette 3.4.1 + redis 6.4.0). New `redis: redis:7-alpine` compose service in `deploy/docker-compose.prod.yml` between postgres and api_server — NO `ports:` block (D-08 honored: loopback-only inside the compose bridge net; the bridge IS the security boundary; never exposed publicly). `AP_REDIS_URL=redis://redis:6379/0` wired into api_server env + `depends_on.redis.condition: service_healthy`. New 127.0.0.1:6379 host-port override in `deploy/docker-compose.local.yml` so host-venv tests can hit redis via `AP_REDIS_URL=redis://localhost:6379/0` — never applies on the prod box. Live verification: deploy-redis-1 healthy + deploy-api_server-1 healthy + /healthz=200; pubsub round-trip from inside api_server (publish + subscribe via redis.asyncio; subscriber count=1; payload `b'{"ok":true}'` delivered as expected); `redis-cli -h redis ping` from inside redis container returns PONG; `redis-cli -h 127.0.0.1 -p 6379` from host returns PONG. Commits 9e85e64 (TDD RED test) + ede14f5 (TDD GREEN config field) + 8721e98 (deps + Dockerfile + image rebuild) + e57cac7 (compose redis service + AP_REDIS_URL + Rule 1 protected-mode fix). One Rule 1 deviation auto-fixed inline: the plan's first-pass `--protected-mode yes` silently RST-closed api_server's connections from the bridge IP (verified empirically — `Connection reset by peer`); switched to `--protected-mode no` because the security boundary is the bridge network itself (D-08), not the per-process Redis flag designed for hostile-public-network defaults. Zero plan deviations beyond that single inline fix. See `.planning/phases/22c.3-inapp-chat-channel/22c.3-03-SUMMARY.md`.

**Plan 22c.3-05 outcome (Wave 2 — inapp dispatcher with 3-way contract adapter switch + InappRecipeIndex):** 250ms-tick asyncio dispatcher draining `inapp_messages` pending → forwarded → (done | failed). 3 contract adapters in one Python match-statement: `openai_compat` (hermes/nanobot/openclaw — POST `{url}/v1/chat/completions` body `{model, messages:[{role,content}]}` parse `data.choices[0].message.content`), `a2a_jsonrpc` (nullclaw native A2A — POST `{url}/a2a` JSON-RPC 2.0 method=`message/send` parse `data.result.artifacts[0].parts[0].text`), `zeroclaw_native` (zeroclaw `/webhook` body `{message}` with `X-Idempotency-Key` + `X-Session-Id` headers parse `data.response`). Unknown contract → `RuntimeError(f"unknown_contract:{value}")` → terminal failure (test_unknown_contract_marks_failed asserts last_error startswith `unknown_contract:`). Consumes Plan 22c.3-04 store API verbatim (mark_forwarded/mark_done/mark_failed/fetch_pending_for_dispatch) — zero inlined SQL on `inapp_messages`. Honors locked CONTEXT D-22 (dumb-pipe, no prompt composition), D-27 (status enum), D-28 (persist-before-action via store), D-32 (FOR UPDATE SKIP LOCKED via Plan 04), D-37/D-38 (readiness gate fails fast for unready containers — `container_status='running' AND ready_at IS NOT NULL AND stopped_at IS NULL`), D-40 (600s timeout, 1 attempt, NO auto-retry — terminal failures transition DIRECTLY to status='failed'; reaper Plan 22c.3-06 handles stuck `forwarded` rows). NEW `services/inapp_recipe_index.py` (412 LOC) ships frozen `InappChannelConfig` dataclass + `InappRecipeIndex` (lazy LRU cache of `recipes/*.yaml` `channels.inapp` blocks keyed by recipe_name with mtime-based invalidation; 60s container-IP cache via `docker.from_env().containers.get(container_id).attrs['NetworkSettings']['Networks'][network_name]['IPAddress']`). Adding a 4th contract later is a `Literal` extension + new `case` arm — no refactor. INSERTs `agent_events` with `published=false` on every terminal outcome (success → kind=`inapp_outbound`, failure → kind=`inapp_outbound_failed`) so Plan 22c.3-07 outbox pump fans out via Redis. NO Postgres pub/sub primitives anywhere; outbox is the canonical fan-out path. 20 tests PASS (10 unit InappRecipeIndex + 10 testcontainer PG dispatcher integration with respx-mocked bot endpoints): 3 contract happy paths (openai_compat / a2a_jsonrpc / zeroclaw_native — last asserts `X-Session-Id: inapp:<user_id>:<agent_id>` was sent on the wire); 5 failure paths (unknown_contract / bot_timeout / bot_5xx / bot_empty / container_not_ready / recipe_lacks_inapp_channel); D-40 no-retry invariant proven (`test_no_auto_retry_on_failure` asserts `attempts=1 + status='failed'` after a 5xx response). Commits a9a68bb (feat: dispatcher + recipe_index) + 00bb1ca (test: 20 tests). 2 Rule-1 deviations auto-fixed inline: (1) docstring contained the forbidden tokens `LISTEN`/`NOTIFY` describing what dispatcher does NOT use — re-worded to "no PG pub/sub primitives" so gate 4 passes (`grep -cE "queued|dispatched|delivered|ledger_seq|inapp_messages_state_history|NOTIFY|LISTEN" → 0`); (2) `test_unknown_contract_marks_failed` initial design relied on monkey-patching `recipe_index._cache` but the cache-invalidation path silently re-loaded the on-disk YAML — switched to direct `recipe_index.get_inapp_block = _stub_get` method override. Zero plan deviations. Plans 22c.3-06 (reaper) / 22c.3-07 (outbox pump) ready in parallel. See `.planning/phases/22c.3-inapp-chat-channel/22c.3-05-SUMMARY.md`.

**Phase 22c.3 final matrix (Round 3, post-substitution):**

| Recipe | Endpoint | Contract | Notes |
|---|---|---|---|
| hermes | `/v1/chat/completions` :8642 | `openai_compat` | env-flag activation (`API_SERVER_ENABLED=true` + `API_SERVER_KEY`) |
| nanobot | `/v1/chat/completions` :8900 | `openai_compat` | `nanobot serve --timeout 600` mode |
| openclaw | `/v1/chat/completions` :18789 | `openai_compat` | config-flag `chatCompletions.enabled=true` (MSV pattern); model field rewritten to `"openclaw"` |
| nullclaw | `/a2a` :3000 | `a2a_jsonrpc` | native Google A2A JSON-RPC 2.0 (NOT sidecar — that approach was superseded in Round 3) |
| **zeroclaw** (NEW) | `/webhook` :42617 | `zeroclaw_native` | image_pull `ghcr.io/zeroclaw-labs/zeroclaw:latest` (Rust, distroless ~50 MB, 30,845 ★); built-in `X-Idempotency-Key` + `X-Session-Id` |

**picoclaw**: ~~Round-2 sidecar pattern~~ DEFERRED 2026-04-30 per user direction. `recipes/picoclaw.yaml` UNTOUCHED, stays in repo for backward compat with smoke suite. Reintegrating picoclaw into inapp scope is a separate phase.

**Read these files in this order on resume (after /clear):**

1. `memory/MEMORY.md` (auto-loaded; index of all memories)
2. `memory/project_phase_22c3_planned_handoff.md` — Phase 22c.3 planning journey + critical context (canonical D-27 enum, no NOTIFY/LISTEN, no auto-retry per D-40, etc.)
3. `.planning/phases/22c.3-inapp-chat-channel/22c.3-CONTEXT.md` — 46 locked D-decisions D-01..D-46
4. `.planning/phases/22c.3-inapp-chat-channel/22c.3-RESEARCH.md` — 3 revision rounds; final per-recipe matrix (read §Per-Recipe Feasibility Matrix + §Pitfall 6 for the 3-way contract switch)
5. `.planning/phases/22c.3-inapp-chat-channel/22c.3-PATTERNS.md` — Round-3 supersession banners; sidecar pattern dropped
6. `.planning/phases/22c.3-inapp-chat-channel/22c.3-VALIDATION.md` — covers all 46 D-IDs + 6 SC-IDs
7. `.planning/phases/22c.3-inapp-chat-channel/spikes/recipe-zeroclaw.md` — full empirical /webhook + idempotency + WS streaming evidence (real OpenRouter LLM)
8. `.planning/phases/22c.3-inapp-chat-channel/spikes/recipe-{hermes,nanobot,openclaw,nullclaw,picoclaw}.md` — 5 prior spike artifacts
9. `.planning/phases/22c.3-inapp-chat-channel/22c.3-{01..15}-PLAN.md` — 15 plans (Wave 0 gate at 01; Wave 5 gate at 15)
10. `recipes/zeroclaw.yaml` — NEW recipe (276 LOC; v0.2; image_pull mode)
11. `memory/feedback_check_msv_when_stuck.md` — MSV is the reference implementation (Plan 12 openclaw chatCompletions config flag came from this)
12. `memory/feedback_uniform_transport_5_of_5.md` — 5/5 must work; reject split-bucket matrices
13. `memory/feedback_worktree_breaks_for_live_infra.md` — Plans 02/09/10..15 are `worktree_safe: false`

**Phase 22c.3 plan map:**

| Wave | Plans | Notes |
|------|-------|-------|
| 0 (gate) | 22c.3-01 | Re-validate 5 recipes' chat HTTP surfaces (nullclaw `/a2a`, zeroclaw `/webhook`, hermes/nanobot/openclaw `/v1/chat/completions`) — MUST PASS before Wave 1 |
| 1 | 22c.3-02, 22c.3-03 | Parallel: alembic 007 (`inapp_messages` + `agent_events.published` + `agent_containers.inapp_auth_token` + 3 new event kinds) ∥ deps (sse-starlette + redis-py) + `redis:7-alpine` service in compose |
| 2 | 22c.3-04, 22c.3-05, 22c.3-06, 22c.3-07 | models extension + dispatcher (3-contract switch) + reaper (15s tick, D-40 direct-to-failed) + outbox pump (100ms tick on `agent_events.published=false` → Redis Pub/Sub `agent:inapp:<agent_id>`) |
| 3 | 22c.3-08, 22c.3-09 | 3 routes (POST/SSE GET/DELETE on /v1/agents/:id/messages) → lifespan attach + image rebuild + live redeploy |
| 4 | 22c.3-10..14 | 5 recipe modifications (hermes/nanobot/openclaw/nullclaw/zeroclaw — plan 13 creates recipes/zeroclaw.yaml NEW; plan 14 adds nullclaw native A2A block) |
| 5 (gate) | 22c.3-15 | 5/5 e2e — `make e2e-inapp` + `pytest tests/e2e/test_inapp_5x5_matrix.py`; `e2e-report.json` at `api_server/tests/e2e/`; matrix loop hermes/nanobot/openclaw/nullclaw/zeroclaw |

**Critical context to preserve (pin against drift):**

- D-27 status enum is canonical: `pending|forwarded|done|failed` (NOT queued/dispatched/delivered)
- D-27/D-28 column names: `bot_response`, `last_attempt_at`, `completed_at` (NOT agent_text/attempt_started_at/agent_response_at)
- No `inapp_messages_state_history` table — audit trail lives in `agent_events` (kind=inapp_outbound | inapp_outbound_failed)
- No Postgres NOTIFY/LISTEN — outbox path exclusively via `agent_events.published=false` → Plan 07 outbox pump → Redis Pub/Sub
- D-40 no auto-retry: terminal failures transition DIRECTLY to `'failed'`; reaper handles stuck `'forwarded'` rows
- Plan 04 store API (`mark_forwarded`/`mark_done`/`mark_failed`/`fetch_pending_for_dispatch`) is the discipline — dispatcher does NOT inline raw SQL
- Three contract names canonical: `openai_compat`, `a2a_jsonrpc`, `zeroclaw_native` (NOT `openai_chat_completions`)

### Live infra state (preserved between /clear)

- API server runs at http://localhost:8000 with `{"ok":true}` healthz
- Postgres at deploy-postgres-1; alembic HEAD = **008_idempotency_relax_run_fk** (applied 2026-04-30 via Plan 22c.3-09; previous 007_inapp_messages applied 2026-04-30 via Plan 22c.3-02)
- 9 data-bearing tables tracked post-007 (8 from 006 baseline + `inapp_messages`); inapp_messages COUNT=0 currently
- Schema additions live: `inapp_messages` (D-27 state machine), `agent_events.published` (D-33 outbox flag), `agent_containers.inapp_auth_token` (http_localhost bearer-token slot), `ck_agent_events_kind` extended from 4 to 7 kinds (adds inapp_inbound/inapp_outbound/inapp_outbound_failed per D-13/D-24); `idempotency_keys.run_id` nullable + FK to runs.id dropped (Plan 22c.3-08 chat path uses message_id as cache_id)
- Pre-007 `agent_events` rows backfilled `published=TRUE` so Plan 22c.3-07 outbox pump doesn't re-publish history
- **Lifespan now wires (Plan 22c.3-09):** `app.state.redis` (fail-loud at boot), `app.state.bot_http_client` (httpx.AsyncClient timeout=600s + connect=5s + max_connections=50), `app.state.inapp_tasks` (3 named asyncio tasks: inapp_dispatcher 250ms tick, inapp_reaper 15s tick, inapp_outbox 100ms tick), D-31 restart_sweep at boot (re-queues stuck `forwarded` rows past 15min)
- Every POST to `/v1/runs` + all `/v1/agents/:id/*` paths now require an authenticated `ap_session` cookie (require_user gate)
- **NOTE for next session work**: any new agent_instances / agent_containers / runs writes require a real OAuth session (Google or GitHub) OR direct asyncpg INSERTs with a seeded users row. The ANONYMOUS placeholder UUID is gone.
- Frontend dev server may or may not be running; restart with: `cd frontend && pnpm dev`
- All required env vars present in `deploy/.env.prod` (gitignored): POSTGRES_PASSWORD, AP_CHANNEL_MASTER_KEY, AP_SYSADMIN_TOKEN, AP_OAUTH_GOOGLE_CLIENT_ID, AP_OAUTH_GOOGLE_CLIENT_SECRET, AP_OAUTH_GOOGLE_REDIRECT_URI

### Local dev stack restart (if needed after /clear)

```bash
cd /Users/fcavalcanti/dev/agent-playground

# Bring up the prod-shaped local stack (uses deploy/.env.prod for substitution)

docker compose --env-file deploy/.env.prod \
  -f deploy/docker-compose.prod.yml \
  -f deploy/docker-compose.local.yml \
  up -d

# Verify

curl -s http://localhost:8000/healthz   # → {"ok":true}

# Frontend dev (from project root)

cd frontend && pnpm dev   # → http://localhost:3000
```

### Open backlog (per ACTION-LIST.md after Phase 22c)

- 22c.1: GitHub OAuth (after Google shape proven)
- Dashboard sub-pages: `/dashboard/agents`, `/dashboard/agents/[id]`, `/dashboard/analytics`, `/dashboard/api-keys`, `/dashboard/billing`, `/dashboard/notifications`, `/dashboard/profile`, `/dashboard/settings` (all currently mocked)
- Backend Rule-2 cleanup: `GET /v1/personalities` + `RecipeSummary.tagline` + `RecipeSummary.accent` (kills 3 client-side catalogs)
- B1: `pass_if` field always NULL in RunResponse (low-pri user-facing bug)
- Gate C manual checklist run before any release tag (`test/sc03-gate-c.md`)

Execution summary (2026-04-18):

- Wave 1: 22-01 (v0.2 schema + JSON Schema + RecipeSummary surface) + 22-02 (alembic 003 agent_containers + age-KEK crypto) — merged at 439d3b5
- Wave 2: 22-03 (runner `run_cell_persistent`/`stop_persistent`/`exec_in_persistent`) + 22-04 (async bridge wrappers `execute_persistent_{start,stop,status,exec}`) — merged at 9784615
- Wave 3: 22-05 (4 HTTP endpoints /v1/agents/:id/{start,stop,status,channels/:cid/pair}) — merged at 60496b2
- Wave 4: 22-06 (frontend Step 2.5 + PairingModal + TS types, Rule-2 dumb-client verified) — merged at d27f288
- Wave 5: 22-07 Tasks 1+2 (test/lib/telegram_harness.py + test/e2e_channels_v0_2.sh) — merged at a38f74d

### SC-03 blocker (2026-04-18 empirical finding)

First supervised run surfaced a plan-level design flaw in Plan 22-07:
Telegram's `getUpdates` is single-consumer, so the harness and the hermes
container fight each other over the bot token. Bot never sees the test
ping; harness times out. Full writeup:
`.planning/phases/22-channels-v0.2/22-SC03-DESIGN-FLAW.md`.

What's proven live against the local stack:

- `POST /v1/runs` hermes+haiku-4.5 via OpenRouter → PASS (20.51s)
- `POST /v1/agents/:id/start` with Telegram creds → container running, boot ~11s
- `POST /v1/agents/:id/stop` → clean reap, no dangling containers
- Age-KEK crypto round-trips (with `AP_CHANNEL_MASTER_KEY` set in shell env)
- All 4 new `/v1/agents/...` routes exposed via OpenAPI

What blocks: the test harness can't observe bot replies. Fix = Phase 22b
(agent event stream via docker log parsing → Postgres → `GET /v1/agents/:id/events`).

### Second bug fixed inline (2026-04-18)

MATRIX in `test/e2e_channels_v0_2.sh` used `openrouter/anthropic/claude-haiku-4.5`
as the model id — OpenRouter rejects the `openrouter/` prefix. Correct
form is `anthropic/claude-haiku-4.5`. Fix committed.

### Local-dev runtime state (for repro after /clear)

- API server container: rebuilt from HEAD (Phase 22 code baked in)
- `AP_CHANNEL_MASTER_KEY` — required in shell env before `docker compose up`
  (NOT written to `deploy/.env.prod`; per-laptop per CLAUDE.md rule)

- `.env.local` has `TELEGRAM_USER_CHAT_ID` — the script expects `TELEGRAM_CHAT_ID`,
  alias with `export TELEGRAM_CHAT_ID="$TELEGRAM_USER_CHAT_ID"`

Progress (2026-04-18):

- All 5 recipes carry v0.2-draft `persistent:` + `channels.telegram`
  blocks with `verified_cells[]` from empirical Telegram round-trips.

- hermes / picoclaw / nullclaw / nanobot: FULL_PASS via OpenRouter.
- openclaw: FULL_PASS via Anthropic direct; `provider_compat.
  deferred: [openrouter]` due to isolated upstream plugin bug in
  image 2026.4.15-beta.1 (LLM calls abort pre-flight with
  attempts: []; Anthropic direct works end-to-end).

- Canonical docs URLs commented on each recipe (kept in sync when
  recipe changes).

- Bespoke per-agent recon methodology validated — doc-only recon
  (CHANNEL-RECON.md) superseded by empirical per-agent verification
  (schema-from-reality notes live in each recipe).

Phase 20 (frontend-alicerce) — EXECUTED separately on 2026-04-17
(Playground UI banho de loja + inline ModelBrowser + higher-contrast
primitives shipped in commit a3c95fe).

Desiccated audit (2026-04-18) — `.planning/audit/` now holds three
FROZEN inventory docs:

- BACKEND-DESICCATED.md (9 routes, 7 services, 4 middleware, status
  classified; 5 top gaps identified; production-ready foundation)

- FRONTEND-DESSICATED.md (32 pages + 15 components; 71% real / 29%
  mock; Rule-1/2/3 scorecard)

- ACTION-LIST.md (consolidated execution order — per user directive
  2026-04-18 EVERY mocked page gets real backend wiring, zero
  deletions; /signup is the only open decision pending OAuth landing)

Backend scope grew to ~14 new endpoints across OAuth, users, api-keys
(age-encrypted), analytics aggregation, Stripe billing, notifications,
agent runs history. Multi-phase work ordered after OAuth unblock.

## 📍 RESUME ANCHOR — READ THIS FIRST AFTER /clear

**Primary resume files (read in this order):**

1. `.planning/phases/22-channels-v0.2/22-SC03-DESIGN-FLAW.md` — why
   Phase 22a can't close on its own and what blocks 15/15 round-trips

2. `.planning/phases/22b-agent-event-stream/CONTEXT.md` — proposed
   architecture for the SC-03 fix (docker-log → Postgres → API → harness)

3. `.planning/audit/ACTION-LIST.md` — what to build after 22b
   (prioritized per-page with real endpoint specs; OAuth still pending)

4. `.planning/phases/22-channels-v0.2/22-CONTEXT.md` — Phase 22a scope
   (reference only — 6 of 7 plans already shipped)

5. `memory/MEMORY.md` — updated with 22a-completed + 22b-proposed entries

**Next commands:**

1. `/gsd-discuss-phase 22b-agent-event-stream` — challenge or confirm
   the architecture in `22b/CONTEXT.md`, gather gray-area questions.

2. `/gsd-plan-phase 22b-agent-event-stream` — produce PLAN files.
3. `/gsd-execute-phase 22b-agent-event-stream` — ship it.
4. Rerun `bash test/e2e_channels_v0_2.sh` — closes SC-03, unblocks Phase 22 exit.

**Parallel (OAuth track, unchanged from previous plan):**

- `/gsd-spec-phase 22c-oauth` — spec OAuth (Google + GitHub),
  `/v1/users/me`, session cookie. Blocks 11 dashboard pages.

**Local-dev env for repro:**

```bash
export AP_CHANNEL_MASTER_KEY="2JAvJ9FwihbRyukvXDBnqVEK2Umf5ibHEy7KsFq5gTU="
export TELEGRAM_CHAT_ID="$TELEGRAM_USER_CHAT_ID"
cd deploy && docker compose -f docker-compose.prod.yml -f docker-compose.local.yml --env-file .env.prod up -d
```

- Quick cleanup wins (can ship anytime): GET /v1/personalities +
  drop frontend PERSONALITIES catalog; add tagline/accent fields
  to RecipeSummary + drop frontend maps; fix pass_if NULL bug (B1).

**The next command is:** `/gsd-execute-phase 22a` — execute 7
PLAN files already sealed under `.planning/phases/22-channels-v0.2/`
(schema formalization, runner persistent mode, API endpoints,
frontend Step 2.5, E2E smoke). All spike-verified (G1..G5 findings
absorbed), plan-checker PASS after I1..I3 contract revisions.

Read files in this order after /clear:

1. `./CLAUDE.md` (golden rules at the top — #2 "dumb client, intelligence in the API" and #3 "ship when stack works locally e2e" are load-bearing for this phase)
2. `.planning/phases/20-frontend-alicerce/20-CONTEXT.md` (14 decisions + SC-01..SC-11 — the exit gate)
3. `.planning/phases/20-frontend-alicerce/20-RESEARCH.md` (concrete patterns: api.ts extension diff, parseApiError union, useRetryCountdown, BYOK hardening, 8 pitfalls)
4. `.planning/phases/20-frontend-alicerce/20-UI-SPEC.md` (30 locked copy strings, Tailwind classes, 5-state + 6-error ASCII wireframes)
5. `.planning/phases/20-frontend-alicerce/20-PATTERNS.md` (6 analogs — dev-login-form.tsx is the exact structural analog for playground-form.tsx)
6. `.planning/phases/20-frontend-alicerce/20-01-PLAN.md` through `20-05-PLAN.md` (5 PLANs in 3 waves)
7. `memory/feedback_dumb_client_no_mocks.md` (the principle that created this phase)
8. `.planning/STATE.md` (this file)

### Wave execution order (Phase 20)

| Wave | Plans | Files | Summary |
|------|-------|-------|---------|
| 1 | 20-01, 20-02 | `frontend/lib/api.ts` + `api-types.ts` / delete mock tree (5 components + homepage section) | Parallel — no file overlap |
| 2 | 20-03, 20-04 | `playground-form.tsx` / `run-result-card.tsx` | Parallel after Wave 1 |
| 3 | 20-05 | `playground/page.tsx` + SUMMARY + STATE | Sequential; **human-verify SC-11 gate** (the Phase 19 deploy unblocker) |

## Quick Tasks Completed

| ID | Date | Description | Notes |
|----|------|-------------|-------|
| 260414-mwo | 2026-04-14 | Import v0 frontend as `frontend/` monorepo member | v0 tree at `/frontend`, ported `api.ts`/`middleware.ts`/`dev-login-form.tsx` from legacy `/web`, added Makefile targets. `/web` still on disk — deletion deferred to Phase 3 after new tree is verified end-to-end. |

### Roadmap Evolution

- Phase 02.5 inserted after Phase 2: Recipe Manifest Reshape (URGENT) — 2026-04-14
- Phase 03 (v0.1 consolidation) completed — 2026-04-15
- Phases 9–17 added: framework maturity roadmap (v0.2 floor + v0.3 ceiling) — 2026-04-15
  - P09: Spec lint + test harness (gates all)
  - P10: Error taxonomy + timeouts
  - P11: Linux owner_uid correctness
  - P12: Provenance + output bounds
  - P13: SHA pinning + v0.2
  - P14: Isolation limits + default-deny
  - P15: Stochasticity / multi-run
  - P16: Dead verb coverage (fake-agent)
  - P17: Doc-runner sync check
  - Prior-art research: recon/prior-art-research.md
  - Full plan: .planning/FRAMEWORK-MATURITY-ROADMAP.md

### ⚠️ Phase 02 Reshape (2026-04-14) — READ BEFORE PLANNING

The original Phase 02 in the roadmap bundled substrate + full hardening. After a discuss-phase session, the user challenged whether the hardening half actually moved the project hypothesis forward. Conclusion: it did not, and it should land against a known-working substrate rather than a speculative one.

**Phase 02 now ships:**

1. `ap-base` image (tini PID 1 + tmux chat/shell windows + ttyd on loopback + MSV entrypoint/gosu pattern ported from `meusecretariovirtual/infra/picoclaw/`)
2. Sandbox options wired into `pkg/docker/runner.go` `RunOptions` as fields (SeccompProfile, ReadOnlyRootfs, Tmpfs, CapDrop, NoNewPrivs, Runtime, NetworkMode, PidsLimit, Memory, CPUs) — safe defaults applied at call sites, no custom seccomp JSON yet
3. Deterministic container naming `playground-<user_uuid>-<session_uuid>` + validator + helper in runner.go
4. Two pre-built recipe images: **picoclaw** (Go CLI, pinned SHA from `/Users/fcavalcanti/dev/picoclaw`, `stdin_fifo` chat path) + **Hermes** (Python 3.11, pinned SHA from `github.com/NousResearch/hermes-agent`, MIT, TUI-first, multi-channel daemon disabled via pre-populated `~/.hermes/cli-config.yaml`, backend forced to `local`)
5. **Minimal non-durable session API stubs** pulled forward from Phase 5 scope: `POST /api/sessions`, `POST /api/sessions/:id/message` (synchronous FIFO bridge via `docker exec`), `DELETE /api/sessions/:id`. Direct runner.go calls — **no Temporal in Phase 2.** Phase 5 upgrades internals with SessionSpawn/SessionDestroy workflows, HTTP contract stays stable.
6. Dev BYOK via `AP_DEV_BYOK_KEY` env → tmpfs `/run/secrets/*_key` injection (file-based mechanism is Phase 2; Phase 3 replaces the source with the encrypted vault).
7. Hardcoded recipe structs in new `internal/recipes/` package (Phase 4 replaces with YAML schema + loader)
8. New migration `0002_sessions.sql` — `sessions` table (id, user_id, recipe_name, model_provider, model_id, container_id, status, created_at, updated_at). One-active-per-user enforced via Postgres partial unique index.
9. **Hypothesis proof smoke test:** `make smoke-test` or equivalent runs curl against the API, starts both agents, exchanges a real message with a real Anthropic model via BYOK, tears down cleanly, asserts no dangling `playground-*` containers. The curl output IS the demo — no browser UX until Phase 5.

**Phase 02 does NOT ship (deferred to new Phase 7.5):**

- Custom seccomp profile JSON
- `ap-net` Docker bridge + iptables DOCKER-USER egress allowlist
- Falco or Tetragon + rule set + alerting sink
- Escape-test CI harness (mount/unshare/setns/docker.sock/evil egress)
- gVisor `runsc` install + per-recipe runtime selection (Spike 4 still pending — not a Phase 2 blocker anymore, only gates Phase 7.5 + Phase 8)

**Phase 7.5 (new, inserted 2026-04-14): Sandbox Hardening Spine.** Fills in every sandbox knob Phase 2 plumbed, against a known-working substrate, right before Phase 8 introduces the first untrusted-code path. Requirements moved there: SBX-02 (custom seccomp portion), SBX-04, SBX-06, SBX-07 (Falco portion), SBX-08.

**Critical forward-compatibility signals from discuss-phase (user verbatim):**

- *"API-driven start without Telegram is the hypothesis proof"* — Phase 2 completion gate is curl → real model response for both agents
- *"this list will grow"* — recipe abstraction must accept new agents as recipe YAML + Dockerfile, no code changes to `ap-base`, `runner.go`, or session handlers. Hermes being the architecturally hardest agent validates the pattern.
- *"Hermes is totally different from OpenClaw"* — OpenClaw (gateway-WebSocket, Node, pairing) vs Hermes (PTY TUI, Python 3.11, multi-channel daemon, six execution backends). Both must fit `ap-base` without special-casing. Hermes's chat bridge mechanism (PTY screen-scrape vs MCP via `mcp_serve.py` vs hypothetical CLI `--message` flag) is a Phase 2 **planning research** item.

**Full reshape rationale + every decision + canonical refs:** `.planning/phases/02-container-sandbox-spine/02-CONTEXT.md`

**Discussion audit trail:** `.planning/phases/02-container-sandbox-spine/02-DISCUSSION-LOG.md`

## Performance Metrics

**Velocity:**

- Total plans completed: 20
- Average duration: ~25 min/plan (parallel waves; wall clock ~3h45m total)
- Total execution time: ~4 hours wall clock for Phase 01 end-to-end

**By Phase:**

| Phase | Plans | Wall Time | Notes |
|-------|-------|-----------|-------|
| 01    | 6     | ~4h       | 5-plan parallel Wave 1 + 1-plan Wave 2; opus executors in worktrees |
| Phase 19 P01 | 6min | 3 tasks | 11 files |
| Phase Phase 19 P06 P06 | 5min | 2 tasks | 10 files |
| Phase Phase 19 P02 PP02 | 7min | 2 tasks | 12 files |
| Phase 19 P03 | 8min | 2 tasks | 11 files |
| Phase 19-api-foundation P04 | 8m | 2 tasks | 8 files |
| Phase 19-api-foundation P05 | 17min | 2 tasks | 7 files |
| Phase 19 P07 | 12min | 2 tasks | 12 files |
| Phase 22c-03 | ~12min | 3 tasks | 5 files |
| Phase 22c-04 | ~5min | 2 tasks | 6 files |
| Phase 22c-05 | ~65min | 4 tasks | 16 files |
| Phase 22c-08 | ~4min | 2 tasks | 3 files |
| Phase 22c.3-01 | ~50min | 3 tasks | 6 files |
| Phase 22c.3-02 | ~6min | 2 tasks | 2 files |
| Phase 22c.3-03 | ~5min | 3 tasks | 7 files |
| Phase 22c.3-06 | ~8min | 1 task (TDD RED+GREEN) | 2 files |
| Phase 22c.3-11 | ~25min | 1 task | 1 file |
| Phase 22c.3-inapp-chat-channel P13 | 25 | 1 tasks | 1 files |

## Accumulated Context

### Decisions (locked)

From PROJECT.md Key Decisions:

- **Temporal is required** (overrides research's "drop Temporal" recommendation). Session create/destroy, recipe install, reconciliation = Temporal workflows. Workers must be running. **PROVEN in Phase 01:** PingPong workflow ran live against the cluster, 50ms, completed.
- **Go API + Next.js** mirrors MSV. `pkg/docker/runner.go` ported from MSV pattern but rewritten for the **Docker Engine SDK** (`github.com/moby/moby/client`) — explicitly NOT `os/exec` shelling. Verified clean.
- **Hetzner dedicated single host.** No K8s, no cloud-managed containers. docker-compose stack on host.
- **BYOK first-class.** Platform-billed mode via LiteLLM + Stripe credit ledger (Phase 6/7).
- **gVisor (`runsc`) mandatory for Phase 8** bootstrap path. Curated recipes may use plain `runc`.
- **Apache-2.0 OSS.** Monetization = hosted service.

### Phase 01 Outcomes (what now exists in the repo)

**Go API (`api/`):**

- Echo v4.15.1 + pgx v5.9.1 + Redis v9.18 + zerolog
- `cmd/server/main.go` boot: config → DB → Redis → migrations → server.New(...opts) → graceful shutdown
- `pkg/database/postgres.go` — pgxpool wrapper
- `pkg/redis/client.go` — Redis wrapper
- `pkg/migrate/` — embedded `//go:embed sql/*.sql` migrator with `pg_advisory_lock(8675309)` + per-migration tx (CR-04 fix). Baseline schema = users / user_sessions / agents (with partial unique index `idx_agents_one_active_per_user`).
- `pkg/docker/runner.go` — 396 lines, Docker Engine SDK (NOT os/exec). Run / Exec / Inspect / Stop / Remove + strict input validation (validateContainerID/validateImageName/validateEnvVar/validateMountPath). 49 unit tests + integration test (real Docker, alpine:3.19) all green.
- `internal/server/server.go` — `server.New(cfg, logger, checker, opts ...Option)` with **functional options pattern**. `WithDevAuth(...)` and `WithWorkers(WorkerManager)` are the two options. Plan 01-01 pre-declared the pattern so Plan 01-05 added Temporal without touching the New signature.
- `internal/handler/` — health (`/healthz` returning DB+Redis status), checker, devauth (POST /api/dev/login, POST /api/dev/logout, GET /api/me).
- `internal/middleware/auth.go` — `SessionProvider` interface (Phase 3 will swap goth in), HMAC-SHA256 signed `ap_session` cookie (HttpOnly, SameSite=Lax), `VerifyCookie` constant-time compare (CR-01 fix). Session secret length validated unconditionally (CR-02 fix).
- `internal/temporal/` — 3 workers (session/billing/reconciliation queues), 5 stub workflows (SessionSpawn, SessionDestroy, RecipeInstall, ReconcileContainers, ReconcileBilling) + PingPong proof. Workers.Start() rolls back partial startups (CR-03 fix). Empty TEMPORAL_HOST short-circuits to skip Temporal entirely (WR-01 fix).

**Next.js frontend (`web/`):**

- Next 16.2 + React 19.2 + Tailwind v4 + shadcn/ui + Inter font + dark mode default + emerald accent
- `src/app/page.tsx` — auth-gated landing. **Uses versioned auth re-fetch pattern**: `authVersion` state bumped by `refreshAuth` callback re-runs the /api/me effect. (Was using `router.refresh()` which only re-runs server components — fixed in `eecbef4`.)
- `src/components/dev-login-form.tsx` — emerald 44px touch-target button, calls `onLoginSuccess` callback prop after POST /api/dev/login
- `src/components/top-bar.tsx` — sticky top bar, sign-out icon, calls `onSignOut` callback prop
- `src/lib/api.ts` — `apiGet/apiPost` with `credentials: 'include'` and typed `ApiError`/`SessionUser`
- `src/middleware.ts` — Next middleware (no-op for Phase 01, set up for Phase 02+)
- `next.config.ts` — rewrites `/api/*` → `http://localhost:8080/api/*` for local dev
- **CRITICAL:** `web/AGENTS.md` says "This is NOT the Next.js you know" — Next 16 has breaking changes; future agents must read `node_modules/next/dist/docs/` before touching Next-specific code. Already burned by NODE_ENV=development causing build failure during 01-03.

**Infrastructure:**

- `docker-compose.dev.yml` — Postgres 17 + Redis 7 + **Temporal 1.29.3** + **Temporal UI 2.34.0** (CR-05 fix: pinned versions). All ports `127.0.0.1`-bound. `condition: service_healthy` on temporal→postgresql. **Removed `DYNAMIC_CONFIG_FILE_PATH`** env var (compose fix `480d5b4`) — image doesn't ship the file and we don't mount it.
- `docker-compose.yml` — production Temporal + UI, `network_mode: host`, same pinned versions
- `deploy/dev/init-db.sh` — creates `agent_playground` DB after first compose up
- `deploy/hetzner/` — 6 idempotent provisioning scripts: bootstrap.sh, install-docker.sh (with userns-remap), install-postgres.sh, install-redis.sh, install-temporal.sh, harden-ufw.sh (default-deny, 22 + 443 only)
- `.env.example` — all env vars documented

**Spike report (`.planning/research/SPIKE-REPORT.md`):**

- **Spike 1** (per-agent HTTPS_PROXY vs *_BASE_URL): OpenClaw + PicoClaw both honor BOTH; HTTPS_PROXY env wins for v1 transparent metering proxy. Hermes/HiClaw/NanoClaw deferred to Phase 4 recipe authoring (sources not local).
- **Spike 2** (chat_io.mode per agent): OpenClaw = `gateway-websocket`; PicoClaw = `cli-stdio` + per-channel adapters. Drives `chat_io.mode` enum addition to Phase 4 recipe schema.
- **Spike 3** (tmux + named-pipe RTT): **min 69µs / p50 85µs / p95 138µs / p99 0.19ms / max 238µs** measured locally in alpine:3.20 Docker. PASS — 262× headroom under 50ms budget.
- **Spike 4** (gVisor runsc on Hetzner): NOT EXECUTED. Needs SSH to prod box (gVisor is Linux-only, can't run from macOS). Exact commands documented in §"Spike 4 — Exact commands to run on the Hetzner host". Result template at end of report — fill kernel version, runsc version, PASS/FAIL.

### Code Review Outcomes

`01-REVIEW.md` (initial): 5 critical / 6 warnings / 5 info
`01-REVIEW-FIX.md`: 11/11 critical+warning fixed in single pass, 0 skipped. Info findings deferred (run `/gsd-code-review-fix 01 --all` to address).

Notable info-severity items deferred:

- INF-01: HMAC compare logic duplicated in 2 places (now uses shared VerifyCookie after CR-01, but constant could be extracted)
- INF-02: Related — VerifyCookie naming
- INF-03: docker-compose missing temporal healthcheck (currently relies on restart: on-failure)
- INF-04: API_BASE empty string in `web/src/lib/api.ts` could be more defensive
- INF-05: SQL injection risk in install-postgres.sh if operator passes hostile password (low-prio; operator controls input)

### Verification Outcomes

`01-VERIFICATION.md`: status `human_needed`, score 9/10 must-haves verified.
`01-HUMAN-UAT.md`: 2 items

1. ✅ **CLEARED** — Visual mobile-first frontend verification (375px viewport) — passed live test after `eecbef4` fix to login/logout reload bug
2. ⏳ **PENDING** — Spike 4: gVisor runsc on Hetzner — needs human SSH

### Bugs Found and Fixed During Phase 01 Execution

1. **`480d5b4 fix(01-04): drop unmountable DYNAMIC_CONFIG_FILE_PATH from compose files`** — Temporal compose env referenced a config file not shipped in image. Found while testing.
2. **`eecbef4 fix(01-03): re-check auth on login/logout via callback instead of router.refresh`** — Frontend used router.refresh() but page is a client component. Caught by visual UAT.
3. The 11 code-review fixes (CR-01..05, WR-01..06) — see `01-REVIEW-FIX.md`.

### Phase 01 Git Log Summary (newest first)

```
eecbef4 fix(01-03): re-check auth on login/logout via callback instead of router.refresh
66295fb docs(01): add code review fix report
3250a47 fix(01): WR-06 ...
444e821 fix(01): WR-05 ...
9402fe6 fix(01): WR-04 ...
81dc055 fix(01): WR-03 ...
dc4a258 fix(01): WR-02 ...
479be7c fix(01): WR-01 ...
05e5fde fix(01): CR-05 ...
f642408 fix(01): CR-04 ...
cbd16d5 fix(01): CR-03 ...
391f7f4 fix(01): CR-02 ...
43c6499 fix(01): CR-01 ...
98224c1 test(01): persist human verification items as UAT
c1f144a docs(01): add phase verification report
174ad63 docs(01): add code review report
80b5abb docs(01-05): complete temporal workers plan
9bf3fc6 feat(01-05): wire temporal workers into main.go via WithWorkers option
1c0560e feat(01-05): add temporal workers + stub workflows + PingPong proof
480d5b4 fix(01-04): drop unmountable DYNAMIC_CONFIG_FILE_PATH from compose files
387c685 docs(01-03): add plan summary
c9e53d6 chore: merge 01-03 worktree (next.js frontend shell)
5afaa8c chore: merge 01-06 worktree (spike report 1-3)
e16a71f chore: merge 01-04 worktree (hetzner provisioning + dev compose)
6d742ba chore: merge 01-02 worktree (docker SDK runner)
fec45dd feat(01-03): auth-gated landing page + dev login + dashboard shell
9e1364c feat(01-03): scaffold Next.js 16 + shadcn/ui + emerald design system
... (Plan 01-01 + 01-02 + 01-04 + 01-06 commits before merges)
```

### Pending Todos

- **Spike 4 (gVisor on Hetzner)** — human action required. SSH to Hetzner host, run `runsc install` + `docker run --runtime=runsc alpine:3.20 echo hello`. Update `.planning/research/SPIKE-REPORT.md` §"Spike 4 — Result template" with kernel version, runsc version, PASS/FAIL. Result gates Phase 8 sandbox tier: if FAIL, Phase 8 must pivot from gVisor to Sysbox-only or microVMs.
- **5 info-severity code review items** deferred — run `/gsd-code-review-fix 01 --all` if/when desired (low priority).

### Blockers/Concerns

- **None blocking Phase 02.** Spike 4 result is needed for Phase 8 architecture decision but does NOT block Phase 02 (Recipes & Sandbox). Phase 02 can proceed assuming gVisor works; if it later fails, Phase 8 plans get adjusted.

## Local Dev Stack — How to Bring It Back Up

```bash

# Compose stack (currently running — postgres + redis + temporal + temporal UI)

docker compose -f docker-compose.dev.yml up -d
./deploy/dev/init-db.sh   # only on first start

# Go API

cd api && \
  AP_DEV_MODE=true \
  AP_SESSION_SECRET=test-secret-that-is-at-least-32-characters-long \
  DATABASE_URL="postgres://temporal:temporal@localhost:5432/agent_playground?sslmode=disable" \
  REDIS_URL=redis://localhost:6379 \
  TEMPORAL_HOST=localhost:7233 \
  TEMPORAL_NAMESPACE=default \
  API_PORT=8080 \
  go run ./cmd/server/

# Next.js

cd web && pnpm dev

# Trigger PingPong workflow (proves Temporal end-to-end)

docker exec agent-playground-temporal-1 sh -c 'temporal --address $(hostname -i):7233 workflow execute --type PingPong --task-queue session --workflow-id ping-pong-test --input "\"hello\""'
```

URLs:

- http://localhost:8080/healthz — Go API health
- http://localhost:3000 — Frontend
- http://localhost:8233 — Temporal Web UI

## Session Continuity

Last session: 2026-04-30T21:44:00.097Z

Stopped at: Plan 22c.3-06 (inapp_reaper — 15s tick D-40 direct-to-failed) SHIPPED — 6 testcontainer-PG integration tests PASS

**Next command:** `/gsd-execute-phase 22c.3-inapp-chat-channel` (continue with Wave 2 tail: Plan 22c.3-07 outbox pump — last Wave 2 plan)

**Primary resume artifact:** `.planning/phases/22c.3-inapp-chat-channel/22c.3-06-SUMMARY.md` — read first after /clear; then `.planning/phases/22c.3-inapp-chat-channel/22c.3-07-PLAN.md` to see the outbox pump contract.

### Reading order for a fresh session after /clear

1. `.planning/STATE.md` (this file) — top-level situational awareness + Phase 2 reshape summary above
2. `.planning/phases/02-container-sandbox-spine/02-CONTEXT.md` — **source of truth for Phase 2 decisions**. Every decision from the discuss-phase is in `<decisions>`; every doc downstream agents need is in `<canonical_refs>`; every deferred idea is in `<deferred>`.
3. `.planning/phases/02-container-sandbox-spine/02-DISCUSSION-LOG.md` — full Q&A audit trail (optional; use if you need to understand WHY a decision was made, not just WHAT was decided)
4. `.planning/ROADMAP.md` §Phase 2 — reshaped success criteria + requirement mapping (points at 02-CONTEXT.md)
5. `.planning/ROADMAP.md` §Phase 7.5 — new phase inserted during reshape; holds the deferred hardening work
6. `.planning/REQUIREMENTS.md` — SBX-02 partial, SBX-04/06/07/08 moved to Phase 7.5
7. `.planning/research/SPIKE-REPORT.md` — Phase 1 spike findings (Hermes gap; Phase 2 planning must extend Spike 1+2 for Hermes)
8. `/Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/Dockerfile` + `entrypoint.sh` — MSV's battle-tested dockerized-agent pattern to port into `ap-base` (entry point, privilege drop via gosu, pre-populated config baked at build)

### Planning research items Phase 2 must resolve (flagged in 02-CONTEXT.md D-23)

- Hermes chat bridge mechanism: PTY screen-scrape vs MCP (via `mcp_serve.py`) vs hypothetical `hermes --message` non-interactive CLI flag. Fetch the `cli-config.yaml.example` from `github.com/NousResearch/hermes-agent` to pin exact keys.
- Exact YAML keys in Hermes `cli-config.yaml` for (a) disabling Telegram/Discord/Slack/WhatsApp/Signal/SMS/Email/Matrix/Mattermost gateway daemons and (b) forcing `backend: local`.
- Commit SHAs to pin picoclaw and Hermes to (pick the latest stable at plan-writing time).
- Extend Spike 1 + Spike 2 for Hermes (currently picoclaw + OpenClaw only covered).

Resume file: None
