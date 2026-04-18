# Phase 22a — Plan Verification

**Phase:** 22-channels-v0.2
**Plans verified:** 7 (22-01 through 22-07)
**Date:** 2026-04-18
**Verdict:** **PASS with 2 MINOR advisories** (fixable at execution time; no plan revision required)

---

## 2026-04-19 — Spike-sourced plan revisions absorbed (G1–G5)

The 5 gotchas documented in `22-SPIKES/RESULTS.md` §"Gotchas requiring plan revision" have been absorbed into the PLAN files. Each revision is a mechanical delta — no structural rewrite.

| ID | Spike | Plans touched | Summary |
|----|-------|---------------|---------|
| G1 | spike-02 | 22-02 | pyrage API — use module-level `pyrage.passphrase.encrypt/decrypt`; Recipient.from_str / Identity.from_str don't exist |
| G2 | spike-01 | 22-02 | New Task 0 — add `pyrage` + `cryptography` to `api_server/pyproject.toml`, introduce `AP_CHANNEL_MASTER_KEY` env, rebuild api_server image |
| G3 | spike-07 | 22-03, 22-05, 5 recipe YAMLs | Per-recipe `graceful_shutdown_s` (hermes 15, picoclaw 2, nullclaw 10, openclaw 5, nanobot 0); `sigterm_handled: true` on all except nanobot (false); `stop_persistent` skips SIGTERM when `sigterm_handled=false`; returns `force_killed: bool` surfaced through AgentStopResponse |
| G4 | spike-10 | 22-05, 22-06 | openclaw pair approve is ~60s cold-boot (not 2s). `docker exec` timeout 90s; response schema adds `wall_s`; endpoint rate-limit 3 req/min/user; PairingModal 90s fetch timeout + up-front UX disclosure + retry disabled until first response + spinner elapsed-time readout |
| G5 | spike-11 | 22-01, 22-05, 5 recipe YAMLs | `health_check` is a `oneOf` union (`process_alive` \| `http{port,path}`). Recipe YAMLs: hermes process_alive, picoclaw http 18790 `/health` (NOT `/ready` — 503 even when OK), nanobot http 18790 `/health`, openclaw http 18789 `/`, nullclaw process_alive. `GET /status` dual-branch probe with `curl \|\| wget` fallback for image toolchain variance |

**Next:** re-run plan-checker against the revised PLANs to confirm the absorbed deltas match the spike evidence before executing Wave 1.

---

## Per-plan verdict

| Plan | Wave | Hours | Status | Critical issues |
|------|------|-------|--------|-----------------|
| 22-01 schema + loader + TS mirror | 1 | 4 | PASS | none |
| 22-02 migration + age crypto | 1 | 4 | PASS | none |
| 22-03 runner `--mode persistent` | 2 | 5 | PASS (A1) | CLI Task 3 references nonexistent `load_recipes()` — inline fix |
| 22-04 runner_bridge wrappers | 2 | 2 | PASS | none |
| 22-05 HTTP endpoints | 3 | 6 | PASS (A2) | minor cross-plan contract check — already aligned |
| 22-06 frontend Step 2.5 + PairingModal | 4 | 7 | PASS | Task 2 is borderline large for a single commit — 7h estimate is tight |
| 22-07 E2E SC-03 gate | 5 | 4 | PASS | none |

**Total effort:** 32 hours

**Dependency graph** (verified cycle-free, forward-references-free):

```
Wave 1 (parallel):  22-01 ─┐    22-02 ─┐
                           │            │
Wave 2 (parallel):  22-03 ◄┘    22-04 ◄┘
                           │            │
Wave 3:             22-05 ◄┴────────────┘
                           │
Wave 4:             22-06 ◄┘
                           │
Wave 5:             22-07 ◄┘
```

---

## Per-SC coverage

