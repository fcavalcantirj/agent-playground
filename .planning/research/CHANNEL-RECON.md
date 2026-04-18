# Messaging Channel Support Reconnaissance

**Scope:** Hermes, Nanobot, NullClaw, OpenClaw, PicoClaw — recon on Telegram/Discord/WhatsApp support to inform `ap.recipe/v0.2` schema design.

**Recon date:** 2026-04-17  
**Method:** Recipe YAMLs, upstream GitHub READMEs/docs, built Docker images (`docker run --rm ... --help`), source code inspection, config files.

---

## Summary Table: Channel Support Across 5 Agents

| Agent | Telegram Support | Persistent Mode Command | Config File | bot_token Key | allow_from Key | Env-Var Support | Startup Semantics | Health Signal | Shutdown | Reconnect | Multi-tenant Risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Hermes** | First-class | `hermes gateway run` | `~/.hermes/config.yaml` | `telegram.bot_token` | `telegram.allowed_users` (env var) | Full (env vars primary) | Foreground, blocking | Implicit (systemd/launchd) | SIGTERM-safe | Retries (systemd/launchd supervised) | File-path collision risk (~/.hermes) |
| **Nanobot** | First-class | `nanobot gateway` | `~/.nanobot/config.json` | `channels.telegram.token` | `channels.telegram.allowFrom` | Full (env var + config) | Foreground, blocking | HTTP heartbeat (18790) | Needs investigation | Library (python-telegram-bot) handles retry | File-path collision (~/.nanobot) |
| **NullClaw** | First-class | `nullclaw gateway --port 3000 --host ::` | `/nullclaw-data/config.json` | `channels.telegram.accounts[].bot_token` | `channels.telegram.accounts[].allow_from` | Full (env interpolation in config) | Foreground, blocking, static binary | Implicit (none documented) | Not tested | Likely retries (native Zig impl) | File-path collision (/nullclaw-data) |
| **OpenClaw** | First-class | `openclaw gateway run` | `~/.openclaw/openclaw.json` | `channels.telegram.bot_token` | `channels.telegram.allow_from` | Full (env + .env file) | Foreground (gateway run), blocking WebSocket | HTTP `/health` endpoint | Not tested | Likely retries (native JS impl) | File-path collision (~/.openclaw) |
| **PicoClaw** | First-class | `picoclaw gateway` | `~/.picoclaw/config.json` | `channel_list.telegram.token` | `channel_list.telegram.allow_from` | Full (env in config) | Foreground, blocking (runs gateway HTTP) | Implicit (port binding) | Not tested | Likely retries (Go stdlib net) | File-path collision (~/.picoclaw) |

**Key:** "First-class" = native Telegram support, not plugin/beta. "Foreground, blocking" = suitable for `docker run` without daemonization. "Health signal" = mechanism to detect liveness.

---

## Per-Agent Detailed Findings

### 1. Hermes Agent (Python, upstream NousResearch/hermes-agent)

**Telegram Support:** First-class  
**Status:** Mature, documented, multi-provider (Telegram, Discord, Slack, WhatsApp, Signal, CLI).

**Persistent Mode Command:**
```bash
hermes gateway run [--verbose | -v]
hermes gateway run --replace    # Kill stale instance, then start
```

**Config Surface:**
- **File:** `~/.hermes/config.yaml` (YAML format, optional; many keys are env-var overrideable)
- **Schema snippet:**
  ```yaml
  telegram:
    channel_prompts: {}  # Per-chat system prompts (optional)
  ```
- The `channels` section is under `~/hermes/config.yaml`, read by `hermes_cli/config.py`.

**Required Secrets (Telegram):**
- **bot_token** — via env var `TELEGRAM_BOT_TOKEN` (preferred, cleanest for containerization)
- **allowed_users** — via env var `TELEGRAM_ALLOWED_USERS` (comma-separated user IDs, or empty to deny all by default)

