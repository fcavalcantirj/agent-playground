# Phase 23: Backend Mobile API — Context

**Gathered:** 2026-05-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Backend ships everything mobile needs to demo Phase 25's flow against a local
api_server: harden the existing chat-send endpoint, add the missing models
proxy + agent-status field, ship 2 mobile-OAuth credential exchange endpoints,
and reuse 100% of the in-app chat substrate that Phase 22c.3/22c.3.1 already
built. **No new tables, no new chat endpoint, no dev-mode auth shim.** Tests
run against testcontainers Postgres + real Docker (same harness as Phase
22c.3.1's `make e2e-inapp-docker`).

The scout discovery that re-shaped this phase: **OAuth (Phase 22c-oauth-google)
HAS shipped** (all 9 plans complete: SessionMiddleware, require_user, ap_session
cookie, browser flow). **`inapp_messages` table HAS shipped** (migration 007
with `(id, agent_id→agent_instances, user_id, content, status, bot_response,
created_at, completed_at)`). **`POST /v1/agents/:id/messages` HAS shipped**
(Phase 22c.3-08, fast-ack into outbox + dispatcher + SSE). **`inapp_dispatcher`
HAS shipped** with 3 contract adapters (openai_compat / a2a_jsonrpc /
zeroclaw_native), readiness gate, transactional outbox via `agent_events`,
reaper for stuck rows. The mobile-mvp-decisions.md note was authored on stale
assumptions ("planned-not-executed", "~80 LOC proxy", "new messages table");
this CONTEXT.md is the corrected source of truth.

The five new mechanisms Phase 23 actually delivers:
1. **Idempotency-Key required** on existing `POST /v1/agents/:id/messages` (~3 LOC).
2. **`status` + `last_activity` fields** on existing `GET /v1/agents` (LATERAL JOIN extension).
3. **`GET /v1/models`** OpenRouter passthrough proxy with 15min in-process cache.
4. **`POST /v1/auth/{google,github}/mobile`** — 2 new credential-exchange endpoints for native Flutter OAuth SDK tokens.
5. **GZipMiddleware** for response compression (with verified SSE compatibility).

Out of phase: Flutter app code (Phase 24/25), Hetzner deploy (separate effort),
streaming chat (deferred seed), token-level streaming.

</domain>

<decisions>
## Implementation Decisions

### Persistence model

- **D-01:** **Reuse `inapp_messages` as the single chat-history source.** Zero new tables, zero new migrations. Existing schema (id, agent_id→agent_instances, user_id, content, status, bot_response, created_at, completed_at) covers mobile's needs. Spec API-06 (new `messages` table) is **DROPPED** — see D-32 for the REQUIREMENTS.md amendment.
- **D-02:** **URL `:id` = `agent_instances.id`** for ALL Phase 23 endpoints. Matches Phase 22c.3 inapp contract verbatim. inapp_messages.agent_id FK already targets agent_instances.id. No translation layer.
- **D-03:** **GET /messages returns `status IN ('done','failed')`.** `done` rows emit `(role:user from content, role:assistant from bot_response)` two events per row. `failed` rows emit `(role:user from content, role:assistant content="⚠️ delivery failed: <last_error>", kind:'error')` so the UI can render distinctly. In-flight (`pending`/`forwarded`) NOT shown. Mobile sees ghost-failure feedback on bot timeouts.
- **D-04:** **GET /messages — ORDER BY created_at ASC, default limit=200, max=1000.** Per REQUIREMENTS.md API-02 verbatim. Pagination is OUT of MVP per locked decisions.

### Chat send + reply transport

- **D-05:** **Backend completes bot call regardless of client disconnect.** Source of truth is the DB. Mobile re-fetches via `GET /messages` on reconnect; backend never aborts a bot call because TCP went away. No client-disconnect-cancellation path.
- **D-06:** **Container not running → fail fast.** UI is responsible for not surfacing chat input on stopped agents. Reuse dispatcher's `container_not_ready` failure mode (D-37/D-38 of Phase 22c.3 — already wired).
- **D-07:** **Per-agent serialization across channels.** One in-flight bot request at a time per agent. Telegram + mobile + web → one queue per agent. The dispatcher already serializes (single tick, FOR UPDATE SKIP LOCKED, sequential per agent). Inheriting this is free if we go through the dispatcher path.
- **D-08:** **Cross-channel history alignment.** Web and mobile chat history must be byte-identical. The new sends MUST emit `agent_events(kind=inapp_outbound, published=false)` so existing SSE listeners on `agent:inapp:<agent_id>` see them. Going through the dispatcher path makes this automatic.
- **D-09:** **`Idempotency-Key` REQUIRED on `POST /v1/agents/:id/messages`.** Missing header → 400 with Stripe-shape error envelope (existing `make_error_envelope()`). Mobile generates a UUID per Send press. `IdempotencyMiddleware` already lists this path as eligible (line 4 of middleware) — handler-level enforcement of header presence is the only new code (~3 LOC). Web frontend's chat page is currently mocked (see deferred ideas) so zero callers break.
- **D-12 SUPERSEDED by D-14:** No new `/chat` endpoint. Pure fast-ack (202 + message_id) via the existing endpoint. Client polls via SSE, not blocking HTTP.
- **D-13:** **Mobile receives replies via SSE on existing `GET /v1/agents/:id/messages/stream`** (Phase 22c.3-08). Backend infra reused 100% — Redis pub/sub on `agent:inapp:<agent_instance_id>`, fed by outbox pump from `agent_events` rows. Flutter side uses `flutter_client_sse` package + Last-Event-ID resume on reconnect.
- **D-14:** **Mobile uses existing `POST /v1/agents/:id/messages` (body `{content: str}`) AS-IS.** Spec API-01's `/chat` URL naming is dropped (see D-32 for REQUIREMENTS.md amendment). Flutter Dart matches the existing wire shape verbatim — no body field aliasing, no alias endpoint, zero duplication.

### Auth (mobile OAuth)

- **D-15:** **No dev-mode auth shim.** Mobile uses real OAuth via native Flutter SDKs (`google_sign_in` for Google — official Flutter pkg, native iOS/Android sign-in UI; `flutter_appauth` for GitHub — AppAuth standard, system browser + PKCE + custom URI scheme). Google explicitly blocks WebView OAuth for new apps (security policy as of 2021), so webview is an anti-pattern.
- **D-16:** **Phase 23 ships 2 mobile-credential-exchange endpoints:**
  - `POST /v1/auth/google/mobile` — body `{id_token: string}` → verify JWT against Google JWKS (`https://www.googleapis.com/oauth2/v3/certs`) → audience claim must match one of the configured mobile client IDs (D-23) → existing `upsert_user(provider='google', sub=<google_sub>, email, display_name, avatar_url)` → existing `mint_session()` → return `{session_id, expires_at, user: <SessionUserResponse shape>}`.
  - `POST /v1/auth/github/mobile` — body `{access_token: string}` → call GitHub `/user` (and `/user/emails` fallback per D-22c-OAUTH-03) → existing `upsert_user(provider='github', ...)` → existing `mint_session()` → same response shape as Google variant.
  - Reuses 100% of Phase 22c-03's `upsert_user()` + `mint_session()` helpers. New code is purely the credential-verification layer at the boundary.
- **D-17:** **Mobile sends `Cookie: ap_session=<uuid>` header directly.** No middleware changes. `ApSessionMiddleware` reads the existing cookie either way (web cookie jar OR mobile-explicit header — same wire shape). `Authorization: Bearer <openrouter-byok>` continues to mean BYOK on `/runs` and `/start`. Sessions and BYOK occupy different transport slots, zero conflict.
- **D-23:** **New env var `GOOGLE_OAUTH_MOBILE_CLIENT_IDS`** (comma-separated). Google Cloud Console issues separate client IDs per platform (Android, iOS) — both are different from the existing web `GOOGLE_OAUTH_CLIENT_ID`. The mobile JWT verifier accepts tokens whose `aud` claim matches any of the configured mobile IDs. `deploy/.env.dev.example` gets the new var with placeholder. Cloud Console mobile-client registration is a deploy runbook task.
- **D-24:** **GitHub reuses existing OAuth app.** GitHub doesn't distinguish mobile vs web apps. Add the mobile redirect URI scheme (e.g. `solvr://oauth/github` — final scheme settled in Phase 24's spec) to the existing GitHub OAuth app's whitelist. No new env var.
- **D-30:** **Mobile OAuth test scaffolding** at `tests/auth/test_oauth_mobile.py`. respx mocks: Google JWKS, GitHub `/user` + `/user/emails`. Coverage matrix per provider:
  - happy path (valid token → 200 with session_id + user data)
  - invalid token (signature fail or expired → 401)
  - audience mismatch (Google JWT for wrong client_id → 401)
  - missing required claims (no `sub` or no `email` → 401)
  - private GitHub email + /user/emails fallback verified
  Reuse 22c-09's `respx_oauth_providers` fixture pattern + TRUNCATE CASCADE harness (8 tables incl. sessions+users). Add `authenticated_mobile_session` fixture mirroring `authenticated_cookie`.

