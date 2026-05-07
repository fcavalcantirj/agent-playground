# syntax=docker/dockerfile:1.4
# Custom Dockerfile for ap-recipe-goose:latest.
#
# Upstream block/goose ships docker/Dockerfile, but it ONLY builds the
# goose-cli binary (`cargo build --release --package goose-cli`). The HTTP
# daemon binary `goosed` lives in a separate crate (`goose-server`) and is
# NOT compiled by upstream's image — the desktop app links to a locally-
# built copy at dev time.
#
# AP needs the goosed HTTP+SSE surface (POST /reply with the ChatRequest /
# MessageEvent shape) to deploy goose as an inapp recipe. So this Dockerfile:
#
#   1. Builds BOTH goose-cli and goose-server in the cargo step.
#   2. Copies BOTH `goose` and `goosed` to /usr/local/bin.
#   3. Runs as root (the entrypoint sh-chain in the recipe needs to write
#      ~/.config/goose/config.yaml; running as the upstream `goose` user
#      adds friction without security gain inside the AP-isolated container).
#   4. ENTRYPOINT is left unset so the recipe's persistent_argv_override
#      can supply `sh -c '<heredoc>; exec goosed agent'`.
#
# Build context is the upstream block/goose source clone at /tmp/goose.
# Build command (one-time, local):
#
#   docker build -t ap-recipe-goose:latest \
#     -f /Users/fcavalcanti/dev/agent-playground/tools/dockerfiles/goose.Dockerfile \
#     /tmp/goose
#
# Once the image exists locally, the recipe's build.mode=image_pull short-
# circuits via the runner's image_exists() early-exit (run_recipe.py:644).

FROM rust:1.82-bookworm AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    libssl-dev \
    libdbus-1-dev \
    libclang-dev \
    protobuf-compiler \
    libprotobuf-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY . .

ENV CARGO_REGISTRIES_CRATES_IO_PROTOCOL=sparse
# Faster spike builds: skip LTO + use parallel codegen + opt-level 3 instead
# of size-optimized. Rebuilding for prod can re-enable LTO/strip later.
ENV CARGO_PROFILE_RELEASE_LTO=false
ENV CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16
ENV CARGO_PROFILE_RELEASE_OPT_LEVEL=3
ENV CARGO_PROFILE_RELEASE_STRIP=false

RUN cargo build --release \
    --package goose-cli \
    --package goose-server

# Runtime stage
FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl3 \
    libdbus-1-3 \
    libgomp1 \
    libxcb1 \
    curl \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/target/release/goose /usr/local/bin/goose
COPY --from=builder /build/target/release/goosed /usr/local/bin/goosed

ENV PATH="/usr/local/bin:${PATH}"
ENV HOME="/root"
WORKDIR /root
RUN mkdir -p /root/.config/goose /root/.local/share/goose

# No ENTRYPOINT — recipe's persistent_argv_override sets sh + heredoc.

LABEL org.opencontainers.image.title="ap-recipe-goose"
LABEL org.opencontainers.image.description="goose CLI + goosed HTTP daemon for Agent Playground"
LABEL org.opencontainers.image.source="https://github.com/block/goose"
