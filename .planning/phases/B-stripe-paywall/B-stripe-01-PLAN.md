---
phase: B-stripe
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - api_server/tests/_spikes/wave0_stripe_paywall.md
  - api_server/tests/_spikes/spike_a_webhook_signature.py
  - api_server/tests/_spikes/spike_b_debit_activity_contract.py
  - api_server/tests/_spikes/spike_c_atomic_ledger.py
  - api_server/tests/_spikes/spike_d_temporal_schedule.py
  - api_server/tests/_spikes/spike_g_lazy_customer_create.py
  - api_server/tests/_spikes/spike_h_migration_roundtrip.py
  - mobile/integration_test/spike_e_inappwebview_intercept.dart
  - api_server/tests/_spikes/spike_f_stripe_cli_deploy_stack.md
autonomous: false
gap_closure: false
requirements_addressed:
  - D-04 (webhook sole writer of users.tier — spike a verifies signature path)
  - D-09 (Temporal scheduled workflow — spike d verifies create_schedule idempotency)
  - D-10 (TEST keys gate — spike preconditions document them)
  - D-11 (lazy customer create — spike g)
  - D-12 (pre-flight 402 — built on spike c ledger pattern)
  - D-13 (debit only on success — spike b activity contract)
  - D-17 (ledger-as-truth — spike c concurrent debit safety)
  - D-22 (test substrate — spikes a + g use signed fixtures)
  - D-26 (migration backfill — spike h alembic round-trip)
  - AMD-01 (stripe>=15.0,<16.0 — spike imports verify)
  - AMD-02 (signed-fixture helper — spike a builds it)
  - AMD-03 (flutter_inappwebview — spike e exercises shouldOverrideUrlLoading)
  - AMD-04 (StripeClient.construct_event — spike a uses it)
  - AMD-05 (single-event listening — spike a documents which events the matrix subscribes to)
must_haves:
  truths:
    - "Webhook signature verification round-trip works against a hand-rolled signed fixture using StripeClient.construct_event (AMD-04)"
    - "debit_balance activity returns Decimal-as-string and is idempotent on UNIQUE(reference_id, reference_type) violation"
    - "Atomic ledger pattern (INSERT credit_transactions + UPDATE credit_balances same-tx) is concurrent-safe under 8 parallel debits"
    - "Temporal create_schedule + try/RPCError/update fallback produces an idempotent register_schedules helper that survives second worker boot"
    - "Mobile InAppWebView shouldOverrideUrlLoading callback intercepts a fake success_url before the page loads"
    - "Stripe CLI listen --forward-to http://localhost:8000/v1/billing/webhook delivers events to the deploy api_server container (NOT native uvicorn)"
    - "Lazy customer create under SELECT FOR UPDATE serializes two concurrent first-click requests into one Stripe Customer create"
    - "Migration 014 upgrade + downgrade + upgrade round-trip is idempotent and produces all expected schema shapes"
  artifacts:
    - path: "api_server/tests/_spikes/wave0_stripe_paywall.md"
      provides: "Wave 0 evidence file documenting 8 spike PASS results with command outputs"
      contains: "PASS"
    - path: "api_server/tests/_spikes/spike_a_webhook_signature.py"
      provides: "Hand-rolled signed-fixture + StripeClient.construct_event round-trip (AMD-02 + AMD-04)"
      exports: ["sign_webhook_payload"]
    - path: "api_server/tests/_spikes/spike_b_debit_activity_contract.py"
      provides: "Class-bound activity that returns Decimal-as-string and stays idempotent on retry"
    - path: "api_server/tests/_spikes/spike_c_atomic_ledger.py"
      provides: "Concurrent debit safety against real Postgres testcontainer"
    - path: "api_server/tests/_spikes/spike_d_temporal_schedule.py"
      provides: "Idempotent register_schedules helper template (try/RPCError/update)"
    - path: "mobile/integration_test/spike_e_inappwebview_intercept.dart"
      provides: "InAppWebView shouldOverrideUrlLoading interception evidence"
    - path: "api_server/tests/_spikes/spike_f_stripe_cli_deploy_stack.md"
      provides: "Manual evidence Stripe CLI delivers to deploy stack (NOT native uvicorn)"
    - path: "api_server/tests/_spikes/spike_g_lazy_customer_create.py"
      provides: "Race-free lazy customer create under SELECT FOR UPDATE"
    - path: "api_server/tests/_spikes/spike_h_migration_roundtrip.py"
      provides: "alembic upgrade/downgrade/upgrade idempotent round-trip evidence (DRAFT migration body lives here, not in alembic/versions yet)"
  key_links:
    - from: "spike_a_webhook_signature.py"
      to: "stripe.StripeClient.construct_event"
      via: "verified raw-bytes payload + Stripe-Signature header"
      pattern: "client\\.construct_event\\(payload, sig, secret\\)"
    - from: "spike_b_debit_activity_contract.py"
      to: "Phase 28 D-22 contract in workflows/dispatch_message.py"
      via: "@activity.defn(name='debit_balance') signature returns str"
      pattern: "@activity\\.defn\\(name=\"debit_balance\"\\)"
    - from: "spike_d_temporal_schedule.py"
      to: "temporalio.client.Client.create_schedule"
      via: "try/except RPCError 'already exists' + get_schedule_handle.update"
      pattern: "RPCError"
    - from: "spike_e_inappwebview_intercept.dart"
      to: "flutter_inappwebview.InAppWebView shouldOverrideUrlLoading"
      via: "NavigationActionPolicy.CANCEL on success URL match"
      pattern: "shouldOverrideUrlLoading"
