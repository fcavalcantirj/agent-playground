---
phase: B-stripe
plan: 04
type: execute
wave: 2
depends_on: [B-stripe-02]
files_modified:
  - api_server/src/api_server/routes/usage.py
  - api_server/tests/routes/test_usage_summary_tier_projection.py
autonomous: true
gap_closure: false
requirements_addressed:
  - D-02 (tier-aware semantics — ultra users see credits, free/pro see USD)
  - D-21 (mobile bimodal display branched on tier)
must_haves:
  truths:
    - "GET /v1/usage/summary projects tier and balance_cents fields when calling user has tier='ultra'"
    - "Free + Pro users continue to see the existing USD-cost projection (no balance_cents leaked)"
    - "Existing /v1/usage/summary contract stays byte-identical for the fields Phase A clients already consume"
  artifacts:
    - path: "api_server/src/api_server/routes/usage.py"
      provides: "Updated UsageSummaryResponse with optional tier + balance_cents fields"
      contains: "balance_cents"
  key_links:
    - from: "api_server/src/api_server/routes/usage.py"
      to: "credit_balances table"
      via: "LEFT JOIN credit_balances + WHERE u.id = $1 + tier branch"
      pattern: "credit_balances"
---

<objective>
Tier-aware projection in the existing `/v1/usage/summary` route. Mobile's `UsageTickerWidget` (Wave 5 update) reads this single endpoint and branches its render on tier (USD for free/pro, credits for ultra). The single-endpoint approach keeps mobile from having to choose between two endpoints, which is the dumb-client rule.

Purpose: Phase A's USD-cost ticker is the single existing tier-display surface. Phase B adds tier + balance fields without breaking existing Phase A consumers (free + pro users see the existing fields unchanged).
Output: usage.py modified to LEFT-JOIN credit_balances + project tier + balance_cents (only for ultra), integration test.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/B-stripe-paywall/CONTEXT.md
@.planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md
@.planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md
@.planning/phases/B-stripe-paywall/B-stripe-02-SUMMARY.md
@api_server/src/api_server/routes/usage.py
@api_server/tests/routes/test_usage_endpoints.py

<interfaces>
From api_server/src/api_server/routes/usage.py (existing — Phase A surface):
```python
class UsageSummaryResponse(BaseModel):
    total_usd: str
    by_provider: list[ProviderUsage]
    period_start: datetime
    period_end: datetime
    # Phase B adds: tier (always), balance_cents (only ultra), display_balance_cents (only ultra), is_negative (only ultra)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: usage.py — add tier + balance_cents projection (ultra only) + test</name>
  <files>api_server/src/api_server/routes/usage.py, api_server/tests/routes/test_usage_summary_tier_projection.py</files>
  <read_first>
    - api_server/src/api_server/routes/usage.py (FULL — existing /v1/usage/summary handler + UsageSummaryResponse model)
    - api_server/tests/routes/test_usage_endpoints.py (existing test fixtures + _seed_user pattern)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"routes/usage.py MODIFICATION")
    - api_server/src/api_server/services/ledger.py (Wave 1 — credit_balances cache rebuild semantics)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_summary_for_free_tier_returns_tier_field_but_NOT_balance_cents
    - test_summary_for_pro_tier_returns_tier_field_but_NOT_balance_cents
    - test_summary_for_ultra_tier_returns_tier_AND_balance_cents_AND_display_balance_AND_is_negative
    - test_summary_for_ultra_with_zero_balance_returns_balance_cents_zero_is_negative_false
    - test_summary_for_ultra_with_negative_balance_returns_negative_is_negative_true_display_zero
    - test_summary_existing_phase_a_fields_unchanged_for_free_user
  </behavior>
  <action>
**Modification — `api_server/src/api_server/routes/usage.py`:**

1. Update `UsageSummaryResponse`:

```python
class UsageSummaryResponse(BaseModel):
    total_usd: str
    by_provider: list[ProviderUsage]
    period_start: datetime
    period_end: datetime
    # Phase B additions — ALL OPTIONAL so Phase A consumers don't break:
    tier: str = "free"                                # always present; defaults preserve free shape
    balance_cents: int | None = None                  # only when tier='ultra'
    display_balance_cents: int | None = None          # only when tier='ultra' (clamped to >= 0)
    is_negative: bool | None = None                   # only when tier='ultra'
