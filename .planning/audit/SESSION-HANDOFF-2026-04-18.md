---
session_date: 2026-04-18
session_duration: ~full day (context exhausted at 90%)
pushed_to_origin: true
head_commit: f94d9ac
status: READY-TO-EXECUTE Phase 22a
---

# Session Handoff — 2026-04-18

> **Purpose:** Preserve every decision, every gotcha, every piece of evidence
> produced across a long multi-hour session so the next session can resume
> without archaeological recovery. Read after `/clear`, alongside
> `.planning/STATE.md`.

---

## 1. Arc of the session (what happened, in order)

| # | Phase of work | Outcome |
|---|---|---|
| 1 | UI/UX "banho de loja" polish (overall screen + ModelBrowser + borders) | Shipped commits `cf12af8`..`a3c95fe` |
| 2 | Slug-drift fix: `claude-haiku-4-5` → `claude-haiku-4.5` across 3 YAMLs | `7832eee` |
| 3 | API: expose `verified_models[]` on `/v1/recipes` | `9d9ad71` |
| 4 | Debug hermes silent-stderr INVOKE_FAIL (`/gsd-debug`) | Fix A (`--verbose` to hermes argv) + Fix B (stdout tail fallback in runner). Committed as `fa0676b` + `06838c9`. Session doc at `.planning/debug/hermes-invoke-fail-silent-stderr.md`. |
| 5 | Channel recon v0.2-draft across all 5 recipes — **bespoke per-agent, docs first, then empirical Telegram round-trip** | `06838c9` |
| 6 | Deep debug openclaw silent-fail (user-guided isolation) | Root cause: isolated to openrouter plugin in openclaw image `2026.4.15-beta.1` — Anthropic direct works end-to-end. Documented under `openclaw.yaml.known_quirks` + `provider_compat.deferred: [openrouter]`. |
| 7 | Desiccated audit: backend + frontend inventories + action list | `2a401d1` + `195e44f` (no-deletions revision) + `8a72f78` (pivot STATE) |
| 8 | Add Golden Rule #5 to CLAUDE.md: test gray areas empirically BEFORE planning | `8fafa33` |
| 9 | Plan Phase 22a — 7 plans + CONTEXT + PATTERNS + VERIFICATION | `04c1199` |
| 10 | Spike 10 of 13 probes against real infra (pyrage, age-HKDF, partial unique idx, schema oneOf, docker -d, ready-log regex, SIGTERM, module paths, pairing latency, health endpoints) | `d8f8d8b` + `32b7a60` |
| 11 | Absorb G1..G5 spike findings into plans + recipes | `8f53881` |
| 12 | Absorb I1..I3 plan-checker contract advisories (bridge ↔ route ↔ TS) | `ca7d44c` |
| 13 | FINAL verification pass (plan-checker PASS, ready for execute) | `f94d9ac` |

Everything pushed to `origin/main` through commit `f94d9ac`.

---

## 2. Phase 22a — ready to execute, sealed evidence

**Location:** `.planning/phases/22-channels-v0.2/`

**Artifacts (all committed):**

```
22-CONTEXT.md                # Scope lock: SC-01..SC-06 exit gate
22-PATTERNS.md               # gsd-pattern-mapper output: 7 artifacts with in-repo analogs
22-01-PLAN.md                # Wave 1 — recipe schema v0.2 formalization
22-02-PLAN.md                # Wave 1 — migration script for existing recipes
22-03-PLAN.md                # Wave 2 — runner --mode persistent (docker -d + health wait)
22-04-PLAN.md                # Wave 2 — bridge (pyrage-encrypted API key store)
22-05-PLAN.md                # Wave 3 — API endpoints (3 new routes)
22-06-PLAN.md                # Wave 4 — frontend Step 2.5 channel picker
22-07-PLAN.md                # Wave 5 — E2E Telegram smoke
22-VERIFICATION.md           # Three sections: initial PASS, G1..G5 absorbed, FINAL post-I1/I2/I3 PASS
22-SPIKES/                   # 10 probe results + RESULTS.md + SPIKES-PLAN.md
```

**Total estimated effort:** ~32h (5 waves).

**Exit gate:** SC-01..SC-06 — every one of the 5 recipes (hermes/picoclaw/nullclaw/nanobot/openclaw-Anthropic) must complete a real Telegram round-trip against live infra via the new persistent runner + API + frontend UI.

---

## 3. Empirical findings (don't re-derive)

### 3.1 Per-recipe SIGTERM + graceful_shutdown_s

Captured via `spike-07-sigterm-graceful.md`:

