---
phase: B-stripe
plan: 13
type: execute
wave: 6
depends_on: [B-stripe-05, B-stripe-06, B-stripe-07, B-stripe-08, B-stripe-09, B-stripe-11, B-stripe-12]
files_modified:
  - docker-compose.dev.yml
  - api_server/Makefile
  - Makefile
  - api_server/pyproject.toml
  - api_server/tests/e2e/test_phase_b_money_path.py
  - .github/workflows/e2e-phase-b.yml
  - deploy/.env.prod.example
  - .env.example
  - .planning/phases/B-stripe-paywall/B-HUMAN-UAT.md
  - .planning/PHASE-B-EXIT-GATE-PASSED
autonomous: false
gap_closure: false
requirements_addressed:
  - D-10 (Stripe TEST keys + dashboard config out-of-band — documented in B-HUMAN-UAT.md)
  - D-19 (Phase B starts now; live webhook delivery deferred to H7)
  - D-22 (CI runs against real Stripe TEST mode)
  - D-25 (PHASE-B-EXIT-GATE-PASSED requires automated CI + manual UAT)
  - BIL-01..BIL-06 (Stripe billing requirements — exit gate covers all)
must_haves:
  truths:
    - "make e2e-phase-b-stripe runs the full Free → Ultra → message → debit → drained → 402 flow against real Stripe TEST mode"
    - "stripe-mock service is in docker-compose.dev.yml on port 12111 for unit tests"
    - "GH workflow .github/workflows/e2e-phase-b.yml runs e2e-phase-b-stripe on PRs touching api_server/ or mobile/"
    - "B-HUMAN-UAT.md documents the manual flow against real Stripe TEST card 4242..."
    - ".planning/PHASE-B-EXIT-GATE-PASSED marker exists with timestamp + automated coverage status + 'manual UAT pending' or 'manual UAT complete'"
    - "pytest marker 'phase_b_e2e' is registered so default test suite excludes real-Stripe runs"
    - ".env.example + deploy/.env.prod.example document the 9 new AP_STRIPE_* env vars"
  artifacts:
    - path: ".planning/PHASE-B-EXIT-GATE-PASSED"
      provides: "Phase B exit marker"
      contains: "PHASE-B-EXIT-GATE-PASSED"
    - path: ".planning/phases/B-stripe-paywall/B-HUMAN-UAT.md"
      provides: "Manual UAT script with TEST card numbers + 4 verification scenarios"
      contains: "4242 4242 4242 4242"
    - path: ".github/workflows/e2e-phase-b.yml"
      provides: "GH workflow runs e2e-phase-b-stripe against secrets.AP_STRIPE_TEST_API_KEY"
      contains: "e2e-phase-b-stripe"
    - path: "api_server/tests/e2e/test_phase_b_money_path.py"
      provides: "Free → Ultra → debit → 402 e2e test"
      contains: "phase_b_e2e"
  key_links:
    - from: ".github/workflows/e2e-phase-b.yml"
      to: "api_server/Makefile e2e-phase-b-stripe target"
      via: "GH workflow run step"
      pattern: "make e2e-phase-b-stripe"
    - from: "api_server/Makefile"
      to: "api_server/tests/e2e/test_phase_b_money_path.py"
      via: "pytest -m phase_b_e2e"
      pattern: "phase_b_e2e"
---

<objective>
Phase B exit gate. Mirrors Phase 31's split-gate shape (automated CI + manual UAT). Adds the docker-compose stripe-mock service for unit tests, the Makefile target + pytest marker for the real-Stripe e2e gate, the GH workflow, the manual UAT document, and the exit-gate marker.

