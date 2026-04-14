# ap-base — Agent Playground base image
# Provides: tini PID 1, tmux (chat + shell windows), ttyd 1.7.7 on loopback,
# gosu privilege-drop entrypoint shim, FIFO scaffolding at /run/ap, secret
# bind-mount target at /run/secrets, agent user uid 10000.
# Recipe overlays FROM ap-base:vX.Y.Z and add the agent binary + config only.
# Phase: 02. Pinned: ttyd 1.7.7 (verified GitHub releases 2024-03-30).

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Runtime deps (D-10): tini, gosu, tmux, bash, git, curl, jq, ca-certificates, procps.
# procps is needed for `ps` so the smoke test can verify PID 1 = tini.
# `gosu nobody true` at the tail smoke-tests gosu (mirrors MSV picoclaw/Dockerfile line 24).
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        gosu \
        tmux \
        bash \
        git \
        curl \
        jq \
        ca-certificates \
        procps \
    && rm -rf /var/lib/apt/lists/* \
    && gosu nobody true

# ttyd — pinned binary release (D-07). Default arch is x86_64 (Hetzner prod target).
# Local dev on arm64 Macs: `docker build --build-arg TTYD_ARCH=aarch64 …`.
# ttyd publishes ttyd.{x86_64,aarch64,arm,mips} release assets.
ARG TTYD_VERSION=1.7.7
ARG TTYD_ARCH=x86_64
RUN curl -fsSL -o /usr/local/bin/ttyd \
      "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.${TTYD_ARCH}" \
    && chmod +x /usr/local/bin/ttyd \
    && /usr/local/bin/ttyd --version

# Unprivileged agent user (D-08). uid 10000 matches Hermes upstream conventions and
# stays clear of host system UIDs even after userns-remap.
RUN useradd -u 10000 -m -d /home/agent -s /bin/bash agent

# CRITICAL (Pitfall 7): pre-create the secret bind-mount target AND the FIFO dir
# at image build time. With --read-only rootfs at runtime, you cannot mkdir these
# after the fact. /run/secrets stays root-owned mode 0500 — Plan 04 bind-mounts the
# per-session secret file over this dir; /run/ap is owned by agent so entrypoint
# phase 2 can mkfifo on the tmpfs overlay.
RUN mkdir -p /work /home/agent /run/ap /run/secrets \
    && chown -R agent:agent /work /home/agent /run/ap \
    && chmod 0500 /run/secrets

# Entrypoint shim — copy with explicit mode so we do not need a separate chmod layer.
COPY --chmod=0755 entrypoint.sh /entrypoint.sh

# Stay as root — entrypoint phase 1 fixes perms, then drops via gosu to agent.
WORKDIR /home/agent

# tini -g forwards SIGTERM/SIGINT to the entire process group, not just the direct
# child (Pitfall 1). This is what lets `docker stop` tear down ttyd + tmux + the
# agent process cleanly in one shot.
ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/entrypoint.sh"]

# Default CMD proves the supervision chain works for a bare ap-base smoke test.
# Recipe overlays override CMD or set AP_AGENT_CMD env to launch their agent.
CMD ["bash", "-lc", "tail -f /dev/null"]
