# ap-runtime-python — Phase 02.5 runtime base for Python recipes.
#
# Lock chain:
#   - FROM ap-base:v0.1.0 (Phase 2, Debian trixie + tini + tmux + ttyd + gosu)
#   - COPY --from ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie
#   - D-19: Python 3.13 + uv; pip is forbidden in python recipes (loader translates pip → uv pip)
#   - D-21: thin layer — language toolchain only, no other tooling
#   - D-22: recipe overlays FROM this image, never from ap-base directly
#
# Size target: <1.5 GB (D-23, planning guardrail not hard gate)

FROM ap-base:v0.1.0

USER root

# Astral's uv image bundles uv + python3.13 + stdlib on Debian trixie. COPY --from
# pulls them deterministically — no apt pin dance, no cache pollution.
COPY --from=ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie /usr/local/bin/uv /usr/local/bin/uv
COPY --from=ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie /usr/local/bin/uvx /usr/local/bin/uvx
COPY --from=ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie /usr/local/bin/python3.13 /usr/local/bin/python3.13
COPY --from=ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie /usr/local/lib/python3.13 /usr/local/lib/python3.13
# [Rule 1/3 auto-fix] python3.13 is dynamically linked against libpython3.13.so.1.0
# which lives at /usr/local/lib/libpython3.13.so.1.0 in the Astral uv image (NOT
# inside /usr/local/lib/python3.13/). Without this COPY, `python3 --version` fails
# with: "error while loading shared libraries: libpython3.13.so.1.0: cannot open
# shared object file". The plan sketch omitted this file; acceptance verify would
# have caught it at the human-verify checkpoint.
COPY --from=ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie /usr/local/lib/libpython3.13.so.1.0 /usr/local/lib/libpython3.13.so.1.0

# Make python3 / python resolve to 3.13, ensure agent user owns its cache dir.
RUN ln -sf /usr/local/bin/python3.13 /usr/local/bin/python3 && \
    ln -sf /usr/local/bin/python3.13 /usr/local/bin/python && \
    mkdir -p /home/agent/.cache /home/agent/.local/bin && \
    chown -R agent:agent /home/agent/.cache /home/agent/.local

# NOTE: do NOT set `USER agent` — the container's PID 1 must start as
# root so ap-base's entrypoint.sh Phase 1 can create /run/ap and
# /run/secrets on the tmpfs before gosu-dropping to `agent` for Phase 2.
# Runner.Exec explicitly passes User: "agent" for postCreate hooks and
# per-message chat exec, so runtime commands still run as agent.
WORKDIR /home/agent

ENV PYTHON_VERSION=3.13 \
    UV_LINK_MODE=copy \
    UV_SYSTEM_PYTHON=1 \
    PATH=/home/agent/.local/bin:/usr/local/bin:$PATH

# No ENTRYPOINT / CMD — ap-base provides tini + entrypoint shim. Inherit unchanged.
