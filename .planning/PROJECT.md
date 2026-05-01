# Agent Playground

## Mission

**Democratize agent deployment — the easiest way to deploy any agent × any model combination.**

## What This Is

A mobile-first web platform where users create any number of agent instances — each combining a coding agent (OpenClaw, Hermes, HiClaw, PicoClaw, NanoClaw, and others from the clawclones catalog) with any model (OpenRouter, Anthropic, OpenAI) — and get a persistent dockerized container per agent, accessible via browser chat, web terminal, SSH, or webhook. Each agent is a tab on the mobile UI. Users create as many agents as their credits allow. Inspired by MSV but without its constraints: no Telegram dependency, not locked to one agent or one model.

## Core Value

**Any agent × any model × any user, in one click.** If everything else fails, the agent-agnostic install pipeline (deterministic recipes for known agents, Claude-Code bootstrap for unknown ones) must work — that's the differentiator.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Google + GitHub OAuth login
- [ ] Agent catalog UI — user picks one agent from a list of supported agents
- [ ] Model picker — user picks a model from OpenRouter, Anthropic, or OpenAI (BYOK or platform-billed)
- [ ] Agent-agnostic install pipeline:
  - [ ] Deterministic, Docker-tested recipes for seed agents: Hermes, HiClaw, PicoClaw (plus OpenClaw as the default full agent)
  - [ ] Generic Claude-Code-driven bootstrap prompt for any git repo the user points at
  - [ ] Recipes stored in-repo under `agents/<name>/`
- [ ] N agent instances per user — each is its own dockerized container with webhook URL, SSH access, and chat channel. Users create as many as credits allow.
- [ ] Multi-surface access: mobile-first browser chat (primary), web terminal, SSH, webhook per agent
- [ ] Mobile-first UI: agents as tabs for quick-switch chat; designed for phone first, desktop enhances
- [ ] Session tiers: free = ephemeral container, paid = persistent container with backed-up volume
- [ ] v1 enforces 1 active (running) agent at a time — but schema, API, and UI designed for N-active. Flipping the limit is a config change, not a rewrite.
- [ ] BYOK: user pastes their own OpenRouter / Anthropic / OpenAI keys, platform never sees billing
- [ ] Platform-billed credits: Stripe top-up, metered per token/call, USD balance displayed and draining
- [ ] Open-source the whole platform (frontend + Go API + recipe catalog + container bases) under a permissive license; monetize via the hosted service

### Out of Scope

- **Telegram bot integration** — MSV's biggest constraint; we explicitly remove it.
- **Locked-in single agent or single model provider** — the whole point is agent × model agnosticism.
- **N active (running) agents simultaneously in v1** — schema supports N, v1 enforces 1 active. N-active is a v2 config flip.
- **Monthly subscription billing in v1** — credit balance only. Subscriptions can come later if users ask.
- **Cloud-managed hosting (AWS/GCP/Fly)** — Hetzner dedicated box mirrors MSV and keeps container costs predictable.
- **Closed-source core** — platform is open source; monetization is the hosted service, not the code.
- **Curated-only agent catalog** — we must support arbitrary git repos via the generic Claude-Code bootstrap, not just a hand-picked list.

## Context

**Inspiration:** `/Users/fcavalcanti/dev/meusecretariovirtual` (MSV) — Go API + Next.js frontend, Hetzner dedicated, dockerized PicoClaw per user, Telegram onboarding. Proven pattern for "one container per user" at scale. This project mirrors the stack and deployment model, drops the Telegram dependency, and generalizes to N agents per user × any model choice.

**Agent ecosystem:** Catalog lives at <https://clawclones.com/#clones> — OpenClaw, Hermes-agent, grip-ai, NanoClaw, Carapace, IronClaw, ZeroClaw, OpenFang, Poco, nanobot, plus PicoClaw and HiClaw. Most are open source, most support multiple providers. The ecosystem is growing, which is exactly why the platform has to be agent-agnostic from day one rather than bet on a fixed list.

**Install strategy:** The team will run local dockerized test runs against each known agent to derive a deterministic install + launch recipe (base image, install commands, launch command, required env vars). Those recipes are committed to `agents/<name>/` in this repo. For unknown agents, a generic Claude-Code bootstrap prompt runs inside a base container, reads the target git repo, attempts install + launch, and caches the resulting recipe for reuse.

**User's background:** BasicPay / LinkerPay stack is already Next.js, and MSV is already Go API + Next.js. This project fits directly into the user's existing stack muscle memory.

## Constraints