Purpose: D-25 requires both automated and manual gates. This plan lands both AND the marker file that signals Phase B has shipped.
Output: dev compose service, Makefile target, GH workflow, e2e test, B-HUMAN-UAT.md, env doc, PHASE-B-EXIT-GATE-PASSED marker.
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
@.planning/phases/B-stripe-paywall/B-stripe-08-SUMMARY.md
@.planning/phases/B-stripe-paywall/B-stripe-09-SUMMARY.md
@.planning/phases/B-stripe-paywall/B-stripe-11-SUMMARY.md
@.github/workflows/e2e-money-path.yml
@docker-compose.dev.yml
@api_server/Makefile
@Makefile
@.planning/phases/31-pre-stripe-billing-hardening/31-HUMAN-UAT.md
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: docker-compose stripe-mock + Makefile target + pytest marker + e2e test</name>
  <files>docker-compose.dev.yml, api_server/Makefile, Makefile, api_server/pyproject.toml, api_server/tests/e2e/test_phase_b_money_path.py</files>
  <read_first>
    - docker-compose.dev.yml (existing services + format)
    - api_server/Makefile:45-78 (dockerized e2e harness pattern)
    - Makefile:236-238 (top-level money-path target shape)
    - api_server/pyproject.toml `[tool.pytest.ini_options]` markers
    - api_server/tests/e2e/ (existing e2e tests if any; Phase 31 H8 patterns)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_phase_b_money_path_full_flow (marked phase_b_e2e):
      - Seed a free user.
      - POST /v1/billing/checkout {pack_id: "pack_5"} → expect checkout_url.
      - Drive Stripe API directly (using the test API key) to "pay" the session — use Stripe TEST card "tok_visa" or paid-by-default test mode.
      - Wait/poll for the webhook (or trigger via stripe CLI in CI; trigger via direct API call in test).
      - Assert: user.tier='ultra', credit_balances.balance_cents=500, credit_transactions has topup row.
      - Send 5 chat messages (the AP cost-per-call should be sub-cent; we want fewer than 500 calls).
      - For test efficiency: monkeypatch the upstream LLM mock to return cost_usd=1.20 (12000 cents) for one message, draining the balance. Assert balance is now <=0.
      - Send the 6th chat message → expect 402 INSUFFICIENT_BALANCE.
  </behavior>
  <action>
**File 1 — `docker-compose.dev.yml`:** Add the stripe-mock service. Mirror existing service block format (e.g. `redis`):

```yaml
  stripe-mock:
    image: stripe/stripe-mock:latest
    container_name: agent-playground-stripe-mock
    ports:
      - "12111:12111"   # http
      - "12112:12112"   # https
    restart: unless-stopped
```

Note: dev-only. Not added to `deploy/docker-compose.prod.yml` — production hits real Stripe.

**File 2 — `api_server/Makefile`:** Add target. Mirror `Makefile:236-238` (top-level money-path) since Phase B uses real Stripe TEST mode:

```makefile
e2e-phase-b-stripe:  ## Phase B integration: real Stripe TEST mode
	@test -n "$$AP_STRIPE_TEST_API_KEY" || (echo "ERROR: AP_STRIPE_TEST_API_KEY not set" && exit 1)
	@test -n "$$AP_STRIPE_TEST_WEBHOOK_SECRET" || (echo "ERROR: AP_STRIPE_TEST_WEBHOOK_SECRET not set" && exit 1)
	cd api_server && uv run pytest tests/e2e/test_phase_b_money_path.py -m phase_b_e2e -v --tb=short
```

**File 3 — `Makefile` (top-level):** Add a phony target alias if the project convention has top-level e2e shortcuts:

```makefile
.PHONY: e2e-phase-b-stripe
e2e-phase-b-stripe:
	$(MAKE) -C api_server e2e-phase-b-stripe
```

**File 4 — `api_server/pyproject.toml`:** Register the marker. Find `[tool.pytest.ini_options]` markers list and add:

```toml
markers = [
    # ...existing...
    "phase_b_e2e: real Stripe TEST mode end-to-end tests (requires AP_STRIPE_TEST_API_KEY + AP_STRIPE_TEST_WEBHOOK_SECRET; serializes via concurrency)",
]
```

**File 5 — `api_server/tests/e2e/test_phase_b_money_path.py`:** Phase B equivalent of `tests/e2e/test_money_path.py` (Phase 31 H8). Use Postgres testcontainer + a real Stripe API call.

