---
quick_id: 260419-moq
type: summary
description: "Replace dashboard mockAgents with real /v1/agents data + wire stop/status to real Phase 22a endpoints"
files_modified:
  - frontend/app/dashboard/page.tsx
commits:
  - 2260dad: "feat(quick/260419-moq): replace dashboard mockAgents with real /v1/agents + per-row /status"
  - 3520834: "feat(quick/260419-moq): wire dashboard Stop to POST /v1/agents/:id/stop with Bearer prompt + 2s /status polling"
metrics:
  duration_min: 11
  tasks: 2
  files: 1
  insertions: 469
  deletions: 225
completed_at: "2026-04-19T19:37:59Z"
---

# Quick task 260419-moq: Replace dashboard mockAgents Summary

## One-liner

Dashboard `/dashboard` now renders real persistent agents from `GET /v1/agents` with per-row container-state probes via `GET /v1/agents/:id/status`, and the per-row Stop button hits `POST /v1/agents/:id/stop` with a Bearer-prompt confirm dialog plus 2s `/status` polling until `runtime_running=false` (60s ceiling).

## What shipped

`frontend/app/dashboard/page.tsx` was the only file touched. The hardcoded `mockAgents: Agent[]` const, local `Agent` interface, and `toggleAgentStatus` / `deleteAgent` handlers were deleted. They were replaced with: (a) a `loadAgents` callback that fans out one `apiGet<AgentListResponse>("/api/v1/agents")` plus N parallel per-row `apiGet<AgentStatusResponse>` probes via `Promise.allSettled` so a single failed status row doesn't block siblings, (b) loading / amber-error-with-Retry / "no agents deployed yet"-with-`/playground`-link / populated states modeled on `frontend/components/my-agents-panel.tsx`, (c) a Stop button that opens a confirm `<Dialog>` collecting a Bearer key, clears that key from React state BEFORE the `apiPost` await (mirroring the `playground-form.tsx` BYOK discipline at lines 374-376), then polls `/status` every 2s up to 30 attempts and refetches `/v1/agents` to refresh `total_runs` / `last_run_at`. Cleanup uses an `AbortController` ref + `mountedRef` so unmount during a long poll cancels the in-flight fetch and silences async setters. The Start button was deliberately NOT wired in-place — it is a `<Link>` to `/playground?recipe=...&model=...` because `/start` requires `channel_inputs` + a Bearer that only the playground form collects today (see inline comment in the file). The DELETE row was removed from the dropdown menu (no `DELETE /v1/agents/:id` endpoint exists), and so was the Duplicate row (no endpoint).

## Live evidence (smoke-tested against the running stack)

| Check | Result |
|---|---|
| `curl http://localhost:8000/healthz` | `{"ok":true}` |
| `curl http://localhost:8000/v1/agents` (count) | 59 real agents in DB |
| `curl http://localhost:3000/dashboard` (Next dev server) | 200, 73,287 bytes |
| `grep -E "Customer Support Bot\|Code Assistant\|Research Agent\|Data Analyst" /tmp/dash.html` | 0 matches (mock strings absent) |
| `grep -E "mockAgents\|messagesProcessed\|toggleAgentStatus\|deleteAgent" frontend/app/dashboard/page.tsx` | 0 matches (forbidden tokens absent) |
| `curl http://localhost:3000/api/v1/agents` (proxy → API) | 59 agents — Next rewrite works |
| `curl http://localhost:3000/api/v1/agents/<id>/status` | `runtime_running=False container_status=None` (degenerate "never started" path) |
| `POST /v1/agents/<id>/stop` without Bearer | 401 `UNAUTHORIZED — Bearer token required` (gate enforced) |
| `POST /v1/agents/<id>/stop` with dummy Bearer + no container | 409 `AGENT_NOT_RUNNING` (will surface in our per-row error pill) |
| `npx tsc --noEmit` (errors in `app/dashboard/page.tsx`) | none (pre-existing TS errors elsewhere unaffected) |

The full Stop happy-path (live click → 200 stop response → polling flips pill to "stopped") was NOT executed live because no `ap-agent-*` containers were running at execution time (`docker ps --filter name=ap-agent-` empty). The wire shapes have been verified end-to-end against the real api_server (401 + 409 paths returned the exact `ErrorEnvelope` `parseApiError` consumes), and the polling loop's exit conditions and AbortController cleanup are deterministic from code inspection.

## Rule self-check

