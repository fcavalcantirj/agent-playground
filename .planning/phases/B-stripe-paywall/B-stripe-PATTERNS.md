# Phase B: Stripe Paywall — Pattern Map

**Mapped:** 2026-05-08
**Files analyzed:** 38 new files + 10 modifications + 1 CI workflow + 2 deploy/Make changes
**Analogs found:** 47 / 51

> **CRITICAL — DO NOT REPLICATE (per CONTEXT canonical_refs):**
>
> 1. MSV "Pokens" proprietary unit. Phase B is **USD-cents end-to-end**.
> 2. Hardcoded catalog mirrored on the client. **Single SOT** in api_server (`GET /v1/billing/packs`); mobile fetches it. (`feedback_dumb_client_no_mocks.md`)
> 3. MSV's 75% post-facto BYOK discount hybrid. Phase B is bimodal: **BYOK = visibility only; Ultra = full metering**.
> 4. SSE pre-DONE chunk parsing for cost. Phase B re-uses post-hoc OpenRouter `/api/v1/generation` (Phase 29/30 already ship).
> 5. **Native uvicorn smoke alongside the deploy stack on macOS** (`memory/feedback_no_native_uvicorn_with_deploy_stack.md`). Rebuild the deploy api_server image (`docker compose -f deploy/docker-compose.prod.yml build api_server && up -d api_server`).
> 6. **`webview_flutter`** (AMD-03). Use `flutter_inappwebview` for Stripe Checkout return-URL interception.
> 7. **Legacy `stripe.Customer.create(...)` / `stripe.Webhook.construct_event(...)` module-level static methods** (AMD-04). Use `StripeClient` instance methods.
> 8. **Listening to `payment_intent.succeeded`** for credit-pack top-ups (AMD-05). Use `checkout.session.completed` only.

---

## File Classification

