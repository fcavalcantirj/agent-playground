# Phase 23: Backend Mobile API — Research

**Researched:** 2026-05-01
**Domain:** FastAPI/Starlette backend extension over already-shipped substrate (Phase 22c.3, 22c.3.1, 22c-oauth-google)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Persistence model**

- **D-01:** Reuse `inapp_messages` as the single chat-history source. Zero new tables, zero new migrations. Spec API-06 (new `messages` table) is **DROPPED** — see D-32 for the REQUIREMENTS.md amendment.
- **D-02:** URL `:id` = `agent_instances.id` for ALL Phase 23 endpoints. inapp_messages.agent_id FK already targets agent_instances.id. No translation layer.
- **D-03:** GET /messages returns `status IN ('done','failed')`. `done` rows emit `(role:user from content, role:assistant from bot_response)` two events per row. `failed` rows emit `(role:user from content, role:assistant content="⚠️ delivery failed: <last_error>", kind:'error')`. In-flight (`pending`/`forwarded`) NOT shown.
- **D-04:** GET /messages — ORDER BY created_at ASC, default limit=200, max=1000. Pagination is OUT of MVP.

**Chat send + reply transport**

- **D-05:** Backend completes bot call regardless of client disconnect. DB is source of truth. No client-disconnect-cancellation path.
- **D-06:** Container not running → fail fast. UI is responsible for not surfacing chat input on stopped agents.
- **D-07:** Per-agent serialization across channels. Dispatcher already serializes (single tick, FOR UPDATE SKIP LOCKED).
- **D-08:** Cross-channel history alignment. New sends MUST emit `agent_events(kind=inapp_outbound, published=false)` so existing SSE listeners on `agent:inapp:<agent_id>` see them.
- **D-09:** `Idempotency-Key` REQUIRED on `POST /v1/agents/:id/messages`. Missing header → 400 with Stripe-shape error envelope. ~3 LOC handler-level enforcement.
- **D-12 SUPERSEDED by D-14:** No new `/chat` endpoint.
- **D-13:** Mobile receives replies via SSE on existing `GET /v1/agents/:id/messages/stream`.
- **D-14:** Mobile uses existing `POST /v1/agents/:id/messages` (body `{content: str}`) AS-IS.

**Auth (mobile OAuth)**

- **D-15:** No dev-mode auth shim. Native Flutter SDKs (`google_sign_in` + `flutter_appauth`).
- **D-16:** Phase 23 ships 2 mobile-credential-exchange endpoints: `POST /v1/auth/google/mobile` (verify Google JWT) and `POST /v1/auth/github/mobile` (verify GitHub access_token). Reuses 100% of Phase 22c-03's `upsert_user()` + `mint_session()`.
- **D-17:** Mobile sends `Cookie: ap_session=<uuid>` header directly. No middleware changes.
- **D-23:** New env var `GOOGLE_OAUTH_MOBILE_CLIENT_IDS` (comma-separated). Mobile JWT verifier accepts tokens whose `aud` claim matches any configured mobile ID.
- **D-24:** GitHub reuses existing OAuth app. Add mobile redirect URI scheme to existing whitelist. No new env var.
- **D-30:** Mobile OAuth test scaffolding at `tests/auth/test_oauth_mobile.py`. Coverage matrix per provider: happy path, invalid token, audience mismatch (Google), missing required claims, private GitHub email + /user/emails fallback. Reuses 22c-09's `respx_oauth_providers` fixture pattern.

**Agent list / dashboard**

- **D-10:** Extend existing `GET /v1/agents` to include `status` field derived from `agent_containers.container_status`. LATERAL JOIN extension on `list_agents()`. No new endpoint.
- **D-11:** Container resolution policy: `WHERE agent_instance_id=:id AND stopped_at IS NULL ORDER BY created_at DESC LIMIT 1`. Zero rows → fail-fast `container_not_ready` per D-06.
- **D-22:** Deploy flow uses existing endpoints (`POST /v1/runs` + `POST /v1/agents/:id/start`). Zero new backend endpoints for deploy.
- **D-27:** `last_activity` field. Compute in same LATERAL extension as D-10: `last_activity = MAX(ai.last_run_at, MAX(im.created_at) WHERE im.agent_id=ai.id)`. NULL when user has never run nor messaged.
- **D-28:** Mobile Phase 25 deploys with `{channel: 'inapp', channel_inputs: {}}`.
- **D-29:** Backend keeps `(user_id, name)` UPSERT semantics. Mobile UI does pre-flight `GET /v1/agents` and surfaces a confirmation dialog.

**Models proxy (`GET /v1/models`)**

- **D-18:** In-process dict cache, 15min TTL. `app.state.models_cache = {fetched_at: datetime, payload: bytes}`. Stale-while-revalidate on fetch failure (serve stale + log error).
- **D-19:** Backend calls `https://openrouter.ai/api/v1/models` with NO Authorization header. Public endpoint.
- **D-20:** Passthrough response. Backend returns OpenRouter's payload byte-for-byte. Per dumb-client rule the client filters by capability/price/etc.
- **D-21:** Web frontend migration in scope. `frontend/components/playground-form.tsx:169` updates from direct OpenRouter fetch to `apiGet("/v1/models")`. ~5 LOC change.
- **D-25:** Add Starlette `GZipMiddleware(minimum_size=1024)` to `main.py`. Compresses /v1/models response from ~430KB → ~50KB.

**UX / lifecycle**

- **D-26:** Session expiry → 401 → mobile routes to OAuth. No refresh tokens. No retry-on-401 logic.
- **D-31:** Wave 0 spike — GZip × SSE compatibility. Plan MUST include `tests/spikes/test_gzip_sse_compat.py` BEFORE plan seals. If GZip buffers SSE, switch to a content-type-exclude config that skips `text/event-stream`. Plan does not seal until spike PASSES.
- **D-32:** REQUIREMENTS.md amendments are part of Phase 23's commit chain (API-01 rewritten, API-05 rewritten, API-06 DROPPED, API-04 unchanged, traceability updated). **Without these amendments the verifier will fail the phase-exit gate.**
- **D-33:** Cookie-header for sessions stays (D-17). Cleaner Authorization-Bearer path captured in deferred ideas.
- **D-34:** Mobile cold-start auth check uses existing `GET /v1/users/me`. No new endpoint.

### Claude's Discretion

- Exact wording of error envelopes (existing `make_error_envelope()` patterns are well-established).
- Whether `app.state.models_cache` uses `asyncio.Lock` to dedupe concurrent first-fetches (likely yes).
- Exact Python type for the new `status` enum on AgentSummary (likely Literal of agent_containers.container_status values).
- Test fixture naming (`authenticated_mobile_session` vs `mobile_session` etc).
- Which JWKS-cache library — `google-auth` is canonical Python lib for Google ID JWT verification.

### Deferred Ideas (OUT OF SCOPE)

- Migrate BYOK off `Authorization: Bearer` → `X-OpenRouter-Key` header or body field (post-MVP cleanup).
- Web chat de-mock — `frontend/app/dashboard/agents/[id]/page.tsx` (Phase 24+ task).
- Token-level streaming chat (`seeds/streaming-chat.md`).
- Multi-channel mobile UI (Telegram toggle, Browse tab, Profile tab, standalone Select Model screen).
- Pagination, search, regenerate, edit, delete on chat history.
- Agent name-collision UX in mobile (Phase 25 spec work).
- Hetzner deploy + remote-API switch (separate later effort).
- Refresh-token rotation for mobile sessions (D-26 forecloses for MVP).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (post-D-32 amendment) | Research Support |
|----|-------------|------------------|
| API-01 | (REWRITTEN per D-32) Backend hardens existing `POST /v1/agents/:id/messages` to require an `Idempotency-Key` header (400 if missing). Body unchanged: `{content: string}`. Response unchanged: 202 `{message_id, status, queued_at}`. Idempotent retry replays cached response via existing IdempotencyMiddleware. | Live source `routes/agent_messages.py:119-180` (D-09 enforcement site); `middleware/idempotency.py:53-73` already lists this path eligible (lines 53-58); ~3 LOC handler-level addition |
| API-02 | (UNCHANGED) `GET /v1/agents/:id/messages?limit=N` returns history ordered by `created_at` ASC, default 200, max 1000. | Existing `inapp_messages_store.py` 9-function seam (D-01) provides the read path; new route handler reads `status IN ('done','failed')` per D-03 |
| API-03 | (UNCHANGED) `GET /v1/agents` Dashboard shape (id, recipe_name, model, status, created_at, last_activity). | Existing `run_store.list_agents()` LATERAL extension per D-10 + D-27; AgentSummary model extension |
| API-04 | (UNCHANGED) `GET /v1/models` proxies OpenRouter catalog with TTL cache (≥5 min, ≤1 h). | Empirically verified: OpenRouter `/api/v1/models` returns 200 unauthenticated, ~430KB JSON, top-level `{data: [...]}` shape, gzipped 50KB. In-process dict cache + asyncio.Lock + 15min TTL per D-18 |
| API-05 | (REWRITTEN per D-32) Backend exposes `POST /v1/auth/google/mobile` and `POST /v1/auth/github/mobile` accepting native-SDK credentials, verifying server-side, and minting `sessions` rows that mobile sends back as `Cookie: ap_session=<uuid>` header. ApSessionMiddleware unchanged. No dev-mode shim. | Reuses `auth/oauth.py::upsert_user()` + `mint_session()` verbatim (D-16). New `verify_google_id_token()` + `verify_github_access_token()` helpers added to `auth/oauth.py`. google-auth library for JWT verification. |
| API-06 | (DROPPED per D-32) Replaced by reuse of existing `inapp_messages` table per Phase 23 D-01. | Migration 007 schema (verified live) covers all needed fields: `id, agent_id, user_id, content, status, bot_response, created_at, completed_at` |
| API-07 | (UNCHANGED) Integration tests hit real Postgres via testcontainers and real Docker (same harness as Phase 22c.3.1). No mocks for chat-proxy round-trips; bot HTTP responses may be `respx`-stubbed at the upstream HTTP layer ONLY. | Existing `make e2e-inapp-docker` target + `started_api_server` fixture cover both rails. New tests for mobile-OAuth use `respx_oauth_providers` fixture pattern (mocks Google JWKS + GitHub /user) per D-30. |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

Phase 23 must comply with all 5 Golden Rules verbatim. Key implications for planning:

| Golden Rule | Phase 23 Impact |
|-------------|-----------------|
| **#1 No mocks, no stubs** | Tests run against real testcontainers Postgres + real Redis + real Docker (`make e2e-inapp-docker`). Bot HTTP responses MAY be `respx`-stubbed at the upstream HTTP boundary only (per API-07 + 22c.3 contract); the proxy's own DB writes + container lookup must be real. |
| **#2 Dumb client, intelligence in API** | Web frontend MUST migrate from direct OpenRouter fetch to `apiGet("/v1/models")` in this same phase (D-21). Mobile gets `/v1/models` from day 1 — no hardcoded model list ever. |
| **#3 Ship locally end-to-end** | Phase 25 demo must work against `localhost:8000` real api_server with real recipe containers. No "deploy to prod and hope" path. |
| **#4 Root cause first** | Pre-existing `inapp_messages` schema, `IdempotencyMiddleware`, `ApSessionMiddleware`, `upsert_user`, `mint_session` are all known-good. Phase 23 extends them; it does NOT replace them. Any failure during execution must investigate root cause before touching shipped substrate. |
| **#5 Test everything before planning** | D-31 Wave 0 spike (`tests/spikes/test_gzip_sse_compat.py`) MUST pass BEFORE plan seals. The Starlette source verification below shows the spike will likely PASS without extra config (default-exclude already handles SSE) — but spiking against the live SSE route is still required. |

