---
phase: B-stripe
plan: 02
type: execute
wave: 1
depends_on: [B-stripe-01]
files_modified:
  - api_server/alembic/versions/014_phase_b_credit_ledger_and_tier.py
  - api_server/tests/test_migration_014_phase_b.py
  - api_server/src/api_server/config.py
  - api_server/src/api_server/services/stripe_client.py
  - api_server/src/api_server/services/billing_packs.py
  - api_server/src/api_server/services/ledger.py
  - api_server/src/api_server/main.py
  - api_server/tests/conftest.py
  - api_server/tests/test_billing_packs.py
  - api_server/tests/test_ledger_atomic.py
autonomous: true
gap_closure: false
requirements_addressed:
  - D-01 (users.tier enum + migration 014)
  - D-06 (5-pack catalog single SOT in api_server)
  - D-07 (1:1 USD→credit grant — encoded in PACKS data)
  - D-08 (ap_multiplier data migration 1.0 → 1.15)
  - D-11 (lazy customer create — service helper)
  - D-17 (ledger-as-truth — services/ledger.py with same-tx atomic pattern)
  - D-23 (USD only — no currency column)
  - D-26 (migration 014 backfill users.tier='free')
  - AMD-01 (stripe>=15.0,<16.0)
  - AMD-04 (StripeClient instance lives on app.state.stripe_client)
must_haves:
  truths:
    - "Migration 014 upgrades cleanly against a real Postgres testcontainer and survives downgrade/upgrade round-trip"
    - "users.tier defaults to 'free' for every existing row after upgrade and CHECK constraint blocks invalid values"
    - "credit_balances + credit_transactions + stripe_webhook_events tables exist with the right indexes/UNIQUEs"
    - "cost_weights.ap_multiplier rows previously at 1.0 are now 1.15"
    - "Settings exposes 9 new AP_STRIPE_* fields with placeholder fallback in dev"
    - "StripeClient instance is constructed once in lifespan and stashed on app.state.stripe_client"
    - "billing_packs.PACKS exposes 5 packs with correct stripe_price_id wiring from Settings"
    - "ledger.debit_user / credit_user / record_tier_change run atomically under caller's transaction"
  artifacts:
    - path: "api_server/alembic/versions/014_phase_b_credit_ledger_and_tier.py"
      provides: "Migration 014 — tier column, 3 new tables, ap_multiplier data migration"
      contains: "revision = \"014_phase_b_credit_ledger_and_tier\""
    - path: "api_server/src/api_server/services/stripe_client.py"
      provides: "build_stripe_client(settings) factory + create_pack_checkout_session + create_subscription_checkout_session helpers"
      exports: ["build_stripe_client", "create_pack_checkout_session", "create_subscription_checkout_session", "lazy_create_or_fetch_customer"]
    - path: "api_server/src/api_server/services/billing_packs.py"
      provides: "PACKS frozen list of 5 dataclasses (Pack)"
      exports: ["Pack", "PACKS"]
    - path: "api_server/src/api_server/services/ledger.py"
      provides: "Atomic helpers: debit_user, credit_user, record_tier_change"
      exports: ["debit_user", "credit_user", "record_tier_change"]
  key_links:
    - from: "api_server/src/api_server/main.py"
      to: "api_server/src/api_server/services/stripe_client.py"
      via: "lifespan constructs StripeClient and stores on app.state.stripe_client"
      pattern: "app\\.state\\.stripe_client"
    - from: "api_server/src/api_server/services/billing_packs.py"
      to: "api_server/src/api_server/config.py"
      via: "stripe_price_id_pack_* fields read at module import"
      pattern: "stripe_price_id_pack_"
---

<objective>
Schema + dependency + base-substrate plan. Lands migration 014 (tier column + 3 new tables + ap_multiplier data migration), pydantic Settings extensions for the 9 new AP_STRIPE_* fields, the StripeClient lifespan-owned service, the static pack catalog, and the atomic ledger helpers.

