# ap-hermes

Phase 2 recipe overlay that adds the Hermes Python TUI agent to `ap-base:v0.1.0`.

## What it does

- Installs Hermes upstream apt deps (build-essential, nodejs, npm, python3-dev,
  ripgrep, ffmpeg, libffi-dev, procps) on the ap-base Debian trixie layer.
- Pulls `uv` + `uvx` static binaries from the official `ghcr.io/astral-sh/uv`
  image (pinned tag `0.11.6-python3.13-trixie`).
- Clones `github.com/NousResearch/hermes-agent` into `/opt/hermes` and pins
  it to commit SHA `5621fc4` via `git checkout`.
- Runs `npm install` + `npx playwright install --with-deps chromium` for the
  Node-side bridges.
- Creates a Python venv via `uv venv` and installs Hermes with `uv pip install -e ".[all]"`
  as uid 10000 (`agent`).
- Pre-bakes `cli-config.yaml` to `/home/agent/.hermes/config.yaml` forcing
  anthropic provider + local terminal backend + ephemeral memory.
- Symlinks the `hermes` shell entrypoint into `/usr/local/bin/hermes`.
- Sets `AP_AGENT_CMD=""` so ap-base's entrypoint skips tmux chat-window creation.

## Pinned upstream

- Repo: https://github.com/NousResearch/hermes-agent
- Commit: `5621fc449a7c00f11168328c87e024a0203792c3`
- Python: 3.13 (NOT 3.11 — RESEARCH override of CONTEXT D-19)
- Verified: 2026-04-14 (Phase 2 RESEARCH)

## Build

```sh
make build-hermes
```

Warning: ~3GB image, first build ~10+ minutes (Playwright chromium download
dominates). Depends on `make build-ap-base`.

## Smoke test

```sh
docker run --rm --entrypoint hermes ap-hermes:v0.1.0-5621fc4 --help
```

Notes:

- `--entrypoint` override is required because ap-base's `ENTRYPOINT` is the
  tini + tmux supervision chain, not the agent binary.
- For the live chat path (Plan 05 smoke test) the runtime incantation is
  `docker exec -i <container> hermes chat -q "<msg>"`.

## Chat path

`ChatIOExec` — one-shot `hermes chat -q "<msg>"` per POST /messages request.
There is no long-lived agent process inside the container; each message is a
fresh fork under tini. This is why `AP_AGENT_CMD` stays empty and ap-base's
entrypoint never creates the tmux `chat` window.

## Why no channel-daemon disable key

The upstream messaging gateways (Telegram, Discord, Slack, WhatsApp, Signal,
Matrix, Mattermost) are subcommand-activated via `hermes gateway`, not
config-activated. Phase 2 never invokes `hermes gateway`, so no daemon ever
loads. CONTEXT D-21 was wrong about needing a config-level disable key —
verified against `hermes_cli/main.py`.

## Forward-compat

- Phase 4 replaces this static Dockerfile with a declarative `agents/hermes/recipe.yaml`
  loaded by `internal/recipes/`.
- Phase 7 adds an `ap-vol-<user>` persistent volume mount at `/home/agent/.hermes/`
  so Hermes memory survives session restarts (currently `memory_enabled: false`
  because there's no persistent storage in Phase 2).