| SC | Covered by | Verdict |
|----|-----------|---------|
| SC-01 schema additive | 22-01 Tasks 1/2/3 | PASS — jsonschema v0.1 + v0.2 branches under `oneOf`; Task 3 verify asserts all 5 recipes validate under v0.2 |
| SC-02 <90s start latency | 22-02 (atomic DB) + 22-03 (`run_cell_persistent` returns `boot_wall_s`) + 22-04 (bridge) + 22-05 (9-step flow with DB scope 1→await→DB scope 2) + 22-06 (UI) | PASS — hermes baseline 10s, openclaw worst ~120s; caller-supplied `boot_timeout_s` allows override with 180s default |
| SC-03 15 round-trips PASS | 22-07 Tasks 1/2/3 | PASS — MATRIX encodes 5 recipes × 3 rounds; openclaw routed via Anthropic; real Telegram + real Docker + real LLM (Rule 1 compliant) |
| SC-04 clean teardown | 22-02 Task 3 (partial unique index) + 22-03 Task 2 (SIGTERM → poll → force rm) + 22-05 Task 3 + 22-07 (trap + `docker ps -a` post-run) | PASS |
| SC-05 BYOK discipline | 22-02 (age + per-user HKDF KEK) + 22-03 (env-file 0o600 + unlink + widened redaction) + 22-05 (`_redact_creds`, no plaintext persisted) + 22-06 (`type="password"`, state cleared in `finally`) | PASS — token never reaches DB plaintext, log, argv, or long-lived React state |
| SC-06 upstream issue filed | OUT-OF-CODE | DEFERRED — tracked as retrospective item; `recipes/openclaw.yaml` already embeds the repro text |

---

## Cross-cutting verdicts

| Check | Status |
|---|---|
| **Rule 1 (no mocks)** | PASS — 22-07 uses real Telegram API, Docker, OpenRouter, Anthropic. Zero `mock_`/`unittest.mock` references anywhere. Cost accepted (~$0.02–0.05 per run). |
| **Rule 2 (dumb client, no catalogs)** | PASS — 22-06 renders all channel inputs via `allInputs.map(...)` derived from `GET /v1/recipes/:name`. `byokLabel` derived from `channel_provider_compat.supported[0]`. Zero `recipe.name === "openclaw"` checks in React state. |
| **Rule 3 (ship when local works)** | PASS — 22-07 Task 3 is a blocking human-verify checkpoint. 22-05 verify asserts route mounting. 22-06 runs `pnpm tsc --noEmit`. |
| **Rule 4 (root cause first)** | PASS — 22-05 catches `UniqueViolationError` at both INSERT and UPDATE sites; partial unique index is the root-cause mechanism. 22-01 docs why `$defs.category` must not be edited in place. |
| **Security (bot_token + channel_config)** | PASS — env-file 0o600 + unlink post-run mirror existing `OPENROUTER_API_KEY` handling. `_redact_api_key` widened for all secrets. age passphrase mode with HKDF-derived per-user KEK; cross-user decrypt verify test included. |
| **Atomicity** | PASS with note — 22-06 Task 2 is borderline large but scoped to one coherent user-facing feature; planner's 7h estimate tight but acceptable. |
| **Deviations flagged up-front** | PARTIAL — 22-03 flags `ensure_image`, 22-06 flags `SectionHeader.step` type, 22-06 flags pairingBearer lifecycle. Advisory A1 (below) identifies one gap. |

---

## Advisories (minor — fixable at execution time, no plan revision)

### A1 — Plan 22-03 Task 3 references nonexistent `load_recipes()`

- **Location:** 22-03-PLAN.md Task 3 CLI wiring (`recipe = load_recipes()[args.recipe]`)
- **Reality:** `tools/run_recipe.py` has `load_recipe(path: Path)` singular at line 114 taking a path. There is no plural `load_recipes()`.
- **Inline fix:** Executor writes `recipe_path = Path(f"recipes/{args.recipe}.yaml").resolve(); recipe = load_recipe(recipe_path)` — matches the existing primary CLI path.
- **Severity:** Minor. Secondary to main API path. Does not affect SC-02/04/05.

### A2 — Plan 22-05 Task 3 cross-plan contract (informational)

- **Location:** `running.get("channel_type")` in response mapping
- **Reality:** Plan 22-02 Task 3's `fetch_running_container_for_agent` DOES select `channel_type`. Contract aligned. No fix needed.
- **Severity:** Informational.

---

## Checker-identified gotchas for executors

