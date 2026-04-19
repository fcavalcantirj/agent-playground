---
quick_id: 260419-moq
type: execute
mode: quick
description: "Replace dashboard mockAgents with real /v1/agents data + wire stop/status buttons to real Phase 22a endpoints"
files_modified:
  - frontend/app/dashboard/page.tsx
autonomous: true
must_haves:
  truths:
    - "Visiting /dashboard fetches GET /api/v1/agents on mount (no hardcoded mockAgents in the file)"
    - "Each card shows real AgentSummary fields: name, recipe_name, model, last_verdict, last_run_at, total_runs"
    - "Each agent card shows live container state via GET /api/v1/agents/:id/status (running / stopped / unknown), fetched per-row on mount"
    - "Loading state renders before the first /v1/agents response settles (skeleton or spinner — NOT mockAgents)"
    - "Empty state shows honest 'No agents yet — head to /playground' link when /v1/agents returns []"
    - "Error state shows parsed UiError message + Retry button when /v1/agents fails"
    - "Stop button on a running agent calls POST /api/v1/agents/:id/stop with Authorization: Bearer (key prompted in-row), polls /status every 2s until runtime_running=false, then refetches /v1/agents"
    - "Start button on a stopped agent does NOT pretend to start in-place — it links to /playground (the only place that has the channel_inputs + LLM key the /start endpoint requires)"
  artifacts:
    - path: "frontend/app/dashboard/page.tsx"
      provides: "Real-data dashboard with /v1/agents list + stop/status wiring"
      forbids: "no const mockAgents, no setAgents toggle that just flips a local 'status' field"
  key_links:
    - from: "frontend/app/dashboard/page.tsx (useEffect on mount)"
      to: "GET /api/v1/agents"
      via: "apiGet<AgentListResponse> from @/lib/api"
      pattern: "apiGet.*v1/agents"
    - from: "frontend/app/dashboard/page.tsx (per-row status fetch)"
      to: "GET /api/v1/agents/:id/status"
      via: "apiGet<AgentStatusResponse>"
      pattern: "v1/agents/.*/status"
    - from: "frontend/app/dashboard/page.tsx (Stop button onClick)"
      to: "POST /api/v1/agents/:id/stop"
      via: "apiPost with Authorization: Bearer header"
      pattern: "v1/agents/.*/stop"
---

<objective>
The /dashboard page currently ships a hardcoded `mockAgents` const and a `toggleAgentStatus` that just flips a local React field. This violates Rule 1 (no mocks) and Rule 2 (intelligence in the API).

Replace the mock list with a real `GET /v1/agents` fetch on mount. Wire each row's container-state badge to `GET /v1/agents/:id/status`. Wire the Stop button to `POST /v1/agents/:id/stop` with Bearer-prompt + 2s status polling until terminal. Leave the Start button as a link to `/playground` (it is the only place that has channel creds + LLM key, both of which `/start` requires per `AgentStartRequest` shape).

Purpose: implement rows 36 + 38 of `.planning/audit/ACTION-LIST.md` FRONTEND P1, as far as possible without inventing endpoints (Start in-place is impossible without a creds-collection UI we already have at /playground; redirecting is the honest move).

Output: a single updated `frontend/app/dashboard/page.tsx` that satisfies all `must_haves` truths, with two atomic commits.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@.planning/audit/ACTION-LIST.md

# Existing structural analog — copy state machine from here
@frontend/components/my-agents-panel.tsx

# Current file (the mock-laden one we're replacing in place)
@frontend/app/dashboard/page.tsx

# API client + parsed error helper
@frontend/lib/api.ts

# TS types for AgentSummary / AgentListResponse / AgentStatusResponse / AgentStopResponse / parseApiError / UiError
@frontend/lib/api-types.ts

# Real backend routes — proves the wire shape we must call
@api_server/src/api_server/routes/agents.py
@api_server/src/api_server/routes/agent_lifecycle.py
@api_server/src/api_server/models/agents.py

