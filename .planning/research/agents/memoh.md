---
name: memoh
real: true
source: https://github.com/memohai/Memoh
language: Go
license: AGPL-3.0
stars: 1500
last_commit: 2026-04-02
---

# Memoh

## L1 — Paper Recon

**Install mechanism:** binary release / docker (self-hosted server + containerd workspaces)

**Install command:**
```
# Not explicitly quoted in README excerpt — repo offers self-hosted binary + web UI
```

**Supported providers:** "Any OpenAI-compatible, Anthropic, or Google provider" with per-bot model assignment. Uses in-process **Twilight AI SDK** (custom Go SDK) for provider integration.

**Model-selection mechanism:** Per-bot model assignment via web UI ("Multi-Model: Any OpenAI-compatible, Anthropic, or Google provider"), persisted to Postgres.

**Auth mechanism (best guess from docs):** Provider OAuth flow + bot-level model config stored in Postgres. Injected to workspace containers via the gRPC bridge, not env vars at container start. **NEW auth mechanism for our matrix: `grpc_injected_at_runtime`** — key material never lives in the container's env or filesystem, it's requested on-demand by the workspace over UDS.

**Chat I/O shape:** **NEW mode — `grpc_uds`.** Workspace containers talk to the Memoh control plane over a gRPC bridge on a Unix Domain Socket mounted from host. This is neither FIFO nor HTTP gateway nor exec-per-message — it's a structured RPC bridge that's persistent for the container lifetime. Maps roughly to our `http_gateway` but with UDS + protobuf framing instead of HTTP.

**Persistent state needs:** containerd per-bot isolated containers with dedicated filesystem and network ("like having its own computer"). Backing store: Postgres + Qdrant (vector DB for memory). Workspace container has long-lived state.

**Notes from README (anything unusual for sandboxing):**
- **containerd directly, not Docker.** Different runtime — would require either running containerd alongside dockerd on the Hetzner box OR skipping Memoh-style recipes.
- **gRPC-over-UDS bridge** is a novel bridge mechanism we haven't seen elsewhere. Bind-mounting a UDS from host to container for control-plane comms is a cleaner sandbox model than exec-per-message (no `docker exec` at all after session start).
- **AGPL-3.0 is a meaningful license footprint** — any derivative or network-accessible fork of Memoh would have to ship source. Flags it as "copy patterns, don't copy code" for us.
- Vue 3 frontend (not Next.js) — can't transfer UI patterns directly.
- Architecture: REST API → In-process AI Agent → Tool Providers → gRPC (UDS) → containerized bots, backed by Postgres + Qdrant. Close to our planned architecture, but with the inversion that workspace containers pull from the control plane instead of the control plane pushing to them.
- Containerd per-bot collides with our one-container-per-session model — would need adaptation if used as a reference recipe.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
