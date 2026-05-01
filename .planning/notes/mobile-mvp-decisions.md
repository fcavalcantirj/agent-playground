---
title: Mobile MVP — locked architectural decisions
date: 2026-05-01
context: gsd-explore session — Flutter native mobile app for Solvr Labs / Agent Playground
status: locked-pre-milestone
---

# Mobile MVP — locked architectural decisions

Captured from the `/gsd-explore` session on 2026-05-01 immediately after Phase 22c.3.1
(runner-inapp-wiring) shipped. Use this note as the single source of truth when seeding
the new "Mobile MVP" milestone — these decisions are **not** open for re-litigation
during planning.

## Product framing

**Solvr Labs** is the user-facing brand. "Agent Playground" remains the project codename
in the repo. Brand reconciliation (do we rename, do we keep both, what goes on app stores)
is **deferred** — a post-MVP question once we have something to demo.

The mockups in this conversation (6 screens) define the visual target. The MVP cuts that
to **3 screens** (see scope below); the rest become later-phase work.

## MVP scope — what ships

**Three screens, end-to-end against a local backend:**

1. **Dashboard** — list of the user's existing agents (model + handle + status), tap to open Chat. Bottom tab bar from the mockup is purely cosmetic in MVP.
2. **New Agent (Deploy)** — pick clone (5 options: hermes/openclaw/nullclaw/picoclaw/nanobot), pick OpenRouter model, name, hit Deploy → server spawns container → app routes to Chat for the new agent.
3. **Chat** — message list + input. Block-and-wait (no streaming yet). History persists across app restarts.

**Networking target:**
- Default: same-wifi LAN — Flutter app on the phone reaches the laptop's LAN IP (e.g. `http://192.168.1.x:8000`).
- Fallback when not on the same wifi: **ngrok** (or equivalent tunnel) — exposes `localhost:8000` to a public URL the phone hits.
- **Deploy is NOT in MVP.** Phase 19 (Hetzner deploy) is a separate later effort, gated on actually-want-to-show-this-publicly. End-to-end on localhost first; *then* we deploy.

## Backend changes required

Five additions on top of what Phase 22c.3.1 already shipped. Nothing exotic.

| # | Change | Why |
|---|--------|-----|
| 1 | New table `messages (id, agent_id FK, role, content, created_at)` + Alembic migration | Chat history persistence |
| 2 | `POST /v1/agents/:id/chat` — body `{message}`, looks up the agent's container (bridge IP + port + auth token from `agent_containers`), POSTs to its `/v1/chat/completions` (OpenAI shape, `stream: false`), INSERTs user-row + assistant-row, returns `{message}` | The proxy. Mobile cannot reach docker bridge IPs from off-host; the API server can. ~80 LOC. |
| 3 | `GET /v1/agents/:id/messages?limit=N` | Load history when chat opens |
| 4 | `GET /v1/agents` (or `GET /v1/agents/me`) — list current user's agent_containers rows | Dashboard list |
| 5 | Auth shim — FastAPI `Depends(current_user_id)` returning a hardcoded UUID in dev mode (env-gated). OAuth (Phase 22c-oauth-google, planned-not-executed) plugs into the same dependency later, swapping the impl, NOT the call sites. | Defer auth without forcing a rewrite later |

## What's explicitly NOT in MVP

- **Streaming chat** — block-and-wait first. Streaming added LATER as an additive endpoint (e.g. `POST /v1/agents/:id/chat?stream=true` returning SSE) — coexists with block-and-wait, so it's a feature flag at the Flutter call site, not a rewrite. See `seeds/streaming-chat.md`.
- **Login screen / OAuth** — auth shim is hardcoded. The Login mockup is a later-phase artifact.
- **Agent Settings, Browse tab, Profile tab, Select Model as standalone screen** — out of MVP. Model picker is *embedded* in the New Agent screen (no separate browse view).
- **Telegram integration toggle on New Agent** — out of MVP. Telegram path already works; the toggle just gates which channel(s) the agent activates. Defer the UX until in-app channel works in the mobile app.
- **Push notifications, deep links, app-store identity** — none of these are MVP.
- **Conversation history pagination, search, export** — none of these are MVP.
- **Multi-message-at-once / regenerate / edit / delete** — none of these are MVP. Send a message, see a reply. That's it.

