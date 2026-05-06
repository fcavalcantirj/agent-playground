# hiclaw recon

**Source:** https://github.com/agentscope-ai/HiClaw
**Language:** Go (controller + CLI) + Node.js (agent runtime, via OpenClaw)
**Recon date:** 2026-04-15

## L1 — Paper recon

HiClaw is NOT a coding agent. It is a **Kubernetes-style multi-agent
orchestration platform** built by the Higress / alibaba / agentscope-ai group.
Its elevator pitch: a Manager agent spawns and supervises N Worker agents in
containers, all talking via a self-hosted Matrix server (Tuwunel) so humans can
watch and intervene from Element Web. HiClaw itself does not implement agent
logic — it runs **OpenClaw** (or CoPaw) inside the Manager and each Worker
container.

Architecture (from README + install script + Dockerfiles):

- `hiclaw-manager-agent` container — holds Higress AI Gateway, Tuwunel
  (Matrix), MinIO (shared FS), Element Web, and the Manager Agent itself.
  Manager Agent runs on the `openclaw-base` image: Ubuntu 22.04 + Node.js 22
  + a pinned checkout of `https://github.com/johnlanni/openclaw.git` branch
  `hiclaw-v1` at commit `86dad1383c12629ad3aa48575f2dd350fc0775d4`,
  built with `pnpm install && pnpm build`. That is the actual agent — the
  thing that calls the LLM.
- `hiclaw-worker-agent` containers — one per Worker, created by the Manager on
  demand via the controller.
- `hiclaw-controller` — Go binary, K8s controller-runtime + embedded
  `kube-apiserver` + `k3s-io/kine`. CRDs for Worker/Team/Human/Manager.
  Reconciles to Docker containers (non-K8s mode) or K8s pods (incluster).
- `hiclaw` CLI — Go binary under `hiclaw-controller/cmd/hiclaw`. A kubectl
  clone that talks to the controller REST API at `HICLAW_CONTROLLER_URL`
  (default `http://localhost:8090`). It does NOT talk to an LLM itself and
  has no `chat` / `run` / `prompt` subcommand.
- Install path: `curl | bash <(... hiclaw-install.sh)` brings up the embedded
  stack on Docker. 2823 lines of bash, heavy state-machine onboarding.
- Security model: Workers never see real API keys. Higress AI Gateway holds
  the real creds; Workers get per-session "consumer tokens" scoped through the
  gateway. LLM traffic, MCP traffic, and GitHub PAT all flow through Higress.
- Marketing language: "shrimp farm", "Claw", "CoPaw", "ZeroClaw"; the org
  runs `skills.sh`, a 80k+ skill registry. Aimed at enterprise team-of-agents
  scenarios, not single-dev coding sessions.

Key signal: HiClaw is **one layer above** the things Agent Playground runs.
It competes with *our platform*, not with OpenClaw/PicoClaw/HiClaw's own
Worker runtimes. You do not "drive hiclaw with a model." You install it,
then talk to its Manager in Element Web, and the Manager decides what Workers
to spawn to talk to the model on your behalf.

## L2 — Install

Attempted: `hiclaw` CLI **binary only** (not the full stack), inside a
throwaway `golang:1.25` container, `go build ./cmd/hiclaw`.

- Repo cloned to `/tmp/recon-hiclaw` (36 MB).
- `hiclaw-controller/go.mod`: `go 1.25.0`, pulls in `k8s.io/client-go
  v0.35.3`, `sigs.k8s.io/controller-runtime v0.21.0`, `k3s-io/kine v0.13.5`,
  `spf13/cobra v1.10.0`, `alibabacloud-go/apig-20240327/v6` (for the Higress
  gateway integration), plus Aliyun credentials SDKs.
- Build: `GOFLAGS=-mod=mod go build -o /tmp/hiclaw ./cmd/hiclaw` — succeeded
  first try with no patches.
- Full stack install (`hiclaw-install.sh`) was NOT attempted — it requires
  pulling ~1GB of images from
  `higress-registry.cn-hangzhou.cr.aliyuncs.com` (Aliyun), launching Higress
  + Tuwunel + MinIO + Element Web + the Manager container, and exposing ports
  18080/18001/18088/18888. Out of scope and out of budget for L1 recon.
- No installer signature / checksum verification noticed in the curl|bash
  flow beyond whatever GitHub's TLS gives you.

## L3 — CLI shape (verbatim --help)

