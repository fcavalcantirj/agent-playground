# Phase 2: Container Sandbox Spine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-13
**Phase:** 02-container-sandbox-spine
**Areas discussed:** Phase scope reshape, smoke-test agent selection, stub API placement, Hermes architecture research

---

## Phase scope reshape (hypothesis-forward vs hardening-first)

The discussion opened with Claude presenting four gray areas for the original ROADMAP scope of Phase 2 (hardening + image shape, egress allowlist, anomaly detection + escape tests, gVisor/Spike 4 handling).

**User response to the gray-areas question:** *"dude, what we gain from tjis? how are we closer to proving hypothesis?"*

Claude acknowledged the challenge and offered three reframing options:

| Option | Description | Selected |
|---|---|---|
| Slim Phase 2 to hypothesis-critical only | Ship ap-base + naming + basic cap-drop; defer Falco / egress / escape tests / gVisor to Phase 2.5 or fold into Phase 8 | |
| Keep Phase 2 as-is | Full security spine now; slower to demo but "when you demo, it's sandboxed" | |
| Split Phase 2 into 2a (image + naming) and 2b (hardening spine, defer until after Phase 5 demo) | Vertical slice first, harden before opening to users | ✓ (refined further) |

**User's counter:** *"Well, if you think it won't be work lost, we can do it, but we haven't tested a single agent, right? How can we test the combination before making it allowed to be used by the web, which is what tmux is doing as is?"*

This deepened the reshape: the user identified that tmux+ttyd exists to expose the container to the browser, and you cannot validate "the web-facing surface" before validating "the agent in the box". The correct order is agent-in-a-box first, then web exposure. This moved the reshape from "slim hardening" to "prove the agent runs under API control".

Claude proposed a reshape where Phase 2 becomes an agent install spike + minimal ap-base, and challenged the user on whether "we've never run an agent" was strictly true.

**User's counter-counter:** *"Well, we already know we can dockerize a pickle claw, right? We already proved this with the msv, right? And you also have the code to check, right?"*

Claude checked MSV and confirmed: `meusecretariovirtual/infra/picoclaw/Dockerfile` runs `npm install -g openclaw@latest` and exposes a gateway WS on port 18789. MSV proves agent-in-a-container works in production. No agent-run spike is needed. Phase 2 is about substrate + API wiring, not feasibility.

A second reshape was presented with a lock-in question:

| Option | Description | Selected |
|---|---|---|
| Yes, lock in the reshape | ap-base (tini+tmux+ttyd, MSV entrypoint ported), runner.go sandbox options wired, deterministic naming, picoclaw smoke test via ap-base. Hardening deferred | |
| Reshape but keep some hardening in P2 | Same as above, plus one or two specific non-deferrable items | |
| Keep Phase 2 as originally scoped | Full security spine; slower to demo | |

**User's answer:** *"The security hardening defers to a later phase. What I think we would benefit from now is proving that we can, via API, start an agent even without the need for the Telegram like msv does. What do you think? I also have you check on the different architecture needs for Hermes, which is totally different than OpenClaw related."*

This selected the reshape with two explicit amplifications:
1. Phase 2 must prove *API-driven* start, not just runner.go-driven start. The session HTTP endpoints must land in Phase 2.
2. Hermes's architecture must be surveyed so Phase 2's substrate design is forward-compatible with it, not just picoclaw.

Claude searched for Hermes, found `github.com/NousResearch/hermes-agent` (Nous Research, Python 3.11, MIT, TUI-first, six execution backends, built-in multi-channel daemon). The architecture differs from OpenClaw along every axis: runtime (Python vs Node), chat surface (PTY TUI vs gateway WebSocket), multi-platform (built-in daemon for Telegram/Discord/Slack/WhatsApp/Signal/SMS/Email/Matrix/Mattermost vs device-pairing into a gateway), execution (six backends including Docker/SSH/Singularity/Modal — nested-container hazard), state (persistent FTS5 memory vs stateless).