| Recipe | `graceful_shutdown_s` | `sigterm_handled` | Notes |
|---|---|---|---|
| hermes | 15 | true | Python signal handlers clean up MCP sessions |
| picoclaw | 2 | true | Go binary, fast drain |
| nullclaw | 10 | true | Zig event loop unwinds channel_catalog |
| nanobot | 0 | **false** | **Never honors SIGTERM; always SIGKILL** — runner must skip `docker stop --time`, go straight to `docker kill` |
| openclaw | 5 | true | Node server + plugin shutdown hooks |

**Implication for 22-03:** runner must read `graceful_shutdown_s` + `sigterm_handled` per recipe, branch `docker stop -t N` vs `docker kill`.

### 3.2 Per-recipe health_check endpoints

Captured via `spike-11-health-endpoints.md`:

| Recipe | health_check | Notes |
|---|---|---|
| hermes | `process_alive` | No HTTP surface; check `docker inspect` state |
| picoclaw | `http 18790 /health` | **NOT `/ready`** — `/ready` returns 503 until first message; docs were wrong |
| nullclaw | `process_alive` | No HTTP surface |
| nanobot | `http 18790 /health` | Works, consistent with picoclaw port |
| openclaw | `http 18789 /` | Root returns 200 with version string |

### 3.3 nullclaw `user_override: root`

`/nullclaw-data` inside the image is `root:root` but the default container user is `nobody`. Image has an ownership bug that docs don't reflect. Recipe must pin `user_override: root` to write config.

Additional: config.json has an empty `channels: {}` block. Must **replace** via awk, not **append** — appending causes `DuplicateField` errors that the Zig parser swallows silently.

### 3.4 openclaw openrouter plugin silent-fail

- Runs with Anthropic direct: full response, tokens counted, tools invoked ✓
- Runs with OpenRouter: `attempts: []`, 0 tokens, container exits 0, no stderr
- **Isolated to the openrouter plugin in image `2026.4.15-beta.1`**
- Bug NOT in agent loop, gateway, embedded dispatch — just the plugin
- Tracker item: file upstream issue at github.com/openclaw/openclaw

Recipe carries dual verified_cells: `FULL_PASS` (anthropic) + `CHANNEL_PASS_LLM_FAIL` (openrouter) for transparency.

### 3.5 60s openclaw pair-approve latency

Captured via `spike-10-pairing-approve-latency.md`: first pairing approve call took 58.7s end-to-end. Plan 22-05 timeout bumped to 90s. Plan 22-06 adds UX disclosure ("Pairing can take up to 90 seconds on first approve").

### 3.6 pyrage correct API surface

Planner initially wrote `pyrage.passphrase.Recipient.from_str` (nonexistent). `spike-01-pyrage-install.md` + `spike-02-age-hkdf.md` confirm correct API:

```python
from pyrage import passphrase
ciphertext = passphrase.encrypt(plaintext, passphrase_str)
plaintext  = passphrase.decrypt(ciphertext, passphrase_str)
```

HKDF per-user KEK derived from server master key + user UUID is computed separately, then used as the passphrase.

### 3.7 Postgres partial unique index for channel uniqueness

Verified via `spike-03-partial-unique-index.md`:

```sql
CREATE UNIQUE INDEX channels_tg_chat_user_uniq
  ON channels (user_id, channel_type, (config->>'chat_id'))
  WHERE deleted_at IS NULL;
```

`asyncpg.UniqueViolationError` mapped to 409 in FastAPI layer.

### 3.8 jsonschema oneOf works for channels discriminated union

`spike-04-schema-oneOf.md` confirmed the v0.2 schema validates a nested `channels:` block with `channel_type: telegram | discord | slack` using `oneOf` discriminator + per-type `$ref`.

---

## 4. Plan-checker revisions absorbed (G1..G5 + I1..I3)

| Tag | Issue | Where applied |
|---|---|---|
| G1 | `pyrage.Recipient.from_str` nonexistent | `22-04-PLAN.md` — corrected to `passphrase.encrypt/decrypt` |
| G2 | 5s SIGTERM too short for hermes (15s) | `22-03-PLAN.md` — per-recipe shutdown budget |
| G3 | picoclaw `/ready` returns 503 | `recipes/picoclaw.yaml` — `/health` not `/ready` |
| G4 | nullclaw channels block needs awk replace, not append | `recipes/nullclaw.yaml` — `user_override: root` + awk pattern |
| G5 | 60s openclaw first-pair latency | `22-05-PLAN.md` + `22-06-PLAN.md` — 90s timeout + UX copy |
| I1 | Bridge returns `bridge_pid`, route expected `container_id` | `22-04-PLAN.md` — contract unified on `container_id` |
| I2 | `checksum` field missing from TS types | `22-06-PLAN.md` — added to `ChannelResponse` |
| I3 | FastAPI error shape differed from Stripe conventions | `22-05-PLAN.md` — aligned to `{ error: { code, message, param } }` |

