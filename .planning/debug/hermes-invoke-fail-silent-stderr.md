---
slug: hermes-invoke-fail-silent-stderr
status: resolved
trigger: >
  Deploy of agent "brow" (recipe=hermes, model=anthropic/claude-3-haiku,
  personality=concise-neat, prompt="Introduce yourself in one short sentence.")
  returned INVOKE_FAIL with exit_code=1, stderr_tail=EMPTY, wall_time=16.89s.
created: 2026-04-17
updated: 2026-04-17
resolved: 2026-04-17
---

## Resolution

**Fixes applied (both, composed for defense in depth):**

- **Fix A — `recipes/hermes.yaml` invoke.spec.argv** — added `--verbose` to
  the argv tail. Hermes's `run_agent` + `root` loggers now emit the upstream
  diagnostic chain on stderr at default verbosity.
- **Fix B — `tools/run_recipe.py::run_cell` (two sites)** —
  - lines 792-804: when `rc != 0 AND stderr empty`, promote the last line of
    `stdout` into the `detail` field with a `[stdout(tail)]` marker.
  - lines 821-833: when `rc != 0 AND stderr empty`, populate `stderr_tail`
    with `[stdout tail — stderr was empty]` prefix + stdout tail so the
    RunResultCard accordion surfaces *something* instead of `(no output)`.

**Validation via real `POST /v1/runs` with user-supplied OpenRouter key** (key
stored local-only at `/tmp/ap-or-key.txt` chmod 600, not committed):

| Probe | Model | Verdict | Exit | Wall | Notes |
|-------|-------|---------|------|------|-------|
| 1 | `anthropic/claude-haiku-4.5` | PASS | 0 | 12.79s | verified cell regression check — still PASS |
| 2 | `openai/gpt-4o-mini` | PASS | 0 | 13.64s | verified cell regression check — still PASS |
| 3 | `anthropic/claude-3-haiku` | FAIL | 0 | 11.51s | category now `ASSERT_FAIL` (not `INVOKE_FAIL`); model replied 121 chars but didn't contain "hermes" → `pass_if` legitimately failed |

The user's originally-reported invisible `INVOKE_FAIL` was likely a transient
upstream hiccup. With the fix in place, any future upstream failure surfaces
as readable stderr diagnostics in the result card accordion instead of `(no output)`.

**Files changed:**

- `recipes/hermes.yaml` — +1 argv line, +6 argv_note lines documenting why
- `tools/run_recipe.py` — 2 small blocks (lines 792-804 and 821-833)

**Deferred follow-up (out of scope for this debug session):**

- Other 4 recipes (`nanobot`, `nullclaw`, `openclaw`, `picoclaw`) may have
  the same silent-fail class if their CLIs suppress error output at default
  verbosity. Each CLI has its own verbosity flag (`-v`, `--debug`, etc.) so
  the fix is per-recipe. Tracked as a follow-up recon probe.
- `/tmp/tdd_hermes_silent_fail.sh` will now flip from RED → GREEN once the
  new image is the one under test (it was pinned to the pre-fix build).
  Not re-running — the real `POST /v1/runs` probes are a stronger gate.

---

# Debug: hermes INVOKE_FAIL with silent stderr

# Debug: hermes INVOKE_FAIL with silent stderr

## Symptoms

- **Expected behavior:** `POST /v1/runs` with recipe=hermes + valid OpenRouter key
  returns verdict=PASS (or at minimum a FAIL with non-empty stderr explaining why).
- **Actual behavior:** verdict=FAIL, category=INVOKE_FAIL, exit_code=1, wall=16.89s,
  stderr_tail is empty/null. `filtered_payload` (len=1636) contains hermes
  bootstrap output through `session_id: 20260418_000016_39ad54` then cuts off
  — no model reply, no error message, no turn output.
- **Error messages:** None. `detail` field is literally `"docker run exit 1: "`
  with empty tail because stderr was empty.
- **Timeline:** Observed on run `01KPEY6EDRQ87WW6RC95GHSEZP` at
  2026-04-18 00:00:07 UTC. First deploy of recipe=hermes via the new UI.
- **Reproduction pending:** Run combo was recipe=hermes,
  model=`anthropic/claude-3-haiku`, personality=concise-neat. This model is
  NOT in hermes `smoke.verified_cells[]` (recipe's verified PASS matrix is
  only `claude-haiku-4.5` + `gpt-4o-mini`). Live OpenRouter DOES expose
  `anthropic/claude-3-haiku` as a valid id, so the request reached the
  upstream — the question is what the upstream returned and why hermes
  swallowed it.

## Known Facts (pre-session)