---

<objective>
Wave 0 BLOCKING gate. Probe all 8 gray-area mechanisms identified in RESEARCH.md against real infra BEFORE any implementation wave seals. Per CLAUDE.md Golden Rule #5: every non-trivial mechanism (new HMAC path, new SDK service pattern, new activity contract, new mobile webview API, new Temporal schedule, new race-defense) gets spiked and the spike result captured as evidence.

Purpose: De-risk Phase B sealed plans. Without Wave 0 evidence, Wave 1+ executors would inherit the load-bearing assumptions from RESEARCH.md untested.
Output: 8 spike artifacts in `api_server/tests/_spikes/` (+ one mobile spike in `mobile/integration_test/`) AND a `wave0_stripe_paywall.md` summary file with PASS markers and command outputs. Human verification required before Wave 1 starts.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/phases/B-stripe-paywall/CONTEXT.md
@.planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md
@.planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md
@CLAUDE.md
@api_server/src/api_server/temporal/activities/debit_balance.py
@api_server/src/api_server/temporal/activities/record_usage.py
@api_server/src/api_server/temporal/worker.py
@api_server/src/api_server/services/proxy_byok_cache.py
@api_server/src/api_server/services/usage_recorder.py
@api_server/alembic/versions/013_phase29_proxy_columns.py
@api_server/tests/test_migration_013_proxy_columns.py
</context>

<preconditions>
**Stripe TEST keys MUST be present in environment before this plan runs (D-10):**
- `AP_STRIPE_TEST_API_KEY` (sk_test_*)
- `AP_STRIPE_TEST_WEBHOOK_SECRET` (whsec_*)

If absent, executor MUST stop and surface a `checkpoint:human-action` asking the user to add them to the deploy `.env` and rerun.

**Stripe CLI MUST be installed on host:**
- `which stripe` returns a path (install via `brew install stripe/stripe-cli/stripe` then `stripe login`).

**Deploy stack MUST be running (per CLAUDE.md macOS rule):**
- `docker compose -f deploy/docker-compose.prod.yml ps` shows api_server + temporal-worker + postgres + redis + temporal up.
- Native uvicorn MUST NOT be running side-by-side (split-brain trap).
</preconditions>

<tasks>