Four concrete implications were surfaced:
- tmux + ttyd must be in `ap-base` from day 1 (Hermes needs PTY; FIFO pipes break readline)
- Recipe schema needs a third `chat_io.mode = pty_tui`
- Recipe must force `backend: local` to prevent nested-container hazards
- Recipe must disable built-in multi-channel daemons via config

**User's answer to "which agents to validate end-to-end":** *"picoclaw and https://hermes-agent.nousresearch.com/ - but this list will grow."*

| Option | Description | Selected |
|---|---|---|
| picoclaw only | One agent, cli-stdio, fastest to demo | |
| picoclaw + openclaw-npm | Two agents covering stdin_fifo + gateway_ws | |
| picoclaw + openclaw + hermes | All three chat_io modes | (modified) |

The user's actual choice was **picoclaw + Hermes** (skipping OpenClaw), with the explicit signal *"this list will grow"*. Interpretation: OpenClaw's gateway-WS path is covered by MSV's production deployment; Hermes is chosen precisely because it's the architecturally hardest agent and proving it works validates the substrate for the long tail.

**User's answer to "session API in Phase 2 or defer to Phase 5":**

| Option | Description | Selected |
|---|---|---|
| Land stub endpoints in Phase 2 | Non-durable API now; Phase 5 replaces internals with Temporal, same HTTP contract | ✓ |
| Keep API in Phase 5, Phase 2 uses Go test harness | Smaller Phase 2 scope but "API-driven" goal only partially proven | |

**User's choice:** Land stub endpoints in Phase 2. Recommended default accepted.

## Hermes architecture research

Claude performed two web fetches:
1. `hermes-agent.nousresearch.com` — marketing page. Only surface-level info extracted (install command, MIT license, supported platforms).
2. `github.com/NousResearch/hermes-agent` — README and repo metadata. Extracted: Python 3.11 baseline, `uv pip install -e ".[all,dev]"`, config dir `~/.hermes/`, `cli-config.yaml.example` template file, `hermes` / `hermes gateway` entrypoints, `hermes setup` interactive wizard, six execution backends (local, Docker, SSH, Daytona, Singularity, Modal), `mcp_serve.py` for Model Context Protocol support, FTS5 for session search.

Gaps flagged as Phase 2 planning research items:
- Exact YAML key to disable channel daemons in `cli-config.yaml`
- Exact YAML key to force `backend: local`
- Whether MCP interface supports browser-style message exchange
- Whether `hermes` CLI has a `--message` non-interactive flag

## Claude's Discretion

Areas where the user left decisions to Claude / planning:
- Base OS choice for `ap-base` (Claude picked Debian slim — matches MSV, Hermes Python dependency)
- Exact Dockerfile layering strategy
- Default resource limits (1GB / 1 vCPU / 256 PIDs — revisable by planning if Hermes starves)
- Chat bridge mechanism for Hermes (PTY vs MCP vs `--message` CLI flag — planning research decides)
- Commit SHAs to pin picoclaw and Hermes to
- Error response shapes for new HTTP endpoints
- Go package naming (`internal/recipes`, `internal/session`, etc.)

## Deferred Ideas

- OpenClaw recipe (covered by MSV proof; belongs in Phase 4 recipe expansion)
- Custom seccomp JSON authoring
- `ap-net` bridge + egress allowlist
- Falco or Tetragon + escape-test CI
- gVisor `runsc` install (Spike 4 still pending)
- `ap.recipe/v1` YAML schema + loader (Phase 4)
- Temporal-backed session lifecycle (Phase 5)
- Chat WS, terminal WS, reconciliation loop, idle reaper, heartbeat (Phase 5)
- BYOK encrypted vault + settings UI (Phase 3)
- Paid-tier persistent Hermes memory volume (Phase 7)
- ROADMAP.md update to reflect the reshape
