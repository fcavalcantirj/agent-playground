# ap-hermes — Phase 2 recipe overlay
# Layered on top of ap-base:v0.1.0. Adds Python 3.13 + uv + the Hermes source
# tree pinned to upstream commit SHA 5621fc4 (2026-04-14), pre-bakes the CLI
# config to force anthropic provider + local terminal backend.
#
# Chat path: ChatIOExec (one-shot `hermes chat -q "<msg>"` per request via
# docker exec — verified upstream cli.py lines 1-12 + main() lines 9787-9837).
# No FIFO involvement, no long-lived chat-window process. AP_AGENT_CMD stays
# empty so the chat tmux window is never created.
#
# IMPORTANT: Hermes upstream uses Python 3.13 (NOT 3.11 as CONTEXT D-19 said).
# This is the corrected baseline — do not "fix" it back to 3.11.

ARG HERMES_SHA=5621fc449a7c00f11168328c87e024a0203792c3

FROM ap-base:v0.1.0

# Re-declare ARG inside the stage so ${HERMES_SHA} is visible to the RUN below.
ARG HERMES_SHA

USER root

# --- Hermes upstream apt deps (verbatim from upstream Dockerfile) ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        nodejs \
        npm \
        python3 \
        python3-dev \
        python3-venv \
        ripgrep \
        ffmpeg \
        gcc \
        libffi-dev \
        procps && \
    rm -rf /var/lib/apt/lists/*

# --- Install uv (Python package manager) from official static binary ---
COPY --chmod=0755 --from=ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie /usr/local/bin/uv /usr/local/bin/uv
COPY --chmod=0755 --from=ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie /usr/local/bin/uvx /usr/local/bin/uvx

# --- Clone Hermes at pinned SHA ---
RUN git clone https://github.com/NousResearch/hermes-agent /opt/hermes && \
    cd /opt/hermes && \
    git checkout "${HERMES_SHA}"

# --- Install Node deps (Playwright + node-side bridges) ---
WORKDIR /opt/hermes
RUN npm install --prefer-offline --no-audit && \
    npx playwright install --with-deps chromium

# --- Install Python deps as the agent user ---
RUN chown -R agent:agent /opt/hermes
USER agent
RUN cd /opt/hermes && uv venv && uv pip install --no-cache-dir -e ".[all]"

# --- Bake the cli-config + create the work dir ---
USER root
RUN mkdir -p /home/agent/.hermes /home/agent/work && \
    chown -R agent:agent /home/agent/.hermes /home/agent/work
COPY --chown=agent:agent cli-config.yaml /home/agent/.hermes/config.yaml

# --- Symlink the hermes shell script into PATH ---
RUN ln -sf /opt/hermes/hermes /usr/local/bin/hermes

# --- Runtime env (consumed by hermes process) ---
ENV HERMES_HOME=/home/agent/.hermes
ENV PATH=/opt/hermes/.venv/bin:/usr/local/bin:$PATH
ENV HERMES_QUIET=1
ENV HERMES_INFERENCE_PROVIDER=anthropic

# --- IMPORTANT: AP_AGENT_CMD stays empty for Hermes ---
# Hermes uses ChatIOExec mode (Plan 04) — POST /messages does
# `docker exec <container> hermes chat -q "<msg>"` per request, so there is
# NO long-lived chat-window process. Leaving AP_AGENT_CMD empty causes
# ap-base's entrypoint to skip the tmux chat-window creation entirely.
ENV AP_AGENT_CMD=""

WORKDIR /home/agent