1. `test/e2e_channels_v0_2.sh` reads `$TELEGRAM_ALLOWED_USER`; matrix populates both plural and singular — harness only needs one. OK.
2. `docs/RECIPE-SCHEMA.md` current version is v0.1.1 — Plan 22-01 correctly extends, not replaces.
3. `_import_run_recipe_module` uses `parents[4]` from `services/runner_bridge.py` — verified to resolve to repo root correctly.
4. `recipes/openclaw.yaml` does not yet have a `pairing:` block — Plan 22-05 Task 3 adds it via minor recipe edit; schema from 22-01 Task 2 accepts it as optional.
5. `SectionHeader` prop type swap from `number` to `number | string` is a micro-change scoped inline to 22-06.

---

## Ready to execute

```
/gsd-execute-phase 22a
```

Wave 1 (22-01 + 22-02) runs in parallel — no file overlap, no dependency. Executor picks up per-plan SUMMARY.md after each plan commits.

---

## 2026-04-18 — FINAL verification (post-I1/I2/I3 absorption)

**Verdict: PASS.** Three plan-checker advisories from the post-G1..G5-revision pass have been absorbed:

- **I1** — `22-04-PLAN.md:223-261` `execute_persistent_stop` now accepts `sigterm_handled: bool = True` and `recipe_name: str | None = None`, forwards both to `mod.stop_persistent`, guarantees `force_killed: bool` in result dict via `setdefault`.
- **I2** — `22-04-PLAN.md:264-333` `execute_persistent_status` now accepts `recipe_health_check: dict | None = None`; dual-branch probe (process_alive via `docker inspect`; http via `docker exec <c> sh -c 'curl ... || wget ...'`) hoisted into bridge-layer `_probe()`; returns `http_code: int | None` + `ready: bool | None`.
- **I3** — `22-06-PLAN.md:202-211` `AgentStopResponse` TS type mirrors backend Pydantic exactly: `force_killed: boolean` with G3 spike-07 comment.

**Cross-plan contract matrix — all 6 pairs aligned:**

| Field | 22-04 bridge | 22-05 route | 22-06 TS |
|---|---|---|---|
| stop: `sigterm_handled` kwarg | accepts | passes | n/a |
| stop: `recipe_name` kwarg | accepts | passes | n/a |
| stop: `force_killed` return | guarantees | surfaces | declares |
| status: `recipe_health_check` kwarg | accepts | passes | n/a |
| status: `http_code` return | returns | surfaces | declares |
| status: `ready` return | returns | surfaces | declares |

**Concurrency preserved** — `_probe()` is read-only `docker inspect` + `exec` + `logs`, wrapped in `asyncio.to_thread`, no new locks or semaphores required.

**All 6 SC covered; Rules 1-5 intact; spike evidence end-to-end propagated.**

**Only residual advisory:**

- **A1** (22-03 Task 3 line 609) — `load_recipes()` plural doesn't exist; inline fix at execution time: `recipe = load_recipe(Path(f"recipes/{args.recipe}.yaml").resolve())`. Secondary CLI debug path only; does NOT affect API/bridge path.

**Status: READY TO EXECUTE.** Next command: `/gsd-execute-phase 22a`.

---

## 2026-04-18 evening — Post-revision re-verification (commit `8f53881`)

**Verdict:** **REVISE_MINOR** — G1, G2, G3, G4, G5 are all absorbed in the plans that own them, recipes carry the correct per-recipe fields, and the 5 SCs remain covered. BUT two mechanical propagation gaps in Plan 22-04 break the contract with Plan 22-05, and one TS type + one known pre-existing advisory also need a one-liner each. All fixes are signature-level; no re-architecting required.

### Per-plan status post-revisions

