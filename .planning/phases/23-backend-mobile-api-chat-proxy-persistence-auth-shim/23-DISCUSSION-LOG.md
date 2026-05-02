# Phase 23: Backend Mobile API — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `23-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-01
**Phase:** 23 — Backend Mobile API (chat-proxy + persistence + auth shim)
**Areas discussed:** Persistence model, Chat-proxy architecture, Auth shim, Models proxy, +4 second-pass + 4 third-pass extras
**Discussion mode:** interactive (3 passes)

---

## Pre-discussion scout findings (re-shaped the gray areas)

Before any questions, the scout uncovered five facts that invalidated assumptions in `mobile-mvp-decisions.md`:

1. **OAuth (Phase 22c-oauth-google) HAS shipped** — all 9 plans complete, browser flow + ap_session cookie + require_user + SessionMiddleware all live. (Memory note said "planned-not-executed".)
2. **Migration 007 already shipped `inapp_messages`** — schema with `bot_response` column, NOT a two-row `(role, content)` model. Spec API-06 wanted a brand new `messages` table.
3. **`POST /v1/agents/:id/messages` already exists** — Phase 22c.3-08 ships fast-ack outbox + 3-contract dispatcher + SSE outbound.
4. **`GET /v1/agents` already exists** — current shape `{id, name, recipe_name, model, personality, created_at, last_run_at, total_runs, last_verdict}`. Spec API-03 wants a slightly different shape.
5. **`frontend/components/playground-form.tsx:169` does `fetch("https://openrouter.ai/api/v1/models")` direct** — current Golden-Rule-#2 violation that the new `/v1/models` proxy must close.

These findings shifted the gray-area set toward "what to reuse vs. what to add" rather than "what to build from scratch."

---

## Initial gray-area selection (multi-select)

**Question:** Which gray areas to discuss for Phase 23?
**Selected:** All four (Persistence, Chat-proxy, Auth, Models) + user note: "dude, web interface already does part... shows agents and models, inputs for telegram bot stuf, etc"

User note triggered an additional scout: web frontend has a working dashboard + playground deploy form already. Mobile is essentially a Flutter port of a partially-working web flow.

---

## Area: Persistence model

### Q1: Where does mobile chat history live?

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse `inapp_messages` | Single source of truth. Existing schema + indexes. Two roles emitted from one row via content + bot_response. | ✓ |
| New `messages` table | Spec verbatim. Two-row role-based model. Creates parallel persistence. | |
| Hybrid: messages VIEW | Postgres VIEW unioning inapp_messages rows. Read shape matches spec, write path unchanged. | |

**Selected:** Reuse `inapp_messages` → **D-01.**

### Q2: URL `:id` resolution?

| Option | Description | Selected |
|--------|-------------|----------|
| `agent_instances.id` | Matches existing 22c.3 inapp contract verbatim. inapp_messages.agent_id FK already targets here. | ✓ |
| `agent_containers.id` | What spec API-06 said when it was a new table. Forces a translation layer. | |
| Mixed by endpoint | Asymmetric. Easy footgun. | |

**Selected:** `agent_instances.id` → **D-02.**

### Q3: Visible row statuses on GET /messages?

| Option | Description | Selected |
|--------|-------------|----------|
| Done + Failed (with sentinel) | Failed rows emit `"⚠️ delivery failed: <last_error>"` assistant-row with kind:'error'. Prevents silent ghost UX. | ✓ |
| Done only | Cleanest timeline but failed messages vanish from view. | |
| All non-pending | Includes in-flight rows. Most chat-app-like but client must poll/stream to update. | |

**Selected:** Done + Failed with sentinel → **D-03.**

### Q4: Ordering and limits?

| Option | Description | Selected |
|--------|-------------|----------|
| ASC, default 200, max 1000 | Per REQUIREMENTS API-02 verbatim. | ✓ |
| ASC, default 50, max 500 | Tighter defaults. | |
| DESC + reverse client-side | Better when pagination ships, overkill for MVP. | |

**Selected:** ASC, default 200, max 1000 → **D-04.**

---

## Area: Chat-proxy architecture

### Q1 (initial — rejected/clarified): Sync return mechanism for POST /chat

User asked clarification before answering: "extract to bot, seems correct. but, lets think. how its today? via e2e.. right now, using completions route? we get a return sicnronously, right. want to test? so, caller (web, app or WS, webhook) receives answer. middleman, middleware maybe, stores, persists, idk"

**Response:** I described today's flow (POST→fast-ack→dispatcher 250ms tick→bot 5-30s→outbox→SSE) and surfaced the dispatcher race condition.

User pushback: "race condition??????"