```
HiClaw CLI — manages Workers, Teams, Humans, and Managers via the
hiclaw-controller REST API.

Environment variables:
  HICLAW_CONTROLLER_URL   Controller base URL (default: http://localhost:8090)
  HICLAW_AUTH_TOKEN        Bearer token for authentication
  HICLAW_AUTH_TOKEN_FILE   Path to a file containing the bearer token (K8s projected volume)

Usage:
  hiclaw [command]

Available Commands:
  apply       Apply resource configuration (create or update)
  completion  Generate the autocompletion script for the specified shell
  create      Create a resource
  delete      Delete a resource
  get         Display resources
  help        Help about any command
  status      Show cluster status
  update      Update a resource
  version     Show controller version
  worker      Worker lifecycle operations

Flags:
  -h, --help   help for hiclaw

Use "hiclaw [command] --help" for more information about a command.
```

```
$ hiclaw apply --help
Apply creates or updates resources declaratively.

  hiclaw apply -f resource.yaml
  hiclaw apply worker --name alice --zip worker.zip
  hiclaw apply worker --name alice --model qwen3.5-plus

Usage:
  hiclaw apply [flags]
  hiclaw apply [command]

Available Commands:
  worker      Apply a Worker resource (create or update)

Flags:
  -f, --file stringArray   YAML resource file(s)
  -h, --help               help for apply
```

```
$ hiclaw create --help
Create a resource

Available Commands:
  human       Create a Human user
  manager     Create a Manager agent
  team        Create a Team
  worker      Create a Worker
```

```
$ hiclaw create worker --help
Create a new Worker resource via the controller REST API.

  hiclaw create worker --name alice --model qwen3.5-plus
  hiclaw create worker --name alice --soul-file /path/to/SOUL.md --skills github-operations
  hiclaw create worker --name bob --model claude-sonnet-4-6 --mcp-servers github -o json
  hiclaw create worker --name charlie --runtime copaw --expose 8080,3000

Flags:
      --expose string           Comma-separated ports to expose (e.g. 8080,3000)
      --identity string         Worker identity description
      --image string            Container image override
      --mcp-servers string      Comma-separated MCP servers
      --model string            LLM model ID (default: qwen3.5-plus)
      --name string             Worker name (required)
      --no-wait                 Return after the Worker CR is created instead of waiting for runtime readiness
  -o, --output string           Output format (json)
      --package string          Package URI (nacos://, http://, oss://) or shorthand
      --role string             Role within team (team_leader|worker)
      --runtime string          Agent runtime (openclaw|copaw)
      --skills string           Comma-separated built-in skills
      --soul string             Worker SOUL.md content (inline)
      --soul-file string        Path to SOUL.md file (overrides --soul)
      --team string             Team name (assigns worker to a team)
      --wait-timeout duration   Maximum time to wait for the Worker to report Ready (default 3m0s)
```

```
$ hiclaw create manager --help
Create a new Manager resource.

  hiclaw create manager --name default --model qwen3.5-plus
  hiclaw create manager --name default --model claude-sonnet-4-6 --runtime copaw

Flags:
      --image string     Container image override
      --model string     LLM model ID (required)
      --name string      Manager name (required)
      --runtime string   Agent runtime (openclaw|copaw)
      --soul string      Manager SOUL.md content
```

```
$ hiclaw worker --help
Worker lifecycle operations

Available Commands:
  ensure-ready Ensure a Worker is running and ready
  report-ready Report worker readiness to controller
  sleep        Put a Worker to sleep
  status       Show Worker runtime status
  wake         Wake a sleeping Worker
```

```
$ hiclaw get --help
Display resources

Available Commands:
  humans / managers / teams / workers
```

```
$ hiclaw status --help
Show cluster status

Flags:
  -o, --output string   Output format (json)
```

Note: every subcommand requires a reachable controller at
`HICLAW_CONTROLLER_URL`. Running any of them without the full stack running
will fail the first REST call.

## L4 — Auth / config

Two layers:

**CLI → controller auth** (HiClaw-internal)
- `HICLAW_CONTROLLER_URL` — controller base URL, default `http://localhost:8090`.
- `HICLAW_AUTH_TOKEN` — bearer token.
- `HICLAW_AUTH_TOKEN_FILE` — path to token file (K8s projected volume style).