Purpose: Establish the data + secret + service substrate every later Phase B wave reads. Without this wave Wave 2+ has nothing to bind to.
Output: Migration 014, services/{stripe_client,billing_packs,ledger}.py, config.py extensions, lifespan wiring, and migration round-trip test.
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
@.planning/phases/B-stripe-paywall/B-stripe-01-SUMMARY.md
@api_server/alembic/versions/013_phase29_proxy_columns.py
@api_server/alembic/versions/010_usage_logs_cost_weights.py
@api_server/tests/test_migration_013_proxy_columns.py
@api_server/src/api_server/config.py
@api_server/src/api_server/main.py
@api_server/src/api_server/services/proxy_byok_cache.py
@api_server/src/api_server/services/usage_recorder.py

<interfaces>
<!-- Key types for executors. Extracted from the existing codebase + Wave 0 spike artifacts. -->

From api_server/src/api_server/temporal/activities/debit_balance.py (current stub — Wave 4 replaces body):
```python
@activity.defn(name="debit_balance")
async def debit_balance(inp: DispatchMessageInput) -> str:
    return "0"
```

From api_server/src/api_server/services/usage_recorder.py (caller-owns-tx pattern this plan mirrors):
```python
async def some_helper(conn: asyncpg.Connection, *, user_id: UUID, ...) -> Decimal:
    # caller is INSIDE conn.transaction(); helper does NOT commit
    ...
```

From the Wave 0 draft migration (api_server/tests/_spikes/draft_014_migration.py):
- table credit_balances(user_id uuid PK FK users.id ON DELETE CASCADE, balance_cents BIGINT NOT NULL DEFAULT 0, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())
- table credit_transactions(id uuid PK gen_random_uuid(), user_id uuid FK, kind text CHECK in ('topup','debit','refund','tier_change','admin_writeoff'), amount_cents BIGINT NOT NULL, reference_id text NULL, reference_type text NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())
  - UNIQUE INDEX uq_credit_transactions_reference (reference_id, reference_type) WHERE reference_id IS NOT NULL
  - INDEX ix_credit_transactions_user_created (user_id, created_at DESC)
- table stripe_webhook_events(id uuid PK gen_random_uuid(), stripe_event_id text UNIQUE, event_type text NOT NULL, payload text NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())
- users.tier text NOT NULL DEFAULT 'free' with CHECK in ('free','pro','ultra')
- users.stripe_customer_id text NULL
- users.refund_writeoff_cents bigint NOT NULL DEFAULT 0

