# Feature Landscape

**Domain:** AI coding agent playground / per-user dockerized agent runner (agent × model agnostic)
**Researched:** 2026-04-11
**Confidence:** MEDIUM-HIGH (reference products well-documented; agent-recipe-catalog dimension is novel and partially extrapolated from devcontainer feature ecosystem)

## Reference Products Surveyed

| Product | What It Is | Key Lessons |
|---------|------------|-------------|
| **e2b.dev** | Cloud sandboxes for AI-generated code, ~150ms cold start, pause/resume with full VM snapshot | Session lifecycle is a first-class product surface, not an afterthought. Per-second billing while running; billing stops on pause. |
| **daytona.io** | Agent-native sandbox infra; sub-90ms creation; declarative image builder | Auto-stop/auto-archive/auto-delete policies, fine-grained lifecycle states, "describe environment, build it" pattern |
| **replit (Agent 3)** | Browser-first IDE + agentic builder; effort-based pricing | "Code in 60 seconds" onboarding bar; credit-pool UX; Economy/Power/Turbo modes; free tier with daily credit cap |
| **GitHub Copilot Workspace** | Ephemeral GitHub Actions environment driven by issues → PR | Cloud agents don't need a UI for the env itself; the PR is the artifact. No free tier — paid only. |
| **Cursor (background agents)** | Isolated Ubuntu cloud VMs running agents in parallel; up to 8 in parallel | Parallel session count is the upgrade lever. "Agent and Edit rely on custom models that cannot be billed to an API key" — they explicitly nerf BYOK to protect platform billing. |
| **Warp.dev (Agent Mode)** | Terminal that natively understands NL; Oz cloud orchestration for parallel agents | Agent Mode is a *mode* of the same input box (not a separate product), Full Terminal Use, BYOK with 0-credit footer indicator |
| **aider chat** | Pure CLI; reads `.env`/`--api-key provider=key`; OpenAI-compatible support | Reference for "every provider is a key + base URL"; no platform billing surface at all |
| **MSV (`/Users/fcavalcanti/dev/meusecretariovirtual`)** | Single-machine Hetzner host, dockerized PicoClaw per user, Telegram onboarding | The exact pattern this project mirrors *minus* Telegram and *minus* the locked agent. Cost projection was $0.044/user/month at 10k users. |
| **Devcontainer Features (containers.dev)** | OCI-distributed install scripts (`install.sh` + `devcontainer-feature.json`) for community-contributed tools | This is the model for `agents/<name>/` — a packaged install script + metadata, PR-driven, optionally OCI-distributed. |

---

## Table Stakes

Features users expect on day one. Missing any of these and the product feels broken or untrustworthy.

### Auth & Account

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Google OAuth | Universal dev-and-non-dev coverage | Low | NextAuth/Auth.js handles it |
| GitHub OAuth | Dev audience expects it; needed later for repo-pull features | Low | Same provider config |
| Single account, single profile page | Replit, Cursor, e2b — all do this trivially | Low | Email, avatar, sign-out, delete account |
| Session timeout / sign-out everywhere | Security baseline | Low | |

### Agent + Model Selection

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Agent picker (visual catalog with name, logo, one-liner) | The whole product premise; users need to *see* what's available | Medium | List of seed agents (OpenClaw, Hermes, HiClaw, PicoClaw + bootstrap path) |
| Model picker scoped to selected provider | Replit/Cursor/Warp all have this | Medium | Three providers (OpenRouter, Anthropic, OpenAI); model lists fetched live where possible |
| "Last used" / "default" memory per user | Reduces choice friction on return visits | Low | Profile setting |
| Provider/model compatibility hints | Some agents only support some providers; users hit dead ends without warnings | Medium | Recipe metadata declares supported providers |