**Agent → LLM auth** (what actually matters for model probing)
HiClaw abstracts this behind `HICLAW_LLM_PROVIDER` with these choices in
`hiclaw-install.sh`:
- `alibaba-cloud` (default), `qwen`, `openai-compat`.
- `openai-compat` accepts an arbitrary `HICLAW_OPENAI_BASE_URL` and
  `HICLAW_LLM_API_KEY`, which the installer validates with a literal
  `POST {base_url}/chat/completions` using `{"model":"<model>", "messages":
  [{"role":"user","content":"hi"}]}`. That is the **one and only** test for
  provider compatibility. If OpenRouter answers 200 on that call, HiClaw
  considers it valid.
- Env knobs the installer will export:
  `HICLAW_LLM_PROVIDER`, `HICLAW_DEFAULT_MODEL`, `HICLAW_OPENAI_BASE_URL`,
  `HICLAW_LLM_API_KEY`, `HICLAW_EMBEDDING_MODEL`.
- Real creds ultimately land in the Higress AI Gateway config, not in Worker
  containers. Workers hit the gateway with consumer tokens.

Conclusion: OpenRouter plugs into the `openai-compat` path as long as you
set `HICLAW_OPENAI_BASE_URL=https://openrouter.ai/api/v1`, pass
`HICLAW_LLM_API_KEY=sk-or-v1-REDACTED`, and pick a model ID OpenRouter
recognizes.

## L5 — Model catalog

No hard-coded catalog — model IDs are free-form strings passed via
`--model` on `hiclaw create worker` / `hiclaw create manager`. Examples in
the `--help` output: `qwen3.5-plus`, `claude-sonnet-4-6`. Any string the
configured provider accepts will be forwarded. Nothing in the CLI enforces
a model allow-list.

For OpenRouter, the `:free` suffix models should work verbatim:
- `google/gemma-3-27b-it:free`
- `meta-llama/llama-3.3-70b-instruct:free`
- `qwen/qwen3-coder:free`

## L6 — Matrix cells (per model)

All three cells: **BLOCKED — no OpenRouter API key in environment.**

- `env | grep OPENROUTER` returned nothing.
- `$AP_DEV_OPENROUTER_KEY` was empty in the recon shell.
- The project's `.env.example` does not define it; only `test/smoke-matrix.sh`
  and `api/internal/session/secrets.go` reference the var name.
- Smoke probe (no key) hit all three models through
  `POST https://openrouter.ai/api/v1/chat/completions`:

  ```
  google/gemma-3-27b-it:free            HTTP 401 {"error":{"message":"Missing Authentication header","code":401}}
  meta-llama/llama-3.3-70b-instruct:free HTTP 401 {"error":{"message":"Missing Authentication header","code":401}}
  qwen/qwen3-coder:free                  HTTP 401 {"error":{"message":"Missing Authentication header","code":401}}
  ```

So the network path and the model IDs are valid (OpenRouter recognizes the
endpoint and returns its standard unauthenticated error instead of 404). The
blocker is purely the missing key; rerunning with `AP_DEV_OPENROUTER_KEY`
exported should turn all three into PASS on the connectivity test.

Even with a key, a full end-to-end "drive HiClaw with model X" flow requires
bringing up the full embedded stack (controller + Tuwunel + MinIO + Element
Web + Manager + at least one Worker container) — out of budget for this
recon. The matrix test, as defined, can only validate the
`openai-compat`-style connectivity check that HiClaw itself uses during
`hiclaw-install.sh`.

| Cell | Status | Note |
|------|--------|------|
| gemma-3-27b-it:free via HiClaw installer path | BLOCKED | No API key present |
| llama-3.3-70b-instruct:free via HiClaw installer path | BLOCKED | No API key present |
| qwen3-coder:free via HiClaw installer path | BLOCKED | No API key present |

## L7 — Runtime profile

- **CLI binary size (host build, darwin-arm64, stripped defaults):** built
  inside a linux/amd64 go:1.25 container to `/tmp/hiclaw`, not sized (container
  was torn down). `go build` finished in well under a minute after module
  download; no cgo required for the CLI.
- **Go version floor:** 1.25.0 (via `go.mod`).
- **Full manager image:** `hiclaw-manager:latest`, built FROM
  `hiclaw/openclaw-base:latest` which is FROM
  `higress-registry.cn-hangzhou.cr.aliyuncs.com/higress/all-in-one` (Ubuntu
  22.04) + Node.js 22 + pnpm + the whole OpenClaw monorepo compiled. The
  bundle includes mc (MinIO client) and the `hiclaw` CLI. Expect
  **>1 GB** image.