## Locked rules — apply throughout planning + execution

1. **"Code we'll reuse"** — no throwaway MVP shortcuts. Auth shim is additive (same call sites pre/post OAuth). Streaming is additive (new endpoint, not a rewrite). Persistence is real on day 1. **No** in-memory chat that has to be replaced.
2. **No mocks/stubs** (Golden Rule #1) — backend tests hit real Postgres + real Docker via testcontainers, same as Phase 22c.3.1. Flutter tests hit a real local API server, not a mock client.
3. **Dumb client, intelligence in API** (Golden Rule #2) — Flutter does NOT ship a hardcoded recipe catalog or model catalog. Recipes come from `GET /v1/recipes` (already exists). Models come from a backend endpoint (proxied from OpenRouter) — **not** from a Dart-side hardcoded list.
4. **Ship when stack works locally end-to-end** (Golden Rule #3) — milestone "done" is "tap Deploy on the phone, get to Chat, type a message, see a reply" against a local backend. Not "Flutter compiles" — the actual flow works.
5. **Root cause first** (Golden Rule #4) — same as always.
6. **Test everything; spike before planning** (Golden Rule #5) — for the Flutter side: spike at minimum the OAuth-shim header injection + the chat POST + the deploy round-trip against a real API server before sealing the screens plan.

## Suggested phase shape for the "Mobile MVP" milestone

(For the `/gsd-new-milestone` workflow that consumes this note.)

| Phase | Scope | Ships |
|-------|-------|-------|
| P1 — Backend chat-proxy + persistence | `messages` table + migration; `POST /v1/agents/:id/chat`; `GET /v1/agents/:id/messages`; `GET /v1/agents`; auth shim | All-on-backend; testable via `curl` + existing pytest harness; no Flutter dependency |
| P2 — Flutter scaffold | Project init; state-mgmt choice (Riverpod default, settle in spec phase); routing (go_router); theme matching mockup; typed API client matching P1 + existing `/v1/agents/:id/start` + `/v1/recipes`; ngrok config + LAN-IP env var | App boots, hits a health endpoint, no real screens yet |
| P3 — Flutter screens | Dashboard + New Agent + Chat wired to the API client | The demo flow works end-to-end on localhost |

**Deploy (Hetzner) is NOT in this milestone.** Once P3 ships and the demo runs, the user
decides whether to deploy. That's a separate milestone or phase, not bundled here.

## Open research questions to settle in P2's spec/research

These are flagged here so the planner doesn't drift:

- **Flutter state mgmt**: Riverpod (modern default) vs Bloc vs Provider. Default Riverpod unless research surfaces a project-specific reason to deviate.
- **Networking lib**: dio (interceptors, multipart, cancel tokens) vs http (stdlib-equivalent). dio is the better fit for an API client with auth header injection + retries.
- **API client gen**: hand-write vs `retrofit` codegen vs `openapi-generator` against an OpenAPI spec exported from FastAPI. Hand-write is fine for ~6 endpoints; codegen pays off later when there are 20+.
- **Theme**: monochrome with a single accent (the green dot in the dashboard mockup). Settle palette + typography in P2's spec.
- **Model catalog**: backend proxy of OpenRouter `/api/v1/models` is the right answer (Rule 3 — dumb client). Cache on backend with a TTL. Settle TTL + auth resolution (does the proxy use platform key or per-user key?) in P1's spec.

## Sources

- This conversation (Felipe + Claude, `/gsd-explore` session, 2026-05-01)
- Phase 22c.3.1 SUMMARY.md — proves the inapp channel + container spawn + auth-token mint already work end-to-end via the route handler
- Mockups (6 screens, 375x812) shared in conversation
- `CLAUDE.md` — golden rules referenced above
- `MEMORY.md` — feedback rules (no mocks/stubs, dumb client, code we'll reuse)
