---
name: picoclaw
real: true
source: https://github.com/sipeed/picoclaw
language: Go
license: MIT
stars: 28142
last_commit: 2026-04-14
---

# PicoClaw

## L1 — Paper Recon

**Install mechanism:** precompiled binary (official site/GitHub Releases) or `git clone` + `make build`. Docker Compose also supported. Single static Go binary.

**Install command:**
```
# Option A: download binary from https://picoclaw.io (auto-detects arch)
# Option B: from GitHub releases tarball
wget https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_Linux_<arch>.tar.gz
tar xzf picoclaw_Linux_<arch>.tar.gz
./picoclaw onboard

# Option C: build from source (requires Go 1.25+, Node 22+, pnpm for WebUI)
git clone https://github.com/sipeed/picoclaw.git && cd picoclaw && make deps && make build
```

**Supported providers:** OpenAI (and OpenAI-compatible), Anthropic (via `.security.yml` per README v0.2.4 notes), OpenRouter, DeepSeek, AWS Bedrock, Azure, Xiaomi MiMo, Kimi/Moonshot, MiniMax, Avian, GLM/z.ai, and any OpenAI-compatible endpoint via `model_list` entries.

**Model-selection mechanism:** `picoclaw model` CLI subcommand to show/change default, or declarative `model_list` entries in `~/.picoclaw/config.json` with `model_name` + `model` (provider/id) fields. `agents.defaults.model_name` selects which is active.

**Auth mechanism (best guess from docs):** API keys live in `~/.picoclaw/.security.yml` (split from `config.json` in v1+; config.json migration auto-moves secrets). Also supports `picoclaw auth` subcommand (login/logout/status) — likely for Nous/Sipeed cloud-style identity, not LLM keys. BYOK path is the YAML secrets file.

**Chat I/O shape:** Multiple modes:
- `picoclaw agent -m "question"` → one-shot stdout
- `picoclaw agent` → interactive REPL (stdin/stdout)
- `picoclaw gateway` → long-running process fronting chat apps (Telegram, Matrix, IRC, WeCom, Discord proxy) and a WebUI on `:18800`
- WebUI launcher (`picoclaw-launcher`) with browser chat
- TUI launcher (`picoclaw-launcher-tui`)

**Persistent state needs:** `~/.picoclaw/` workspace directory created by `picoclaw onboard`. Contains `config.json`, `.security.yml`, JSONL memory store, skills, sessions. Docker image in our sandbox bakes this under `/home/agent/.picoclaw/`.

**Notes from README (anything unusual for sandboxing):**
- "Do not deploy to production before v1.0" — README explicitly flags unresolved security issues.
- Recent builds may use 10–20MB RAM (not the marketed <10MB). Still extremely light.
- Has a `.security.yml` auto-migration step on first run that rewrites `config.json` — we must ship that file or run `onboard` in the container entrypoint.
- Gateway binds `127.0.0.1` by default; for containerized use set `PICOCLAW_GATEWAY_HOST=0.0.0.0` or pass `-public`.
- MCP protocol supported natively — we could proxy tool calls via MCP if needed.
- Smart routing layer can route simple queries to cheaper models — billing implication: one user turn may fan out to multiple upstream calls.
- Local `--help` confirms subcommands: `agent`, `auth`, `cron`, `gateway`, `migrate`, `model`, `onboard`, `skills`, `status`, `version`.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
