# ap-base — Agent Playground base image

Debian 13 (trixie) slim base image that every Phase 2+ recipe FROMs.

**Provides:**
- `tini` as PID 1 (signal forwarding + zombie reaping, `-g` process group flag)
- `gosu` privilege drop (root → uid 10000 `agent`)
- `tmux` session `ap` with `shell` window (and `chat` window when `AP_AGENT_CMD` is set)
- `ttyd 1.7.7` bound to `127.0.0.1:7681` (loopback only — Phase 5 adds the Go WS reverse proxy)
- FIFO scaffolding at `/run/ap/chat.in` and `/run/ap/chat.out` (tmpfs at runtime)
- Secret bind-mount target at `/run/secrets/` (Phase 2 dev BYOK source: env var → host file → bind-mount → entrypoint reads `/run/secrets/anthropic_key` and exports `ANTHROPIC_API_KEY` into the agent process env only)

**Build:**
```bash
make build-ap-base
```

On aarch64 dev hosts override the ttyd arch:
```bash
docker build --build-arg TTYD_ARCH=aarch64 -t ap-base:v0.1.0 deploy/ap-base/
```

**Smoke test:**
```bash
docker run -d --rm --name aps --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --tmpfs /run:rw,noexec,nosuid,size=16m \
  ap-base:v0.1.0
docker exec aps ps -p 1 -o comm=          # → tini
docker exec aps id agent                  # → uid=10000
docker exec -u agent aps tmux list-windows -t ap
docker stop aps
```

**Recipe overlays:** Recipes FROM `ap-base:v0.1.0` and add only the agent binary. They MUST NOT edit ap-base; agent-agnostic is the contract.

**Ported from:** `meusecretariovirtual/infra/picoclaw/{Dockerfile,entrypoint.sh}` lines 13-30 (gosu drop) verbatim. MSV-specific OAuth/AMCP/OpenClaw bits intentionally NOT ported.