# Bearer-prompt pattern reference (Step-4 deploy uses Authorization: Bearer ${byok}, then clears state)
@frontend/components/playground-form.tsx

<interfaces>
<!-- Authoritative shapes the executor must use directly. Do NOT redefine these. -->

From frontend/lib/api.ts:
```ts
export class ApiError extends Error { status: number; body: string; headers: Headers; }
export type ApiCallOptions = { signal?: AbortSignal };
export function apiGet<T>(path: string, opts?: ApiCallOptions): Promise<T>;
export function apiPost<T>(path: string, body?: unknown, headers?: HeadersInit, opts?: ApiCallOptions): Promise<T>;
```

From frontend/lib/api-types.ts (already exported, do not redeclare):
```ts
export type AgentSummary = {
  id: string;
  name: string;
  recipe_name: string;
  model: string;
  personality?: PersonalityId | null;
  created_at: string;
  last_run_at?: string | null;
  total_runs: number;
  last_verdict?: string | null;
  last_category?: string | null;
  last_run_id?: string | null;
};
export type AgentListResponse = { agents: AgentSummary[] };
export type AgentStatusResponse = {
  agent_id: string;
  container_row_id?: string | null;
  container_id?: string | null;
  container_status?: string | null;        // "running" | "stopped" | "starting" | etc — string from server
  channel?: string | null;
  ready_at?: string | null;
  boot_wall_s?: number | null;
  runtime_running: boolean;
  runtime_exit_code?: number | null;
  log_tail: string[];
  last_error?: string | null;
};
export type AgentStopResponse = {
  agent_id: string;
  container_row_id: string;
  container_id: string;
  stopped_gracefully: boolean;
  exit_code: number;
  stop_wall_s: number;
  force_killed: boolean;
};
export type UiError = /* discriminated union, see file */;
export function parseApiError(err: unknown): UiError;
```

From frontend/components/my-agents-panel.tsx (the structural analog — same load-error-empty-list shape):
```ts
const [agents, setAgents] = useState<AgentSummary[] | null>(null);
const [error, setError] = useState<UiError | null>(null);
const load = useCallback(async () => {
  try {
    const data = await apiGet<AgentListResponse>("/api/v1/agents");
    setAgents(data.agents);
    setError(null);
  } catch (e) { setError(parseApiError(e)); }
}, []);
useEffect(() => { load(); }, [load]);
```

