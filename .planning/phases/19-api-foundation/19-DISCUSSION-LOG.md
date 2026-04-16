# Phase 19: API Foundation — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `19-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-04-16
**Phase:** 19-api-foundation
**Areas discussed:** Idempotency storage, BYOK flow, Runner streaming seam (scope), /healthz vs /readyz, Rate limiting, Deployment packaging, Web terminal WS, OpenAPI docs exposure (8 areas, all selected)

---

## Idempotency-Key storage

| Option | Description | Selected |
|--------|-------------|----------|
| SQLite (file, 24h TTL) | Zero-infra durable store; portable | |
| In-memory dict only | Simplest; lost on restart | |
| Postgres from day one | Matches long-term stack; one behavior dev/prod | ✓ |
| Both in-memory + SQLite | Hot cache + durable write-behind; 3x complexity | |

**User's choice:** Postgres from day one.
**Notes:** "API DUDE. GOLDE RULE. NO MOCKS OR STUBS. API AND POSTGRES." Locked as D-01. Saved as memory `feedback_no_mocks_no_stubs.md`.

---

## BYOK delivery flow

| Option | Description | Selected |
|--------|-------------|----------|
| Bearer per request | Industry standard; in-process only | ✓ |
| Ephemeral run token | POST /v1/keys → opaque run_token_xxx | |
| Encrypted user vault | Requires auth (deferred) | |
| Both (tier it) | 2x implementation for two audiences | |

**User's choice:** "Dude, claude description. robust, production api without overengineer but folllow best practices" → Claude picked Bearer per request.
**Notes:** Locked as D-02. Rationale: Cloudflare Workers AI, Replicate, OpenRouter all use Bearer for pass-through BYOK. Ephemeral token is overengineering pre-auth.

---

## Runner streaming seam (scope question, not seam shape)

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — sync now, SSE later | Phase 19 = foundation; Phase 19.5 adds SSE | ✓ |
| No — keep SSE in phase 19 | Original plan; bigger phase | |
| Mixed — SSE without runner refactor | Worse UX compromise | |

**User's choice:** "sse after, right. ground basics first?" → confirmed sync now, SSE deferred.
**Notes:** Locked as D-03. New phase 19.5 will be added for SSE work.

---

## /healthz vs /readyz depth

| Option | Description | Selected |
|--------|-------------|----------|
| Split /healthz + /readyz | K8s-idiomatic; clean seam | ✓ |
| Only thin /healthz | Simplest; no readiness visibility | |
| Only rich /healthz | LB probes hit slow paths | |
| Split + /metrics | Over-now | |

**User's choice:** Split /healthz + /readyz.
**Notes:** Locked as D-04.

---

## Rate limiting posture + DB model scope

Merged discussion — user surfaced DB model directive during rate limit Q.

**Rate limit options:**
| Option | Description | Selected |
|--------|-------------|----------|
| IP-based via slowapi now | Off-the-shelf middleware | |
| Concurrency semaphore only | No per-IP cap | |
| Semaphore + Postgres-backed counters | Real persistence, no Redis | ✓ |
| Defer entirely | Public DoS vector | |

**DB scope options:**
| Option | Description | Selected |
|--------|-------------|----------|
| Full platform skeleton now | users + agent_instances + runs + idempotency + rate_limit | ✓ |
| Just users + runs + idempotency | Minimal; add later | |
| Only rate + idempotency, no users | Migration required later | |
| Let me describe different scope | | |

**User's choices:**
- "Dude, the database model must allow users to deploy multiple agents, and we could have throttle, just not too aggressive." → D-05 soft throttle via Postgres.
- "Full platform skeleton now" → D-06 full DB schema.

**Notes:** Soft limits: 10/min runs, 120/min lint, 300/min GET. Seed `anonymous` user for phase 19 pre-auth.

---

## Run semantics + Service deployment

Merged because user clarified terminology (agent deploy vs service deploy).

**Run semantics options:**
| Option | Description | Selected |
|--------|-------------|----------|
| One-shot runs (current runner) | POST /v1/runs returns final verdict; no persistent containers | |
| Session-based deploys | POST /v1/agents, persistent containers, messaging | |
| Both | 2x surface; risky | |
| Something else | User describes | ✓ (combined with option 1 spirit) |

**Service deployment options:**
| Option | Description | Selected |
|--------|-------------|----------|
| docker-compose.dev.yml + Postgres | Local dev only | |
| Dev compose + production Dockerfile | Deployable, not deployed | |
| Full Hetzner deploy now | Live on the internet | ✓ |
| Just uvicorn locally | Conflicts with no-stubs | |

**User's choices:**
- "Yeah, post on vi runs and deploy an instance of the agent and store everything in the database, right?" → D-07: one-shot execution + FULL DB persistence (creates agent_instances row + runs row).
- "Full Hetzner deploy now" → D-08: actually deployed with TLS.

**Notes:** Significant scope add. Phase 19 ships real infrastructure end-to-end.

---

## Web terminal WS route

| Option | Description | Selected |
|--------|-------------|----------|
| Defer entirely to phase 22+ | HTTP-only phase | ✓ |
| Scaffold WS route (501) | Symbolic | |
| Ship real WS terminal | Major scope explosion | |

**User's choice:** Defer to phase 22+.
**Notes:** Locked as D-09. Consistent with D-07 (no persistent containers).

---

## OpenAPI docs exposure

| Option | Description | Selected |
|--------|-------------|----------|
| Curate + env-gated /docs | include_in_schema=False; dev-only /docs | ✓ |
| Expose all defaults | Leaks internal routes | |
| Hide all in prod | Frontend type-gen breaks | |
| Docs-on-frontend only | Frontend controls public docs | |

**User's choice:** "You decide. Claude's description, probably number one." → Curate + env-gated.
**Notes:** Locked as D-10. /openapi.json always on for type generation.

---

## Claude's Discretion (user-deferred)

- Async Postgres driver (`asyncpg` vs `psycopg3` — planner's call)
- Migration tool (Alembic vs plain sqlalchemy — planner's call)
- Rate limiter algorithm (sliding window vs token bucket — planner's call)
- Hetzner subdomain (`api.agentplayground.dev` vs `agentplayground.dev/api/*` — planner's call)

## Deferred Ideas

- SSE streaming → new phase 19.5
- OAuth authentication → phase 21+
- Web terminal → phase 22+
- Runtime limits (tokens, turns, cost) → phase 23+
- Stripe billing + metering → future
