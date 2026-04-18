# Channel Recon — empirical per-agent (Phase 22 pre-work)

> **Supersedes**: `CHANNEL-RECON.md` (doc-research by Explore agent, 2026-04-17).
> **Method**: bespoke per-agent study — read each upstream's docs/source in main context, probe each image's CLI directly, then run each agent with the real test bot (`@AgentPlayground_bot`) and observe actual Telegram round-trip. Only battle-proven agents enter v0.2 schema.
> **Test creds**: `.env.local` (gitignored) — OpenRouter key, bot token `8710255942:AAE...` for `AgentPlayground_bot`, user chat_id `152099202`.
> **Running order** (sequential — shared bot, long-poll collides): nullclaw → hermes → nanobot → openclaw → picoclaw.

---

## Per-agent findings

### 1. nullclaw — DOCS ✅

**Config path inside container**: `/nullclaw-data/config.json` (env `NULLCLAW_HOME=/nullclaw-data`, `HOME` also set to same).

**Telegram schema** (verified in upstream `README.md`):

```json
{
  "channels": {
    "telegram": {
      "accounts": {
        "main": {
          "bot_token": "...",
          "allow_from": ["felipecavalcantirj"],
          "reply_in_private": true
        }
      }
    }
  }
}
```

- `allow_from`: access allowlist. Empty = deny all. `"*"` = allow all. Expects Telegram **usernames** (per README example `["user1"]`). Whether it accepts numeric chat_ids needs verification during empirical run.
- `reply_in_private`: bool.
- Multi-account supported natively: `accounts.<name>.{...}`. Use `main` for v0.2 single-account.

**Env-var support for bot_token**: **NO** per README. Must be in file.

**Persistent-mode command**:

- Option A: `nullclaw gateway` — runs all configured channels + HTTP/WS on default port 3000. Already image's default `CMD`.
- Option B: `nullclaw channel start telegram` — starts only the telegram listener. Simpler, no port exposure, better for our use case.

**Baked base config** (verified via `docker run --rm --entrypoint /bin/sh ap-recipe-nullclaw:latest -c 'cat /nullclaw-data/config.json'`):

```json
{
  "agents": {"defaults": {"model": {"primary": "openrouter/anthropic/claude-sonnet-4"}}},
  "models": {"providers": {"openrouter": {}}},
  "gateway": {"port": 3000, "host": "::", "allow_public_bind": true}
}
```

OpenRouter already first-class. We append `channels.telegram.accounts.main` on top, and continue using the existing `nullclaw onboard --api-key ... --provider openrouter` to inject the OpenRouter key (same flow as the one-shot recipe).

**Lifecycle**: foreground blocking. Safe for `docker run -d`. Non-root user uid=65534.

**Health signal**: HTTP on port 3000 (if `gateway` used). Unclear if `channel start telegram` alone exposes anything — needs empirical check.

**Multi-tenant**: all paths under `$HOME = /nullclaw-data` (baked default). Per-container is isolated as long as we don't share-mount that volume across containers. Per-user containers fine.

**Reconnect / SIGTERM**: needs empirical check.

**Evidence pointers**:
- `https://github.com/nullclaw/nullclaw` README (fetched 2026-04-17) — Telegram section with schema example
- `docker run --rm ap-recipe-nullclaw:latest --help` — full command surface
- `docker run --rm ap-recipe-nullclaw:latest channel list` — shows 24 channel slots total, Telegram is slot 2
- `docker run --rm ap-recipe-nullclaw:latest channel start` (no config) — error message reveals exact schema expectation

**Open questions for empirical**:
- Does `allow_from` accept numeric chat_id or only `@username`?
- Does `channel start telegram` exit 0 if config missing or foreground-block?
- Bot reply routing: does the agent reply to the sender's chat, or to a configured "reply_chat_id"?

---

### 2. hermes — DOCS ✅

**Env-var-driven** (cleanest path — no JSON templating needed):

- `TELEGRAM_BOT_TOKEN` — bot token from BotFather.
- `TELEGRAM_ALLOWED_USERS` — comma-separated **numeric** user IDs (e.g. `152099202`). Numeric IDs confirmed by example `123456789,987654321`.
- `TELEGRAM_HOME_CHANNEL` — optional, for scheduled-task output destination.