### Agent list / dashboard

- **D-10:** **Extend existing `GET /v1/agents`** to include `status` field derived from `agent_containers.container_status` healthcheck (the runner_bridge already updates this column). LATERAL JOIN extension on `list_agents()`. No new endpoint.
- **D-11:** **Container resolution policy:** `WHERE agent_instance_id=:id AND stopped_at IS NULL ORDER BY created_at DESC LIMIT 1`. Returns the single live container or zero rows. Zero rows → fail-fast `container_not_ready` per D-06.
- **D-22:** **Deploy flow uses existing endpoints.** `POST /v1/runs` (creates the agent_instances row via `(user_id, name)` UPSERT + smoke-tests recipe+model+BYOK) → `POST /v1/agents/:id/start` (spawns persistent container with channel config). Web playground-form already uses exactly this 2-call flow. Mobile reuses identically. **Zero new backend endpoints for deploy.**
- **D-27:** **`last_activity` field.** Compute in the same LATERAL extension as D-10: `last_activity = MAX(ai.last_run_at, MAX(im.created_at) WHERE im.agent_id=ai.id)`. NULL when user has never run nor messaged. Existing `last_run_at` field stays for backward compat with Phase 22c-09 callers; `last_activity` is the new mobile-friendly field.
- **D-28:** **Mobile Phase 25 deploys with `{channel: 'inapp', channel_inputs: {}}`.** Backend `POST /v1/agents/:id/start` contract unchanged (it accepts all channels). Constraint at the planner level so executor doesn't auto-add Telegram/other-channel UI to Phase 25. The Telegram/web/etc paths stay accessible via the existing web playground.
- **D-29:** **Backend keeps `(user_id, name)` UPSERT semantics.** Mobile UI (Phase 25) does pre-flight `GET /v1/agents` and surfaces a "name already used by [recipe/model] — re-deploy or rename?" confirmation dialog before submitting Deploy. Backend behavior unchanged.

