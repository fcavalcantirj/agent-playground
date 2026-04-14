# ap-picoclaw — Phase 2 recipe overlay
# Layered on top of ap-base:v0.1.0. Adds the picoclaw Go binary pinned to
# upstream commit SHA c7461f9 (2026-03-31), runs `picoclaw onboard` at build
# time to seed ~/.picoclaw config, then leaves the agent process to be launched
# by ap-base's entrypoint shim via AP_AGENT_CMD.
#
# Chat path: ChatIOFIFO (long-lived `picoclaw agent --session cli:default`
# in tmux chat window, stdin from /run/ap/chat.in, stdout to /run/ap/chat.out).
# Plan 04 may switch to ChatIOExec (`picoclaw agent -m`) if FIFO bridging
# proves brittle — both code paths are validated upstream.

ARG PICOCLAW_SHA=c7461f9e963496c4471336642ac6a8d91a456978

# --- Stage 1: build picoclaw from pinned SHA ---
FROM golang:1.25-alpine AS builder
# Re-declare ARG inside the stage so ${PICOCLAW_SHA} is visible to the RUN below.
# Docker ARG scoping: a global ARG before the first FROM is only available to
# FROM instructions; stages need their own ARG line to consume it.
ARG PICOCLAW_SHA
RUN apk add --no-cache git make
WORKDIR /src
RUN git clone https://github.com/sipeed/picoclaw . && \
    git checkout "${PICOCLAW_SHA}" && \
    go mod download && \
    make build

# --- Stage 2: layer the binary onto ap-base ---
FROM ap-base:v0.1.0

USER root
COPY --from=builder /src/build/picoclaw /usr/local/bin/picoclaw
RUN chmod +x /usr/local/bin/picoclaw

# Run picoclaw onboard as the agent user to create initial config
USER agent
WORKDIR /home/agent
RUN /usr/local/bin/picoclaw onboard

# Fix picoclaw's baked model catalog: it lists the Claude model as
# `claude-sonnet-4.6` (dot notation) but Anthropic's canonical API name
# uses hyphens (`claude-sonnet-4-6`). Without this rewrite, every
# request to api.anthropic.com/v1 returns 404 "model not found".
# We also keep the dot-notation model_name as the picoclaw-facing
# identifier so recipe/smoke-test configs don't need to change — only
# the wire-level `model:` field gets the corrected Anthropic ID.
RUN jq '(.model_list[] | select(.model_name == "claude-sonnet-4.6") | .model) = "anthropic/claude-sonnet-4-6"' \
    /home/agent/.picoclaw/config.json > /tmp/pc.json && \
    mv /tmp/pc.json /home/agent/.picoclaw/config.json

# Pre-create the session-state dir as an empty mountpoint. The session
# handler mounts a tmpfs here at run time so picoclaw's session journal
# writes succeed under the read-only rootfs posture.
RUN mkdir -p /home/agent/.picoclaw/workspace/sessions

# Restore root for the runtime entrypoint (ap-base entrypoint drops via gosu)
USER root
WORKDIR /home/agent

# AP_AGENT_CMD launches picoclaw in interactive mode in the tmux chat window.
# The ap-base entrypoint shim wraps stdin from /run/ap/chat.in and stdout to
# /run/ap/chat.out (verified: cmd/picoclaw/internal/agent/command.go lines 1-30
# — interactive mode is the default when -m is not passed).
ENV AP_AGENT_CMD="picoclaw agent --session cli:default"
