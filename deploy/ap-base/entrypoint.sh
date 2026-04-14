#!/bin/bash
# ap-base entrypoint shim.
# Phase 1 (root): fix mounted-volume perms, then exec gosu agent self.
# Phase 2 (agent): pre-open FIFOs (Pitfall 2 fix), read /run/secrets/*_key,
#                  start ttyd in background, start tmux session with chat +
#                  shell windows, exec the recipe's launch command.
# Ported from MSV infra/picoclaw/entrypoint.sh lines 13-30 verbatim,
# all OAuth/AMCP/OpenClaw bits (MSV lines 36-202) intentionally NOT ported.
set -euo pipefail

AGENT_USER="agent"
AGENT_HOME="/home/agent"
RUN_DIR="/run/ap"
FIFO_IN="${RUN_DIR}/chat.in"
FIFO_OUT="${RUN_DIR}/chat.out"
TTYD_PORT="${AP_TTYD_PORT:-7681}"

# === PHASE 1: root ===
if [ "$(id -u)" = "0" ]; then
    # /run is a tmpfs under the default sandbox posture — the build-time /run/ap
    # and /run/secrets dirs do not survive the tmpfs overlay, so recreate them
    # here (phase 1 is still root and can mkdir freely on the tmpfs). /run/secrets
    # stays root-owned mode 0500 so the Plan 04 bind-mount target exists; absent a
    # bind-mount it is just an empty dir. This preserves Pitfall 7 semantics at
    # runtime the same way the Dockerfile did at build time.
    mkdir -p "$RUN_DIR" /run/secrets
    chmod 0500 /run/secrets

    # Fix ownership of any mounted volumes (Phase 7 will mount /work as a
    # named volume; Phase 2 uses tmpfs, so this is a no-op then). Tolerate
    # failures — read-only rootfs may make some chowns fail harmlessly.
    chown -R "$AGENT_USER:$AGENT_USER" /work "$AGENT_HOME" "$RUN_DIR" 2>/dev/null || true

    # Re-exec self as agent.
    exec gosu "$AGENT_USER" "$0" "$@"
fi

# === PHASE 2: agent ===
echo "=== ap-base entrypoint (user: $(whoami) uid=$(id -u)) ==="

# --- Create FIFOs on the tmpfs at /run/ap ---
# /run/ap is created at image build time and is a tmpfs at runtime per the
# default sandbox posture. mkfifo on tmpfs is supported (Spike 3 verified
# p99 0.19ms RTT). Pre-existing FIFOs (after a container restart) are reused.
[ -p "$FIFO_IN"  ] || mkfifo "$FIFO_IN"
[ -p "$FIFO_OUT" ] || mkfifo "$FIFO_OUT"
chmod 600 "$FIFO_IN" "$FIFO_OUT"

# --- CRITICAL (Pitfall 2): hold the FIFOs open from PID 1 BEFORE launching
# any reader/writer. Otherwise the first POSIX open() for write blocks
# forever waiting for a reader, and vice versa. The exec assigns FDs that
# stay open for the entrypoint's lifetime.
exec 3<>"$FIFO_IN"
exec 4<>"$FIFO_OUT"

# --- Read injected secrets into a per-agent env list (NOT into PID 1's env) ---
# Phase 2 dev BYOK source: /run/secrets/anthropic_key (host bind-mount).
# Phase 3 swaps source for the encrypted vault — same in-container path.
AGENT_ENV=()
if [ -f /run/secrets/anthropic_key ]; then
    AGENT_ENV+=("ANTHROPIC_API_KEY=$(cat /run/secrets/anthropic_key)")
fi
if [ -f /run/secrets/openai_key ]; then
    AGENT_ENV+=("OPENAI_API_KEY=$(cat /run/secrets/openai_key)")
fi
if [ -f /run/secrets/openrouter_key ]; then
    AGENT_ENV+=("OPENROUTER_API_KEY=$(cat /run/secrets/openrouter_key)")
fi

# --- Start ttyd in the background, loopback only ---
# Recipe overlays may override AP_TTYD_PORT. Phase 5 will front this with a Go
# WS reverse proxy; Phase 2 just verifies it binds and responds on loopback.
# NOTE: --once is intentionally OMITTED — see Assumption A2 in RESEARCH; --once
# would kill the supervision chain after the first WS client disconnect.
ttyd \
    --port "$TTYD_PORT" \
    --interface 127.0.0.1 \
    --writable \
    --max-clients 1 \
    bash -lc 'tmux attach -t ap || tmux new -s ap' \
    > "$RUN_DIR/ttyd.log" 2>&1 &
TTYD_PID=$!
echo "ttyd started on 127.0.0.1:$TTYD_PORT (pid $TTYD_PID)"

# --- Create the tmux session with two windows ---
# Window "shell": plain bash for ttyd-attached web terminal
# Window "chat":  agent process attached to FIFOs (recipe-specific, optional)
tmux new-session -d -s ap -n shell "exec bash -l"

# --- Launch the agent in the "chat" window if AP_AGENT_CMD is set ---
# AP_AGENT_CMD is set by the recipe overlay (e.g. picoclaw recipe sets
# "picoclaw agent --session cli:default"). For Hermes (ChatIOExec mode),
# the recipe leaves AP_AGENT_CMD empty and the chat window stays unused —
# POST /messages will exec `hermes chat -q` per request instead.
if [ -n "${AP_AGENT_CMD:-}" ]; then
    # Build env prefix for the agent (NOT exported into entrypoint env)
    ENV_PREFIX=""
    for kv in "${AGENT_ENV[@]}"; do
        ENV_PREFIX="$ENV_PREFIX $kv"
    done
    tmux new-window -t ap -n chat \
        "env $ENV_PREFIX bash -c '$AP_AGENT_CMD < $FIFO_IN > $FIFO_OUT 2>&1'"
fi

# --- Stay alive as long as the tmux session lives ---
# tini (PID 1) supervises this script; this script supervises tmux + ttyd.
# Loop sleep is fine — Spike 3 RTT proved FIFO writes are sub-ms; the only
# job of this loop is to keep PID 1 from exiting.
while tmux has-session -t ap 2>/dev/null; do
    sleep 5
done

echo "tmux session ended; entrypoint exiting"
