# ap-runtime-node — Phase 02.5 runtime base for Node recipes.
#
# Lock chain:
#   - FROM ap-base:v0.1.0 (Phase 2, Debian trixie + tini + tmux + ttyd + gosu)
#   - COPY --from node:22-slim (Debian-based, NOT Alpine — D-20 + Phase 2 D-04)
#   - Node 22 LTS is the current LTS line (active support through 2027)
#   - D-21: thin layer — language toolchain only
#
# Size target: <800 MB (D-23, planning guardrail)

FROM ap-base:v0.1.0

USER root

# Copy the node binary + npm/npx + node_modules from the official node:22-slim
# image. Using COPY --from avoids pulling Debian's node packages (they lag upstream
# by months) and avoids a separate apt download step that would inflate the layer.
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-slim /usr/local/include/node /usr/local/include/node
COPY --from=node:22-slim /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx && \
    ln -sf /usr/local/lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack && \
    mkdir -p /home/agent/.npm && \
    chown -R agent:agent /home/agent/.npm

# NOTE: do NOT set `USER agent` — container PID 1 must start as root
# so ap-base's entrypoint.sh Phase 1 can create /run/ap + /run/secrets
# before gosu-dropping to agent. Runner.Exec explicitly passes
# User: "agent" for hooks + chat exec, so agent semantics hold.
WORKDIR /home/agent

ENV NODE_VERSION=22 \
    NPM_CONFIG_CACHE=/home/agent/.npm \
    PATH=/home/agent/.local/bin:/usr/local/bin:$PATH

# No ENTRYPOINT / CMD — inherit from ap-base.
