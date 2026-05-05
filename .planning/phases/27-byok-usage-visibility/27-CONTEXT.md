# Phase 27: BYOK Usage Visibility — Context

**Gathered:** 2026-05-04
**Status:** Change 1 + 2 SHIPPED (commits `eb406da`, `475e11e`); Change 3a/3b/4 ahead
**Methodology:** Lean (no full GSD ceremony chain — recon → write → test → atomic commit). 3 parallel Explore agents per change. **TDD from Change 3a onward** — write tests first, then make them pass.

<domain>
## Phase Boundary

Surface **what is this agent costing me?** to BYOK users. Captures upstream LLM usage per chat message (tokens + USD), persists per-user / per-agent totals, displays a real-time USD running total in the AppBar (mobile + web — always visible) plus a per-agent breakdown screen with last 7d / last 30d series.

**No money flow.** No Stripe, no debits, no balance, no paywall, no 402. Phase A (this phase) is the pure-visibility precursor that proves the data shape against real upstream calls before Phase B (paywall + platform-billed tier) lands.

**MSV's "always-proxy" pattern is wrong here.** MSV pays upstream → proxy is the cash register. AP-BYOK = user pays upstream → proxy NOT load-bearing for cash; only needed for visibility. Phase A captures via response-body parse (openai_compat) — no proxy. Phase B (later) introduces a proxy ONLY for non-BYOK users.

**Out of scope (this phase):**
- Money flow (Phase B)
- Post-hoc OpenRouter `/api/v1/generation` fetch for stripped-contract recipes (a2a_jsonrpc nullclaw, zeroclaw_native zeroclaw) — deferred; current behavior writes `status='unknown'` rows
- 1-hour Anthropic prompt-cache write pricing (collapses into 5m rate; ~37% under-price if used; no recipe uses 1h caching today)
- `service_tier` differentiation (standard vs priority vs batch) — defer; recipes don't use batch
- Mobile + web "Settings" surface for usage / cost-history export

</domain>

<decisions>
## Implementation Decisions

### Schema (D-01..D-04) — SHIPPED in Change 1 (commit `eb406da`)
- **D-01:** Two tables — `usage_logs` (append-only per-call ledger) + `cost_weights` (admin-mutable pricing). Both via Alembic migration 010.
- **D-02:** `usage_logs.cost_usd` is `NUMERIC(14, 8)` USD — NOT integer cents. Anthropic haiku at 14+4 tokens costs $0.000034; cents would round to zero. NUMERIC(14,8) preserves sub-cent precision and aggregates cleanly.
- **D-03:** Schema captures tokens + cost + cache breakdown + status + latency + stop_reason + source. 17 columns. Tokens stored separately from cost so future re-pricing (admin edits a `cost_weights` row) doesn't require recomputing historical USD on the fly — `cost_usd` is the value that was true at write time.
- **D-04:** Indexes — `(user_id, created_at DESC) INCLUDE (cost_usd)` for the AppBar ticker hot path (Index Only Scan, EXPLAIN-confirmed) + `(agent_instance_id, created_at DESC)` for per-agent screens. Third composite was considered and dropped — the leading-prefix of the user index covers user-only queries.

### Cost weights seed (D-05) — SHIPPED in Change 1
- **D-05:** 6 baseline rows seeded — 3 OpenRouter (haiku, sonnet, gpt-4o-mini) live-confirmed; 2 Anthropic-direct (haiku-4-5, sonnet-4-5) live-confirmed; 1 OpenAI direct (gpt-4o-mini) doc-confirmed. Cache multipliers verified: 1.25× write, 0.10× read.