### Models proxy (`GET /v1/models`)

- **D-18:** **In-process dict cache, 15min TTL.** `app.state.models_cache = {fetched_at: datetime, payload: bytes}`. First request fetches OpenRouter, caches in process memory. **Stale-while-revalidate** on fetch failure (serve stale + log error). No new migration, no DB write, no Redis dependency. Multi-replica = each replica fetches once per TTL window (~one fetch / 15min / replica = trivial). 15min TTL balances OpenRouter quota friendliness and "new model just dropped" UX.
- **D-19:** **Backend calls `https://openrouter.ai/api/v1/models` with NO Authorization header.** That endpoint is public on OpenRouter. The "platform key vs per-user key" sub-decision is moot — BYOK only matters for chat-completions calls (already correctly user-side in `playground-form.tsx`).
- **D-20:** **Passthrough response.** Backend returns OpenRouter's payload byte-for-byte. No filtering, no stripping, no field renames. Per dumb-client rule the client filters by capability/price/etc.
- **D-21:** **Web frontend migration in scope.** `frontend/components/playground-form.tsx:169` updates from `fetch("https://openrouter.ai/api/v1/models")` to `apiGet("/v1/models")`. ~5 LOC change. Closes Golden Rule #2 violation in the same phase that creates the substrate.
- **D-25:** **Add Starlette `GZipMiddleware(minimum_size=1024)` to `main.py`.** Compresses /v1/models response from ~200KB → ~50KB. 2-LOC change. Trivial mobile bandwidth win on every cold-cache load.