### Session Lifecycle (the most-copied dimension across e2b/Daytona/Cursor)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| One-click "Start session" → working container in <10s | e2b sets the bar at 150ms, Daytona at 27-90ms; we won't beat them but must feel snappy | High | Pre-warmed base image pool helps |
| Visible session state (creating / running / stopped / failed) | e2b and Daytona both expose this; users panic without it | Medium | State machine + UI badge |
| Stop / destroy session button | Users must be able to terminate to stop billing | Low | |
| Session timeout with warning | Free tier needs idle timeout; warn before kill | Medium | Daytona's auto-stop pattern |
| Reconnect after browser close | Users will close tabs; container should still be there for paid tier | Medium | Session ID in URL or persisted |
| One active session per user (v1) | Constraint, but enforce visibly so users don't get confused | Low | "You already have a running session — open or destroy" modal |

### Hybrid Chat + Web Terminal UX

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Browser chat as default view | Casual users; Replit/Cursor/Workspace all default to chat | Medium | Stream agent stdout into chat bubbles |
| Drop-into-terminal toggle | Power users; Warp's "agent mode is a mode" pattern | High | xterm.js + websocket → docker exec, both views attached to the same container |
| Both views show the same container state | If they diverge, users lose trust | High | Agent CLI runs as a tmux/screen session both surfaces attach to, OR chat is just a typed prompt to the same TTY |
| Copy-able command history / scrollback | Standard terminal expectation | Low | xterm.js native |
| Mobile-tolerant chat view | Replit/MSV are mobile-first; terminal can be desktop-only | Medium | Chat works on phones; terminal degrades gracefully |

### BYOK Key Management

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Settings page with one row per provider (OpenRouter, Anthropic, OpenAI) | Warp, JetBrains, Vercel AI Gateway all do this | Low | |
| "Test key" button per provider | Vercel AI Gateway has this; users want validation before spending session time | Low | Cheap models-list call |
| Keys stored encrypted at rest | Baseline security | Medium | App-level encryption with KMS-equivalent; never log, never return in API |
| Visual indicator that BYOK is active in current session ("0 credits used") | Warp's exact pattern; eliminates confusion about who's paying | Low | Footer chip in chat |
| Last-4 / masked display, never full key after save | Standard pattern | Low | |
| Per-session override of which key to use | Users may have multiple OpenRouter keys (work vs personal) | Medium | v1.5 — defer if needed |

### Platform-Billed Credits

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Stripe-backed top-up flow | Replit/Cursor pattern; no subscription friction | Medium | Stripe Checkout + webhook |
| USD balance displayed in header, draining live during session | Users' #1 anxiety with metered billing is "how fast is it bleeding" | Medium | Polling or websocket; round to cents |
| Per-session cost meter (tokens × model price + container second cost) | e2b shows per-second; Replit shows effort-based | High | Token usage from provider responses + container time accounting |
| "Low balance" warning at 20% / "out" cutoff | Stops runaway spend; required for trust | Medium | |
| Transaction history (top-ups, sessions, refunds) | Required for any billing dispute | Medium | Append-only ledger |
| Cost preview before starting expensive operations | Replit Agent shows "this looks like a $0.40 task" — sets expectations | High | Defer to v1.5 |

### Onboarding

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| "From sign-in to running session" in <60 seconds | Replit's bar; this is the demo test | High | OAuth → default agent → default model (BYOK or free credits) → start |
| Free credits on signup ($1-$5) | Replit/Cursor pattern; lets users try without paying or pasting keys | Medium | Tied to abuse prevention (1 per Google ID) |
| Empty-state on dashboard explains the three paths | Avoid blank-screen confusion | Low | "Start a session" / "Add your API key" / "Top up credits" |
| Default to a known-good agent (OpenClaw) on first run | Reduce decision paralysis | Low | Pre-select on agent picker |

### Tier Differentiation (Free vs Paid)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Free = ephemeral container, killed on disconnect/idle | MSV cost model; matches free tier of e2b/Replit | Medium | Volume mounted as tmpfs; nothing persists |
| Paid = persistent volume, container can resume | Daytona's pattern; Cursor's cloud agents | High | Per-user named volume on host; backup via rsync to object storage |
| Tier displayed on session header ("Free — ephemeral" badge) | Sets expectations; avoids "I lost my work" surprises | Low | |