### api_server — NEW

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `api_server/alembic/versions/014_credit_balances_and_ledger.py` | migration | DDL + data backfill | `013_phase29_proxy_columns.py` (additive cols + check-constraint widening) + `010_usage_logs_cost_weights.py` (table create + seed rows) | exact (combine both) |
| `api_server/src/api_server/routes/billing.py` | controller | request-response (CRUD) | `routes/usage.py` (require_user + Pydantic models + asyncpg pool + ready-to-render JSON) | exact |
| `api_server/src/api_server/routes/billing_webhook.py` | controller | event-driven (inbound webhook) | NONE in AP (no inbound webhooks today). MSV `payment.go:576-725` for shape. Local analogs for the FastAPI primitives: `routes/llm_proxy.py:265-340` (raw `await request.body()`, request.app.state.* lookups, _err helper) | role-match (FastAPI primitives) + MSV (HMAC + idempotency + branch) |
| `api_server/src/api_server/services/stripe_client.py` | service | request-response (outbound HTTP) | NONE in AP for an SDK-wrapped service. Closest pattern is `services/proxy_byok_cache.py` for "lifespan-owned async object on `app.state.X`" + `services/usage_recorder.py:286-332` for "fetch DB config + apply business rule + return Decimal" | role-match |
| `api_server/src/api_server/services/billing_packs.py` | utility | static catalog (in-memory) | `services/proxy_dispatcher.py::PROVIDERS` (module-level frozen dict of provider specs; consumed by `routes/llm_proxy.py:302`) | exact |
| `api_server/src/api_server/services/ledger.py` | service | CRUD (atomic same-tx) | `services/usage_recorder.py:340-…` (asyncpg conn passed in, INSERT inside caller's transaction). MSV `web_user_repo.go:562` + `poken_service.go:180` for the SUM-rebuild idiom | exact (AP) + MSV (algorithm) |
| `api_server/src/api_server/services/tier_enforcement.py` | service | predicate / read-side filter | `services/inapp_messages_store.py` (asyncpg helpers used by routes; per-user `WHERE user_id=$1` filter) + `routes/usage.py:199-203` (Pattern A ownership check) | role-match |
| `api_server/src/api_server/temporal/activities/prune_messages.py` | activity | batch delete (cron-triggered) | `temporal/activities/record_usage.py` (class-bound `RecordUsageActivities`, asyncpg pool injected via `__init__`) | exact |
| `api_server/src/api_server/temporal/activities/reconcile_stripe.py` | activity | batch fetch + idempotent insert | `temporal/activities/backfill_openrouter_cost.py` (class-bound activity that talks to upstream HTTP via `proxy_upstream_http` + writes DB) | exact |
| `api_server/src/api_server/temporal/activities/reconcile_ledger.py` | activity | batch read + drift detection | `temporal/activities/record_usage.py` (asyncpg-only batch activity) | role-match |
| `api_server/src/api_server/temporal/workflows/prune_messages.py` | workflow | scheduled (cron) | `temporal/workflows/dispatch_message.py` (workflow.defn + execute_activity + retry policy + sandbox-passthrough imports) | role-match (cron variant; see Pattern 4 in RESEARCH) |
| `api_server/src/api_server/temporal/workflows/reconcile_stripe.py` | workflow | scheduled (cron) | same as above | role-match |
| `api_server/src/api_server/temporal/workflows/reconcile_ledger.py` | workflow | scheduled (cron) | same as above | role-match |
| `api_server/src/api_server/temporal/schedules.py` | utility | one-shot bootstrap | NONE in AP. RESEARCH §Pattern 4 supplies the exact try/RPCError/update_schedule template | role-match (RESEARCH) |
| `api_server/tests/test_migration_014_phase_b.py` | test | DDL assertion | `tests/test_migration_013_proxy_columns.py` (testcontainers Postgres 17 + alembic upgrade head + asyncpg DDL probes + downgrade round-trip) | exact |
| `api_server/tests/routes/test_billing_webhook.py` | test | integration (signed fixture POST → DB) | `tests/routes/test_llm_proxy.py` (real PG via testcontainers + respx for upstream + `async_client` fixture + `pytest.mark.api_integration`) | role-match |
| `api_server/tests/routes/test_billing_topup.py` | test | integration (route → Stripe SDK respx) | `tests/routes/test_llm_proxy.py` + `tests/routes/test_usage_endpoints.py` (seeded rows + `_seed_*` helpers) | exact |
| `api_server/tests/temporal/test_debit_balance_activity.py` | test | activity unit + integration | `tests/temporal/test_backfill_openrouter_cost_activity.py` (class-bound activity + Postgres testcontainer) | exact |
| `api_server/tests/test_ledger_atomic.py` | test | integration (Postgres concurrency) | `tests/test_inapp_messages_store.py` (asyncpg fixture + concurrent-task test pattern) | role-match |
| `api_server/tests/routes/test_pro_downgrade.py` | test | integration (webhook → tier flip → entitlement enforcement) | combination of `tests/routes/test_billing_webhook.py` (signed fixture) + `tests/routes/test_agent_lifecycle_inapp.py` (agent state assertions) | role-match |
| `api_server/tests/routes/test_tier_enforcement.py` | test | unit / integration (per-tier branches) | `tests/routes/test_usage_endpoints.py` (per-user `_seed_*` + assertion shape) | exact |
| `api_server/tests/routes/test_messages_list.py` | test | integration (retention filter) | `tests/test_inapp_messages_store.py` (insert old + recent rows; assert filter) | exact |
| `api_server/tests/routes/test_llm_proxy_402.py` | test | integration (proxy pre-flight) | `tests/routes/test_llm_proxy.py` (FakeBYOKCache, async_client, respx) | exact |
| `api_server/tests/temporal/test_prune_messages_workflow.py` | test | workflow integration | `tests/temporal/test_dispatch_message_workflow.py` (`WorkflowEnvironment.start_time_skipping`, fake activities, real worker registration) | role-match |
| `api_server/tests/temporal/test_reconcile_ledger_workflow.py` | test | workflow integration | same as above | role-match |
| `api_server/tests/_fixtures/sign_webhook.py` | test util | crypto helper | NONE in AP — RESEARCH AMD-02 supplies the exact `t=<unix>,v1=hmac_sha256(...)` formula | none (RESEARCH) |
| `api_server/tests/_fixtures/stripe_webhooks/` | test util | static JSON | NONE | none |

### api_server — MODIFICATIONS

| Modified File | Behavior Change | Closest "Don't Touch" Anchor |
|---------------|-----------------|------------------------------|
| `api_server/src/api_server/temporal/activities/debit_balance.py` | Replace body; preserve `@activity.defn(name="debit_balance")` decorator + `async def debit_balance(inp) -> str:` signature + `Decimal-as-string` return contract (Phase 28 D-22 lock). | The `name=` kwarg, the input dataclass arg, and the str return type are byte-identical to `activities/debit_balance.py:29-40`. |
| `api_server/src/api_server/routes/llm_proxy.py` | Insert pre-flight 402 block after BYOK cache resolves (`# ---------- 2.5 ----------` between current sections 2 and 3). NO other change. | The existing comment-numbered sections (`# ---------- 1. ... 2. ... 3. ----------`) at lines 274-322 are the contract. Insertion goes between section 2 (lines 296-304) and section 3 (lines 306-322). |
| `api_server/src/api_server/routes/usage.py` | `UsageSummaryResponse` adds optional `balance_cents: int | None` and `tier: str` fields; route projects them only when `users.tier='ultra'` (NULL/None for free/pro). | Pydantic response model + `_err()` helper + `require_user` flow at lines 51-69 + 162-179 stay byte-identical. |
| `api_server/src/api_server/auth/deps.py` | `require_user` (or sibling) exposes a way to read `users.tier`. Recommended shape: KEEP `require_user` returning `UUID` (no breaking change to dozens of routes); ADD a sibling `require_user_with_tier(request) -> JSONResponse | tuple[UUID, str]` that does ONE extra query. Per D-18 lazy re-read on every authenticated billing-touching call. | The `require_user` signature at lines 37-72 stays unchanged. Adding a new sibling helper preserves every existing call site. |
| `api_server/src/api_server/middleware/rate_limit.py` | Add `"billing": (?, 60)` bucket to `_LIMITS`; add path predicate matching `/v1/billing/{packs,balance,transactions,checkout,subscription}` (NOT `/v1/billing/webhook`); webhook is excluded (Stripe is the sole caller; rate-limiting Stripe causes retry storms). | Keep `_LIMITS` dict shape, `_bucket_for` precedence ordering, `_AUTH_ROUTE_KEYS` style of stable-alias mapping (to outlast path renames). |
| `api_server/src/api_server/config.py` | Add 9 new fields under existing `Settings`: `stripe_api_key`, `stripe_webhook_secret`, `stripe_price_id_pro_monthly`, plus 5× `stripe_price_id_pack_*`, with `validation_alias="AP_STRIPE_*"`. Optional in dev (placeholder warning); raise loudly in prod when any are missing (mirror OAuth `_resolve_or_fail`). | The `Field(...)` + `validation_alias=` pattern at lines 106-174 is the contract. |
| `api_server/pyproject.toml` | Add `"stripe>=15.0,<16.0"` to `[project.dependencies]` (per AMD-01). Re-lock via `cd api_server && uv lock`. | Pin floor-and-major-ceiling discipline used for `temporalio>=1.27.0,<1.28` (line 73) and `sentry-sdk[fastapi]>=2.20,<3.0` (line 85). |
| `api_server/src/api_server/main.py` | `lifespan`: construct `StripeClient(settings.stripe_api_key)` and stash on `app.state.stripe_client` (after Sentry init, before Temporal connect). `create_app`: register `billing` + `billing_webhook` routers under `/v1`. After Temporal client connect, call `register_schedules(client, task_queue)` once (idempotent — see RESEARCH Pattern 4). | Existing `app.state.X` assignment ordering at lines 84-285 is the contract. New `app.state.stripe_client` slots between line 174 (Sentry) and line 199 (Temporal connect). New `app.include_router(billing_route.router, prefix="/v1", tags=["billing"])` slots after line 600 (usage_route). |
| `api_server/src/api_server/temporal/worker.py` | Register the 3 new workflows + 3 new class-bound activities (`prune_acts`, `reconcile_stripe_acts`, `reconcile_ledger_acts`). After `make_client(settings)` succeeds, call `register_schedules(client, task_queue)` (worker boots schedules; if api_server boots first that's also fine — registration is idempotent on either side, so put it in BOTH places guarded with `try/except RPCError "already exists"`). | The `Worker(...)` constructor's `workflows=[...]`, `activities=[...]` lists at lines 222-242 + the class-bound activity instantiation block at lines 175-192 are the templates. |
| `api_server/Makefile` | Add `e2e-phase-b-stripe` target. | Mirror `e2e-money-path` shape from `Makefile:236-238` (top-level) AND the dockerized harness pattern from `api_server/Makefile:45-78` (since Phase B uses real Stripe TEST mode). |

### mobile — NEW

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `mobile/lib/features/billing/billing_models.dart` | model (DTOs) | JSON deserialize | `mobile/lib/features/usage/usage_models.dart` (hand-written `fromJson` per D-34, USD as `String`, defensive defaults) | exact |
| `mobile/lib/features/billing/billing_api.dart` | service | request-response (Dio) | `mobile/lib/core/api/api_client.dart:407-440` (Dio.get → `Result.ok(Model.fromJson(res.data!))` / DioException → `Result.err`) | exact |
| `mobile/lib/features/billing/billing_providers.dart` | provider | Riverpod hub | `mobile/lib/features/usage/usage_providers.dart` (`@riverpod` + `CancelToken` guard + `appLifecycleProvider` listen + Result switch) | exact |
| `mobile/lib/features/billing/topup_screen.dart` | component | UI screen | `mobile/lib/features/usage/agent_usage_screen.dart` (Scaffold + AppBar + async.when + RefreshIndicator + RetryBanner) | exact |
| `mobile/lib/features/billing/pack_picker_widget.dart` | component | list-render | `mobile/lib/features/dashboard/agent_row.dart` (card-list pattern with onTap) | role-match |
| `mobile/lib/features/billing/checkout_webview_screen.dart` | component | webview + nav delegate | NONE — RESEARCH §Example D supplies the `flutter_inappwebview` shape (navigationDelegate + shouldOverrideUrlLoading) | none (research only) |
| `mobile/lib/features/billing/insufficient_credits_modal.dart` | component | modal | `mobile/lib/shared/confirm_dialog.dart` (`showDialog`/`AlertDialog` pattern; D-21 explicitly REJECTS RetryBanner here) | role-match |
| `mobile/lib/features/billing/topup_inflight_widget.dart` | component | inflight UX | `mobile/lib/features/new_agent/deploy_step.dart:387-444` (Stopwatch + Timer.periodic 1s tick + mm:ss formatter + Cancel button) | exact |
| `mobile/lib/features/billing/transactions_screen.dart` | component | paginated list | `mobile/lib/features/usage/agent_usage_screen.dart` (RefreshIndicator + async.when + pull-to-refresh) | role-match |
| `mobile/test/features/billing/...` | tests | widget tests | `mobile/test/features/usage/usage_ticker_widget_test.dart`, `mobile/test/features/new_agent/deploy_step_test.dart` | exact |

### mobile — MODIFICATIONS

| Modified File | Behavior Change | Closest "Don't Touch" Anchor |
|---------------|-----------------|------------------------------|
| `mobile/pubspec.yaml` | Add `flutter_inappwebview: ^6.1.5` (verify latest at planning-time per AMD-03). | Existing dep ordering. |
| `mobile/lib/features/usage/usage_models.dart` | `UsageSummary` adds `String? tier` and `int? balanceCents` fields with defensive defaults. (D-21 + research line 700-704 — bimodal display.) | Hand-written `fromJson`, `String` for USD, defensive default-on-missing patterns at lines 14-32 stay the contract. |
| `mobile/lib/features/usage/usage_ticker_widget.dart` | When `summary.value.tier == 'ultra'`, render `formatCredits(balanceCents)` (new formatter); else render `formatUsd(totalUsd)` as today. | Single `Text(label, style: ...)` widget tree at lines 60-83 is the contract — only the `label` derivation changes. |
| `mobile/lib/features/dashboard/dashboard_providers.dart` | tier-aware projection (no behavior change unless tier=ultra). | `@riverpod class AgentsList` lines 36-82 stay byte-identical. |
| `mobile/lib/features/chat/chat_providers.dart` | When the POST /messages call returns 402, route to `InsufficientCreditsModal` (NOT to `chatStreamErrorProvider`/RetryBanner). The 402 is a **post**-classifier branch — extend `classifyChatStreamError` is OK BUT D-21 specifies modal not banner, so the dispatch is at the catchError site. | Existing `classifyChatStreamError` enum lines 13-25 + 401→authExpired branch at line 46 stay the contract. Add a new dispatch line for `status == 402` → call modal-show fn passed via Ref. |
| `mobile/lib/main.dart` + `mobile/lib/app.dart` | `loginSuccessProvider` listener AND any tier-flip event update the Sentry user context with `setData('tier', tier)`. (D-18 lazy re-read; research §Mobile section.) | `Sentry.configureScope((scope) => scope.setUser(SentryUser(id: next.id)))` at `app.dart:72-74` is the contract. Add `..setData('tier', next.tier)` adjacent. |
| `mobile/lib/core/router/app_router.dart` | Add `/billing/topup`, `/billing/checkout`, `/billing/transactions` routes. | `GoRoute(...)` shape at lines 89-95 is the template. |
| `mobile/lib/core/api/api_endpoints.dart` | Add `billingPacks`, `billingBalance`, `billingTransactions`, `billingCheckout`, `billingSubscription`. | `static const String usageSummary = '/v1/usage/summary';` line 40 is the template. |
| `mobile/lib/core/api/api_client.dart` | Add `billingPacks()`, `billingBalance()`, `createCheckoutSession({pack_id})`, `createSubscription()`, `billingTransactions({limit, before})` methods. | Method shape at lines 407-440 is the template. |

### deploy + CI

| File | Change | Analog |
|------|--------|--------|
| `deploy/.env.prod` | Add `AP_STRIPE_API_KEY`, `AP_STRIPE_WEBHOOK_SECRET`, `AP_STRIPE_PRICE_ID_PRO_MONTHLY`, 5× `AP_STRIPE_PRICE_ID_PACK_*`. | Existing `AP_OAUTH_*` block in `deploy/.env.prod` (per CLAUDE.md "Local dev" section). |
| `docker-compose.dev.yml` | Add `stripe-mock` service on port 12111 (image `stripe/stripe-mock:latest`). | `redis` service block at `docker-compose.dev.yml:55-65`. |
| `.github/workflows/e2e-phase-b.yml` | New CI workflow gated on `secrets.AP_STRIPE_TEST_API_KEY` + `secrets.AP_STRIPE_TEST_WEBHOOK_SECRET`. | `.github/workflows/e2e-money-path.yml` (full file, 1-90; mirror concurrency block, env-var-via-secrets, postgres+redis boot, alembic upgrade, real upstream call). |

---

## Pattern Assignments

### `014_credit_balances_and_ledger.py` (migration, DDL + data)

**Analog 1 (additive cols + check-constraint widening + data backfill):** `api_server/alembic/versions/013_phase29_proxy_columns.py`
**Analog 2 (table create + check constraints + seed rows):** `api_server/alembic/versions/010_usage_logs_cost_weights.py`

**Revision header pattern** (`013_phase29_proxy_columns.py:60-69`):

```python
revision = "014_credit_balances_and_ledger"   # ≤32 chars per alembic_version.version_num
down_revision = "013_phase29_proxy_columns"
branch_labels = None
depends_on = None
```

**Additive column pattern** (`013_phase29_proxy_columns.py:76-98`):

```python
def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tier", sa.Text(), nullable=False, server_default=sa.text("'free'")),
    )
    op.create_check_constraint(
        "ck_users_tier", "users",
        "tier IN ('free','pro','ultra')",
    )
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("refund_writeoff_cents", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )
```

**Table-create + index pattern** (`010_usage_logs_cost_weights.py:166-270`):

```python
op.create_table(
    "credit_transactions",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
              server_default=sa.text("gen_random_uuid()")),
    sa.Column("user_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("kind", sa.Text(), nullable=False),
    sa.Column("amount_cents", sa.BigInteger(), nullable=False),
    sa.Column("reference_id", sa.Text(), nullable=True),
    sa.Column("reference_type", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.text("NOW()")),
)
op.create_check_constraint(
    "ck_credit_transactions_kind", "credit_transactions",
    "kind IN ('topup','debit','refund','tier_change','admin_writeoff')",
)
# Idempotency-on-retry per D-17: UNIQUE on (reference_id, reference_type)
# so a Temporal-retried debit cannot insert a second row.
op.create_index(
    "uq_credit_transactions_reference",
    "credit_transactions", ["reference_id", "reference_type"],
    unique=True, postgresql_where=sa.text("reference_id IS NOT NULL"),
)
op.create_index(
    "ix_credit_transactions_user_created",
    "credit_transactions",
    ["user_id", sa.text("created_at DESC")],
)
```

**Data-backfill pattern** (`013_phase29_proxy_columns.py:118-120` for the `op.execute(...)` style):

```python
# D-08 — bump ap_multiplier 1.0 → 1.15 across all rows.
op.execute("UPDATE cost_weights SET ap_multiplier = 1.15 WHERE ap_multiplier = 1.0")
# D-26 — backfill users.tier (no-op when server_default='free' applies on column add).
```

**Downgrade discipline** (`013_phase29_proxy_columns.py:151-188`): mirror `upgrade` in reverse order; document irreversible operations explicitly.

---

### `routes/billing.py` (controller, request-response — CRUD)

**Analog:** `api_server/src/api_server/routes/usage.py`

**Imports + module shape** (`usage.py:26-44`):

```python
from __future__ import annotations
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth.deps import require_user
from ..models.errors import ErrorCode, make_error_envelope

_log = logging.getLogger("api_server.billing")
router = APIRouter()
```

**Pydantic response model + `_decimal_to_str` helper** (`usage.py:52-145`):

```python
class PackEntry(BaseModel):
    id: str
    label: str
    usd_amount_cents: int
    credit_cents: int

class PackCatalogResponse(BaseModel):
    packs: list[PackEntry]

class BalanceResponse(BaseModel):
    tier: str
    balance_cents: int
    display_balance_cents: int
    is_negative: bool
```

**Auth + handler pattern** (`usage.py:162-179`):

```python
@router.get("/billing/balance", response_model=BalanceResponse)
async def get_balance(request: Request):
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.tier, COALESCE(b.balance_cents, 0) AS balance_cents
            FROM users u LEFT JOIN credit_balances b ON b.user_id = u.id
            WHERE u.id = $1
            """,
            user_id,
        )
    return BalanceResponse(
        tier=row["tier"],
        balance_cents=row["balance_cents"],
        display_balance_cents=max(row["balance_cents"], 0),
        is_negative=row["balance_cents"] < 0,
    )
```

**`_err()` helper** (`usage.py:107-121`): mirror byte-identical so 4xx envelopes stay uniform across the surface.

---

### `routes/billing_webhook.py` (controller, event-driven — inbound webhook)

**Analog 1 (FastAPI raw-body + app.state lookup + _err pattern):** `api_server/src/api_server/routes/llm_proxy.py:265-340`
**Analog 2 (HMAC verify + idempotency + branch on event_type):** MSV `payment.go:576-725` + RESEARCH §Pattern 1

**Raw body + signature header read** (mirror `llm_proxy.py:307-308` for the `await request.body()` idiom; never `await request.json()` first — Stripe signs raw bytes):

```python
@router.post("/billing/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    payload = await request.body()  # MUST be raw bytes — see RESEARCH Pitfall 1
    if stripe_signature is None:
        return _err(400, ErrorCode.INVALID_REQUEST, "missing signature")

    settings = request.app.state.settings
    client = request.app.state.stripe_client  # StripeClient (AMD-04)
    try:
        event = client.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret,
        )
    except stripe.SignatureVerificationError:
        return _err(400, ErrorCode.UNAUTHORIZED, "bad signature")
```

**Idempotency + side-effect in same transaction** (mirror RESEARCH §Pattern 1 + Pitfall 2 — INSERT into `stripe_webhook_events` AND apply side-effect inside ONE `async with conn.transaction():` block):

```python
pool = request.app.state.db
async with pool.acquire() as conn:
    async with conn.transaction():
        inserted = await conn.fetchval(
            """
            INSERT INTO stripe_webhook_events (stripe_event_id, event_type, payload)
            VALUES ($1, $2, $3)
            ON CONFLICT (stripe_event_id) DO NOTHING
            RETURNING stripe_event_id
            """,
            event.id, event.type, payload.decode(),
        )
        if inserted is None:
            return JSONResponse({"received": True}, status_code=200)
        # Branch on event type — side-effect runs in SAME transaction.
        if event.type == "checkout.session.completed":
            await _handle_checkout_completed(conn, event.data.object)
        elif event.type == "customer.subscription.created":
            ...
        # AMD-05: do NOT branch on payment_intent.succeeded for credit packs
        # (only payment_intent.payment_failed is in the matrix).
return JSONResponse({"received": True}, status_code=200)
```

**Public route — NO `require_user`** (only inbound webhook in the codebase; auth is via Stripe-Signature HMAC).

**Webhook handler placement on the rate-limit allowlist:** when modifying `middleware/rate_limit.py`, ensure `/v1/billing/webhook` does **not** match the `billing` bucket — Stripe is the sole caller and rate-limiting Stripe causes its retry storm to escalate.

---

### `services/stripe_client.py` (service, request-response — outbound)

**Analog 1 (process-wide async object on app.state, lifespan-owned):** `api_server/src/api_server/services/proxy_byok_cache.py` (per `main.py:280-285`)
**Analog 2 (DB lookup + business rule + Decimal return):** `api_server/src/api_server/services/usage_recorder.py:286-332`

**StripeClient instance pattern (AMD-04):** the v15 SDK exposes `stripe.StripeClient(api_key)`. Construct ONCE in `main.lifespan` (or `worker.main` if reconcile activities need it), stash on `app.state.stripe_client`. Routes / activities read it via `request.app.state.stripe_client` (mirror `llm_proxy.py:297` `request.app.state.proxy_byok_cache`).

**Service-method shape** (RESEARCH §Example C, lines 714-760):

```python
async def create_pack_checkout_session(
    *, conn, user_id: UUID, pack_id: str, success_url: str, cancel_url: str,
    client: StripeClient,
) -> str:
    # 1. Lazy customer create (D-11) under SELECT FOR UPDATE (Pitfall 5).
    async with conn.transaction():
        row = await conn.fetchrow(
            "SELECT email, stripe_customer_id FROM users WHERE id = $1 FOR UPDATE",
            user_id,
        )
        customer_id = row["stripe_customer_id"]
        if customer_id is None:
            customer = client.customers.create(params={
                "email": row["email"],
                "metadata": {"ap_user_id": str(user_id)},
            })
            customer_id = customer.id
            await conn.execute(
                "UPDATE users SET stripe_customer_id = $1 WHERE id = $2",
                customer_id, user_id,
            )
    # 2. Lookup pack catalog (single SOT — billing_packs.PACKS).
    pack = next(p for p in PACKS if p.id == pack_id)
    # 3. Create Checkout Session.
    session = client.checkout.sessions.create(params={
        "customer": customer_id,
        "mode": "payment",
        "line_items": [{"price": pack.stripe_price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "allow_promotion_codes": True,                 # D-24
        "metadata": {
            "ap_user_id": str(user_id),
            "pack_id": pack.id,
            "credit_cents": str(pack.credit_cents),
        },
        "automatic_tax": {"enabled": True},            # Stripe Tax (D-Discretion)
    })
    return session.url
```

**Race-defense for lazy customer create** (Pitfall 5): the `SELECT ... FOR UPDATE` on the user row serializes concurrent first-clicks.

---

### `services/billing_packs.py` (utility, static catalog)

**Analog:** `api_server/src/api_server/services/proxy_dispatcher.py::PROVIDERS` (read by `routes/llm_proxy.py:302` and `services/proxy_byok_cache.py`).

**Pattern:** module-level frozen dict / list of dataclasses, importable everywhere. NO database table for the catalog — D-06 hardcodes the 5 packs in api_server. Mobile fetches via `GET /v1/billing/packs` (dumb-client rule).

```python
from dataclasses import dataclass
from ..config import get_settings   # to read AP_STRIPE_PRICE_ID_PACK_*

@dataclass(frozen=True)
class Pack:
    id: str
    label: str
    usd_amount_cents: int
    credit_cents: int                # D-07: 1:1 with usd_amount_cents
    stripe_price_id: str

def _packs_from_settings() -> list[Pack]:
    s = get_settings()
    return [
        Pack(id="pack_5",   label="$5",   usd_amount_cents=500,   credit_cents=500,   stripe_price_id=s.stripe_price_id_pack_5),
        Pack(id="pack_10",  label="$10",  usd_amount_cents=1000,  credit_cents=1000,  stripe_price_id=s.stripe_price_id_pack_10),
        Pack(id="pack_25",  label="$25",  usd_amount_cents=2500,  credit_cents=2500,  stripe_price_id=s.stripe_price_id_pack_25),
        Pack(id="pack_50",  label="$50",  usd_amount_cents=5000,  credit_cents=5000,  stripe_price_id=s.stripe_price_id_pack_50),
        Pack(id="pack_100", label="$100", usd_amount_cents=10000, credit_cents=10000, stripe_price_id=s.stripe_price_id_pack_100),
    ]

PACKS = _packs_from_settings()
```

---

### `services/ledger.py` (service, atomic same-DB-tx)

**Analog 1 (asyncpg conn passed in, INSERT inside caller's transaction):** `api_server/src/api_server/services/usage_recorder.py:340-420`
**Analog 2 (atomic credit/debit + version idiom):** MSV `web_user_repo.go:562` + `poken_service.go:180`

**Function signature pattern** (`usage_recorder.py:340-354`): caller-owned conn + transaction; helper does NOT commit:

```python
async def debit_user(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    cost_cents: int,
    reference_id: str,           # e.g. usage_logs.id
    reference_type: str = 'usage_log',
) -> Decimal:
    """Insert ledger debit row + UPDATE balance cache.

    Caller MUST be inside an asyncpg transaction. Returns USD as Decimal
    (workflow stringifies to preserve Phase 28 D-22 contract).

    Idempotent on UNIQUE(reference_id, reference_type): a Temporal-retried
    debit raises asyncpg.UniqueViolationError; caller catches and returns
    the previously-debited amount.
    """
    try:
        await conn.execute(
            """
            INSERT INTO credit_transactions
                (user_id, kind, amount_cents, reference_id, reference_type)
            VALUES ($1, 'debit', $2, $3, $4)
            """,
            user_id, -cost_cents, reference_id, reference_type,
        )
    except asyncpg.UniqueViolationError:
        return Decimal(cost_cents) / Decimal(100)   # already debited
    # SUM-from-ledger rebuild (D-17) — single statement caches drift away.
    await conn.execute(
        """
        UPDATE credit_balances
           SET balance_cents = (SELECT COALESCE(SUM(amount_cents), 0)
                                FROM credit_transactions WHERE user_id = $1),
               updated_at = NOW()
         WHERE user_id = $1
        """,
        user_id,
    )
    return Decimal(cost_cents) / Decimal(100)
```

**Mirror functions:** `credit_user(conn, user_id, kind, amount_cents, reference_id, reference_type)` + `record_tier_change(conn, user_id, from_tier, to_tier, stripe_event_id)`.

---

### `temporal/activities/debit_balance.py` (activity body REPLACEMENT)

**Analog 1 (class-bound activity + asyncpg pool injection):** `api_server/src/api_server/temporal/activities/record_usage.py`
**Analog 2 (algorithm — read usage_logs → compute cents → insert ledger → rebuild cache):** RESEARCH §Pattern 2 (lines 374-443)

**Contract DO-NOT-CHANGE** (per CONTEXT D-22 + Phase 28 D-22 lock):

- `@activity.defn(name="debit_balance")` — keep the `name=` kwarg byte-identical.
- `async def debit_balance(inp) -> str:` — keep the signature; takes the workflow's `DispatchMessageInput` dataclass.
- Returns Decimal-to-string (e.g. `"0.000034"` or `"0"`); the workflow's `execute_activity(...)` call site at `workflows/dispatch_message.py:194-205` is sealed.

**Activity body shape** (mirror `record_usage.py:42-81` for the class-bound + asyncpg pool pattern):

```python
class DebitBalanceActivities:
    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="debit_balance")
    async def debit_balance(self, inp: Any) -> str:
        """Phase B body — ledger debit on success only (D-13)."""
        from ...services.ledger import debit_user
        from decimal import Decimal
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                # Bail when not platform-billed.
                tier = await conn.fetchval(
                    "SELECT tier FROM users WHERE id = $1::uuid", inp.user_id,
                )
                if tier != "ultra":
                    return "0"
                # Read the usage_logs row created by llm_proxy.py.
                row = await conn.fetchrow(
                    "SELECT id, cost_usd, status FROM usage_logs "
                    "WHERE message_id = $1::uuid AND user_id = $2::uuid "
                    "ORDER BY created_at DESC LIMIT 1",
                    inp.message_id, inp.user_id,
                )
                if row is None or row["status"] != "success" or not row["cost_usd"]:
                    return "0"            # D-13 — debit only on success.
                cost_cents = int((row["cost_usd"] * Decimal(100)).quantize(Decimal("1")))
                if cost_cents <= 0:
                    return "0"
                charged = await debit_user(
                    conn,
                    user_id=row_user_id,
                    cost_cents=cost_cents,
                    reference_id=str(row["id"]),
                    reference_type="usage_log",
                )
                return str(charged)
```

**Worker registration delta** (`worker.py:175-242`): instantiate `debit_acts = DebitBalanceActivities(db_pool=db_pool)` and replace the standalone `debit_balance` import + line 237 with `debit_acts.debit_balance`. (Currently the standalone module-level `@activity.defn` exists; switch to class-bound mirroring `record_usage.py`'s shape for proper db_pool injection.)

---

### `routes/llm_proxy.py` MODIFICATION (pre-flight 402 insertion)

**Analog:** RESEARCH §Pattern 3 (lines 446-470)

**Insertion point:** between current section 2 (BYOK cache resolve at line 296-304) and section 3 (body mutation at line 306-322). Add a comment line `# ---------- 2.5. Phase B pre-flight 402 (D-12) ----------` so the section-numbered comment scheme stays continuous.

```python
# ---------- 2.5. Phase B pre-flight 402 (D-12) ----------
async with request.app.state.db.acquire() as conn:
    row = await conn.fetchrow(
        """
        SELECT u.tier, COALESCE(b.balance_cents, 0) AS balance_cents
        FROM users u
        LEFT JOIN credit_balances b ON b.user_id = u.id
        WHERE u.id = $1
        """,
        user_id,
    )
if row and row["tier"] == "ultra" and row["balance_cents"] < 1:
    return _err(402, ErrorCode.INSUFFICIENT_BALANCE,
                "Out of credits. Top up to continue.")
```

**Note on `ErrorCode.INSUFFICIENT_BALANCE`:** add to `models/errors.py`'s ErrorCode enum (mirrors how Phase 27 added `AGENT_NOT_FOUND`, etc).

**Predicate intentionally covers negative balances** (RESEARCH Security V4): `< 1` is true for both 0 and any negative — D-16 refunds that drive balance negative correctly trigger 402.

---

### Workflows: `prune_messages.py`, `reconcile_stripe.py`, `reconcile_ledger.py`

**Analog (workflow shape, sandbox imports, retry policy):** `api_server/src/api_server/temporal/workflows/dispatch_message.py:1-50, 86-238`

**Cron-style workflow body pattern** (a 2-step workflow vs dispatch_message's 4-step):

```python
@workflow.defn(name="PruneMessagesWorkflow")
class PruneMessagesWorkflow:
    @workflow.run
    async def run(self) -> int:
        deleted = await workflow.execute_activity(
            prune_messages.prune_messages,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return deleted
```

**Sandbox imports** (`dispatch_message.py:41-50`):

```python
with workflow.unsafe.imports_passed_through():
    from ..activities import prune_messages
```

**Worker registration** (`worker.py:222-242`):

```python
worker = Worker(
    client,
    task_queue=settings.temporal_task_queue,
    workflows=[
        DispatchMessageWorkflow,
        BackfillOpenRouterCostWorkflow,
        PruneMessagesWorkflow,           # NEW
        ReconcileStripeWorkflow,         # NEW
        ReconcileLedgerWorkflow,         # NEW
    ],
    activities=[
        ready_acts.check_container_ready,
        forward_acts.forward_to_agent,
        usage_acts.record_usage,
        emit_inapp_outbound,
        mark_acts.mark_message_done,
        mark_failed_acts.mark_message_failed,
        debit_acts.debit_balance,        # CHANGED — class-bound now
        backfill_acts.backfill,
        prune_acts.prune_messages,       # NEW
        reconcile_stripe_acts.reconcile, # NEW
        reconcile_ledger_acts.reconcile, # NEW
    ],
    max_concurrent_activities=10,
    max_activities_per_second=5,
)
```

---

### `temporal/schedules.py` (one-shot bootstrap)

**Analog:** RESEARCH §Pattern 4 (lines 481-541) — exact try/RPCError/update template.

**Idempotent re-creation key:** wrap each `client.create_schedule(id, schedule)` in `try / except RPCError if "already exists" in str(e).lower(): get_schedule_handle(id).update(lambda _: schedule)`. Without this guard the worker crash-loops on second boot (Pitfall 8).

---

### `tests/test_migration_014_phase_b.py` (DDL assertion)

**Analog:** `api_server/tests/test_migration_013_proxy_columns.py` (88 lines visible; full file is the reference)

**Pattern:**
1. Module-scoped Postgres 17 testcontainer.
2. `_alembic(container, "upgrade", "head")` → assert column shapes via asyncpg `pg_attribute` probes.
3. `_alembic(container, "downgrade", "-1")` → assert columns removed.
4. `_alembic(container, "upgrade", "head")` → assert idempotent.
5. `pytestmark = pytest.mark.api_integration`.

**Specific Phase B assertions (per CONTEXT D-26 + D-08):**
- `users.tier` = TEXT NOT NULL DEFAULT 'free' with CHECK constraint allowing `('free','pro','ultra')`.
- `users.stripe_customer_id` = TEXT NULL.
- `users.refund_writeoff_cents` = BIGINT NOT NULL DEFAULT 0.
- `credit_balances` table exists with PK = user_id (FK ON DELETE CASCADE), `balance_cents` BIGINT NOT NULL DEFAULT 0.
- `credit_transactions` table with `kind` CHECK including `('topup','debit','refund','tier_change','admin_writeoff')` and UNIQUE(reference_id, reference_type) WHERE reference_id IS NOT NULL.
- `stripe_webhook_events` with UNIQUE(stripe_event_id).
- Data migration: `cost_weights.ap_multiplier` rows previously at 1.0 are now 1.15.

---

### `tests/routes/test_billing_webhook.py` (integration — signed fixtures)

**Analog 1 (testcontainers + respx + async_client):** `api_server/tests/routes/test_llm_proxy.py:1-80, 50-78`
**Analog 2 (signed fixture helper — AMD-02):** RESEARCH AMD-02 (lines 96 + Wave 0 Gaps line 943)

**Key fixture (NEW — `tests/_fixtures/sign_webhook.py`):** hand-rolled HMAC because stripe-mock has no webhook simulation:

```python
import hashlib, hmac, time

def sign_webhook_payload(payload_bytes: bytes, secret: str) -> str:
    t = int(time.time())
    sig = hmac.new(
        secret.encode(), f"{t}.{payload_bytes.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"t={t},v1={sig}"
```

**Test pattern (mirror `test_llm_proxy.py:1-80`):**

```python
@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_subscription_created_flips_tier(async_client, db_pool):
    user_id = await _seed_user_with_stripe_customer(db_pool, customer_id="cus_test_123")
    payload = json.dumps({...subscription.created event payload...}).encode()
    sig = sign_webhook_payload(payload, secret="whsec_test")
    r = await async_client.post(
        "/v1/billing/webhook", content=payload,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    async with db_pool.acquire() as conn:
        tier = await conn.fetchval("SELECT tier FROM users WHERE id = $1", user_id)
    assert tier == "pro"
```

**Coverage mandates** (from CONTEXT D-22 + RESEARCH §Validation Architecture line 916-930):
- `test_signature_required` — bad sig → 400.
- `test_idempotent_redelivery` — same event id twice → exactly one side-effect.
- `test_subscription_created_flips_tier` — `customer.subscription.created` → tier=pro.
- `test_checkout_completed_credits_balance` — `checkout.session.completed` for pack → ledger row + balance updated.
- `test_charge_refunded_negates_amount` — refund → ledger negative row.

---

### `tests/temporal/test_debit_balance_activity.py`

**Analog:** `api_server/tests/temporal/test_backfill_openrouter_cost_activity.py` (class-bound activity + Postgres testcontainer + WorkflowEnvironment)

**Pattern:**
- Use `WorkflowEnvironment.start_time_skipping()` (mirror `test_dispatch_message_workflow.py:84-120`).
- Register `DebitBalanceActivities(db_pool=test_pool).debit_balance` against a unique-task-queue worker.
- Drive via a tiny test workflow that invokes the activity directly (or call via `Client.execute_activity` if SDK supports).
- Coverage: `test_no_debit_when_tier_free`, `test_no_debit_on_failed_status`, `test_no_debit_on_zero_cost`, `test_idempotent_on_retry` (UNIQUE violation path), `test_balance_rebuilds_from_sum`.

---

### Mobile: `features/billing/billing_models.dart` (DTOs)

**Analog:** `mobile/lib/features/usage/usage_models.dart`

**Discipline (D-34 + research line 5-12):**
- Hand-written `factory FromJson` (NO `json_serializable` / `build_runner` JSON codegen — Phase 24 D-34 lock).
- USD as `String`, NOT double.
- Defensive defaults: `(json['x'] as int?) ?? 0`, `(json['s'] as String?) ?? '0'`.

```dart
class Pack {
  const Pack({
    required this.id,
    required this.label,
    required this.usdAmountCents,
    required this.creditCents,
  });

  factory Pack.fromJson(Map<String, dynamic> json) => Pack(
        id: json['id'] as String,
        label: json['label'] as String,
        usdAmountCents: (json['usd_amount_cents'] as int?) ?? 0,
        creditCents: (json['credit_cents'] as int?) ?? 0,
      );

  final String id;
  final String label;
  final int usdAmountCents;
  final int creditCents;
}

class Balance {
  const Balance({
    required this.tier,
    required this.balanceCents,
    required this.displayBalanceCents,
    required this.isNegative,
  });
  factory Balance.fromJson(Map<String, dynamic> json) => Balance(
        tier: json['tier'] as String,
        balanceCents: (json['balance_cents'] as int?) ?? 0,
        displayBalanceCents: (json['display_balance_cents'] as int?) ?? 0,
        isNegative: (json['is_negative'] as bool?) ?? false,
      );
  final String tier;
  final int balanceCents;
  final int displayBalanceCents;
  final bool isNegative;
}
```

---

### Mobile: `features/billing/billing_api.dart` (Dio client + Result envelope)

**Analog:** `mobile/lib/core/api/api_client.dart:407-440`

```dart
Future<Result<List<Pack>>> billingPacks({CancelToken? cancelToken}) async {
  try {
    final res = await _dio.get<Map<String, dynamic>>(
      ApiEndpoints.billingPacks,
      cancelToken: cancelToken,
    );
    final raw = (res.data!['packs'] as List<dynamic>);
    return Result.ok(raw
        .map((e) => Pack.fromJson(e as Map<String, dynamic>))
        .toList(growable: false));
  } on DioException catch (e) {
    return Result.err(ApiError.fromDioException(e));
  }
}

Future<Result<String>> createPackCheckoutSession({
  required String packId,
  CancelToken? cancelToken,
}) async {
  try {
    final res = await _dio.post<Map<String, dynamic>>(
      ApiEndpoints.billingCheckout,
      data: {'pack_id': packId},
      cancelToken: cancelToken,
    );
    return Result.ok(res.data!['checkout_url'] as String);
  } on DioException catch (e) {
    return Result.err(ApiError.fromDioException(e));
  }
}
```

---

### Mobile: `features/billing/billing_providers.dart` (Riverpod hub)

**Analog:** `mobile/lib/features/usage/usage_providers.dart` (full file, 92 lines)

```dart
@riverpod
class BalanceNotifier extends _$BalanceNotifier {
  CancelToken? _cancel;

  @override
  Future<Balance> build() async {
    _cancel?.cancel('superseded by ref.invalidate');
    final cancel = _cancel = CancelToken();
    ref.onDispose(() {
      if (!cancel.isCancelled) cancel.cancel('BalanceNotifier disposed');
    });
    // Trigger #2 — refetch on app resume (lifted from usage_providers).
    ref.listen<AppLifecycleState>(appLifecycleProvider, (prev, next) {
      if (prev != next && next == AppLifecycleState.resumed) {
        ref.invalidateSelf();
      }
    });
    final api = ref.watch(apiClientProvider);
    final r = await api.billingBalance(cancelToken: cancel);
    return switch (r) {
      Ok(:final value) => value,
      // ignore: only_throw_errors
      Err(:final error) => throw error,
    };
  }
}
```

**Polling helper for post-Checkout** (D-21): the `checkout_webview_screen` returns success → providers invalidate `balanceNotifierProvider` repeatedly with a 1.5s throttle until `balance_cents` reflects the top-up (5–15s typical via webhook; backstopped by 5-min Temporal poller).

---

### Mobile: `features/billing/topup_inflight_widget.dart` (inflight UX)

**Analog:** `mobile/lib/features/new_agent/deploy_step.dart:387-444`

**Lift this exact widget shape**:

```dart
String _formatElapsed(Stopwatch? s) {
  final secs = s?.elapsed.inSeconds ?? 0;
  final mm = (secs ~/ 60).toString().padLeft(2, '0');
  final ss = (secs % 60).toString().padLeft(2, '0');
  return '$mm:$ss';
}

// In build(): for state == awaitingWebhook:
return Container(
  padding: const EdgeInsets.all(16),
  decoration: BoxDecoration(border: Border.all(color: SolvrColors.border)),
  child: Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Row(
        children: [
          SizedBox(width: 24, height: 24,
              child: CircularProgressIndicator(strokeWidth: 2)),
          SizedBox(width: 8),
          Expanded(child: Text('Confirming top-up…')),
        ],
      ),
      const SizedBox(height: 8),
      Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(_formatElapsed(elapsed),
              style: SolvrTextStyles.mono(fontSize: 12).copyWith(
                  color: SolvrColors.mutedForeground)),
          TextButton(onPressed: onCancel, child: const Text('Cancel')),
        ],
      ),
    ],
  ),
);
```

**Spinner + lock-trigger discipline** (`feedback_inflight_ui_for_long_awaits.md` per `deploy_step.dart:80-83`): keep `_cancel: CancelToken? _cancel;` + `_elapsed: Stopwatch? _elapsed;` + `_tick: Timer? _tick;` as the inflight-state triplet. Cancel `_tick` on success/failure/dispose to avoid leaks.

---

### Mobile: `features/billing/insufficient_credits_modal.dart` (402 modal)

**Analog (modal shape):** `mobile/lib/shared/confirm_dialog.dart`
**Anti-analog (D-21 EXPLICIT REJECTION):** `mobile/lib/shared/retry_banner.dart` is the Phase 31 H4 transient-SSE banner. **Do NOT** route the 402 there — the user picked blocking-modal UX.

```dart
Future<void> showInsufficientCreditsModal(BuildContext context) async {
  await showDialog<void>(
    context: context,
    barrierDismissible: false,             // BLOCKING — D-21
    builder: (ctx) => AlertDialog(
      title: const Text('Out of credits'),
      content: const Text('Top up your balance to keep chatting.'),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('Later'),
        ),
        FilledButton(
          onPressed: () {
            Navigator.of(ctx).pop();
            ctx.push('/billing/topup');     // D-21 — primary CTA
          },
          child: const Text('Top up'),
        ),
      ],
    ),
  );
}
```

---

### Mobile: `features/billing/checkout_webview_screen.dart` (InAppWebView)

**Analog:** RESEARCH §Example D (lines 766-803)

**Discipline:**
- Use `flutter_inappwebview` (AMD-03), NOT `webview_flutter`.
- `shouldOverrideUrlLoading` callback intercepts `success_url` / `cancel_url` (the Stripe-hosted Checkout page redirects to these on completion).
- Recommended `success_url`: `https://app.solvrlabs.com/billing/return-success?session_id={CHECKOUT_SESSION_ID}` (RESEARCH Open Q #2 — webview-internal sentinel; no AppLinks/UniversalLinks plumbing).
- Pop screen with a `_PaymentResult` enum (`success`/`cancelled`). Caller invalidates `balanceNotifierProvider` and shows `topup_inflight_widget` with the timer.

---

### Mobile: `core/api/api_endpoints.dart` MODIFICATION

**Analog:** `mobile/lib/core/api/api_endpoints.dart` (45 lines)

```dart
// Phase B — billing surface.
static const String billingPacks         = '/v1/billing/packs';
static const String billingBalance       = '/v1/billing/balance';
static const String billingTransactions  = '/v1/billing/transactions';
static const String billingCheckout      = '/v1/billing/checkout';
static const String billingSubscription  = '/v1/billing/subscription';
```

---

### `.github/workflows/e2e-phase-b.yml`

**Analog:** `.github/workflows/e2e-money-path.yml` (full 90 lines)

**Mandatory clones from money-path:**
- `concurrency.group: e2e-phase-b-stripe` + `cancel-in-progress: false` (real-money runs serialize).
- `env.AP_STRIPE_TEST_API_KEY: ${{ secrets.AP_STRIPE_TEST_API_KEY }}` + `env.AP_STRIPE_TEST_WEBHOOK_SECRET: ${{ secrets.AP_STRIPE_TEST_WEBHOOK_SECRET }}`.
- Boot `docker-compose.dev.yml` postgres + redis; wait for `pg_isready`.
- Create `agent_playground_api` DB; `make migrate-api`.
- Run `make e2e-phase-b-stripe`.
- Tear-down with `if: always()`.

**Webhook URL exposure for CI** (RESEARCH Wave 0 Gap line 947): the test process triggers events via `stripe trigger checkout.session.completed --add checkout_session:metadata.ap_user_id=<uid>` against a local Stripe CLI listener forwarding to `localhost:8000/v1/billing/webhook`. The deploy api_server container publishes 8000.

---

### `api_server/Makefile` `e2e-phase-b-stripe` target

**Analog 1 (top-level Makefile money-path):** `Makefile:236-238`
**Analog 2 (dockerized harness):** `api_server/Makefile:45-78`

Phase B integration tests need REAL Stripe TEST mode, so the simpler analog (top-level money-path) is the right shape:

```makefile
e2e-phase-b-stripe:  ## Phase B integration: real Stripe TEST mode
	@test -n "$$AP_STRIPE_TEST_API_KEY" || (echo "ERROR: AP_STRIPE_TEST_API_KEY not set" && exit 1)
	@test -n "$$AP_STRIPE_TEST_WEBHOOK_SECRET" || (echo "ERROR: AP_STRIPE_TEST_WEBHOOK_SECRET not set" && exit 1)
	cd api_server && pytest -m phase_b_e2e -v --tb=short
```

**`pytest.ini` marker** (Wave 0 Gap line 945): `phase_b_e2e` so default suites can `pytest -m 'not phase_b_e2e and not e2e_money_path'` to exclude both real-upstream gates.

---

## Shared Patterns

### Authentication (per-route, `require_user`)

**Source:** `api_server/src/api_server/auth/deps.py:37-72`
**Apply to:** Every `/v1/billing/*` route EXCEPT `/v1/billing/webhook` (which uses Stripe-Signature HMAC).

```python
result = require_user(request)
if isinstance(result, JSONResponse):
    return result
user_id: UUID = result
```

For tier-aware reads, use a NEW sibling helper `require_user_with_tier(request) -> JSONResponse | tuple[UUID, str]` (see "MODIFICATIONS" table above) — do NOT modify `require_user`'s signature (dozens of call sites).

### Error envelope (Stripe-shape across the surface)

**Source:** `api_server/src/api_server/models/errors.py` (`make_error_envelope`); helpers like `_err()` in `routes/usage.py:107-121` and `routes/llm_proxy.py:77-82`.
**Apply to:** Every billing 4xx/5xx response.

New ErrorCode values to add in this phase:
- `INSUFFICIENT_BALANCE` (402; pre-flight + post-debit-drained).
- `TIER_LIMIT_EXCEEDED` (403; agent.create cap, messages.list retention).
- `STRIPE_WEBHOOK_INVALID` (400; signature failure).
- `INVALID_PACK_ID` (400; client passed a pack id not in PACKS).

### Sentry instrumentation

**Source (api_server):** `api_server/src/api_server/middleware/session.py:91-97`
**Source (mobile):** `mobile/lib/app.dart:42-80`
**Apply to:** All new billing routes (errors auto-captured by FastAPI integration); on tier change, mobile updates `Sentry.configureScope((scope) => scope..setUser(SentryUser(id: id))..setData('tier', tier))`.

### Rate limiting

**Source:** `api_server/src/api_server/middleware/rate_limit.py:54-72` (`_AUTH_ROUTE_KEYS` + `_LIMITS` dict-of-tuples).
**Apply to:** Add `"billing": (?, 60)` and a `_BILLING_ROUTES` predicate matching the prefix `/v1/billing/` MINUS the webhook path.

```python
_LIMITS["billing"] = (30, 60)   # per-(user, route)
def _bucket_for(scope):
    ...
    if path.startswith("/v1/billing/") and path != "/v1/billing/webhook":
        return "billing"
    ...
```

### Asyncpg transaction discipline

**Source:** `api_server/src/api_server/services/usage_recorder.py:340-420`
**Apply to:** `services/ledger.py`, all billing-webhook side-effects, `debit_balance.py` activity.

- Caller owns the conn + transaction.
- Helper does NOT commit.
- For webhooks: dedupe INSERT + side-effect inside ONE `async with conn.transaction():` block (Pitfall 2).

### USD as JSON string (D-14 from Phase 27)

**Source:** `api_server/src/api_server/routes/usage.py:124-133` (`_decimal_to_str`)
**Apply to:** Any USD-typed field in billing responses; mobile DTOs use `String` for USD.

For `balance_cents` use `int` (cents already), not Decimal — same precedent as `usage_logs.cost_usd` (Decimal) vs `cost_weights.input_per_1m_usd` (Numeric); cents are safe as ints since BIGINT covers $92Q.

---

## No Analog Found

Files where the codebase has nothing close enough — planner should defer to RESEARCH.md examples + MSV references in CONTEXT canonical_refs.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `routes/billing_webhook.py` | controller | event-driven (inbound) | NO inbound webhooks exist in api_server today. Combine FastAPI primitives from `routes/llm_proxy.py:265-340` with the algorithm from MSV `payment.go:576-725` + RESEARCH §Pattern 1. |
| `services/stripe_client.py` | service | SDK wrapper | NO Stripe-shaped service exists. Use AP's "lifespan-owned object on app.state" pattern (`services/proxy_byok_cache.py`) + RESEARCH §Example C. |
| `mobile/lib/features/billing/checkout_webview_screen.dart` | mobile widget | webview + nav delegate | NO InAppWebView usage in codebase today. RESEARCH §Example D + AMD-03 supply the contract. |
| `tests/_fixtures/sign_webhook.py` | test util | crypto helper | NO HMAC fixture exists. AMD-02 supplies the formula. |

---

## Validation Gates (cross-reference)

The following Phase 31 H8-style real-upstream guarantees apply to Phase B:
- Phase B's `make e2e-phase-b-stripe` MUST run alongside (NOT replace) the existing `make e2e-money-path`. Both are real-money gates; both serialize via concurrency blocks; neither blocks the other.
- The Phase B exit gate (CONTEXT D-25) requires BOTH the automated CI workflow AND `B-HUMAN-UAT.md` walking the same flow.

---

## Metadata

**Analog search scope:**
- `api_server/src/api_server/{routes,services,middleware,auth,temporal,alembic,instrumentation}/`
- `api_server/tests/{,routes,services,temporal,e2e}/`
- `mobile/lib/{app.dart,main.dart}` + `mobile/lib/{core,features,shared}/`
- `mobile/test/features/`
- `.github/workflows/`
- `Makefile` + `api_server/Makefile`
- `deploy/{docker-compose.prod.yml,Caddyfile}` + `docker-compose.dev.yml`

**Files scanned:** ~80
**Analogs read in full or via targeted ranges:** 22
**Pattern extraction date:** 2026-05-08

---

## PATTERN MAPPING COMPLETE
