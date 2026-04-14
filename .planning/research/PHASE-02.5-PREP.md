---
status: recon-complete-ready-for-phase-planning
last_updated: 2026-04-14
resume_anchor: true
read_first: true
next_command: "/gsd-insert-phase 02.5 \"Recipe Manifest Reshape\" --discuss"
purpose: |
  Resume-after-/clear anchor for Phase 02.5 planning. If you are a new
  Claude session opening this file, read this document FIRST, then the
  files listed under `## Read in this order`, then issue the command
  under `## Next command`. Everything needed to plan Phase 02.5 is
  captured here or linked from here. Nothing in chat context is required.
---

# Phase 02.5 — Recipe Manifest Reshape — PREP ANCHOR

This file is the handoff artifact between the recon phase (just completed) and Phase 02.5 planning (not yet started). Context from the recon session is too large to keep alive, so the full picture is persisted in Markdown across a small set of files.

## Status snapshot

| Layer | State | File |
|---|---|---|
| **Phase 2** | ✅ Complete (validated end-to-end with real LLM reply through hardened sandbox + BYOK + FIFO bridge + demux fix) | `.planning/phases/02-container-sandbox-spine/` |
| **Quick task: frontend import** | ✅ Complete (260414-mwo) | `.planning/quick/260414-mwo-import-v0-frontend-as-web-monorepo-membe/SUMMARY.md` |
| **Recon: L1 sweep (40 agents)** | ✅ Complete (Wave 1 + Wave 2) | `.planning/research/AGENT-MATRIX.md` |
| **Recon: schema prior art (12 projects)** | ✅ Complete (external research) | `.planning/research/SCHEMA-PRIOR-ART.md` |
| **Recipe schema draft** | ✅ Draft ready (10 worked reference recipes) | `.planning/research/RECIPE-SCHEMA-DRAFT.md` |
| **Phase 02.5 plan** | ❌ NOT STARTED (this is the next thing to do) | `.planning/phases/02.5-recipe-manifest-reshape/` (does not exist yet) |

## Decisions locked in (do not re-open without strong cause)

These were debated, decided, and persisted. New sessions should honor them unless there's specific new information.

1. **Claude Code: keep.** Shipped with `policy_flags: [non_oss, oauth_required_suppressed]`. Frontend filters non-OSS by default but users who want it get it. OAuth flow is blocked; `ANTHROPIC_API_KEY` is force-injected. License conflict with CLAUDE.md's OSS stance is accepted — the platform is OSS, the recipes are pluggable.
2. **Sysbox is the Tier-2 sandbox** for v1 nested-docker agents (hermes, moltis, nanoclaw, OpenHands GUI, HiClaw). NOT the final tier — Phase 8 adds gVisor/Firecracker as Tier 3-4 for untrusted bootstrap path. Tiered sandbox per CLAUDE.md roadmap.
3. **Dead agents stay in the matrix as historical context** but do NOT get recipes: gpt-engineer (→aider), SWE-agent (→mini-swe-agent), Cody (→Amp), smol-developer, mentat. Their replacements (mini-swe-agent, Amp) are live and get recipes in Phase 02.5 scope.
4. **Recipe count for Phase 02.5 v1 catalog: 10 worked reference recipes**, not 2-3. The 10 span every runtime family × every reachable chat_io mode × every healthy auth mechanism. These double as few-shot context for the Phase 8 bootstrap path.
5. **The monorepo reshape is frontend-forward.** Existing `web/` from Phase 01-03 stays for now. New `frontend/` is the v0 import with ported `lib/api.ts` / `middleware.ts` / `dev-login-form.tsx` / `next.config.mjs`. `web/` gets deleted during Phase 3 after the new tree is verified.
6. **L2 is lazy, not upfront.** We don't spend 3-4 hours running `pip install` across 15 agents before planning. Instead, each recipe in Phase 02.5 has a "verify install path" task inside its plan — ground-truthing happens during implementation, one recipe at a time. L3 (real LLM round-trip) is the hard acceptance gate per recipe.
7. **5 runtime base images, not 1 per agent.** `ap-runtime-node`, `ap-runtime-python`, `ap-runtime-go`, `ap-runtime-rust`, `ap-runtime-zig`. Agents install at `postCreateCommand` runtime hook time. Hermes drops from 5.54 GB → ~1.2 GB as a side effect.
8. **Schema is forked from 5 battle-tested prior arts** (Daytona runtime, Dev Containers lifecycle + security, MCP launch + stdio, Praktor auth + vault, Plandex providers/models, Coder frontend metadata, OpenHands runtime backend enum). NOT invented. See `RECIPE-SCHEMA-DRAFT.md` for the full provenance table.
9. **Phase 02.5 must design for LLM-writability.** If Claude Sonnet can't emit a valid recipe from just the schema + 5 few-shot examples, Agent Playground's "unknown agent bootstrap" differentiator fails. Every schema decision is tested against this.

