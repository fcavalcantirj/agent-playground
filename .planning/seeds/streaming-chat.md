---
title: Streaming chat — additive upgrade after Mobile MVP lands
trigger_condition: |
  After Mobile MVP milestone ships AND any of:
  - Block-and-wait chat latency exceeds ~3s typical and feels janky in real use
  - Demo audience comments specifically on the lack of streaming
  - We start using a model where typical first-token-latency makes the wait feel broken
planted_date: 2026-05-01
parent_milestone: mobile-mvp
status: planted
---

# Streaming chat (deferred during MVP, additive)

## Why this is a seed, not a phase

Surfaced during the `/gsd-explore` session for the Mobile MVP milestone. We chose
**block-and-wait** chat for MVP because:

- The five agents we ship all run OpenAI-compatible servers that already support `stream: true`, so the work is purely on **our** proxy, not on agents.
- Block-and-wait is ~80 LOC of proxy. Streaming is ~150 LOC + Flutter widget rework.
- "Code we'll reuse" rule: the upgrade path is **additive**, not a rewrite — see below.
- We don't have demo evidence yet that latency is the limiting factor for "feels real."

## Concrete scope when triggered

**Backend (~70 LOC additional on top of MVP proxy):**

1. New endpoint variant: `POST /v1/agents/:id/chat?stream=true` returning Server-Sent Events.
   - Forwards downstream with `stream: true` to the agent container's `/v1/chat/completions`.
   - Pipes `data: {chunk}` SSE events back to the mobile client as they arrive.
   - Accumulates the full assistant message in a buffer.
   - On stream close, INSERTs both user-row + assistant-row into `messages` table (same schema as MVP).
2. The original block-and-wait `POST /v1/agents/:id/chat` (no `?stream`) continues to work — coexists with the streaming variant. **No removal, no rename, no breaking change.**

**Flutter:**

1. Replace the `await client.chat(...)` call site in the Chat screen with a stream subscription.
2. Append chunks to the in-progress assistant message bubble as they arrive.
3. On stream close, mark the bubble final and refresh the messages list (or trust the local buffer).
4. Keep the block-and-wait path as a fallback flag (or just delete it if the streaming path proves stable).

## Why this is genuinely additive

- **Same endpoint shape, query-param toggle** — `?stream=true` vs. omitted. No URL versioning needed.
- **Same persistence point** — both paths write to `messages` table at the same logical moment (after the agent finishes responding).
- **Same auth** — passes through the same `Depends(current_user_id)` middleware.
- **Same tests** — block-and-wait integration test stays; add a streaming integration test alongside it.
- **No client lock-in** — Flutter can choose per-call which mode to use (e.g. streaming for chat, block-and-wait for any future bulk operation).

If at trigger time the design has drifted and this seed needs revising, that's fine —
the seed is a starting point, not a contract.

## Anti-scope (what NOT to do when this triggers)

- **Don't switch to WebSocket.** SSE is simpler, server-push, fits HTTP semantics. WebSocket only makes sense if/when we need bidirectional streaming (server pushes notifications to client without a request) — that's a different problem.
- **Don't introduce a message broker** (Redis pub/sub, RabbitMQ, etc.) for this. The proxy is one process, one response. Direct SSE forwarding is enough.
- **Don't turn this into a rewrite of the chat endpoint.** Add a variant; don't replace.
- **Don't bundle this with other improvements** (typing indicators, read receipts, retry logic). Those are separate seeds if/when needed.

## Sources

- `/gsd-explore` session, 2026-05-01 (decision to defer streaming for MVP)
- `notes/mobile-mvp-decisions.md` — Rule 1 ("code we'll reuse") and the streaming opt-out reasoning
- Phase 22c.3.1 — proves the agent containers respond to `/v1/chat/completions` (the upstream we'd be streaming from)