<task type="auto">
  <name>Task 1: Spike A + B + C — webhook signature, debit activity contract, atomic ledger</name>
  <files>api_server/tests/_spikes/sign_webhook.py, api_server/tests/_spikes/spike_a_webhook_signature.py, api_server/tests/_spikes/spike_b_debit_activity_contract.py, api_server/tests/_spikes/spike_c_atomic_ledger.py</files>
  <read_first>
    - .planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md (Patterns 1, 2; Pitfalls 1, 2, 4; AMD-02, AMD-04)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (sections "routes/billing_webhook.py", "services/ledger.py", "temporal/activities/debit_balance.py")
    - api_server/src/api_server/temporal/activities/record_usage.py (class-bound activity + asyncpg pool injection template)
    - api_server/src/api_server/temporal/activities/debit_balance.py (current "0" stub — contract to preserve byte-identically)
    - api_server/src/api_server/services/usage_recorder.py:286-420 (asyncpg-conn-passed-in helper pattern)
  </read_first>
  <action>
Add `stripe>=15.0,<16.0` to `api_server/pyproject.toml` `[project.dependencies]` and run `cd api_server && uv lock`. Then create the four files below.

**File 1 — `sign_webhook.py` (helper imported by every spike that needs a signed fixture; per AMD-02):**

```python
import hashlib
import hmac
import time

def sign_webhook_payload(payload_bytes: bytes, secret: str, ts: int | None = None) -> str:
    """Build a Stripe-Signature header value: t=<unix>,v1=<hmac_sha256(secret, f'{t}.{payload}')>"""
    t = ts if ts is not None else int(time.time())
    sig = hmac.new(
        secret.encode(),
        f"{t}.{payload_bytes.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"t={t},v1={sig}"
```

**File 2 — `spike_a_webhook_signature.py`:** Build a minimal `checkout.session.completed` JSON payload, sign it with `sign_webhook_payload(payload, "whsec_spike_secret")`, instantiate `stripe.StripeClient("sk_test_dummy")` (AMD-04 service pattern, NOT module-level), and call `client.construct_event(payload, signature, "whsec_spike_secret")`. Assert: (a) it returns an event with `event.id` and `event.type == "checkout.session.completed"`; (b) calling with a tampered payload raises `stripe.SignatureVerificationError`; (c) calling with a stale timestamp (`ts = int(time.time()) - 600`) raises `stripe.SignatureVerificationError` (Stripe SDK enforces 5-min tolerance by default). Wrap the script with `if __name__ == "__main__":` + `print("PASS spike-a")` on success. Run via `cd api_server && uv run python tests/_spikes/spike_a_webhook_signature.py`.