**Response:** Verified the claim from `inapp_messages_store.py:66-73` (insert_pending auto-commits) + dispatcher's `WHERE m.status='pending'` SELECT. Confirmed race exists if handler does naive INSERT-then-forward across two transactions; trivially mitigable by inserting `forwarded` directly.

### Q2 (after user surfaced more sub-questions): Comprehensive doubts

User: "any doubts? gray areas?"

**Response:** Enumerated 7 sub-grays:
1. Mobile timeout vs bot timeout mismatch
2. Container not running
3. Concurrent-send serialization
4. Outbox emission for cross-channel
5. Idempotency on retry
6. GET /v1/agents shape mismatch
7. agent_containers row resolution

User answered inline (not via AskUserQuestion):
1. "API receives the inference. stores. then, either mobile re-asks, or webhook" → **D-05** (backend completes regardless of client disconnect)
2. "UI will prevent chat with agent not running" → **D-06** (fail fast, no auto-start)
3. "dont complicate, for now.. if user sends message via telegram and via app, forwards first to agent, wait answer, forwards next" → **D-07** (per-agent serialization across channels)
4. "web and inapp history must be aligned always" → **D-08** (cross-channel alignment via outbox)
5. "explain me more" → triggered idempotency follow-up
6. "only status missing, right? use as is, status must derive from healthcheck from container/agent" → **D-10** (extend GET /v1/agents with status field)
7. "wtf man, message will always be to a single containner" → **D-11** (single non-stopped container per instance)

### Q3: Idempotency-Key behavior?

| Option | Description | Selected |
|--------|-------------|----------|
| Required (400 if missing) | Mobile generates UUID per Send. Middleware caches response. Safest. | ✓ |
| Recommended (warn) | Header optional, double-bot-call possible on retry. | |
| Off | Ignore header entirely. Riskiest. | |

**Selected:** Required → **D-09.**

### Q4: Sync budget for POST /chat?

User pushback: "dude, agents can take minutes to reply sometimes. seconds to 10 or more minutes"

**Response:** Re-framed — the locked "block-and-wait" was authored assuming sub-3s replies. Mobile carriers reset idle TCP at 60-120s, far shorter than agent runs. Re-asked architecture.

### Q5: Sync vs fast-ack (revisit)?

| Option | Description | Selected |
|--------|-------------|----------|
| Pure fast-ack + poll | POST /chat returns 202 in <1s. Client polls GET /messages. Single shape. Trivial streaming-later path. | ✓ |
| Sync-attempt up to 60s, fallback | Dual return shape, dual client logic, hard to reason about. | |
| Sync-attempt up to 30s | Same with tighter window. | |

**Selected:** Pure fast-ack + poll → **D-12** (later superseded by D-14).

### Q6: Poll or websocket?

User asked: "poll or websocket"

**Response:** Verified existing infra — `GET /v1/agents/:id/messages/stream` SSE endpoint already ships from Phase 22c.3-08, backed by Redis pub/sub `agent:inapp:<agent_instance_id>` and outbox pump. WebSocket would be net-new infra. Reframed as poll vs SSE.

| Option | Description | Selected |
|--------|-------------|----------|
| SSE (reuse /messages/stream) | Real-time UX. Backend reuses 100% existing infra. Flutter SSE client + Last-Event-ID resume. | ✓ |
| Poll GET /messages | Simplest Flutter code. Wastes bandwidth on 10-min agents. | |
| SSE primary + poll on focus | Best UX, more code. | |

**Selected:** SSE → **D-13.**

### Q7 (clarification): Use existing /messages or add /chat alias?

User: "use as is, unless impossible"

**Response:** Verified `IdempotencyMiddleware` already lists /messages as eligible (line 4). Frontend has zero `Idempotency-Key` references AND web chat is mocked (no current callers). Adding required enforcement breaks nothing. Locked **D-14** (mobile uses existing /messages with body `{content}`, /chat URL naming dropped).

---

## Area: Auth shim mechanism

### Q1: Dev-mode auth shim mechanism?

| Option | Description | Selected |
|--------|-------------|----------|
| Middleware injects from env | New ~30-LOC middleware between ApSession and RateLimit. Env-gated. | (initially picked) |
| Modify require_user fallback | Touches load-bearing 22c-06 helper. Risk of regression. | |
| Mobile does real OAuth (webview) | Skip shim. Heavier Flutter work. | |

**Initially selected:** Middleware injects from env → **D-15** (later superseded).

### Q2 (clarification on dev user provisioning):

User: "dev user real oauth"

**Response:** User overrode the locked "skip auth for MVP" decision. Re-locked **D-15** as: drop dev-mode shim entirely. Mobile uses real OAuth. API-05 collapses from "build dev shim" to "verify existing OAuth works for mobile callers."

### Q3: How does Flutter consume OAuth, where does work live?

User: "dude, dont reinvent wheel. how does flutter uses google auth? robust" + "actually, you decide"

