---
phase: 19-api-foundation
status: deploy_blocked_pending_dumb_playground
paused_at: 2026-04-17T18:00:00Z
resume_on: 2026-04-18
plan_open: 19-07
task_open: Task 3 BLOCKED — do not deploy until /playground actually works end-to-end
---

# Phase 19 — DO NOT DEPLOY YET

**STOP. The Hetzner deploy is cancelled until a real user workflow works locally end-to-end.**

## Why (golden rule violation caught 2026-04-17 afternoon)

Phase 19 shipped a working API. The frontend at `/playground` is a v0-generated mock: hardcoded `defaultClones` array, hardcoded model list, Deploy button flips `isRunning: true` in React state with zero network traffic. Clicking through the UI drives nothing real.

Deploying the API to `api.agentplayground.dev` in this state means:
- A user opens the URL → sees the mock playground
- Picks a clone → pure client-side state
- Clicks "Deploy All Agents" → **nothing happens**, no API call, no feedback
- The deployed URL is useful only for `curl` clients

That's shipping a mock to prod. See golden rule #3 in `CLAUDE.md`.

## What's still valid from Phase 19

Plans 19-01 through 19-07 (Tasks 1+2) are shipped and correct. The API is genuinely solid:
- Live Postgres + Docker integration (testcontainers): 49 tests green
- Production-shaped Docker stack (compose + alembic + asyncpg): validated locally with `make dev-api-local`
- `curl localhost:3000/api/v1/recipes` round-trips browser → Next → containerized API → postgres
- 5 prod-blocking deploy bugs found and fixed locally before they could bite on Hetzner (commit `cdcc897`)

That work does not need to be redone. The **API is deploy-ready**. The platform is not.

## What must happen before the deploy

New phase (tentative: **19.1-dumb-playground** or fold into Phase 20):
- Rip out mock `defaultClones` from `frontend/components/agent-configurator.tsx` (or replace the whole `/playground` page with a thin functional shell)
- `/playground` fetches recipes from `GET /v1/recipes` on mount
- Model input: free-text or API-driven (not a hardcoded array)
- Deploy button: POST `/v1/runs` with `{recipe_name, model, prompt}` + `Authorization: Bearer <BYOK>` header from a form field
- Run result visible on the page (verdict, category, exit_code, stderr tail)
- Run history: `GET /v1/runs/{id}` or a list endpoint (may need new API route)
- Everything else (A2A graph, Tasks tab, Monitor tab, pricing, docs) can stay cosmetic

**Local validation gate** (must pass before Hetzner deploy resumes):
1. `make dev-api-local` brings up the containerized API
2. `make dev-frontend` brings up Next.js at :3000
3. User opens `http://localhost:3000/playground`
4. User configures recipe + model + prompt + BYOK key
5. User clicks Deploy → real `POST /v1/runs` → waits → sees real verdict
6. Run persists in postgres; confirmed via `docker compose ... exec postgres psql ...`

Only after that works does `bash deploy.sh` against Hetzner become the next step.

## Resume kickoff for tomorrow

```text
Dumb playground phase — golden rule #2 (dumb client, intelligence in the API) requires replacing the v0 mock /playground before deploying Phase 19.

Please read:
1. CLAUDE.md  (golden rules at the top — #2 and #3 are load-bearing here)
2. .planning/phases/19-api-foundation/RESUME-TOMORROW.md  (this file)
3. memory/feedback_dumb_client_no_mocks.md  (the principle)
4. frontend/components/agent-configurator.tsx  (the mock that must go)
5. frontend/lib/api.ts  (existing thin fetch wrapper to reuse)

Then: /gsd-discuss-phase 19.1  (or propose Phase 20 scope if it fits there)
Goal: a /playground page that drives real /v1/runs end-to-end. Nothing hardcoded client-side that the API owns.
```

## What NOT to do tomorrow

- **Do NOT** run `bash deploy/deploy.sh` against Hetzner
- **Do NOT** run `/gsd-execute-phase 19 --wave 4` — that path goes to the cancelled deploy
- **Do NOT** mark Phase 19 complete until the playground works locally end-to-end
- **Do NOT** introduce new client-side arrays of recipes/models/channels — if it's a list, fetch it

Memory pointers: `memory/project_phase_19_deploy_handoff.md`, `memory/feedback_dumb_client_no_mocks.md`.