```python
import os
import uuid
import pytest
import stripe

pytestmark = [pytest.mark.phase_b_e2e]

@pytest.fixture(scope="session")
def real_stripe_client():
    api_key = os.environ.get("AP_STRIPE_TEST_API_KEY")
    if not api_key:
        pytest.fail("AP_STRIPE_TEST_API_KEY required for phase_b_e2e tests")
    return stripe.StripeClient(api_key)


async def test_phase_b_money_path_full_flow(async_client, db_pool, real_stripe_client):
    """Free → Ultra → message → debit → drained → 402."""
    # 1. Seed a fresh free user.
    user_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, email, tier) VALUES ($1, $2, 'free')",
            user_id, f"phase-b-e2e-{user_id}@example.com",
        )
    # 2. Authenticate (use the test fixture for session cookie).
    cookie = ...test session cookie helper...

    # 3. Hit POST /v1/billing/checkout with pack_5.
    r = await async_client.post(
        "/v1/billing/checkout",
        json={"pack_id": "pack_5"},
        headers={"Cookie": f"ap_session={cookie}"},
    )
    assert r.status_code == 200
    checkout_url = r.json()["checkout_url"]
    assert checkout_url.startswith("https://checkout.stripe.com/")

    # 4. Drive Stripe API to mark the session paid (TEST mode allows this directly).
    # Strategy: extract session_id from URL, then either:
    #   (a) Use stripe.checkout.sessions.expire then re-create with status='complete', OR
    #   (b) Use stripe.checkout.sessions.modify to mark paid, OR
    #   (c) Use the real_stripe_client.test_helpers if available
    # Simpler: use Stripe CLI `trigger checkout.session.completed --override session.metadata.ap_user_id=<uid>`
    # invoked via subprocess.
    import subprocess
    subprocess.run([
        "stripe", "trigger", "checkout.session.completed",
        "--override", f"checkout_session:metadata.ap_user_id={user_id}",
        "--override", "checkout_session:metadata.pack_id=pack_5",
        "--override", "checkout_session:metadata.credit_cents=500",
    ], check=True, env={**os.environ, "STRIPE_API_KEY": real_stripe_client.api_key})

    # 5. Wait for webhook to land (Stripe CLI listen + our route).
    # Poll DB for the topup row.
    import asyncio
    for _ in range(30):
        await asyncio.sleep(1)
        async with db_pool.acquire() as conn:
            tier = await conn.fetchval("SELECT tier FROM users WHERE id = $1", user_id)
            balance = await conn.fetchval(
                "SELECT balance_cents FROM credit_balances WHERE user_id = $1", user_id,
            )
        if tier == "ultra" and balance == 500:
            break
    else:
        pytest.fail(f"Webhook didn't land within 30s — tier={tier}, balance={balance}")

    # 6. Now the user is ultra with $5.00. Send 5 chat messages with synthetic upstream that
    #    returns very small cost_usd (~$0.01 each) — total ~$0.05 used.
    # Then send a 6th message with mock cost_usd=$5.00 → drains balance.
    # Send 7th message → 402.
    # ... (test scaffolding using existing chat-test fixtures + respx mocking llm upstream)

    # Cleanup: delete test user + Stripe Customer.
    customer_id = await db_pool.acquire().fetchval(
        "SELECT stripe_customer_id FROM users WHERE id = $1", user_id,
    )
    if customer_id:
        real_stripe_client.customers.delete(customer_id)
```

