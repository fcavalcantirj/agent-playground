# Agent Playground

## What This Is

A web platform where logged-in users pick any combination of coding agent (OpenClaw, Hermes, HiClaw, PicoClaw, NanoClaw, and others from the clawclones catalog) and any model (OpenRouter, Anthropic, OpenAI) and get a dockerized session to drive it — via a browser chat UI or a web terminal into the same container. Inspired by `/Users/fcavalcanti/dev/meusecretariovirtual` (MSV) but without its constraints: no Telegram dependency, not locked to PicoClaw, not locked to Anthropic models.

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
- [ ] Per-user dockerized session on the Hetzner host, isolated filesystem
- [ ] Hybrid session UX: browser chat as default, drop-into-web-terminal for power users (both views of the same container)
- [ ] Session tiers: free = ephemeral container, paid = persistent container with backed-up volume
- [ ] One active session per user (parallel sessions out of scope for v1)
- [ ] BYOK: user pastes their own OpenRouter / Anthropic / OpenAI keys, platform never sees billing
- [ ] Platform-billed credits: Stripe top-up, metered per token/call, USD balance displayed and draining
- [ ] Open-source the whole platform (frontend + Go API + recipe catalog + container bases) under a permissive license; monetize via the hosted service

### Out of Scope

- **Telegram bot integration** — MSV's biggest constraint; we explicitly remove it. Interaction is browser-only.
- **Locked-in single agent or single model provider** — the whole point is agent × model agnosticism.
- **Multiple parallel sessions per user in v1** — one active session is simpler infra; tier-gated parallelism is a v2 lever.
- **Monthly subscription billing in v1** — credit balance only. Subscriptions can come later if users ask.
- **Cloud-managed hosting (AWS/GCP/Fly)** — Hetzner dedicated box mirrors MSV and keeps container costs predictable.
- **Closed-source core** — platform is open source; monetization is the hosted service, not the code.
- **Curated-only agent catalog** — we must support arbitrary git repos via the generic Claude-Code bootstrap, not just a hand-picked list.

## Context

**Inspiration:** `/Users/fcavalcanti/dev/meusecretariovirtual` (MSV) — Go API + Next.js frontend, Hetzner dedicated, dockerized PicoClaw per user, Telegram onboarding. Proven pattern for "one container per user" at scale. This project mirrors the stack and deployment model, drops the Telegram dependency, and generalizes the agent + model choice.

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
- **Session concurrency**: One active session per user; multi-session is tier-gated v2 work.
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
| One active session per user in v1 | Simpler infra, tier-gating comes later as an upgrade lever. | — Pending |
| Use Temporal for durable workflows | User override of research recommendation. Session spawn/destroy, recipe install, reconciliation, billing reconciliation all run as Temporal workflows. Mirrors MSV's executor. | — Pending |

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
*Last updated: 2026-04-11 after initialization*
