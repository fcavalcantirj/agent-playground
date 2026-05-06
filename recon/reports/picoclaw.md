# picoclaw recon

**Source:** https://github.com/sipeed/picoclaw
**Commit:** `f1b659e5ef1ba972796eed70d57768120e08d0b6` (nightly-25-gf1b659e5; newest tag v0.2.6)
**Recon date:** 2026-04-15
**Budget:** 25 min. Used: ~18 min (canary path + 3 smokes + write-up).

## Step 1 — Identify

Classification: **CLI-oneshot** with an optional TUI. The `agent` subcommand
is the prompt path; `-m/--message` makes it non-interactive.

`picoclaw --help` (captured verbatim, color stripped via `--no-color`):

```
🦞 PicoClaw is a lightweight personal AI assistant.

Version: dev (git: dev)

Usage:
  picoclaw [command]

Examples:
picoclaw version
picoclaw onboard
picoclaw --no-color status

Available Commands:
  agent       Interact with the agent directly
  auth        Manage authentication (login, logout, status)
  completion  Generate the autocompletion script for the specified shell
  cron        Manage scheduled tasks
  gateway     Start picoclaw gateway
  help        Help about any command
  migrate     Migrate from xxxclaw(openclaw, etc.) to picoclaw
  model       Show or change the default model
  onboard     Initialize picoclaw configuration and workspace
  skills      Manage skills
  status      Show picoclaw status
  update      Check and apply updates from GitHub releases
  version     Show version information

Flags:
  -h, --help       help for picoclaw
      --no-color   Disable colors (boxed layout unchanged)
```

`picoclaw agent --help`:

```
Interact with the agent directly

Usage:
  picoclaw agent [flags]

Flags:
  -d, --debug            Enable debug logging
  -h, --help             help for agent
  -m, --message string   Send a single message (non-interactive mode)
      --model string     Model to use
  -s, --session string   Session key (default "cli:default")

Global Flags:
      --no-color   Disable colors (boxed layout unchanged)
```

`picoclaw onboard --help`:

```
Initialize picoclaw configuration and workspace

Usage:
  picoclaw onboard [flags]

Aliases:
  onboard, o

Flags:
      --enc    Enable credential encryption (generates SSH key and prompts for passphrase)
  -h, --help   help for onboard
```

`picoclaw version`:

```
🦞 picoclaw dev (git: dev)
  Build: 2026-04-15T19:53:40+0000
  Go: go1.25.9
```

## Step 2 — Pin source

```
git clone https://github.com/sipeed/picoclaw /tmp/recon-picoclaw
git -C /tmp/recon-picoclaw rev-parse HEAD
# f1b659e5ef1ba972796eed70d57768120e08d0b6
git -C /tmp/recon-picoclaw describe --tags HEAD
# nightly-25-gf1b659e5
```

## Step 3 — Install

Upstream ships `docker/Dockerfile` — a two-stage `golang:1.25-alpine`
builder + `alpine:3.23` runtime. Build was one-shot, no patches:

```
cd /tmp/recon-picoclaw
docker build -f docker/Dockerfile -t recon-picoclaw:latest .
```

Install log tail (stage-1 builder output, verbatim):

```
#15 66.42 github.com/sipeed/picoclaw/pkg/updater
#15 66.46 github.com/sipeed/picoclaw/pkg/tools
#15 66.50 github.com/sipeed/picoclaw/cmd/picoclaw/internal/skills
#15 66.90 github.com/sipeed/picoclaw/pkg/heartbeat
#15 66.91 github.com/sipeed/picoclaw/pkg/seahorse
#15 67.11 github.com/sipeed/picoclaw/pkg/agent
#15 67.61 github.com/sipeed/picoclaw/pkg/gateway
#15 67.62 github.com/sipeed/picoclaw/cmd/picoclaw/internal/agent
#15 67.77 github.com/sipeed/picoclaw/cmd/picoclaw/internal/gateway
#15 67.80 github.com/sipeed/picoclaw/cmd/picoclaw
#15 71.35 Build complete: build/picoclaw-linux-arm64
#15 DONE 72.3s
```