**Response (Claude's call):** Researched standard Flutter OAuth pattern:
- Google → `google_sign_in` (official, native iOS/Android UI, returns ID token JWT)
- GitHub → `flutter_appauth` (AppAuth standard, system browser + PKCE + custom URI)
- WebView OAuth is an anti-pattern (Google blocked it for new apps in 2021)

Locked **D-15, D-16, D-17** without re-asking — user delegated.

---

## Area: Models proxy

### Q1: Cache substrate + TTL?

| Option | Description | Selected |
|--------|-------------|----------|
| In-process dict, 15min TTL | Simplest. No DB, no Redis. Stale-while-revalidate. | ✓ |
| Postgres row, 1h TTL | Survives restarts. New migration. | |
| On-disk file, 30min TTL | Cheapest. Doesn't survive container restarts. | |

**Selected:** In-process dict 15min → **D-18.**

### Auto-locked (no question — dissolved by elimination):
- **D-19**: No auth header (OpenRouter /models is public)
- **D-20**: Passthrough response
- **D-21**: Web frontend playground-form.tsx:169 migrated in same phase

---

## Second-pass extras (user requested "Explore more gray areas")

### Multi-select: Which extras to discuss?

User selected ALL FOUR + note: "dude, google auth and deploy agent... theres a pattern for google auth in flutter right? use it. also, the agents route already exists right?"

**Response:** Verified `POST /v1/runs` (creates agent_instance via UPSERT + smoke) and `POST /v1/agents/:id/start` (spawns container) BOTH exist and are exactly what mobile needs. Web playground uses this 2-call flow already. Locked **D-22** (zero new deploy backend code) and revised **D-17** (Cookie-header for mobile sessions, no transport conflict with BYOK).

Auto-locked from research:
- **D-23**: GOOGLE_OAUTH_MOBILE_CLIENT_IDS env var (Android+iOS comma-separated)
- **D-24**: GitHub reuses existing OAuth app, add mobile redirect URI to whitelist
- **D-25**: GZipMiddleware(minimum_size=1024) added to main.py
- **D-26**: 401-then-OAuth, no refresh tokens, no retry

---

## Third-pass extras (user requested "More grays" again)

### Multi-select: Final gray areas

User selected ALL FOUR + note "all gray areas":

| Area | Decision |
|------|----------|
| last_activity field shape | **D-27** — MAX(last_run_at, MAX(inapp_messages.created_at)) via LATERAL extension |
| Channel=inapp for mobile deploy | **D-28** — Phase 25 always sends `{channel:'inapp'}`, planner-level constraint |
| Agent name collision UX | **D-29** — Backend keeps UPSERT, Phase 25 UI does pre-flight check |
| Mobile OAuth test scaffolding | **D-30** — `tests/auth/test_oauth_mobile.py` + respx + 5-case matrix per provider |

---

## Fourth-pass extras (user requested third "More grays")

### Multi-select: Final-final round

User selected ALL FOUR + note "all grays":

| Area | Decision |
|------|----------|
| GZip + SSE collision spike | **D-31** — Wave 0 spike `tests/spikes/test_gzip_sse_compat.py` MUST PASS before plan seals |
| REQUIREMENTS.md amendments | **D-32** — Phase 23 includes API-01/05/06 amendments |
| Bearer vs Cookie revisit | **D-33** — Cookie stays per "use as is"; full Authorization-Bearer migration deferred |
| Verify session on app open | **D-34** — Mobile uses existing GET /v1/users/me on cold start |

---

## Claude's Discretion

Decisions where I locked without asking, justified inline:
- **D-15..D-17, D-23..D-26**: User said "you decide" / "use the standard pattern" — I researched native Flutter OAuth and locked accordingly.
- **D-19..D-21**: Dissolved by elimination — OpenRouter /models is public, passthrough is the dumb-client default, web migration is trivial scope.
- **D-22**: User asked "agents route already exists right?" — I verified yes and locked.
- **D-27..D-31**: User selected via multi-select but didn't sub-pick within each; I locked sensible defaults with rationale.
- **D-32**: REQUIREMENTS.md amendments are mandatory regardless of preference (verifier will fail otherwise).

## Deferred Ideas (mentioned during discussion)

- BYOK relocation off Authorization header (post-MVP cleanup phase) — surfaced when D-17 was revisited
- Web chat de-mock (frontend/app/dashboard/agents/[id]/page.tsx — line 67-69 is hardcoded sample)
- Token-level streaming (existing seed)
- Telegram channel UI in mobile (locked-out per mobile-mvp-decisions.md)
- Chat history pagination/search/regenerate/edit/delete (locked-out)

---

*End of audit trail. Final decisions live in `23-CONTEXT.md`.*
