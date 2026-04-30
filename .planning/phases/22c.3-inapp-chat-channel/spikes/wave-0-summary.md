# Wave 0 spike summary — 22c.3 inapp re-probe

**Date:** 2026-04-30
**Operator:** Plan 22c.3-01 executor (Claude Opus 4.7 / 1M context, sequential mode)
**Phase:** 22c.3-inapp-chat-channel — Wave 0 close-out gate

## Matrix

| Recipe   | Endpoint                          | Contract          | Verification |
|----------|-----------------------------------|-------------------|--------------|
| hermes   | port 8642, /v1/chat/completions   | openai_compat     | PASS — see spikes/recipe-hermes.md (real OpenRouter call, 163-char persona-correct reply) |
| nanobot  | port 8900, /v1/chat/completions   | openai_compat     | PASS — see spikes/recipe-nanobot.md (real OpenRouter call, 90-char persona-correct reply) |
| openclaw | port 18789, /v1/chat/completions  | openai_compat     | PASS — see spikes/recipe-openclaw.md (contract shape PASS — OpenAI envelope intact, choices[0].message.content populated; content surfaced an upstream Anthropic billing error from zero-credit probe-time key, faithfully relayed by the bot per dumb-pipe D-22) |
| nullclaw | port 3000, /a2a                   | a2a_jsonrpc       | PASS — see spikes/recipe-nullclaw.md (revised v3 native A2A; real OpenRouter call, state=completed, 102-char reply at result.artifacts[0].parts[0].text; agent-card.json shows protocolVersion=0.3.0) |
| zeroclaw | port 42617, /webhook              | zeroclaw_native   | PASS — see spikes/recipe-zeroclaw.md (Round-3 substitution for picoclaw; real OpenRouter call, 100-char persona-correct reply at body.response with model field; X-Idempotency-Key replay returns {idempotent:true,status:"duplicate"}) |

picoclaw — DEFERRED per RESEARCH §Revision Notice Round 3 (user direction 2026-04-30). No spike in this plan. `recipes/picoclaw.yaml` UNTOUCHED.

## Round-3 deltas vs prior waves

- **nullclaw** moved from openai-compat-via-sidecar (Round-2 v2 spike, port 18791, runtime package install + HTTP-to-CLI bridge) to NATIVE `/a2a` JSON-RPC 2.0 (`a2a_jsonrpc` contract, port 3000) — uses nullclaw's built-in Google A2A protocol via `a2a.enabled=true` in config.json + `gateway.require_pairing=false`. Sidecar pattern fully dropped per Round-3 supersession.
- **picoclaw** deferred → **zeroclaw** substituted (`zeroclaw_native` contract). `ghcr.io/zeroclaw-labs/zeroclaw:latest` is the highest-starred (30,845 ★) clawclones.com agent we don't yet have; built-in idempotency + session headers + WS streaming are batteries-included.
- **3 contract adapters** required in dispatcher (Plan 22c.3-05): `openai_compat` / `a2a_jsonrpc` / `zeroclaw_native`. All three empirically validated in this Wave 0 against `ap-recipe-*:latest` images (and `ghcr.io/zeroclaw-labs/zeroclaw:latest` for zeroclaw).

## Gate

WAVE-0-CLOSED: 5/5 recipes PASS their probes against the current ap-recipe-* images.

Plans 22c.3-{02..15} unblocked.

If any recipe FAILS its probe, this gate is OPEN and Plans 22c.3-{02..15} stay BLOCKED until the failure is investigated and the spike re-runs PASS.

## Cross-references

- Plan `22c.3-05-PLAN.md` (dispatcher) consumes the 3 contract shapes — `openai_compat` / `a2a_jsonrpc` / `zeroclaw_native` — empirically validated in this gate.
- Plans `22c.3-{10,11,12,14,13}-PLAN.md` (recipe modifications for hermes/nanobot/openclaw/nullclaw/zeroclaw) consume the per-recipe `channels.inapp` shape proposed in each spike file.
- Plan `22c.3-15-PLAN.md` (5/5 e2e gate) re-runs every probe via `pytest tests/e2e/test_inapp_5x5_matrix.py` after the dispatcher and recipe blocks land.

## Operator notes (probe-time environment)

- `OPENROUTER_API_KEY` sourced from `/Users/fcavalcanti/dev/agent-playground/.env.local` at probe time. Real LLM calls billed against the developer's OpenRouter credit balance.
- `ANTHROPIC_API_KEY` (used in openclaw probe per `recipes/openclaw.yaml::provider_compat.supported=[anthropic]`) had zero credit at probe time; the contract-shape verdict is unaffected (HTTP 200 + OpenAI envelope intact + content populated with upstream error string per dumb-pipe D-22). Independently confirmed against `https://api.anthropic.com/v1/messages` — same `invalid_request_error / credit balance is too low` response.
- All 5 spike containers were `docker rm -f`'d at the end of each probe; `w0-zero-data` volume removed.
- All probes ran on the developer's local Docker Desktop (darwin 25.3.0 arm64); no remote infra used.