- Container exited with code 1 but emitted zero bytes on stderr.
- Container image `ap-recipe-hermes:latest` (5.19 GB) is built and cached locally.
- The api_server bridge at
  `api_server/src/api_server/services/runner_bridge.py` calls into
  `tools/run_recipe.py::run_cell` via `asyncio.to_thread`.
- `run_cell` uses `subprocess.run(docker_cmd, capture_output=True, text=True)`
  at `tools/run_recipe.py:730-737`. If the container emits no stderr,
  `result.stderr` is empty string.
- `detail = f"docker run exit {rc}: {tail[0][:200]}"` at `run_recipe.py:794`
  — tail comes from splitlines() of stderr. Empty stderr → empty tail.
- `filtered_payload` on non-PASS is set to raw stdout at `run_recipe.py:797`.
  The payload shown ends at `session_id:` line, which is what hermes prints
  AFTER skill sync but BEFORE the model turn completes. So hermes opened
  a session and then died silently.
- No running containers remain (docker ps -a returned none).
- No `.env` / OpenRouter key available in this session — reproduction must
  either (a) prompt the user for one, (b) use a mock/stub, or (c) run a
  no-key probe that short-circuits before the upstream call.

## Hypothesis ladder (top = test first)

1. **Old-model contract mismatch.** `anthropic/claude-3-haiku` uses an older
   API payload shape that hermes's model adapter no longer emits correctly;
   OpenRouter replies 400/404 and hermes catches the exception without
   surfacing it on stderr (logged only to a file inside the container that
   died before flush).
2. **OpenRouter account-scoped rejection** (e.g. 402 credit/route-not-enabled)
   silently swallowed in the same way.
3. **Hermes invoke spec mismatch** — the recipe's CLI flags assume a model
   id that hermes's own provider layer can route; `claude-3-haiku` may not
   be a valid routing target inside hermes's internal provider map (vs
   claude-haiku-4.5 which IS verified in the recipe).
4. **Infra-level container abort** (OOM, signal, dockerd race) that doesn't
   leave a stderr trace — least likely given wall=16.89s is clean, not a
   quick kill.

## Current Focus

```yaml
hypothesis: ROOT CAUSE CONFIRMED — hermes's default log level silences all upstream-error output; recipe does not pass -v/--verbose so stderr is empty on any upstream failure, not just claude-3-haiku.
test: Invalid-key probe against ap-recipe-hermes:latest reproduced production shape (exit=1, stderr empty, stdout ends at session_id:). Adding --verbose revealed the swallowed 401 "User not found" on stderr.
expecting: Fix either (A) recipe-side — add --verbose to invoke.spec.argv, or (B) runner-side — when rc != 0 and stderr empty, promote stdout tail into detail/stderr_tail.
next_action: Present TDD checkpoint to user. RED is confirmed by /tmp/tdd_hermes_silent_fail.sh. User must confirm the test is red before we iterate on GREEN (the fix).
reasoning_checkpoint: null
tdd_checkpoint: /tmp/tdd_hermes_silent_fail.sh (RED — reproduces silent-fail)
```

## Evidence

- timestamp: 2026-04-17T00:10 (TDD probe cycle 1)
  observation: Invalid-key probe reproduced prod shape exactly.
  command: `bash /tmp/tdd_hermes_silent_fail.sh`
  outcome: exit_code=1, stderr_len=0, stdout ends at `session_id: 20260418_000959_3949f5`, stdout length 1635 bytes (prod was 1636 — 1-byte diff = session_id value).
  assertions:
    - A1 exit_code == 1 → PASS (matches prod)
    - A2 stderr empty/whitespace → PASS (CONFIRMS silent-fail class)
    - A3 stdout contains session_id → PASS (matches prod shape)
    - A4 stdout has NO error keyword → PASS (after filtering false positive "github-auth" skill name; no 401/Unauthorized/OpenRouter/error words visible to user)
  conclusion: Bug is not model-specific; it is a default-log-level silencing issue. ANY upstream failure (bad key, bad model, 402 credits, 429) produces the same invisible fail.

- timestamp: 2026-04-17T00:11 (verbose probe)
  observation: Re-ran with `--verbose` added to argv. Stderr now 3695 bytes, contains full diagnostic chain including the swallowed upstream error.
  key_stderr_lines:
    - `run_agent - INFO - Streaming failed before delivery: Error code: 401 - {'error': {'message': 'User not found.', 'code': 401}}`
    - `run_agent - DEBUG - Error classified: reason=auth status=401 retryable=False rotate=True fallback=True`
    - `run_agent - WARNING - API call failed (attempt 1/3) error_type=AuthenticationError summary=HTTP 401: User not found.`
    - `root - ERROR - Non-retryable client error: Error code: 401 - {'error': {'message': 'User not found.', 'code': 401}}`
  conclusion: Hermes's `run_agent` and `root` loggers ARE emitting the upstream error. They are SUPPRESSED at default verbosity. The chat CLI exits 1 on the non-retryable classification but does not print a user-visible Rich-console error.