**Env file location**: `~/.hermes/.env` (read at `hermes gateway` startup). In the image, `HOME=/root` + `HERMES_HOME=/opt/data`, so the file goes in `/root/.hermes/.env`. **Note**: the Dockerfile drops root and runs as an unprivileged user (per one-shot recipe recon), so `~` resolves to that user's home — needs empirical check for exact path.

**Optional YAML** (`~/.hermes/config.yaml`) — only if using advanced features like `fallback_ips` or `dm_topics` (DM topic routing). For v0.2 MVP, skip the YAML.

**Persistent-mode command**: `hermes gateway` (foreground). Non-interactive when env vars are set — the `hermes gateway setup` wizard is skipped entirely.

**Response routing**: **dynamic per-message origin**. Bot replies in same chat the sender messaged from. No fixed reply_chat_id. Exactly what we want for multi-user-friendly bot behavior.

**DM pairing**: exists as alternative to allowlist — user DMs the bot a pairing code. When `TELEGRAM_ALLOWED_USERS` is set, that allowlist is enforced and DM pairing is an alternative path, not required.

**Image facts**:
- Binary: `/opt/hermes/hermes` (+ `/opt/hermes/.venv/bin/hermes`)
- `HOME=/root`, `HERMES_HOME=/opt/data`
- `PLAYWRIGHT_BROWSERS_PATH=/opt/hermes/.playwright` (5GB image — loaded)

**Evidence pointers**:
- `https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram` — fetched 2026-04-17
- `https://hermes-agent.nousresearch.com/docs/user-guide/messaging` — env var naming confirmation
- `docker run --rm --entrypoint /bin/sh ap-recipe-hermes:latest -c 'env'` — confirms HERMES_HOME baked

**Open questions for empirical**:
- Exact path of `.env` when run as non-root user (probably `/home/hermesuser/.hermes/.env` but Dockerfile inspection needed).
- Does `hermes gateway` exit on missing env or block waiting?
- Does the 30-turn `--max-turns` flag apply here, or is gateway mode unbounded turns?
- Does gateway mode honor `--model` flag, or must model come from `hermes config set`?

---

### 3. nanobot — DOCS ✅

**Config path**: `~/.nanobot/config.json` = `/home/nanobot/.nanobot/config.json` (image runs as user `nanobot`, `HOME=/home/nanobot`). **Not pre-baked** — dir exists empty, recipe must generate.

**Telegram schema**:

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "...",
      "allowFrom": ["152099202"]
    }
  }
}
```

- Field naming: `token` (NOT `bot_token`), `allowFrom` (camelCase, NOT snake_case). Inconsistent with nullclaw/picoclaw.
- `${TELEGRAM_TOKEN}` **env-var interpolation supported inline** in the JSON file — agent substitutes at read time. Useful: we can write the template once with `${TOKEN}`, set the env var at container start, agent reads it. No heredoc per-run needed.
- `allowFrom` — README says "Copy this value **without the @ symbol**" — suggests Telegram username. Whether numeric IDs also work: empirical.

**Persistent-mode command**: `nanobot gateway` (foreground). Accepts `-c/--config path` for alternate config path — useful for multi-tenant per-user file locations.

**Subcommands surface**: `nanobot channels` has only `status` + `login` (not helpful for config). Must write JSON directly.

**Image facts**:
- `HOME=/home/nanobot`
- binary on PATH

**Evidence**:
- `https://github.com/HKUDS/nanobot` README — schema confirmed
- `docker run --rm --entrypoint /bin/sh ap-recipe-nanobot:latest -c 'nanobot --help'` — subcommand surface

**Open questions for empirical**:
- Does `allowFrom` accept numeric user IDs alongside usernames?
- Does the `${VAR}` interpolation actually work in v0.1.5?
- Where does the ANSI-streaming output go when invoked as gateway (the prior one-shot recon showed Rich cursor codes spraying stdout — may need `--no-color` or `--quiet`)?

---

### 4. openclaw — DOCS ✅

**Config path**: `~/.openclaw/openclaw.json5` (JSON5 — supports comments & trailing commas).  In the image `HOME=/home/node`, so `/home/node/.openclaw/openclaw.json5`.