From api_server/src/api_server/routes/agent_lifecycle.py — wire shape for /stop:
- Method: POST
- Path: /v1/agents/{agent_id}/stop
- Headers: Authorization: Bearer <provider_key> (REQUIRED — handler returns 401 without it; the value isn't read by /stop but the gate is enforced)
- Body: none
- Returns AgentStopResponse on success; 404 AGENT_NOT_FOUND, 409 AGENT_NOT_RUNNING, 502 INFRA_UNAVAILABLE on errors

From api_server/src/api_server/routes/agent_lifecycle.py — wire shape for /status:
- Method: GET
- Path: /v1/agents/{agent_id}/status
- Headers: NONE (the only persistent-mode endpoint that does NOT require Bearer — confirmed in source comments)
- Returns AgentStatusResponse always-200 (degenerate shape with only agent_id when no container row exists)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Replace mockAgents with real /v1/agents fetch + per-row /status fetch + loading/empty/error states</name>
  <files>frontend/app/dashboard/page.tsx</files>
  <read_first>
    1. frontend/components/my-agents-panel.tsx — copy its load/error/empty state machine (apiGet + parseApiError + useCallback load + useEffect on mount).
    2. frontend/app/dashboard/page.tsx — current file; preserve the visual shape (header + 3 stat cards + search input + status filter pills + ScrollArea list + per-row card with name/recipe/model/badges/Stop button + DropdownMenu).
    3. frontend/lib/api-types.ts lines 81–98, 188–201 — confirm AgentSummary / AgentListResponse / AgentStatusResponse exact field names. DO NOT add new fields to api-types.ts; the existing shapes cover this task end-to-end.
    4. api_server/src/api_server/routes/agents.py — confirm response is `{ agents: AgentSummary[] }`.
    5. api_server/src/api_server/routes/agent_lifecycle.py lines 650–737 — confirm /status returns 200 even when no container exists, and that no Bearer is required.
  </read_first>
  <action>
**Delete** the `mockAgents: Agent[]` const (lines ~45–90), the local `Agent` interface (lines ~33–43), and the `toggleAgentStatus`/`deleteAgent` functions (lines ~107–117).

**Replace the local Agent type** with the imported `AgentSummary` from `@/lib/api-types`. Also import `AgentListResponse`, `AgentStatusResponse`, `parseApiError`, and `type UiError` from the same module. Import `apiGet` from `@/lib/api`.

**State machine** (mirror MyAgentsPanel exactly):
- `const [agents, setAgents] = useState<AgentSummary[] | null>(null)` — null = not-yet-loaded sentinel
- `const [listError, setListError] = useState<UiError | null>(null)`
- `const [statuses, setStatuses] = useState<Record<string, AgentStatusResponse | "loading" | "error">>({})` — keyed by `agent.id`
- Keep existing `searchQuery` and `statusFilter` state.

**Fetch logic**:
1. `loadAgents = useCallback(async () => {...})` — wraps `apiGet<AgentListResponse>("/api/v1/agents")`, sets agents/listError per the MyAgentsPanel pattern. On success, kick off per-row status fetches (see step 2).
2. `useEffect(() => { loadAgents() }, [loadAgents])` on mount.
3. Inside `loadAgents` after `setAgents(data.agents)`: for each agent, `apiGet<AgentStatusResponse>(\`/api/v1/agents/\${a.id}/status\`)` in parallel via `Promise.allSettled`. Mark the entry as `"loading"` first, then store the resolved value or `"error"` on rejection. Wrap each call in try/catch — a single failed status MUST NOT prevent other agents from rendering.

**Mapping mock fields → real fields** (rewrite the per-card render):
- `agent.name` → real `agent.name`
- `agent.clone` → real `agent.recipe_name`  (label change in copy: "Recipe")
- `agent.model` → real `agent.model`
- `agent.status` ("running"|"stopped") → derived from `statuses[agent.id]`:
  - if status row is "loading" → render a small spinner + "checking…"
  - if status row is "error" → render a muted "status unavailable"
  - if `runtime_running === true` → render the existing green pulsing pill with copy "running"
  - if `runtime_running === false` && `container_status == null` → render muted pill with copy "never started"
  - if `runtime_running === false` && `container_status` is non-null → render muted pill with copy "stopped"
- `agent.channels` (mock array) → DELETE the channel chips block entirely (server doesn't expose a per-agent channels list on AgentSummary; statuses returns a single `channel?: string | null`). If a status row has a channel, render a single small chip with that string; otherwise render nothing.
- `agent.messagesProcessed` → real `agent.total_runs`; copy: "{n} run{s}". Use the same MessageSquare icon row.
- `agent.uptime` → DELETE entirely (no server field; do not invent).
- `agent.lastActive` → real `agent.last_run_at ?? agent.created_at`. Use the existing Clock icon row. Helper: copy `timeAgo` from `frontend/components/my-agents-panel.tsx` lines 37–48 directly into this file (do not import from a new shared module — keep diff small).

**Stats row** (top 3 cards):
- "Running Agents" → count of agents whose `statuses[id]?.runtime_running === true`. While statuses are loading, show "—".
- "Total Agents" → `agents?.length ?? 0`.
- DELETE the "Messages Processed" card (no server field for total messages). Replace with a "Total runs" card that sums `agents.reduce((s,a) => s + a.total_runs, 0)` — same Zap icon, copy "Total runs".

**Status filter pills** (all/running/stopped): keep them, but they now filter by the *derived* container state from `statuses[id]?.runtime_running`. While a row's status is still "loading" treat it as matching `all` only (not running and not stopped).

**Loading state** (agents === null && !listError): render a centered Loader2 spinner + "Loading your deployed agents…" — copy MyAgentsPanel lines 82–89 verbatim into a div that takes the place of the ScrollArea.

**Empty state** (agents !== null && agents.length === 0): replace the existing "No agents found" block with: heading "No agents deployed yet" + body "Head to the playground to deploy your first agent." + a link `<Link href="/playground">Go to playground</Link>` styled as the existing primary Button. Keep the Activity icon.

**Error state** (listError !== null): render an amber-bordered card (mirror MyAgentsPanel lines 91–98) with `Couldn't load your agents: {listError.message}` + a Retry button calling `loadAgents`.

**Search filter**: keep the existing client-side `searchQuery.toLowerCase().includes(...)` filter, but apply it against `agent.name` and `agent.recipe_name` (not `agent.clone`).

**DropdownMenu**: keep "View Details" → `/dashboard/agents/${agent.id}`, keep "View Logs" → `/dashboard/agents/${agent.id}/logs`, keep "Settings" → `/dashboard/agents/${agent.id}/settings`. **Remove** the "Duplicate" item (no endpoint) and **remove** the "Delete" item entirely (no `DELETE /v1/agents/:id` endpoint exists per scope_constraints). Adjust DropdownMenuSeparator accordingly so we don't ship a separator with nothing after it.

**Stop button render**: leave the button visually present but DO NOT wire its onClick yet — Task 2 owns that. For Task 1 only: stub the button onClick to a no-op (`onClick={() => {}}`) and add a `disabled` prop that is `true` when status is "loading". This keeps Task 1's diff isolated to data wiring; the wire-up lives in Task 2.

**Start button render** (visible only when status indicates not-running): change it from a button to `<Button asChild><Link href={\`/playground?recipe=\${agent.recipe_name}&model=\${encodeURIComponent(agent.model)}\`}>Start</Link></Button>`. Inline comment must say `// /start requires Bearer + channel_inputs (see AgentStartRequest); /playground is where the user supplies them. Re-deploying via /playground UPSERTs into the same agent_instances row keyed by (user, recipe, model).`

**No new files. No edits outside frontend/app/dashboard/page.tsx.** Do not touch `frontend/lib/api-types.ts` (existing types already cover everything). Do not touch `frontend/components/`.
  </action>
  <verify>
    <automated>cd frontend && grep -n "mockAgents\|messagesProcessed\|uptime\|lastActive\|toggleAgentStatus\|deleteAgent" app/dashboard/page.tsx; test $? -eq 1 && grep -n "apiGet.*v1/agents\|AgentListResponse\|AgentStatusResponse\|parseApiError" app/dashboard/page.tsx | wc -l | xargs -I {} test {} -ge 4</automated>
    <manual>
      1. `cd frontend && pnpm dev` (kill any existing :3000 first per CLAUDE.md).
      2. Ensure the api_server stack is up locally per .planning/STATE.md (the AP_CHANNEL_MASTER_KEY + docker compose recipe).
      3. Visit http://localhost:3000/dashboard.
         - Expect: a brief spinner, then either the empty state ("No agents deployed yet" with /playground link) OR a card per real agent.
         - DO NOT expect: "Customer Support Bot", "Code Assistant", "Research Agent", "Data Analyst" (the mock names).
      4. Stop the api_server (`docker compose down api` or kill it). Reload /dashboard.
         - Expect: amber error card with "Couldn't load your agents:" + Retry button. Click Retry → the same error or success when api comes back.
      5. Bring api back up. With at least one agent in DB, hit /dashboard.
         - Expect: each row shows a status pill ("checking…" → then "running" / "stopped" / "never started" / "status unavailable") within ~2s.
         - Expect: stats card shows correct running count + total agents + summed total runs.
    </manual>
  </verify>
  <done>
    - `app/dashboard/page.tsx` no longer contains the strings `mockAgents`, `messagesProcessed`, `uptime`, `lastActive`, `toggleAgentStatus`, `deleteAgent`.
    - `apiGet<AgentListResponse>("/api/v1/agents")` is called on mount.
    - `apiGet<AgentStatusResponse>` is called per-agent on mount.
    - Loading / error / empty / populated states all render correctly against the real api_server.
    - Start button is a Link to /playground; Stop button exists but is a no-op (Task 2 wires it).
    - Manual verify steps above all pass.
    - One git commit: `feat(quick/260419-moq): replace dashboard mockAgents with real /v1/agents + per-row /status`.
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire Stop button to POST /v1/agents/:id/stop with Bearer prompt + 2s /status polling until terminal</name>
  <files>frontend/app/dashboard/page.tsx</files>
  <read_first>
    1. The state machine added in Task 1 — Task 2 builds on it; do not refactor it.
    2. frontend/components/playground-form.tsx lines 313–390 — Bearer collection + clear-after-use pattern. Specifically: collect Bearer in a local `byok` state, send via `{ Authorization: \`Bearer \${byok}\` }` headers arg to `apiPost`, clear the state in a finally block UNLESS a follow-up call is pending.
    3. frontend/lib/api.ts apiPost signature — confirm headers go in arg 3 not arg 2.
    4. api_server/src/api_server/routes/agent_lifecycle.py lines 529–642 — confirm /stop response shape and that 401 fires without Bearer (the value is parsed but not forwarded, but the gate is enforced — we MUST send a non-empty Bearer).
  </read_first>
  <action>
**Add state**:
- `const [stoppingId, setStoppingId] = useState<string | null>(null)` — which row is mid-stop
- `const [bearerPromptFor, setBearerPromptFor] = useState<string | null>(null)` — agent.id whose Stop click triggered the prompt
- `const [bearerInput, setBearerInput] = useState("")` — controlled input value, cleared on submit AND on cancel
- `const [stopError, setStopError] = useState<{ id: string; message: string } | null>(null)` — per-row error surface

**Stop click handler** (`onStopClick(agent: AgentSummary)`):
1. If `stoppingId !== null` (another stop in flight) → no-op (UI already disables others).
2. Set `setBearerPromptFor(agent.id)`.

**Bearer-prompt UI** (a small inline `<Dialog>` from `@/components/ui/dialog`, OR a conditional render below the row card — pick the Dialog for cleaner UX since Dialog is already a project ui primitive):
- Title: "Confirm stop for {agent.name}"
- Body: a single password-type `<Input>` bound to `bearerInput` with placeholder "Bearer key (any non-empty value works for /stop — your provider key)". Helper text: "The /stop endpoint requires an Authorization: Bearer header but does not read its value. Your input is cleared from React state immediately after the request."
- Two buttons: Cancel (`setBearerPromptFor(null); setBearerInput("")`) and Stop (`onConfirmStop(agent.id)`); Stop button is disabled when `bearerInput.trim().length === 0`.

**`onConfirmStop(agentId)` flow**:
1. `setStoppingId(agentId); setBearerPromptFor(null); setStopError(null)`
2. `const key = bearerInput.trim(); setBearerInput("")` — clear from React state BEFORE the await (mirror playground-form discipline).
3. `try { await apiPost<AgentStopResponse>(\`/api/v1/agents/\${agentId}/stop\`, undefined, { Authorization: \`Bearer \${key}\` }) } catch (e) { setStopError({ id: agentId, message: parseApiError(e).message }); setStoppingId(null); return; }`
4. Begin polling: `await pollUntilStopped(agentId)` (defined below).
5. After polling resolves: `await loadAgents()` (refetch the full list so total_runs / last_run_at are fresh). Then `setStoppingId(null)`.

**`pollUntilStopped(agentId)` flow** (every 2s, max 30 attempts = 60s ceiling):
- `for (let i = 0; i < 30; i++) { await sleep(2000); try { const s = await apiGet<AgentStatusResponse>(\`/api/v1/agents/\${agentId}/status\`); setStatuses(prev => ({ ...prev, [agentId]: s })); if (!s.runtime_running) return; } catch { /* keep polling — transient errors don't break the loop */ } }`
- Use `useRef<AbortController | null>(null)` to cancel pending status fetches when the component unmounts mid-poll. Pass `signal` via `apiGet`'s `ApiCallOptions`.
- Local `sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))` helper at module scope (NOT inside the component).

**Stop button render update** (replace the Task-1 stub):
- `disabled` when `stoppingId !== null && stoppingId !== agent.id` (another row is mid-stop) OR when `statuses[agent.id]` is "loading" OR when the row's `runtime_running !== true`.
- When `stoppingId === agent.id`: render an inline Loader2 + "Stopping…" copy. Button still disabled.
- onClick → `onStopClick(agent)`.

**Per-row error surface**: when `stopError?.id === agent.id`, render a single line of red text below the action buttons: `Stop failed: {stopError.message}` plus a small "Dismiss" link that clears `stopError`. The error MUST NOT block the user from clicking Stop again with a fresh Bearer.

**Cleanup on unmount**: in a `useEffect` cleanup, call the AbortController abort + flag a mounted ref so any in-flight `setStatuses`/`setStoppingId` checks bail.

**No new files. Diff is additive on top of Task 1's `app/dashboard/page.tsx`.** Do not touch any other file. Do not introduce a new shared component.
  </action>
  <verify>
    <automated>cd frontend && grep -n "apiPost.*v1/agents.*stop\|Authorization.*Bearer\|stoppingId\|pollUntilStopped" app/dashboard/page.tsx | wc -l | xargs -I {} test {} -ge 4 && grep -n "setBearerInput(\"\")\|setBearerInput('')" app/dashboard/page.tsx</automated>
    <manual>
      1. Bring api_server + frontend back up (kill previous :3000 first per CLAUDE.md).
      2. From /playground, deploy a hermes+telegram agent end-to-end so you have one in `running` state. Confirm /status returns `runtime_running: true` for it.
      3. Visit /dashboard. Find that agent's row — pill should show "running".
      4. Click Stop. The confirm Dialog opens.
         - Click Cancel — Dialog closes, no request sent (verify via api_server logs: no POST /v1/agents/.../stop entry).
      5. Click Stop again. Type any non-empty string into the Bearer input. Click the Stop confirm.
         - Expect: Dialog closes, button shows "Stopping…" + spinner, other rows' Stop buttons are disabled.
         - Within ~2–10s the pill flips to "stopped", "Stopping…" reverts, the row's last_run_at refreshes (because loadAgents re-runs).
         - Open `docker ps` — the agent's container is gone.
      6. Click Stop on a non-running row → button is disabled (no Dialog).
      7. Stop the api_server, then click Stop on a running row + submit Bearer → expect a red "Stop failed:" line below the row + button re-enabled. Bring api back up, click Stop again → succeeds.
      8. While "Stopping…" is showing, refresh the page → polling stops cleanly (no console errors about setting state on unmounted component).
    </manual>
  </verify>
  <done>
    - Stop button on /dashboard hits POST /api/v1/agents/:id/stop with a real Bearer header.
    - After /stop returns, polling GET /api/v1/agents/:id/status every 2s flips the pill to "stopped" within the polling window.
    - The row's data refreshes via `loadAgents` after polling resolves.
    - Bearer input is cleared from React state before the await (grep for `setBearerInput("")` immediately followed by `apiPost`).
    - Per-row stop error renders + can be dismissed; user can retry without a page reload.
    - In-flight polling is cancelled on unmount via AbortController.
    - Manual verify steps above all pass.
    - One git commit: `feat(quick/260419-moq): wire dashboard Stop to POST /v1/agents/:id/stop with Bearer prompt + 2s /status polling`.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → /api/v1/* | User-supplied Bearer in dialog crosses to api_server via proxy |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-260419-moq-01 | Information Disclosure | Bearer key value retained in React state | mitigate | Clear `setBearerInput("")` BEFORE the apiPost await (mirrors playground-form pattern lines 376–386); the local `key` var is scoped to the handler closure and dies when it returns |
| T-260419-moq-02 | Information Disclosure | Bearer key in browser devtools network tab | accept | This is the same posture as playground-form `/runs` and `/start` calls today; all four endpoints take Bearer in the header — frontend sees plaintext on the wire by design (BYOK model). Mitigation lives at HTTPS termination + the api_server's existing access-log middleware that drops Authorization |
| T-260419-moq-03 | Denial of Service | Per-row /status polling could starve the API if many agents | mitigate | Polling is gated to ONLY the row currently mid-stop (`stoppingId === agent.id`) via the for-loop in `pollUntilStopped`. Initial mount fetches statuses ONCE per agent in parallel via `Promise.allSettled` — bounded by `agents.length` |
| T-260419-moq-04 | Tampering | Hardcoded user identity (ANONYMOUS_USER_ID) means any visitor sees+stops any agent | accept | Inherited Phase 19/22a posture documented in `routes/agents.py` and `routes/agent_lifecycle.py` source comments. OAuth-track (Phase 22c) replaces the resolver; this quick task does not move that gate. Per scope_constraints "DO NOT touch login/layout — waits for OAuth" |
</threat_model>

<verification>
- `mockAgents` const removed from `frontend/app/dashboard/page.tsx` (grep returns no hits).
- `apiGet<AgentListResponse>("/api/v1/agents")` is called on mount.
- `apiGet<AgentStatusResponse>("/api/v1/agents/:id/status")` is called per agent on mount.
- `apiPost<AgentStopResponse>("/api/v1/agents/:id/stop", undefined, { Authorization: "Bearer ..." })` is called from the Stop confirm flow.
- Polling resolves the pill to "stopped" within ≤30 attempts (60s ceiling).
- Bearer string is cleared from React state before the network await.
- No new endpoints invented. No new files. No types added to api-types.ts. No edits outside `frontend/app/dashboard/page.tsx`.
- Login page untouched. Layout's "Alex Chen" hardcoded user untouched.
- No DELETE button (no `DELETE /v1/agents/:id` endpoint exists; row removed from DropdownMenu).
- Recipe accent / tagline catalogs in `playground-form.tsx` and `my-agents-panel.tsx` UNTOUCHED (out of scope — separate Rule-2 cleanup task per ACTION-LIST P2).
</verification>

<success_criteria>
1. `/dashboard` renders ONLY data the api_server returns. No mock strings remain (grep for the four mock agent names: "Customer Support Bot", "Code Assistant", "Research Agent", "Data Analyst" returns 0 hits in `frontend/app/dashboard/page.tsx`).
2. Loading / error / empty / populated states each render correctly against the real local api_server, verified manually per Task 1 step 5 + Task 2 step 5.
3. Clicking Stop with a non-empty Bearer reaps the container in docker ps within the polling window.
4. The diff is two atomic commits totaling one file.
</success_criteria>

<output>
After completion, create `.planning/quick/260419-moq-replace-dashboard-mockagents-with-real-v/260419-moq-SUMMARY.md` per the standard quick-task SUMMARY template, including:

- One paragraph on what shipped
- The two commit SHAs
- A Rule 1 / Rule 2 / Rule 3 self-check (NO MOCKS / dumb client / works locally end-to-end)
- The unaddressed-but-flagged items: (a) Start button redirects to /playground rather than starting in-place — `/start` requires channel_inputs the dashboard can't collect without becoming a deploy form; (b) `RECIPE_ACCENTS` still hardcoded in `my-agents-panel.tsx` per P2 scope constraint; (c) DELETE row removed from menu pending a real `DELETE /v1/agents/:id` endpoint; (d) ANONYMOUS_USER_ID inheritance unchanged (Phase 22c OAuth track owns).
</output>