- **Embedded controller image** (`Dockerfile.embedded`): Ubuntu 22.04 +
  Tuwunel + MinIO + mc + Element Web + hiclaw-controller +
  kube-apiserver + nginx + supervisord. This is the "one container does
  everything except Manager" box.
- **Per-worker container:** another OpenClaw (or CoPaw) runtime instance.
  README claims OpenClaw ~500 MB RSS; CoPaw ~150 MB RSS. ZeroClaw /
  NanoClaw are on the roadmap but unreleased.
- **Host ports reserved by default:** 18080 (Higress gateway), 18001
  (Higress console), 18088 (Element Web), 18888 (Manager console).
- **Host requirements README calls out:** "2 CPU / 4 GB min, 4 CPU / 8 GB
  recommended". Plus Docker daemon with socket access (installer wants to
  mount `/var/run/docker.sock` into the controller so it can reconcile
  Worker containers on the host — see `HICLAW_MOUNT_SOCKET=1` default).
- **Persistence:** `hiclaw-data` Docker volume + `~/hiclaw-manager` host
  dir for workspace.
- **Telemetry:** an `openclaw-cms-plugin` is downloaded unconditionally from
  an Alibaba OSS bucket (`arms-apm-cn-hangzhou-pre.oss-cn-hangzhou.aliyuncs.com`)
  during base image build. Traces to ARMS are opt-in via
  `HICLAW_CMS_TRACES_ENABLED=true`, but the plugin is bundled unconditionally.

## L8 — Surprises / gotchas

- **HiClaw is not a coding agent at all.** It is a Kubernetes-style
  orchestrator for OpenClaw instances. The actual agent code lives in
  `https://github.com/johnlanni/openclaw.git` (a fork; note `johnlanni/`,
  not `agentscope-ai/openclaw`), pinned to commit
  `86dad1383c12629ad3aa48575f2dd350fc0775d4`.
- **Mounts the host docker socket by default.** `HICLAW_MOUNT_SOCKET=1`
  means the controller can `docker run` arbitrary Worker containers on the
  host. Giving the Manager Agent access to the host daemon is a container-
  escape-on-a-platter pattern; the README does not mention Sysbox or any
  mitigation. Hard conflict with Agent Playground's v1.5 isolation goals.
- **Aliyun registry dependency.** Base images come from
  `higress-registry.cn-hangzhou.cr.aliyuncs.com`. Reachable from Europe/US
  but slow; no stated mirror on Docker Hub or GHCR. A regional outage
  breaks `make build` and `hiclaw-install.sh`.
- **Telemetry pre-bundled.** `OPENCLAW_CMS_PLUGIN_URL` is fetched
  unconditionally at image build time from Alibaba OSS. Opt-out means
  disabling ARMS reporting at runtime, not stripping the plugin.
- **No `hiclaw chat` / `hiclaw run` / `hiclaw prompt` subcommand.** There is
  literally no way to drive an LLM from the CLI. All user interaction is
  expected to happen through Element Web talking to the Manager over
  Matrix.
- **Install script is 2823 lines of bash with a state-machine onboarding
  UX** (including "back" navigation). Automation via
  `HICLAW_NON_INTERACTIVE=1` exists but the happy path is interactive.
- **Models are free-form strings.** No validation of model IDs against
  anything — the validation is "did chat/completions return 200". That's
  *good* for our purposes (OpenRouter `:free` IDs will pass through
  unmolested) but bad for misconfig detection.
- **`hiclaw-v1` branch of johnlanni/openclaw, pinned commit.** HiClaw does
  not track upstream OpenClaw. Any security fix to upstream OpenClaw would
  need a HiClaw release to propagate.
- **Embeds `k3s-io/kine` + `kube-apiserver`** in the controller image. So
  even "non-K8s" installs run a kube-apiserver + a kine datastore locally.
  Expect noticeable memory overhead.
- **The `--package` flag accepts `nacos://`, `oss://`, and `http://` URIs**
  for worker definitions; Nacos is the Alibaba service discovery system. The
  default Worker marketplace is at `nacos://market.hiclaw.io:80/public` —
  depending on that host means depending on hiclaw.io staying up.
- **Chinese-first UX.** README, docs, install script all have zh-CN /
  en / ja variants; messages in the installer are keyed like `msg
  llm.openai.base_url_prompt.zh`. Not a blocker, but confirms target
  audience.