```

2. Modify the existing handler. Locate the SQL query that fetches the per-provider usage rows. After it (or before, depending on the existing flow), add a tier+balance lookup:

```python
async with pool.acquire() as conn:
    tier_row = await conn.fetchrow(
        """
        SELECT u.tier, COALESCE(b.balance_cents, 0)::BIGINT AS balance_cents
        FROM users u
        LEFT JOIN credit_balances b ON b.user_id = u.id
        WHERE u.id = $1
        """,
        user_id,
    )
    # ...existing usage_logs aggregation...
```

3. Construct the response:

```python
tier = tier_row["tier"] if tier_row else "free"
balance_cents_int = int(tier_row["balance_cents"]) if tier_row else 0

response = UsageSummaryResponse(
    total_usd=total_usd_str,
    by_provider=...,
    period_start=...,
    period_end=...,
    tier=tier,
)
if tier == "ultra":
    response.balance_cents = balance_cents_int
    response.display_balance_cents = max(balance_cents_int, 0)
    response.is_negative = balance_cents_int < 0
return response
```

**Backward compatibility invariant:** every field name + type that already exists in Phase A's response stays byte-identical. Free / Pro users must NOT see `balance_cents`, `display_balance_cents`, `is_negative` in the response (Pydantic's `exclude_none=True` is NOT default — explicitly use `model_dump(exclude_none=True)` if needed, OR set the model config `model_config = ConfigDict(json_encoders=..., extra='ignore')` and project None as missing — verify by curling `/v1/usage/summary` for a free user and checking the JSON keys.

**File — `api_server/tests/routes/test_usage_summary_tier_projection.py`:** Postgres testcontainer + async_client. Seed 3 users (free, pro, ultra). Seed credit_balances row only for the ultra user (with balance 1234, 0, -500 across 3 sub-tests). Assert the JSON response shape per `<behavior>`.

For the "free user JSON shape" test, hit the endpoint, get the JSON, assert `"balance_cents" not in response.json()` and `"is_negative" not in response.json()`.
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/routes/test_usage_summary_tier_projection.py -x</automated>
  </verify>
  <done>
- All 6 tier-projection tests pass.
- `grep "balance_cents" api_server/src/api_server/routes/usage.py | wc -l` ≥ 2 (model field + handler projection).
- Free/Pro JSON response keys do NOT include `balance_cents`, `display_balance_cents`, `is_negative` (verified by test).
- Existing `tests/routes/test_usage_endpoints.py` tests still pass (Phase A regression gate).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Mobile/web → /v1/usage/summary | existing Phase A surface; auth-gated; rate-limited via existing buckets |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-XT | InfoDisclosure | routes/usage.py | mitigate | LEFT JOIN credit_balances WHERE u.id = $1; never accept user_id from request body |
| T-B-LEAK | InfoDisclosure | UsageSummaryResponse | mitigate | balance_cents only included when tier='ultra'; free/pro users get unchanged Phase A response shape |
| T-B-NEG | InfoDisclosure | routes/usage.py | accept | display_balance_cents=0 + is_negative=true for negative balance is the intentional UX (Pitfall 6) |
</threat_model>

<verification>
- 6 new tier-projection tests pass.
- Phase A regression: existing `tests/routes/test_usage_endpoints.py` passes unchanged.
- Mobile (Wave 5) Update: when this lands, the AppBar ticker can branch on `summary.value.tier` to render USD vs credits.
</verification>

<success_criteria>
- `cd api_server && uv run pytest tests/routes/test_usage_summary_tier_projection.py tests/routes/test_usage_endpoints.py -x` all green.
- Curl: `curl -b "ap_session=..." http://localhost:8000/v1/usage/summary` for a free user returns the existing Phase A keys + a new `tier:"free"` field but NO balance_cents key.
- Curl: same for an ultra user returns `tier:"ultra", balance_cents:1234, display_balance_cents:1234, is_negative:false`.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-04-SUMMARY.md` documenting the projection branching logic and any deviations.
</output>