From AMD-04 (StripeClient v15 service pattern):
```python
import stripe
client = stripe.StripeClient(api_key)
client.customers.create(params={...})
client.checkout.sessions.create(params={...})
client.construct_event(payload, sig_header, secret)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Migration 014 + round-trip test + Settings extension</name>
  <files>api_server/alembic/versions/014_phase_b_credit_ledger_and_tier.py, api_server/tests/test_migration_014_phase_b.py, api_server/src/api_server/config.py</files>
  <read_first>
    - api_server/alembic/versions/013_phase29_proxy_columns.py (FULL — copy revision-header + upgrade/downgrade discipline)
    - api_server/alembic/versions/010_usage_logs_cost_weights.py (table-create + check-constraint + index template)
    - api_server/tests/test_migration_013_proxy_columns.py (FULL — testcontainer + alembic round-trip + asyncpg pg_attribute probe pattern)
    - api_server/src/api_server/config.py (Field/validation_alias/get_settings pattern; OAuth _resolve_or_fail dev/prod placeholder pattern)
    - api_server/tests/_spikes/draft_014_migration.py (Wave 0 evidence — copy verbatim)
  </read_first>
  <behavior>
    Tests written FIRST (TDD per Phase B baseline; spike-h proved the round-trip works in draft form):
    - test_upgrade_creates_users_tier_column_with_default_and_check
    - test_upgrade_creates_credit_balances_with_pk_and_fk_cascade
    - test_upgrade_creates_credit_transactions_with_kind_check_and_unique_index
    - test_upgrade_creates_stripe_webhook_events_with_unique_event_id
    - test_upgrade_bumps_ap_multiplier_to_1_15_for_existing_rows
    - test_downgrade_removes_all_added_objects
    - test_upgrade_after_downgrade_is_idempotent
    - test_settings_exposes_9_stripe_fields_with_placeholders_in_dev
  </behavior>
  <action>
**File 1 — `api_server/alembic/versions/014_phase_b_credit_ledger_and_tier.py`:** Copy `api_server/tests/_spikes/draft_014_migration.py` verbatim into `alembic/versions/`, ensuring:

- `revision = "014_phase_b_credit_ledger_and_tier"` (≤32 chars per alembic_version.version_num — count: 36 — TOO LONG; use `"014_phase_b_credit_ledger"` instead, which is 25 chars).
- `down_revision = "013_phase29_proxy_columns"`.
- Module docstring documents per-line CONTEXT decision IDs (D-01, D-06, D-08, D-17, D-23, D-26).
- `upgrade()` produces the schema in this order: users column adds → credit_balances → credit_transactions + indexes + check → stripe_webhook_events + UNIQUE → ap_multiplier UPDATE.
- `downgrade()` reverses in mirror order; the ap_multiplier UPDATE in downgrade reverts 1.15 → 1.0 ONLY for rows where the value is exactly 1.15 (so downgrade is safe if admins later changed multipliers).
- Use `postgresql.UUID(as_uuid=True)` for uuid columns; `sa.text("gen_random_uuid()")` for default; `sa.text("NOW()")` for timestamptz default.

**File 2 — `api_server/tests/test_migration_014_phase_b.py`:** Mirror `tests/test_migration_013_proxy_columns.py` shape:
- `pytestmark = pytest.mark.api_integration`.
- Module-scoped Postgres 17 testcontainer fixture.
- Helper `_alembic(container, *args)` runs alembic CLI with `version_locations` set to `api_server/alembic/versions`.
- Tests run upgrade → assert via asyncpg `pg_attribute` + `pg_constraint` + `pg_index` probes (mirror lines 40-86 of test_migration_013).
- Specific assertions:
  - `users.tier`: type=`text`, NOT NULL, default `'free'::text`.
  - `users` has CHECK constraint `ck_users_tier` covering `('free','pro','ultra')`.
  - `users.stripe_customer_id`: type=`text`, NULLABLE.
  - `users.refund_writeoff_cents`: type=`bigint`, NOT NULL, default `0::bigint`.
  - `credit_balances`: PK on `user_id`, FK to `users.id` ON DELETE CASCADE.
  - `credit_transactions`: CHECK constraint covering all 5 kinds; UNIQUE INDEX on (reference_id, reference_type) WHERE reference_id IS NOT NULL.
  - `stripe_webhook_events`: UNIQUE constraint on `stripe_event_id`.
  - Data: `SELECT COUNT(*) FROM cost_weights WHERE ap_multiplier = 1.15` ≥ count of rows that previously had 1.0 (seed fixture if cost_weights is empty in test).
- Also include the existing migration's seed data for cost_weights so the data-migration assertion is meaningful (mirror `test_migration_013_proxy_columns.py` seeding pattern; OR call `_alembic(container, "upgrade", "010_usage_logs_cost_weights")` as a step before applying 014).

**File 3 — `api_server/src/api_server/config.py` extension:** Add 9 new fields under `class Settings(BaseSettings)`:

```python
stripe_api_key: str = Field(default="", validation_alias="AP_STRIPE_API_KEY")
stripe_webhook_secret: str = Field(default="", validation_alias="AP_STRIPE_WEBHOOK_SECRET")
stripe_price_id_pro_monthly: str = Field(default="", validation_alias="AP_STRIPE_PRICE_ID_PRO_MONTHLY")
stripe_price_id_pack_5: str = Field(default="", validation_alias="AP_STRIPE_PRICE_ID_PACK_5")
stripe_price_id_pack_10: str = Field(default="", validation_alias="AP_STRIPE_PRICE_ID_PACK_10")
stripe_price_id_pack_25: str = Field(default="", validation_alias="AP_STRIPE_PRICE_ID_PACK_25")
stripe_price_id_pack_50: str = Field(default="", validation_alias="AP_STRIPE_PRICE_ID_PACK_50")
stripe_price_id_pack_100: str = Field(default="", validation_alias="AP_STRIPE_PRICE_ID_PACK_100")
```

Add a `_resolve_or_warn_stripe()` validator (mirror existing `_resolve_or_fail` for OAuth) that:
- In `env=='dev'`: log a single warning per missing field at `api_server.config` level, set placeholder values like `"sk_test_DEV_PLACEHOLDER"`, `"whsec_DEV_PLACEHOLDER"`, `"price_DEV_PLACEHOLDER_pro"`, etc.
- In `env=='prod'`: raise `RuntimeError(f"AP_STRIPE_X required in prod")` if any field is empty.

Test that the dev placeholder path emits the warning and produces non-empty defaults; prod path raises.
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/test_migration_014_phase_b.py -x</automated>
  </verify>
  <done>
- All 7 migration tests pass + the Settings dev/prod test passes.
- `cd api_server && uv run alembic heads` shows `014_phase_b_credit_ledger` as the head.
- `grep "validation_alias=\"AP_STRIPE_" api_server/src/api_server/config.py | wc -l` outputs `8` (the 9th is implicit via the env handling).
- Migration file revision string ≤32 chars.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: services/billing_packs.py + services/stripe_client.py + services/ledger.py + main.py lifespan wiring</name>
  <files>api_server/src/api_server/services/billing_packs.py, api_server/src/api_server/services/stripe_client.py, api_server/src/api_server/services/ledger.py, api_server/src/api_server/main.py, api_server/tests/test_billing_packs.py, api_server/tests/test_ledger_atomic.py, api_server/tests/conftest.py</files>
  <read_first>
    - api_server/src/api_server/services/proxy_byok_cache.py (lifespan-owned async object on app.state.X)
    - api_server/src/api_server/services/proxy_dispatcher.py (PROVIDERS frozen module-level dict pattern)
    - api_server/src/api_server/services/usage_recorder.py:286-420 (caller-owned conn + transaction, returning Decimal, defensive defaults)
    - api_server/src/api_server/main.py (lifespan ordering between Sentry init and Temporal connect)
    - .planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md (Example C — create_pack_checkout_session full template; Pattern 1 lazy customer + SELECT FOR UPDATE)
    - api_server/tests/_spikes/spike_c_atomic_ledger.py (Wave 0 evidence for concurrent debit safety)
    - api_server/tests/_spikes/spike_g_lazy_customer_create.py (Wave 0 evidence for lazy customer race-defense)
  </read_first>
  <behavior>
    Tests written FIRST:
    - billing_packs:
      - test_packs_module_exposes_5_packs_in_known_order
      - test_pack_ids_match_d_06_set
      - test_credit_cents_equals_usd_amount_cents_per_d_07
      - test_packs_pull_stripe_price_id_from_settings
    - ledger (Postgres testcontainer + asyncpg):
      - test_debit_user_inserts_negative_amount_and_rebuilds_balance
      - test_debit_user_idempotent_on_unique_violation_returns_original_amount
      - test_credit_user_inserts_positive_amount_and_rebuilds_balance
      - test_record_tier_change_inserts_zero_amount_audit_row
      - test_8_concurrent_debits_conserve_balance (mirrors spike-c)
  </behavior>
  <action>
**File 1 — `api_server/src/api_server/services/billing_packs.py`:** Module-level frozen list per D-06. Mirror `services/proxy_dispatcher.py::PROVIDERS` shape:

```python
from __future__ import annotations
from dataclasses import dataclass
from ..config import get_settings

