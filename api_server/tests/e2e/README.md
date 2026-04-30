# Phase 22c.3 SC-03 — In-app chat 5-cell e2e gate

This directory contains the canonical phase-exit gate for Phase 22c.3
(in-app chat channel). The gate proves that the inapp dispatcher's
3-way contract switch — `openai_compat`, `a2a_jsonrpc`,
`zeroclaw_native` — completes a real round-trip against all 5
inapp-opted-in recipes, talking to real OpenRouter.

## What the gate proves

For each of the 5 inapp recipes (hermes, nanobot, openclaw, nullclaw,
zeroclaw), the matrix test:

1. Spawns a real Docker container from `ap-recipe-<name>:latest` on a
   dedicated bridge network.
2. Renders the recipe's `channels.inapp.persistent_argv_override` and
   `activation_env` blocks (`${MODEL}`, `${INAPP_AUTH_TOKEN}`,
   `${OPENROUTER_API_KEY}`, `{agent_name}`, `{agent_url}`).
3. Mints a per-session `INAPP_AUTH_TOKEN`, persists it to
   `agent_containers.inapp_auth_token`.
4. Drives the production dispatcher's `_handle_row` with a real
   `httpx.AsyncClient` — same code path the live dispatcher loop runs.
5. Asserts: `inapp_messages.status='done'`, non-empty `bot_response`,
   `agent_events` row with `kind='inapp_outbound'`, latency under
   D-40's 600s budget per cell.
6. Writes a per-cell PASS/FAIL entry to `e2e-report.json`.

If any cell fails the JSON's `passed=false` and the test re-raises so
CI fails loud.

## SC-01..SC-06 acceptance map

| Criterion | How the gate satisfies it |
| --- | --- |
| SC-01 | dispatcher dispatches across 3 contracts | covered by openai_compat ×3, a2a_jsonrpc ×1, zeroclaw_native ×1 in one run |
| SC-02 | persist-before-action (D-28) | each cell asserts the agent_events row is written transactionally with mark_done |
| SC-03 | 5/5 PASS in e2e-report.json | 5-cell matrix; report on disk after every run |
| SC-04 | OpenRouter creds round-trip via OAuth (D-32) | `oauth_user_with_openrouter_key` fixture inserts the key into a real DB row + injects it as `OPENROUTER_API_KEY` env |
| SC-05 | no mocks, no stubs | real Postgres (testcontainers), real Docker, real OpenRouter HTTP |
| SC-06 | re-run idempotent | TRUNCATE between tests + container/network teardown on session end |

## Required env

- `OPENROUTER_API_KEY` (sourced from env or `.env.local` at repo root) —
  the gate needs a funded OpenRouter key to make real model calls. The
  per-cell call costs <0.001 USD against `anthropic/claude-haiku-4.5`.

## Required local images

The gate expects these images to be present locally:

  - `ap-recipe-hermes:latest`
  - `ap-recipe-nanobot:latest`
  - `ap-recipe-openclaw:latest`
  - `ap-recipe-nullclaw:latest`
  - `ap-recipe-zeroclaw:latest`

Build/pull via `tools/run_recipe.py` first — the gate refuses to start
without all 5.

## One-liner

```bash
cd api_server
make e2e-inapp
```

Expected on PASS:

```
tests/e2e/test_inapp_5x5_matrix.py::test_recipe_inapp_round_trip[hermes] PASSED
tests/e2e/test_inapp_5x5_matrix.py::test_recipe_inapp_round_trip[nanobot] PASSED
tests/e2e/test_inapp_5x5_matrix.py::test_recipe_inapp_round_trip[openclaw] PASSED
tests/e2e/test_inapp_5x5_matrix.py::test_recipe_inapp_round_trip[nullclaw] PASSED
tests/e2e/test_inapp_5x5_matrix.py::test_recipe_inapp_round_trip[zeroclaw] PASSED
GATE PASS — 5/5 cells
```

## 5-cell matrix

| Recipe   | Endpoint                        | Contract          | Provider   | Model                          |
|----------|---------------------------------|-------------------|------------|--------------------------------|
| hermes   | port 8642, /v1/chat/completions | openai_compat     | openrouter | anthropic/claude-haiku-4.5     |
| nanobot  | port 8900, /v1/chat/completions | openai_compat     | openrouter | anthropic/claude-haiku-4.5     |
| openclaw | port 18789, /v1/chat/completions| openai_compat     | openrouter | anthropic/claude-haiku-4-5     |
| nullclaw | port 3000, /a2a                 | a2a_jsonrpc       | openrouter | anthropic/claude-haiku-4.5     |
| zeroclaw | port 42617, /webhook            | zeroclaw_native   | openrouter | anthropic/claude-haiku-4.5     |

picoclaw is DEFERRED out of Phase 22c.3 inapp scope per user direction
2026-04-30 (RESEARCH §Revision Notice Round 3).

## Why this is the SC-03 phase exit criterion

Plans 22c.3-{01..14} build the substrate piece by piece (store, dispatcher,
reaper, outbox pump, lifespan, 5 recipe channels.inapp blocks). This
plan's matrix test ratifies that the assembled pieces actually work as
a system — every recipe's channels.inapp shape, the dispatcher's 3-way
contract switch, the persistence chain, and the SSE outbound event are
exercised end-to-end on every run.

Phase 22c.3 cannot be marked SHIPPED until `e2e-report.json` shows
`passed=true` with 5 PASS entries.

## Architecture caveats — what this gate does NOT cover

- The gate uses **Route B** per the Plan 15 executor context: the
  `recipe_container_factory` fixture renders the recipe's
  `persistent_argv_override` / `activation_env` directly. The runner-side
  wiring at `routes/agent_lifecycle.py::start_persistent` (which would
  consume those fields at deploy time when `channel="inapp"` is selected)
  is documented as follow-up work in the Plan 15 SUMMARY. Until that
  ships, the production `POST /v1/agents/:id/start` cannot launch a
  recipe in inapp mode end-to-end — but the dispatcher contract switch
  and the SSE outbound path are proven by this gate.
- `app.state.recipe_index` is not yet wired in `main.py` lifespan —
  this gate's `recipe_index` fixture constructs a real `InappRecipeIndex`
  bound to the recipes dir + a real docker client. The lifespan wiring
  is also documented as follow-up.
- The SSE outbound stream is exercised at the `agent_events` insert
  level (the test asserts the row exists with `published=false`); the
  full Redis Pub/Sub fan-out + `EventSourceResponse` consumer is covered
  by Plan 22c.3-08's `tests/routes/test_agent_messages_sse.py`.

These caveats are deliberate — the gate proves the **contract switch
and dispatcher round-trip** which are the load-bearing properties of
the phase. The runner-side wiring is a single-file extension that
unblocks the production user flow but does not change the contract.
