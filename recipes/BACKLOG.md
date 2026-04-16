# Agent Recipe Backlog

> **⚠️ ON HOLD as of 2026-04-15 — format v0.1 consolidation phase pending before adding more agents.**
>
> 5 recipes validated end-to-end (hermes, openclaw, picoclaw, nullclaw, nanobot) but the format has grown organically and accumulated debt across 8 concrete items: a thin `pass_if` vocabulary, CLI-only smoke prompts, undocumented schema fields, no structured runner output, no sweep mode, no disk guard, no regression re-runs, no user-facing docs.
>
> Phase brief: `.planning/phases/03-recipe-format-v0.1/CONTEXT.md`
> Debt detail: auto-memory `feedback_recipe_runner_debt.md`
>
> **Do NOT add a new recipe before format-v0.1 lands.** The stars-desc queue below resumes AFTER that phase completes. Top of queue: ZeroClaw (30,171 ★, Rust).

Tracking agents we want to validate against `ap.recipe/v0`. A row flips to `[x]` only when the recipe is committed **and** `tools/run_recipe.py` returns `PASS` against at least one model cell.

**Status legend**

- `[ ]` todo — not started
- `[~]` in progress — recon or runner iteration under way
- `[x]` done — recipe committed, runner PASS
- `[-]` skipped — not a coding agent / out of scope
- `[?]` deferred — needs a decision before we work on it
- `[v1]` deferred to v1 — out of v0 scope

---

## v0 scope: self-improving agents only

Agent Playground's flagship value prop is hosting agents that **improve over time** — skills, persistent memory, cross-session learning, self-curated state. A per-user sandbox matters most for these. Pure LLM-wrapper CLIs (aider, goose, plandex, etc.) work with the recipe format but don't exercise the persistence story. They ship in v1.

### Completed

- [x] **Hermes Agent** (Nous Research) — https://github.com/NousResearch/hermes-agent — `recipes/hermes.yaml` — validated 2026-04-15 with `openai/gpt-4o-mini` via OpenRouter, wall 16.3s. Recon via Solvr `clawdbot-hermes-helper` + bespoke subagent + `tools/run_recipe.py` first-run PASS. **Self-improving:** 79 bundled skills + user skills + persistent memory + SQLite session store with FTS5 + cron scheduler + cross-platform messaging gateway. Closed learning loop.

- [x] **OpenClaw** — https://github.com/openclaw/openclaw — TypeScript/Node 24, 358k stars, 2026.4.15-beta.1 — `recipes/openclaw.yaml` — validated 2026-04-15 with `anthropic/claude-haiku-4-5` via OpenRouter, wall 72.5s. Recon: direct source read + Solvr follow-up to `clawdbot-hermes-helper`. **Required format innovation:** bash-chained `openclaw config set agents.defaults.model openrouter/<model>` before `infer model run --local --json` — the `--model` flag on `infer model run` is decorative; the embedded agent runtime reads its lane model from the config file, not the CLI flag. **Self-improving:** skills, workspace continuity, multi-channel gateway, agent lanes with memory/context. **Known model incompatibility:** `openai/gpt-4o-mini` via OpenRouter returns `attempts: []` and "⚠️ Agent couldn't generate a response" — not a recipe bug, a model-side contract mismatch with openclaw's embedded agent turn dispatch. Claude models work fine.

- [x] **PicoClaw** — https://github.com/sipeed/picoclaw — Go 1.25, 28k stars, v0.2.4+ — `recipes/picoclaw.yaml` — validated 2026-04-15 with `openai/gpt-4o-mini` via OpenRouter, wall **2.6s**. Recon: direct source + built-image empirical check + Solvr correction (MSV's `infra/picoclaw/` is OpenClaw-wrapped, not sipeed/picoclaw — name collision). **Required format innovation:** `invoke.spec.entrypoint` override (`sh`) to bypass upstream `docker/entrypoint.sh`'s two-stage `onboard → exit` flow, plus sh-heredoc-templated `config.json` written before the invoke so `picoclaw agent -m` finds an openrouter-routed model. Runner extended to honor `entrypoint` field. **Self-improving:** workspace state, skills, persistent session store, multi-channel gateway. **Ultra-lightweight**: ~200 MB image (vs ~5 GB for hermes/openclaw), single Go binary, Alpine base.