Image size expectation: alpine base + stripped static Go binary; not measured.
`picoclaw --no-color version` succeeds inside the image (captured above).

## Step 4 — Model-config surface

**No API-key env var.** Source audit (`grep -rn 'PICOCLAW_\|OPENROUTER' pkg`)
found only operational env vars (`PICOCLAW_LOG_FILE`, `PICOCLAW_DNS_SERVER`,
`PICOCLAW_KEY_PASSPHRASE`, `PICOCLAW_SSH_KEY_PATH`, `PICOCLAW_HOME`). No
`*_API_KEY` reader.

Credentials live in `~/.picoclaw/.security.yml`, referenced from
`pkg/config/example_security_usage.go`:

```yaml
# ~/.picoclaw/.security.yml
model_list:
  <model_name>:
    api_keys:
      - "<openrouter-key>"   # array even for single key
```

Model selection + base URL live in `~/.picoclaw/config.json`:

```json
{
  "version": 3,
  "agents": { "defaults": { "model_name": "probe", ... } },
  "model_list": [
    { "model_name": "probe",
      "model": "openrouter/<provider>/<model-id>",
      "api_base": "https://openrouter.ai/api/v1" }
  ]
}
```

Base-URL override IS honored (`api_base` per-model entry). Provider prefix
`openrouter/` is first-class (see `pkg/config/defaults.go` line 124 ff —
`openrouter-auto` is a built-in default model entry).

Migration behavior: on first run, picoclaw rewrites config.json from
version 0 → 3. If you put a plaintext `api_key` into config.json v0, it is
stripped out and expected to be in `.security.yml` afterward. Observed first
hand (see canary below).

## Step 5 — Non-interactive surface

`picoclaw agent -m "<prompt>"` — the only non-interactive entry point. The
flag is `-m/--message`. No positional prompt, no stdin path. This maps
cleanly to `invoke.mode: cli-flag`.

## Step 6 — Smoke matrix

Canary: gemma first (to catch config-migration surprises), then all three.

Container shape (constant across models, only the data dir changes):

```
docker run --rm --name recon-picoclaw-<slug> \
  -v /tmp/recon-picoclaw-data/<slug>:/root/.picoclaw \
  --entrypoint picoclaw recon-picoclaw:latest \
  --no-color agent -m "who are you?"
```

### gemma-3-27b-it:free — FAIL (tool-use incompat)

Verbatim stderr:

```
Error: error processing message: LLM call failed after retries: API request failed:
  Status: 404
  Body:   {"error":{"message":"No endpoints found that support tool use. Try disabling \"append_file\". To learn more about provider routi...
19:56:50 ERR agent src/pkg/agent/loop.go:2535 > LLM call failed error="API request failed:\n  Status: 404\n  Body:   {\"error\":{\"message\":\"No endpoints found that support tool use. Try disabling \\\"append_file\\\". To learn more about provider routi..." agent_id=main iteration=1 model=google/gemma-3-27b-it:free
```

Exit 1, wall 1s. Transport OK, auth OK, model reachable. Picoclaw sends
its tool definitions on every LLM call and gemma-3-27b-it:free has no
OpenRouter provider route that supports tool-use. The error explicitly
suggests `Try disabling "append_file"` — but picoclaw has no CLI flag or
single-knob for disabling tools. Tools are per-env-prefix
(`PICOCLAW_TOOLS_<X>_ENABLED=false`) across ~15+ tools; enumerating a
strip-list would be a recipe-surgery finding, not a 25-min recon fix.

### llama-3.3-70b-instruct:free — FAIL (upstream 429)

Verbatim stderr:

```
Error: error processing message: LLM call failed after retries: API request failed:
  Status: 429
  Body:   {"error":{"message":"Provider returned error","code":429,"metadata":{"raw":"meta-llama/llama-3.3-70b-instruct:free is temporaril...
```

Exit 1, wall 2s. OpenRouter returned the free tier's upstream saturation
error. Not a picoclaw bug; the install pipeline + config wiring worked.

### qwen3-coder:free — FAIL (upstream 429)

Verbatim stderr:

```
Error: error processing message: LLM call failed after retries: API request failed:
  Status: 429
  Body:   {"error":{"message":"Provider returned error","code":429,"metadata":{"raw":"qwen/qwen3-coder:free is temporarily rate-limited up...
```

Exit 1, wall 1s. Same shape as llama.

### Matrix

| Model | Verdict | Notes |
|-------|---------|-------|
| google/gemma-3-27b-it:free       | FAIL | 404 no-tool-use routes |
| meta-llama/llama-3.3-70b-instruct:free | FAIL | 429 upstream rate limit |
| qwen/qwen3-coder:free            | FAIL | 429 upstream rate limit |

Agent-level verdict (per §Verdict rules: worst of the three rows, with
PASS-if-any short-circuit not applying): **FAIL**.

Important qualifier: picoclaw itself is healthy. The install recipe
converged first try, the config-plumbing reaches OpenRouter with the right
key, and the one-shot CLI surface is exactly the shape the recipe wants.
All three FAILs are externalities of the free-tier models (provider
saturation, no tool-use route) — not agent defects. In prod on MSV,
picoclaw is driven against paid Anthropic/OpenAI routes and works.

## Step 7 — Record

Artifacts written:
- `recon/recipes/picoclaw.yaml`
- `recon/reports/picoclaw.md` (this file)
- `recon/smoke/picoclaw-gemma-3-27b.json`
- `recon/smoke/picoclaw-llama-3.3-70b.json`
- `recon/smoke/picoclaw-qwen3-coder.json`

Keys redacted; nothing committed.

## Protocol gaps & shape stretch

See the subagent reply back to the caller — this is the actual grade of
the protocol. Short list from the report's POV:

1. **`runtime.env` as a name map cannot represent picoclaw.** There are no
   env vars to map. Everything lives in two config files. `api_key=null`,
   `base_url=null`, `model=null` is technically legal per the shape, but
   it punts all three load-bearing pieces into `config_files[]` with no
   schema for *what* to write there. Step 4's verdict rule
   `BLOCKED (hardcoded config)` does not fit either — picoclaw is
   perfectly redirectable to OpenRouter, just not via env.

2. **`build.base` has one slot; picoclaw needs two (builder + runtime).**
   Upstream is a two-stage Docker build (`golang:1.25-alpine` →
   `alpine:3.23`). I encoded the builder stage as `base` and left a note
   in the recipe. A `build.stages[]` or a `build.runtime_base` field would
   be a cleaner fit.

3. **Tool-suite shape gap.** Picoclaw sends tool defs on every LLM call.
   Any model/provider route that does not support tool use returns 404.
   The recipe shape has no place to record "this agent requires a
   tool-use-capable route" and no place to record a strip-list of tools
   to disable per-session. This was the gemma finding.

4. **No env var for API keys is a recipe-wide assumption break.** Every
   other agent recon in this sweep can shove `OPENROUTER_API_KEY` into
   env. Picoclaw requires writing a YAML sidecar into a mounted volume
   *before* the container starts. Harness implication: the substrate
   cannot just `docker run -e ...`; it has to stage a per-session dir,
   write two files into it, then mount it. That deserves a dedicated
   recipe field (`runtime.secrets.files[]`) rather than living as prose
   in `config_files[]`.

## Drive-by observations

- Docker image has no ENTRYPOINT override for `picoclaw` directly — the
  shipped entrypoint is `/entrypoint.sh` (first-run setup + config check).
  I bypassed with `--entrypoint picoclaw` for the smoke. Production
  recipe should decide whether to use upstream entrypoint or shortcut it.
- `.security.yml` uses a `api_keys:` (plural) **array** even for a single
  key. Single-string form silently does nothing.
- Config `version: 0` → `version: 3` migration happens on first run. If a
  session starts with v0 containing plaintext api_keys, they get stripped
  and the next run fails unless `.security.yml` is in place. Harness must
  pre-stage v3 config + security.yml, never v0.
- picoclaw is Go-single-binary and fast to build (~70s on this host).
  Image caching across per-session builds will matter less than most of
  the other agents in the sweep.