## Read in this order (after /clear)

A new session should read these files in this exact order. Total is ~4500 lines, ~60 KB — large but one-pass.

1. **`.planning/research/PHASE-02.5-PREP.md`** (this file) — top-level anchor.
2. **`.planning/STATE.md`** — project-wide state, milestone progress, Phase 2 outcomes, current focus.
3. **`.planning/PROJECT.md`** — core value, constraints, tech stack, open questions.
4. **`./CLAUDE.md`** — project instructions, stack decisions, anti-patterns.
5. **`.planning/research/AGENT-MATRIX.md`** — the 40-agent L1 sweep findings (primary input to Phase 02.5).
6. **`.planning/research/SCHEMA-PRIOR-ART.md`** — external research on 12 schema projects; the "what to steal" guide.
7. **`.planning/research/RECIPE-SCHEMA-DRAFT.md`** — the actual schema draft + 10 worked reference recipes + JSON Schema outline + LLM writability test plan. **This is the primary artifact Phase 02.5 planning consumes.**
8. **`.planning/research/agents/praktor.md`** — the #1 prior art for our schema. The YAML we forked from.
9. **`.planning/research/agents/memoh.md`** — #2 prior art, grpc_uds mode discovery.
10. **`.planning/phases/02-container-sandbox-spine/02-CONTEXT.md`** — what Phase 2 actually delivered vs planned, so Phase 02.5 knows where it's starting from.

Everything else in `.planning/research/agents/*.md` (40 files total) is reference data; read a specific agent's file only if Phase 02.5 planning needs its details.

## Next command (to continue the plan)

```
/gsd-insert-phase 02.5 "Recipe Manifest Reshape" --discuss
```

This inserts a decimal phase 02.5 between Phase 2 (just completed) and Phase 3 (auth/BYOK/vault), then runs discuss-phase to surface any gray areas before planning. The discuss step takes `RECIPE-SCHEMA-DRAFT.md` as its primary reference — its job is NOT to redesign the schema but to catch decisions we haven't thought about yet.

**If you are running this fresh and unsure whether `/gsd-insert-phase` is the right command**, first run `/gsd-progress` to see where the project is — it will confirm Phase 2 is complete and suggest Phase 02.5 insertion as the next logical step.

## Phase 02.5 proposed scope (input to the discuss step)

This is the scope I intend to propose to `/gsd-insert-phase`. Discuss may refine it.

### Must-have deliverables

1. **Schema + validation**
   - Finalize `recipe.yaml` schema from the draft
   - Write `schemas/recipe.schema.json` (Draft 2019-09, full, not just outline)
   - Wire client-side + server-side validation in the Go orchestrator
   - LLM writability test against mini-swe-agent (blind) — passes = schema locked

2. **Runtime substrate**
   - `ap-runtime-node` base image (replaces the node portion of current ap-picoclaw)
   - `ap-runtime-python` base image (replaces the python portion of current ap-hermes)
   - `ap-runtime-go`, `ap-runtime-rust`, `ap-runtime-zig` stub images (minimal, just the toolchain + tini + gosu + tmux + ttyd)
   - Old `ap-picoclaw:v0.1.0-c7461f9` and `ap-hermes:v0.1.0-5621fc4` images DELETED from Makefile