@dataclass(frozen=True)
class Pack:
    id: str
    label: str
    usd_amount_cents: int
    credit_cents: int
    stripe_price_id: str

def _build_packs() -> tuple[Pack, ...]:
    s = get_settings()
    return (
        Pack("pack_5",   "$5",   500,   500,   s.stripe_price_id_pack_5),
        Pack("pack_10",  "$10",  1000,  1000,  s.stripe_price_id_pack_10),
        Pack("pack_25",  "$25",  2500,  2500,  s.stripe_price_id_pack_25),
        Pack("pack_50",  "$50",  5000,  5000,  s.stripe_price_id_pack_50),
        Pack("pack_100", "$100", 10000, 10000, s.stripe_price_id_pack_100),
    )

PACKS: tuple[Pack, ...] = _build_packs()

def get_pack(pack_id: str) -> Pack | None:
    return next((p for p in PACKS if p.id == pack_id), None)
```

Per D-07, `credit_cents == usd_amount_cents` for every pack — invariant tested.

**File 2 — `api_server/src/api_server/services/stripe_client.py`:** Process-wide StripeClient instance + 3 helpers. Use AMD-04 service pattern.

```python
from __future__ import annotations
from uuid import UUID
import asyncpg
import stripe

from ..config import Settings
from .billing_packs import get_pack