| Plan | Status | G absorption | Notes |
|------|--------|--------------|-------|
| 22-01 | PASS | G5 absorbed cleanly | `$defs.health_check` is a `oneOf` union (lines 152-167); table at 168-175 mirrors spike-11 exactly including picoclaw `/health` NOT `/ready` gotcha. `$defs.channel_entry.pairing` declared. |
| 22-02 | PASS | G1 + G2 absorbed cleanly | Task 0 (lines 98-138) prepends pyrage + cryptography + AP_CHANNEL_MASTER_KEY env + image rebuild BEFORE Task 1 migration. Task 2 lines 247-252 use `pyrage.passphrase.encrypt/decrypt` directly and explicitly call out that `Recipient.from_str` / `Identity.from_str` don't exist, pointing at spike-02. |
| 22-03 | PASS with A1 unfixed | G3 absorbed cleanly | Per-recipe table at Task 2 lines 381-387; `sigterm_handled: false` path skips SIGTERM and logs warning (not error); `force_killed: bool` surfaced in return dict (line 478); caller contract example shows recipe.persistent.spec lookup (lines 484-494). **Advisory A1 from first pass still present**: Task 3 line 609 reads `recipe = load_recipes()[args.recipe]` — `load_recipes()` plural doesn't exist in `tools/run_recipe.py`; should be `load_recipe(Path(f"recipes/{args.recipe}.yaml").resolve())`. Marked "minor, fixable at execution time" in first pass but still worth flagging. |
| 22-04 | **REVISE** | **G3 and G5 NOT propagated** | See issues I1 + I2 below. The new kwargs (`sigterm_handled`, `recipe_name` for stop; `recipe_health_check` for status) appear in Plan 22-05's call sites but NOT in Plan 22-04's signatures. Plan will fail to compile/type-check at the bridge layer. |
| 22-05 | PASS | G3 + G4 + G5 absorbed cleanly | G3: `/stop` reads `persistent.spec.graceful_shutdown_s + sigterm_handled` (lines 559-562), forwards both to `execute_persistent_stop` with `recipe_name`, surfaces `force_killed` in `AgentStopResponse` (line 214+ and 583). G4: `/pair` has `timeout_s=90` (line 739), `wall_s` alias field (line 229+752), endpoint-specific 3/min rate limit comment (lines 699-704). G5: `/status` reads per-recipe `health_check`, forwards as `recipe_health_check` to `execute_persistent_status` (lines 614-621), surfaces `http_code` + `ready` in `AgentStatusResponse` (lines 204-206). Dual-branch probe reference impl at lines 641-674 including `curl||wget` fallback. |
| 22-06 | PASS with I3 | G4 absorbed cleanly | PairingModal has 90s fetch timeout (line 608), up-front disclosure copy "up to 60 seconds" (lines 702-706), submit button disabled during request (line 757), elapsed-time readout ticking every 500ms (lines 630-647). **Issue I3**: `AgentStopResponse` TS type at lines 202-209 is missing the new `force_killed: boolean` field added by Plan 22-05's Pydantic model. One-line fix. |
| 22-07 | PASS | n/a (unchanged since last pass) | E2E matrix + telegram harness + bash driver all covered. |

### Per-SC coverage post-revisions

| SC | Covered by | Verdict |
|----|-----------|---------|
| SC-01 schema additive | 22-01 Task 2 `oneOf` + health_check union | PASS (G5 strengthens, not weakens) |
| SC-02 <90s start | 22-02 (DB) + 22-03 (boot_wall_s) + 22-04 (bridge) + 22-05 (`/start`) + 22-06 (UI) | PASS — unchanged; boot_timeout_s=180 default covers openclaw ~120s worst case |
| SC-03 15 round-trips | 22-07 matrix | PASS (unchanged) |
| SC-04 clean teardown | 22-03 (G3 per-recipe path including nanobot force-kill) + 22-05 (surfaces force_killed) + 22-07 (trap cleanup) | PASS — strengthened by G3: nanobot's SIGTERM-ignore path is handled cleanly rather than timing out |
| SC-05 BYOK discipline | 22-02 (age + HKDF KEK, now with correct pyrage API) + 22-03 (env-file 0o600 + unlink + widened redaction) + 22-05 (`_redact_creds`) + 22-06 (`type="password"`) | PASS — G1 fix makes crypto actually runnable; G2 env var addition prevents plaintext fallback in prod |
| SC-06 upstream issue | OUT-OF-CODE | DEFERRED (unchanged) |

### Per-G absorption verdict