- **Tech stack**: Go API + Next.js frontend — mirror MSV, transfer patterns and code directly.
- **Workflow engine**: **Temporal** — used for all durable workflows (session create/destroy, recipe install, reconciliation, billing reconciliation). Mirrors MSV's executor pattern. Explicitly overrides the research recommendation to "drop Temporal" — user decision.
- **Infra**: Hetzner dedicated box — same as MSV; one beefy host, Docker on host for per-user containers.
- **Auth**: Google + GitHub OAuth only in v1 — no email/password.
- **Billing**: Credit balance via Stripe for platform-billed mode; BYOK path has zero billing touchpoints.
- **Models**: Must support OpenRouter, Anthropic direct, and OpenAI direct on day 1. Local/Ollama is a later tier.
- **Open source**: Whole platform ships OSS under a permissive license (MIT or Apache-2.0) — decision deferred to planning.
- **Mobile-first**: All UI is designed for mobile viewport first, desktop enhances. Phone is the primary device.
- **Multi-agent model**: N agents per user (each = container + webhook + SSH + chat channel), v1 limits 1 active (running), schema + API ready for N-active. Flipping the limit = config change.
- **Access channels**: Browser chat (primary), web terminal, SSH, webhook per agent. Not browser-only.
- **Security**: Per-user isolated Docker container on a shared host; recipe execution inside containers must not trust user-supplied repo URLs blindly (sandbox hardening is a hard requirement for the generic bootstrap path).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Agent-agnostic from day 1, not curated-only | The catalog is growing; locking to a fixed list defeats the product insight. Generic Claude-Code bootstrap handles the long tail. | — Pending |
| Dual install path: tested recipes + generic bootstrap | Known agents get determinism and speed; unknown agents get coverage. Recipes cached after first bootstrap. | — Pending |
| Recipes in-repo at `agents/<name>/` | Simplest versioning and review; PR-driven. Can split to a separate public repo if catalog grows beyond the repo. | — Pending |
| Go API + Next.js frontend | Mirror MSV; transfer patterns. User already owns the muscle memory. | — Pending |
| Hetzner dedicated host | Same as MSV; predictable cost per container; fits the "one beefy machine" pattern. | — Pending |
| Hybrid chat + web terminal, same container | Chat for casual users, terminal for power users, without doubling infra. | — Pending |
| Credit balance (Stripe) for platform-billed usage | Simplest mental model for users, aligns cost with usage, no subscription friction. | — Pending |
| BYOK is first-class, not an afterthought | Some users will never top up credits; they want to use their own keys. Must be supported from v1. | — Pending |
| Google + GitHub OAuth | Dev audience has GitHub; Google is universal. Skip email/password to reduce auth surface. | — Pending |
| Whole platform open source | The hosted service is the monetization, not the code. OSS drives the recipe catalog contributions long-term. | — Pending |
| N agents per user, 1 active in v1, N-active ready | Schema + API support N agents from day 1. v1 enforces 1 running at a time via config. N-active is a v2 config flip, not a rewrite. | User override of "one session" model |
| Mobile-first design | Phone is the primary device. Agents as tabs for quick-switch chat. Desktop enhances, not the other way. | User decision during Phase 1 discuss |
| Multi-surface access (web + SSH + webhook) | Each agent gets browser chat, web terminal, SSH, and webhook URL. Not browser-only. | User decision during Phase 1 discuss |
| Mission: democratize agent deployment | The easiest way to deploy any agent × any model combination, in one click. | User decision during Phase 1 discuss |
| Use Temporal for durable workflows | User override of research recommendation. Session spawn/destroy, recipe install, reconciliation, billing reconciliation all run as Temporal workflows. Mirrors MSV's executor. | — Pending |

## Current Milestone: v0.3 Mobile MVP

**User-facing brand:** Solvr Labs (repo codename remains "Agent Playground")

**Goal:** Ship a Flutter native mobile app that drives the agent-spawn substrate end-to-end on localhost — Deploy → Dashboard → Chat with persisted history. No deploy, no auth, no streaming. "Code we'll reuse."

**Target features:**
- Backend chat-proxy + persistence: `POST /v1/agents/:id/chat`, `GET /v1/agents/:id/messages`, `GET /v1/agents`, model catalog proxy, dev-mode auth shim (additive shape — OAuth plugs in later swapping impl, not call sites)
- Flutter project scaffold: Riverpod (default) + go_router + dio + flat Material 3 theme matching Solvr design language (monochrome, 0 radius, Inter + JetBrains Mono) + LAN/ngrok env config
- Three screens wired end-to-end against local API: Dashboard, New Agent (Deploy), Chat

**Key context:**
- Phase 22c.3.1 (runner-inapp-wiring) just shipped — this milestone CONSUMES the uniform agent-spawn route, doesn't rebuild it
- Locked architectural decisions in `.planning/notes/mobile-mvp-decisions.md` — do not re-litigate during phase planning
- Streaming chat captured as an additive seed in `.planning/seeds/streaming-chat.md` — out of milestone scope
- Hetzner deploy + remote-API switch is OUT of milestone — separate later effort once the local demo lands
- Look-and-feel reference: the mockups in conversation + `/Users/fcavalcanti/dev/solvr/frontend` (Tailwind v4, Radix/shadcn, monochrome high-contrast, flat 0 radius, Inter + JetBrains Mono)

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-01 — milestone v0.3 (Mobile MVP / Solvr Labs) opened; Flutter native targeting localhost end-to-end first*
