# Agent Recipe Backlog

Tracking agents we want to validate against `ap.recipe/v0`. A row flips to `[x]` only when the recipe is committed **and** `tools/run_recipe.py` returns `PASS` against at least one model cell.

**Status legend**

- `[ ]` todo — not started
- `[~]` in progress — recon or runner iteration under way
- `[x]` done — recipe committed, runner PASS
- `[-]` skipped — not a coding agent / out of scope
- `[?]` deferred — needs a decision before we work on it

---

## Completed

- [x] **Hermes Agent** (Nous Research) — https://github.com/NousResearch/hermes-agent — `recipes/hermes.yaml` — validated 2026-04-15 with `openai/gpt-4o-mini` via OpenRouter, wall 16.3s, payload `"I'm Hermes, your CLI AI agent..."`. Recon via Solvr `clawdbot-hermes-helper` + bespoke subagent + `tools/run_recipe.py` first-run PASS.

---

## Recon targets — coding agents

- [ ] **Aider** — https://aider.chat — pip-installable Python CLI, `--model` flag, OpenRouter-compatible via `OPENAI_API_BASE`. Lightweight baseline to stress-test the recipe format against a non-Docker-native agent. **(Next pick.)**
- [ ] **OpenHands** (ex-OpenDevin) — https://github.com/All-Hands-AI/OpenHands — Docker-first, runs its own orchestrator + browser + web UI. Heavy, architecturally different.
- [ ] **Goose** (Block) — https://block.github.io/goose — Rust/Python CLI, MCP-focused, can run offline. Different stack.
- [ ] **Plandex** — https://plandex.ai — Go client/server model. Different language stack.
- [ ] **Browser-use** — https://github.com/browser-use/browser-use — Python, browser automation focus.
- [ ] **Agent Zero** — https://github.com/frdel/agent-zero — Python agent framework (verify org).
- [ ] **Skyvern** — https://skyvern.com — browser automation. Likely freemium.
- [ ] **LaVague** — https://lavague.ai — browser automation.
- [ ] **Sweep** — https://sweep.dev — GitHub-integrated code reviewer. May need a GitHub App.
- [ ] **MicroAgent** — https://github.com/... (verify org).
- [ ] **PicoClaw** — https://github.com/sipeed/picoclaw — canary-tested 2026-04-15 against an earlier protocol draft. Rerun once the recipe format has matured.
- [ ] **NanoClaw** — https://github.com/qwibitai/nanoclaw — from `recon/KICKOFF.md`.
- [ ] **NullClaw** — verify source.
- [ ] **TrustClaw** — https://trustclaw.ai — verify source.
- [ ] **Daybreak** — https://daybreak.ai — verify scope.
- [ ] **MultiOn** — https://multion.ai — likely closed source / API-only. May not install as a CLI.

## Frameworks (may not be "agents" per se)

- [?] **CrewAI** — https://crewai.com — multi-agent orchestration framework. Question: does it install as a runnable "agent" or is it a library to build agents with?
- [?] **Microsoft AutoGen** — https://microsoft.github.io/autogen — same question as CrewAI.

## Out of scope — not coding agents

- [-] **E2B** — https://e2b.dev — sandbox infrastructure (compute primitive). Could be a *backend* for Agent Playground, not a recipe target.
- [-] **Vellum** — https://vellum.ai — LLM ops / prompt management platform.
- [-] **Eesel AI** — https://eesel.app — internal team Q&A over docs.
- [-] **Zep** — https://getzep.com — memory/context store for agents.

If any `[-]` entry should actually be in scope, say the word and I'll rescope it.

---

## Selection heuristic

When picking the next target, prefer:

1. **Architectural diversity** from what's already validated. Last one was Docker-heavy (hermes, 5.19 GB) — next pick should be lightweight (pip-based).
2. **OpenRouter compatibility** — must honor `OPENAI_API_BASE`/`OPENAI_API_KEY` or have a first-class OpenRouter provider.
3. **Non-interactive surface** — must support "one prompt in, one reply out" without a human keyboard.

Agents that fail any of these become `BLOCKED (<reason>)` findings, not recipes — that's still useful data and gets recorded here.