### UX / lifecycle

- **D-26:** **Session expiry → 401 → mobile routes to OAuth.** No refresh tokens. No retry-on-401 logic. Locked here so executor doesn't invent retry/refresh layers.
- **D-31:** **Wave 0 spike — GZip × SSE compatibility.** Phase 23 plan MUST include `tests/spikes/test_gzip_sse_compat.py` BEFORE the plan seals. GZipMiddleware can break SSE if it buffers `text/event-stream` chunks. Spike: configure GZipMiddleware (`minimum_size=1024`), fire SSE through `GET /v1/agents/:id/messages/stream`, assert events arrive un-buffered (chunks delivered as emitted, not batched). If GZip buffers SSE, switch to a content-type-exclude config that skips `text/event-stream`. Plan does not seal until spike PASSES — Golden Rule #5.
- **D-32:** **REQUIREMENTS.md amendments are part of Phase 23's commit chain:**
  - **API-01** rewritten to: "Backend hardens existing `POST /v1/agents/:id/messages` to require an `Idempotency-Key` header (400 if missing). Body unchanged: `{content: string}`. Response unchanged: 202 `{message_id, status, queued_at}`. Idempotent retry replays cached response via existing IdempotencyMiddleware."
  - **API-05** rewritten to: "Backend exposes `POST /v1/auth/google/mobile` and `POST /v1/auth/github/mobile` accepting native-SDK credentials, verifying server-side, and minting `sessions` rows that mobile sends back as `Cookie: ap_session=<uuid>` header. ApSessionMiddleware unchanged. No dev-mode shim."
  - **API-06** **DROPPED.** Add note: "Replaced by reuse of existing `inapp_messages` table per Phase 23 D-01."
  - **API-04** unchanged — existing wording covers /v1/models proxy.
  - Traceability table updated.
  - **Without these amendments the verifier will fail the phase-exit gate** (verifier checks REQUIREMENTS.md against shipped code).
- **D-33:** **Cookie-header for sessions stays (D-17).** Cleaner long-term answer would be `Authorization: Bearer <session>` for mobile + BYOK relocated to `X-OpenRouter-Key` header or request body — but that's a backwards-incompatible change to /runs+/start that web also uses. Captured in deferred ideas as a post-MVP cleanup phase.
- **D-34:** **Mobile cold-start auth check uses existing `GET /v1/users/me`.** No new endpoint. Mobile flow: app open → call /v1/users/me with stored cookie → 200 = render dashboard, 401 = clear local session + route to OAuth. Captured here so Phase 24 spec doesn't invent a new "validate-session" endpoint.

### Claude's Discretion

- Exact wording of error envelopes (existing `make_error_envelope()` patterns are well-established).
- Whether `app.state.models_cache` uses `asyncio.Lock` to dedupe concurrent first-fetches (likely yes; planner picks).
- Exact Python type for the new `status` enum on AgentSummary (likely Literal of agent_containers.container_status values).
- Test fixture naming (`authenticated_mobile_session` vs `mobile_session` etc).
- Which JWKS-cache library (Google ID token JWT verification): `google-auth` is the canonical Python lib for this and ships JWKS caching by default. Planner verifies vs alternatives.

### Folded Todos

None — `gsd-tools list-todos` returned 0.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level locked decisions
- `.planning/PROJECT.md` — Mission, constraints, OAuth-only auth, Hetzner+Docker model.
- `.planning/REQUIREMENTS.md` — API-01..07 (will be amended in Phase 23 per D-32).
- `.planning/notes/mobile-mvp-decisions.md` — Mobile MVP locked architectural decisions (note: contains stale assumptions about OAuth-not-shipped and ~80 LOC proxy that this CONTEXT.md corrects).
- `.planning/seeds/streaming-chat.md` — Token-level streaming roadmap (additive, post-MVP).
- `CLAUDE.md` — Golden rules (no mocks/stubs, dumb client, ship locally, root-cause-first, test before planning).

