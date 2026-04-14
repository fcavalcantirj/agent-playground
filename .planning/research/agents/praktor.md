---
name: praktor
real: true
source: https://github.com/mtzanidakis/praktor
language: Go
license: MIT
stars: 23
last_commit: 2026-04-11
---

# Praktor

## L1 — Paper Recon

**Install mechanism:** docker compose (builds agent image locally, runs Go binary via compose)

**Install command:**
```
docker compose up -d
```

**Supported providers:** Anthropic (primary — `claude-sonnet-4-6`, `claude-opus-4-6`), also supports OAuth via `CLAUDE_CODE_OAUTH_TOKEN`. Hardcoded around Claude Code as the inner runtime.

**Model-selection mechanism:** YAML `model:` key, per-agent with `defaults.model` fallback.

**Auth mechanism (best guess from docs):** **AES-256-GCM encrypted vault** keyed by `PRAKTOR_VAULT_PASSPHRASE`. Secrets referenced in YAML as `"secret:<key-name>"` and injected as env vars or files at container startup. Raw env var substitution via `"${VAR_NAME}"` also supported. Maps to **`env_var_substitution_in_config` + a new `encrypted_vault_ref` mechanism** not yet in our matrix.

**Chat I/O shape:** Telegram I/O to a router; inner agent runs as Claude Code inside per-agent Docker container. Equivalent to our `fifo` mode — stdin/stdout piped via the orchestrator. Praktor adds a Mission Control web UI over WebSocket with embedded NATS broker for inter-agent messaging.

**Persistent state needs:** Per-agent **named workspace** (`workspace: coder`), files/secrets mounted at container-specified target paths with mode bits, idle timeout defaults to 10m, `max_running: 5`.

**Notes from README (anything unusual for sandboxing):**
- **Direct prior art for our recipe manifest** — Go single-binary orchestrator, YAML-declared agents, per-agent Docker isolation, encrypted vault for secrets. The same architectural shape we're building, minus Telegram lock-in and with multi-model support.
- **Embedded NATS broker** for inter-agent messaging (graph-based swarms: fan-out, pipeline, collaborative). Runs in-process — no external NATS server needed.
- **Nix-enabled agents** via `nix_enabled: true` for on-demand tool installation inside the workspace container — different isolation tier than base image.
- **`allowed_tools`** list gates which Claude Code tools an agent can use (`[WebSearch, WebFetch, Read, Write]`) — tool-level capability model we don't have.
- Hot config reload — YAML edits apply without restart.
- Hardcoded to Claude Code as inner runtime; multi-model claim is actually "choose a Claude model", not "choose any provider".
- Stars (23) are low, but recency (April 2026) and architectural fit make this the single most valuable reference in the sweep.

## Prior-art schema keys

From `config/praktor.example.yaml` — verbatim top-level and per-agent keys we must consider when designing the recipe manifest:

```yaml
telegram:
  token: "${PRAKTOR_TELEGRAM_TOKEN}"
  allow_from: []
  main_chat_id: 0

defaults:
  image: "praktor-agent:latest"
  model: "claude-sonnet-4-6"
  max_running: 5
  idle_timeout: 10m
  anthropic_api_key: "${ANTHROPIC_API_KEY}"
  oauth_token: "${CLAUDE_CODE_OAUTH_TOKEN}"

agents:
  general:
    description: "General-purpose assistant for everyday tasks"
    workspace: general
  coder:
    description: "Software engineering specialist"
    model: "claude-opus-4-6"
    workspace: coder
    nix_enabled: true
    env:
      EDITOR: vim
      GITHUB_TOKEN: "secret:github-token"
    files:
      - secret: gcp-service-account
        target: /etc/gcp/sa.json
        mode: "0600"
  researcher:
    description: "Web research and analysis"
    workspace: researcher
    allowed_tools: [WebSearch, WebFetch, Read, Write]

router:
  default_agent: general

web:
  enabled: true
  port: 8080
  auth: "${PRAKTOR_WEB_PASSWORD}"

vault:
  passphrase: "${PRAKTOR_VAULT_PASSPHRASE}"

scheduler:
  poll_interval: 30s
```

**Keys to steal / consider for our schema:**

| Praktor key | Purpose | Our schema mapping |
|---|---|---|
| `defaults.image` | Base Docker image for the agent | Already in our `install.type: docker` shape |
| `defaults.max_running` | Concurrency cap | **NEW** — add to `resource_overrides` |
| `defaults.idle_timeout` | Auto-reap | Already in session state model |
| `agents.<name>.workspace` | Named volume / fs scope | Maps to our `persistent_state.named_volume` |
| `agents.<name>.nix_enabled` | On-demand tool install | **NEW dimension** — runtime extension tier |
| `agents.<name>.env` | Env vars with `secret:` refs | **NEW** — first-class `secret:` prefix syntax beats `${VAR}` substitution |
| `agents.<name>.files` | Secret-backed file mounts | **NEW** — `{secret, target, mode}` triple. Neither `config_file` nor `env_var` in our matrix covers this cleanly. **We should add `secret_file_mount` auth mechanism.** |
| `agents.<name>.allowed_tools` | Tool-level capability gate | **NEW dimension** — not in our schema at all |
| `vault.passphrase` | Master key for AES-256-GCM vault | Maps to our per-user KEK plan; Praktor uses passphrase-based rather than derived |
| `router.default_agent` | Message routing | Not applicable — we don't route, user picks |

**Critical takeaway:** the `files:` key (list of `{secret, target, mode}` mounts) is the cleanest answer to our hermes / picoclaw / moltis `.security.yml` templating pain. **Add `secret_file_mount` as a first-class auth mechanism in Phase 02.5.**

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