def build_stripe_client(settings: Settings) -> stripe.StripeClient:
    """Construct once per process. Stash on app.state.stripe_client (main.py lifespan)."""
    return stripe.StripeClient(settings.stripe_api_key)

async def lazy_create_or_fetch_customer(
    conn: asyncpg.Connection, *, user_id: UUID, client: stripe.StripeClient,
) -> str:
    """SELECT FOR UPDATE → create Stripe Customer if NULL → UPDATE row. Caller owns the transaction."""
    row = await conn.fetchrow(
        "SELECT email, stripe_customer_id FROM users WHERE id = $1 FOR UPDATE",
        user_id,
    )
    if row is None:
        raise ValueError(f"user {user_id} not found")
    if row["stripe_customer_id"] is not None:
        return row["stripe_customer_id"]
    customer = client.customers.create(params={
        "email": row["email"],
        "metadata": {"ap_user_id": str(user_id)},
    })
    await conn.execute(
        "UPDATE users SET stripe_customer_id = $1 WHERE id = $2",
        customer.id, user_id,
    )
    return customer.id

async def create_pack_checkout_session(
    *, conn: asyncpg.Connection, user_id: UUID, pack_id: str,
    success_url: str, cancel_url: str, client: stripe.StripeClient,
) -> str:
    """Returns the Stripe-hosted Checkout URL (session.url)."""
    pack = get_pack(pack_id)
    if pack is None:
        raise ValueError(f"unknown pack_id: {pack_id}")
    async with conn.transaction():
        customer_id = await lazy_create_or_fetch_customer(conn, user_id=user_id, client=client)
    session = client.checkout.sessions.create(params={
        "customer": customer_id,
        "mode": "payment",
        "line_items": [{"price": pack.stripe_price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "allow_promotion_codes": True,                      # D-24
        "metadata": {
            "ap_user_id": str(user_id),
            "pack_id": pack.id,
            "credit_cents": str(pack.credit_cents),
        },
        "automatic_tax": {"enabled": True},                  # Stripe Tax
    })
    return session.url

async def create_subscription_checkout_session(
    *, conn: asyncpg.Connection, user_id: UUID,
    success_url: str, cancel_url: str, client: stripe.StripeClient,
    settings: Settings,
) -> str:
    """Pro tier $/mo via Checkout in subscription mode."""
    async with conn.transaction():
        customer_id = await lazy_create_or_fetch_customer(conn, user_id=user_id, client=client)
    session = client.checkout.sessions.create(params={
        "customer": customer_id,
        "mode": "subscription",
        "line_items": [{"price": settings.stripe_price_id_pro_monthly, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "allow_promotion_codes": True,                      # D-24
        "metadata": {"ap_user_id": str(user_id)},
        "automatic_tax": {"enabled": True},
    })
    return session.url
```

**File 3 — `api_server/src/api_server/services/ledger.py`:** Atomic helpers per D-17 ledger-as-truth.

```python
from __future__ import annotations
from decimal import Decimal
from uuid import UUID
import asyncpg

async def _ensure_balance_row(conn: asyncpg.Connection, user_id: UUID) -> None:
    """Idempotent UPSERT of the balance cache row (PK on user_id)."""
    await conn.execute(
        "INSERT INTO credit_balances (user_id, balance_cents) VALUES ($1, 0) "
        "ON CONFLICT (user_id) DO NOTHING",
        user_id,
    )

async def _rebuild_balance_from_ledger(conn: asyncpg.Connection, user_id: UUID) -> int:
    """SUM-from-ledger rebuild — single statement caches drift away (D-17)."""
    new_balance = await conn.fetchval(
        "SELECT COALESCE(SUM(amount_cents), 0)::BIGINT FROM credit_transactions WHERE user_id = $1",
        user_id,
    )
    await conn.execute(
        "UPDATE credit_balances SET balance_cents = $1, updated_at = NOW() WHERE user_id = $2",
        new_balance, user_id,
    )
    return int(new_balance)

async def debit_user(
    conn: asyncpg.Connection, *, user_id: UUID, cost_cents: int,
    reference_id: str, reference_type: str,
) -> Decimal:
    """Insert ledger debit row + UPDATE balance cache. Returns Decimal-USD (cents/100).
    Caller MUST be inside conn.transaction(). Idempotent on UNIQUE(reference_id, reference_type)."""
    await _ensure_balance_row(conn, user_id)
    try:
        await conn.execute(
            "INSERT INTO credit_transactions (user_id, kind, amount_cents, reference_id, reference_type) "
            "VALUES ($1, 'debit', $2, $3, $4)",
            user_id, -abs(cost_cents), reference_id, reference_type,
        )
    except asyncpg.UniqueViolationError:
        return Decimal(abs(cost_cents)) / Decimal(100)
    await _rebuild_balance_from_ledger(conn, user_id)
    return Decimal(abs(cost_cents)) / Decimal(100)

async def credit_user(
    conn: asyncpg.Connection, *, user_id: UUID, kind: str, amount_cents: int,
    reference_id: str, reference_type: str,
) -> int:
    """Insert ledger credit/topup/refund/admin_writeoff row + rebuild balance.
    `kind` MUST be one of ('topup','refund','admin_writeoff'). Returns new balance_cents."""
    if kind not in ("topup", "refund", "admin_writeoff"):
        raise ValueError(f"credit_user kind must be topup/refund/admin_writeoff, got: {kind}")
    await _ensure_balance_row(conn, user_id)
    try:
        await conn.execute(
            "INSERT INTO credit_transactions (user_id, kind, amount_cents, reference_id, reference_type) "
            "VALUES ($1, $2, $3, $4, $5)",
            user_id, kind, amount_cents, reference_id, reference_type,
        )
    except asyncpg.UniqueViolationError:
        return await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id = $1", user_id,
        )
    return await _rebuild_balance_from_ledger(conn, user_id)

async def record_tier_change(
    conn: asyncpg.Connection, *, user_id: UUID, from_tier: str, to_tier: str,
    stripe_event_id: str,
) -> None:
    """Audit row only; balance unchanged (D-26). Idempotent on UNIQUE(reference_id='evt_...', reference_type='stripe_event')."""
    try:
        await conn.execute(
            "INSERT INTO credit_transactions (user_id, kind, amount_cents, reference_id, reference_type) "
            "VALUES ($1, 'tier_change', 0, $2, 'stripe_event')",
            user_id, stripe_event_id,
        )
    except asyncpg.UniqueViolationError:
        pass  # already audited
```

**File 4 — `api_server/src/api_server/main.py` modification:** Add StripeClient construction in `lifespan` between Sentry init and Temporal connect:

```python
# In lifespan, after Sentry init (around current line 174), before Temporal connect (around line 199):
from .services.stripe_client import build_stripe_client
app.state.stripe_client = build_stripe_client(settings)
_log.info("stripe_client.initialized api_key_prefix=%s", settings.stripe_api_key[:7])
```

**File 5 — `api_server/tests/conftest.py` extension:** Add a `stripe_client_test` fixture that returns a `stripe.StripeClient` configured for stripe-mock (`stripe.api_base = "http://localhost:12111"` if `STRIPE_MOCK_HOST` env set; else use `"sk_test_dummy"` for shape-only). Mirror existing `async_client` fixture style. Skip the test if pytest mark `phase_b_e2e` is set AND `AP_STRIPE_TEST_API_KEY` is missing.

**File 6 — `api_server/tests/test_billing_packs.py`:** Unit tests for the PACKS module (no DB needed — mock `get_settings()` to return a fake Settings object with the 5 pack price IDs).

**File 7 — `api_server/tests/test_ledger_atomic.py`:** Postgres testcontainer + asyncpg pool. Run migration 014 (use the testcontainer pattern from `test_migration_014_phase_b.py`). Then run all the ledger.py behavior tests including the 8-way concurrent debit conservation (mirror spike-c).
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run pytest tests/test_billing_packs.py tests/test_ledger_atomic.py -x</automated>
  </verify>
  <done>
- All 4 billing_packs tests + 5 ledger atomic tests pass.
- `grep "app.state.stripe_client = build_stripe_client" api_server/src/api_server/main.py | wc -l` outputs `1`.
- `grep "@dataclass(frozen=True)" api_server/src/api_server/services/billing_packs.py` finds the Pack dataclass.
- `cd api_server && uv run python -c "from api_server.services.billing_packs import PACKS; print(len(PACKS))"` prints `5` (with stub Settings env).
- All ledger helpers honor the caller-owned-transaction contract (no internal `conn.transaction()` for debit_user / credit_user / record_tier_change — the helpers DO use `_ensure_balance_row` outside the conditional INSERT, but caller wraps the whole thing).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Settings env → process memory | secret keys load from env-loaded Settings; never from DB or logs |
| api_server → Stripe API | StripeClient instance carries the secret key; outbound HTTPS only |
| asyncpg pool → Postgres | atomic ledger transactions; UNIQUE constraints prevent double-write |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-LK | InfoDisclosure | services/stripe_client.py + lifespan log | mitigate | log only `api_key_prefix=settings.stripe_api_key[:7]` (e.g. `sk_test_`); never log full key. Extend Phase 29 _redact_creds in a later wave to mask `sk_live_*`, `sk_test_*`, `whsec_*` if any code path could log them |
| T-B-LR | Tampering | services/stripe_client.py::lazy_create_or_fetch_customer | mitigate | SELECT ... FOR UPDATE serializes concurrent first-clicks; spike-g proved this in Wave 0 |
| T-B-IDP | Tampering | services/ledger.py::debit_user | mitigate | UNIQUE(reference_id, reference_type) raises UniqueViolationError; helper catches and returns originally-debited amount |
| T-B-MIG | DoS | alembic/versions/014_phase_b_credit_ledger.py | mitigate | downgrade reverses every upgrade step; round-trip test enforces idempotency (spike-h proved in Wave 0) |
| T-B-XT | InfoDisclosure | services/ledger.py | mitigate | every helper takes user_id explicitly; no SELECT * cross-tenant query path |
</threat_model>

<verification>
- Migration 014 in alembic/versions/ + test passes against real testcontainer.
- StripeClient lifespan-owned on app.state.
- PACKS module-level frozen tuple of 5 dataclasses.
- ledger.py helpers caller-owned-transaction discipline.
- Settings extension produces dev placeholders + prod-fail validation.
</verification>

<success_criteria>
- `cd api_server && uv run pytest tests/test_migration_014_phase_b.py tests/test_billing_packs.py tests/test_ledger_atomic.py -x` — all green.
- `cd api_server && uv run alembic heads` shows the new migration head.
- `cd api_server && uv run python -m api_server.main` (or boot via uvicorn) succeeds in dev with placeholder warnings; no crash.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-02-SUMMARY.md` with the migration revision id, the lifespan wiring location, and any deviations from the spike artifacts.
</output>
