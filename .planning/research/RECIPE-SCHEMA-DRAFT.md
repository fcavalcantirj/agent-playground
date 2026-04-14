---
status: draft
stage: pre-phase-02.5
last_updated: 2026-04-14
inputs:
  - .planning/research/AGENT-MATRIX.md    # 40-agent sweep findings
  - .planning/research/SCHEMA-PRIOR-ART.md # External 12-project schema comparison
  - .planning/research/agents/*.md         # Per-agent L1 findings
purpose: |
  Phase 02.5 recipe manifest schema draft. Merges 5 battle-tested prior-art
  contributions into one YAML format, validated by a JSON Schema, and proven
  via 10 worked reference recipes that span every chat_io mode × auth
  mechanism × runtime family × isolation tier in the matrix.

  **This is a DRAFT, not a commitment.** It becomes Phase 02.5's PLAN.md input
  after /gsd-insert-phase 02.5 and any iteration from the discuss step.
---

# Agent Playground Recipe Manifest — Schema Draft

## Provenance

Every field in this schema is borrowed from a prior art with a proven production track record. Nothing is invented. The 5 stitched sources:

| Recipe field | Prior art | Why it wins |
|---|---|---|
| `runtime.image / resources / volumes` | **Daytona `ImageParams`** (72.3k★, AGPL-3) | Cleanest OCI-opaque runtime declaration with explicit resource bounds |
| `lifecycle.{initialize, onCreate, updateContent, postCreate, postStart, postAttach}` | **Dev Containers spec** (CC-BY-4.0, formal JSON Schema) | 6 hooks with strict ordering + parallel execution support + `waitFor` readiness gating |
| `launch.cmd` / `chat_io.stdio` | **MCP `{command, args}`** (7.1k★, MIT) | De-facto standard for AI tool launch + JSON-RPC 2.0 stdio framing |
| `auth.env` / `auth.files` with `secret:<name>` refs | **Praktor** (MIT, April 2026 active) | AES-256-GCM vault + `secret:` syntax + `{secret, target, mode}` file mounts |
| `providers[]` / `models[]` | **Plandex `models-input.schema.json`** (MIT) | Most complete provider/model declaration in the wild; 12-role model pack shape |
| `frontend` metadata | **Coder `coder_app`** (AGPL-3) | Most mature catalog-facing metadata (display_name, icon, slug, tooltip, group, share) |
| `runtime_backend` enum | **OpenHands `runtime` enum** (MIT) | `docker | local | remote | kubernetes` — closest existing escape hatch for nested-container collision |
| `isolation.{capAdd, capDrop, securityOpt, init}` | **Dev Containers security properties** | Maps 1:1 to Docker flags; extensible with tier enum |

**Anti-patterns we're rejecting:** Coder's full Terraform dependency (over-scoped), OpenAgents ONM (solves a2a networking, not manifests), LangChain (no declarative manifest exists), Oracle Agent Spec Flow/Node graph (workflow engine, not description), Plandex alone (too narrow — only model roles, no sandbox concept), Memoh DB-stored configs (not version-controllable).

---

## Design constraints (non-negotiable)

These constraints flow from Agent Playground's core hypothesis: **"any agent × any model × any user, in one click"** PLUS **"deterministic recipes for known agents, Claude-Code bootstrap for unknown ones"** (CLAUDE.md). That second clause is what makes this a real marketplace — an LLM must be able to emit a valid recipe from just a README + the schema + a handful of few-shot examples.

| # | Constraint | Consequence |
|---|---|---|
| 1 | **Closed-vocabulary enums wherever possible** | LLM picks from a list, never invents. `isolation.tier`, `chat_io.mode`, `install.type`, `auth.mechanism`, `runtime.family`, `policy_flags` are all closed enums. |
| 2 | **≤6 required fields, defaults everywhere else** | Required: `id`, `name`, `runtime.family`, `install`, `launch.cmd`, `chat_io.mode`. ~30 other fields default to safe values if omitted. |
| 3 | **JSON Schema ships alongside the YAML** | `schemas/recipe.schema.json` (Draft 2019-09) validates manifests client-side AND server-side AND inside the bootstrap container. LLM can validate its own output before emitting. |
| 4 | **Hooks idempotent, declarative, re-runnable** | Dev Containers semantics: `postCreateCommand` must work on first install AND every subsequent session. No stateful "was this already installed" magic. |
| 5 | **10 reference recipes ship as few-shot examples** | The bootstrap agent's prompt context includes 10 real recipes spanning every chat_io mode + auth mechanism + runtime family. When the LLM sees 10 worked examples, it can extrapolate to new agents. This file carries all 10 inline. |
| 6 | **Per-recipe `isolation.tier` is mandatory, not optional** | Bootstrap-generated recipes default to Tier 3 (gvisor) until hand-reviewed. Trusted catalog recipes can be Tier 1. No implicit trust. |
| 7 | **Schema is LLM-writable** | Every schema decision is tested against "can Claude Sonnet write this correctly from just a README?" — we run a writability test before locking the schema. |

---

## Full schema spec (YAML + inline comments)

```yaml
# ============================================================================
# Agent Playground recipe.yaml — schema v0.1.0 (Phase 02.5 draft)
# ============================================================================
# This file declares how to install, launch, and talk to a single coding
# agent inside Agent Playground's sandboxed container runtime. It is the
# contract between the Go orchestrator (session.Handler) and the agent
# binary inside the container.
#
# Validation: against schemas/recipe.schema.json (Draft 2019-09).
# Authoring:  YAML (this file) or JSON (direct).
# ============================================================================

# ---- IDENTITY (required) ---------------------------------------------------

id: <slug>                    # e.g. "picoclaw", "aider". URL-safe, unique.
name: <display name>          # e.g. "PicoClaw". Shown in the frontend card.
description: <one-liner>      # Shown in the frontend card subtitle.
version: <semver>             # e.g. "0.1.0". Frontend shows it as a badge.

# ---- LICENSE + CATEGORIZATION (required) ----------------------------------

license: <SPDX>               # e.g. "MIT", "Apache-2.0", "AGPL-3.0", "proprietary"
                              # Users filter catalog by `license: OSS-only`.
category: <enum>              # claw | chat | scaffold | one-shot | multi-agent
                              #   | narrow-domain | library | framework-only

# ---- RUNTIME FAMILY (required, drives base image selection) ---------------

runtime:
  family: <enum>              # node | python | rust | go | zig
                              # Maps to ap-runtime-<family> base image.
  version: <string, optional> # e.g. "22" for node, "3.13" for python.
                              # Default: whatever the base image ships.
  resources:                  # From Daytona ImageParams
    memory_mib: 1024          # Default: 1024
    cpus: 1.0                 # Default: 1.0
    pids_limit: 256           # Default: 256
    disk_mib: 2048            # Default: 2048
  volumes:                    # Persistent named volumes across sessions.
    - name: workspace         # Resolved to /home/agent/<name>
      mount: /home/agent/workspace
      size_mib: 1024

# ---- CONFIG FLAVOR (optional — for agents that reuse another agent's runtime) -

config_flavor_of: <id>        # e.g. picoclaw.config_flavor_of: openclaw
                              # Means: install the parent agent, then apply
                              # this recipe's overlay (env + files only).

# ---- INSTALL (required — Dev Containers lifecycle hooks) ------------------

# Hook ordering (Dev Containers spec):
#   1. initializeCommand — runs on HOST before container start. Rare.
#   2. onCreateCommand   — runs once on container create (fresh).
#   3. updateContentCommand — runs on every session start (pull updates).
#   4. postCreateCommand — runs after create. Installs go here.
#   5. postStartCommand  — runs on every start (daemonize agents here).
#   6. postAttachCommand — runs when bridge attaches. Bridge setup here.
#
# All hooks must be IDEMPOTENT. The same hook may run multiple times.

install:
  type: <enum>                # pip | npm | cargo | binary | docker | docker_compose | git_build
  # Type-specific fields:
  package: <string>           # pip/npm/cargo package name
  version: <string, optional> # semver constraint
  extras: [<list>]            # pip extras; default [] (forbidden for hermes's [all])
  # For type=binary:
  url: <string>               # Download URL
  sha256: <string>            # Pinned hash for reproducibility
  # For type=git_build:
  git:
    repo: <string>
    rev: <sha>                # MUST be a commit SHA, never a tag/branch
    build_cmd: [<argv>]
  # For type=docker / docker_compose:
  image: <string>             # For type=docker only
  compose_file: <path>        # For type=docker_compose only

lifecycle:
  initializeCommand: null               # Rare — GPU probe, etc.
  onCreateCommand: null                 # One-time container setup
  updateContentCommand: null            # Per-session pull
  postCreateCommand: <cmd | [parallel]> # Install hook. Most recipes use this.
  postStartCommand: null                # Per-session start
  postAttachCommand: null               # Per-session bridge attach
  waitFor: postCreateCommand            # Which hook blocks readiness

# ---- LAUNCH (required — how the agent process starts) --------------------

launch:
  cmd: [<argv>]               # Default argv for fifo/REPL modes
                              # e.g. ["picoclaw", "agent", "--session", "cli:default"]
  workdir: /home/agent        # $PWD inside container
  wrapper_script: null        # For library-first agents (qwen-agent) — path to
                              # a shim script the recipe ships as a file mount

# ---- CHAT I/O (required — how messages flow between user and agent) ------

chat_io:
  mode: <enum>                # fifo | exec_per_message | one_shot_task
                              #  | http_gateway | json_rpc_stdio
                              #  | terminal_only | grpc_uds
  response_timeout_sec: 60    # Bridge timeout per message. Default: 60.

  # Mode-specific config (only the matching block is read):
  fifo:
    fifo_in:  /run/ap/chat.in
    fifo_out: /run/ap/chat.out
    strip_ansi: true          # Default: true. picoclaw/hermes need this.
    skip_prompt_markers: []   # e.g. ["\x01", "\u001b["] to skip before reply text

  exec_per_message:
    cmd_template: [<argv>]    # {text} placeholder is substituted
                              # e.g. ["hermes", "chat", "-q", "{text}"]
    docker_exec_user: agent   # Default: "agent"

  one_shot_task:
    input_schema:             # Typed form — frontend renders fields instead of chat
      - key: <string>
        type: <enum>          # string | url | enum | textarea
        required: true
        values: []            # For type=enum
    output_path: /tmp/result.json  # Agent writes final answer here
    output_format: json       # json | text | jsonl

  http_gateway:
    internal_port: 8787
    path_prefix: /v1
    healthcheck_path: /health

  json_rpc_stdio:
    framing: length-prefixed  # Content-Length header + JSON body
    protocol_version: "2.0"

  terminal_only:              # ttyd access only, POST /message returns 405
    {}

  grpc_uds:                   # Memoh-style — keys pulled over UDS at exec time
    socket_path: /run/ap/agent.sock
    service: AgentService

# ---- AUTH (required — secret injection) -----------------------------------

auth:
  mechanism: <enum>           # env_var | env_var_substitution_in_config
                              #  | secret_file_mount | cli_flag_on_onboard
                              #  | exec_time_only | gateway_token
                              #  | grpc_injected_at_runtime
                              #  | adc_service_account_json
                              #  | oauth_flow_with_keychain        (UNSUPPORTED v1)
                              #  | oauth_device_code               (UNSUPPORTED v1)
                              #  | interactive_wizard              (UNSUPPORTED v1)
  headless_safe: true         # MUST be true for v1 catalog. Frontend filters
                              # headless_safe:false from the default view.

  # Praktor-style env block — literal values OR "secret:<vault-key>" refs
  env:
    EDITOR: vim               # Literal value
    ANTHROPIC_API_KEY: "secret:anthropic-key"   # Vault ref
    GITHUB_TOKEN: "secret:github-token"
    # Dev Containers-style aliases for nonstandard env var names
    # (e.g. AutoCodeRover uses OPENAI_KEY not OPENAI_API_KEY)
    env_var_aliases:
      OPENAI_API_KEY: OPENAI_KEY

  # Praktor-style {secret, target, mode} file mounts
  files:
    - secret: picoclaw-security-yml       # Vault key
      target: /home/agent/.picoclaw/.security.yml
      mode: "0600"
      template: picoclaw_security_yml     # Named template for rendering
                                          # (templates live in Go code, keyed by name)

  # Schema-side secret metadata (Dev Containers secrets block)
  secrets_schema:
    - name: anthropic-key
      description: "Anthropic API key for direct BYOK"
      documentation_url: https://console.anthropic.com
      required: true
    - name: github-token
      description: "GitHub PAT for repo access"
      required: false

# ---- PROVIDERS + MODELS (required — Plandex shape) ------------------------

providers:                    # LLM providers this recipe can drive
  - id: anthropic             # From closed enum: anthropic | openai | openrouter
    api_base: https://api.anthropic.com/v1  #   | groq | bedrock | gemini | dashscope
    api_key_env_var: ANTHROPIC_API_KEY      #   | local | gateway
    auth_style: bearer        # bearer | x-api-key | custom
  - id: openrouter
    api_base: https://openrouter.ai/api/v1
    api_key_env_var: OPENROUTER_API_KEY
    auth_style: bearer

models:                       # Models this recipe supports (intersect with providers)
  - id: claude-sonnet-4-6
    provider: anthropic
    max_input_tokens: 200000
    max_output_tokens: 32000
    supports_images: true
  - id: claude-opus-4-6
    provider: anthropic
    max_input_tokens: 200000
    max_output_tokens: 32000

model_flag: --model           # How the agent accepts model override at launch
model_env_var: null           # Alternative: env var instead of flag

# ---- CAPABILITIES + POLICY (Phase 7.5 enforcement) ------------------------

allowed_tools: []             # Praktor-style tool capability gate (optional)
                              # e.g. [WebSearch, WebFetch, Read, Write]
                              # Enforced by: (a) agent itself if it honors,
                              # (b) egress proxy if tool makes net call,
                              # (c) bind-mount scope if tool touches files.

policy_flags: []              # Closed vocabulary — frontend shows as badges
                              #   non_oss            (proprietary license)
                              #   gateway_only       (can only use vendor gateway)
                              #   cloud_handoff      (has --cloud escape flag)
                              #   oauth_required     (unsupported in v1)
                              #   interactive_setup  (unsupported in v1)
                              #   nested_container   (requires sysbox tier+)

egress_allowlist:             # Firewall allowlist for outbound HTTP
  - api.anthropic.com
  - openrouter.ai

# ---- ISOLATION (required — selects sandbox runtime) -----------------------

isolation:
  tier: <enum>                # strict  — plain docker + cap-drop (Tier 1)
                              # standard — same as strict (default)
                              # sysbox  — nested-docker capable (Tier 2)
                              # compose — docker-compose multi-container (Tier 2)
                              # gvisor  — runsc (Tier 3, untrusted bootstrap)
                              # firecracker — microVM (Tier 4, abuse-prone)
  nested_container_collision: false  # True for hermes/moltis/nanoclaw/etc.

  # Dev Containers security properties
  cap_drop: [ALL]
  cap_add:                    # Init-only caps; dropped after entrypoint phase 1
    - CHOWN
    - SETUID
    - SETGID
    - SETPCAP
  no_new_privs: true
  read_only_rootfs: true
  security_opt:
    - seccomp=/etc/docker/seccomp-agent.json  # Phase 7.5 ships this

# ---- PERSISTENT STATE (session-survivable or ephemeral) -------------------

persistent_state:
  tmpfs:                      # Ephemeral per-session (Phase 2-2.5)
    - path: /tmp
      size_mib: 128
    - path: /run
      size_mib: 16
    - path: /home/agent/.picoclaw/workspace/sessions
      size_mib: 32
      uid: 10000
      gid: 10000

  named_volume: null          # Phase 7+ — survive across session restarts
                              # e.g. name: picoclaw-workspace
                              #      mount: /home/agent/.picoclaw/workspace
                              #      size_mib: 1024

  bind_mounts: []             # Host-side bind mounts (avoid unless necessary)

# ---- FRONTEND METADATA (Coder coder_app shape) ----------------------------

frontend:
  display_name: PicoClaw
  slug: picoclaw
  icon: hermes                # Lucide icon name
  category_badge: "Local Coder"
  group: claw                 # Grouping for the catalog grid
  tooltip: "PicoClaw — PicoCode lobster agent"
  share: public               # public | unlisted | private
  stars: 357000               # Auto-populated from GitHub
  tier_badge: tier-1          # Frontend shows isolation tier as a badge

# ---- METADATA (Oracle Agent Spec shape) -----------------------------------

metadata:
  source_repo: https://github.com/sipeed/picoclaw
  source_sha: c7461f9e963496c4471336642ac6a8d91a456978
  last_verified: 2026-04-14
  verified_by: claude-sonnet-4-6
  bootstrap_generated: false  # True if this recipe was LLM-generated
  community_pr: null          # PR URL if this was contributed via bootstrap
```

---

## JSON Schema outline

Full schema at `schemas/recipe.schema.json` (Draft 2019-09). Top-level structure:

```json
{
  "$schema": "https://json-schema.org/draft/2019-09/schema",
  "$id": "https://agent-playground.dev/schemas/recipe.schema.json",
  "title": "Agent Playground Recipe",
  "type": "object",
  "required": ["id", "name", "runtime", "install", "launch", "chat_io"],
  "properties": {
    "id": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
    "name": {"type": "string", "minLength": 1, "maxLength": 60},
    "description": {"type": "string", "maxLength": 240},
    "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+"},
    "license": {"type": "string"},
    "category": {"enum": ["claw", "chat", "scaffold", "one-shot", "multi-agent", "narrow-domain", "library", "framework-only"]},
    "runtime": {
      "type": "object",
      "required": ["family"],
      "properties": {
        "family": {"enum": ["node", "python", "rust", "go", "zig"]},
        "version": {"type": "string"},
        "resources": {"$ref": "#/$defs/resources"},
        "volumes": {"type": "array", "items": {"$ref": "#/$defs/volume"}}
      }
    },
    "install": {
      "oneOf": [
        {"$ref": "#/$defs/install-pip"},
        {"$ref": "#/$defs/install-npm"},
        {"$ref": "#/$defs/install-cargo"},
        {"$ref": "#/$defs/install-binary"},
        {"$ref": "#/$defs/install-docker"},
        {"$ref": "#/$defs/install-docker-compose"},
        {"$ref": "#/$defs/install-git-build"}
      ]
    },
    "chat_io": {
      "type": "object",
      "required": ["mode"],
      "properties": {
        "mode": {"enum": ["fifo", "exec_per_message", "one_shot_task", "http_gateway", "json_rpc_stdio", "terminal_only", "grpc_uds"]}
      },
      "allOf": [
        {"if": {"properties": {"mode": {"const": "fifo"}}}, "then": {"required": ["fifo"]}},
        {"if": {"properties": {"mode": {"const": "exec_per_message"}}}, "then": {"required": ["exec_per_message"]}},
        {"if": {"properties": {"mode": {"const": "one_shot_task"}}}, "then": {"required": ["one_shot_task"]}},
        {"if": {"properties": {"mode": {"const": "http_gateway"}}}, "then": {"required": ["http_gateway"]}},
        {"if": {"properties": {"mode": {"const": "json_rpc_stdio"}}}, "then": {"required": ["json_rpc_stdio"]}},
        {"if": {"properties": {"mode": {"const": "grpc_uds"}}}, "then": {"required": ["grpc_uds"]}}
      ]
    },
    "isolation": {
      "type": "object",
      "required": ["tier"],
      "properties": {
        "tier": {"enum": ["strict", "standard", "sysbox", "compose", "gvisor", "firecracker"]}
      }
    }
  }
}
```

The full schema is ~400 lines; Phase 02.5 plan includes "write the full JSON Schema" as one task, with this outline as the spec.

---

## 10 worked reference recipes (cover every shape in the matrix)

Each recipe is inline below. Phase 02.5 will lift these into `agents/<id>/recipe.yaml` files and L3-verify each one with a real LLM round-trip before the recipe lands on `main`. **None of these are trusted yet — they're drafts based on L1 README reads.**

### Coverage table

| # | Recipe | Runtime | chat_io.mode | auth.mechanism | isolation.tier | install.type | Stress tests |
|---|---|---|---|---|---|---|---|
| 1 | **openclaw** | node | `fifo` | `secret_file_mount` | strict | `npm` | Parent runtime for picoclaw |
| 2 | **picoclaw** | node | `fifo` | `secret_file_mount` | strict | (flavor_of openclaw) | `config_flavor_of` mechanism |
| 3 | **aider** | python | `exec_per_message` | `env_var` | strict | `pip` | Gold-standard BYOK, zero state |
| 4 | **hermes-agent** | python | `exec_per_message` | `config_file` + `interactive_wizard` override | sysbox | `pip` (no `[all]`) | Nested-container collision, [all] extras forbidden |
| 5 | **plandex** | go | `http_gateway` | `env_var` (server-side) | strict | `binary` | Go runtime, server/CLI split |
| 6 | **hiclaw** | go+shell | `http_gateway` (compose) | `gateway_token` | compose | `docker_compose` | Multi-container stress test |
| 7 | **auto-code-rover** | python | `one_shot_task` | `env_var` | strict | `pip` | Typed `input_schema`, non-standard env var name |
| 8 | **nullclaw** | zig | `fifo` | `cli_flag_on_onboard` | strict | `binary` | Cleanest onboard pattern, Zig runtime |
| 9 | **ironclaw** | rust | `exec_per_message` | `exec_time_only` | strict | `cargo` | Gold-standard threat model, WASM sandbox |
| 10 | **claude-code** | node | `fifo` | `env_var` (forced) | strict | `npm` | `policy_flags: [non_oss, oauth_required]`, non-OSS but useful |

**Coverage delivered:** 5/5 runtime families, 4/7 chat_io modes (fifo, exec_per_message, one_shot_task, http_gateway), 6/11 auth mechanisms, 3/6 isolation tiers, 5/7 install types, plus `config_flavor_of`, `policy_flags`, `input_schema`, and the `interactive_wizard` override pattern.

**Missing from v1 catalog (intentional):**
- `json_rpc_stdio` — Cody/Amp deferred (non-OSS + gateway_only, same bucket as Claude Code but lower priority)
- `terminal_only` — mentat archived, no active replacement
- `grpc_uds` — Memoh is an orchestrator, awkward as an "agent recipe" row; revisit Phase 8
- `firecracker` — Tier 4 is Phase 8+ territory

---

### Recipe 1: `openclaw`

```yaml
id: openclaw
name: OpenClaw
description: The personal AI assistant that started the clawclones movement
version: 0.1.0
license: MIT
category: claw

runtime:
  family: node
  version: "22"
  resources:
    memory_mib: 1024
    cpus: 1.0
    pids_limit: 256

install:
  type: npm
  package: openclaw
  version: "latest"

lifecycle:
  postCreateCommand:
    - "npm install -g openclaw"
    - "openclaw onboard --non-interactive"
  waitFor: postCreateCommand

launch:
  cmd: [openclaw, agent, --session, cli:default]
  workdir: /home/agent

chat_io:
  mode: fifo
  response_timeout_sec: 60
  fifo:
    fifo_in: /run/ap/chat.in
    fifo_out: /run/ap/chat.out
    strip_ansi: true

auth:
  mechanism: secret_file_mount
  headless_safe: true
  env:
    EDITOR: vim
  files:
    - secret: anthropic-api-key
      target: /home/agent/.openclaw/agents/main/agent/auth-profiles.json
      mode: "0600"
      template: openclaw_auth_profiles_json
  secrets_schema:
    - name: anthropic-api-key
      description: Anthropic API key
      required: true

providers:
  - id: anthropic
    api_base: https://api.anthropic.com/v1
    api_key_env_var: ANTHROPIC_API_KEY
    auth_style: x-api-key

models:
  - id: claude-sonnet-4-6
    provider: anthropic
    max_input_tokens: 200000
    max_output_tokens: 32000

model_flag: --model

isolation:
  tier: strict
  nested_container_collision: false
  cap_drop: [ALL]
  cap_add: [CHOWN, SETUID, SETGID, SETPCAP]
  no_new_privs: true
  read_only_rootfs: true

persistent_state:
  tmpfs:
    - { path: /tmp, size_mib: 128 }
    - { path: /run, size_mib: 16 }

frontend:
  display_name: OpenClaw
  slug: openclaw
  icon: lobster
  category_badge: "The OG"
  stars: 357000
  tier_badge: tier-1

metadata:
  source_repo: https://github.com/openclaw/openclaw
  bootstrap_generated: false
```

### Recipe 2: `picoclaw` (config_flavor_of openclaw)

```yaml
id: picoclaw
name: PicoClaw
description: OpenClaw config flavor — lighter, edge-focused
version: 0.1.0
license: MIT
category: claw

# KEY: picoclaw doesn't install its own runtime. It inherits openclaw's
# install + lifecycle, then overlays this recipe's env + files on top.
config_flavor_of: openclaw

runtime:
  family: node    # Inherited from parent; redeclared for validation

# install + lifecycle are NOT redeclared — flavor inherits parent's.
# If picoclaw needed a different launch.cmd, it could override here.

launch:
  cmd: [picoclaw, agent, --session, cli:default]

chat_io:
  mode: fifo
  response_timeout_sec: 60
  fifo:
    fifo_in: /run/ap/chat.in
    fifo_out: /run/ap/chat.out
    strip_ansi: true

auth:
  mechanism: secret_file_mount
  headless_safe: true
  files:
    - secret: anthropic-api-key
      target: /home/agent/.picoclaw/.security.yml
      mode: "0600"
      template: picoclaw_security_yml   # Different template than parent

providers:
  - id: anthropic
    api_base: https://api.anthropic.com/v1
    api_key_env_var: ANTHROPIC_API_KEY
    auth_style: x-api-key

models:
  - id: claude-sonnet-4-6
    provider: anthropic
    max_input_tokens: 200000
    max_output_tokens: 32000

model_flag: --model

isolation:
  tier: strict
  cap_drop: [ALL]
  cap_add: [CHOWN, SETUID, SETGID, SETPCAP]
  no_new_privs: true
  read_only_rootfs: true

persistent_state:
  tmpfs:
    - { path: /tmp, size_mib: 128 }
    - { path: /run, size_mib: 16 }
    - { path: /home/agent/.picoclaw/workspace/sessions, size_mib: 32, uid: 10000, gid: 10000 }

frontend:
  display_name: PicoClaw
  slug: picoclaw
  icon: lobster-small
  category_badge: "Edge Coder"
  tier_badge: tier-1

metadata:
  source_repo: https://github.com/sipeed/picoclaw
  source_sha: c7461f9e963496c4471336642ac6a8d91a456978
```

### Recipe 3: `aider` (gold-standard BYOK)

```yaml
id: aider
name: Aider
description: Pair-programming with LLMs. Zero state. Cleanest BYOK target.
version: 0.1.0
license: Apache-2.0
category: chat

runtime:
  family: python
  version: "3.13"
  resources:
    memory_mib: 1024
    cpus: 1.0

install:
  type: pip
  package: aider-chat
  version: ">=0.50.0"
  extras: []

lifecycle:
  postCreateCommand: "pip install --no-cache-dir aider-chat"

launch:
  cmd: [aider, --no-auto-commits, --no-suggest-shell-commands]

chat_io:
  mode: exec_per_message
  response_timeout_sec: 90
  exec_per_message:
    cmd_template: [aider, --message, "{text}", --yes-always]
    docker_exec_user: agent

auth:
  mechanism: env_var
  headless_safe: true
  env:
    ANTHROPIC_API_KEY: "secret:anthropic-api-key"
    OPENROUTER_API_KEY: "secret:openrouter-api-key"
  secrets_schema:
    - { name: anthropic-api-key, required: false }
    - { name: openrouter-api-key, required: false }

providers:
  - id: anthropic
    api_base: https://api.anthropic.com/v1
    api_key_env_var: ANTHROPIC_API_KEY
    auth_style: x-api-key
  - id: openai
    api_base: https://api.openai.com/v1
    api_key_env_var: OPENAI_API_KEY
    auth_style: bearer
  - id: openrouter
    api_base: https://openrouter.ai/api/v1
    api_key_env_var: OPENROUTER_API_KEY
    auth_style: bearer

models:
  - { id: claude-sonnet-4-6, provider: anthropic, max_input_tokens: 200000, max_output_tokens: 32000 }
  - { id: claude-opus-4-6, provider: anthropic, max_input_tokens: 200000, max_output_tokens: 32000 }
  - { id: gpt-5.4, provider: openai, max_input_tokens: 128000, max_output_tokens: 16000 }

model_flag: --model

# Phase 7.5 concerns — aider has two escape hatches we MUST block
policy_flags:
  - auto_commits_disabled     # We set --no-auto-commits above
  - clipboard_mode_disabled   # Web-chat paste mode bypasses metering; egress
                              # firewall must block *.paste.*

egress_allowlist:
  - api.anthropic.com
  - api.openai.com
  - openrouter.ai

isolation:
  tier: strict
  cap_drop: [ALL]
  cap_add: [CHOWN, SETUID, SETGID, SETPCAP]
  no_new_privs: true
  read_only_rootfs: true

persistent_state:
  tmpfs:
    - { path: /tmp, size_mib: 128 }
    - { path: /run, size_mib: 16 }

frontend:
  display_name: Aider
  slug: aider
  icon: terminal
  category_badge: "Clean BYOK"
  stars: 80000
  tier_badge: tier-1

metadata:
  source_repo: https://github.com/Aider-AI/aider
  last_verified: 2026-04-14
```

### Recipe 4: `hermes-agent` (nested-container + [all] extras forbidden)

```yaml
id: hermes-agent
name: Hermes
description: Multi-modal agent — pins backend to local, skips Playwright [all] bloat
version: 0.1.0
license: MIT
category: chat

runtime:
  family: python
  version: "3.13"
  resources:
    memory_mib: 2048   # Hermes needs more RAM for Python venv
    cpus: 2.0
    pids_limit: 512

install:
  type: pip
  package: hermes-agent
  version: "==5621fc4"  # Pinned SHA
  # CRITICAL: NEVER use [all] extras. It pulls Playwright + Chromium
  # which inflates the image to 5.5 GB. Use the minimal extra.
  extras: [anthropic, openai]

lifecycle:
  postCreateCommand:
    - "pip install --no-cache-dir 'hermes-agent[anthropic,openai]==5621fc4'"
    - "mkdir -p /home/agent/.hermes"
    # Pre-populate config to BYPASS the interactive setup wizard.
    # The bridge ships the cli-config.yaml.tmpl as a secret-file-mount below.

launch:
  cmd: []  # Hermes is exec_per_message only, no long-running launch
  workdir: /home/agent

chat_io:
  mode: exec_per_message
  response_timeout_sec: 120
  exec_per_message:
    cmd_template: [hermes, chat, -q, "{text}"]
    docker_exec_user: agent

auth:
  mechanism: secret_file_mount   # Hermes reads from ~/.hermes/cli-config.yaml
  headless_safe: true             # Only because we pre-populate the config
  env:
    HERMES_INFERENCE_PROVIDER: anthropic
    HERMES_QUIET: "1"
    # Pin backend to local — BLOCKS hermes's 5 other terminal backends
    # (Docker, SSH, Daytona, Singularity, Modal). Without this pin,
    # hermes tries to spawn nested containers.
    HERMES_TERMINAL_BACKEND: local
  files:
    - secret: hermes-cli-config
      target: /home/agent/.hermes/cli-config.yaml
      mode: "0600"
      template: hermes_cli_config_yaml
  secrets_schema:
    - { name: anthropic-api-key, required: true }

providers:
  - id: anthropic
    api_base: https://api.anthropic.com/v1
    api_key_env_var: ANTHROPIC_API_KEY
    auth_style: x-api-key

models:
  - id: claude-sonnet-4-6
    provider: anthropic
    max_input_tokens: 200000
    max_output_tokens: 32000

model_flag: -m

# Hermes attempts nested containers by default. MUST ship at sysbox tier.
# The HERMES_TERMINAL_BACKEND=local env above is a belt-and-suspenders
# complement, not a replacement for sysbox.
policy_flags:
  - nested_container
  - interactive_setup_bypassed

egress_allowlist:
  - api.anthropic.com

isolation:
  tier: sysbox                 # Tier 2 — nested-docker capable
  nested_container_collision: true
  cap_drop: [ALL]
  cap_add: [CHOWN, SETUID, SETGID, SETPCAP]
  no_new_privs: true
  read_only_rootfs: true

persistent_state:
  tmpfs:
    - { path: /tmp, size_mib: 256 }  # Hermes scratch is heavier
    - { path: /run, size_mib: 16 }

frontend:
  display_name: Hermes
  slug: hermes
  icon: feather
  category_badge: "Multi-Modal"
  stars: 35000
  tier_badge: tier-2

metadata:
  source_repo: https://github.com/NousResearch/hermes-agent
  source_sha: 5621fc449a7c00f11168328c87e024a0203792c3
  last_verified: 2026-04-14
```

### Recipe 5: `plandex` (Go runtime, http_gateway)

```yaml
id: plandex
name: Plandex
description: Go CLI + Go server for version-controlled multi-step plans
version: 0.1.0
license: MIT
category: multi-agent

runtime:
  family: go
  version: "1.25"
  resources:
    memory_mib: 2048
    cpus: 2.0

install:
  type: binary
  url: https://github.com/plandex-ai/plandex/releases/latest/download/plandex_linux_amd64.tar.gz
  sha256: <TBD-L2>   # L2 verification populates this

lifecycle:
  postCreateCommand:
    - "curl -fsSL ${INSTALL_URL} -o /tmp/plandex.tgz"
    - "tar -xzf /tmp/plandex.tgz -C /usr/local/bin"
    - "chmod +x /usr/local/bin/plandex /usr/local/bin/plandex-server"
  postStartCommand:
    # Plandex has a server process that the CLI talks to over HTTP
    - "plandex-server --host 127.0.0.1 --port 8787 &"

launch:
  cmd: [plandex, repl]
  workdir: /home/agent/plandex-workspace

chat_io:
  mode: http_gateway
  response_timeout_sec: 120
  http_gateway:
    internal_port: 8787
    path_prefix: /v1
    healthcheck_path: /health

auth:
  mechanism: env_var
  headless_safe: true
  env:
    # NOTE: read by plandex-server (the daemon), not the CLI
    ANTHROPIC_API_KEY: "secret:anthropic-api-key"
    OPENAI_API_KEY: "secret:openai-api-key"

providers:
  - { id: anthropic, api_base: https://api.anthropic.com/v1, api_key_env_var: ANTHROPIC_API_KEY, auth_style: x-api-key }
  - { id: openai, api_base: https://api.openai.com/v1, api_key_env_var: OPENAI_API_KEY, auth_style: bearer }

models:
  - { id: claude-sonnet-4-6, provider: anthropic }
  - { id: gpt-5.4, provider: openai }

isolation:
  tier: strict

persistent_state:
  tmpfs:
    - { path: /tmp, size_mib: 128 }
    - { path: /run, size_mib: 16 }
  named_volume:
    name: plandex-workspace
    mount: /home/agent/plandex-workspace
    size_mib: 2048

frontend:
  display_name: Plandex
  slug: plandex
  icon: workflow
  category_badge: "Planner"
  stars: 12000
  tier_badge: tier-1

metadata:
  source_repo: https://github.com/plandex-ai/plandex
```

### Recipe 6: `hiclaw` (compose stress test)

```yaml
id: hiclaw
name: HiClaw
description: Collaborative multi-agent OS with Matrix rooms + Higress gateway
version: 0.1.0
license: Apache-2.0
category: multi-agent

runtime:
  family: go
  resources:
    memory_mib: 4096  # Compose stack needs more headroom
    cpus: 2.0

install:
  type: docker_compose
  compose_file: /etc/hiclaw/docker-compose.yml
  # The compose file ships with the recipe (via COPY at image build time)

lifecycle:
  postCreateCommand:
    - "docker compose -f /etc/hiclaw/docker-compose.yml up -d"
  waitFor: postCreateCommand

launch:
  cmd: []  # Compose services are daemons; chat_io mode talks to the gateway

chat_io:
  mode: http_gateway
  response_timeout_sec: 180
  http_gateway:
    internal_port: 8080
    path_prefix: /v1/agents/default/messages
    healthcheck_path: /healthz

auth:
  mechanism: gateway_token
  headless_safe: true
  env:
    HICLAW_GATEWAY_TOKEN: "secret:hiclaw-gateway-token"
    HICLAW_CONSUMER_ID: "{session_id}"  # Per-session consumer token
    ANTHROPIC_API_KEY: "secret:anthropic-api-key"
  files:
    - secret: hiclaw-higress-config
      target: /etc/higress/config.yaml
      mode: "0644"
      template: hiclaw_higress_config

providers:
  - { id: gateway, api_base: http://localhost:8080/v1, api_key_env_var: HICLAW_GATEWAY_TOKEN, auth_style: bearer }

models:
  - { id: claude-sonnet-4-6, provider: gateway }

policy_flags:
  - nested_container   # Compose runs multiple containers

isolation:
  tier: compose
  nested_container_collision: true

persistent_state:
  tmpfs:
    - { path: /tmp, size_mib: 256 }
    - { path: /run, size_mib: 16 }
  named_volume:
    name: hiclaw-matrix-data
    mount: /var/lib/matrix
    size_mib: 4096

frontend:
  display_name: HiClaw
  slug: hiclaw
  icon: users
  category_badge: "Multi-Agent"
  tier_badge: tier-2

metadata:
  source_repo: https://github.com/agentscope-ai/HiClaw
```

### Recipe 7: `auto-code-rover` (one_shot_task + input_schema)

```yaml
id: auto-code-rover
name: AutoCodeRover
description: Autonomous repo-level repair. Docker in, patch JSON out.
version: 0.1.0
license: MIT
category: one-shot

runtime:
  family: python
  version: "3.13"
  resources:
    memory_mib: 4096
    cpus: 2.0

install:
  type: pip
  package: auto-code-rover
  version: "latest"

lifecycle:
  postCreateCommand: "pip install --no-cache-dir auto-code-rover"

launch:
  cmd: []  # One-shot — no long-running process

chat_io:
  mode: one_shot_task
  response_timeout_sec: 600   # Repair runs are slow
  one_shot_task:
    input_schema:
      - { key: github_issue_url, type: url, required: true }
      - { key: target_repo_url, type: url, required: true }
      - { key: base_commit, type: string, required: false }
    output_path: /tmp/acr_result.json
    output_format: json

auth:
  mechanism: env_var
  headless_safe: true
  env:
    # NOTE: AutoCodeRover uses OPENAI_KEY (non-standard), not OPENAI_API_KEY.
    # The env_var_aliases block teaches the orchestrator about this.
    OPENAI_KEY: "secret:openai-api-key"
    env_var_aliases:
      OPENAI_API_KEY: OPENAI_KEY

providers:
  - { id: openai, api_base: https://api.openai.com/v1, api_key_env_var: OPENAI_KEY, auth_style: bearer }

models:
  - { id: gpt-5.4, provider: openai }

isolation:
  tier: strict

persistent_state:
  tmpfs:
    - { path: /tmp, size_mib: 512 }  # ACR writes a lot of scratch
    - { path: /run, size_mib: 16 }
  named_volume:
    name: acr-workspace
    mount: /home/agent/acr
    size_mib: 4096

frontend:
  display_name: AutoCodeRover
  slug: auto-code-rover
  icon: git-merge
  category_badge: "Repo Repair"
  tier_badge: tier-1

metadata:
  source_repo: https://github.com/AutoCodeRoverSG/auto-code-rover
```

### Recipe 8: `nullclaw` (Zig runtime, cleanest onboard)

```yaml
id: nullclaw
name: NullClaw
description: Zig-native claw. Cleanest non-interactive BYOK in the catalog.
version: 0.1.0
license: MIT
category: claw

runtime:
  family: zig
  resources:
    memory_mib: 256   # Zig is extremely lean
    cpus: 0.5

install:
  type: binary
  url: https://github.com/nullclaw/nullclaw/releases/latest/download/nullclaw-linux-x86_64
  sha256: <TBD-L2>

lifecycle:
  postCreateCommand:
    - "curl -fsSL ${INSTALL_URL} -o /usr/local/bin/nullclaw"
    - "chmod +x /usr/local/bin/nullclaw"

launch:
  cmd: [nullclaw, chat]

chat_io:
  mode: fifo
  response_timeout_sec: 60
  fifo:
    fifo_in: /run/ap/chat.in
    fifo_out: /run/ap/chat.out

auth:
  mechanism: cli_flag_on_onboard
  headless_safe: true
  env:
    ANTHROPIC_API_KEY: "secret:anthropic-api-key"
  # Cleanest auth pattern in the whole sweep: one CLI call sets the key.
  # Runs in postStartCommand, not env injection.
  # This is what `cli_flag_on_onboard` means — a one-shot setup command.

lifecycle:
  postCreateCommand:
    - "curl -fsSL ${INSTALL_URL} -o /usr/local/bin/nullclaw"
    - "chmod +x /usr/local/bin/nullclaw"
  postStartCommand:
    - "nullclaw onboard --api-key ${ANTHROPIC_API_KEY}"

providers:
  - { id: anthropic, api_base: https://api.anthropic.com/v1, api_key_env_var: ANTHROPIC_API_KEY, auth_style: x-api-key }

models:
  - { id: claude-sonnet-4-6, provider: anthropic }

isolation:
  tier: strict

persistent_state:
  tmpfs:
    - { path: /tmp, size_mib: 64 }
    - { path: /run, size_mib: 16 }

frontend:
  display_name: NullClaw
  slug: nullclaw
  icon: zap
  category_badge: "Ultra-Lite"
  stars: 7000
  tier_badge: tier-1

metadata:
  source_repo: https://github.com/nullclaw/nullclaw
```

### Recipe 9: `ironclaw` (Rust, exec_time_only, gold-standard threat model)

```yaml
id: ironclaw
name: IronClaw
description: Rust WASM-sandboxed claw. Keys never at rest.
version: 0.1.0
license: MIT   # TBD at L2
category: claw

runtime:
  family: rust
  resources:
    memory_mib: 512
    cpus: 1.0

install:
  type: cargo
  package: ironclaw
  git:
    repo: https://github.com/nearai/ironclaw
    rev: <TBD-L2>
    build_cmd: [cargo, install, --path, ., --root, /usr/local]

lifecycle:
  postCreateCommand:
    - "git clone https://github.com/nearai/ironclaw /tmp/ironclaw-src"
    - "cd /tmp/ironclaw-src && cargo install --path . --root /usr/local"

launch:
  cmd: []  # ironclaw is exec_per_message — no daemon

chat_io:
  mode: exec_per_message
  response_timeout_sec: 90
  exec_per_message:
    cmd_template: [ironclaw, chat, --message, "{text}"]

auth:
  mechanism: exec_time_only
  headless_safe: true
  # KEY DIFFERENCE: keys are injected into each docker exec invocation ONLY.
  # They never appear in the container's env, filesystem, or process tree
  # outside the exec scope. Bridge layer passes --env flags per exec.
  env:
    ANTHROPIC_API_KEY: "secret:anthropic-api-key"

providers:
  - { id: anthropic, api_base: https://api.anthropic.com/v1, api_key_env_var: ANTHROPIC_API_KEY, auth_style: x-api-key }

models:
  - { id: claude-sonnet-4-6, provider: anthropic }

isolation:
  tier: strict
  # ironclaw's own WASM sandbox is a second layer of isolation on top
  # of Docker cap-drop. Best threat model in the catalog.

persistent_state:
  tmpfs:
    - { path: /tmp, size_mib: 64 }
    - { path: /run, size_mib: 16 }

frontend:
  display_name: IronClaw
  slug: ironclaw
  icon: shield
  category_badge: "Gold-Standard Security"
  tier_badge: tier-1

metadata:
  source_repo: https://github.com/nearai/ironclaw
```

### Recipe 10: `claude-code` (non-OSS but useful, policy-flagged)

```yaml
id: claude-code
name: Claude Code
description: Anthropic's official CLI. Non-OSS, headless-hostile auth, but useful.
version: 0.1.0
license: proprietary    # Anthropic TOS — flagged in policy_flags below
category: chat

runtime:
  family: node
  version: "22"
  resources:
    memory_mib: 1024
    cpus: 1.0

install:
  type: npm
  package: "@anthropic-ai/claude-code"
  version: "latest"

lifecycle:
  postCreateCommand:
    - "npm install -g @anthropic-ai/claude-code"
    # CRITICAL: do NOT invoke `claude login`. OAuth flow lands in
    # ~/.claude.json + macOS Keychain, neither of which work in a
    # headless container. We force ANTHROPIC_API_KEY injection instead.
    - "mkdir -p /home/agent/.claude"

launch:
  cmd: [claude, --no-interactive]
  workdir: /home/agent

chat_io:
  mode: fifo
  response_timeout_sec: 120
  fifo:
    fifo_in: /run/ap/chat.in
    fifo_out: /run/ap/chat.out
    strip_ansi: true

auth:
  mechanism: env_var   # Forced env var instead of Claude Code's native OAuth
  headless_safe: true  # ONLY because we skip /login and force env var
  env:
    ANTHROPIC_API_KEY: "secret:anthropic-api-key"
  # Anthropic's CLI natively wants OAuth. We explicitly DISABLE that path
  # via the launch command (--no-interactive) and by never calling /login.

providers:
  - { id: anthropic, api_base: https://api.anthropic.com/v1, api_key_env_var: ANTHROPIC_API_KEY, auth_style: x-api-key }

models:
  - { id: claude-sonnet-4-6, provider: anthropic, max_input_tokens: 200000, max_output_tokens: 32000 }
  - { id: claude-opus-4-6, provider: anthropic, max_input_tokens: 200000, max_output_tokens: 32000 }

model_flag: --model

# The reason this recipe ships at all: Claude Code is the most-requested
# agent. We flag the license + OAuth concerns so users who want OSS-only
# can filter it out of their view.
policy_flags:
  - non_oss                    # Anthropic TOS
  - oauth_required_suppressed  # Native OAuth blocked, env var forced
  - npm_install_deprecated     # README marks npm install as deprecated;
                               # we track this for future shell-installer migration

egress_allowlist:
  - api.anthropic.com

isolation:
  tier: strict
  cap_drop: [ALL]
  cap_add: [CHOWN, SETUID, SETGID, SETPCAP]
  no_new_privs: true
  read_only_rootfs: true

persistent_state:
  tmpfs:
    - { path: /tmp, size_mib: 128 }
    - { path: /run, size_mib: 16 }

frontend:
  display_name: Claude Code
  slug: claude-code
  icon: anthropic
  category_badge: "Proprietary · Most Requested"
  tier_badge: tier-1

metadata:
  source_repo: https://github.com/anthropics/claude-code
```

---

## LLM writability test plan

Before the schema is locked into Phase 02.5's PLAN.md, we run a **5-minute writability test**:

1. Prompt Claude Sonnet 4.6 with:
   - The full schema from this file
   - The JSON Schema validation spec
   - 5 of the 10 reference recipes above (exclude the other 5 to test generalization)
2. Ask it to emit a valid `recipe.yaml` for **a fresh repo it hasn't seen** — e.g. `mini-swe-agent` (since it's on our shortlist but NOT in the matrix yet).
3. Validate the LLM's output against the JSON Schema.
4. Score:
   - **Pass**: Validates on first try, install command matches upstream README, chat_io.mode is reasonable.
   - **Soft pass**: Validates after ≤2 error-correction iterations.
   - **Fail**: Needs ≥3 iterations OR the generated recipe doesn't L3-round-trip.
5. **If Fail**: iterate on the schema to remove the confusing dimension, re-run.

This test is itself a Phase 02.5 task (it's the closest thing to TDD for a schema).

---

## What this document is NOT

- **NOT a commitment.** This is a draft. `/gsd-insert-phase 02.5` followed by `/gsd-discuss-phase 02.5 --auto` may surface gray areas that change the shape.
- **NOT L2/L3-verified.** Every install command, auth path, and chat_io mode in the 10 recipes above is based on L1 README reads. Phase 02.5 execution does the L3 round-trip per recipe.
- **NOT the frontend contract.** `GET /api/recipes` exposes a subset of these fields — frontend-only metadata + a few summary fields. That contract is a separate Phase 02.5 plan task.
- **NOT self-validating.** The JSON Schema outline above is not complete. Phase 02.5 execution writes the full schema.