### Prior phase contracts (load-bearing)
- `.planning/phases/22c.3-inapp-chat-channel/22c.3-CONTEXT.md` — Full D-01..D-46 of inapp channel (state machine, dispatcher, outbox, SSE).
- `.planning/phases/22c.3.1-runner-inapp-wiring/` — Runner-side inapp wiring + e2e harness.
- `.planning/phases/22c-oauth-google/22c-CONTEXT.md` — D-22c-OAUTH-* (OAuth contracts), D-22c-AUTH-* (require_user, middleware order).
- `.planning/phases/22c-oauth-google/22c-09-SUMMARY.md` — Cross-user isolation test pattern + manual smoke gate.

### Live source files (existing patterns to mirror or extend)
- `api_server/src/api_server/routes/agent_messages.py` — Existing `POST /messages` + SSE `/messages/stream`. **Add Idempotency-Key required validation here (D-09).**
- `api_server/src/api_server/services/inapp_dispatcher.py` — Bot-forwarding logic with 3 contract adapters; reference for mobile chat path (mobile inherits via dispatcher).
- `api_server/src/api_server/services/inapp_messages_store.py` — 9-function single-seam state machine; never inline SQL elsewhere.
- `api_server/src/api_server/services/run_store.py:list_agents` — **Extend with `status` + `last_activity` LATERAL (D-10, D-27).**
- `api_server/src/api_server/middleware/idempotency.py` — IdempotencyMiddleware; `_is_idempotency_eligible` already includes `/v1/agents/:id/messages`.
- `api_server/src/api_server/middleware/session.py` — ApSessionMiddleware (reads `ap_session` cookie → `request.state.user_id`). **No changes per D-17.**
- `api_server/src/api_server/auth/deps.py` — `require_user` inline early-return pattern. New endpoints follow this convention, NOT FastAPI Depends.
- `api_server/src/api_server/auth/oauth.py` — `upsert_user()` + `mint_session()`. **Reuse for mobile credential endpoints (D-16).**
- `api_server/src/api_server/routes/auth.py` — Existing browser OAuth callback. **Add 2 mobile credential endpoints alongside (D-16).**
- `api_server/src/api_server/routes/runs.py` — Existing `POST /v1/runs` (UPSERT agent_instance + smoke). Mobile reuses (D-22).
- `api_server/src/api_server/routes/agent_lifecycle.py:194` — Existing `POST /v1/agents/:id/start`. Mobile reuses (D-22).
- `api_server/src/api_server/routes/users.py` — Existing `GET /v1/users/me`. Mobile cold-start uses this (D-34).
- `api_server/src/api_server/routes/recipes.py` — Existing `GET /v1/recipes`. Mobile reuses for New Agent screen.
- `api_server/src/api_server/main.py` — Middleware order. **Add GZipMiddleware here (D-25).**
- `api_server/alembic/versions/007_inapp_messages.py` — `inapp_messages` schema (single source of chat-history truth per D-01).
- `api_server/alembic/versions/005_sessions_and_oauth_users.py` — `sessions` + `users` schema for D-16.

### Test harness
- `api_server/Makefile` — `e2e-inapp-docker` target (testcontainers + real Docker macOS-parity path).
- `api_server/tests/auth/conftest.py` — `respx_oauth_providers` fixture, `authenticated_cookie` fixture (mirror for mobile).
- `api_server/tests/conftest.py` — `postgres_container`, `migrated_pg`, TRUNCATE CASCADE 8-table list.
- `api_server/tests/spikes/` — Wave 0 spike file location convention.
- `tools/run_recipe.py` — Recipe runner (test container source).
- `recipes/hermes.yaml` and 4 others — recipes used in e2e tests.

### Frontend cross-references
- `frontend/components/playground-form.tsx:169` — Direct OpenRouter fetch site to migrate (D-21).
- `frontend/app/dashboard/page.tsx:97` — Existing `GET /v1/agents` consumer (must keep working when shape extends per D-10/D-27).
- `frontend/app/dashboard/agents/[id]/page.tsx:67-69` — Mocked chat page (deferred ideas — Phase 24+ de-mock work).
- `frontend/lib/api-types.ts` — TypeScript types mirroring backend models.