**File 3 — `spike_b_debit_activity_contract.py`:** Define a minimal `class DebitBalanceActivities` with `__init__(self, *, db_pool)` and `@activity.defn(name="debit_balance")` async method that returns `str`. Use `temporalio.testing.WorkflowEnvironment.start_time_skipping()` + a one-line test workflow that invokes the activity, wired with a Postgres testcontainer (mirror `tests/temporal/test_backfill_openrouter_cost_activity.py` shape — read it for fixture pattern). The activity body inserts a `credit_transactions` row with `reference_id="usage-fixture-1"`, `reference_type="usage_log"`, `amount_cents=-100`, then re-runs the same activity invocation: assert second invocation catches `asyncpg.UniqueViolationError` and returns the originally-debited Decimal-as-string. Schema for the spike is created inline via `conn.execute("CREATE TABLE ...")` for `credit_transactions` + `credit_balances` (do NOT add to alembic yet — that's Wave 1). Print `PASS spike-b` on success.

**File 4 — `spike_c_atomic_ledger.py`:** Postgres testcontainer + asyncpg pool. Create `users(id uuid pk, tier text)`, `credit_balances(user_id uuid pk, balance_cents bigint default 0)`, `credit_transactions(id uuid default gen_random_uuid() pk, user_id uuid, kind text, amount_cents bigint, reference_id text, reference_type text)` with UNIQUE(reference_id, reference_type). Seed one user with tier='ultra' and balance=10000. Spawn 8 concurrent asyncio tasks each running `async with conn.transaction(): INSERT debit row + UPDATE balance from SUM`. Wait for all tasks. Assert: final balance == initial - sum(deltas), all 8 ledger rows present, no double-decrement. Print `PASS spike-c` on success.
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run python tests/_spikes/spike_a_webhook_signature.py &amp;&amp; uv run python tests/_spikes/spike_b_debit_activity_contract.py &amp;&amp; uv run python tests/_spikes/spike_c_atomic_ledger.py</automated>
  </verify>
  <done>
- All three spike scripts print their respective `PASS spike-*` lines on stdout.
- `cd api_server && uv run python -c "import stripe; print(stripe.VERSION)"` prints a version starting with `15.`.
- `sign_webhook.py` exports `sign_webhook_payload`.
- Spike-b proves @activity.defn(name="debit_balance") + str return + UniqueViolationError-on-retry path.
- Spike-c proves 8-way concurrent debit conservation.
  </done>
</task>

<task type="auto">
  <name>Task 2: Spike D + G + H — Temporal schedule, lazy customer create, migration round-trip</name>
  <files>api_server/tests/_spikes/spike_d_temporal_schedule.py, api_server/tests/_spikes/spike_g_lazy_customer_create.py, api_server/tests/_spikes/spike_h_migration_roundtrip.py, api_server/tests/_spikes/draft_014_migration.py</files>
  <read_first>
    - .planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md (Pattern 4 — schedule registration; Pitfall 5 — race on lazy customer; Pitfall 8 — schedule re-creation)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (sections "014_credit_balances_and_ledger.py" — DDL templates; "services/stripe_client.py" — lazy customer)
    - api_server/alembic/versions/013_phase29_proxy_columns.py (revision header + upgrade/downgrade discipline template)
    - api_server/tests/test_migration_013_proxy_columns.py (testcontainer + alembic round-trip pattern)
    - api_server/src/api_server/temporal/worker.py (existing Temporal client setup)
  </read_first>
  <action>
**File 1 — `spike_d_temporal_schedule.py`:** Connect to the deploy stack's Temporal cluster (`AP_TEMPORAL_HOST=localhost:7233`). Define a trivial `@workflow.defn class SpikeDWorkflow: @workflow.run async def run(self) -> int: return 1`. Build the `register_schedules(client, task_queue)` helper from RESEARCH §Pattern 4 — try `client.create_schedule(schedule_id="spike-d-test", schedule=Schedule(...))`; on `RPCError` containing "already exists" (case-insensitive), call `client.get_schedule_handle("spike-d-test").update(lambda inp: schedule)`. Run the helper TWICE in sequence in the same script: first call creates, second call updates without raising. Print `PASS spike-d`. Cleanup: call `client.get_schedule_handle("spike-d-test").delete()` at end.

**File 2 — `spike_g_lazy_customer_create.py`:** Postgres testcontainer + asyncpg pool. Create minimal `users(id uuid pk, email text, stripe_customer_id text)`. Seed one user with `stripe_customer_id IS NULL`. Spawn 2 concurrent asyncio tasks each calling a helper:

```python
async def lazy_create(pool, user_id, fake_stripe_create):
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT email, stripe_customer_id FROM users WHERE id = $1 FOR UPDATE",
                user_id,
            )
            if row["stripe_customer_id"] is None:
                cid = fake_stripe_create(email=row["email"])  # mock counter
                await conn.execute("UPDATE users SET stripe_customer_id = $1 WHERE id = $2", cid, user_id)
                return cid
            return row["stripe_customer_id"]
```

`fake_stripe_create` is a counter-incrementing function that records every invocation. Assert: after both tasks finish, the counter incremented EXACTLY ONCE (not twice). Both tasks return the same customer_id. Without `FOR UPDATE`, the test would record 2 calls. Print `PASS spike-g`.

**File 3 — `draft_014_migration.py`:** Draft of the actual Wave 1 migration, kept in `_spikes/` so it can be exercised end-to-end without polluting `alembic/versions/`. Mirror `013_phase29_proxy_columns.py` shape:

```python
revision = "014_phase_b_credit_ledger_and_tier"
down_revision = "013_phase29_proxy_columns"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("users", sa.Column("tier", sa.Text(), nullable=False, server_default=sa.text("'free'")))
    op.create_check_constraint("ck_users_tier", "users", "tier IN ('free','pro','ultra')")
    op.add_column("users", sa.Column("stripe_customer_id", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("refund_writeoff_cents", sa.BigInteger(), nullable=False, server_default=sa.text("0")))

    op.create_table(
        "credit_balances",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("balance_cents", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("reference_id", sa.Text(), nullable=True),
        sa.Column("reference_type", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_check_constraint(
        "ck_credit_transactions_kind", "credit_transactions",
        "kind IN ('topup','debit','refund','tier_change','admin_writeoff')",
    )
    op.create_index(
        "uq_credit_transactions_reference",
        "credit_transactions", ["reference_id", "reference_type"],
        unique=True, postgresql_where=sa.text("reference_id IS NOT NULL"),
    )
    op.create_index("ix_credit_transactions_user_created", "credit_transactions",
                    ["user_id", sa.text("created_at DESC")])

    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("stripe_event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("stripe_event_id", name="uq_stripe_webhook_events_event_id"),
    )

    # D-08 — bump ap_multiplier 1.0 → 1.15.
    op.execute("UPDATE cost_weights SET ap_multiplier = 1.15 WHERE ap_multiplier = 1.0")

def downgrade() -> None:
    op.drop_table("stripe_webhook_events")
    op.drop_index("ix_credit_transactions_user_created", table_name="credit_transactions")
    op.drop_index("uq_credit_transactions_reference", table_name="credit_transactions")
    op.drop_constraint("ck_credit_transactions_kind", "credit_transactions", type_="check")
    op.drop_table("credit_transactions")
    op.drop_table("credit_balances")
    op.drop_column("users", "refund_writeoff_cents")
    op.drop_column("users", "stripe_customer_id")
    op.drop_constraint("ck_users_tier", "users", type_="check")
    op.drop_column("users", "tier")
    op.execute("UPDATE cost_weights SET ap_multiplier = 1.0 WHERE ap_multiplier = 1.15")
```

**File 4 — `spike_h_migration_roundtrip.py`:** Postgres testcontainer. Use the testcontainer's connection URL to run `alembic upgrade head` against the existing `alembic/versions/` PLUS the draft migration above (copy `draft_014_migration.py` into a temp `versions/` dir or use Alembic's `version_locations` config). Round-trip: upgrade head → assert all schema shapes (users.tier=text default 'free' with CHECK, credit_balances/credit_transactions/stripe_webhook_events tables, UNIQUE indexes, ap_multiplier rows updated to 1.15) → downgrade -1 → assert removed → upgrade head → assert idempotent. Print `PASS spike-h`.
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; uv run python tests/_spikes/spike_d_temporal_schedule.py &amp;&amp; uv run python tests/_spikes/spike_g_lazy_customer_create.py &amp;&amp; uv run python tests/_spikes/spike_h_migration_roundtrip.py</automated>
  </verify>
  <done>