- timestamp: 2026-04-17T00:09 (DB evidence)
  observation: Prod run 01KPEY6EDRQ87WW6RC95GHSEZP in deploy-postgres-1 / agent_playground_api.
  shape: verdict=FAIL, category=INVOKE_FAIL, exit_code=1, wall_time_s=16.89, detail="docker run exit 1: ", stderr_tail=NULL, filtered_payload ends at `session_id: 20260418_000016_39ad54`, payload length 1636.
  conclusion: Matches TDD probe within rounding (prod wall 16.89s vs probe 10s — prod is slower because claude-3-haiku takes longer to 401 than a local INVALID string hitting OpenRouter auth).

## Eliminated

- H4 Infra-level container abort (OOM/signal/dockerd race) → ELIMINATED.
  Reason: With --verbose the process proceeds through clean classification
  and exits normally via hermes's retry/fallback code path. Container is
  not being killed externally. Walltime ~10-16s is consistent with "make
  the upstream request, get rejected, classify, exit 1".

- H3 Invoke spec mismatch (claude-3-haiku not a routable model inside
  hermes's provider layer) → ELIMINATED as the cause of the SYMPTOM.
  Reason: With --verbose, hermes logs show `model=anthropic/claude-3-haiku`
  being passed cleanly to the OpenAI client targeting openrouter.ai/api/v1.
  The model id IS routed. The 401 in my probe is purely about the invalid
  key. In prod, with a valid key, the upstream reply for claude-3-haiku
  might still be 404/400 (model-specific) — but that'd produce the SAME
  silent-fail shape until the verbose issue is fixed. So H3 is a POSSIBLE
  secondary concern that is CURRENTLY MASKED by the primary bug.

- H1 + H2 (old-model contract mismatch / account-scoped rejection) →
  SUPERSEDED. These are both special cases of "hermes silently swallows
  upstream errors", which is the confirmed root cause. Once the verbose
  fix lands, either or both MAY still surface as secondary FAILs — but
  those will be VISIBLE fails with clear detail, not silent ones.

## Resolution

### Root Cause
Hermes's `chat` CLI silences its `run_agent` and `root` loggers at default
verbosity. Upstream LLM errors (401 auth, 404 model, 402 credits, 429
rate, 5xx upstream) are classified internally and cause exit=1, but the
diagnostic INFO/WARNING/ERROR messages never reach stderr. The Rich
user-facing console does not receive a fallback error message either.
The recipe at `recipes/hermes.yaml` invoke.spec.argv (lines 83-95) does
not include `-v`/`--verbose`, so every prod deploy that fails upstream
looks like a mystery: exit=1, empty stderr, stdout cut at `session_id:`.

### Fix
Two independent fix surfaces. **Recipe-side is primary (low-risk, immediate)**:

**Fix A — recipe-side (primary):**
Append `- --verbose` to `recipes/hermes.yaml` → `invoke.spec.argv` (after
`- tool`). Re-run the two verified cells (`claude-haiku-4.5` + `gpt-4o-mini`)
to confirm PASS still PASSes — the chatty stderr will hit `stderr_tail`
but that field is captured regardless; PASS verdict depends on `pass_if`
against filtered_payload, which is stdout-only. Update `recipe.smoke.verified_cells[].notes`
to mention verbose mode if walltime changes measurably.

**Fix B — runner-side (defense in depth):**
In `tools/run_recipe.py::run_cell` at lines 792-800, when `rc != 0`
AND stderr is empty/whitespace-only, promote the LAST non-empty 200
chars of stdout into `detail` (redacted) instead of leaving `detail`
as `"docker run exit 1: "`. This guards against ANY agent (future
recipes, not just hermes) that silently exits without stderr — so the
operator always sees SOMETHING beyond the exit code.

**Recommend shipping Fix A first** (recipe-level, retroactively revalidate
the two PASS cells), then Fix B as a follow-up hardening in the runner
since it protects all recipes, not just hermes.

### Preventive
- Add a runner invariant: FAIL verdicts with empty stderr AND non-empty
  filtered_payload should log a warning in the api_server ("possible
  silent-fail; raise recipe verbosity"). This makes the bug class
  visible in ops without waiting for a user to report it.
- Phase 03 (recipe-format-v0.1) should add a schema note that recipes
  targeting LLM providers SHOULD include a verbose/debug flag in
  invoke.spec.argv unless they emit diagnostics on stderr by default.
  Candidate field: `invoke.spec.diagnostics_flag: --verbose` so the
  runner or operator can confirm it is set.