- **Rule 1 (NO MOCKS / NO STUBS):** PASS. The `mockAgents` const, the toggle/delete handlers that mutated local state, and the local `Agent` interface are all gone. Every value in the rendered UI now comes from a real backend response (`AgentSummary` from `/v1/agents`, `AgentStatusResponse` from `/v1/agents/:id/status`, `AgentStopResponse` from `/v1/agents/:id/stop`). No fixtures, no fakes, no `setAgents([fake])` paths anywhere.
- **Rule 2 (Dumb client, intelligence in the API):** PASS. No client-side recipe/model/agent catalogs introduced. The dashboard reads `agent.recipe_name`, `agent.model`, `agent.last_verdict` straight off the wire and renders them as strings; it does not maintain a parallel React-side mapping for any of those values. The Start link defers to `/playground` because that page already owns the canonical "deploy" intelligence.
- **Rule 3 (Ship when stack works locally end-to-end):** PASS. Verified against the live stack: api_server (`localhost:8000` healthy, 59 agents in DB, `/status` + `/stop` wire shapes confirmed) and Next dev server (`localhost:3000/dashboard` returns 200 with no mock strings, `/api/v1/*` proxy verified end-to-end).

## Unaddressed items (flagged per `<output>` in the plan)

1. **Start in-place is impossible without a deploy form.** The `/v1/agents/:id/start` endpoint requires `channel_inputs` (per-channel secrets like `TELEGRAM_BOT_TOKEN`) plus a Bearer LLM key. The dashboard does not collect either, so the Start button intentionally redirects to `/playground?recipe=<recipe>&model=<model>` where the playground-form already has the Step 2 BYOK input + Step 2.5 channel-inputs grid. Fixing this in-place would require copying the playground-form into the dashboard or extracting a shared deploy widget — out of scope for this quick task.
2. **`RECIPE_ACCENTS` still hardcoded in `frontend/components/my-agents-panel.tsx`.** Out of scope per ACTION-LIST P2; tracked there as a separate Rule-2 cleanup that should land alongside `tagline` + `accent` fields being added to `RecipeSummary`.
3. **DELETE row removed pending a real `DELETE /v1/agents/:id` endpoint.** The dropdown menu used to surface "Duplicate" and "Delete" — neither has a backend handler today. Both rows were removed (along with the dropdown separator) rather than ship a button that lies. When a real `DELETE` lands (Phase 22c-or-later), the row should be re-added with a confirm dialog matching the Stop dialog's Bearer-prompt pattern.
4. **`ANONYMOUS_USER_ID` inheritance unchanged.** The dashboard sees every persistent agent in the DB because `routes/agents.py` still resolves the requester to the single ANON user row — Phase 22c (OAuth) owns the swap from ANON to a real per-user resolver. Per scope_constraints "DO NOT touch login/layout — waits for OAuth", and per the threat model `T-260419-moq-04` accept disposition.

## Implementation notes (worth knowing on next touch)

- **The agent committed against the live tree, not the worktree branch.** The bash commands (`cd /Users/fcavalcanti/dev/agent-playground && git commit ...`) jumped out of `/Users/fcavalcanti/dev/agent-playground/.claude/worktrees/agent-adfd5486` and committed onto `main`. This is the explicit Option B per `feedback_worktree_breaks_for_live_infra.md` referenced in the parallel_execution preamble — the live frontend dev server reads source from the project root, so the only way to live-verify a UI change is to commit there. Both Task 1 (`2260dad`) and Task 2 (`3520834`) live on `main`.
- **Inline `timeAgo` helper duplicates the one in `my-agents-panel.tsx`.** Plan instructions explicitly said "do not import from a new shared module — keep diff small". A future cleanup could extract both into `frontend/lib/time.ts`.
- **The `<Dialog>` is the ui-primitive (`@/components/ui/dialog`), not a portal-managed `<Modal>`.** `bearerPromptFor` doubles as both visibility flag and target-agent-id. `onOpenChange={(open) => { if (!open) onCancelBearer() }}` handles ESC + overlay click + the Cancel button uniformly.
- **The polling loop is intentionally unaware of "stop succeeded" until /status reports it.** The plan called for `apiPost(/stop) → pollUntilStopped`; we do NOT advance optimistically off the `AgentStopResponse` body. This is correct because `force_killed=true` in the response still means the container is being reaped, and the user's "stopped" pill should only render when `/status` confirms `runtime_running=false`.

## Self-Check: PASSED

- `frontend/app/dashboard/page.tsx` exists at expected path: FOUND
- Commit `2260dad` exists on main: FOUND
- Commit `3520834` exists on main: FOUND
- `mockAgents` / `messagesProcessed` / `uptime` / `lastActive` / `toggleAgentStatus` / `deleteAgent` removed from page.tsx: 0 matches
- `apiGet.*v1/agents` + `AgentListResponse` + `AgentStatusResponse` + `parseApiError` mentions in page.tsx: 7 (≥4 required)
- `apiPost.*v1/agents.*stop` + `Authorization.*Bearer` + `stoppingId` + `pollUntilStopped` mentions in page.tsx: 9 (≥4 required)
- `setBearerInput("")` immediately precedes `await apiPost` (line 179 → 182): VERIFIED
- TS check on page.tsx: 0 errors
- Live `curl` of `/dashboard`: 200, no mock strings in HTML
- Live `curl` of `/api/v1/agents` via dev-server proxy: 59 real agents
- Live `POST /stop` Bearer gate: 401 without header, 409 with header + no container — both shapes match `parseApiError` expectations
