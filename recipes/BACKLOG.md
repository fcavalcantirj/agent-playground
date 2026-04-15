# Agent Recipe Backlog

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

### Recon targets — self-improving

- [~] **OpenClaw** — https://github.com/openclaw/openclaw — TypeScript, 358k stars, the direct ancestor of Hermes (hermes ships a `claw migrate` command to import OpenClaw state). Self-improving with skills, memory, and workspace continuity. **Next pick.** Canonical repo confirmed via GitHub API 2026-04-15; `johnlanni/openclaw` (1 star, `hiclaw` branch) is a personal fork, ignore KICKOFF.md's outdated note.
- [ ] **PicoClaw** — https://github.com/sipeed/picoclaw — smaller sibling in the clawclones family. Canary-tested 2026-04-15 against an earlier protocol draft; needs a fresh recon run against the matured `ap.recipe/v0` format. **Verify scope:** is it a learning-loop agent or a minimalist wrapper? Read docs before committing to the flagship list.
- [ ] **NanoClaw** — https://github.com/qwibitai/nanoclaw — smallest of the clawclones family. **Verify scope** before shipping in v0 — if it's a pure wrapper, defer to v1.
- [ ] **NullClaw** — verify source URL and scope. Claw family, learning loop unknown.
- [ ] **TrustClaw** — https://trustclaw.ai — verify source URL and scope.

### Recon targets — architectural diversity (maybe self-improving, need to verify)

- [ ] **OpenHands** (ex-OpenDevin) — https://github.com/All-Hands-AI/OpenHands — Docker-first, runs its own orchestrator + browser + web UI. Likely has memory/persistent state; verify whether it's a learning loop or a session-bound task runner. Heavy, architecturally very different from the claw family.

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