**Telegram schema** (JSON5, camelCase):

```json5
{
  channels: {
    telegram: {
      enabled: true,
      botToken: "...",
      dmPolicy: "allowlist",            // pairing | allowlist | open | disabled
      allowFrom: ["152099202"],         // numeric Telegram user IDs
      groups: { "*": { requireMention: true } }
    }
  }
}
```

**Non-interactive CLI**: `openclaw channels add --channel telegram --token <token>` — writes to config.json5 directly. Eliminates heredoc JSON5 templating if preferred.

**Env var fallback**: `TELEGRAM_BOT_TOKEN=...` — **only for the default account when no explicit config token exists**. Not primary.

**dmPolicy options**:
| Value | Behavior |
|---|---|
| `pairing` | Default. User DMs pairing code. |
| `allowlist` | Numeric IDs in `allowFrom` required. Empty list rejects. |
| `open` | `allowFrom: ["*"]` required. Allows any user. |
| `disabled` | Blocks all DMs. |

**Persistent-mode command**: `openclaw gateway` (foreground). Long polling by default.

**Image facts**:
- `HOME=/home/node` — Node.js image
- Multiple subcommand surface (acp, agents, approvals, capability, channels, cron, daemon, etc.)

**Evidence**:
- `https://docs.openclaw.ai/channels/telegram` — schema confirmed
- `docker run --rm --entrypoint /bin/sh ap-recipe-openclaw:latest -c 'openclaw channels --help'` — CLI surface confirmed

**Open questions for empirical**:
- Does `channels add --channel telegram --token` persist `dmPolicy: allowlist` or default to `pairing`?
- Does `openclaw gateway` honor the recipe's existing `infer` CLI flow, or are they mutually exclusive modes?
- Node runtime — does `node_modules` persist across container restarts or need a volume?

---

### 5. picoclaw — DOCS ✅

**Config path**: `~/.picoclaw/config.json` — in image `HOME=/root`, so `/root/.picoclaw/config.json`.

**Telegram schema** (simplest of all):

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "...",
      "chat_id": "152099202"
    }
  }
}
```

- Fields: `token` (like nanobot), `chat_id` (**single** — not an array). Most restrictive shape: the bot answers **only** the one configured chat_id. Good for platform-deploy (each user → one bot → one chat).
- Secrets split: `api_key` lives in a separate `.security.yml` file per project convention.

**Persistent-mode command**: `picoclaw gateway` (foreground). Long polling.

**Image facts**:
- `HOME=/root`
- Alpine-based, ~45MB (smallest of the 5)

**Evidence**:
- `https://github.com/sipeed/picoclaw` README — confirmed

**Open questions for empirical**:
- Does `chat_id` need to be a string (as shown) or can it be a number? README example shows string.
- Does picoclaw support multiple chat_ids (array), or is it strictly one?
- Does `.security.yml` have a sibling `.channels.yml` for bot token, or does the bot token stay in `config.json`?

---

## Schema divergences (post-recon)

### Divergence 1 — Config transport (3 distinct patterns)

| Pattern | Agents | How runner writes creds |
|---|---|---|
| **env-only** | hermes | Write `.env` file with `KEY=VALUE` lines inside container; runner passes `-e TELEGRAM_BOT_TOKEN=...` on `docker run -d` |
| **file-only** | nullclaw, picoclaw | Heredoc-sh-chain the full config.json at container start before `gateway` invokes |
| **file-with-env-interpolation** | nanobot (native `${VAR}`), openclaw (CLI write + env fallback) | Write templated config once; set env vars at `docker run -d` time |

### Divergence 2 — Telegram schema nesting + field vocabulary

| Agent | Path to bot_token | Path to allowlist | Value type |
|---|---|---|---|
| nullclaw | `channels.telegram.accounts.main.bot_token` | `channels.telegram.accounts.main.allow_from[]` | **username** (per README) |
| hermes | env `TELEGRAM_BOT_TOKEN` | env `TELEGRAM_ALLOWED_USERS` (csv) | **numeric user IDs** |
| nanobot | `channels.telegram.token` | `channels.telegram.allowFrom[]` | **username** (per README "without @") |
| openclaw | `channels.telegram.botToken` | `channels.telegram.allowFrom[]` | **numeric user IDs** |
| picoclaw | `channels.telegram.token` | `channels.telegram.chat_id` (single) | **numeric chat_id** (string) |