---

## Differentiators

These are where this product wins or doesn't ship.

### 1. Agent-Agnostic Recipe System (the headline differentiator)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Deterministic Docker-tested recipes** for seed agents stored in `agents/<name>/` | Known agents launch in seconds with zero "it works on my machine" | High | Each recipe = `recipe.yaml` (base image, install, launch, env, supported providers) + a tested Dockerfile + a smoke-test script |
| **Generic Claude-Code bootstrap** for arbitrary git repos | Long-tail coverage — every clawclones.com agent works without us writing a recipe first | Very High | Run Claude Code in a hardened base container, point it at the user's repo URL, let it install + launch, capture the resulting recipe |
| **Recipe cache** — first successful bootstrap is saved & reused | Bootstrap is slow; second user of the same repo gets the fast path | Medium | Hash repo URL + commit SHA → recipe blob |
| **Recipe browser / catalog UI** | Users discover agents the same way they discover devcontainer features | Medium | Filter by language, provider support, RAM footprint, "official" vs "community" |
| **Recipe contribution flow** — PR to `agents/<name>/` with a CI smoke test | Devcontainer features pattern; community grows the catalog | Medium | GitHub Action runs the recipe in a fresh container, posts pass/fail on PR |
| **Recipe version pinning** (semver) | Users on a paid plan can pin "OpenClaw recipe v1.4.2" so an upstream change doesn't break their session | Medium | Deferable to v1.5 |
| **"Try this repo as an agent" — paste a git URL** | The killer demo; nobody else does this | Very High | Calls into the bootstrap pipeline; great onboarding moment |

**This is the moat.** No reference product treats the agent itself as a swappable resource. e2b/Daytona run *generated code*; Replit/Cursor/Warp run *one specific agent*; we run *any agent the user picks.*

### 2. Hybrid Chat + Terminal on the Same Container

Chat-only products (Workspace, Replit Agent) feel limiting to power users; terminal-only products (Warp, aider) intimidate beginners. Doing both, attached to the same TTY, is a real product wedge. The closest analog is Warp's "agent mode is a mode" of the same input — but Warp is a desktop app, not browser, so the cloud-hosted version is open.

Complexity: **High.** The hard part is making both surfaces show the same scrollback and not fight each other for stdin. Recommended approach: agent runs inside `tmux`, chat surface attaches via `tmux send-keys` + capture-pane, terminal surface attaches via `docker exec -it ... tmux attach`. Both see the same buffer.

### 3. BYOK is First-Class, Not Punished

Cursor explicitly *nerfs* BYOK ("Agent and Edit rely on custom models that cannot be billed to an API key"). Replit doesn't support BYOK at all. This is the openness wedge: a user who never wants to top up credits can use the entire product on their own keys, with zero feature degradation, and the platform never sees their tokens.

| Feature | Value Proposition | Complexity |
|---------|-------------------|------------|
| BYOK works on every agent and every feature, no asterisks | Unmatched among hosted competitors | Medium |
| BYOK sessions show "0 credits used" prominently | Trust signal | Low |
| Per-provider switch in session ("use my Anthropic key for this session, my OpenRouter for the next") | Power-user lever | Medium |

### 4. Whole Platform Open Source

Frontend + Go API + recipe catalog + container bases all OSS under MIT/Apache-2.0. Monetization is the hosted service. This unlocks:
- **Self-hosted deployments** for orgs that need air-gapped agent runs (defer; document the path)
- **Recipe catalog contributions** from people who never pay for the hosted product
- **Trust signal** vs proprietary cloud sandboxes

Complexity is mostly process: clean repo hygiene, public CI, contributor docs, license headers.

### 5. "Try Any Git Repo as an Agent" (Bootstrap Demo)