### Recorder architecture (D-06..D-09) — SHIPPED in Change 2 (commit `475e11e`)
- **D-06:** Module-level async functions in `services/usage_recorder.py` (no `class UsageRecorder` — matches the api_server's existing service-layer convention). Single public entry point `record_usage(conn, ...)`.
- **D-07:** Hook in `inapp_dispatcher._handle_row` Step 6 (success path), called inside the same transaction as `mark_done` + `insert_agent_event`. Atomic — usage row is durable iff message is done.
- **D-08:** **SAVEPOINT isolation** — `record_usage` opens its own nested `conn.transaction()` (asyncpg auto-detects nesting → SAVEPOINT). A recorder failure (FK violation, weights drift, …) rolls back to the savepoint; the outer `mark_done` txn survives. **Without this, an aborted INSERT would poison the txn and roll back the chat reply.** Load-bearing safety property.
- **D-09:** Recorder swallows ALL exceptions and returns `None`. Logged via `_log.exception` so ops can grep. Chat path correctness must NEVER depend on the recorder — the user gets their reply even if the recorder breaks.

### Provider lookup (D-10) — SHIPPED in Change 2
- **D-10:** `runtime.provider` is at the top of every recipe YAML (not under `channels.inapp`). Surfaced via a new optional `provider: str | None` field on `InappChannelConfig` (parsed in `_parse_inapp_block`). The dispatcher passes `inapp.provider` into `record_usage`. `None` → recorder marks `provider='unknown'` + skips cost computation; row still exists for message count.

### Per-contract capture matrix (D-11) — SHIPPED in Change 2
- **D-11:** 4 of 5 recipes (openclaw / hermes / picoclaw / nanobot — all `openai_compat`) → recorder parses `data["usage"]` from the bot's response. Both OpenAI shape (`prompt_tokens`/`completion_tokens`) and Anthropic-passthrough shape (`input_tokens`/`output_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens`) supported. 1 of 5 (nullclaw `a2a_jsonrpc`, zeroclaw_native if/when wired) → bot strips usage; row written with `status='unknown'`, tokens=0, cost=0. Future post-hoc OpenRouter fetch is the documented backfill path.

### Read-side API endpoints (D-12..D-15) — Change 3a (next)
- **D-12:** Two new endpoints, both `require_user`:
  - `GET /v1/usage/summary` — AppBar ticker payload. Shape:
    ```json
    {
      "total_usd": "0.0034",
      "message_count": 12,
      "by_agent": [
        {"agent_id": "<uuid>", "agent_name": "...", "recipe_name": "...",
         "model": "...", "cost_usd": "0.002", "message_count": 8,
         "last_activity": "2026-05-04T22:01:00Z"}
      ]
    }
    ```
  - `GET /v1/agents/:id/usage` — per-agent breakdown screen payload. Shape:
    ```json
    {
      "agent_id": "<uuid>",
      "cumulative": {
        "input_tokens": 123, "output_tokens": 45,
        "cache_read_tokens": 0, "cache_creation_tokens": 0,
        "cost_usd": "0.001234", "message_count": 8,
        "last_activity": "..."
      },
      "series_7d": [
        {"day": "2026-04-28", "cost_usd": "0.0001", "tokens": 50, "message_count": 1},
        ...
      ],
      "series_30d": [...]
    }
    ```
- **D-13:** **Server-side aggregation only.** Per CLAUDE.md golden rule #2 (strengthened 2026-05-04 evening) — clients NEVER `SUM` / `GROUP BY` / aggregate. The endpoints compute every total, every series, every breakdown row in SQL and return ready-to-render JSON. Mobile / web `setState` the response and render directly.
- **D-14:** USD values returned as **strings** (`"0.0034"`), not floats. Avoids JSON float precision issues across language boundaries (Dart's double, JS Number) for sub-cent values. Clients display verbatim.
- **D-15:** Date series uses **UTC days** (`DATE(created_at AT TIME ZONE 'UTC')`). Display-side timezone formatting is the client's job. Empty days are NOT padded server-side — clients zero-fill missing dates if the chart shape requires it (Flutter and React both have utility libs for this).

### TDD discipline (D-16) — Change 3a onward
- **D-16:** **Tests first.** Write `test_usage_endpoints.py` with the expected JSON shape + status codes + auth gate before writing the route handler. Run test, see RED, write the handler, run test, see GREEN. Commit only when GREEN. Mirror the existing `tests/routes/` testcontainers + `authenticated_cookie` fixture pattern.

### Mobile UI (D-17..D-19) — Change 3b
- **D-17:** AppBar USD ticker — top-bar widget, ALWAYS visible when signed in. Polls `/v1/usage/summary` on screen mount + on agent-event SSE notification. Click → `Navigator.push` → per-agent breakdown screen.
- **D-18:** Per-agent breakdown screen — opens from ticker click OR from the dashboard's per-agent row. Shows cumulative (USD + tokens + count + last activity) + 7d + 30d charts. Pure consumer of `/v1/agents/:id/usage`.
- **D-19:** Solvr aesthetic — Matrix/ASCII feel preferred for empty states (e.g., "no usage yet" with falling-text decoration). USD is the headline; tokens are secondary.

### Web UI (D-20..D-21) — Change 4
- **D-20:** Web AppBar USD ticker beside the profile dropdown (top-right). Same `/v1/usage/summary` source, same click → breakdown view (drawer or page — TBD during Change 4).
- **D-21:** Per-agent breakdown view reuses `/v1/agents/:id/usage`. Mobile + web are visual variants over the same JSON.

### Claude's Discretion
- Exact column ordering in `usage_logs.created_at` index (DESC is the default lean direction for "most recent first").
- Pagination on `by_agent` list inside `/v1/usage/summary` — current MVP: return all agents (most users will have <20).
- Whether to add a `/v1/usage/series` endpoint for the AppBar mini-sparkline if we ever build one (defer; likely not needed v1).
- Polling interval for the AppBar ticker — 30s? On-focus? Trigger via SSE agent-event? Decided during Change 3b.

</decisions>

<endpoint_contract>
## Locked Endpoint Contract (Change 3a target)

**`GET /v1/usage/summary`**
- Auth: `require_user` (signed cookie)
- Query params: NONE for v1 (cumulative-all-time). Future: `?since=ISO8601` for "this month" view (deferred).
- 200 response: see D-12 above
- 401: standard envelope `{"error": {"code": "unauthorized", ...}}`

**`GET /v1/agents/:agent_id/usage`**
- Auth: `require_user` + must own the agent (`agent_instances.user_id = user.id`)
- 200 response: see D-12 above
- 403: agent owned by a different user — `{"error": {"code": "forbidden", ...}}`
- 404: agent not found — `{"error": {"code": "agent_not_found", ...}}`

**Implementation file:** `api_server/src/api_server/api/v1/usage.py` (new)
**Service file:** `api_server/src/api_server/services/usage_query.py` (new — read-side query helpers; the `usage_recorder.py` is write-side only)

</endpoint_contract>

<state>
## Phase State Tracker

| Change | Scope | State | Commit | Notes |
|---|---|---|---|---|
| 1 | Migration 010 (`usage_logs` + `cost_weights`) + 6 seed rows | ✅ SHIPPED | `eb406da` | Live round-trip + EXPLAIN proves Index Only Scan |
| 2 | `UsageRecorder` service + `inapp_dispatcher` hook + 12 tests | ✅ SHIPPED | `475e11e` | 32/32 services tests pass; SAVEPOINT isolation |
| — | CLAUDE.md golden rule #2 strengthened (any client) | ✅ SHIPPED | `202900c` | Mobile/web/CLI/SDK all dumb |
| 3a | Backend `GET /v1/usage/summary` + `GET /v1/agents/:id/usage` + tests | 🔜 NEXT | — | TDD: write tests first |
| 3b | Mobile AppBar ticker + per-agent breakdown screen | queued | — | Pure client; no logic |
| 4 | Web AppBar ticker + per-agent breakdown view | queued | — | Reuses 3a endpoints |

**Resume protocol after `/clear`:**
1. Read `memory/MEMORY.md` (auto-loaded — index of everything)
2. Read this file (`.planning/phases/27-byok-usage-visibility/27-CONTEXT.md`)
3. Read `memory/project_phase_27_constraints.md` (locked constraints)
4. Run `git log --oneline -5` — confirm last commit matches the State Tracker above
5. Pick up the next ⏳/🔜 row

</state>

<canonical_refs>
## Canonical References

### Locked constraints (don't re-litigate)
- `memory/project_phase_27_constraints.md` — schema, USD, AppBar ticker scope, Phase B locked design
- `memory/feedback_ap_proxy_is_not_msv_proxy.md` — why we don't mirror MSV's egress proxy

### Architecture rules (apply every change)
- `CLAUDE.md` golden rule #2 — dumb client EVERY client (web, mobile, CLI, SDK)
- `memory/feedback_dumb_client_no_mocks.md` — endpoint-design corollary: server returns ready-to-render JSON
- `memory/feedback_no_mocks_no_stubs.md` — real Postgres, real upstream
- `memory/feedback_test_everything_before_planning.md` — every non-trivial mechanism spiked first
- `memory/feedback_root_cause_first.md` — never fix-to-pass
- `memory/feedback_inflight_ui_for_long_awaits.md` — mobile UX for >2s awaits
- `memory/feedback_asyncio_to_thread_pool_starvation.md` — when post-hoc fetch lands

### Reference points
- `recipes/openclaw.yaml` `inapp:` block (openai_compat + anthropic-direct provider)
- `recipes/nullclaw.yaml` `inapp:` block (a2a_jsonrpc — usage stripped)
- `api_server/alembic/versions/010_usage_logs_cost_weights.py` — schema-of-record
- `api_server/src/api_server/services/usage_recorder.py` — write side
- `api_server/tests/services/test_usage_recorder.py` — 12-test reference for new test patterns

### Live probe artifacts (Change 1 evidence)
- `/tmp/cost_probe/` — OpenRouter generation responses
- `/tmp/cost_probe_v2/` — Anthropic-direct responses (haiku + sonnet)

</canonical_refs>