| G | Status | Evidence |
|---|--------|----------|
| G1 pyrage API | **ABSORBED** | 22-02 Task 2 lines 246-252 use `pyrage.passphrase.encrypt(plaintext, passphrase)` / `decrypt(ciphertext, passphrase)` directly; spike-02 pointer present; no `Recipient.from_str` references remain. |
| G2 deps + env | **ABSORBED** | 22-02 Task 0 lines 98-138 prepend pyrage>=1.2 + cryptography>=42 to pyproject.toml; AP_CHANNEL_MASTER_KEY env template in .env.prod + compose passthrough; image rebuild step explicit. Task 0 runs BEFORE Task 1 (migration). Spike-01 pointer present. |
| G3 SIGTERM per-recipe | **PARTIALLY ABSORBED** | 22-03 Task 2 fully revised (table + warning log + force_killed field); 5 recipe YAMLs carry correct per-recipe values (hermes 15/true, picoclaw 2/true, nullclaw 10/true, openclaw 5/true, nanobot 0/false); 22-05 `/stop` forwards all G3 fields + surfaces force_killed. **GAP: 22-04's `execute_persistent_stop` signature only accepts `graceful_shutdown_s` + `data_dir` — missing `sigterm_handled` and `recipe_name` kwargs that 22-05 calls with. This is a contract break between waves 2 and 3.** |
| G4 openclaw pair latency | **ABSORBED** | 22-05 Task 3 lines 680-752: 90s `timeout_s`, `wall_s` alias field, 3/min rate limit comment. 22-06 Task 3 lines 607-767: 90s fetch timeout with AbortController, up-front 60s disclosure copy, submit button disabled during in-flight, elapsed-time readout. Spike-10 pointers in both plans. |
| G5 health_check oneOf | **PARTIALLY ABSORBED** | 22-01 Task 2 schema lines 152-175 (oneOf union + per-recipe table including picoclaw `/health` gotcha); 5 recipe YAMLs carry correct `health_check` blocks matching spike-11; 22-05 Task 3 lines 591-674 forward `recipe_health_check` and surface `http_code`+`ready` in response. **GAP: 22-04's `execute_persistent_status` signature only accepts `log_tail_lines` — missing `recipe_health_check` kwarg, and body does only `process_alive`-style inspect. The dual-branch reference impl lives in 22-05 Task 3 but 22-04 is the file that will actually implement `execute_persistent_status` body.** |

### Blocking issues (must fix before `/gsd-execute-phase 22a`)

**I1 — Plan 22-04 Task 2: `execute_persistent_stop` signature missing G3 kwargs.**
- File: `.planning/phases/22-channels-v0.2/22-04-PLAN.md`
- Lines 222-250 (`execute_persistent_stop` block)
- Current signature:
  ```python
  async def execute_persistent_stop(container_id, *, graceful_shutdown_s: int = 5, data_dir: str | None = None) -> dict
  ```
- Required signature (to match Plan 22-05 call site at 22-05 line 564-570):
  ```python
  async def execute_persistent_stop(
      container_id: str,
      *,
      graceful_shutdown_s: int,          # remove default — recipe-sourced, always passed
      sigterm_handled: bool = True,
      recipe_name: str | None = None,
      data_dir: str | None = None,
  ) -> dict[str, Any]:
  ```
- And the `asyncio.to_thread(mod.stop_persistent, ...)` call (22-04 lines 236-242) must forward `sigterm_handled=sigterm_handled` and `recipe_name=recipe_name` — Plan 22-03 Task 2's `stop_persistent` already accepts them.
- Also: the truth-list at 22-04 lines 13-19 says "No lock/Semaphore (stop is cheap and concurrent-safe)" — still correct, no change. Just add to the must_haves truths: "`execute_persistent_stop` forwards `sigterm_handled` + `recipe_name` from the caller so G3's per-recipe teardown path works."

**I2 — Plan 22-04 Task 2: `execute_persistent_status` signature missing G5 kwarg + body missing http branch.**
- File: `.planning/phases/22-channels-v0.2/22-04-PLAN.md`
- Lines 253-286 (`execute_persistent_status` block)
- Current signature:
  ```python
  async def execute_persistent_status(container_id, *, log_tail_lines: int = 50) -> dict
  ```
- Required signature (to match Plan 22-05 call site at 22-05 line 617-621):
  ```python
  async def execute_persistent_status(
      container_id: str,
      *,
      recipe_health_check: dict,          # {"kind": "process_alive"} | {"kind": "http", "port": int, "path": str}
      log_tail_lines: int = 50,
  ) -> dict[str, Any]:
  ```