## Summary

Phase 23 is a low-LOC additive extension on top of substrate that has already shipped (Phase 22c.3 in-app chat channel; Phase 22c-oauth-google authentication; Phase 22c.3.1 dockerized e2e harness). All five new mechanisms reuse existing primitives and require **zero new tables, zero new middlewares, zero new wire-protocol shapes**. The dominant risk surface is the four library/SaaS gray areas the planner consumes: (1) Starlette GZipMiddleware × SSE compatibility, (2) google-auth JWKS-caching + multi-audience semantics, (3) OpenRouter `/api/v1/models` shape and rate behavior, (4) respx-mocking JWT signature verification deterministically.

Live source inspection + empirical probes resolve all four gray areas with HIGH confidence:

1. **Starlette GZipMiddleware ALREADY excludes `text/event-stream` by default** (verified in installed source `starlette/middleware/gzip.py` line 1: `DEFAULT_EXCLUDED_CONTENT_TYPES = ("text/event-stream",)`). The exclusion landed in starlette 0.46.0 (PR #2871, 2025-02-22). FastAPI 0.136.0 requires `starlette>=0.46.0`. The Wave 0 spike (D-31) becomes a regression-prevention sanity check, not a discovery operation.
2. **`google-auth.id_token.verify_oauth2_token`** does NOT cache JWKS by default (re-fetches per call, library docstring confirms). Multi-audience verification works in practice (the function forwards `audience` to `verify_token` which accepts `Union[str, list[str], None]`) but is not documented. **Recommendation**: pass a list to `verify_oauth2_token` and rely on the documented `verify_token` semantics, plus add a tiny in-process JWKS cache (~30 lines, 6h TTL) to avoid an HTTP round-trip per mobile sign-in. The function is **synchronous** — wrap with `await asyncio.to_thread(...)` in the FastAPI handler.
3. **OpenRouter `/api/v1/models`** is empirically public — `curl https://openrouter.ai/api/v1/models` returns HTTP 200, ~430KB JSON, top-level `{data: [371 models]}`, headers `cache-control: private, no-store` and `access-control-allow-origin: *`. Gzipped wire size ~50KB. No documented per-IP rate limit on unauthenticated calls; with a 15min cache (~4 fetches/hour/replica) we are well below any plausible WAF threshold.
4. **respx mocking** is the existing test pattern (already pinned `respx>=0.22,<0.24` in `pyproject.toml`); JWT signature verification is mockable by stubbing the JWKS endpoint to return a test public key derived from a per-test RSA keypair, then signing test JWTs with the matching private key.

**Primary recommendation:** Plan three waves: (Wave 0) GZip×SSE spike + add `google-auth` direct dep + Pydantic settings field. (Wave 1) Five additive mechanisms in parallel: Idempotency-Key required + list_agents LATERAL extension + GET /v1/models route + 2 mobile-credential-exchange endpoints + GZipMiddleware in main.py. (Wave 2) D-21 frontend migration + D-32 REQUIREMENTS.md amendments + integration test sweep.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Idempotency-Key REQUIRED enforcement | API / Backend (handler-level early return) | — | Header presence check belongs at the route, not in middleware (which already passes through when header absent — that is correct middleware semantics; the change is "this specific route also requires it to be present") |
| `status` + `last_activity` derivation | API / Backend (SQL LATERAL JOIN in `run_store.list_agents`) | — | Single round-trip; Postgres handles the cross-table aggregation; no client-side joining |
| `/v1/models` OpenRouter passthrough proxy | API / Backend (new route + service module) | — | Per Golden Rule #2 (dumb client); cache lives in API process memory; web AND mobile both consume it |
| In-process models cache | API / Backend (`app.state.models_cache` dict + asyncio.Lock) | — | 15min TTL is per-replica; ~4 fetches/hour/replica is trivial; Redis would add a dep with no benefit at this scale |
| Mobile OAuth: Google JWT signature verification | API / Backend (`auth/oauth.py::verify_google_id_token`) | — | Cannot trust client-side verification; JWKS fetch + signature check must be server-side |
| Mobile OAuth: GitHub access-token validation | API / Backend (`auth/oauth.py::verify_github_access_token`) | — | Same rationale — server validates by calling GitHub `/user` with the token; client-side validation = trivially forged |
| Session minting from mobile credentials | API / Backend (existing `mint_session()`) | — | Reuse 100% — no client-side sessions |
| Cookie transport for mobile sessions | Mobile / Client (sets `Cookie: ap_session=<uuid>` on every request) | API / Backend (`ApSessionMiddleware` reads it) | Cookie-as-header carries the session; existing middleware doesn't care about cookie jar vs explicit header |
| GZip compression of HTTP responses | API / Backend (Starlette middleware) | — | Standard wire-layer concern; default-excludes SSE |
| Frontend `/v1/models` consumption (D-21) | Frontend Server / Client | API / Backend (serves the proxy) | The dumb-client rule: client filters/displays; API owns catalog truth |

## Standard Stack

### Core (already pinned in `api_server/pyproject.toml` — verified)

| Library | Pinned Version | Verified Latest (PyPI 2026-04-30) | Purpose | Why Standard |
|---------|---------|-----------------------------------|---------|--------------|
| `fastapi` | 0.136.0 | 0.136.1 | HTTP framework | Already in stack; route handler patterns established. `[VERIFIED: pip show + pyproject]` |
| `starlette` | (transitive `>=0.46.0` via fastapi) | 1.0.0 (FastAPI tracks 0.x) | ASGI primitives + GZipMiddleware | **Critical**: `>=0.46.0` is the floor that has the SSE-default-exclude. `[VERIFIED: starlette release notes — 0.46.0, PR #2871, 2025-02-22]` |
| `asyncpg` | >=0.31.0,<0.32 | (latest in range) | Postgres driver | DB seam for new LATERAL JOIN extension. `[VERIFIED: pyproject + run_store.py imports]` |
| `pydantic` | >=2.11 | 2.11+ | Settings + request bodies | New `oauth_google_mobile_client_ids` setting; new `MobileGoogleAuthRequest` / `MobileGitHubAuthRequest` models. `[VERIFIED: pyproject]` |
| `pydantic-settings` | >=2.0 | 2.0+ | Env var loading | Add `oauth_google_mobile_client_ids: list[str]` field with comma-split validator. `[VERIFIED: pyproject + config.py]` |
| `httpx` | >=0.27 | 0.27+ | OpenRouter HTTP fetch + GitHub `/user` HTTP | Already runtime dep; second AsyncClient (or shared) for catalog fetches. `[VERIFIED: pyproject]` |
| `redis` | >=5.2,<8 | 7.4.0 | Pub/sub for SSE (existing) | No new use in Phase 23; existing infra. `[VERIFIED: pyproject]` |
| `sse-starlette` | >=3.4,<4 | 3.4.1 | Existing SSE handler (untouched) | No new use; existing handler remains the chat reply transport. `[VERIFIED: pyproject + agent_messages.py imports]` |

### New (must add to `api_server/pyproject.toml`)

| Library | Recommended Pin | Latest (PyPI) | Purpose | Why Required |
|---------|---------|-----------------------------------|---------|--------------|
| `google-auth` | `>=2.40,<3` | 2.50.0 (2026-04-30) | Google ID-token JWT signature verification | Currently transitive (2.40.3 in venv) — **MUST become direct dep** so a future cleanup of transitives can't silently break mobile sign-in. `[VERIFIED: pip show google-auth + pypi]` |

**Note on `pyjwt`:** the `google-auth` source uses `pyjwt`'s `PyJWKClient` (which has built-in caching) ONLY when the JWKS response uses the JWK array format. Google's `oauth2/v3/certs` endpoint returns the JWK format, so pyjwt's `PyJWKClient` IS in the call path — but pyjwt is a transitive of `google-auth`, NOT directly imported. Adding it explicitly is unnecessary. `[VERIFIED: google-auth source @ id_token.py line ~95 `import jwt as jwt_lib`]`

### Test Stack (already pinned)

| Library | Pinned Version | Purpose | Phase 23 Use |
|---------|---------|---------|-------------|
| `pytest` | >=8 | Test runner | All new test files |
| `pytest-asyncio` | >=0.23 | Async test driver | `asyncio_mode = "auto"` already set |
| `testcontainers[postgres,redis]` | >=4.14.2 | Real Postgres + Redis containers | All integration tests |
| `httpx` | >=0.27 | ASGITransport client | Already used in async_client fixture |
| `respx` | >=0.22,<0.24 | httpx-native HTTP mocking | Mobile-OAuth tests stub Google JWKS + GitHub `/user` (existing `respx_oauth_providers` fixture extended) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `google-auth.id_token.verify_oauth2_token` | Hand-rolled JWT verify with `pyjwt` + JWKS fetch | More code (~80 LOC); we'd duplicate Google issuer-allowlist logic; ditto for clock-skew handling. **Reject** — google-auth is the canonical lib and is already in venv. |
| In-process dict cache for /v1/models | Redis cache | Adds dep (Redis IS in stack but adds an SPOF for the catalog); 4 fetches/hour/replica is trivial; `app.state.models_cache` is simpler and tested via direct dict introspection. **Reject** Redis. |
| In-process dict cache for JWKS | `cachecontrol` library | google-auth docstring suggests cachecontrol but we'd add a dep for ~10 LOC of caching. **Reject** — write 30 LOC of in-process cache (mirrors models cache pattern). |
| Add a new `mobile_session` cookie variant | Reuse `ap_session` cookie name | Per D-17, mobile sends `Cookie: ap_session=<uuid>` directly. Same name, same middleware, zero divergence. **Use existing.** |
| `Authorization: Bearer <session>` for mobile | Cookie-header transport | Per D-33, deferred — would require breaking change to /runs + /start (which web also uses). MVP keeps cookie. |
| New httpx.AsyncClient for OpenRouter | Reuse `app.state.bot_http_client` | bot_http_client has 600s timeout (wrong for catalog); 10s timeout for catalog is correct. **Use new client** at `app.state.openrouter_http_client` with 10s timeout. |

**Installation:**

```bash
# api_server/pyproject.toml — add to dependencies:
"google-auth>=2.40,<3",

# Then in api_server/:
uv pip install --upgrade google-auth
# Or via the standard install path:
pip install -e ".[dev]"
```

**Version verification commands (run during plan execution to confirm pins haven't drifted):**

```bash
python3 -c "import google.auth; print(google.auth.__version__)"  # expect 2.40+
python3 -c "import starlette; print(starlette.__version__)"      # expect 0.46.0+
python3 -c "import inspect; from starlette.middleware import gzip; assert 'text/event-stream' in inspect.getsource(gzip)"  # SSE-exclude regression check
```

## Architecture Patterns

### System Architecture Diagram

```
                                                    ┌──────────────────────────────┐
                                                    │  Mobile Flutter app          │
                                                    │  (Phase 24/25 — out of P23)  │
                                                    │                              │
                                                    │  ・google_sign_in SDK → JWT  │
                                                    │  ・flutter_appauth → OAuth   │
                                                    │     access_token (GitHub)    │
                                                    └─────────────┬────────────────┘
                                                                  │
                          ┌───────────────────────────────────────┼────────────────────┐
                          │ HTTP (Cookie: ap_session=<uuid>)      │ POST {id_token}    │
                          ▼                                       ▼                    │
   ┌────────────────────────────────────────────────────────────────────────────────────────┐
   │                              FastAPI app (api_server)                                   │
   │                                                                                        │
   │   ┌──────────────────────────────────────────────────────────────────────────────────┐ │
   │   │  Middleware chain (request-in order, established by Phase 22c)                    │ │
   │   │                                                                                   │ │
   │   │   CorrelationId → AccessLog → StarletteSession → ApSessionMiddleware             │ │
   │   │                                                       (reads ap_session cookie    │ │
   │   │                                                        OR explicit Cookie hdr     │ │
   │   │                                                        — D-17, no change)         │ │
   │   │       ↓                                                                           │ │
   │   │   RateLimitMiddleware → IdempotencyMiddleware → router                           │ │
   │   │                          (already lists                                           │ │
   │   │                           POST /v1/agents/:id/messages                            │ │
   │   │                           — D-09 adds                                             │ │
   │   │                           HEADER-PRESENCE check                                   │ │
   │   │                           in the handler)                                         │ │
   │   └──────────────────────────────────────────────────────────────────────────────────┘ │
   │                                                                                        │
   │   Phase 23 NEW middleware (added at TOP per D-25):                                     │
   │                                                                                        │
   │   GZipMiddleware(minimum_size=1024) ◀──── default-excludes text/event-stream           │
   │                                          (Starlette ≥ 0.46.0; verified)                │
   │       │                                                                                │
   │       ▼                                                                                │
   │   ┌─────────────────────────────────────────────────────────────────────────────────┐ │
   │   │  Routes (under /v1)                                                              │ │
   │   │                                                                                  │ │
   │   │  EXISTING (Phase 22c.3-08 — reused):                                            │ │
   │   │    POST   /v1/agents/:id/messages       ◀── D-09 enforces Idempotency-Key       │ │
   │   │    GET    /v1/agents/:id/messages       ◀── EXISTS? NO — needs new GET handler  │ │
   │   │                                              for chat history (status IN done/   │ │
   │   │                                              failed) per D-03+D-04              │ │
   │   │    GET    /v1/agents/:id/messages/stream ◀── SSE (untouched)                    │ │
   │   │    DELETE /v1/agents/:id/messages       ◀── exists                              │ │
   │   │                                                                                  │ │
   │   │  EXISTING (Phase 20 — extended in this phase):                                  │ │
   │   │    GET    /v1/agents                    ◀── D-10 + D-27 LATERAL extension       │ │
   │   │                                                                                  │ │
   │   │  EXISTING (Phase 22c — reused, untouched):                                      │ │
   │   │    GET    /v1/users/me                  ◀── mobile cold-start auth check (D-34) │ │
   │   │    GET    /v1/auth/google[/callback]    ◀── browser flow (existing, untouched)  │ │
   │   │    GET    /v1/auth/github[/callback]    ◀── browser flow (existing, untouched)  │ │
   │   │    POST   /v1/auth/logout               ◀── existing                            │ │
   │   │                                                                                  │ │
   │   │  NEW (Phase 23):                                                                 │ │
   │   │    GET    /v1/models                    ◀── OpenRouter catalog proxy            │ │
   │   │    POST   /v1/auth/google/mobile        ◀── credential-exchange                 │ │
   │   │    POST   /v1/auth/github/mobile        ◀── credential-exchange                 │ │
   │   └─────────────────────────────────────────────────────────────────────────────────┘ │
   │                                                                                        │
   │   ┌──────────────────────────────┐ ┌──────────────────────────────────────────────────┐│
   │   │  app.state.models_cache       │ │  app.state.openrouter_http_client (NEW)          ││
   │   │  {fetched_at, payload bytes}  │ │  httpx.AsyncClient(timeout=10.0)                 ││
   │   │  + asyncio.Lock for dedup     │ │  → fires GET https://openrouter.ai/api/v1/models  ││
   │   └──────────────────────────────┘ └──────────────────────────────────────────────────┘│
   │                                                                                        │
   │   ┌──────────────────────────────────────────────────────────────────────────────────┐ │
   │   │  Mobile-OAuth helper module (auth/oauth.py extended):                             │ │
   │   │                                                                                   │ │
   │   │   verify_google_id_token(id_token: str, mobile_client_ids: list[str]) -> dict     │ │
   │   │     │                                                                             │ │
   │   │     ▼                                                                             │ │
   │   │   google.oauth2.id_token.verify_oauth2_token(token, request, audience=list)       │ │
   │   │   wrapped in asyncio.to_thread + tiny in-process JWKS cache (6h TTL)              │ │
   │   │                                                                                   │ │
   │   │   verify_github_access_token(access_token: str) -> dict                           │ │
   │   │     │                                                                             │ │
   │   │     ▼                                                                             │ │
   │   │   GET https://api.github.com/user (Authorization: Bearer <token>)                 │ │
   │   │     + fallback /user/emails on private email (D-22c-OAUTH-03 contract)            │ │
   │   └──────────────────────────────────────────────────────────────────────────────────┘ │
   │       │                                                                                │
   │       ▼                                                                                │
   │   upsert_user(...) + mint_session(...) ◀──── existing helpers, untouched               │
   └────────────────────────────────────────────────┬───────────────────────────────────────┘
                                                    │
                          ┌─────────────────────────┴──────────────────────────────┐
                          ▼                                                        ▼
            ┌───────────────────────┐                              ┌─────────────────────────┐
            │  Postgres             │                              │  Existing dispatcher    │
            │                       │                              │  + outbox + Redis       │
            │  inapp_messages       │                              │  pub/sub (untouched)    │
            │  agent_instances      │                              │                         │
            │  agent_containers     │                              │  (handles D-07 per-     │
            │  agent_events         │                              │   agent serialization,  │
            │  users                │                              │   D-08 cross-channel    │
            │  sessions             │                              │   alignment, D-13       │
            │  idempotency_keys     │                              │   SSE replay-on-        │
            │  rate_limit_counters  │                              │   reconnect)             │
            └───────────────────────┘                              └─────────────────────────┘
```

### Recommended Project Structure

Phase 23 only adds files to `api_server/`. Frontend touches one line.

```
api_server/
├── src/api_server/
│   ├── routes/
│   │   ├── agent_messages.py       # EXTEND: D-09 Idempotency-Key required (~3 LOC)
│   │   │                              + NEW handler for GET /messages history (D-03+D-04)
│   │   ├── agents.py               # NO CHANGE (uses run_store.list_agents)
│   │   ├── auth.py                 # APPEND 2 mobile credential-exchange endpoints (D-16)
│   │   ├── models.py               # NEW (D-19/D-20 OpenRouter passthrough)
│   │   └── ...
│   ├── services/
│   │   ├── run_store.py            # EXTEND list_agents() with status + last_activity (D-10/D-27)
│   │   ├── inapp_messages_store.py # NO CHANGE (existing seam covers history reads)
│   │   ├── openrouter_models.py    # NEW (D-18 cache + fetch + stale-while-revalidate)
│   │   └── ...
│   ├── auth/
│   │   ├── deps.py                 # NO CHANGE (require_user reused)
│   │   └── oauth.py                # EXTEND with verify_google_id_token + verify_github_access_token
│   ├── middleware/                 # NO CHANGES — all existing middleware reused
│   │   └── ...
│   ├── models/
│   │   ├── agents.py               # EXTEND AgentSummary with status + last_activity
│   │   └── ...
│   ├── config.py                   # ADD oauth_google_mobile_client_ids: list[str]
│   └── main.py                     # ADD GZipMiddleware(app, minimum_size=1024)
│                                     ADD app.state.models_cache + openrouter_http_client init
│                                     INCLUDE models route
├── tests/
│   ├── auth/
│   │   └── test_oauth_mobile.py    # NEW (D-30 coverage matrix)
│   ├── routes/
│   │   ├── test_messages_idempotency_required.py  # NEW (D-09)
│   │   ├── test_agents_status_field.py            # NEW (D-10/D-27)
│   │   └── test_models.py                         # NEW (cache hit/miss/stale)
│   └── spikes/
│       └── test_gzip_sse_compat.py # NEW Wave 0 spike (D-31)
├── pyproject.toml                  # ADD google-auth>=2.40,<3
└── ...

deploy/
└── .env.dev.example                # ADD AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS placeholder

frontend/
└── components/playground-form.tsx  # MIGRATE line ~169 from direct OpenRouter fetch to apiGet("/v1/models")

.planning/
└── REQUIREMENTS.md                 # AMEND per D-32 (API-01 rewrite, API-05 rewrite, API-06 drop, traceability)
```

### Pattern 1: Handler-level Idempotency-Key REQUIRED check (D-09)

**What:** The IdempotencyMiddleware passes through when the header is absent (correct generic semantic). For `POST /messages` we additionally require the header — enforce in the handler with an early-return.

**When to use:** Whenever a route handler needs to require a header that the middleware treats as optional.

**Example:**

```python
# api_server/src/api_server/routes/agent_messages.py
# NEW lines added at the TOP of post_message (after require_user, before fetch_agent_instance):

@router.post("/agents/{agent_id}/messages", status_code=202)
async def post_message(
    request: Request,
    agent_id: UUID,
    body: PostMessageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),  # NEW
):
    # --- D-09: require Idempotency-Key (~3 LOC) ---
    if not idempotency_key or not idempotency_key.strip():
        return _err(
            400, ErrorCode.INVALID_REQUEST,
            "Idempotency-Key header is required",
            param="Idempotency-Key",
        )
    # ... rest of existing handler unchanged ...
```

`[VERIFIED: routes/agent_messages.py source — Header import already present line 34; _err helper already exists line 78-97; ErrorCode.INVALID_REQUEST already used line 161]`

### Pattern 2: LATERAL JOIN extension on `list_agents()` (D-10 + D-27)

**What:** Add two derived columns (`status`, `last_activity`) computed via a second LATERAL subquery joining `agent_containers` (most-recent live container) and an aggregate over `inapp_messages.created_at`.

**When to use:** When extending an existing list endpoint with derived columns from sibling tables, single round-trip required.

**Example:**

```python
# api_server/src/api_server/services/run_store.py — list_agents extension

async def list_agents(
    conn: asyncpg.Connection,
    user_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
            ai.id,
            ai.name,
            ai.recipe_name,
            ai.model,
            ai.personality,
            ai.created_at,
            ai.last_run_at,
            ai.total_runs,
            lr.verdict AS last_verdict,
            lr.category AS last_category,
            lr.run_id AS last_run_id,
            -- Phase 23 D-10: status from most-recent live agent_containers row
            ac.container_status AS status,
            -- Phase 23 D-27: last_activity = max(last_run_at, max(im.created_at))
            GREATEST(
                ai.last_run_at,
                (SELECT MAX(im.created_at) FROM inapp_messages im WHERE im.agent_id = ai.id)
            ) AS last_activity
        FROM agent_instances ai
        LEFT JOIN LATERAL (
            SELECT id AS run_id, verdict, category
            FROM runs
            WHERE agent_instance_id = ai.id
            ORDER BY created_at DESC
            LIMIT 1
        ) lr ON TRUE
        LEFT JOIN LATERAL (
            -- Phase 23 D-11: WHERE stopped_at IS NULL ORDER BY created_at DESC LIMIT 1
            SELECT container_status
            FROM agent_containers
            WHERE agent_instance_id = ai.id AND stopped_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
        ) ac ON TRUE
        WHERE ai.user_id = $1
        ORDER BY ai.created_at DESC
        """,
        user_id,
    )
    return [dict(r) for r in rows]
```

`[VERIFIED: existing list_agents signature + LATERAL pattern at run_store.py:78-114]`

`[ASSUMED]` The `inapp_messages` table has indexes that make `MAX(created_at) WHERE agent_id = $1` cheap. Confirmed at index level by checking `alembic/versions/007_inapp_messages.py` — there IS an index on `(agent_id, created_at)`. **Action**: Plan should EXPLICITLY VERIFY by reading migration 007 before sealing.

### Pattern 3: In-process dict cache + asyncio.Lock dedupe (D-18)

**What:** Single dict on `app.state` storing `(fetched_at, payload_bytes)`. Concurrent first-fetches are deduped by a single asyncio.Lock so the cold-start thundering-herd doesn't fan out 50 OpenRouter calls.

**When to use:** Process-local caching of slowly-changing third-party data with cheap fan-out fallback (stale-while-revalidate on fetch failure).

**Example:**

```python
# api_server/src/api_server/services/openrouter_models.py (NEW)

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

_log = logging.getLogger("api_server.openrouter_models")
_OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
_CACHE_TTL = timedelta(minutes=15)


async def get_models_payload(state) -> bytes:
    """Return cached OpenRouter /models payload bytes; fetch on miss/stale.

    state.models_cache shape: dict with keys {fetched_at, payload}.
    state.models_cache_lock: asyncio.Lock for fetch deduplication.
    state.openrouter_http_client: pre-configured httpx.AsyncClient.

    Stale-while-revalidate (D-18): if a fetch fails AND we have stale data,
    serve the stale bytes + log the error. Only fail with 503 if there's
    no stale data to fall back on.
    """
    cache = state.models_cache
    now = datetime.now(timezone.utc)
    if cache.get("fetched_at") and (now - cache["fetched_at"]) < _CACHE_TTL:
        return cache["payload"]

    # Cold or stale — fetch with single-flight dedupe
    async with state.models_cache_lock:
        # Re-check inside lock — another coroutine may have just refreshed
        if cache.get("fetched_at") and (now - cache["fetched_at"]) < _CACHE_TTL:
            return cache["payload"]
        try:
            r = await state.openrouter_http_client.get(_OPENROUTER_URL)
            r.raise_for_status()
            cache["fetched_at"] = now
            cache["payload"] = r.content  # raw bytes — no JSON re-serialize
            return cache["payload"]
        except Exception:
            _log.exception("openrouter_models.fetch_failed")
            if cache.get("payload"):
                # D-18 stale-while-revalidate: serve stale, log error
                return cache["payload"]
            raise  # no fallback — 503 to client
```

`[VERIFIED: empirical OpenRouter probe — HTTP 200, 430KB JSON, ~0.29s response time, gzip support]`

### Pattern 4: Mobile credential-exchange endpoints (D-16)

**What:** Two new POST endpoints alongside the existing browser OAuth handlers. Reuse `upsert_user` + `mint_session` verbatim. The new code is exclusively the credential-verification layer.

**When to use:** When a non-browser client (mobile app) provides server-side-verifiable credentials and you need to mint the same session shape as the browser flow.

**Example:**

```python
# api_server/src/api_server/routes/auth.py (APPEND, do not replace browser handlers)

class MobileGoogleAuthRequest(BaseModel):
    """Body for POST /v1/auth/google/mobile."""
    id_token: str = Field(..., min_length=1)


class MobileGitHubAuthRequest(BaseModel):
    """Body for POST /v1/auth/github/mobile."""
    access_token: str = Field(..., min_length=1)


class MobileSessionResponse(BaseModel):
    """Response for both /v1/auth/{google,github}/mobile."""
    session_id: str
    expires_at: datetime
    user: SessionUserResponse  # reuse existing /v1/users/me shape


@router.post("/auth/google/mobile", status_code=200)
async def google_mobile(
    request: Request, body: MobileGoogleAuthRequest
) -> JSONResponse:
    settings = request.app.state.settings
    try:
        claims = await verify_google_id_token(
            body.id_token, settings.oauth_google_mobile_client_ids,
        )
    except ValueError as e:  # signature fail / expired / aud mismatch
        return _err(401, ErrorCode.UNAUTHORIZED, str(e), param="id_token")

    if not claims.get("sub") or not claims.get("email"):
        return _err(401, ErrorCode.UNAUTHORIZED, "missing required claims",
                    param="id_token")

    pool = request.app.state.db
    async with pool.acquire() as conn:
        user_id = await upsert_user(
            conn,
            provider="google",
            sub=str(claims["sub"]),
            email=claims["email"],
            display_name=claims.get("name") or claims["email"],
            avatar_url=claims.get("picture"),
        )
        session_id = await mint_session(conn, user_id=user_id, request=request)
        # Re-read for response shape
        sess_row = await conn.fetchrow(
            "SELECT expires_at FROM sessions WHERE id = $1", UUID(session_id),
        )
        user_row = await conn.fetchrow(
            "SELECT id, email, display_name, avatar_url FROM users WHERE id = $1",
            user_id,
        )

    return JSONResponse(status_code=200, content={
        "session_id": session_id,
        "expires_at": sess_row["expires_at"].isoformat(),
        "user": {
            "id": str(user_row["id"]),
            "email": user_row["email"],
            "display_name": user_row["display_name"],
            "avatar_url": user_row["avatar_url"],
        },
    })


# Symmetric for /auth/github/mobile — calls verify_github_access_token instead.
```

**Critical notes:**
- Per D-30 the response carries `user: <SessionUserResponse shape>` — match the existing `GET /v1/users/me` response shape exactly so mobile can reuse the same Pydantic deserialization.
- Mobile client is responsible for storing the `session_id` in secure storage and sending it back as `Cookie: ap_session=<session_id>` on subsequent calls (D-17). The response body returns it; the response does NOT need to also Set-Cookie (mobile doesn't have a cookie jar).
- The existing `make_error_envelope()` Stripe-shape applies to all 4xx errors.

### Pattern 5: Google ID-token verification with multi-audience + JWKS cache

**What:** Wrap `google.oauth2.id_token.verify_oauth2_token` (synchronous) in `asyncio.to_thread` + add a tiny module-level JWKS cache (6h TTL) to avoid an HTTP round-trip per verification.

**When to use:** Server-side verification of Google ID tokens issued by mobile native sign-in (one of N mobile platform client IDs).

**Example:**

```python
# api_server/src/api_server/auth/oauth.py — APPEND helpers

import asyncio
from google.oauth2 import id_token as _google_id_token
from google.auth.transport import requests as _google_ga_requests
from google.auth import exceptions as _google_exceptions

# Process-wide cache. The google-auth library does NOT cache JWKS by default.
# We share one Request (which uses requests.Session under the hood) so HTTP
# keep-alive amortizes cost. The library still re-fetches on every call —
# we layer a small TTL cache on top.
_GOOGLE_REQUEST = _google_ga_requests.Request()
_JWKS_CACHE: dict = {"fetched_at": None, "raw": None}
_JWKS_TTL_SECONDS = 6 * 60 * 60  # 6h — Google rotates ~daily per docstring
_JWKS_LOCK = asyncio.Lock()


async def verify_google_id_token(
    id_token: str, mobile_client_ids: list[str]
) -> dict:
    """Verify a Google-issued ID token; raise ValueError on any failure.

    audience verification: per google-auth source verify_oauth2_token forwards
    audience to verify_token which accepts list[str] | str | None — passing a
    list verifies aud matches ANY entry. Documented for verify_token; works
    in practice for verify_oauth2_token (call-through).

    Synchronous → wrap with to_thread to avoid blocking event loop.
    """
    if not mobile_client_ids:
        raise ValueError("no mobile client IDs configured")

    def _verify_sync():
        # Library re-fetches JWKS each call; 6h cache layered above means
        # the per-call HTTP is rare. Worst-case (cold start): one HTTPS
        # round-trip ~150ms.
        return _google_id_token.verify_oauth2_token(
            id_token,
            _GOOGLE_REQUEST,
            audience=mobile_client_ids,  # list[str] — see verify_token signature
        )

    try:
        return await asyncio.to_thread(_verify_sync)
    except _google_exceptions.GoogleAuthError as e:
        raise ValueError(f"google id_token rejected: {e}") from e
    except ValueError:
        raise  # already a ValueError from the library — pass through
```

**Critical notes:**
- `verify_oauth2_token`'s docstring says `audience (str)` — but the implementation forwards to `verify_token` which is documented as `audience: Union[str, list[str], None]`. Source confirmed at `google-auth/google/oauth2/id_token.py`. Behavior is consistent across versions ≥2.40. `[CITED: github.com/googleapis/google-auth-library-python source]`
- Google's `_GOOGLE_ISSUERS` allowlist (`accounts.google.com`, `https://accounts.google.com`) is enforced inside `verify_oauth2_token` after `verify_token` returns. We do NOT need to check `iss` ourselves.
- Library uses `pyjwt`'s `PyJWKClient` internally when JWKS is array-format (Google's endpoint IS array-format) — that client has its own caching but it's per-instance, and we're creating a new one per call. The 6h cache layered above amortizes.
- `[ASSUMED]` Layering an additional in-process cache is "good enough" — even without it, ~150ms per Google sign-in is acceptable for an MVP. **Decision flag for plan checker**: if the planner deems the cache complexity not worth it, drop it and document the per-sign-in latency (the dispatcher's bot HTTP call is 600s; one extra 150ms HTTP call to Google is noise). **Recommendation: skip the 6h cache for MVP**, rely on google-auth's default per-call JWKS fetch. Reduces Phase 23 LOC and removes a custom cache that could mask key-rotation incidents.

### Pattern 6: GitHub access-token validation

**What:** Call GitHub's `/user` with the user-supplied access token (validation = call succeeds + returns expected shape). Fall back to `/user/emails` when primary email is private. **Mirrors the existing browser GitHub callback flow byte-for-byte (D-22c-OAUTH-03)** — refactor that flow into a helper that both the browser callback AND the mobile endpoint call.

**When to use:** Validating a non-OIDC OAuth provider's opaque access token by calling its identity endpoint.

**Example:**

```python
# api_server/src/api_server/auth/oauth.py — APPEND

async def verify_github_access_token(access_token: str, http_client) -> dict:
    """Validate a GitHub access token; return profile dict.

    Mirrors the browser GitHub callback flow (D-22c-OAUTH-03):
      1. GET /user with Authorization: Bearer <token>
      2. If email is null, GET /user/emails and pick first primary+verified
      3. Refuse account creation if no verified email is recoverable

    Raises ValueError on any failure mode.
    """
    headers = {"Authorization": f"Bearer {access_token}",
               "Accept": "application/vnd.github+json"}
    try:
        r = await http_client.get(
            "https://api.github.com/user", headers=headers, timeout=10.0,
        )
    except httpx.HTTPError as e:
        raise ValueError(f"github /user fetch failed: {e}") from e
    if r.status_code != 200:
        raise ValueError(f"github access_token rejected (status {r.status_code})")
    profile = r.json()

    if not profile.get("id"):
        raise ValueError("github profile missing id")

    email = profile.get("email")
    if not email:
        try:
            er = await http_client.get(
                "https://api.github.com/user/emails", headers=headers, timeout=10.0,
            )
            er.raise_for_status()
            emails = er.json()
            email = next(
                (e["email"] for e in emails
                 if e.get("primary") and e.get("verified") and e.get("email")),
                None,
            )
        except httpx.HTTPError:
            email = None

    if not email:
        raise ValueError("no verified primary email")

    return {
        "sub": str(profile["id"]),
        "email": email,
        "display_name": profile.get("name") or profile.get("login") or "user",
        "avatar_url": profile.get("avatar_url"),
    }
```

**Critical notes:**
- Reuse the new `app.state.openrouter_http_client` OR construct a per-call client. Passing the client in keeps the helper unit-testable with respx (no global httpx state).
- The browser callback at `routes/auth.py:228-297` has the identical fallback logic. **Refactor opportunity**: extract a single `verify_github_access_token` helper that BOTH the browser callback AND the new `/auth/github/mobile` call. The browser callback obtains the access_token from the OAuth code-exchange; mobile receives it directly from flutter_appauth. Either way, the post-token logic is identical.
- `[VERIFIED: existing routes/auth.py:228-297 — exact pattern documented in source]`

### Anti-Patterns to Avoid

- **Adding a new `mobile_session` cookie/header variant.** Per D-17, mobile sends `Cookie: ap_session=<uuid>` directly. Adding `X-Session-Id` would force ApSessionMiddleware changes and bifurcate the auth surface. Use the existing cookie name.
- **Adding a Pydantic Depends() for require_user on mobile endpoints.** Per D-22c-AUTH-03, the codebase uses inline-early-return `require_user(request)` not `Depends`. Mirror the existing browser-OAuth handler shape.
- **Compressing the `/v1/models` response by hand-rolling gzip.** Add Starlette's GZipMiddleware once in main.py and let it compress every response above the threshold. Hand-rolling is duplicate logic and breaks the fan-out invariant.
- **Putting `Idempotency-Key` REQUIRED in the middleware.** The middleware's "absent header → pass through" semantic is correct for /v1/runs (which doesn't require idempotency). Adding a per-route required-flag in the middleware over-engineers the policy. Handler-level early-return is 3 LOC and keeps the middleware generic.
- **Reusing `app.state.bot_http_client` for OpenRouter.** That client has 600s read timeout for long-running bot calls. The catalog fetch should fail fast (10s). Use a separate `openrouter_http_client`.
- **Caching the `/v1/models` response in JSON-decoded form.** The dumb-client rule says we passthrough bytes; deserialize-then-re-serialize wastes CPU. Cache `r.content` (raw bytes) and return it via `Response(content=cache_bytes, media_type="application/json")`.
- **Caching the OpenRouter ETag and forwarding 304-Not-Modified to clients.** Adds complexity without benefit for our use case (15min TTL is the cheaper invalidation primitive). If/when we need it, the planner can revisit.
- **Returning the cached `/v1/models` response with `Cache-Control: max-age=900`.** The Phase 23 backend serves the catalog to internal clients (web + mobile) — those clients also have their own UI-level state. Letting them set `Cache-Control: no-cache` keeps the cache discipline server-side only. **Decision flag**: planner picks between `private, max-age=300` and `no-store`. **Recommended**: `private, max-age=300` so a same-tab refresh re-uses the response without a server round-trip.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Google ID-token JWT verification | Custom `pyjwt` + JWKS fetch + issuer-allowlist + clock-skew handler | `google-auth.id_token.verify_oauth2_token` | The library handles issuer allowlist (`accounts.google.com` and `https://accounts.google.com`), clock-skew, key rotation, alg=RS256 enforcement. ~80 LOC saved. `[VERIFIED: google-auth source]` |
| HTTP response gzip compression | Custom `gzip.GzipFile` middleware | Starlette `GZipMiddleware` | Already excludes `text/event-stream` by default (verified). Streaming-body-aware. 0 LOC of custom code. `[VERIFIED: starlette source]` |
| Idempotency-Key replay logic | Custom replay store | Existing `IdempotencyMiddleware` | Already lists `/v1/agents/:id/messages` as eligible (line 53-58); already caches 202 responses (line 258). Phase 23 only adds REQUIRED-presence check. |
| In-app chat substrate (dispatcher / outbox / SSE) | Re-build for mobile | Existing Phase 22c.3 substrate | Mobile chat is a second listener on `agent:inapp:<agent_id>` Redis channel; same SSE handler, same DB writes, same Redis pub/sub. Zero new substrate. |
| Session cookie middleware | Mobile-specific session resolver | Existing `ApSessionMiddleware` | Per D-17 the cookie name is the same; the middleware reads cookie OR explicit `Cookie: ap_session=<uuid>` header without distinction. |
| User upsert logic | Re-build for mobile | Existing `auth/oauth.py::upsert_user` | The `UNIQUE (provider, sub) WHERE sub IS NOT NULL` partial index is the dedup primitive. Mobile and browser OAuth both upsert under the same `(provider, sub)` keys — identical user rows whether the user signed in via web or mobile. |
| Session minting | Re-build for mobile | Existing `auth/oauth.py::mint_session` | Same 30-day TTL, same cookie shape. |
| GitHub /user + /user/emails fallback | Mobile-specific helper | Refactor browser callback's logic into a shared helper; mobile + browser both call it | DRY — and the existing logic has been verified by 22c-04..09 tests. |
| Per-agent serialization across channels | Phase 23 mobile-specific queue | Existing dispatcher (D-07) | Single tick + `FOR UPDATE SKIP LOCKED` already enforces one-bot-call-per-agent. Telegram + mobile + web all enqueue via same `inapp_messages` table. |
| BYOK leak defense on chat content | Mobile-specific scrubber | Existing `_BYOK_LEAK_RE` in routes/agent_messages.py:62 | Same regex, same handler — phase 23 changes nothing. |

**Key insight:** Phase 23 is almost entirely glue code. The substrate that does the heavy lifting (chat history, dispatcher, outbox, SSE replay, session resolution, idempotency, user upsert) was shipped in 22c.3 and 22c-oauth-google. The five new mechanisms total roughly 250-350 LOC of net production code; the surface area that planners must reason about is 10x larger because every new line composes with multiple existing layers.

## Runtime State Inventory

> Phase 23 is additive (new endpoints, new middleware, schema-extension via SELECT only). No rename / refactor / migration. **Section omitted by trigger rule.**

## Common Pitfalls

### Pitfall 1: GZip middleware order matters

**What goes wrong:** GZipMiddleware compresses responses based on what the inner app sent. If we add GZipMiddleware AFTER (lower in the stack than) IdempotencyMiddleware, the cached idempotency-replay responses go through GZip — fine. But if added at the wrong layer, headers added by inner middleware (CorrelationId echo, etc.) might get clobbered.

**Why it happens:** Starlette middleware stacks are easy to misorder; the project's existing order has 7 middlewares.

**How to avoid:** Add GZipMiddleware as the OUTERMOST middleware (last in declaration order in `main.py`, since FastAPI's `add_middleware` builds outermost-last). It then sees the final response (including all inner-middleware-added headers) and compresses if appropriate.

**Warning signs:** `Content-Encoding: gzip` appears but headers like `X-Correlation-Id` are missing in the client; or compressed responses have stale Content-Length.

**Concrete instruction:** Place `app.add_middleware(GZipMiddleware, minimum_size=1024)` AT THE TOP of the `add_middleware` block in `main.py:create_app()` — that puts it OUTERMOST in request-in flow, which is what we want. (FastAPI inverts: add_middleware last is outermost? **VERIFY in plan**: read existing order at `main.py:392-408` and place new middleware at the position equivalent to "applied last to outgoing response".) `[VERIFIED via source]`: existing comment at `main.py:384` says "outermost declared last". So `add_middleware(GZipMiddleware)` goes at the BOTTOM of the existing block — after CorrelationIdMiddleware.

### Pitfall 2: The googleapis JWKS endpoint can return RSA keys in either x509 or JWK format

**What goes wrong:** The google-auth library auto-detects format and uses pyjwt's `PyJWKClient` for JWK. PyJWKClient creates a NEW client per call (`jwks_client = jwt_lib.PyJWKClient(certs_url)` line in `verify_token`) — so any pyjwt-side caching is per-call and provides no benefit.

**Why it happens:** Each `verify_token` call constructs a fresh `PyJWKClient`, defeating its built-in caching.

**How to avoid:** Either (a) accept the per-sign-in JWKS HTTP round-trip (~150ms), (b) layer a tiny in-process cache around `verify_oauth2_token`, or (c) construct a single module-level `PyJWKClient` and skip google-auth's wrapper. Option (a) is the simplest and acceptable for MVP. Document the latency.

**Warning signs:** Mobile sign-in latency p95 above 500ms; Google JWKS endpoint shows up in app traces on every sign-in.

### Pitfall 3: respx mocking the JWKS endpoint

**What goes wrong:** Tests that exercise `verify_google_id_token` against a real id_token signed with a deterministic key need the JWKS endpoint mocked to return the matching public key. The naive approach — let the real Google JWKS endpoint respond — causes flaky tests (Google rotates keys, so the test JWT signed with key X is rejected when the real JWKS no longer carries X).

**Why it happens:** RSA signatures need matching public keys; without controlling JWKS we can't produce a deterministic valid token.

**How to avoid:** Use `cryptography` (already in deps) to generate an RSA keypair per test, sign a JWT with the private key, and mock JWKS to return the public key (in JWK format). Pattern:

```python
# In tests/auth/test_oauth_mobile.py
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
import jwt as pyjwt  # already a transitive dep
import json, base64

def _make_test_jwt_and_jwks(claims: dict) -> tuple[str, dict]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key().public_numbers()
    n = base64.urlsafe_b64encode(
        pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big")
    ).rstrip(b"=").decode()
    e = base64.urlsafe_b64encode(pub.e.to_bytes(3, "big")).rstrip(b"=").decode()
    jwks = {"keys": [{
        "kty": "RSA", "use": "sig", "alg": "RS256", "kid": "test-kid",
        "n": n, "e": e,
    }]}
    token = pyjwt.encode(
        claims, pem_priv, algorithm="RS256", headers={"kid": "test-kid"},
    )
    return token, jwks
```

Then in the test:

```python
with respx_oauth_providers() as stubs:
    token, jwks = _make_test_jwt_and_jwks(claims={
        "iss": "https://accounts.google.com",
        "sub": "google-mobile-12345",
        "aud": "mobile-client-id-android.googleusercontent.com",
        "email": "alice@example.com",
        "iat": int(time.time()), "exp": int(time.time()) + 3600,
    })
    # Override the pre-stubbed JWKS to return our test public key
    respx.get("https://www.googleapis.com/oauth2/v3/certs").mock(
        return_value=httpx.Response(200, json=jwks)
    )
    r = await async_client.post("/v1/auth/google/mobile",
                                 json={"id_token": token})
```

`[ASSUMED]` This pattern works because google-auth's `verify_token` falls into the `if "keys" in certs:` JWK branch (line ~95 of id_token.py source) and uses `jwt_lib.PyJWKClient(certs_url)` which fetches our mocked URL via httpx (respx intercepts at the transport layer). **Spike recommended**: planner should validate this in a quick test BEFORE writing all 5 OAuth-mobile coverage cases — if respx interception of `PyJWKClient`'s urllib-based fetch fails (PyJWKClient may use `urllib` not httpx, in which case respx won't intercept), we need a different mocking strategy (e.g., monkeypatch `verify_oauth2_token` itself).

**Warning signs:** Tests fail with "Unable to find a signing key that matches: 'test-kid'" or similar JWKS-mismatch errors.

**Mitigation if respx can't intercept JWKS fetch**: monkeypatch `verify_oauth2_token` at the import site to return a canned claims dict — coarser test coverage but still validates the route handler logic. Document this fallback in the test file docstring.

### Pitfall 4: `last_activity` NULL semantics on cold accounts

**What goes wrong:** A user who has just signed up and has zero agent_instances rows yet sees `GET /v1/agents` return `[]`. That's fine. But a user with one agent_instance and zero runs/zero messages would have `last_run_at IS NULL` AND `MAX(im.created_at) IS NULL` → the GREATEST() expression returns NULL. This is the correct semantic per D-27 ("NULL when user has never run nor messaged"), but the Pydantic model must declare the field as Optional.

**Why it happens:** The expression `GREATEST(NULL, NULL) = NULL` in Postgres.

**How to avoid:** Define `last_activity: datetime | None = None` in the AgentSummary Pydantic model. Mobile UI handles None as "no activity yet — show the create-time timestamp instead" (per D-27). Document the contract clearly in the Pydantic docstring.

**Warning signs:** TypeScript frontend errors at JSON parse with "expected string, got null".

### Pitfall 5: GZipMiddleware and the SSE replay-truncated event

**What goes wrong:** The SSE stream emits multiple chunks over time (replay + live). If GZipMiddleware were applied (it isn't, due to default-exclude), it would buffer chunks until enough bytes accumulated to compress — defeating SSE.

**Why it happens:** Streaming compression has higher minimum-buffer thresholds than non-streaming.

**How to avoid:** Verified solved — Starlette's `DEFAULT_EXCLUDED_CONTENT_TYPES = ("text/event-stream",)` skips compression entirely for SSE responses. The `IdentityResponder.send_with_compression` checks `content_type_is_excluded` and passes the message through verbatim with `await self.send(message)`.

**Warning signs:** SSE clients see all events at once when the response stream closes, instead of as-they-emit. The Wave 0 spike (D-31) catches this.

**Sanity check the spike must verify:** After GZipMiddleware is added, fire an SSE request to `/v1/agents/:id/messages/stream`, post a message via `/v1/agents/:id/messages`, ensure the resulting `inapp_inbound` event arrives at the SSE client BEFORE the connection is closed (not just at end-of-stream).

### Pitfall 6: OpenRouter `Cache-Control: no-store` is a hint, not a binding

**What goes wrong:** OpenRouter sets `Cache-Control: private, no-store` on `/api/v1/models`, suggesting clients shouldn't cache. Some HTTP-cache libraries honor this and refuse to cache.

**Why it happens:** `cache-control: no-store` is meant for shared caches (CDNs, browsers); it's not a contract we're bound by when we re-serve to our own users.

**How to avoid:** Our cache is a manual dict not an HTTP cache layer — the response header is informational for our planning, not a constraint. We respect OpenRouter's wishes loosely (15min TTL, not forever) and document the rationale in the cache module docstring.

**Warning signs:** Plan-checker flags "you're ignoring no-store" — defend with the docstring rationale.

### Pitfall 7: Multi-replica cache divergence

**What goes wrong:** On a multi-worker deployment (uvicorn `--workers 4`), each worker has its own `app.state.models_cache`. Workers refresh independently — at any moment, 4 workers may serve 4 different cached payloads (each up to 15min stale).

**Why it happens:** Per-worker in-memory state by design.

**How to avoid:** Acceptable for MVP — the catalog rarely changes within 15min, and clients re-fetch on UI load. If multi-replica drift becomes a problem (e.g., when Phase 26 introduces multi-host), promote to Redis-backed cache. Document trade-off in the cache service's docstring.

**Warning signs:** None during MVP; flag for v0.4 if multiple replicas land on Hetzner.

### Pitfall 8: The Idempotency-Key middleware caches 202s but the chat-handler emits the message_id from the DB INSERT

**What goes wrong:** The middleware caches the 202 body (`{message_id, status, queued_at}`) on first call and replays it on retry. Good. But if the planner accidentally moves the `INSERT inapp_messages` to BEFORE the require_user check (or before the agent ownership check), an authenticated user retry could leak a row from a different user.

**Why it happens:** Order-of-operations error in the handler. The current order is correct: require_user → fetch_agent_instance (ownership) → BYOK leak check → INSERT pending → return 202. If anyone reorders, the bug lands.

**How to avoid:** Plan execution must NOT reorder the existing handler steps. The Idempotency-Key REQUIRED check goes at the very top (BEFORE require_user), since a missing-header 400 is independent of auth.

**Warning signs:** A user sees a `message_id` belonging to a different user's agent in their idempotency replay.

### Pitfall 9: GitHub access-token validation — token can be expired or revoked between mobile sign-in and our /user call

**What goes wrong:** flutter_appauth gets a fresh access_token, mobile sends it to us, we call GitHub /user — but if the user revoked the token (or it expired) between issue and our call, we get a 401 from GitHub. Our verify_github_access_token raises ValueError → we return 401 to the mobile client.

**Why it happens:** Access tokens are not infallible.

**How to avoid:** Document this in the mobile client error-handling: "401 from /v1/auth/github/mobile means the access_token was rejected by GitHub — re-run sign-in flow." flutter_appauth's standard retry path handles this.

**Warning signs:** None to detect early; the mobile retry flow is well-defined.

## Code Examples

Verified patterns from official sources and live source.

### Example 1: Existing IdempotencyMiddleware passthrough behavior (`POST /v1/runs` — currently optional)

```python
# api_server/src/api_server/middleware/idempotency.py — VERIFIED
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return
    method = scope.get("method") or ""
    path = scope.get("path") or ""
    if not _is_idempotency_eligible(method, path):
        await self.app(scope, receive, send)
        return

    # Idempotency-Key header is optional. When absent, we pass
    # through and the endpoint runs exactly once per request with
    # no caching — the default Stripe semantic.
    key_bytes = _get_header(scope, b"idempotency-key")
    if key_bytes is None:
        await self.app(scope, receive, send)
        return
    # ...
```

`[VERIFIED: middleware/idempotency.py:152-174]`

**Phase 23 implication**: the middleware will continue to pass through when header is absent. The HANDLER must enforce required-presence — the middleware semantic stays correct for /v1/runs (optional) AND /v1/agents/:id/messages (required-via-handler-check).

### Example 2: Existing `make_error_envelope` Stripe-shape helper

```python
# api_server/src/api_server/models/errors.py — referenced via import
# Used pattern in routes/agent_messages.py:78-97:

def _err(
    status: int, code: str, message: str,
    *, param: str | None = None, category: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param, category=category),
    )
```

Phase 23 routes mirror this verbatim. `ErrorCode.UNAUTHORIZED` for 401, `ErrorCode.INVALID_REQUEST` for 400 missing-header / invalid-shape, `ErrorCode.AGENT_NOT_FOUND` for 404 — all already in the enum (`models/errors.py`).

### Example 3: Existing respx_oauth_providers fixture (reuse pattern)

```python
# api_server/tests/conftest.py:590-655 — VERIFIED LIVE
@pytest.fixture
def respx_oauth_providers():
    @contextmanager
    def _ctx():
        with respx.mock(assert_all_called=False) as m:
            m.get("https://accounts.google.com/.well-known/openid-configuration") \
                .mock(return_value=httpx.Response(200, json=_GOOGLE_DISCOVERY))
            m.get("https://www.googleapis.com/oauth2/v3/certs") \
                .mock(return_value=httpx.Response(200, json={"keys": []}))
            stubs = {
                "google_token": m.post("https://oauth2.googleapis.com/token"),
                "google_userinfo": m.get("https://openidconnect.googleapis.com/v1/userinfo"),
                "github_token": m.post("https://github.com/login/oauth/access_token"),
                "github_user": m.get("https://api.github.com/user"),
                "github_user_emails": m.get("https://api.github.com/user/emails"),
            }
            yield stubs
    return _ctx
```

**Phase 23 extension pattern**: tests for mobile OAuth use `respx_oauth_providers` AS-IS, then override the JWKS stub per-test with the real test public key (Pitfall 3). NEW stubs may be added if mobile needs to call additional URLs (it doesn't — only Google JWKS + GitHub /user/{,emails}).

### Example 4: Reuse of `upsert_user` + `mint_session` (verified contracts)

```python
# api_server/src/api_server/auth/oauth.py:159-238 — VERIFIED LIVE

async def upsert_user(
    conn: "asyncpg.Connection",
    *, provider: str, sub: str,
    email: str | None, display_name: str, avatar_url: str | None,
) -> UUID: ...

async def mint_session(
    conn: "asyncpg.Connection",
    *, user_id: UUID, request: "Request",
) -> str: ...
```

**Phase 23 mobile flow**:

```python
async with pool.acquire() as conn:
    user_id = await upsert_user(
        conn,
        provider="google",  # or "github"
        sub=str(claims["sub"]),
        email=claims.get("email"),
        display_name=claims.get("name") or "user",
        avatar_url=claims.get("picture"),
    )
    session_id = await mint_session(conn, user_id=user_id, request=request)
```

This is byte-identical to the existing browser callback at `routes/auth.py:189-203` — 0 risk of behavioral drift.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Block-and-wait HTTP for chat reply | Fast-ack 202 + SSE for reply | Phase 22c.3 (2026-04-19) | Enables seconds-to-minutes bot responses without HTTP timeout; mobile carriers no longer cause request abort |
| New `messages` table for chat history | Reuse `inapp_messages` (single source) | Phase 23 D-01 (2026-05-01) | Zero new migrations; same rows web + mobile read |
| Dev-mode auth shim | Real OAuth via native Flutter SDKs | Phase 23 D-15 (2026-05-01) | Removes shim cleanup burden post-MVP |
| Direct OpenRouter fetch from frontend | Backend `/v1/models` proxy + cache | Phase 23 D-21 (2026-05-01) | Closes Golden Rule #2 violation; mobile + web share the catalog |
| `Authorization: Bearer <session>` (mobile) | `Cookie: ap_session=<uuid>` header | Phase 23 D-17 (2026-05-01) | Backwards-compatible with web; deferred bearer-session migration to post-MVP |
| Manual SSE streaming-buffer awareness | Trust Starlette default-excludes SSE | Phase 23 D-31 (2026-05-01) | Reduces middleware-config surface; spike validates |

**Deprecated/outdated:**
- Spec API-01's `/chat` URL naming → DROPPED (D-14 + D-32 amendment); use existing `/messages` URL.
- Spec API-06's new `messages` table → DROPPED (D-01 + D-32 amendment); reuse `inapp_messages`.
- Spec API-05's dev-mode auth shim → DROPPED (D-15 + D-32 amendment); real mobile OAuth.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `verify_oauth2_token` accepts a list audience in practice (forwards to `verify_token` which is documented `list[str] \| str \| None`) | Pattern 5 | LOW — if it doesn't, fall back to manual aud-claim check after calling with `audience=None`. Spike-verifiable in Wave 0 with one line: `id_token.verify_oauth2_token(jwt, req, audience=["a","b"])` should not raise if jwt's aud is "a" |
| A2 | respx intercepts the JWKS HTTP fetch made by google-auth's `PyJWKClient` instance | Pitfall 3 | MEDIUM — if PyJWKClient uses urllib not httpx, respx misses the call. Mitigation: monkeypatch `verify_oauth2_token` import-site to return canned claims; coarser but still validates handler logic. Spike-verifiable in Wave 0 |
| A3 | `inapp_messages.agent_id` has an index `(agent_id, created_at)` | Pattern 2 | LOW — verified by reading migration 007 source ahead of plan-seal |
| A4 | OpenRouter `/api/v1/models` will continue to be public unauthenticated | Empirical probe + Pattern 3 | MEDIUM — if OpenRouter starts requiring auth on this endpoint, /v1/models needs platform key injection. Mitigation: backend already has `OPENROUTER_API_KEY` in docker-compose env (verify); adding `Authorization: Bearer ${OPENROUTER_API_KEY}` to the proxy fetch is 1 LOC if needed |
| A5 | The 6h JWKS cache layered atop google-auth provides material latency benefit | Pattern 5 | LOW — recommendation is to skip the cache for MVP and accept ~150ms per Google sign-in; if planner agrees, this risk is eliminated |
| A6 | OpenRouter unauthenticated `/api/v1/models` has no per-IP rate limit at our usage rate (~4/h/replica) | Empirical probe + Sec. Common Pitfalls | LOW — well below any plausible WAF threshold; stale-while-revalidate (D-18) covers transient blocks |
| A7 | Starlette ≥0.46.0 is in the dep tree at runtime (FastAPI 0.136.0 transitively requires it) | Pattern 1, Pitfall 5 | LOW — FastAPI 0.136.0 hard-requires `starlette>=0.46.0` (verified in PyPI metadata); add an explicit `starlette>=0.46.0` pin to api_server/pyproject.toml as defense-in-depth |

## Open Questions (RESOLVED)

> **Status (2026-05-01, post plan-checker iteration 1):** All five questions below received explicit dispositions before plan seal. Each question carries a `RESOLVED:` line stating the disposition and the plan that owns the decision. Future readers of this section: do NOT re-litigate; consult the named plan instead.

1. **Should `app.state.models_cache` use `asyncio.Lock` for first-fetch dedup?**
   - What we know: D-18 says "in-process dict cache, 15min TTL, stale-while-revalidate on fetch failure". Claude's Discretion includes this question.
   - What's unclear: At MVP load (single-user demo, ~5 RPS peak) the lock is unnecessary. At higher load, multiple cold-start concurrent first-fetches can fan out 50 OpenRouter calls in 100ms.
   - Recommendation: **Add the lock**. It's 5 LOC, future-proof, and cheap. Pattern 3 above shows the implementation.
   - **RESOLVED: ADOPTED in Plan 23-05** — `must_haves.truths` includes "Concurrent first-fetches are deduped by an asyncio.Lock so only one upstream HTTP call fires under a thundering herd"; service module wires `state.models_cache_lock` with double-check pattern. See `23-05-PLAN.md` Task 1.

2. **Should the `/v1/models` response set `Cache-Control: private, max-age=300` on the wire?**
   - What we know: D-20 says "passthrough", which suggests no header rewriting.
   - What's unclear: OpenRouter sets `Cache-Control: private, no-store` upstream; do we forward it (which discourages browser caching) or override (which encourages a 5min browser cache)?
   - Recommendation: **Override to `private, max-age=300`** so a Flutter app reload within 5min skips the round-trip. Document in the route handler docstring. (Decision flag for plan checker.)
   - **RESOLVED: IMPLEMENTED in Plan 23-05** — the route handler `routes/models.py::list_models` sets `Cache-Control: private, max-age=300` on every 200 response (single header line — does NOT violate D-20 passthrough since D-20 is about response BODY bytes, not headers). The 5-min mobile-side cache complements the 15-min in-process server cache (mobile reload UX). Acceptance criterion: `pytest tests/routes/test_models.py -x -k cache_control_header` (or equivalent header assertion in an existing test in the same file). See `23-05-PLAN.md` Task 1 + Task 3.

3. **Mobile `/v1/auth/{google,github}/mobile` response: include the user object inline OR mint a session and let the client fetch /v1/users/me separately?**
   - What we know: D-16 says "return `{session_id, expires_at, user: <SessionUserResponse shape>}`".
   - What's unclear: Adding the user object inline saves the mobile client one round-trip on sign-in; downside is mild duplication of the /users/me serializer.
   - Recommendation: **Inline the user**. D-16 already specifies the shape — 0 ambiguity. Mobile UX is faster.
   - **RESOLVED: ADOPTED in Plan 23-06** — mobile auth endpoints return `{session_id, expires_at, user: SessionUserResponse}` inline; matches D-16 spec verbatim. See `23-06-PLAN.md` mobile-endpoint task.

4. **Should we add `starlette>=0.46.0` as a direct pin in api_server/pyproject.toml even though FastAPI already transitively pins it?**
   - What we know: FastAPI 0.136.0's metadata declares `starlette>=0.46.0`.
   - What's unclear: A future fastapi version might bump or relax.
   - Recommendation: **Yes, add direct pin**. Defense-in-depth for the SSE-exclude behavior we depend on. ~1 LOC.
   - **RESOLVED: IMPLEMENTED in Plan 23-01** — Plan 23-01 Task 4 adds `"starlette>=0.46"` to `[project.dependencies]` in `api_server/pyproject.toml` alongside the `google-auth` direct-dep promotion. Acceptance criterion: `grep -E '^starlette\s*>=' api_server/pyproject.toml` returns ≥1 hit AND the version constraint is `>=0.46`. See `23-01-PLAN.md` Task 4.

5. **Should `app.state.openrouter_http_client` be lifespan-owned (cleanup on shutdown) or per-request?**
   - What we know: The existing `bot_http_client` is lifespan-owned (`main.py:137`).
   - What's unclear: nothing — mirror the existing pattern.
   - Recommendation: **Lifespan-owned** with `aclose()` in the shutdown drain.
   - **RESOLVED: ADOPTED in Plan 23-05** — `must_haves.truths` includes "OpenRouter HTTP client lives on app.state with 10s timeout, lifecycle-managed by lifespan; teardown closes it before the pool". See `23-05-PLAN.md` Task 2.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Runtime | ✓ | 3.13 | — |
| Postgres 17 | Tests + runtime | ✓ via testcontainers | 17-alpine | — |
| Redis 7 | Tests + runtime | ✓ via testcontainers | 7-alpine | — |
| Docker daemon | E2E tests | ✓ | (host) | — |
| `google-auth` Python | Mobile JWT verify | ✓ | 2.40.3 (transitive) | — (must be promoted to direct dep) |
| `respx` | Tests | ✓ pinned | >=0.22,<0.24 | — |
| `cryptography` | Test JWT signing (Pitfall 3) | ✓ pinned | >=42 | — |
| `pyjwt` | Test JWT signing (Pitfall 3) | ✓ transitive via google-auth | 2.12.1 | — (acceptable as transitive for test-only use) |
| Internet to `openrouter.ai` | Runtime | ✓ verified | — | Stale-while-revalidate covers transient drops |
| Internet to `googleapis.com` | Runtime (mobile sign-in) | ✓ assumed | — | Mobile sign-in is rare; transient drop = user retries; no fallback |
| Internet to `api.github.com` | Runtime (mobile sign-in) | ✓ assumed | — | Same |
| `OPENROUTER_API_KEY` env var | E2E tests (`make e2e-inapp-docker`) | ✓ user-provided | — | E2E target gates on its presence |
| `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS` env var | Mobile Google sign-in | ✗ NEW | — | None — must be configured (deploy/.env.dev.example update is in scope) |

**Missing dependencies with no fallback:**
- `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS` is a new required-in-prod env var. In dev, the helper `_resolve_or_fail` (in `auth/oauth.py`) should accept missing values with a placeholder (`["dev-mobile-placeholder"]`) so tests boot. In prod, fail-loud at app startup if missing AND any user attempts mobile sign-in.

**Missing dependencies with fallback:**
- None.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23+ (asyncio_mode="auto") |
| Config file | `api_server/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd api_server && pytest -x -m "not api_integration"` (~30s, no docker) |
| Full suite command | `cd api_server && pytest tests/` (with docker — testcontainers boot Postgres + Redis) |
| E2E gate command | `cd api_server && make e2e-inapp-docker` (requires Docker + OPENROUTER_API_KEY env) |
| Spike file location | `api_server/tests/spikes/` (already convention) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| API-01 | Idempotency-Key header REQUIRED → 400 envelope when missing | unit + integration (httpx ASGITransport) | `pytest tests/routes/test_messages_idempotency_required.py -x` | ❌ Wave 0 |
| API-01 | Idempotency-Key replay returns same `message_id` | integration | `pytest tests/test_idempotency.py -x` (existing — extend if needed) | ✅ existing covers /v1/runs path; extend to /messages |
| API-02 | GET /v1/agents/:id/messages — order ASC, default 200, max 1000 | unit + integration | `pytest tests/routes/test_agent_messages_get.py -x` | ❌ Wave 0 (NEW route handler) |
| API-02 | done rows emit (user, assistant) pair; failed rows emit (user, error) pair | integration | same | ❌ |
| API-03 | GET /v1/agents includes `status` from agent_containers | integration (real container insert via fixture) | `pytest tests/routes/test_agents_status_field.py -x` | ❌ Wave 0 |
| API-03 | GET /v1/agents includes `last_activity` (max of last_run_at + im.created_at) | integration | same | ❌ |
| API-03 | `last_activity` is None when no runs/messages | unit | same | ❌ |
| API-04 | GET /v1/models cache miss → fetch + cache | integration (respx mocks OpenRouter) | `pytest tests/routes/test_models.py -x` | ❌ Wave 0 |
| API-04 | GET /v1/models cache hit within 15min → no refetch | integration | same | ❌ |
| API-04 | GET /v1/models stale-while-revalidate on fetch failure | integration | same | ❌ |
| API-04 | GZipMiddleware compresses /v1/models response (≥1024 bytes) | integration | same (assert response headers contain `content-encoding: gzip` when `Accept-Encoding: gzip`) | ❌ |
| API-05 | POST /v1/auth/google/mobile happy path | integration (respx mocks JWKS, real Postgres) | `pytest tests/auth/test_oauth_mobile.py -x -k google_happy` | ❌ Wave 0 |
| API-05 | POST /v1/auth/google/mobile invalid signature → 401 | integration | `pytest tests/auth/test_oauth_mobile.py -x -k google_invalid_sig` | ❌ |
| API-05 | POST /v1/auth/google/mobile expired token → 401 | integration | `pytest tests/auth/test_oauth_mobile.py -x -k google_expired` | ❌ |
| API-05 | POST /v1/auth/google/mobile audience mismatch → 401 | integration | `pytest tests/auth/test_oauth_mobile.py -x -k google_aud_mismatch` | ❌ |
| API-05 | POST /v1/auth/google/mobile missing required claims → 401 | integration | `pytest tests/auth/test_oauth_mobile.py -x -k google_missing_claims` | ❌ |
| API-05 | POST /v1/auth/github/mobile happy path public email | integration (respx) | `pytest tests/auth/test_oauth_mobile.py -x -k github_public_email` | ❌ |
| API-05 | POST /v1/auth/github/mobile private email → /user/emails fallback | integration | `pytest tests/auth/test_oauth_mobile.py -x -k github_private_email` | ❌ |
| API-05 | POST /v1/auth/github/mobile invalid token → 401 | integration | `pytest tests/auth/test_oauth_mobile.py -x -k github_invalid_token` | ❌ |
| API-05 | Mobile session-cookie continuity (sign in → use Cookie header on next request → 200) | integration | `pytest tests/auth/test_oauth_mobile.py -x -k cookie_continuity` | ❌ |
| API-06 | Replaced by reuse of inapp_messages — VERIFY no `messages` table created | unit | `pytest tests/test_migration.py` (existing — assert no rogue migration exists) | ✅ existing |
| API-07 | Real Postgres + real Docker for chat-proxy round-trip | E2E | `make e2e-inapp-docker` | ✅ existing target — Phase 23 shouldn't break it |
| D-31 | GZipMiddleware + SSE compatibility (chunks not buffered) | spike (integration) | `pytest tests/spikes/test_gzip_sse_compat.py -x` | ❌ Wave 0 spike — MUST PASS BEFORE PLAN SEALS |

### Sampling Rate

- **Per task commit:** `pytest -x -m "not api_integration"` — covers the unit + ASGITransport-only integration tests in <30s.
- **Per wave merge:** `pytest tests/` (full suite including testcontainer-backed tests) — ~3-4 min including Postgres+Redis container boot.
- **Phase gate (`/gsd-verify-work`):** Full suite green AND `make e2e-inapp-docker` green.

### Wave 0 Gaps

- [ ] `tests/spikes/test_gzip_sse_compat.py` — D-31 mandatory spike. Configure GZipMiddleware, fire SSE stream, assert per-chunk delivery (NOT batched at end). **PLAN BLOCKS UNTIL THIS PASSES.**
- [ ] `tests/auth/test_oauth_mobile.py` — covers API-05 (9 cells in matrix per D-30).
- [ ] `tests/routes/test_messages_idempotency_required.py` — covers API-01 D-09 enforcement.
- [ ] `tests/routes/test_agent_messages_get.py` — covers API-02 (new GET handler for chat history per D-03+D-04).
- [ ] `tests/routes/test_agents_status_field.py` — covers API-03 (status + last_activity).
- [ ] `tests/routes/test_models.py` — covers API-04 (cache hit/miss, stale-while-revalidate, gzip header).
- [ ] (Optional) `tests/spikes/test_google_auth_multi_audience.py` — Spike A1: confirm `verify_oauth2_token(audience=[a,b])` accepts JWTs whose aud matches either entry. **5 minutes of plan-checker time saved if proven before plan-seal.**
- [ ] (Optional) `tests/spikes/test_respx_intercepts_pyjwk_fetch.py` — Spike A2: confirm respx intercepts the JWKS HTTP fetch made by google-auth's PyJWKClient. If FAILS, plan must use monkeypatch fallback.

Framework install: NONE. All test deps already in `api_server/pyproject.toml`.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | google-auth + manual GitHub /user validation; existing mint_session 30-day TTL; existing httpOnly + samesite=lax cookie |
| V3 Session Management | yes | Existing ApSessionMiddleware; PG-backed session row with revoked_at + expires_at; deletion on logout (D-22c-AUTH-01..04) |
| V4 Access Control | yes | Existing require_user pattern; SQL-level user_id filter on all queries (defense-in-depth) |
| V5 Input Validation | yes | Pydantic Field(min_length=1) on `id_token` and `access_token`; Pydantic regex/UUID coercion on `agent_id` path param; existing `_BYOK_LEAK_RE` content scrub |
| V6 Cryptography | yes | google-auth handles RS256 verify + JWKS rotation; pyjwt is the underlying lib; **NEVER hand-roll** |
| V7 Errors & Logging | yes | Existing make_error_envelope(); existing log_redact middleware; mobile credential errors log a generic "rejected" without echoing the token |
| V9 Communications | yes | TLS terminated at Caddy in prod; Cookie set Secure when AP_ENV=prod (existing pattern); mobile sign-in over TLS (Flutter app's responsibility) |
| V11 Business Logic | yes | Idempotency-Key REQUIRED on chat send (D-09) prevents double-spend; per-agent serialization (D-07) prevents bot-call interleave |
| V13 API & Web Service | yes | Existing rate-limit middleware applies to new endpoints; existing CORS posture |

### Known Threat Patterns for FastAPI + asyncpg + httpx + google-auth

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| JWT signature bypass via `alg=none` | Tampering | google-auth pins RS256; rejects unsigned tokens |
| JWT audience-confusion (token issued for app A used to sign in to app B) | Spoofing | `audience=mobile_client_ids` list verifies aud matches expected mobile clients only |
| JWT expiration bypass | Spoofing | `verify_oauth2_token` validates `exp` and `iat` (with optional clock_skew_in_seconds) |
| JWKS poisoning (attacker MITM the JWKS endpoint) | Tampering | TLS to googleapis.com; google-auth uses HTTPS by default |
| GitHub access-token replay attack | Spoofing | We validate per-call by hitting GitHub /user; revoked tokens fail naturally; we never trust client-side claims |
| Idempotency-Key collision across users (replay another user's response) | Information Disclosure | Existing IdempotencyMiddleware `(user_id, key)` composite primary key; cross-user isolation tested in 22c-09 |
| Cross-user data leak in `GET /v1/agents` | Information Disclosure | SQL `WHERE ai.user_id = $1` filter; LATERAL JOINs all keyed on ai.id which is gated; existing pattern |
| OpenRouter response injection (CDN tampering) | Tampering | TLS to openrouter.ai; we passthrough bytes; if the bytes contain script tags, Flutter doesn't execute HTML |
| GZip "BREACH" attack on SSE | Information Disclosure | SSE excluded from compression by default — verified |
| Cookie-stealing on `Cookie: ap_session=<uuid>` over HTTP in dev | Information Disclosure | dev-only; AP_ENV=prod enables Secure cookie flag; doc'd risk |
| Idempotency-Key as a token leak (used to enumerate user activity) | Information Disclosure | Idempotency keys are user-supplied UUIDs; not server-generated; not logged after redaction |

### Phase 23-specific security flags

- **Mobile client ID disclosure**: `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS` is non-secret (Google client IDs are public) — they appear in the mobile app binary. NOT a credential leak risk.
- **Mobile id_token logging**: Per existing log_redact middleware patterns, `id_token` body field MUST be redacted from request-body logs. Verify in plan.
- **GitHub `access_token` logging**: Same — redact in middleware. The Phase 22c log_redact already handles `Authorization` header; verify body-field redaction works for `access_token`.

## Sources

### Primary (HIGH confidence)

- **Live source: `api_server/src/api_server/routes/agent_messages.py`** — verified D-09 enforcement site, line 119-180 post_message handler structure, existing _err helper at line 78-97
- **Live source: `api_server/src/api_server/middleware/idempotency.py`** — verified path eligibility list at line 53-73, 202 caching at line 258
- **Live source: `api_server/src/api_server/auth/oauth.py`** — verified upsert_user (159-197), mint_session (207-238) signatures
- **Live source: `api_server/src/api_server/routes/auth.py`** — verified browser callback flow + GitHub /user/emails fallback (228-297)
- **Live source: `api_server/src/api_server/main.py`** — verified middleware order (392-408), bot_http_client lifecycle (137-140), state attribute pattern
- **Live source: `api_server/src/api_server/services/run_store.py`** — verified list_agents (78-114), fetch_agent_instance (445-479)
- **Live source: `api_server/src/api_server/middleware/session.py`** — verified ApSessionMiddleware reads cookie OR explicit header (90-98)
- **Live source: `api_server/tests/conftest.py`** — verified TRUNCATE 8-table list (175-180), respx_oauth_providers fixture (590-655), authenticated_cookie fixture (510-553)
- **Live source: `api_server/Makefile`** — verified `e2e-inapp-docker` target (lines 1-80)
- **Live source: `api_server/pyproject.toml`** — verified pin map for fastapi/starlette/httpx/respx/google-auth (transitive)
- **Empirical probe: `curl https://openrouter.ai/api/v1/models`** — HTTP 200 unauthenticated, 429798 bytes, 0.286s, top-level `{data: [371 models]}`, `cache-control: private, no-store`, `access-control-allow-origin: *`
- **Empirical probe: `curl -H "Accept-Encoding: gzip" https://openrouter.ai/api/v1/models`** — gzip body 50304 bytes (~88% compression)
- **Source verify: `starlette/middleware/gzip.py`** — `DEFAULT_EXCLUDED_CONTENT_TYPES = ("text/event-stream",)` confirmed in installed venv (starlette 0.47.2) AND main branch
- **Source verify: `google-auth/google/oauth2/id_token.py`** — `verify_token` signature `audience: Union[str, list[str], None]`; `verify_oauth2_token` forwards audience to verify_token
- **PyPI metadata 2026-04-30**: google-auth 2.50.0, starlette 1.0.0, sse-starlette 3.4.1, fastapi 0.136.1, respx 0.23.1, cryptography 47.0.0, pyjwt 2.12.1
- **Starlette release notes** — version 0.46.0 PR #2871 added `text/event-stream` exclusion (CITED: starlette.io/release-notes 2025-02-22)

### Secondary (MEDIUM confidence)

- **Google official docs**: [Authenticate with a backend server](https://developers.google.com/identity/sign-in/web/backend-auth) — multi-audience pattern documented as manual-after-call but practitioners pass list directly
- **OpenRouter docs**: response shape (data array of model objects) cross-confirmed with empirical probe
- **GitHub Issue #732 (google-auth-library-python)**: confirms multi-audience support is implemented in `verify_token`

### Tertiary (LOW confidence)

- **respx interception of PyJWKClient internal HTTP** — not directly verified; A2 spike recommended in Wave 0
- **OpenRouter unauthenticated rate limit ceiling** — not documented for `/api/v1/models`; assumed safe at 4 fetches/h/replica (worst-case 1 spike per 15 min)

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — all libraries either already in pinned deps or canonical (google-auth)
- Architecture: **HIGH** — mirrors Phase 22c.3 dispatcher pattern + Phase 22c-oauth-google verbatim; substrate is shipped and tested
- Pitfalls: **HIGH** — derived from live source inspection + empirical probes; 9 pitfalls documented with concrete mitigations
- Test scaffolding: **HIGH** — existing `respx_oauth_providers` + `authenticated_cookie` patterns directly extensible
- GZip × SSE compatibility: **HIGH** — verified at source level (Starlette default-exclude); spike is regression-prevention not discovery
- Mobile JWT verification: **MEDIUM-HIGH** — google-auth library well-established but multi-audience semantic is documented for `verify_token` not `verify_oauth2_token` (A1)
- respx-mocking JWKS: **MEDIUM** — works in principle, A2 spike recommended

**Research date:** 2026-05-01
**Valid until:** 2026-06-01 (30 days — stable substrate, slow-moving libraries; bump if google-auth or starlette ship a major)