Cross-plan contract matrix (22-04 bridge ↔ 22-05 route ↔ 22-06 TS): **6/6 fields aligned**.

---

## 5. Open decisions (deliberately unresolved)

1. **`/signup` fate after OAuth lands** — currently a mock dev-login page. Decision deferred until OAuth Google + GitHub ships. Documented in `.planning/audit/ACTION-LIST.md` as "open decision."
2. **openclaw upstream issue filing** — SC-06 tracker item. Needs reproducer script + reduced test case once upstream repo issue form reviewed.
3. **Retroactive verified_cells matrix expansion** — `recipes/BACKLOG.md` carries a chore to extend `verified_cells[]` across more (recipe × model × channel) permutations once the base matrix is green.

---

## 6. Golden Rule #5 — the methodology shift

Added to `CLAUDE.md` (commit `8fafa33`):

> **Test everything. Probe gray areas empirically BEFORE planning.**
> No PLAN may assume "pattern X in another module will work the same
> here" — every non-trivial mechanism (new file format, new subprocess
> lifecycle, new encryption path, new env-var injection, new health
> check, new container flag, new regex, new HTTP contract, new DB
> constraint) must be spiked against real infra and the spike result
> captured as evidence BEFORE the planner consumes it.

This rule is load-bearing for every future GSD phase. The 10 spikes under `22-SPIKES/` are the canonical worked example.

Companion memory: `memory/feedback_test_everything_before_planning.md`.

---

## 7. What was NOT touched (honor the boundaries)

- No `/api/` Go substrate edits (CLAUDE.md rule: "Do NOT touch `api/`, `deploy/`, `test/`, or the old substrate")
- No deletion of the 5 existing recipes — all additive v0.2-draft blocks
- No new agent recipes from `BACKLOG.md` (format-v0.1 + channels-v0.2 consolidation gate)
- No `.env` modifications (tokens added to `.env.local` which is gitignored)
- No force pushes, no amends, no destructive git ops
- No invented APIs after G1 corrected pyrage usage

---

## 8. Resume sequence for next session

```
/clear
```

Then read (in order):

1. `./CLAUDE.md` — 5 golden rules, especially #5 (new)
2. `.planning/STATE.md` — this file's companion (resume anchor)
3. `.planning/audit/SESSION-HANDOFF-2026-04-18.md` — this file
4. `.planning/audit/ACTION-LIST.md` — per-page implementation plan
5. `.planning/phases/22-channels-v0.2/22-CONTEXT.md` — phase scope
6. `.planning/phases/22-channels-v0.2/22-VERIFICATION.md` — final PASS
7. `.planning/phases/22-channels-v0.2/22-SPIKES/RESULTS.md` — G1..G5 evidence

Then execute:

```
/gsd-execute-phase 22a
```

**Parallel track (independent):** `/gsd-spec-phase 22b-oauth` — specs OAuth (Google + GitHub), `/v1/users/me`, session cookie. Unblocks 11 dashboard pages under `frontend/app/dashboard/*`.

---

## 9. Commit manifest (this session)

```
f94d9ac docs(22a): FINAL verification — plan-checker PASS, ready for execute
ca7d44c fix(22a): absorb plan-checker I1/I2/I3 advisories into 22-04 + 22-06
8f53881 feat(22a-revisions): absorb G1..G5 spike findings into plans + recipes
32b7a60 feat(22a-spikes): 10 empirical probes resolve gray areas before execute
d8f8d8b docs(22a): spike plan — 13 probes against real infra before execute
8fafa33 docs(rules): add Golden Rule #5 — test gray areas empirically before planning
04c1199 docs(22): PLAN phase 22a — 7 plans + patterns + verification (PASS)
8a72f78 docs(gsd): seal audit docs + pivot STATE to audit-as-input for next phases
195e44f docs(audit): revise action list — implement every page, no deletions
2a401d1 docs(audit): desiccated backend + frontend inventory + action list
5abe28f docs(state): pivot resume anchor to Phase 22 (channels v0.2)
04c772f docs(22): channels v0.2 recon + phase context
06838c9 feat(recipes): channels v0.2-draft — Telegram end-to-end verified for 5/5
a3c95fe feat(playground): readable banho de loja — inline ModelBrowser, higher-contrast primitives
9d9ad71 feat(api): expose verified_models on /v1/recipes; backlog test-matrix expansion chore
fa0676b fix(runner): surface stdout tail when stderr empty on non-zero exit
7832eee fix(recipes): correct claude-haiku slug drift (-4-5 → -4.5) in verified_cells
```

All pushed to `origin/main`. Working tree state: clean except for pre-existing untracked `.planning/phases/` scaffolding (unchanged this session).
