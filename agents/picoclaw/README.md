# ap-picoclaw

Phase 2 recipe overlay that adds the `picoclaw` Go binary to `ap-base:v0.1.0`.

## What it does

- Builds `picoclaw` from upstream source in a `golang:1.25-alpine` stage.
- Copies the static binary into the ap-base runtime at `/usr/local/bin/picoclaw`.
- Runs `picoclaw onboard` at build time as uid 10000 (`agent`) to seed `~/.picoclaw/`.
- Sets `AP_AGENT_CMD="picoclaw agent --session cli:default"` so ap-base's entrypoint
  launches the interactive agent in the tmux `chat` window with stdin/stdout bound
  to `/run/ap/chat.in` and `/run/ap/chat.out` (ChatIOFIFO path).

## Pinned upstream

- Repo: https://github.com/sipeed/picoclaw
- Commit: `c7461f9e963496c4471336642ac6a8d91a456978`
- Verified: 2026-03-31 (Phase 1 SPIKE-REPORT, re-verified during Phase 2 planning)

## Build

```sh
make build-picoclaw
```

(depends on `make build-ap-base`)

## Smoke test

```sh
docker run --rm --entrypoint picoclaw ap-picoclaw:v0.1.0-c7461f9 version
```

Notes:

- `--entrypoint` override is required because ap-base's `ENTRYPOINT` is the
  tini + tmux supervision chain, not the agent binary; a one-shot version
  probe needs to bypass that chain.
- picoclaw uses `version` as a subcommand (not a `--version` flag). Verified
  against upstream Cobra layout at commit `c7461f9`.

## Chat path

`ChatIOFIFO` — long-lived agent in the tmux chat window consuming from the FIFOs
ap-base pre-opens at PID 1. Plan 04's session handler exec's writes into
`/run/ap/chat.in` and reads from `/run/ap/chat.out`.

## Forward-compat

Phase 4 replaces this static Dockerfile with a declarative `agents/picoclaw/recipe.yaml`
loaded by `internal/recipes/`. The image tag `ap-picoclaw:v0.1.0-c7461f9` is the
cross-phase contract Plan 02-04 references in `internal/recipes/recipes.go`.
