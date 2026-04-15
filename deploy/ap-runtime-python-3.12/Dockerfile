# ap-runtime-python (3.12 variant) — Phase 02.5 Plan 07 fallback base image.
#
# Why this exists:
#   aider-chat 0.86.2 declares `requires_python: <3.13,>=3.10` AND hard-pins
#   numpy==1.26.4 (no cp313 wheel). Installing aider-chat into the primary
#   ap-runtime-python:v0.1.0-3.13 base fails because:
#     (a) pip/uv refuses the package due to requires_python, OR
#     (b) numpy 1.26.4 falls back to sdist and fails to compile without gcc.
#
#   Per Plan 02.5-07 fallback instructions ("If A3 fails"), the aider recipe
#   is pinned to runtime.version=3.12 + runtime.image=ap-runtime-python:v0.1.0-3.12
#   while the primary 3.13 base image stays in place for future recipes.
#
#   This Dockerfile is a byte-for-byte copy of deploy/ap-runtime-python/Dockerfile
#   with all "3.13" token substitutions swapped to "3.12". If Plan 06 is
#   eventually re-issued to mint a second Python base, this file is the
#   canonical source it should consume.
#
# Lock chain:
#   - FROM ap-base:v0.1.0 (Phase 2)
#   - COPY --from ghcr.io/astral-sh/uv:0.11.6-python3.12-trixie

FROM ap-base:v0.1.0

USER root

COPY --from=ghcr.io/astral-sh/uv:0.11.6-python3.12-trixie /usr/local/bin/uv /usr/local/bin/uv
COPY --from=ghcr.io/astral-sh/uv:0.11.6-python3.12-trixie /usr/local/bin/uvx /usr/local/bin/uvx
COPY --from=ghcr.io/astral-sh/uv:0.11.6-python3.12-trixie /usr/local/bin/python3.12 /usr/local/bin/python3.12
COPY --from=ghcr.io/astral-sh/uv:0.11.6-python3.12-trixie /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=ghcr.io/astral-sh/uv:0.11.6-python3.12-trixie /usr/local/lib/libpython3.12.so.1.0 /usr/local/lib/libpython3.12.so.1.0

RUN ln -sf /usr/local/bin/python3.12 /usr/local/bin/python3 && \
    ln -sf /usr/local/bin/python3.12 /usr/local/bin/python && \
    mkdir -p /home/agent/.cache /home/agent/.local/bin && \
    chown -R agent:agent /home/agent/.cache /home/agent/.local

USER agent
WORKDIR /home/agent

ENV PYTHON_VERSION=3.12 \
    UV_LINK_MODE=copy \
    UV_SYSTEM_PYTHON=1 \
    PATH=/home/agent/.local/bin:/usr/local/bin:$PATH

# No ENTRYPOINT / CMD — ap-base provides tini + entrypoint shim. Inherit unchanged.
