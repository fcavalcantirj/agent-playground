# Manifest schemas across 12 agent orchestrators

**No single existing schema covers the full surface area Agent Playground needs.** Dev Containers' `devcontainer.json` comes closest for container lifecycle, Oracle Agent Spec leads on agent-level declarative structure, and MCP owns the tool-advertisement pattern — but none combines sandbox isolation, chat I/O bridging, model-provider declaration, and install/launch commands into one manifest. The recommendation is to design from scratch, lifting specific dimensions from the best prior art documented below.

## 1. Per-project schema summary

### 1.1 Praktor

- **URL**: [github.com/mtzanidakis/praktor](https://github.com/mtzanidakis/praktor) (2 stars, MIT)
- **Schema exists**: Yes — `praktor.yaml`
- **Format**: YAML
- **Top-level keys**: `telegram` (allow_from, main_chat_id), `defaults` (model, max_running, idle_timeout, image), `agents` (map → per-agent: `description`, `model`, `nix_enabled`, `env`, `files`, `allowed_tools`), `router` (default_agent)
- **Lifecycle**: Hot config reload on file change; containers lazily started, stopped on `idle_timeout`, restarted on config change; cron/interval/one-shot scheduled tasks
- **Auth/secrets**: AES-256-GCM encrypted vault with Argon2id KDF. Referenced via `secret:name` syntax in `env` values and `files` entries. Secrets injected at container start, never passed through the LLM.
- **Extensibility**: MCP servers (stdio + HTTP), Claude Code plugins via marketplace, skills as SKILL.md files, Nix package installation, agent swarms (fan-out, pipeline, collaborative)
- **License**: MIT

### 1.2 Memoh

- **URL**: [github.com/memohai/Memoh](https://github.com/memohai/Memoh) (366 stars, AGPL-3.0)
- **Schema exists**: Partial — `config.toml` for infrastructure; bot-level config stored in PostgreSQL, managed via Vue 3 UI
- **Format**: TOML (infra), database records (bots)
- **Top-level keys** (infra TOML): server settings, PostgreSQL connection, Qdrant vector DB, admin credentials, JWT secret, browser gateway port. Bot-level (DB): provider/model, bot name/type, channel connections, container settings, memory provider, MCP federation, skills, scheduled tasks, heartbeat
- **Lifecycle**: Container lifecycle via containerd (create/start/stop/export/import/backup/restore); cron-scheduled tasks; heartbeat; context/memory compaction
- **Auth/secrets**: All API keys stored in database, not config files. JWT authentication. Per-bot model/API key assignment. Container isolation prevents cross-bot access.
- **Extensibility**: MCP federation, skills, pluggable memory providers (Built-in, Mem0, OpenViking), channel adapters (Telegram, Discord, Matrix, WeChat, etc.), TTS providers
- **License**: AGPL-3.0

### 1.3 Daytona

- **URL**: [github.com/daytonaio/daytona](https://github.com/daytonaio/daytona) (72.3k stars, AGPL-3.0)
- **Schema exists**: Yes — Go SDK structs and JSON REST API payloads; also a declarative `DockerImage` builder API
- **Format**: Go structs / JSON API
- **Top-level keys** (`CreateWorkspaceDTO`): `Id`, `Name`, `Source`, `EnvVars`, `Labels`, `TargetId`. `ImageParams`: `Image`, `Resources` (vCPU, RAM, disk), `EnvVars`, `Labels`, `Volumes` (VolumeID, MountPath). `CreateSnapshotParams`: `Name`, `Image`, `Resources`, `Entrypoint`, `SkipValidation`
- **Lifecycle**: Webhooks for sandbox events; **auto-stop**, **auto-archive**, **auto-delete** intervals; snapshots for pre-built environments; resize; ephemeral mode (delete on stop)
- **Auth/secrets**: Organization-scoped API keys, JWT tokens, env var injection (`DAYTONA_API_KEY`), per-sandbox firewall rules, Git credential handling
- **Extensibility**: Multi-language SDKs (Python, TypeScript, Go, Ruby, Java), MCP server, LSP integration, Computer Use service, declarative DockerImage builder, OCI compatibility
- **License**: AGPL-3.0

### 1.4 Coder

- **URL**: [github.com/coder/coder](https://github.com/coder/coder) (AGPL-3.0)
- **Schema exists**: Yes — Terraform HCL templates using `coder/coder` provider
- **Format**: HCL (Terraform)
- **Top-level keys**: `coder_agent` resource (`os`, `arch`, `dir`, `auth`, `startup_script`, `shutdown_script`, `env`, `metadata`, `display_apps`, `connection_timeout`), `coder_app` resource (`agent_id`, `slug`, `display_name`, `command`, `url`, `icon`, `share`, `subdomain`, `healthcheck`), `coder_workspace` data source (`start_count`, `owner`, `name`)
- **Lifecycle**: `startup_script` (on start), `shutdown_script` (before stop), `healthcheck` on apps (url, interval, threshold)
- **Auth/secrets**: Agent auth modes: `token`, `google-instance-identity`, `aws-instance-identity`, `azure-instance-identity`. External auth via OAuth/OIDC. Sensitive `token` output.
- **Extensibility**: Full Terraform ecosystem — any provider (AWS, GCP, K8s, Docker). Coder Module Registry (registry.coder.com) for reusable modules. Dev Container builder support.
- **License**: AGPL-3.0

### 1.5 OpenHands

- **URL**: [github.com/OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) (formerly All-Hands-AI/OpenHands; MIT)
- **Schema exists**: Yes — `config.template.toml` (536 lines)
- **Format**: TOML + Python dataclasses
- **Top-level keys**: `[core]` (workspace_base, runtime, default_agent, max_iterations, max_budget_per_task, jwt_secret, workspace_mount_path_in_sandbox), `[llm]` (api_key, model, base_url, temperature, max_input_tokens, max_output_tokens, custom_llm_provider, native_tool_calling, caching_prompt), `[agent]` (enable_browsing), `[sandbox]`, `[security]`, `[kubernetes]`, `[cli]`, `[condenser]`, `[mcp]`
- **Lifecycle**: Agent iteration loop with `max_iterations`; trajectory recording/replay; `.openhands_instructions` per-repo; microagents from `.openhands/` directory; conversation auto-close timeout
- **Auth/secrets**: LLM keys via TOML/env/UI; `UserSecrets` persisted to `secrets.json`; API key masking in serialization; runtime secrets passed to sandbox via SDK
- **Extensibility**: MCP servers (CLI-managed), custom sandbox Docker images, pluggable agent types, microagents, Python SDK (`Agent`, `LLM`, `Conversation`, `Tool`)
- **License**: MIT

### 1.6 Plandex

- **URL**: [github.com/plandex-ai/plandex](https://github.com/plandex-ai/plandex) (MIT)
- **Schema exists**: Partial — JSON Schema for model packs (`model-pack-inline.schema.json`, `models-input.schema.json`); no workspace/plan manifest
- **Format**: JSON with JSON Schema validation
- **Top-level keys** (model pack): `planner`, `coder`, `architect`, `summarizer`, `builder`, `wholeFileBuilder`, `names`, `commitMessages`, `autoContinue`, `verifier`, `autoFix`, `localProvider`. Role config: `modelId`, `temperature`, `topP`, `largeContextFallback`, `errorFallback`, `strongModel`. Custom models: `providers[]` (name, baseUrl, apiKeyEnvVar, skipAuth), `models[]` (modelId, publisher, maxTokens, maxOutputTokens, hasImageSupport, preferredOutputFormat, providers[])
- **Lifecycle**: No explicit hooks. Auto-continue, auto-fix, auto-debug are implicit behaviors. Version-controlled plans with branching.
- **Auth/secrets**: API keys via environment variables only (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.). `apiKeyEnvVar` per custom provider. `skipAuth` for local models. No vault or secret store.
- **Extensibility**: Custom model packs, custom providers (OpenAI-compatible), multi-provider failover. No plugin API.
- **License**: MIT

### 1.7 Dev Containers spec

- **URL**: [containers.dev](https://containers.dev/implementors/json_reference/), [github.com/devcontainers/spec](https://github.com/devcontainers/spec) (CC-BY-4.0)
- **Schema exists**: Yes — formal JSON Schema (Draft 2019-09) at `schemas/devContainer.base.schema.json`
- **Format**: JSONC (`devcontainer.json`)
- **Top-level keys**: `name`, `image`, `build` (dockerfile, context, args, target), `features`, `forwardPorts`, `portsAttributes`, `containerEnv`, `remoteEnv`, `containerUser`, `remoteUser`, `mounts`, `init`, `privileged`, `capAdd`, `securityOpt`, `customizations`, `hostRequirements` (cpus, memory, storage, gpu), `workspaceFolder`, `workspaceMount`, `secrets`, `shutdownAction`, `overrideCommand`. Compose mode: `dockerComposeFile`, `service`, `runServices`.
- **Lifecycle**: **6 hooks** in order: `initializeCommand` (host), `onCreateCommand`, `updateContentCommand`, `postCreateCommand`, `postStartCommand`, `postAttachCommand`. All support parallel execution via object syntax. `waitFor` controls readiness gating.
- **Auth/secrets**: `secrets` key with env var names + metadata (description, documentationUrl). Variable substitution: `${localEnv:VAR}`, `${containerEnv:VAR}`.
- **Extensibility**: OCI-distributed **Features** (`devcontainer-feature.json`), **Templates** (`devcontainer-template.json`), namespaced `customizations` object per tool.
- **License**: CC-BY-4.0

### 1.8 Nix flakes

- **URL**: [wiki.nixos.org/wiki/Flakes](https://wiki.nixos.org/wiki/Flakes), [github.com/NixOS/nix](https://github.com/NixOS/nix) (LGPL-2.1-or-later)
- **Schema exists**: Partial — enforced by evaluator, no standalone machine-readable schema
- **Format**: Nix expression language (`.nix`)
- **Top-level keys**: `description` (string), `inputs` (attrset of dependencies with url/follows/flake), `outputs` (function → attrset). Output schema: `packages.<system>.<name>`, `devShells.<system>.<name>`, `apps.<system>.<name>` ({type, program}), `overlays.<name>`, `nixosModules.<name>`, `templates.<name>` ({path, description}), `checks.<system>.<name>`. `nixConfig` for binary cache and Nix settings.
- **Lifecycle**: None. `shellHook` in `mkShell` is the closest analog. Build lifecycle is purely functional/deterministic.
- **Auth/secrets**: None. Wiki explicitly warns against storing secrets in flake files. External tools (agenix, sops-nix) recommended.
- **Extensibility**: Flake inputs composition, `follows` for dependency unification, overlays, NixOS modules, flake-parts module system.
- **License**: LGPL-2.1-or-later

### 1.9 LangChain

- **URL**: [github.com/langchain-ai/langchain](https://github.com/langchain-ai/langchain) (MIT)
- **Schema exists**: No declarative manifest. LC serialization format exists for persistence.
- **Format**: Python API + JSON serialization
- **Top-level keys** (per serialized object): `lc` (version integer), `type` ("constructor" | "secret" | "not_implemented"), `id` (namespace path array), `kwargs` (recursive constructor args). `Serializable` class properties: `lc_secrets` (constructor arg → secret id map), `lc_attributes`, `lc_id()`
- **Lifecycle**: None declarative. Programmatic agent loop (reason → tool → observe). LangGraph provides graph-node execution.
- **Auth/secrets**: `lc_secrets` property maps args to secret IDs. `secrets_map` / `secrets_from_env` on deserialization. Environment variables for API keys.
- **Extensibility**: LCEL pipe composition, `@tool` decorator, `bind_tools()`, LangChain Hub for prompt sharing, LangGraph for graph-based agents, ConfigurableField for runtime params.
- **License**: MIT

### 1.10 MCP (Model Context Protocol)

- **URL**: [github.com/modelcontextprotocol/modelcontextprotocol](https://github.com/modelcontextprotocol/modelcontextprotocol) (7.1k stars, MIT)
- **Schema exists**: Yes — TypeScript types at `schema/2025-11-25/schema.ts`, auto-generated JSON Schema
- **Format**: TypeScript (canonical) + JSON Schema
- **Top-level keys** (`ServerCapabilities`): `experimental`, `prompts` (listChanged), `resources` (subscribe, listChanged), `tools` (listChanged), `logging`, `completions`. Three primitives: **Tools** (name, description, inputSchema, outputSchema, annotations), **Resources** (URI-identified data), **Prompts** (templates). Client config: `mcpServers.<name>` → `command`, `args`, `env` (stdio) or `type`, `url`, `headers` (HTTP).
- **Lifecycle**: Three-phase: initialize → operation → shutdown. `ping` health checks. Progress/cancellation notifications.
- **Auth/secrets**: OAuth 2.1 for remote HTTP servers. Env var interpolation (`${VAR}`) in client configs. `sensitive: true` fields encrypted via OS keychain in desktop extensions.
- **Extensibility**: Open `experimental` field for custom capabilities. Tool annotations. Server-level instructions.
- **License**: MIT

### 1.11 OpenAgents ONM

- **URL**: [github.com/openagents-org/openagents](https://github.com/openagents-org/openagents), [openagents.org](https://openagents.org/)
- **Schema exists**: Partial — conceptual spec with YAML configs in SDK, no formal JSON Schema
- **Format**: YAML (configs) + Python SDK
- **Top-level keys**: Network config: `network` (name, description, coordinator, protocols, workspace, security). Agent config: `type`, `agent_id`, `config` (model_name, instruction, react_to_all_messages, max_iterations, triggers), `mods`, `connection` (host, port, transport). Event envelope: `id`, `type`, `source`, `target`, `payload`, `metadata`, `timestamp`, `network`.
- **Lifecycle**: Event-driven triggers on glob patterns. Mods pipeline: Guard → Transform → Observe → Delivery.
- **Auth/secrets**: Progressive verification (Level 0 anonymous → Level 3 W3C DID). Per-network minimum verification. Env var-based credential management.
- **Extensibility**: Mods (Guard/Transform/Observe interceptors), multi-transport (HTTP, WebSocket, gRPC, stdio, A2A, MCP).
- **License**: Open source (exact SPDX not verified)

### 1.12 Oracle Agent Spec

- **URL**: [github.com/oracle/agent-spec](https://github.com/oracle/agent-spec) (213 stars, Apache-2.0 OR UPL-1.0)
- **Schema exists**: Yes — formal language specification with JSON Schema, latest v26.1.0
- **Format**: JSON (canonical) / YAML, validated by JSON Schema
- **Top-level keys** (base component): `component_type`, `name`, `description`, `properties`, `inputs` (JSON Schema typed), `outputs` (JSON Schema typed), `metadata`, `$component_ref`. Component types: Agent (system_prompt, llm_config, tools), Flow (nodes, edges), LLMConfig (model_id, provider subtypes for OpenAI/Anthropic/Ollama/etc.), Tools (LocalTools, ClientTools, RemoteTools, ToolBoxes), Nodes (LLMNode, ToolNode, StartNode, EndNode, BranchingNode, MapNode, ParallelFlowNode).
- **Lifecycle**: Tracing with standard span/event types. Evaluation harness. Flow execution (StartNode → processing → EndNode). No runtime lifecycle handshake — purely declarative.
- **Auth/secrets**: `Fields` for sensitive data handling (v26.1.0). Per-provider auth configs (e.g., `OciClientConfigWithApiKey`). No protocol-level auth standard.
- **Extensibility**: Plugin system for custom component types, runtime adapters (LangGraph, AutoGen, CrewAI, WayFlow, OpenAI Agents), `$component_ref` for composition, AG-UI integration, MCP tool consumption.
- **License**: Apache-2.0 OR UPL-1.0

## 2. Comparative matrix

| Project | Install cmd | Launch cmd | Auth handling | Lifecycle hooks | Chat/stdio bridging | Sandbox runtime | Model/LLM decl | Extensibility | License |
|---|---|---|---|---|---|---|---|---|---|
| **Praktor** | Nix packages | Per-agent container start | AES-256-GCM vault, `secret:` refs | 3 (reload, idle, cron) | Telegram + NATS | Docker | `model` per agent | MCP, plugins, swarms | MIT |
| **Memoh** | Via containerd image | Container start per bot | DB-stored keys, JWT | 3 (cron, heartbeat, compaction) | gRPC/UDS, multi-channel | containerd | Provider/model in DB | MCP, skills, memory providers | AGPL-3.0 |
| **Daytona** | DockerImage builder | Entrypoint in snapshot | Org API keys, JWT, firewall | 4 (auto-stop/archive/delete, webhooks) | PTY, MCP server, SSH | OCI sandbox (dedicated kernel) | None (infra-only) | Multi-SDK, MCP, LSP | AGPL-3.0 |
| **Coder** | `startup_script` | `startup_script` + `coder_app.command` | Token, cloud instance identity | 3 (startup, shutdown, healthcheck) | SSH, web terminal | Any (via Terraform) | None (infra-only) | Terraform ecosystem | AGPL-3.0 |
| **OpenHands** | Custom sandbox Dockerfile | `runtime` type selection | TOML/env/UI keys, SecretsStore | 4 (iterations, trajectory, microagents, auto-close) | CLI stdio, WebSocket, MCP | Docker / process / remote / K8s | `[llm]` section (model, provider, cost) | MCP, custom agents, SDK | MIT |
| **Plandex** | None (host-local) | CLI `plandex` | Env var API keys, `skipAuth` | 0 (implicit auto-continue/fix) | REPL stdin/stdout | None (logical diff sandbox) | JSON model packs (12 roles) | Custom models/providers | MIT |
| **Dev Containers** | `postCreateCommand` | `overrideCommand` / compose | `secrets` key + env substitution | **6** (init→postAttach) | None | Docker / Compose | None | Features, Templates | CC-BY-4.0 |
| **Nix flakes** | `buildInputs` in devShell | `apps.<sys>.default.program` | None (external tools) | 0 (`shellHook` only) | None | Nix build sandbox | None | Inputs, overlays, modules | LGPL-2.1+ |
| **LangChain** | None | Programmatic | `lc_secrets` + `secrets_map` | 0 | Streaming, message types | None | Via constructor kwargs | LCEL, tools, LangGraph | MIT |
| **MCP** | Client config `command`+`args` | Server process via stdio/HTTP | OAuth 2.1, env var interpolation | 3 (init, operation, shutdown) | **Native stdio** transport | None (out of scope) | None | `experimental` field, annotations | MIT |
| **ONM** | Docker / systemd | Agent connect to network | Progressive verification (4 levels) | 2 (event triggers, mods pipeline) | Multi-transport (gRPC, stdio, WS) | Docker (optional) | `model_name` in agent config | Mods (Guard/Transform/Observe) | OSS (unverified) |
| **Oracle Agent Spec** | None (declarative only) | Runtime adapter executes | `Fields` for sensitive data | 2 (tracing, eval harness) | AG-UI events, MCP tools | None (runtime-delegated) | `LLMConfig` component (multi-provider) | Plugins, adapters, `$component_ref` | Apache-2.0 |

## 3. What we should steal

**`recipe.runtime`** → **Daytona's `ImageParams`** pattern. Its `Image` + `Resources` (vCPU, RAM, disk) + `Volumes` structure is the cleanest declarative sandbox spec. Unlike Coder's Terraform dependency or Dev Containers' Docker-only assumption, Daytona treats the sandbox as an opaque OCI image with explicit resource bounds. Steal the shape: `image`, `resources`, `volumes`.

**`recipe.install`** → **Dev Containers' `postCreateCommand`** lifecycle hook. It runs once after container creation, supports parallel commands via object syntax, and cleanly separates install from launch. The `onCreateCommand` → `updateContentCommand` → `postCreateCommand` chain is more granular than any competitor.

**`recipe.launch`** → **Praktor's per-agent `model` + container-start pattern**, combined with **MCP's `command` + `args`** client config shape. Praktor proves that a simple YAML key per agent works at the right abstraction level; MCP's `{"command": "node", "args": ["server.js"]}` is the most widely adopted launch descriptor.

**`recipe.chat_io`** → **MCP's stdio transport**. It is the de facto standard for AI tool communication. The `StdioServerTransport` pattern — stdin for requests, stdout for responses, JSON-RPC 2.0 framing — is battle-tested across thousands of MCP servers. For non-stdio agents, steal **Daytona's PTY** abstraction as fallback.

**`recipe.auth`** → **Praktor's `secret:name` vault reference syntax**. It decouples secret storage from the manifest cleanly: `env: { "API_KEY": "secret:openai_key" }`. The vault is AES-256-GCM encrypted, secrets never touch the LLM. Dev Containers' `secrets` key with `description` and `documentationUrl` metadata is a good complement for the schema declaration side.

**`recipe.providers`** → **Plandex's `models-input.schema.json`**. Its `providers[]` (name, baseUrl, apiKeyEnvVar) and `models[]` (modelId, maxTokens, maxOutputTokens, hasImageSupport) arrays are the most complete provider/model declaration found. Oracle Agent Spec's `LLMConfig` subtypes (OpenAiConfig, AnthropicConfig, OllamaConfig) show the alternative approach of typed provider configs.

**`recipe.persistent_state`** → **Daytona's `VolumeMount`** (VolumeID + MountPath) combined with its snapshot/archive lifecycle. The auto-archive interval and ephemeral mode flags are exactly the primitives needed for session state management.

**`recipe.isolation_tier`** → **Dev Containers' security properties**: `privileged`, `capAdd`, `securityOpt`, `init`. These map directly to Docker security options and can be extended to declare gVisor/sysbox/firecracker tiers as an enum on top.

**`recipe.license`** → **Oracle Agent Spec's `metadata` field**. A freeform metadata object that can carry SPDX identifiers without polluting the core schema. Simple `metadata.license: "MIT"` pattern.

**`recipe.frontend_metadata`** → **Coder's `coder_app` resource**: `display_name`, `icon`, `slug`, `tooltip`, `group`, `share`. This is the most mature frontend-facing metadata schema. Also borrow Oracle Agent Spec's `metadata` for arbitrary GUI hints (coordinates, color-coding).

**`recipe.nested_container_collision`** → **OpenHands' `runtime` type enum** ("docker", "local", "remote", "kubernetes"). No project explicitly solves nested Docker-in-Docker collision, but OpenHands' approach of offering multiple runtime backends is the best escape hatch. Declare `isolation: docker | sysbox | remote` and let the platform route accordingly.

**`recipe.config_flavor_of`** → **Dev Containers' `devcontainer.json`** format. JSONC with a formal JSON Schema (Draft 2019-09), variable substitution (`${localEnv:VAR}`), and tool-namespaced `customizations` is the gold standard for a machine-readable, IDE-friendly config format. Use YAML as the authoring format but publish a JSON Schema for validation.

## 4. Red flags and anti-patterns

**Ships too much complexity.** Coder's full Terraform dependency means every template author must understand HCL, provider configuration, and state management to define a workspace. This is powerful for infrastructure teams but wildly over-scoped for "pick an agent, get a sandbox." Oracle Agent Spec's Flow/Node graph model (StartNode, BranchingNode, ParallelMapNode) is a workflow engine, not a manifest — it solves orchestration, not description.

**Too narrow.** Plandex is single-purpose: it only models LLM role assignments (planner, coder, architect) with no container, sandbox, or runtime concept. LangChain has no declarative manifest at all — everything is Python constructors, making it unusable as a portable config format. Memoh stores bot configuration in PostgreSQL rather than files, making it impossible to version-control or template agent definitions.

**Dead or stale.** LangChain Hub (hwchase17/langchain-hub) was archived April 2024; the YAML agent serialization format it supported is deprecated. Plandex has not shipped container isolation despite using docker-compose for its server. The ONM v1.0 spec launched March 2026 and lacks a formal IDL — the "schema" is embedded in Python SDK code and Medium blog posts, not a versioned machine-readable document.

**Solves the wrong problem.** OpenAgents ONM is an agent-to-agent **networking** model (event routing, mods pipeline, progressive verification) rather than a manifest schema. It answers "how do agents talk to each other?" not "how do you describe what an agent needs to run." Similarly, MCP is a **runtime protocol** (capability negotiation, tool invocation) — it tells you what a server *can do* after it's running, not how to *install and launch* it. Neither replaces a recipe manifest.

## 5. Direct-adoption recommendation

No existing schema covers enough surface area — Agent Playground must design its own `recipe.yaml` schema, using Dev Containers' lifecycle hooks, Daytona's runtime/volume model, MCP's stdio transport shape, Praktor's `secret:name` vault references, and Plandex's provider/model arrays as the specific building blocks to assemble into a unified format validated by a JSON Schema.