- And the inline `_probe()` body (22-04 lines 265-285) must branch on `recipe_health_check["kind"]` — process_alive via `docker inspect`, http via `docker exec ... curl -s -o/dev/null -w'%{http_code}' ... || wget -qO/dev/null ...`. Plan 22-05 Task 3 lines 646-673 has the verbatim reference implementation; hoist it into Plan 22-04's `_probe()` so it ships in the bridge layer (routes/agent_lifecycle.py then only needs to pass the recipe_health_check dict through; the dual-branch logic doesn't belong in the route handler).
- Return dict must include `http_code: int | None` and `ready: bool | None` (in addition to current `running`, `exit_code`, `log_tail`) — 22-05's `AgentStatusResponse` at lines 193-207 expects them.

**I3 — Plan 22-06 Task 1: `AgentStopResponse` TS type missing G3 `force_killed` field.**
- File: `.planning/phases/22-channels-v0.2/22-06-PLAN.md`
- Lines 202-209
- Current:
  ```typescript
  export type AgentStopResponse = {
    agent_id: string;
    container_row_id: string;
    container_id: string;
    stopped_gracefully: boolean;
    exit_code: number;
    stop_wall_s: number;
  };
  ```
- Required (mirror Plan 22-05 Pydantic `AgentStopResponse` at 22-05 lines 209-216):
  ```typescript
  export type AgentStopResponse = {
    agent_id: string;
    container_row_id: string;
    container_id: string;
    stopped_gracefully: boolean;
    force_killed: boolean;   // G3 (spike-07): true when recipe has sigterm_handled=false (nanobot) OR SIGTERM timed out
    exit_code: number;
    stop_wall_s: number;
  };
  ```
- Note: Plan 22-06's UI doesn't currently render `force_killed` to the user — that's fine for this phase. But the type must match the server response shape so `pnpm tsc --noEmit` passes once Plan 22-05 ships. No component change required.

### Minor advisories (not blocking — same classification as first pass)

**A1 (unchanged) — Plan 22-03 Task 3 references `load_recipes()` plural.**
- File: `.planning/phases/22-channels-v0.2/22-03-PLAN.md`
- Line 609: `recipe = load_recipes()[args.recipe]`
- Inline fix at execution time: `recipe = load_recipe(Path(f"recipes/{args.recipe}.yaml").resolve())`. Same severity as first pass — doesn't affect the primary API path (runner_bridge uses `_import_run_recipe_module()`), only the manual CLI debug seam.

### Cross-cutting checks (unchanged)

| Check | Status |
|-------|--------|
| Rule 1 (no mocks) | PASS — 22-07 hits real Telegram, real Docker, real LLM |
| Rule 2 (dumb client, no catalogs) | PASS — 22-06 all channel inputs from `GET /v1/recipes/:name`, byokLabel derived from `channel_provider_compat`, no hardcoded `"openclaw"` string checks |
| Rule 3 (ship when local works) | PASS — 22-07 Task 3 is the blocking human-verify checkpoint |
| Rule 4 (root cause first) | PASS — G1-G5 all resolved via spike evidence before plan revisions, not by silencing errors |
| Rule 5 (test everything before planning) | **SATISFIED** — 10 spikes ran; 5 gotchas surfaced; plans revised with per-recipe empirical values; no more untested mechanisms |
| Security (bot_token + channel_config) | PASS — G2 adds AP_CHANNEL_MASTER_KEY prod guard; G1 fix makes pyrage actually callable |
| Atomicity | PASS — revisions are mechanical field additions; no plan exceeded borderline threshold |
| Dependency graph | PASS — cycle-free, no forward refs, waves unchanged (1: 22-01+22-02; 2: 22-03+22-04; 3: 22-05; 4: 22-06; 5: 22-07) |

### Recommendation

**REVISE_MINOR.** Three mechanical fixes (I1, I2, I3) in two files (22-04, 22-06). Total edit surface: ~30 lines across 3 code blocks. Reference implementations for I1+I2 already exist in Plan 22-05 — hoist them into Plan 22-04. I3 is a one-field TS type addition.

No structural rewrite needed. G-absorption for 22-01, 22-02, 22-03, 22-05, 22-06, 22-07 is correct — the gaps are purely in the Plan 22-04 bridge layer (where new kwargs need to be threaded through) and one frontend TS type.

After these three fixes, re-run plan-checker one more time, then `/gsd-execute-phase 22a`.
