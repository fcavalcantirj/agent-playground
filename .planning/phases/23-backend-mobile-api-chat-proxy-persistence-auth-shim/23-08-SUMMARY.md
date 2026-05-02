---
phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
plan: 08
subsystem: planning-docs
tags:
  - requirements
  - traceability
  - documentation-only
  - phase-exit-gate
dependency_graph:
  requires:
    - "23-02"
    - "23-03"
    - "23-04"
    - "23-05"
    - "23-06"
  provides:
    - "REQUIREMENTS.md aligned with shipped Phase 23 reality (API-01/05 amended, API-06 dropped)"
    - "Phase-exit verifier no longer fails on stale wording"
  affects:
    - ".planning/REQUIREMENTS.md (API-01, API-05, API-06 + Traceability rows for those three)"
tech_stack:
  added: []
  patterns:
    - "Strikethrough preserves dropped-requirement history rather than wholesale deletion"
    - "Per-row Traceability annotation captures amendment cause inline (no separate changelog)"
key_files:
  created:
    - ".planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-08-SUMMARY.md"
  modified:
    - ".planning/REQUIREMENTS.md"
decisions:
  - "Documentation-only plan — no code changes; 4 surgical edits applied via Python (Edit/Write tool path was blocked by environment-level read-cache mismatch; Bash+Python wrote correct bytes to disk)"
  - "Strikethrough convention honored on API-06 (preserves original wording for traceability while making dropped-status explicit)"
  - "API-02, API-03, API-04, API-07, APP-*, UI-*, and all v1 requirement IDs are untouched (verified by `git diff --stat` showing only the 4 expected hunks)"
metrics:
  duration: "~16 minutes"
  completed: 2026-05-02
---

# Phase 23 Plan 08: REQUIREMENTS.md D-32 Amendment Summary

Synchronized `.planning/REQUIREMENTS.md` with Phase 23 D-32 by rewriting API-01 + API-05, marking API-06 as DROPPED, and updating the Traceability table — closing the phase-exit verifier's wording-mismatch gate.

## What Shipped

Four surgical edits applied to `.planning/REQUIREMENTS.md`:

| Edit | Target | Final landing line(s) | Convention |
|------|--------|----------------------|------------|
| 1 | API-01 wording | line 174 | Wholesale rewrite + amendment-trail in italic note (cites D-32 + supersession) |
| 2 | API-05 wording | line 178 | Wholesale rewrite + amendment-trail in italic note (cites D-32 + supersession) |
| 3 | API-06 wording | line 179 | **Strikethrough preserves history**; bullet/checkbox structure kept; explicit DROPPED + replacement note |
| 4 | Traceability rows | lines 388, 392, 393 | Inline annotation per row — `Pending — amended D-32 (...)` for API-01/05; `DROPPED — replaced by inapp_messages reuse per D-01` for API-06 |

Final line numbers match plan-time predictions exactly (no upstream drift between plan-write and execute).

## Strikethrough Convention

API-06 uses `~~Alembic migration creates a `messages` table.~~ **DROPPED in Phase 23.** Replaced by reuse of existing `inapp_messages` table per Phase 23 D-01 ...` so:

- Original intent is preserved as struck-through text (visible in raw markdown + rendered as crossed-out)
- DROPPED status is unambiguous (bold + explicit phrase)
- Replacement reference is inline (single hop to D-01 + the runtime seam at `services/inapp_messages_store.py`)
- Bullet checkbox `- [ ]` retained for layout consistency with surrounding API-01..07 entries (the strikethrough — not the checkbox — conveys the dropped state)

API-01 + API-05 use a different convention (wholesale rewrite + italic amendment-trail) because their replacement wording occupies the same conceptual slot — `~~old~~ new` would have been visually noisy. The italic trail (`*(Amended Phase 23 per D-32 — original ... superseded by ...)*`) preserves the supersession provenance.

## Untouched Requirements (verified)

`git diff --stat .planning/REQUIREMENTS.md` reports exactly 6 insertions / 6 deletions in 1 file — no other lines changed. Specifically untouched:

- API-02, API-03, API-04, API-07 (Backend Mobile API)
- APP-01..05 (Flutter App Foundation)
- UI-01..04 (Mobile Screens)
- All v1 requirement families: FND, AUTH, SBX, SEC, REC, SES, CHT, TRM, MET, BIL, PER, BST, OSS
- Out-of-scope table, deferred-features sections, Coverage stats footer

## Acceptance Criteria

All eight plan-defined acceptance criteria pass:

| Criterion | Result |
|-----------|--------|
| API-01 mentions `Idempotency-Key` REQUIRED | PASS — 2 hits (API-01 entry + Traceability row) |
| API-01 references `/v1/agents/:id/messages`, no /chat in API-01 block (amendment-trail tagged) | PASS — original `/chat` only appears in italic supersession note tagged `amended Phase 23 per D-32` |
| API-05 mentions both `auth/google/mobile` + `auth/github/mobile` | PASS — 1 hit each |
| API-05 says "no dev-mode shim" | PASS — 2 hits |
| API-06 marked DROPPED | PASS — 1 hit ("DROPPED in Phase 23") + Traceability row "DROPPED" |
| API-06 references replacement | PASS — 1 hit ("Replaced by reuse of existing `inapp_messages`") |
| Traceability shows amendments | PASS — 2 hits ("amended D-32") |
| Traceability shows API-06 dropped | PASS — 1 hit ("API-06 \| Phase 23 \| DROPPED") |
| API-02/03/04/07 wording preserved | PASS — `GET /v1/agents/:id/messages?limit=N` (API-02) + `GET /v1/models` (API-04) intact verbatim |
| Markdown still parses (no broken pipes / stray chars) | PASS — visual diff inspection clean |

## Deviations from Plan

### Rule 3 - Tooling Workaround

**Discovered during:** Task 1 first edit attempt
**Issue:** The Edit and Write tools' in-memory file cache became desynchronized from the on-disk file after a `git reset --hard` returned the worktree to the plan's expected base commit. Subsequent Edit/Write calls reported success but the on-disk file was never modified (verified via `md5`, `awk`, and `git diff` all showing the OLD content while the Read tool returned the NEW content).
**Fix:** Applied the four edits via a Python script invoked through Bash. Python read the actual on-disk bytes, performed exact-string substitutions matching the plan's specified old/new pairs, and wrote the result back. All four substitutions used `assert old in content` guards so the script would fail fast if any anchor string drifted.
**Files modified:** `.planning/REQUIREMENTS.md` only (the same file the Edit/Write tools were targeting; the deliverable was unchanged — only the write transport differed)
**Commit:** `347530e`

This is a Rule 3 fix (blocking issue prevented completing the task via the canonical tool path). The final on-disk content is byte-identical to what the plan specified; verification commands all pass; no scope or wording was altered to work around the issue.

## Self-Check: PASSED

| Claim | Verification | Result |
|-------|-------------|--------|
| `.planning/REQUIREMENTS.md` modified per D-32 | `grep "Idempotency-Key" .planning/REQUIREMENTS.md` → 2 hits | FOUND |
| Commit `347530e` exists with the 4-edit diff | `git log --oneline -1` → `347530e docs(23-08): amend REQUIREMENTS API-01/05/06 per D-32` | FOUND |
| Diff scope matches plan (6 insertions / 6 deletions) | `git diff --stat HEAD~1 .planning/REQUIREMENTS.md` → `1 file changed, 6 insertions(+), 6 deletions(-)` | FOUND |
| API-06 strikethrough syntax present | `grep "~~Alembic migration creates" .planning/REQUIREMENTS.md` → 1 hit | FOUND |
| Traceability table has API-01/05 amended + API-06 DROPPED | `grep "amended D-32"` → 2 hits, `grep "API-06.*DROPPED"` → 1 hit | FOUND |

## Threat Flags

None — this plan modifies only documentation. No new network endpoints, auth paths, file access patterns, or schema changes.

## Known Stubs

None — documentation-only plan; no UI, no data wiring.
