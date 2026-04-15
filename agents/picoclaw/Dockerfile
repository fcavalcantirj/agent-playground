# ap-picoclaw — Phase 02.5 recipe overlay (rebuilt from Phase 2)
#
# Inheritance chain (D-22):
#   ap-base:v0.1.0 ← ap-runtime-node:v0.1.0-22 ← this image
#
# Phase 02.5 change: the FINAL stage now layers on top of ap-runtime-node
# instead of ap-base directly. Recipes must never inherit ap-base directly —
# they must target an ap-runtime-<family> base, so the family→base mapping
# stays a single source of truth. For picoclaw (a Go binary) the runtime base is
# `node` because Pattern 11 (D-40b) declares runtime.family=node; node
# itself is unused by the picoclaw binary but the runtime plumbing is
# consistent with the manifest's declared family.
#
# The Go toolchain stage is UNCHANGED from Phase 2 — picoclaw is a Go
# binary built via `make build`, producing a statically linkable artifact.
#
# Pinned SHA (D-42): 773a94c41437d21c7cb1fcc429cee1ac605dd509 — see
# agents/picoclaw/recipe.yaml metadata.source_sha and
# .planning/phases/02.5-recipe-manifest-reshape/02.5-08-scratch-a7.md.
#
# Chat path: ChatIOFIFO (long-lived `picoclaw agent --session cli:default`
# in tmux chat window, stdin from /run/ap/chat.in, stdout to /run/ap/chat.out).
# See recipe.yaml chat_io.mode=fifo for the declarative equivalent.

ARG PICOCLAW_SHA=773a94c41437d21c7cb1fcc429cee1ac605dd509

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

# --- Stage 2: layer the binary onto ap-runtime-node (Phase 02.5 D-22) ---
FROM ap-runtime-node:v0.1.0-22

USER root
COPY --from=builder /src/build/picoclaw /usr/local/bin/picoclaw
RUN chmod +x /usr/local/bin/picoclaw

# Run picoclaw onboard as the agent user to create initial config
USER agent
WORKDIR /home/agent
RUN /usr/local/bin/picoclaw onboard

# Fix picoclaw's baked model catalog: historically it shipped with
# `claude-sonnet-4.6` (dot notation) in the `model:` field, while
# Anthropic's canonical wire name is `claude-sonnet-4-6` (hyphenated).
# Without this rewrite, every request to api.anthropic.com/v1 returned
# 404 "model not found". The rewrite is IDEMPOTENT — if the upstream
# catalog has already been corrected at the pinned SHA, jq leaves the
# field untouched. We keep the step defensively so the image works
# regardless of which side of the upstream fix we're on.
RUN if [ -f /home/agent/.picoclaw/config.json ]; then \
      jq '(.model_list[]? | select(.model_name == "claude-sonnet-4.6") | .model) = "anthropic/claude-sonnet-4-6"' \
        /home/agent/.picoclaw/config.json > /tmp/pc.json && \
      mv /tmp/pc.json /home/agent/.picoclaw/config.json; \
    fi

# Pre-create the session-state dir as an empty mountpoint. The session
# handler mounts a tmpfs here at run time so picoclaw's session journal
# writes succeed under the read-only rootfs posture. (Mirrors Phase 2.)
RUN mkdir -p /home/agent/.picoclaw/workspace/sessions

# Restore root for the runtime entrypoint (ap-base entrypoint drops via gosu)
USER root
WORKDIR /home/agent

# AP_AGENT_CMD launches picoclaw in interactive mode in the tmux chat window.
# The ap-base entrypoint shim wraps stdin from /run/ap/chat.in and stdout to
# /run/ap/chat.out (ChatIOFIFO path). Kept verbatim from Phase 2.
ENV AP_AGENT_CMD="picoclaw agent --session cli:default"