**Note on practical execution:** This test requires a working `stripe listen` running locally OR in CI (forwarding events to the test's HTTP target). The CI workflow handles this in the next task. For local execution, the executor verifies steps 1-5 work; the chat-drain steps 6-7 may need to be split out into a sibling test that uses the existing chat fixtures.

For TDD discipline: write the test in the structure above; if step 6 + 7 are too entangled with existing chat infra, factor them into a smaller `test_drain_to_402` that uses respx mocks on the llm proxy.
  </action>
  <verify>
    <automated>cd api_server &amp;&amp; AP_STRIPE_TEST_API_KEY=$AP_STRIPE_TEST_API_KEY AP_STRIPE_TEST_WEBHOOK_SECRET=$AP_STRIPE_TEST_WEBHOOK_SECRET make e2e-phase-b-stripe</automated>
  </verify>
  <done>
- e2e test passes with real Stripe TEST keys + Stripe CLI listen forwarding.
- `grep -c 'stripe-mock' docker-compose.dev.yml` ≥ 1.
- `grep -c 'phase_b_e2e' api_server/pyproject.toml` ≥ 1.
- `make e2e-phase-b-stripe` exits 0 with the env vars + a running Stripe CLI listener.
  </done>
</task>

<task type="auto">
  <name>Task 2: GH workflow + env documentation + B-HUMAN-UAT.md</name>
  <files>.github/workflows/e2e-phase-b.yml, deploy/.env.prod.example, .env.example, .planning/phases/B-stripe-paywall/B-HUMAN-UAT.md</files>
  <read_first>
    - .github/workflows/e2e-money-path.yml (FULL — concurrency block, env-via-secrets, postgres+redis boot, alembic migrate, pattern)
    - .planning/phases/31-pre-stripe-billing-hardening/31-HUMAN-UAT.md (FULL — manual UAT shape; Phase B mirrors it)
    - existing .env.example or deploy/.env.prod (find the AP_OAUTH_* block as the analog for naming/comment style)
  </read_first>
  <action>
**File 1 — `.github/workflows/e2e-phase-b.yml`:** Mirror `.github/workflows/e2e-money-path.yml`:

```yaml
name: e2e-phase-b

on:
  pull_request:
    paths:
      - 'api_server/**'
      - 'mobile/**'
      - '.github/workflows/e2e-phase-b.yml'
      - 'docker-compose.dev.yml'
      - 'Makefile'
  workflow_dispatch:

concurrency:
  group: e2e-phase-b-stripe-${{ github.ref }}
  cancel-in-progress: false   # real-money runs serialize

jobs:
  e2e-phase-b:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      AP_STRIPE_TEST_API_KEY: ${{ secrets.AP_STRIPE_TEST_API_KEY }}
      AP_STRIPE_TEST_WEBHOOK_SECRET: ${{ secrets.AP_STRIPE_TEST_WEBHOOK_SECRET }}
      AP_STRIPE_API_KEY: ${{ secrets.AP_STRIPE_TEST_API_KEY }}
      AP_STRIPE_WEBHOOK_SECRET: ${{ secrets.AP_STRIPE_TEST_WEBHOOK_SECRET }}
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: agent_playground_api
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready --health-interval 5s --health-timeout 3s --health-retries 12
      redis:
        image: redis:7
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v4
      - name: Skip if secrets unavailable
        if: env.AP_STRIPE_TEST_API_KEY == ''
        run: |
          echo "AP_STRIPE_TEST_API_KEY not set — Phase B e2e gate skipped."
          exit 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install Stripe CLI
        run: |
          curl -L https://github.com/stripe/stripe-cli/releases/latest/download/stripe_linux_x86_64.tar.gz | tar xz
          sudo mv stripe /usr/local/bin/stripe
          stripe --version
      - name: Install api_server deps
        run: |
          pip install uv
          cd api_server && uv sync --frozen
      - name: Create test database (idempotent)
        run: |
          PGPASSWORD=postgres psql -h localhost -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='agent_playground_api'" | grep -q 1 || \
          PGPASSWORD=postgres psql -h localhost -U postgres -c "CREATE DATABASE agent_playground_api"
      - name: Run migrations
        run: cd api_server && uv run alembic upgrade head
      - name: Start Stripe CLI listener (background)
        run: |
          stripe listen --forward-to http://localhost:8000/v1/billing/webhook --skip-verify > stripe-listen.log 2>&1 &
          sleep 5
      - name: Boot api_server (background)
        run: |
          cd api_server && uv run uvicorn api_server.main:app --host 0.0.0.0 --port 8000 > api-server.log 2>&1 &
          sleep 5
      - name: Run e2e gate
        run: make e2e-phase-b-stripe
      - name: Logs on failure
        if: failure()
        run: |
          echo "=== api_server log ==="
          cat api-server.log || true
          echo "=== stripe listen log ==="
          cat stripe-listen.log || true
```

**File 2 — `deploy/.env.prod.example`:** If file exists, append. Else create:

```
# ---------- Phase B (Stripe Paywall) ----------
# Required in prod; placeholders OK in dev (api_server emits a warning log).
# Get TEST keys from https://dashboard.stripe.com/test/apikeys
# LIVE keys from https://dashboard.stripe.com/apikeys (DO NOT commit; load via secrets)
AP_STRIPE_API_KEY=sk_test_REPLACE_ME
AP_STRIPE_WEBHOOK_SECRET=whsec_REPLACE_ME

# Pro monthly subscription price (created in Stripe Dashboard → Products)
AP_STRIPE_PRICE_ID_PRO_MONTHLY=price_REPLACE_ME

# 5 credit packs — create one Product + Price per pack in Stripe Dashboard.
AP_STRIPE_PRICE_ID_PACK_5=price_REPLACE_ME
AP_STRIPE_PRICE_ID_PACK_10=price_REPLACE_ME
AP_STRIPE_PRICE_ID_PACK_25=price_REPLACE_ME
AP_STRIPE_PRICE_ID_PACK_50=price_REPLACE_ME
AP_STRIPE_PRICE_ID_PACK_100=price_REPLACE_ME
```

**File 3 — `.env.example`:** Same content as above; this is the dev-side template.

**File 4 — `.planning/phases/B-stripe-paywall/B-HUMAN-UAT.md`:** Manual UAT script. Mirror `.planning/phases/31-pre-stripe-billing-hardening/31-HUMAN-UAT.md`:

```markdown
# Phase B — HUMAN-UAT

> Manual gate per D-25. Run AFTER all automated tests are green and BEFORE flipping `.planning/PHASE-B-EXIT-GATE-PASSED` to "fully verified".

**Prerequisites:**

- [ ] Stripe TEST mode keys in `deploy/.env.prod` (or `.env`):
  - AP_STRIPE_API_KEY=sk_test_...
  - AP_STRIPE_WEBHOOK_SECRET=whsec_...  ← from `stripe listen` output
- [ ] 6 Stripe Products + Prices created in TEST mode dashboard:
  - 1× Pro Monthly subscription (recurring)
  - 5× one-time credit packs ($5, $10, $25, $50, $100)
  - All 6 price IDs are pasted into the env file
- [ ] Stripe CLI installed on host: `which stripe` returns a path
- [ ] `stripe login` completed
- [ ] Deploy stack running: `docker compose -f deploy/docker-compose.prod.yml ps` shows api_server + temporal-worker + postgres + temporal up
- [ ] Mobile app installed on iOS/Android device or simulator + pointed at `http://localhost:8000` via `--dart-define BASE_URL=http://localhost:8000`

## UAT-1 — Free → Ultra via credit pack ($5)

1. [ ] Sign up a fresh user (e.g. `phase-b-uat-1@yourdomain.com`) via Google/GitHub OAuth.
2. [ ] Confirm tier is 'free' in DB: `psql -c "SELECT tier FROM users WHERE email='phase-b-uat-1@yourdomain.com'"`
3. [ ] In a terminal: `stripe listen --forward-to http://localhost:8000/v1/billing/webhook` — record the printed `whsec_...` value into `deploy/.env.prod` as AP_STRIPE_WEBHOOK_SECRET if not already there.
4. [ ] Restart deploy api_server: `docker compose -f deploy/docker-compose.prod.yml restart api_server`.
5. [ ] In the mobile app, navigate to `/billing/topup`.
6. [ ] Tap the "$5" pack.
7. [ ] In the in-app webview, enter Stripe TEST card: `4242 4242 4242 4242`, expiry any future date, CVC any 3 digits, postal code any 5 digits.
8. [ ] Submit payment.
9. [ ] EXPECT: webview pops automatically; "Confirming top-up…" with mm:ss timer appears; within 5-15s a SnackBar shows "Top-up confirmed!".
10. [ ] Confirm tier flipped to 'ultra' in DB: `psql -c "SELECT tier, b.balance_cents FROM users u LEFT JOIN credit_balances b ON b.user_id=u.id WHERE email='phase-b-uat-1@yourdomain.com'"`. Expect tier='ultra' and balance_cents=500.

PASS / FAIL: ____________________

## UAT-2 — Send chat → debit → 402

1. [ ] With the same UAT-1 user (now ultra, $5 balance), open chat to any agent.
2. [ ] Send a message; observe the response. Confirm a `usage_logs` row was created and a `credit_transactions` debit row exists in DB.
3. [ ] Send chat messages until balance < 1¢ (or, in dev, manually drain via a debit fixture if message costs are too small).
4. [ ] Send the next message → EXPECT a blocking modal "Out of credits" with "Top up" / "Later" CTAs.
5. [ ] Tap "Top up" → EXPECT routing to `/billing/topup`.

PASS / FAIL: ____________________

## UAT-3 — Promo code applied to Checkout

1. [ ] In Stripe TEST dashboard, mint a 50%-off-once promo code (Coupons → New).
2. [ ] In the mobile app, hit `/billing/topup`, tap a pack.
3. [ ] In the Stripe Checkout webview, click "Have a promo code?" and enter the code.
4. [ ] EXPECT: the displayed total is halved.
5. [ ] Submit (with TEST card). Confirm webhook fires + DB shows `credit_transactions` row with the FULL pack credit_cents (D-07 invariant — promo applies to the line item amount but the user still gets the same credit count per the locked-decision; verify against the real Stripe payload — Open Q #7 in RESEARCH).

PASS / FAIL: ____________________

## UAT-4 — Pro upgrade + cancel grace period + downgrade

1. [ ] Sign up a new user `phase-b-uat-4@yourdomain.com`.
2. [ ] Tap a "Subscribe to Pro" CTA (location: TBD — TopUpScreen could include this; if not yet, hit POST /v1/billing/subscription via curl with the session cookie).
3. [ ] In Stripe Checkout, enter TEST card, submit.
4. [ ] EXPECT tier flip to 'pro' (DB confirm).
5. [ ] In Stripe TEST dashboard, cancel the subscription (set cancel_at_period_end=true).
6. [ ] Confirm the user's tier remains 'pro' until the period_end (DB column `subscription_cancel_at_period_end=true`, `subscription_current_period_end` set).
7. [ ] In Stripe TEST dashboard, force-end the period (or use `stripe trigger customer.subscription.deleted`).
8. [ ] EXPECT tier flips to 'free' AND 4 oldest agents (if user has >1) auto-paused.

PASS / FAIL: ____________________

## Sign-off

- [ ] All 4 UAT scenarios PASS.
- [ ] Failures documented above with attached logs / screenshots.
- [ ] User: ___________________ Date: ___________________
- [ ] After sign-off, append the timestamp + outcome to `.planning/PHASE-B-EXIT-GATE-PASSED` and commit.
```

**File 5 — `.planning/PHASE-B-EXIT-GATE-PASSED`:**

```
PHASE-B-EXIT-GATE-PASSED
========================

**Automated coverage:** PASSED <YYYY-MM-DD HH:MM TZ>
- make e2e-phase-b-stripe — GREEN
- make e2e-money-path (Phase 31 H8 regression) — GREEN
- All 7 webhook event types covered by signed-fixture integration tests
- All 13 plans across 7 waves shipped (B-stripe-01 through B-stripe-13)

**Manual UAT:** [PENDING|COMPLETE — see B-HUMAN-UAT.md]
- UAT-1 (Free → Ultra credit pack): _____
- UAT-2 (chat drain → 402): _____
- UAT-3 (promo code): _____
- UAT-4 (Pro cancel grace + downgrade): _____

**Wave 0 evidence:** B-stripe-01-SUMMARY.md (8 spikes PASS)

**Locked decisions implemented:** D-01 through D-26 + AMD-01 through AMD-05.

**Tagged commit:** TBD (git tag phase-b-shipped after manual UAT signs off)
```

The marker file's exact wording can be filled in by the executor based on actual outcomes; the template above is the shape.
  </action>
  <verify>
    <automated>cd /Users/fcavalcanti/dev/agent-playground &amp;&amp; test -f .github/workflows/e2e-phase-b.yml &amp;&amp; test -f .planning/phases/B-stripe-paywall/B-HUMAN-UAT.md &amp;&amp; test -f .planning/PHASE-B-EXIT-GATE-PASSED &amp;&amp; grep -c 'PHASE-B-EXIT-GATE-PASSED' .planning/PHASE-B-EXIT-GATE-PASSED</automated>
  </verify>
  <done>
- `.github/workflows/e2e-phase-b.yml` exists and references `make e2e-phase-b-stripe`.
- `.env.example` + `deploy/.env.prod.example` document the 9 new AP_STRIPE_* vars.
- `.planning/phases/B-stripe-paywall/B-HUMAN-UAT.md` exists with all 4 UAT scenarios + signed prerequisites.
- `.planning/PHASE-B-EXIT-GATE-PASSED` exists with the marker template.
- `grep -c 'AP_STRIPE_TEST_API_KEY' .github/workflows/e2e-phase-b.yml` ≥ 1.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Phase B exit gate sign-off</name>
  <what-built>
- 13 plans across 7 waves SHIPPED (Wave 0 spikes through Wave 6 exit gate).
- Migration 014 + 6 services + 2 routes + 1 webhook + 3 Temporal workflows.
- Mobile billing module (6 widgets + 3 Riverpod providers + DTOs + API client).
- Pre-flight 402 in llm_proxy.
- e2e gate: `make e2e-phase-b-stripe` GREEN against real Stripe TEST mode.
- Manual UAT script in B-HUMAN-UAT.md.
- Phase 31 H8 regression: `make e2e-money-path` still GREEN.
  </what-built>
  <how-to-verify>
1. Confirm all automated CI gates GREEN by inspecting the latest GH Actions run.
2. Walk through `B-HUMAN-UAT.md` with real Stripe TEST credentials (4 scenarios).
3. Append the manual UAT outcomes to `.planning/PHASE-B-EXIT-GATE-PASSED`.
4. After all 4 UAT scenarios PASS, optionally tag the commit `git tag phase-b-shipped` (NEVER push — the user pushes tags manually per global instructions).
5. Note any remaining pending items (e.g. live webhook delivery awaits H7) in PHASE-B-EXIT-GATE-PASSED.
6. Approve the gate or describe specific failures.
  </how-to-verify>
  <resume-signal>Type "approved — Phase B SHIPPED" or describe specific blockers.</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GH workflow → Stripe TEST API | uses repository secrets; never logged |
| `stripe listen` host process → deploy api_server container | localhost-only forwarding; matches CLAUDE.md macOS rule |
| Manual UAT card numbers | Stripe TEST card 4242... is published Stripe documentation; not a secret |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-CI-LK | InfoDisclosure | .github/workflows/e2e-phase-b.yml | mitigate | secrets used via env, not echo'd; api-server.log + stripe-listen.log are uploaded only on failure (not by default) and Phase 29 _redact_creds masks the keys before any log write |
| T-B-DEV-LK | InfoDisclosure | .env.example + deploy/.env.prod.example | mitigate | all values are `REPLACE_ME` placeholders; no real keys committed. .env files themselves remain gitignored (verify in .gitignore) |
| T-B-MARKER | Repudiation | PHASE-B-EXIT-GATE-PASSED | accept | marker file is human-edited at sign-off; git history shows the appender + timestamp; not a security boundary |
</threat_model>

<verification>
- All 13 Phase B plans implemented + tested.
- e2e gate passes against real Stripe TEST mode.
- Manual UAT documented with 4 scenarios.
- Exit gate marker file exists.
- Human sign-off recorded.
</verification>

<success_criteria>
- `cd api_server && AP_STRIPE_TEST_API_KEY=... AP_STRIPE_TEST_WEBHOOK_SECRET=... make e2e-phase-b-stripe` exits 0 (against real Stripe TEST mode + Stripe CLI forwarder).
- GH workflow runs to completion on a PR touching `api_server/`.
- All 4 UAT scenarios PASS.
- `.planning/PHASE-B-EXIT-GATE-PASSED` contains a timestamp + sign-off note.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-13-SUMMARY.md` listing the e2e gate result, the GH workflow run, the manual UAT outcomes, and any deferred items (e.g. live webhook delivery gated on H7).
</output>
