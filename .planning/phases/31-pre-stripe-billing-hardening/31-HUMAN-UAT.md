---
status: partial
phase: 31-pre-stripe-billing-hardening
source: [31-VERIFICATION.md]
started: 2026-05-08T16:00:00Z
updated: 2026-05-08T16:00:00Z
---

## Current Test

[awaiting human action]

## Tests

### 1. AC22 — OpenRouter dashboard $5/mo cap + artifact
expected: log into openrouter.ai → Settings → Billing → Spend Limit set to $5.00; commit a screenshot or dashboard URL artifact (suggested path `.planning/phases/31-pre-stripe-billing-hardening/spend-cap.png`)
result: [pending]

### 2. AC20 — Add OPENROUTER_CI_KEY to GitHub repo secrets
expected: create a NEW OpenRouter API key dedicated to CI (separate from any developer BYOK), bound to the same account as Gate 1; add to GitHub → Settings → Secrets and variables → Actions as `OPENROUTER_CI_KEY`. Do NOT paste the value anywhere — confirm with the message `secret-set` only.
result: [pending]

### 3. AC23 — No-op PR triggers workflow + green baseline
expected: open a whitespace-only PR touching `api_server/` (e.g. `api_server/README.md`); confirm the `e2e-money-path` workflow runs and exits 0 in 5–10 minutes; OpenRouter dashboard records ~$0.0004 charge
result: [pending]

### 4. AC24 — Regression PR fails workflow + PR closed unmerged
expected: open a PR that deliberately breaks proxy cost-capture (e.g. forces `cost_usd = 0.0`); confirm the workflow fails at the `cost_usd > 0` assertion; CLOSE the PR without merging
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