- [x] **NullClaw** — https://github.com/nullclaw/nullclaw — **Zig** 0.15.2+, 7.2k stars, 2026.4.9+ — `recipes/nullclaw.yaml` — validated 2026-04-15 with `anthropic/claude-haiku-4-5` via OpenRouter, wall **2.5s** (tied with picoclaw for fastest). Recon: direct source read (no Solvr helper). **Required format innovation:** sh-chained two-step `nullclaw onboard --api-key ... --provider openrouter` → `nullclaw agent -m "..." --model "openrouter/..."` inside a single container. Upstream Dockerfile *already bakes* `openrouter/anthropic/claude-sonnet-4` as the default model — we only inject the API key via onboard. **Self-improving:** 10 memory engines, 35+ tools, MCP, subagents, 50+ providers, 19 channels. **Ultra-ultra-lightweight**: **678 KB static binary**, ~1 MB RAM, <8 ms startup. **Smoke finding:** the default `who are you?` prompt returns a blank-slate persona ("I don't have a name yet..."), so the recipe uses `"What is NullClaw? Reply in one short sentence starting with 'NullClaw is'."` to force the keyword into the response. Documented in recipe under `smoke.known_weak_probes`.

- [x] **nanobot** (HKUDS) — https://github.com/HKUDS/nanobot — Python 3.11+, 39.6k stars, v0.1.5.post1 — `recipes/nanobot.yaml` — validated 2026-04-15 with `openai/gpt-4o-mini` via OpenRouter. Recon: direct source + built-image empirical CLI check. **Required format innovation:** JSON config.json heredoc with **explicit `agents.defaults.provider: "openrouter"` override** to prevent nanobot's auto-provider resolver from sending the full `openrouter/<model>` prefixed string to the OpenRouter API. First attempt with `provider: auto` returned HTTP 400 "not a valid model ID"; explicit provider fixes it. **Self-improving:** skills, dream memory, context compaction, cron scheduler, 13+ channel plugins, heartbeat. nanobot is the original project PicoClaw was ported from — the `agent -m` CLI signature is 1:1 identical. **Known quirk:** Rich streaming UI emits ANSI cursor/spinner codes even with `--no-markdown`; plain text response extractable but not 100% clean.

### Recon targets — self-improving (by highest stars, per user direction 2026-04-15)

Remaining clawclones.com candidates, sorted by ★ desc:

- [ ] **ZeroClaw** — 30,171 ★ — Rust — https://github.com/zeroclaw-labs/zeroclaw (verify org) — security-by-default, ~8 MB binary, 8 ms boot. **Next.**
- [ ] **AstrBot** — 30,013 ★ — Python — https://github.com/Soulter/AstrBot (verify) — polished multi-platform chatbot framework, QQ/WeChat/15+ channels, plugin marketplace, sandboxed skill execution.
- [ ] **AionUi** — 21,898 ★ — TypeScript — cross-platform "Cowork" desktop app, multi-agent orchestration.
- [ ] **OpenFang** — 16,641 ★ — Rust — "Agent Operating System", 32 MB binary, 137K LOC, autonomous 24/7 Hands.
- [ ] **CoPaw** — 15,401 ★ — Python — Alibaba's AgentScope-based personal AI workstation.
- [ ] **IronClaw** — 11,786 ★ — Rust — security-first, WASM sandbox, Ed25519-signed plugins.
- [ ] **LobsterAI** — 5,028 ★ — TypeScript — NetEase Youdao Electron desktop with Alpine sandbox.
- [ ] **MimiClaw** — 5,177 ★ — C — ESP32-S3 embedded, 16 MB flash.
- [ ] **TinyClaw** — 3,512 ★ — TypeScript — multi-agent orchestration monorepo.
- [ ] **MetaClaw** — 3,407 ★ — Python — "talk to your agent, it learns and evolves".
- [ ] **Goclaw** — 2,726 ★ — Go — extreme perf + dev ergonomics.
- [ ] **Moltis** — 2,557 ★ — Rust — sandboxed execution, single-binary, zero Node.js.
- [ ] **Spacebot** — 2,086 ★ — Rust — concurrent multi-process agent, team collab.
- [ ] **zclaw** — 2,074 ★ — C — ESP32 firmware, 888 KiB hard cap, IoT.
- [ ] **ThePopeBot** — 1,682 ★ — JavaScript — self-evolving via GitHub Actions.
- [ ] **DroidClaw** — 1,382 ★ — TypeScript — Android accessibility-tree control.
- [ ] **Poco** — 1,281 ★ — TypeScript — polished UI, artifacts rendering, Claude Code.
- [ ] **Picobot** — 1,176 ★ — Go — ~9 MB binary, persistent memory, zero bloat.
- [ ] **MicroClaw** — 649 ★ — Rust — 13+ channels, Docker sandboxing.
- [ ] **Loongclaw** — 613 ★ — Rust — "learn easily, customize anything".
- [ ] **ZeptoClaw** — 591 ★ — Rust — 6 MB binary, defense-in-depth TOCTOU mitigation.
- [ ] **Ouroboros** — 493 ★ — Python — self-modifying agent, git-based identity.
- [ ] **memU Bot** — 377 ★ — TypeScript — enterprise memory-first.
- [ ] **LettaBot** — 314 ★ — TypeScript — Letta SDK, multi-channel memory.
- [ ] **SmallClaw** — 233 ★ — TypeScript — local-first, optimized for small models.
- [ ] **n8nClaw** — 223 ★ — TypeScript — visual n8n workflows.
- [ ] **GitClaw** — 208 ★ — TypeScript — agents as git repos.
- [ ] **LightClaw** — 205 ★ — Rust — 15 MB single binary.
- [ ] **SafeClaw** — 131 ★ — Python — **out of scope** (deterministic, NO LLM — can't smoke test via OpenRouter).
- [ ] **OpenGork** — 110 ★ — Shell — Grok "Heretic Mode" wrapper.
- [ ] **AndyClaw** — 77 ★ — Kotlin — Android local-LLM on ethOS.
- [ ] **Freeclaw** — 54 ★ — Python — NVIDIA NIM / Groq / OpenRouter free-tier.
- [ ] **Carapace** — 43 ★ — Rust — Ed25519-signed WASM plugins.
- [ ] **TitanClaw** — 24 ★ — Rust — swarm mesh, WASM tools.
- [ ] **KafClaw** — 18 ★ — Go — Apache Kafka multi-agent orchestration.
- [ ] **grip-ai** — 6 ★ — Python — Claude Agent SDK + LiteLLM fallback.
- [ ] **BashoBot** — 6 ★ — Shell — pure Bash with named pipes.

### Blocked / deferred
- **NanoClaw** — https://github.com/qwibitai/nanoclaw — TypeScript, 27k stars, "Lightweight alternative to OpenClaw... runs directly on Anthropic's Agents SDK". **BLOCKED(format)** 2026-04-15. Reasons (in order of hardness):
  1. **OneCLI Agent Vault is mandatory** — `src/container-runner.ts:218` imports `OneCLI` from `@onecli-sh/sdk` and creates a client with `ONECLI_URL`+`ONECLI_API_KEY`. The agent container NEVER holds raw API keys; credentials are injected at request time by a separate OneCLI host service. Without OneCLI running on the host, no API calls happen. This is an external-service dependency the v0 recipe format does not support.
  2. **Claude Agent SDK only** — `container/Dockerfile:35` installs `@anthropic-ai/claude-code` as the execution engine. OpenRouter routing would require `ANTHROPIC_BASE_URL` override inside the sandboxed agent container AND bypassing OneCLI's credential injection. Fragile and upstream-unsupported.
  3. **AI-native install flow** — README prescribes `gh repo fork → claude → /setup` (inside a Claude Code session), not a programmatic setup. Recipes consume programmatic install paths.
  4. Orchestrator vs agent split: `src/index.ts` is a long-running polling loop; only the spawned agent container (`container/Dockerfile`) accepts stdin JSON (`{prompt, groupFolder, chatJid, isMain}` per `container/build.sh:96`). Fitting only the inner container would still need OneCLI and Claude SDK.
  **What v0 format is missing to unblock**: `runtime.external_services[]` (declaring required sidecar services like OneCLI), `setup.interactive: true` escape hatch, and an `invoke.provider_proxy` field for SDK-native agents. Deferred until v1 when we have more agents demanding the same fields.
- **TrustClaw** — https://github.com/trustclaw/trustclaw — 2 stars, TypeScript, description is word-for-word copy of OpenClaw ("Your own personal AI assistant. Any OS. Any Platform. The lobster way. 🦞"). **SKIPPED** — indistinguishable from a fork/clone of openclaw; no recon value.

### Removed from scope

- **OpenHands** — https://github.com/All-Hands-AI/OpenHands — Python, 71k stars. Attempted 2026-04-15 as an architectural-diversity add-on. Found to be **out of clawclones.com scope entirely** (All-Hands-AI is a different lineage — formerly OpenDevin — not part of the OpenClaw family the v0 backlog tracks). Also hit a format mismatch: response goes to trajectory JSON files + auto-continue flow either hangs or auto-finishes before response capture, and V0 headless main.py is deprecated with a scheduled-removal banner ("April 1, 2026"). Backed out cleanly; `ap-recipe-openhands` image and `recipes/openhands.yaml` removed 2026-04-15 (reclaimed ~15 GB).

---

## v1 — pure LLM wrappers (deferred)

These agents work fine under AP but don't benefit from the persistent sandbox story. Valid targets for v1 once v0 ships.

- [v1] **Aider** — https://aider.chat — pip-installable, Python CLI, LiteLLM backend. Recipe was drafted and validated PASS on 2026-04-15 against `openai/gpt-4o-mini`, then removed from the repo when scope pivoted to self-improving-only. Notes kept in recon archives for when v1 reopens this lane.
- [v1] **Goose** (Block) — https://block.github.io/goose — Rust/Python, MCP-focused, offline-capable.
- [v1] **Plandex** — https://plandex.ai — Go client/server, planning-focused.
- [v1] **Browser-use** — https://github.com/browser-use/browser-use — Python browser automation.
- [v1] **Agent Zero** — https://github.com/frdel/agent-zero — Python agent framework.
- [v1] **Skyvern** — https://skyvern.com — browser automation. Freemium.
- [v1] **LaVague** — https://lavague.ai — browser automation.
- [v1] **Sweep** — https://sweep.dev — GitHub App, PR-scoped. Likely requires a GitHub App install.
- [v1] **MicroAgent** — verify org.
- [v1] **MultiOn** — https://multion.ai — closed source / API-only. May not install as a CLI at all.
- [v1] **Daybreak** — https://daybreak.ai — verify scope.

## Frameworks (not agents)

- [?] **CrewAI** — https://crewai.com — multi-agent orchestration framework, not an agent itself.
- [?] **Microsoft AutoGen** — https://microsoft.github.io/autogen — same shape as CrewAI.

## Out of scope

- [-] **E2B** — https://e2b.dev — sandbox infrastructure. Could be a *backend* for Agent Playground, not a recipe target.
- [-] **Vellum** — https://vellum.ai — LLM ops / prompt management platform.
- [-] **Eesel AI** — https://eesel.app — internal team Q&A over docs.
- [-] **Zep** — https://getzep.com — memory/context store.

---

## Selection heuristic for v0

Pick the next target by prioritizing:

1. **Self-improvement shape** — does the agent have skills/memory/learning loops that benefit from a persistent per-user sandbox? If no, defer to v1.
2. **Architectural diversity** from what's already validated. Hermes is Python + Docker + TUI + heavy `[all]` extras. Next pick should be a different shape: different language, different install strategy, different invocation surface — to stress the recipe format.
3. **OpenRouter compatibility** — must honor `OPENROUTER_API_KEY` directly or via a LiteLLM-style routing layer.
4. **Non-interactive surface** — must support "one prompt in, one reply out" without a human keyboard.

Agents that fail checks 3 or 4 become `BLOCKED (<reason>)` findings recorded here.