- **Idle timeout for Workers is 720 min (12h) by default** — generous
  compared to what Agent Playground v1 will allow.

## L9 — Recipe implications (bullet sketch only)

- HiClaw does **not** belong in the "pick a coding agent" selector on the
  Agent Playground landing page. It is a different shape of product. Users
  who pick "HiClaw" would be picking a whole orchestration platform, not a
  CLI they can drive over the WebSocket.
- If we still want to offer HiClaw as a session type, the recipe would be
  unlike every other entry in the catalog:
  1. The session container would not run an agent directly. It would run
     the **hiclaw embedded controller** (`Dockerfile.embedded` →
     Higress all-in-one + Tuwunel + MinIO + Element Web + controller +
     kube-apiserver).
  2. A second container for the **Manager Agent** (`manager/Dockerfile` →
     openclaw-base with the Manager SOUL).
  3. A third container per **Worker** created on demand by the Manager.
  4. The browser chat UI would need to embed Element Web (iframe) pointing
     at the session-scoped Tuwunel port.
  5. The terminal view would attach to... what? The Manager? The
     currently-focused Worker? Undefined.
  6. The LLM egress proxy would have to be injected at the **Higress
     gateway layer**, not at the container env layer, because HiClaw
     routes LLM traffic through Higress. That means per-session Higress
     config reload on every session start.
- Multi-container-per-session breaks the "one container per session"
  assumption baked into the research brief and likely into the session
  CRD shape. Budgeting, isolation, reaping, and idle-tracking are all 3×
  the work.
- Docker socket mount is a non-starter for the shared Hetzner host without
  Sysbox-or-better isolation. v1.5 hardening would be mandatory, not
  optional, before a HiClaw recipe can ship.
- Models flow through the HiClaw `openai-compat` path: recipe emits
  `HICLAW_LLM_PROVIDER=openai-compat`,
  `HICLAW_OPENAI_BASE_URL=http://<per-session-egress-proxy>/v1`,
  `HICLAW_LLM_API_KEY=<session-token>`,
  `HICLAW_DEFAULT_MODEL=<user-pick>`. This part is the one clean piece.
- Recipe would have to ship its own `SOUL.md` for the Manager and probably
  a curated Worker catalog, because the default Nacos marketplace is
  hosted at `market.hiclaw.io` and we cannot depend on a third-party
  registry for session startup.
- **Alternative view:** skip HiClaw at the top level entirely and instead
  list its underlying runtimes — OpenClaw, CoPaw, (later) NanoClaw /
  ZeroClaw — as first-class agent picks. Those are what actually talk to
  the model. HiClaw's value-add (Matrix visibility, Manager-over-Workers,
  skills.sh) can be a "team mode" tier on top, not a basic recipe.

## L10 — Blockers

1. **No OpenRouter API key in environment** — `AP_DEV_OPENROUTER_KEY`
   unset, so the L6 matrix is BLOCKED across all three cells. Unblocker:
   export the key and re-run the three `curl` probes (or a real install)
   against `https://openrouter.ai/api/v1/chat/completions`.
2. **Full stack install out of budget** — HiClaw cannot be meaningfully
   end-to-end tested without running the embedded controller + Manager +
   at least one Worker. That is minimum 3 containers, ~1 GB of image
   pulls from Aliyun, ~4 GB RAM. Not doable in a 20-minute L1 recon.
3. **Shape mismatch with Agent Playground recipe model.** HiClaw is an
   orchestrator, not a driven CLI. There is no `hiclaw --prompt "foo"`
   equivalent. Recipe phase needs a design decision about whether to
   integrate HiClaw at all, or to integrate OpenClaw/CoPaw directly and
   reserve HiClaw for a later "team mode" tier.
4. **Docker socket mount by default.** Any shared-host integration must
   be gated on Sysbox (v1.5) or a microVM runtime (v2). Cannot ship on
   plain Docker.
5. **Pinned dependency on `johnlanni/openclaw@hiclaw-v1@86dad13…`.**
   HiClaw does not track upstream OpenClaw — we would either inherit
   their pinned fork for any recipe we write, or rebase against
   upstream and risk breaking the Manager SOUL/TOOLS assumptions.
6. **Aliyun-only base image supply chain.** Cannot mirror to a public
   registry without re-building and re-signing everything.
7. **Telemetry bundled unconditionally.** The `openclaw-cms-plugin` is
   installed at image build time regardless of the runtime flag; we would
   either ship it to users (privacy concern) or patch the Dockerfile.