### External
- Google ID token verification: `https://www.googleapis.com/oauth2/v3/certs` (JWKS). Python lib: `google-auth` (`google.oauth2.id_token.verify_oauth2_token`).
- GitHub user info: `https://api.github.com/user` + `/user/emails` (existing flow already uses these).
- OpenRouter models catalog: `https://openrouter.ai/api/v1/models` (public, no auth).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (DO NOT re-implement)
- **`inapp_messages` table** + `inapp_messages_store.py` 9-function seam — single source of chat history (D-01).
- **`inapp_dispatcher`** — 3-contract adapter (openai_compat / a2a_jsonrpc / zeroclaw_native), readiness gate, transactional outbox. Mobile inherits all of this for free by going through the existing `POST /messages` path.
- **`agent_events` table** + outbox pump → Redis pub/sub `agent:inapp:<agent_instance_id>` → SSE on `/messages/stream`.
- **`require_user`** inline early-return helper (NOT FastAPI Depends).
- **`ApSessionMiddleware`** — cookie-based session resolution; works for mobile cookie-header transport unchanged (D-17).
- **`IdempotencyMiddleware`** — already lists `/v1/agents/:id/messages` as eligible; only handler-level required-presence validation is new (D-09).
- **`RateLimitMiddleware`** — auto-applies to new mobile-credential endpoints, no changes needed.
- **`upsert_user()` + `mint_session()`** in `auth/oauth.py` — reuse verbatim for mobile credential endpoints.
- **`POST /v1/runs`** — creates agent_instance via UPSERT, smoke-tests recipe+model+BYOK. Mobile reuses (D-22).
- **`POST /v1/agents/:id/start`** — spawns persistent container with channel config. Mobile reuses with `channel='inapp'` (D-28).
- **`GET /v1/agents`** + `list_agents()` — extend with `status` + `last_activity` (D-10, D-27).
- **`GET /v1/users/me`** — mobile cold-start session validation (D-34).
- **`GET /v1/recipes`** — mobile fetches recipe catalog from this (already exists).
- **`make e2e-inapp-docker`** — Phase 23 reuses this harness for integration tests (testcontainers + real Docker).
- **`respx_oauth_providers` fixture + 8-table TRUNCATE CASCADE** — copy-extend for mobile-OAuth tests (D-30).

### Established Patterns
- **Single-seam state machines** — never inline SQL outside `*_store.py`. Mobile-OAuth flow inserts via existing `upsert_user`, doesn't add new SQL.
- **Inline early-return for auth** — `require_user(request) -> JSONResponse | UUID`, NOT FastAPI Depends + HTTPException.
- **Stripe-shape error envelope** — `make_error_envelope(ErrorCode.X, message, param=...)`.
- **Migration → unit test → integration test (testcontainers) → live-apply → SUMMARY commit cadence** — established by Phase 22c.
- **Wave 0 spike gate before sealing plan** — Golden Rule #5. D-31 specifies the GZip×SSE spike for this phase.
- **D-numbered context decisions, AMD-numbered amendments** — locked-decision artifacts.
- **TRUNCATE CASCADE 8-table list for test isolation**: users, agent_instances, agent_containers, runs, agent_events, idempotency_keys, rate_limit_counters, sessions.

### Integration Points (where new code lives)

**New files:**
- `api_server/src/api_server/routes/models.py` — NEW route handler for `GET /v1/models`.
- `api_server/src/api_server/services/openrouter_models.py` — NEW (cache + fetch + stale-while-revalidate).
- `api_server/tests/auth/test_oauth_mobile.py` — NEW (D-30 coverage matrix).
- `api_server/tests/routes/test_models.py` — NEW.
- `api_server/tests/spikes/test_gzip_sse_compat.py` — NEW Wave 0 spike (D-31).
- `api_server/tests/routes/test_messages_idempotency_required.py` — NEW (D-09 enforcement).
- `api_server/tests/routes/test_agents_status_field.py` — NEW (D-10/D-27).
- `deploy/.env.dev.example` — NEW env var stanza for `GOOGLE_OAUTH_MOBILE_CLIENT_IDS`.