3. **Orchestrator changes in `api/internal/session/`**
   - Replace `recipes.AllRecipes` hardcoded map with a YAML loader reading `agents/<id>/recipe.yaml`
   - Replace `recipes.AgentAuthFiles` + `Render` closures with Praktor-shape `files: [{secret, target, mode, template}]` + Go template registry
   - Implement the 6 Dev Containers lifecycle hooks in `runner.go` (`RunWithLifecycle`)
   - Extend chat bridge to support ALL 7 chat_io modes (we have fifo + exec_per_message from Phase 2; add one_shot_task, http_gateway, json_rpc_stdio, terminal_only, grpc_uds stub)
   - Implement vault: Praktor-style `secret:<name>` resolver in `session.SecretSource`

4. **10 reference recipes**
   - Migrate picoclaw + hermes to new format (preserving Phase 2 acceptance tests)
   - Write 8 more recipes: openclaw, aider, plandex, hiclaw, auto-code-rover, nullclaw, ironclaw, claude-code
   - L3 round-trip each one against a real LLM (minimum: 1 model per recipe, preferably 2)

5. **Frontend contract**
   - `GET /api/recipes` endpoint exposes a filtered view (public metadata only)
   - Frontend's hardcoded `ClawClone` catalog replaced with fetch from `/api/recipes`
   - Isolation tier + OSS filter toggles on the catalog page

6. **`web/` deletion**
   - After Phase 3 lands auth and the frontend cutover is verified, `git rm -rf web/`
   - Tracked separately from Phase 02.5 in Phase 3 scope

### Explicit non-goals for Phase 02.5

- **No bootstrap path.** That's Phase 8. Phase 02.5 just ensures the schema CAN support it.
- **No Sysbox install.** That's Phase 7.5. Phase 02.5 recipes that need Sysbox declare `isolation.tier: sysbox` but won't run until Phase 7.5 ships.
- **No GATEWAY-only recipes L3-tested.** Cody/Amp/gh-copilot/Cursor CLI are schema-documented but skipped for L3 — they require vendor gateway accounts we don't have.
- **No content-addressable recipe hashing.** Phase 8 bootstrap path requires it; Phase 02.5 uses simple file-path addressing.

## Assumptions-analyzer watchlist (for discuss-phase)

Things I'm assuming that a `gsd-assumptions-analyzer` should challenge:

1. **"LLM-writability test passes on first try."** If it doesn't, the schema needs simplification — which may require cutting fields. Phase 02.5 scope may shrink.
2. **"5 runtime base images are enough."** What if an agent needs a language not in {node, python, go, rust, zig}? Elixir, Haskell, .NET, JVM? Probably rare in the agent ecosystem but worth a pre-check.
3. **"Dev Containers 6-hook lifecycle matches what agents need."** We didn't L2-verify any of the 10 reference recipes. Some may need hooks we don't have.
4. **"Praktor's `secret_file_mount` covers all auth cases."** It covers picoclaw, hermes, openclaw. Does it cover Memoh's grpc_uds at-runtime injection? Probably not — grpc_uds is listed but we have no recipe for it.
5. **"We have enough recon."** Tempting to keep sweeping. Discuss may confirm we're over-researched, or may flag 2-3 specific agents we should L1 before planning (e.g., Void's CLI existence, Amp's exact auth mechanism, Memoh's gRPC schema).

## Tokens / session budget

This recon phase burned a lot of context. Everything is persisted above. **A fresh `/clear`-ed session can pick up Phase 02.5 planning with ~15% context utilization** after reading the 10 files under "Read in this order", vs the >70% the current session is at.

The single biggest thing that made this work: **writing RECIPE-SCHEMA-DRAFT.md with 10 inline worked recipes before clearing.** Those recipes are the actual thing Phase 02.5 will verify and migrate — they're not a design exercise, they're a migration manifest.

---

## If you read this and something is missing

If a fresh session opens this file and discovers a gap — "I need X to plan Phase 02.5 but it's not captured anywhere" — the correct response is to ADD it to this file, commit, and THEN continue. This is the handoff artifact; it gets richer as we discover new needs, not thinner.

The single command to continue: **`/gsd-insert-phase 02.5 "Recipe Manifest Reshape" --discuss`**