- All three spike scripts print PASS markers.
- spike_d proves register_schedules helper is idempotent across two boots.
- spike_g proves SELECT FOR UPDATE serializes concurrent first-clicks.
- spike_h proves migration round-trip is idempotent and produces every required schema shape.
- `draft_014_migration.py` exists in `_spikes/` (NOT yet in `alembic/versions/` — that's Wave 1).
  </done>
</task>

<task type="auto">
  <name>Task 3: Spike E + F — mobile InAppWebView interception, Stripe CLI deploy-stack delivery</name>
  <files>mobile/integration_test/spike_e_inappwebview_intercept.dart, mobile/pubspec.yaml, api_server/tests/_spikes/spike_f_stripe_cli_deploy_stack.md</files>
  <read_first>
    - .planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md (§Example D, AMD-03, Pitfall 7, Open Question #2)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"checkout_webview_screen.dart")
    - CLAUDE.md (macOS deploy-stack rule, OAuth env-var requirements — flutter_inappwebview must coexist with flutter_appauth)
    - mobile/pubspec.yaml (current deps; verify flutter_inappwebview NOT yet present, confirm flutter_appauth IS present)
  </read_first>
  <action>
**File 1 — `mobile/pubspec.yaml`:** Add `flutter_inappwebview: ^6.1.5` under `dependencies:` (verify `^6.1.5` is the latest at execution time via `curl -s https://pub.dev/api/packages/flutter_inappwebview | python3 -c "import sys,json; print(json.load(sys.stdin)['latest']['version'])"` — if newer, use that within v6 major). Run `cd mobile && flutter pub get`.

**File 2 — `mobile/integration_test/spike_e_inappwebview_intercept.dart`:** Integration test that mounts an `InAppWebView` widget loading `https://app.solvrlabs.com/billing/return-success?session_id=cs_spike_dummy` (a fake URL — DO NOT need real Stripe response). The webview's `shouldOverrideUrlLoading` callback inspects the navigation request, asserts the path == `/billing/return-success` AND the query parameter `session_id == 'cs_spike_dummy'`, returns `NavigationActionPolicy.CANCEL`, then sets a Completer. Test waits for the Completer (timeout 10s). On success, print `PASS spike-e`.

This proves the API surface flutter_inappwebview gives us is exactly what AMD-03 / RESEARCH §Example D promises. Test runs via `flutter test integration_test/spike_e_inappwebview_intercept.dart` (no real device required — uses the headless integration test driver).

**File 3 — `spike_f_stripe_cli_deploy_stack.md`:** Markdown evidence file with the exact commands the executor ran AND the resulting log lines from `docker compose -f deploy/docker-compose.prod.yml logs api_server`. Document one specific scenario:

1. Start deploy stack: `docker compose -f deploy/docker-compose.prod.yml up -d` (or confirm already running).
2. In a separate terminal: `stripe listen --forward-to http://localhost:8000/v1/billing/webhook --skip-verify` (skip-verify because the route doesn't exist yet — we just need to see the request hit the container).
3. In a third terminal: `stripe trigger checkout.session.completed --skip-verify` (no actual Stripe Customer needed — this is fixture-only).
4. Confirm in the deploy api_server logs that the request reached the container (will 404 because the route doesn't exist — that's the SUCCESS condition for spike-f; we just want proof it routed to the deploy container, NOT a hypothetical native uvicorn).
5. Document the 404 log line in the markdown file as PASS evidence.

**This spike is the most critical — it proves the CLAUDE.md macOS rule holds for the webhook contract.** If for any reason the request lands somewhere else (a side-launched uvicorn, the wrong container), executor STOPS and surfaces a `checkpoint:human-action` because Wave 3+ webhook work depends on this routing.
  </action>
  <verify>
    <automated>cd mobile &amp;&amp; flutter test integration_test/spike_e_inappwebview_intercept.dart &amp;&amp; test -f api_server/tests/_spikes/spike_f_stripe_cli_deploy_stack.md &amp;&amp; grep -q PASS api_server/tests/_spikes/spike_f_stripe_cli_deploy_stack.md</automated>
  </verify>
  <done>
- mobile/pubspec.yaml has `flutter_inappwebview` pinned in v6 major.
- spike_e Flutter integration test passes (`PASS spike-e` in stdout).
- spike_f markdown file exists with evidence (curl/log output) and contains a `PASS` marker.
- `flutter pub get` produces no version conflicts with flutter_appauth (Assumption A7 confirmed).
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4: Wave 0 sign-off — write evidence summary and gate Wave 1</name>
  <what-built>
- 8 spike artifacts: signature round-trip, debit activity contract, atomic ledger, Temporal schedule idempotency, mobile webview interception, Stripe CLI deploy-stack delivery, lazy customer create race-defense, migration round-trip.
- A draft of migration 014 in `_spikes/draft_014_migration.py` ready to copy into `alembic/versions/` in Wave 1.
- `flutter_inappwebview` pinned in `mobile/pubspec.yaml`.
- `stripe>=15.0,<16.0` pinned in `api_server/pyproject.toml`.
  </what-built>
  <how-to-verify>
1. Read `api_server/tests/_spikes/wave0_stripe_paywall.md` (the executor wrote this as the final action of Wave 0). It MUST list each of the 8 spikes with: spike id, file path, command run, output excerpt with PASS marker, brief one-line "what this proved".
2. Run all spikes once more end-to-end:
   ```
   cd api_server && for s in tests/_spikes/spike_a_*.py tests/_spikes/spike_b_*.py tests/_spikes/spike_c_*.py tests/_spikes/spike_d_*.py tests/_spikes/spike_g_*.py tests/_spikes/spike_h_*.py; do echo "=== $s ==="; uv run python "$s"; done
   cd ../mobile && flutter test integration_test/spike_e_inappwebview_intercept.dart
   ```
3. Confirm `cat api_server/tests/_spikes/spike_f_stripe_cli_deploy_stack.md` shows the exact command sequence and a PASS marker referencing the deploy stack container ID.
4. Confirm `git diff HEAD -- api_server/alembic/versions/` shows NO changes (the draft migration lives in `_spikes/` only — Wave 1 will copy it).
5. Approve to release Wave 1, OR reject with specific spike that needs deeper investigation.
  </how-to-verify>
  <resume-signal>Type "approved" to release Wave 1, or describe which spike needs revisit (Wave 0 is BLOCKING — Wave 1+ executors are forbidden from starting until this gate passes).</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Stripe → api_server (webhook POST) | untrusted external POST to a public route; Stripe-Signature header is the only auth |
| Mobile → api_server (HTTPS) | authenticated via session cookie; existing boundary |
| api_server → Stripe API (outbound) | secret API key MUST stay server-side; never logged or returned to client |
| Mobile InAppWebView → Stripe-hosted Checkout | external HTTPS; no AP secrets cross this boundary; navigation-delegate intercepts redirect |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-W1 | Spoofing | spike_a_webhook_signature.py + production billing_webhook.py | mitigate | StripeClient.construct_event verifies HMAC-SHA256 in constant time + 5-min timestamp tolerance; spike-a proves both happy path and SignatureVerificationError on tamper/stale |
| T-B-LR | Tampering | spike_g_lazy_customer_create.py + production stripe_client.py | mitigate | SELECT ... FOR UPDATE serializes concurrent first-click requests; spike-g proves single Stripe Customer create under race |
| T-B-IDP | Tampering | spike_b_debit_activity_contract.py | mitigate | UNIQUE(reference_id, reference_type) raises asyncpg.UniqueViolationError; activity catches and returns the originally-debited amount; spike-b proves idempotency on Temporal retry |
| T-B-MIG | DoS | spike_h_migration_roundtrip.py | mitigate | Migration round-trip (up/down/up) prevents shipping a one-way migration that can't be reverted in production |
| T-B-SCH | DoS | spike_d_temporal_schedule.py | mitigate | Idempotent register_schedules prevents worker boot crash-loop on schedule re-creation (Pitfall 8) |
| T-B-DBL | Tampering | (Wave 3 design — surfaced here for awareness) | mitigate | Listening to checkout.session.completed only (AMD-05); spike-a documents the matrix; double-credit risk eliminated by event selection + UNIQUE on stripe_event_id |
</threat_model>

<verification>
- All 4 tasks complete with PASS markers in their respective spike artifacts.
- `wave0_stripe_paywall.md` summary exists with all 8 spikes documented.
- Human sign-off recorded in PR / commit message.
- No code lands in `alembic/versions/`, no production routes, no production widgets — Wave 0 is evidence-only (plus dep pins which are byte-additive).
</verification>

<success_criteria>
- 8 PASS markers across the 8 spike scripts.
- Migration draft exists in `_spikes/` (NOT in `alembic/versions/`).
- Stripe SDK 15.x importable; flutter_inappwebview ^6.x installable; flutter_appauth still works.
- Deploy stack delivers Stripe-CLI-forwarded webhooks to the deploy api_server container, confirmed by log inspection.
- Human sign-off task #4 explicitly approved or specific blocker raised.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-01-SUMMARY.md` summarizing each spike, the evidence captured, and any deviations from RESEARCH.md predictions.
</output>