**Files extended (NOT replaced):**
- `api_server/src/api_server/routes/auth.py` — append 2 mobile-credential endpoints (D-16). DO NOT touch existing browser OAuth handlers.
- `api_server/src/api_server/auth/oauth.py` — add `verify_google_id_token(id_token, mobile_client_ids)` and `verify_github_access_token(access_token)` helpers. Reuse existing `upsert_user` + `mint_session` verbatim.
- `api_server/src/api_server/services/run_store.py` — extend `list_agents()` LATERAL JOIN with `status` (from agent_containers) + `last_activity` (from MAX of last_run_at + inapp_messages.created_at).
- `api_server/src/api_server/models/agents.py` — extend `AgentSummary` with `status`, `last_activity` fields.
- `api_server/src/api_server/routes/agent_messages.py` — `post_message` handler adds `Idempotency-Key` presence check at the top (return 400 if missing).
- `api_server/src/api_server/main.py` — add `GZipMiddleware(app, minimum_size=1024)`. Order: must NOT compress SSE — verify in D-31 spike.
- `api_server/src/api_server/config.py` — add `oauth_google_mobile_client_ids: list[str]` Pydantic setting.
- `frontend/components/playground-form.tsx` — line 169: replace direct OpenRouter fetch with `apiGet("/v1/models")` (D-21).
- `.planning/REQUIREMENTS.md` — amendments per D-32.

</code_context>

<specifics>
## Specific Ideas

- **"Use as is, unless impossible"** is the over-arching principle from this discussion. Every new endpoint or schema change required justification against an existing alternative; most got dropped.
- The transition from "block-and-wait at the HTTP boundary" to "client-side polling via SSE" was the biggest architecture pivot — driven by the user's clarification that agent replies span seconds-to-10+min, which makes one-HTTP-roundtrip block-and-wait infeasible on mobile carriers.
- The user explicitly requested industry-standard Flutter OAuth ("dont reinvent wheel") — that decision is locked to `google_sign_in` (Google's own pkg) + `flutter_appauth` (AppAuth standard for GitHub). Anything else is rejected at planner level.
- The web frontend currently violates Golden Rule #2 in TWO places: chat page is mocked (`dashboard/agents/[id]/page.tsx:67-69`) AND playground-form fetches OpenRouter directly (`playground-form.tsx:169`). Phase 23 closes only the second one (D-21). The first is deferred (Phase 24+).
- **A user note worth preserving for memory:** "API receives the inference. stores. then, either mobile re-asks, or webhook." — This frames the entire backend chat philosophy: the DB is the source of truth, the bot call always completes, clients reconcile on reconnect. NO synchronous-result coupling between client TCP and bot lifecycle.

</specifics>

<deferred>
## Deferred Ideas

- **Migrate BYOK off `Authorization: Bearer` → `X-OpenRouter-Key` header or body field** — frees Authorization header for native bearer-token sessions on mobile (currently sessions ride the Cookie header per D-17). Backwards-incompatible change to /runs + /start contracts; web frontend would need a coordinated update. Post-MVP cleanup phase.
- **Web chat de-mock** — `frontend/app/dashboard/agents/[id]/page.tsx` currently shows hardcoded sample messages. After Phase 23 ships idempotent /messages + SSE, the web chat should consume the same endpoints mobile does. Phase 24+ task.
- **Token-level streaming chat** — see `seeds/streaming-chat.md`. Triggered post-MVP if latency feels janky in real demos.
- **Multi-channel mobile UI** — Telegram toggle on New Agent screen, Browse tab, Profile tab, standalone Select Model screen. All locked-out per mobile-mvp-decisions.md.
- **Pagination, search, regenerate, edit, delete on chat history** — locked-out per mobile-mvp-decisions.md.
- **Agent name-collision UX in mobile (Phase 25)** — D-29 specifies the pre-flight check + confirmation dialog. The exact dialog wording is Phase 25 spec work.
- **Hetzner deploy + remote-API switch** — separate later effort gated on demo-readiness. Not Phase 23.
- **Refresh-token rotation for mobile sessions** — D-26 explicitly forecloses this for MVP. Long-lived 30-day session is sufficient.

### Reviewed Todos (not folded)
None — todo list was empty (`gsd-tools list-todos` returned 0).

</deferred>

---

*Phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim*
*Context gathered: 2026-05-01*