Specifically called out as differentiator #1 sub-feature, but it deserves its own bullet because it's the *demoable* moment: paste a GitHub URL on the homepage → 30 seconds later → working session with that thing running. Nobody else in the space lets you do this.

### 6. Predictable Per-Container Cost (Hetzner Single-Host Model)

MSV proved $0.044/user/month at 10k users on a single Hetzner AX162. e2b is $0.083/hour just for the smallest sandbox; Daytona is sub-second but cloud-priced. Our cost structure lets us offer free credits other platforms can't.

This isn't a user-facing feature — it's a *pricing-page* differentiator. "More free credits than anyone else" is the surface form.

### 7. Recipe-Driven Provider Compatibility Checks

Because each recipe declares which providers it supports, the model picker can grey out incompatible model/agent combinations *before* the user starts a session. Replit/Cursor/Warp don't have this problem because they're locked to one agent. We turn the multi-agent complexity into a guard rail rather than a footgun.

---

## Anti-Features

Things to deliberately NOT build, even when users ask.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Telegram bot onboarding / Telegram-as-UI** | MSV's biggest constraint. Couples the product to a platform we don't control, fragments support, and breaks the open-source self-host story. | Browser-only. Period. If users want mobile, the chat view is mobile-tolerant. |
| **Locked to a single agent** (PicoClaw-only, OpenClaw-only) | Defeats the entire product premise. The catalog at clawclones.com is growing weekly; betting on one is suicide. | Agent picker is a top-level concept from day 1. |
| **Locked to a single model provider** (Anthropic-only) | Users have OpenRouter accounts, OpenAI accounts, sometimes only one. Locking them out kills BYOK. | Three providers on day 1; OpenRouter alone covers ~100 models. |
| **Multi-session / parallel sessions per user in v1** | Cursor charges premium for this; the infra (port allocation, resource accounting, UI complexity) is a v2 multiplier. | One active session, with a clear "destroy and start new" flow. Tier-gate parallelism in v2 as an upgrade lever. |
| **Monthly subscription billing in v1** | Subscription friction kills signup; Replit added it later, not first. Users hate "what am I paying for if I don't use it this month." | Credit balance + Stripe top-up. Subscriptions can come later if a clear demand signal appears. |
| **Cloud-managed hosting (AWS Fargate, GCP Cloud Run, Fly Machines)** | Per-container costs are 5-10× Hetzner; kills the cost differentiator. | Hetzner dedicated host, Docker on host. Same as MSV. |
| **Closed-source core** | Kills the recipe catalog contribution loop and the trust signal. | Whole platform OSS; monetize the hosted service. |
| **Curated-only agent catalog** | Long tail of clawclones is the addressable market. Curating only means we miss the next OpenClaw before it's famous. | Generic bootstrap path is mandatory; curated recipes are an *acceleration*, not a *gate*. |
| **Email/password auth** | Adds password reset, email verification, account recovery, breach surface. The dev audience is on Google + GitHub. | OAuth-only (Google + GitHub) in v1. |
| **In-product file editor / IDE** | We're not Replit. Trying to be an IDE means competing with Cursor, Replit, Workspace. We are an *agent runner*. | Terminal + chat. Files happen via the agent's own commands. If users want an IDE, they git clone locally. |
| **Cost preview before every operation** (Replit's effort-based pricing UX) | Replit can do this because they own the agent and the model. We don't — we'd have to predict on behalf of arbitrary agents. False precision is worse than no precision. | Show the *running* cost during the session (live drain). Defer prediction to v2 if at all. |
| **Custom billable models on top of BYOK** (Cursor's "you can't use Edit with your own keys" trap) | The whole point of BYOK is *no asterisks*. Punishing BYOK users to protect platform revenue is exactly the opposite of the open positioning. | Every feature works with BYOK. Platform credits are an alternative payment, not a feature gate. |
| **Single global terminal that all users share** | Security horror, container escapes, key leakage. | One container per user, full filesystem isolation. |
| **Letting the generic bootstrap blindly run user-supplied scripts on the host** | Container escape risk; this is the biggest security exposure in the whole product. | Bootstrap runs *inside* the per-user container, with no host docker socket, no host filesystem mounts beyond the user's own volume, and a hardened seccomp profile. |
| **Local/Ollama provider in v1** | Adds a 4th provider and the hardest one (resource model is totally different — GPU/CPU vs API call). | Three remote providers in v1; Ollama in v1.5 as a paid-tier feature gated by host GPU. |
| **Real-time collaborative sessions** (multiple users in one container) | Big infra cost, niche use case, security headache. | Single-user sessions only. Sharing happens via PR / git push out of the container. |

---

## Feature Dependencies

```
OAuth login
   └─→ User profile
         └─→ BYOK key storage
               └─→ Session start (BYOK path)
         └─→ Stripe customer
               └─→ Credit balance
                     └─→ Session start (platform-billed path)

Recipe catalog (agents/<name>/)
   └─→ Agent picker UI
         └─→ Model picker (filtered by recipe.supported_providers)
               └─→ Session start
                     └─→ Container provisioning
                           └─→ Recipe install + launch
                                 └─→ TTY ready
                                       ├─→ Chat surface (tmux send-keys)
                                       └─→ Terminal surface (xterm.js)

Generic bootstrap path:
   "Try this repo" URL
   └─→ Hardened base container
         └─→ Claude Code bootstrap prompt
               └─→ Captured recipe
                     └─→ Recipe cache (reuseable for next user)

Tier system:
   Free → ephemeral container (no volume)
   Paid → persistent named volume + idle-timeout extension + reconnect after disconnect
```

**Critical path for first usable demo:** OAuth → agent picker (1 hardcoded recipe) → BYOK key paste → start session → terminal surface. Everything else is layered on top.

---

## MVP Recommendation

### Must ship in v1 (otherwise the product doesn't make sense)

1. Google + GitHub OAuth
2. Agent picker with **3-4 hardcoded recipes** (OpenClaw, Hermes, HiClaw, PicoClaw)
3. Model picker for OpenRouter + Anthropic + OpenAI
4. BYOK key management (settings page, encrypted storage, "test key")
5. Session start → Docker container → recipe install → launch
6. **Terminal surface** (xterm.js into the container) — this is the simpler of the two UX surfaces
7. Stop / destroy session
8. One active session per user (enforced)
9. Free tier = ephemeral container

### Should ship in v1.0 (the first marketable release)

10. Chat surface alongside terminal (hybrid view)
11. Stripe credit top-up + balance display
12. Session timeout + idle warning
13. Paid tier = persistent volume + reconnect-after-disconnect
14. "Test key" validation
15. Cost meter draining live during platform-billed sessions

### Defer to v1.5

16. **Generic Claude-Code bootstrap pipeline** — yes, this is the headline differentiator, but it's also the highest-risk feature. Ship the curated path first to prove the rest of the product works, then add bootstrap.
17. Recipe contribution flow (PR + CI smoke test)
18. "Try any git repo" homepage demo
19. Recipe browser / catalog UI (vs hardcoded list)
20. Last-used model/agent memory

### Defer to v2

21. Multiple parallel sessions (tier-gated)
22. Recipe version pinning
23. Local/Ollama provider
24. Cost prediction / preview
25. Self-hosted deployment docs
26. Subscription billing alternative

---

## Sources

- [E2B sandbox persistence docs](https://e2b.dev/docs/sandbox/persistence) — pause/resume lifecycle, ~150ms VM snapshot
- [E2B pricing](https://e2b.dev/pricing) — per-second billing model
- [E2B vs Daytona comparison (ZenML)](https://www.zenml.io/blog/e2b-vs-daytona) — lifecycle state comparison
- [Daytona homepage](https://www.daytona.io/) — sub-90ms creation, agent-native infra
- [Daytona: Redefining Agent Experience](https://www.daytona.io/dotfiles/daytona-redefining-agent-experience) — declarative image builder pattern
- [Replit pricing](https://replit.com/pricing) — Starter/Core/Pro/Enterprise tier structure
- [Replit effort-based pricing blog](https://blog.replit.com/effort-based-pricing) — Agent 3 pricing model
- [Replit Review 2026 (Hackceleration)](https://hackceleration.com/replit-review/) — "60 seconds to coding" onboarding bar
- [GitHub Copilot Workspace](https://githubnext.com/projects/copilot-workspace) — ephemeral GitHub Actions environment
- [GitHub Copilot cloud agent docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-environment) — environment customization
- [Cursor Background Agents (Morph)](https://www.morphllm.com/cursor-background-agents) — parallel agent count, isolated VMs
- [Cursor BYOK ban issue (apidog)](https://apidog.com/blog/cursor-byok-ban-alternative/) — explicit BYOK degradation example
- [Warp Agent Mode docs](https://docs.warp.dev/features/warp-ai/agent-mode) — agent-mode-as-a-mode pattern
- [Warp BYOK docs](https://docs.warp.dev/support-and-community/plans-and-billing/bring-your-own-api-key) — "0 credits used" indicator
- [aider API keys docs](https://aider.chat/docs/config/api-keys.html) — provider-key-as-env-var pattern
- [aider OpenAI-compatible providers](https://aider.chat/docs/llms/openai-compat.html) — generic provider compatibility
- [JetBrains BYOK announcement](https://blog.jetbrains.com/ai/2025/12/bring-your-own-key-byok-is-now-live-in-jetbrains-ides/) — settings UX reference
- [Vercel AI Gateway BYOK](https://vercel.com/docs/ai-gateway/authentication-and-byok/byok) — "Test key" UX reference
- [Devcontainer Features distribution](https://containers.dev/implementors/features-distribution/) — OCI registry pattern for community recipes
- [Authoring a Dev Container Feature](https://containers.dev/guide/author-a-feature) — `install.sh` + `feature.json` recipe model (direct analog for `agents/<name>/`)
- [devcontainers/feature-starter](https://github.com/devcontainers/feature-starter) — bootstrap repo pattern with publishing GitHub Action
- [xterm.js + Docker tutorial (Presidio)](https://www.presidio.com/technical-blog/building-a-browser-based-terminal-using-docker-and-xtermjs/) — websocket-to-docker-exec pattern
- [xterm.js homepage](https://xtermjs.org/) — used by VS Code, Hyper, Theia
- `/Users/fcavalcanti/dev/agent-playground/.planning/PROJECT.md` — project requirements
- `/Users/fcavalcanti/dev/meusecretariovirtual/README.md` — MSV cost model ($0.044/user/mo at 10k users), MSV constraints (Telegram, locked agent) we are removing

---

## Confidence Notes

- **HIGH** on reference-product features (e2b, Daytona, Replit, Cursor, Warp, Workspace, aider) — multiple corroborating sources, all current to 2026.
- **HIGH** on devcontainer features as the recipe-catalog model — official spec, reference repos, known-good pattern.
- **MEDIUM** on the hybrid chat-terminal UX implementation specifics (tmux attach pattern). The pattern is sound but I haven't seen a hosted competitor doing exactly this; it's extrapolation from how `tmux` and `xterm.js + docker exec` actually compose.
- **MEDIUM** on the generic Claude-Code bootstrap differentiator — no competitor does this, so there's no prior art to validate. The risk is technical (Claude Code reliably figuring out arbitrary agent install steps), not market.
- **LOW** on specific token/cost-meter accounting accuracy — this depends on whether each provider returns usage in its responses (Anthropic and OpenAI yes; OpenRouter passes it through; some routed models may not). Worth a phase-specific spike before committing to a precise live drain UX.