**Naming chaos:** `bot_token` vs `token` vs `botToken`; `allow_from` vs `allowFrom`; `allowlist array` vs `single chat_id`.

**Implication for v0.2 schema:** recipe declares the TEMPLATE (own vocabulary), runner only materializes `$bot_token` + `$allow_id` into it. Schema does NOT try to unify field names.

### Divergence 3 — Allowlist value type

- nullclaw / nanobot accept usernames (per README) — requires user to supply `@handle` (no @).
- hermes / openclaw / picoclaw accept numeric IDs — user supplies chat_id from `@userinfobot`.

**Implication:** UI `Step 2.5` must have **both** fields or accept either, and the recipe must declare which kind it wants. v0.2 schema: `required_user_context.allow_id.kind: telegram_username | telegram_numeric_id`.

### Divergence 4 — Pre-baked vs empty home dir

- nullclaw: config.json **pre-baked** with OpenRouter section. Runner appends `channels.telegram` to existing file.
- others: empty home dir. Runner generates full config.

**Implication:** schema `config_strategy: append | replace`.

### Divergence 5 — Health signal

- hermes, nullclaw (when `gateway` mode): HTTP port 3000 / process_alive.
- nanobot: HTTP heartbeat claimed on 127.0.0.1:18790 (unverified).
- openclaw: `/health` endpoint claimed (unverified).
- picoclaw: unclear; likely process_alive only.

**Implication:** schema `health_check.kind: process_alive | http` with optional `port` + `path`.

---

## Which agent to ship first (Phase 22a PoC)

**Recommendation: hermes** (changed from original "nullclaw" recommendation).