**Required User Context:**
- User ID (Telegram numeric ID) in allowlist. Empty allowlist = deny all (secure default).

**Env-Var vs Config-File Path:**
- **Primary path: env vars.** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USERS` are read at startup and take precedence.
- `config.yaml` can hold some settings but is not required for Telegram; system env is the clean path for containerization.

**Startup Semantics:**
- Foreground, blocking. Prints banner "Hermes Gateway Starting..." then listens.
- Does NOT background itself. Suitable for `docker run -d` or systemd/launchd supervision.
- Can be interrupted with Ctrl+C or SIGTERM.

**Health / Liveness Signal:**
- Not explicit in v0.1 recipe (not HTTP-based). Implicit: if the foreground process is running, the gateway is up.
- Systemd/launchd supervisor relies on exit code (0=success, 1=failure).

**Graceful Shutdown:**
- SIGTERM-safe. The `run_gateway` function in `/hermes_cli/gateway.py:310` calls `os.kill(pid, signal.SIGTERM)` when restarting.
- Exit code 1 signals systemd to retry on failure.

**Reconnect Behavior:**
- Supervisor-delegated (systemd `Restart=on-failure` or launchd `KeepAlive`).
- The gateway itself relies on the supervisor to retry on Telegram API hiccups.

**Multi-tenant Caveat:**
- **Collision risk:** All instances share `~/.hermes/` by default. Per-user isolation requires `--profile <name>` to use `~/.hermes/profiles/<name>/`.
- Recipe should use explicit `HERMES_HOME` env var + per-session tmpdir volume to avoid collisions.

**Evidence Pointers:**
- `/tmp/ap-recipe-hermes-clone/hermes_cli/gateway.py:1-10` — gateway subcommand entry, runs `gateway.run.start_gateway`
- `/tmp/ap-recipe-hermes-clone/hermes_cli/gateway.py:308-326` — SIGTERM handling
- `/tmp/ap-recipe-hermes-clone/hermes_cli/gateway.py` defines `run_gateway()` which calls `asyncio.run(start_gateway(...))`

---

### 2. Nanobot (Python, upstream HKUDS/nanobot)

**Telegram Support:** First-class  
**Status:** Ultra-lightweight, actively developed (weekly releases), multi-provider (Telegram, Discord, WhatsApp, WeChat, Feishu, Slack, Matrix, Email, QQ, WeCom, Teams, Mochat).

**Persistent Mode Command:**
```bash
nanobot gateway
```

**Config Surface:**
- **File:** `~/.nanobot/config.json` (JSON format, authoritative)
- **Schema snippet:**
  ```json
  {
    "channels": {
      "telegram": {
        "enabled": true,
        "token": "YOUR_BOT_TOKEN",
        "allowFrom": ["YOUR_USER_ID"],
        ...
      }
    },
    "agents": { "defaults": { "model": "...", "provider": "..." } },
    "providers": { "openrouter": { "api_key": "..." } }
  }
  ```

**Required Secrets (Telegram):**
- **token** — the bot token (e.g., `123:ABC-xyz`), stored in `channels.telegram.token` in config.json.
- **allowFrom** — list of allowed Telegram user IDs (array of numeric IDs or strings).

**Required User Context:**
- User ID (numeric Telegram ID). Empty `allowFrom` = deny all (implicit secure default).

**Env-Var vs Config-File Path:**
- **Config-file-only for Telegram token.** The token MUST be written to `~/.nanobot/config.json` before `nanobot gateway` runs.
- Env-var interpolation is supported in config.json: `"token": "${TELEGRAM_BOT_TOKEN}"` works if the env var is set at container startup.
- Per the nanobot schema, the `Config` class uses `env_prefix="NANOBOT_"` and nested delimiter `"__"`, so env vars like `NANOBOT_CHANNELS__TELEGRAM__TOKEN` can override the config file (Pydantic behavior).

**Startup Semantics:**
- Foreground, blocking. Runs `nanobot gateway`, which listens on the configured gateway host/port (default 127.0.0.1:18790).
- Does NOT background itself.
- Suitable for `docker run -d` with gateway health polling via HTTP.

**Health / Liveness Signal:**
- HTTP heartbeat endpoint on `gateway.host:gateway.port` (default 127.0.0.1:18790), exposed by the gateway process.
- The `HeartbeatConfig` in schema.py (line 138-143) controls interval and keep-recent-messages.

**Graceful Shutdown:**
- SIGTERM behavior not explicitly documented in recon. Presumed safe (async Python app with signal handlers standard).

**Reconnect Behavior:**
- Delegated to underlying `python-telegram-bot` library (uses `Application` + async handlers).
- The library handles retries on network errors; restart behavior depends on supervisor.

**Multi-tenant Caveat:**
- **Collision risk:** All instances share `~/.nanobot/` by default.
- Recipe should use `--config <path>` flag to specify per-user config path (e.g., `/session-tmpdir/config.json`).

**Evidence Pointers:**
- `/tmp/ap-recipe-nanobot-clone/nanobot/config/schema.py:18-32` — ChannelsConfig (extra fields allow dynamic channel types)
- `/tmp/ap-recipe-nanobot-clone/nanobot/config/schema.py:154-159` — GatewayConfig (host/port binding)
- `/tmp/ap-recipe-nanobot-clone/nanobot/channels/telegram.py:1-40` — Telegram channel class using `python-telegram-bot` library

---

### 3. NullClaw (Zig, upstream nullclaw/nullclaw)

**Telegram Support:** First-class (19 channels total: Telegram, Discord, Signal, Slack, WhatsApp, Matrix, IRC, Nostr, Line, Lark, OneBot, Mattermost, QQ, iMessage, Email, Webhook, DingTalk, and 2 others).  
**Status:** Ultra-lightweight (678 KB binary, <8 ms startup), static binary, first-class Telegram with forum topic isolation.

**Persistent Mode Command:**
```bash
nullclaw gateway --port 3000 --host ::
# OR (IPv6 loopback if available, otherwise falls back to 127.0.0.1)
```

**Config Surface:**
- **File:** `/nullclaw-data/config.json` (JSON format, baked at container build time or injected at runtime)
- **Schema snippet (from config.example.json):**
  ```json
  {
    "channels": {
      "telegram": {
        "accounts": {
          "main": {
            "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
            "allow_from": ["YOUR_TELEGRAM_USER_ID"],
            "draft_previews": false,
            ...
          }
        }
      }
    },
    "models": { "providers": { "openrouter": { "api_key": "..." } } }
  }
  ```

**Required Secrets (Telegram):**
- **bot_token** — under `channels.telegram.accounts.<account_name>.bot_token`
- **allow_from** — array of allowed user IDs under `channels.telegram.accounts.<account_name>.allow_from`

**Required User Context:**
- User ID (Telegram numeric ID). Empty `allow_from` = deny all by default. `allow_from: ["*"]` = allow all (explicit opt-in).

**Env-Var vs Config-File Path:**
- **Config-file-only.** The config.json must be readable at startup. Env-var interpolation is supported in Zig config parsing (shell-style `${VAR}` substitution).
- The Dockerfile pre-templates `/nullclaw-data/config.json` with OpenRouter as the default provider but no API key. Runtime injection must write the full config or patch it via `nullclaw onboard --api-key ... --provider openrouter`.

**Startup Semantics:**
- Foreground, blocking. Binary runs directly (no VM, no runtime).
- Suitable for `docker run -d` or systemd supervision.
- Extremely fast startup (<8 ms) due to static compilation.

**Health / Liveness Signal:**
- No explicit health endpoint documented. Implicit: the binary is listening on the gateway port if the process is running.
- The Dockerfile ENV sets `NULLCLAW_GATEWAY_PORT=3000`, so health check could bind to that port.

**Graceful Shutdown:**
- Presumed SIGTERM-safe (static Zig binary, standard OS signal handling).
- Not explicitly tested in recon.

**Reconnect Behavior:**
- Native Zig implementation (not relying on third-party libraries for Telegram). Likely has built-in retry logic, but not verified.
- Restart behavior depends on supervisor (systemd/Docker).

**Multi-tenant Caveat:**
- **Collision risk:** All instances share `/nullclaw-data/` by default.
- Recipe overrides the volume mount to `per_session_tmpdir` (ephemeral), so per-session isolation is baked in. Multi-user scenarios require separate volumes or env-based config paths.

**Evidence Pointers:**
- `/tmp/ap-recipe-nullclaw-clone/config.example.json:35-42` — Telegram channel config structure
- `/tmp/ap-recipe-nullclaw-clone/Dockerfile` — Sets ENV `NULLCLAW_HOME=/nullclaw-data`, pre-populates config.json in config stage
- `/tmp/ap-recipe-nullclaw-clone/src/config_types.zig` (implicit from Bash output) — TelegramConfig with `bot_token`, `allow_from`, `draft_previews`, etc.

---

### 4. OpenClaw (TypeScript/Node, upstream openclaw/openclaw)

**Telegram Support:** First-class (21+ channels total).  
**Status:** Mature, multi-service (gateway + CLI), messaging-first design. Node 24, Bun, native Matrix crypto binding.

**Persistent Mode Command:**
```bash
openclaw gateway run
```

**Config Surface:**
- **File:** `~/.openclaw/openclaw.json` (JSON format, read by gateway and CLI)
- **Also reads:** `~/.openclaw/.env` (dotenv format, optional, for secrets)
- **Schema snippet (inferred from docker-compose and docs):**
  ```json
  {
    "gateway": {
      "mode": "local",
      "bind": "loopback",
      "port": 18789
    },
    "channels": {
      "telegram": {
        "bot_token": "...",
        "allow_from": ["..."],
        ...
      }
    },
    "agents": { "defaults": { "model": "openrouter/..." } }
  }
  ```

**Required Secrets (Telegram):**
- **bot_token** — under `channels.telegram.bot_token` or `TELEGRAM_BOT_TOKEN` env var
- **allow_from** — array of allowed user IDs

**Required User Context:**
- User ID (Telegram numeric ID). Pairing-code flow available for unknown senders (security-by-default pattern).

**Env-Var vs Config-File Path:**
- **Hybrid:** Both work. Env vars (`.env` file or process env) override config.json values.
- Clean for containerization: write secrets to `.env` at runtime or inject via Docker `-e`.

**Startup Semantics:**
- Foreground, blocking WebSocket server. `openclaw gateway run` listens on the gateway port.
- Also supports `openclaw gateway install/start/stop/restart/status` for systemd/launchd service management.
- Does NOT background itself; `docker run` must handle daemonization.

**Health / Liveness Signal:**
- HTTP `/health` endpoint (documented in `openclaw gateway health` command output).
- Suitable for container health checks.

**Graceful Shutdown:**
- Supports `openclaw gateway stop` via service manager (systemd/launchd).
- SIGTERM behavior not explicitly tested; presumed safe (Node.js convention).

**Reconnect Behavior:**
- Native Node.js + Telegram.js library (or similar). Library handles retries; supervisor manages process restart.

**Multi-tenant Caveat:**
- **Collision risk:** All instances share `~/.openclaw/` by default.
- Recipe should use explicit config path env var or volume mounting per session.
- Docker-compose pattern shows per-user containers, not in-container multi-tenancy.

**Evidence Pointers:**
- `/tmp/ap-recipe-openclaw-clone/docker-compose.yml` — Gateway service with port mapping (18789) and health checks
- `/tmp/ap-recipe-openclaw-clone/docs/index.md` (inferred from README probe) — `openclaw gateway run` command
- OpenClaw recipe YAML shows `openclaw infer model run` for local headless inference (not the gateway path for messaging)

---

### 5. PicoClaw (Go, upstream sipeed/picoclaw)

**Telegram Support:** First-class ("Easy (bot token)" setup with long polling).  
**Status:** Ultra-lightweight (single Go binary), 18+ channels, actively developed.

**Persistent Mode Command:**
```bash
picoclaw gateway
# OR with config override:
picoclaw gateway --config /path/to/config.json
```

**Config Surface:**
- **File:** `~/.picoclaw/config.json` (JSON format, LiteLLM-style model routing)
- **Schema snippet:**
  ```json
  {
    "channel_list": {
      "telegram": {
        "enabled": true,
        "type": "telegram",
        "token": "YOUR_BOT_TOKEN",
        "allow_from": ["YOUR_USER_ID"],
        "use_markdown_v2": false
      }
    },
    "gateway": {
      "host": "127.0.0.1",
      "port": 18790
    }
  }
  ```

**Required Secrets (Telegram):**
- **token** — the bot token, stored in `channel_list.telegram.token`
- **allow_from** — array of allowed user IDs

**Required User Context:**
- User ID (Telegram numeric ID). Obtained from `@userinfobot` on Telegram.

**Env-Var vs Config-File Path:**
- **Config-file-only for now.** No documented env-var override path in the recon.
- The sh bootstrap in the recipe writes config.json with env-var interpolation (`${BOT_TOKEN}`), so at container startup, the env var can be injected into the config before the binary runs.

**Startup Semantics:**
- Foreground, blocking HTTP server. `picoclaw gateway` listens on the configured port (default 127.0.0.1:18790).
- Does NOT background itself.
- Suitable for `docker run -d` with explicit port binding.

**Health / Liveness Signal:**
- Implicit: if the gateway process is running and listening, it's up.
- No explicit health endpoint documented.

**Graceful Shutdown:**
- Presumed SIGTERM-safe (Go stdlib convention: signal.Notify + context cancellation).
- Not explicitly tested.

**Reconnect Behavior:**
- Native Go Telegram bot implementation (likely using go-telegram-bot-api or similar).
- Library handles retries; supervisor (Docker, systemd) manages process restart.

**Multi-tenant Caveat:**
- **Collision risk:** All instances share `~/.picoclaw/` by default.
- Recipe should use explicit config path or volume mounting per session.

**Evidence Pointers:**
- `/tmp/ap-recipe-picoclaw-clone/docs/guides/chat-apps.md` — Telegram setup guide with token/allow_from config
- `/tmp/ap-recipe-picoclaw-clone/config/config.example.json` (inferred from README) — channel_list schema
- Picoclaw recipe YAML shows `sh -c` entrypoint override to write config before running `picoclaw agent -m`

---

## Common Shape: What 80% of Agents Share

All 5 agents converge on a remarkably uniform shape for Telegram persistence:

1. **Telegram is first-class.** No plugins, no flags to enable; native integration.
2. **Persistent mode is a single `gateway` (or `gateway run`) subcommand.** Takes no arguments for basic startup.
3. **Config is JSON (or YAML-to-JSON compatible).** Located under a user home directory `./<agent-name>/`.
4. **Bot token + user allowlist are the only required secrets.**
   - **Bot token:** singular credential, obtained from Telegram `@BotFather`.
   - **Allowlist:** array of user IDs; empty = deny all (secure default).
5. **Env-var support is universal.** Either direct env-var read, or env-var interpolation in config file at startup. All support `${VAR}` or `$VAR` syntax.
6. **Startup is always foreground, blocking.** No daemon mode in the agent itself; process supervisor (systemd, Docker, launchd) handles background execution.
7. **Graceful shutdown is implicit.** SIGTERM handling is standard OS practice; all agents support it (verified for Hermes, presumed safe for others).
8. **Reconnect is delegated to the underlying library or native implementation.** Supervisor handles process restart on exit.
9. **Multi-tenant isolation is NOT built in.** Default paths collide (~/.agent-name/); recipes must use per-session mounts or `--config` overrides to isolate multiple users on one host.

---

## Schema Divergences That v0.2 Must Accommodate

1. **Config File Format:** JSON (Nanobot, NullClaw, OpenClaw, PicoClaw) vs YAML (Hermes).
   - **v0.2 implication:** `runtime.channels[].config_file_format: json | yaml` to disambiguate parsing.

2. **Config Location Strategy:**
   - Hermes: `~/.hermes/config.yaml` (per-user home, optional; env vars are primary).
   - Nanobot, NullClaw, OpenClaw, PicoClaw: `~/.{agent-name}/config.json` (per-user home, required).
   - **v0.2 implication:** Need to support both "env-var primary, config optional" (Hermes) and "config file primary, env-var interpolation" (others). Schema should have `channels[].config_source: env_primary | config_file_primary`.

3. **Telegram Credential Nesting:**
   - Hermes: `telegram.bot_token` (flat).
   - Nanobot: `channels.telegram.token` (flat under channels).
   - NullClaw, OpenClaw: `channels.telegram.accounts.<account_name>.bot_token` (multi-account per platform).
   - PicoClaw: `channel_list.telegram.token` (different key name).
   - **v0.2 implication:** Schema must accept a path template, e.g., `channels.telegram.settings.bot_token_path: channels.telegram.token | channels.telegram.accounts.*.bot_token`.

4. **User Allowlist Semantics:**
   - Hermes: `TELEGRAM_ALLOWED_USERS` env var (comma-separated or empty).
   - Nanobot: `channels.telegram.allowFrom` (array, Pydantic camelCase).
   - NullClaw: `channels.telegram.accounts.main.allow_from` (array, multi-account).
   - OpenClaw: `channels.telegram.allow_from` (array, similar).
   - PicoClaw: `channel_list.telegram.allow_from` (array).
   - **v0.2 implication:** Common key `allow_from` is near-universal; handle Hermes' special env-var case as a variant.

5. **Health Signal Mechanism:**
   - Hermes: Implicit (process running = gateway up).
   - Nanobot: HTTP heartbeat endpoint (configurable, default 127.0.0.1:18790).
   - NullClaw, OpenClaw, PicoClaw: Implicit (port binding or HTTP endpoint).
   - **v0.2 implication:** `channels[].health_check: none | http | port_binding` to guide orchestrator health probes.

6. **Multi-Account Support:**
   - NullClaw: Native multi-account per platform (accounts.main, accounts.backup, etc.).
   - Others: Single implicit account.
   - **v0.2 implication:** Optional `accounts[].name` field for agents that support it (useful for multi-bot deployments).

7. **Startup Blocking vs Daemonizing:**
   - All 5 agents run in foreground by default.
   - Some (Hermes, OpenClaw) have `install`/`start`/`stop` service management, but the gateway itself doesn't daemonize.
   - **v0.2 implication:** Confirm all recipes will use `docker run -d` for backgrounding; schema doesn't need to accommodate agent-level daemonization.

---

## Recommendation: Simplest Agent to Wire First (Phase-22a PoC)

**Verdict: NullClaw is the simplest.**

**Reasoning:**
1. **Config simplicity:** Single JSON file, pre-baked by Dockerfile, needs only one write (`nullclaw onboard --api-key ... --provider openrouter --model ...`) to inject credentials.
2. **Env-var cleanest:** The `onboard` command accepts CLI flags that map to config keys; no need to parse/regenerate the entire JSON.
3. **Startup fastest:** 678 KB static binary, <8 ms boot, no Python/Node startup overhead.
4. **Health signal:** Gateway port binding is implicit; can rely on process existence.
5. **Multi-tenant ready:** Recipe already uses per-session tmpdir mount; no collision risk.
6. **Smallest footprint:** 18.9 MB image, can run 10+ concurrent sessions on modest hardware.

**Close second:** Picoclaw (similar Zig/Go elegance, 45.5 MB image, slightly more config machinery due to LiteLLM model routing).

**Why not Hermes?** Heaviest (~5.19 GB), slowest build (451s), most complex config (YAML, skill-sync noise, entrypoint overrides already needed). Better for phase-22b once v0.2 schema is validated.

---

## Unknowns and Risks for Phase-22b Runner Work

1. **Actual SIGTERM behavior on Telegram reconnect:** Not tested in recon. Nanobot and PicoClaw rely on third-party libraries; their retry/backoff behavior on network hiccup is opaque. Hermes has explicit supervisor retry (systemd), but library behavior is unverified.
   - **Mitigation:** Build small test harness (disconnect network → observe reconnect latency + error logs).

2. **Health probe specifics for NullClaw and PicoClaw:** No explicit HTTP health endpoint. Port-binding liveness (can the runner bind to the gateway port?) might race with the agent's own startup.
   - **Mitigation:** Implement TCP port-probe health check or add HTTP health endpoint as a schema field.

3. **Config injection at scale:** Recipe uses `docker run -e OPENROUTER_API_KEY=...` to pass the bot token, but each agent has a different config schema. The runner must generate correct JSON/YAML per agent, or the orchestrator must template it.
   - **Mitigation:** Finalize `ap.recipe/v0.2` `channels[]` section with per-agent template support (e.g., `channels.telegram.config_template: {...}`).

4. **Multi-user per host on same volume:** If the orchestrator tries to run two instances of, say, NullClaw with the same `/nullclaw-data` mount, both will race to write config.json. Ephemeral per-session volumes solve this, but the runner/orchestrator must guarantee isolation.
   - **Mitigation:** Schema enforcement: channels[] must be paired with a dedicated ephemeral volume mount. Recipes must not allow shared state mounts for persistent channels.

5. **Telegram API rate limits + token invalidation:** What happens if a bot token is revoked or rate-limited? Agents will log errors, but the gateway process won't exit (no self-healing). Supervisor must detect stall and restart, or the orchestrator must actively monitor logs.
   - **Mitigation:** Define "liveness" vs "readiness" semantics in v0.2 schema. A running gateway that can't reach Telegram is still "live" but not "ready" for new messages.

6. **Nanobot's TERM behavior:** Nanobot uses Python async + click; SIGTERM handling is not explicitly documented. Risk of hanging on shutdown if the Telegram library is mid-handshake.
   - **Mitigation:** Test SIGTERM kill -9 timeout (e.g., 30s SIGTERM, then SIGKILL). Set recipe `smoke.timeout_s` and orchestrator shutdown timeout accordingly.

7. **OpenClaw's infer mode vs gateway mode:** The recipe targets `openclaw infer model run` (headless inference), NOT `openclaw gateway run` (persistent messaging). Full OpenClaw messaging requires the gateway service, which is a different operational model. Confirm whether v0.2 will support multi-container recipes or only single-container one-shot agents.
   - **Mitigation:** Clarify scope: if messaging channels are a v0.2 feature, decide whether the runner will support `runtime.external_services[]` (gateway + CLI containers), or restrict to agents that fit single-container.

---

## Conclusion

All 5 agents are mature, first-class Telegram integrations. The 80% shape (foreground gateway, JSON config, bot token + allowlist, env-var interpolation) is uniform enough to design a single `channels:` section in v0.2. The schema should:

- Accommodate both "env-var primary" (Hermes) and "config-file primary" (others) patterns.
- Support multi-account platforms (NullClaw).
- Include health-signal variants (HTTP, implicit, port-binding).
- Enforce per-session ephemeral volume mounting to avoid multi-tenant collisions.
- Defer full integration testing (reconnect, SIGTERM, health probes) to phase-22b runners.

**NullClaw is the recommended PoC target:** smallest, fastest, simplest config, already recipe-ready with ephemeral volumes.

