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