**Why hermes wins:**
1. **Env-var-only** config transport = NO templating complexity, NO config.json generation per-user, NO heredoc-sh-chain. Runner just does `docker run -d -e TELEGRAM_BOT_TOKEN=... -e TELEGRAM_ALLOWED_USERS=152099202 ap-recipe-hermes:latest hermes gateway`.
2. **Numeric user IDs** accepted (matches what `@userinfobot` gives) — one less UI field to disambiguate.
3. **Response routing is dynamic** (sender's chat) — no extra reply_chat_id config needed.
4. Recipe already validated with 2 models (haiku-4.5, gpt-4o-mini) in one-shot mode — image is known-good.
5. `hermes gateway` is the documented entrypoint for non-interactive persistent mode.

**Why NOT nullclaw as first:**
- Multi-account nesting (`accounts.main.bot_token`) requires deeper JSON structure
- Config file templating needed (not env-var supported)
- `allow_from` takes USERNAMES per docs — collision with our `@userinfobot`-supplied numeric IDs

**Phase 22a scope re-confirmed**: ship hermes Telegram end-to-end, schema v0.2 MINIMAL (only what hermes needs), runner `--mode persistent` for env-var agents first. Phase 22b extends schema with `config_file.template` for file-based agents (nullclaw, picoclaw, openclaw, nanobot) and rolls out.

---

## Empirical probe results

_To be populated — sequential runs starting with hermes, using `@AgentPlayground_bot` from `.env.local`._

## Verdict matrix

| Agent | Docs | Empirical run | Verdict |
|---|---|---|---|
| hermes | ✅ | ✅ 2026-04-17 22:06 | **CHANNEL_PASS** |
| picoclaw | shallow | pending | — |
| nullclaw | shallow | pending | — |
| nanobot | shallow | pending | — |
| openclaw | shallow | pending | — |

## Empirical probe — hermes (2026-04-17 22:06)

**Setup**: `docker run -d --name ap-ch-test-hermes -e OPENROUTER_API_KEY=... -e TELEGRAM_BOT_TOKEN=... -e TELEGRAM_ALLOWED_USERS=152099202 ap-recipe-hermes:latest gateway run -v`

**Gateway boot sequence observed**:
```
INFO gateway.run: Starting Hermes Gateway...
INFO gateway.run: Session storage: /opt/data/sessions
INFO gateway.run: Connecting to telegram...
INFO gateway.platforms.telegram_network: DoH discovery yielded no new IPs ... using seed fallback IPs 149.154.167.220
INFO telegram.ext.Application: Application started
INFO gateway.platforms.telegram: [Telegram] Telegram menu: 100 commands registered, 9 hidden
INFO gateway.platforms.telegram: [Telegram] Connected to Telegram (polling mode)
INFO gateway.run: ✓ telegram connected
INFO gateway.run: 1 hook(s) loaded
INFO gateway.run: Gateway running with 1 platform(s)
INFO gateway.run: Channel directory built: 0 target(s)
INFO gateway.run: Cron ticker started (interval=60s)
```

**Round-trip evidence** (from user's `@fcavalcantirj` account, Telegram client, @AgentPlayground_bot):

```
Felipe [22:06:44]: /start
AgentPlayground [22:06:45]: Unknown command /start. Type /commands to see what's available, or resend without the leading slash to send as a regular message.

Felipe [22:06:48]: oi
AgentPlayground [22:06:49]: 📬 No home channel is set for Telegram. A home channel is where Hermes delivers cron job results and cross-platform messages.
Type /sethome to make this chat your home channel, or ignore to skip.

Oi Felipe! Sou o Hermes, seu assistente pessoal. Posso te ajudar com tarefas de programação, pesquisa, automação, e muito mais. Manda /help pra ver os comandos disponíveis. Como posso te ajudar?
```

**Monitor events** (filtered from `docker logs -f`):
- `WARNING gateway.run: Unrecognized slash command /start from telegram — replying with unknown-command notice`
- `INFO gateway.platforms.base: [Telegram] Sending response (131 chars) to 152099202`  (/start reply)
- `INFO agent.auxiliary_client: Auxiliary auto-detect: using openrouter (google/gemini-3-flash-preview)`  (LLM probe)
- `INFO gateway.platforms.base: [Telegram] Sending response (194 chars) to 152099202`  (LLM reply)

**Verdict**: **CHANNEL_PASS**. All 3 assertions green:
1. Bot receives inbound msg from allowlisted user → yes (allowlist works for numeric IDs).
2. Gateway calls LLM via configured provider → yes (auto-selected `google/gemini-3-flash-preview` via OpenRouter auxiliary client; recipe's baked OPENROUTER_API_KEY injection inherited cleanly in persistent mode).
3. Bot replies to sender's chat within reasonable time → yes (~1s turnaround /start reply; LLM reply ~1s for a short prompt).

**Side observations**:
- Hermes also suggested `/sethome` for the user's chat — this is where cron/proactive messages will route. Out of scope for MVP; document as a follow-up.
- Auxiliary client auto-selected `gemini-3-flash-preview` despite the recipe's verified_cells listing only `claude-haiku-4.5` and `gpt-4o-mini`. Hermes has its own provider auto-detection; user-chosen model from the recipe one-shot does NOT automatically carry over into gateway mode. For MVP this is acceptable. For production, we'll want `hermes config set model <user-picked>` before `gateway` to honor the user's model choice.
- Container exit=0 + SIGTERM took 5s graceful — good for `-d` lifecycle.
- No webhook needed (long polling) — zero public IP required.

**What the hermes recipe needs for v0.2** (just the delta from current recipe):
- New top-level block `channels:` → `telegram:` → transport: `env`, required env: `[TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS]`, optional env: `[TELEGRAM_HOME_CHANNEL, TELEGRAM_HOME_CHANNEL_NAME]`.
- Persistent mode argv override: `gateway run -v` (instead of `chat -q "$PROMPT" -Q --provider openrouter -m $MODEL --yolo --max-turns 30 --source tool --verbose`).
- New `lifecycle: persistent` flag at channel level.
- Recommended: pre-command `hermes config set model $MODEL` in sh-chain so user's model choice survives to gateway mode.

---

## Deep-docs — picoclaw (in progress)

_Per methodology: exhaustive official-source research before any recipe edit or empirical run._

**Sources to review**:
- [ ] Upstream README (shallow-fetched earlier)
- [ ] `docs/` folder in repo (if any)
- [ ] Example configs in `examples/` / `configs/`
- [ ] Source code for Telegram handler / config parsing
- [ ] Docker entrypoint / default CMD behavior for `gateway` subcommand

_To be populated._
