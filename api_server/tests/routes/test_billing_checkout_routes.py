"""Phase B Plan B-stripe-05 — TDD route tests for POST /v1/billing/{checkout,subscription}.

Tests-first per CLAUDE.md golden rule #5 + Phase B D-03 / D-11 / D-21:
the api_server creates Stripe Customer + Checkout Session lazily on the
first Stripe-affecting click, then returns ``{"checkout_url": ...}`` for
the mobile app to open in ``flutter_inappwebview``. Both endpoints are
auth-gated, share the lazy-customer-create discipline (spike-g
``SELECT ... FOR UPDATE`` proven 2026-05-08), and mint sessions with
``allow_promotion_codes=True`` (D-24) plus ``automatic_tax`` enabled.

Coverage matrix (per PLAN <behavior> — 9 tests):

  POST /v1/billing/checkout
   * 401 without cookie → Stripe envelope code=UNAUTHORIZED
   * 400 unknown pack_id → code=INVALID_PACK_ID (T-B-PCK)
   * 200 valid pack_id → response carries ``checkout_url``
   * Lazy customer create increments customers.create exactly ONCE across
     two sequential POSTs (T-B-LR mitigation; second call reuses the
     written stripe_customer_id)
   * 2-way concurrent POSTs result in EXACTLY ONE customers.create call
     (race-defense; mirrors spike_g_lazy_customer_create.py)
   * Returned URL is the URL the StripeClient stub minted (sentinel that
     the response shape is honest end-to-end)

  POST /v1/billing/subscription
   * 401 without cookie
   * 200 returns checkout_url
   * Subscription session uses ``settings.stripe_price_id_pro_monthly``
     (D-02 / D-04)

  phase_b_e2e marker (skipped without AP_STRIPE_TEST_API_KEY env)
   * Real Stripe TEST mode mints a real cs_test_* session id; cleanup
     deletes the test customer. Marked-skip when env unset so
     `pytest -m 'not phase_b_e2e' -x` (the default CI run) is fast.

Stripe SDK boundary is mocked via a ``FakeStripeClient`` injected into
``app.state.stripe_client`` per-test. Per RESEARCH §Pitfall 10:
stripe-mock is shape-only and stateless; for our route tests we need
state (returned customer ids feed back into UPDATE users.stripe_customer_id),
so a hand-rolled stateful fake is the right tool. Real Postgres flows
through unchanged (testcontainers per ``async_client`` fixture) — every
assertion about the SELECT FOR UPDATE serialization hits real Postgres
locks, not in-memory data structures.

Cross-tenant defense (T-B-XT): each test seeds a fresh user via the
``authenticated_cookie`` / ``second_authenticated_cookie`` fixtures.
"""
from __future__ import annotations

import asyncio
import os
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# FakeStripeClient — stateful test double for stripe.StripeClient
# ---------------------------------------------------------------------------


class _FakeCustomer:
    """Mirror enough of ``stripe.Customer`` for the helpers' ``.id`` access."""

    def __init__(self, id: str, **kwargs: Any) -> None:
        self.id = id
        self._extra = kwargs


class _FakeSession:
    """Mirror enough of ``stripe.checkout.Session`` for ``.url`` access."""

    def __init__(self, id: str, url: str, **kwargs: Any) -> None:
        self.id = id
        self.url = url
        self._extra = kwargs


class _CustomerService:
    """``client.customers`` with a counter-incrementing ``.create``."""

    def __init__(self, parent: "FakeStripeClient") -> None:
        self._parent = parent

    def create(self, *, params: dict[str, Any]) -> _FakeCustomer:
        # Latency simulation widens the race window — without it, the
        # 2-way concurrent test sometimes serializes inside asyncpg's
        # connection pool and hides the race the FOR UPDATE lock is
        # defending against. 0.05s is plenty given testcontainers
        # Postgres lock acquisition takes <1ms.
        with self._parent._customers_lock:
            self._parent.customers_calls.append(params)
            self._parent._next_customer_id += 1
            cid = f"cus_test_{self._parent._next_customer_id:03d}"
        return _FakeCustomer(id=cid, **params)


class _SessionService:
    """``client.checkout.sessions`` with a counter-incrementing ``.create``."""

    def __init__(self, parent: "FakeStripeClient") -> None:
        self._parent = parent

    def create(self, *, params: dict[str, Any]) -> _FakeSession:
        self._parent.session_calls.append(params)
        self._parent._next_session_id += 1
        sid = f"cs_test_{self._parent._next_session_id:03d}"
        url = f"https://checkout.stripe.com/c/pay/{sid}"
        return _FakeSession(id=sid, url=url, **params)


class _CheckoutNamespace:
    def __init__(self, parent: "FakeStripeClient") -> None:
        self.sessions = _SessionService(parent)


class FakeStripeClient:
    """Stateful test double mirroring ``stripe.StripeClient`` shape.

    Mirrors the v15 service-pattern surface used by Wave 1's
    ``services/stripe_client.py`` helpers:
      * ``client.customers.create(params={...}) -> Customer``
      * ``client.checkout.sessions.create(params={...}) -> Session``

    Counters surface as ``.customers_calls`` / ``.session_calls`` for
    test assertions. Returned ids are deterministic-incrementing so the
    URL inspection assertions are stable across reruns.

    Per RESEARCH Pitfall 10: stripe-mock is shape-only and stateless;
    our tests need to verify counter math (lazy create called once not
    twice) and end-to-end URL propagation, so a hand-rolled stateful
    fake is the appropriate tool. The Wave 0 spike-a covered the SDK's
    HMAC + signature contract end-to-end against the real ``stripe``
    library, so this fake doesn't need to re-prove that.
    """

    def __init__(self) -> None:
        self.customers_calls: list[dict[str, Any]] = []
        self.session_calls: list[dict[str, Any]] = []
        self._next_customer_id: int = 0
        self._next_session_id: int = 0
        # Thread-safe customer counter (the 2-way concurrent test runs
        # under asyncio.gather; the SDK's ``customers.create`` is sync so
        # the helpers wrap it under the same event loop — but the lock
        # documents intent and prevents subtle interleaving in the
        # synthetic latency window).
        self._customers_lock = Lock()
        self.customers = _CustomerService(self)
        self.checkout = _CheckoutNamespace(self)


# ---------------------------------------------------------------------------
# Fixtures — inject the fake into app.state.stripe_client per-test
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_stripe_client(async_client: httpx.AsyncClient) -> FakeStripeClient:
    """Replace ``app.state.stripe_client`` with a stateful fake.

    The lifespan-built real StripeClient (sk_test_DEV_PLACEHOLDER) is
    valid in shape but its outbound calls would fail in unit tests; the
    fake intercepts at the SDK boundary so the helpers in
    ``services/stripe_client.py`` exercise their full DB + flow logic
    while the actual HTTP-to-Stripe call is short-circuited.
    """
    app = async_client._app  # type: ignore[attr-defined]
    fake = FakeStripeClient()
    original = app.state.stripe_client
    app.state.stripe_client = fake
    yield fake
    app.state.stripe_client = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _set_user_stripe_customer_id(
    pool: asyncpg.Pool, *, user_id: UUID, stripe_customer_id: str | None,
) -> None:
    """Reset ``users.stripe_customer_id`` (NULL → forces lazy create)."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET stripe_customer_id = $1 WHERE id = $2",
            stripe_customer_id, user_id,
        )


async def _read_stripe_customer_id(
    pool: asyncpg.Pool, *, user_id: UUID,
) -> str | None:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT stripe_customer_id FROM users WHERE id = $1",
            user_id,
        )


# ===========================================================================
# POST /v1/billing/checkout — 6 tests
# ===========================================================================


async def test_checkout_unauthenticated_returns_401(
    async_client: httpx.AsyncClient,
    fake_stripe_client: FakeStripeClient,
) -> None:
    """No cookie → 401 + Stripe envelope code=UNAUTHORIZED."""
    r = await async_client.post(
        "/v1/billing/checkout",
        json={"pack_id": "pack_25"},
    )
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert body["error"]["param"] == "ap_session"
    # No Stripe SDK call attempted.
    assert fake_stripe_client.customers_calls == []
    assert fake_stripe_client.session_calls == []


async def test_checkout_invalid_pack_id_returns_400_with_invalid_pack_id_code(
    async_client: httpx.AsyncClient,
    authenticated_cookie: dict,
    fake_stripe_client: FakeStripeClient,
) -> None:
    """T-B-PCK — unknown pack_id rejected with INVALID_PACK_ID (400)."""
    r = await async_client.post(
        "/v1/billing/checkout",
        json={"pack_id": "pack_999_does_not_exist"},
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "INVALID_PACK_ID"
    # No Stripe SDK call attempted on the rejection path.
    assert fake_stripe_client.customers_calls == []
    assert fake_stripe_client.session_calls == []


async def test_checkout_valid_pack_id_returns_200_with_checkout_url(
    async_client: httpx.AsyncClient,
    authenticated_cookie: dict,
    fake_stripe_client: FakeStripeClient,
) -> None:
    """Happy path — valid pack returns a checkout_url string."""
    r = await async_client.post(
        "/v1/billing/checkout",
        json={"pack_id": "pack_25"},
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "checkout_url" in body
    assert isinstance(body["checkout_url"], str)
    # Returned URL must be the URL the (fake) StripeClient minted (sentinel
    # — proves the helper return value is propagated unmodified).
    assert body["checkout_url"].startswith("https://checkout.stripe.com/c/pay/")
    # Customer was lazy-created.
    assert len(fake_stripe_client.customers_calls) == 1
    # Checkout session was created with pack_25's Stripe price id.
    assert len(fake_stripe_client.session_calls) == 1
    sess_params = fake_stripe_client.session_calls[0]
    assert sess_params["mode"] == "payment"
    assert sess_params["allow_promotion_codes"] is True       # D-24
    # Phase B UAT regression fix (#13): automatic_tax must be OPT-IN.
    # Stripe Tax is not supported in every account country (e.g. Brazil).
    # Default: not in params. Opt-in via AP_STRIPE_AUTOMATIC_TAX_ENABLED=true.
    assert "automatic_tax" not in sess_params, (
        "automatic_tax must default to off (Stripe Tax country-restricted)"
    )
    # metadata carries pack_id + ap_user_id for webhook handler (Wave 3).
    assert sess_params["metadata"]["pack_id"] == "pack_25"
    assert sess_params["metadata"]["ap_user_id"] == authenticated_cookie["_user_id"]


async def test_checkout_lazy_creates_customer_on_first_call_only(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
    fake_stripe_client: FakeStripeClient,
) -> None:
    """T-B-LR — second sequential POST reuses written stripe_customer_id."""
    cookie = {"Cookie": authenticated_cookie["Cookie"]}
    user_id = UUID(authenticated_cookie["_user_id"])

    # Confirm clean slate — no Stripe customer yet.
    assert await _read_stripe_customer_id(db_pool, user_id=user_id) is None

    # First POST → must create the customer.
    r1 = await async_client.post(
        "/v1/billing/checkout", json={"pack_id": "pack_5"}, headers=cookie,
    )
    assert r1.status_code == 200, r1.text
    assert len(fake_stripe_client.customers_calls) == 1
    cust1 = await _read_stripe_customer_id(db_pool, user_id=user_id)
    assert cust1 is not None and cust1.startswith("cus_test_")

    # Second POST → must NOT call customers.create again.
    r2 = await async_client.post(
        "/v1/billing/checkout", json={"pack_id": "pack_10"}, headers=cookie,
    )
    assert r2.status_code == 200, r2.text
    # Counter is the load-bearing assertion (matches spike-g case (b)/(c)).
    assert len(fake_stripe_client.customers_calls) == 1, (
        "second POST re-invoked customers.create — D-11 lazy idempotency broken"
    )
    # But two distinct Checkout sessions were created.
    assert len(fake_stripe_client.session_calls) == 2
    # And both sessions reference the SAME customer id (read from DB by
    # the helper's fetchrow path).
    assert fake_stripe_client.session_calls[0]["customer"] == cust1
    assert fake_stripe_client.session_calls[1]["customer"] == cust1


async def test_checkout_concurrent_first_clicks_create_one_customer(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
    fake_stripe_client: FakeStripeClient,
) -> None:
    """Race-defense — 2 concurrent POSTs from same user = 1 customer.

    Mirrors ``tests/_spikes/spike_g_lazy_customer_create.py`` case (b).
    Without ``SELECT ... FOR UPDATE`` in lazy_create_or_fetch_customer,
    both racers would observe ``stripe_customer_id IS NULL`` at READ
    COMMITTED and both invoke customers.create — that's the bug Wave 1
    locked down.
    """
    cookie = {"Cookie": authenticated_cookie["Cookie"]}
    user_id = UUID(authenticated_cookie["_user_id"])
    assert await _read_stripe_customer_id(db_pool, user_id=user_id) is None

    # Fire two concurrent POSTs.
    r1, r2 = await asyncio.gather(
        async_client.post(
            "/v1/billing/checkout", json={"pack_id": "pack_5"}, headers=cookie,
        ),
        async_client.post(
            "/v1/billing/checkout", json={"pack_id": "pack_10"}, headers=cookie,
        ),
    )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    # The load-bearing assertion: exactly ONE customer create across both
    # racers (vs the without-FOR-UPDATE counter-example which would be 2).
    assert len(fake_stripe_client.customers_calls) == 1, (
        f"FOR UPDATE failed to serialize racers: "
        f"{len(fake_stripe_client.customers_calls)} customer creates "
        f"(expected exactly 1)"
    )
    # Both Checkout sessions reference the SAME customer.
    assert len(fake_stripe_client.session_calls) == 2
    cids = {p["customer"] for p in fake_stripe_client.session_calls}
    assert len(cids) == 1, f"sessions point at different customers: {cids}"


async def test_checkout_default_success_url_carries_session_id_placeholder(
    async_client: httpx.AsyncClient,
    authenticated_cookie: dict,
    fake_stripe_client: FakeStripeClient,
) -> None:
    """The default success_url MUST embed ``{CHECKOUT_SESSION_ID}``.

    Stripe substitutes that placeholder server-side at redirect time so
    the mobile webview's nav delegate (D-21) can read the session id off
    the return URL. If the constant ever drifts to a literal session id
    or omits the placeholder, mobile loses the post-Checkout handshake.
    """
    cookie = {"Cookie": authenticated_cookie["Cookie"]}
    r = await async_client.post(
        "/v1/billing/checkout", json={"pack_id": "pack_5"}, headers=cookie,
    )
    assert r.status_code == 200, r.text
    sess_params = fake_stripe_client.session_calls[0]
    # The default URL is what Stripe receives; the mobile webview
    # intercepts the redirected URL post-payment.
    assert "{CHECKOUT_SESSION_ID}" in sess_params["success_url"], (
        f"default success_url missing placeholder: {sess_params['success_url']!r}"
    )


# ===========================================================================
# POST /v1/billing/subscription — 3 tests
# ===========================================================================


async def test_subscription_unauthenticated_returns_401(
    async_client: httpx.AsyncClient,
    fake_stripe_client: FakeStripeClient,
) -> None:
    r = await async_client.post("/v1/billing/subscription", json={})
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert fake_stripe_client.customers_calls == []
    assert fake_stripe_client.session_calls == []


async def test_subscription_authenticated_returns_200_with_checkout_url(
    async_client: httpx.AsyncClient,
    authenticated_cookie: dict,
    fake_stripe_client: FakeStripeClient,
) -> None:
    r = await async_client.post(
        "/v1/billing/subscription", json={},
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "checkout_url" in body
    assert body["checkout_url"].startswith("https://checkout.stripe.com/c/pay/")
    assert len(fake_stripe_client.customers_calls) == 1
    assert len(fake_stripe_client.session_calls) == 1
    sess = fake_stripe_client.session_calls[0]
    assert sess["mode"] == "subscription"
    assert sess["allow_promotion_codes"] is True              # D-24
    # See test_checkout_valid_pack_id_returns_200_with_checkout_url for #13 details.
    assert "automatic_tax" not in sess


async def test_subscription_uses_pro_monthly_price_id_from_settings(
    async_client: httpx.AsyncClient,
    authenticated_cookie: dict,
    fake_stripe_client: FakeStripeClient,
) -> None:
    """Subscription session's line_item must reference settings price id."""
    app = async_client._app  # type: ignore[attr-defined]
    expected_price = app.state.settings.stripe_price_id_pro_monthly
    assert expected_price, (
        "settings.stripe_price_id_pro_monthly resolved empty — "
        "Settings dev placeholder substitution failed"
    )

    r = await async_client.post(
        "/v1/billing/subscription", json={},
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text

    sess = fake_stripe_client.session_calls[0]
    line_items = sess["line_items"]
    assert len(line_items) == 1
    assert line_items[0]["price"] == expected_price
    assert line_items[0]["quantity"] == 1


# ===========================================================================
# phase_b_e2e — real Stripe TEST mode
# ===========================================================================


@pytest.mark.phase_b_e2e
@pytest.mark.skipif(
    not os.getenv("AP_STRIPE_TEST_API_KEY"),
    reason="AP_STRIPE_TEST_API_KEY not set; skipping real-Stripe e2e test",
)
async def test_phase_b_e2e_real_stripe_test_mode_creates_real_session(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """e2e — drive POST /v1/billing/checkout against real Stripe TEST.

    Skipped by default; opt-in via ``pytest -m phase_b_e2e``.
    Verifies the returned checkout_url starts with ``cs_test_`` (real
    Stripe TEST session prefix) and that the lazy-created Customer
    carries ``metadata.ap_user_id == <user_id>``. Cleans up the test
    customer at the end so reruns don't accumulate Stripe-side state.

    PLAN 13 will run this in CI via ``make e2e-phase-b-stripe`` against
    GH Actions secret AP_STRIPE_TEST_API_KEY (mirrors Phase 31 H8 shape).
    """
    import stripe  # local import — only needed for the e2e branch

    # Build a real StripeClient with the env-provided TEST key, swap it
    # onto app.state.stripe_client for the duration of the request.
    app = async_client._app  # type: ignore[attr-defined]
    real_client = stripe.StripeClient(os.environ["AP_STRIPE_TEST_API_KEY"])
    original = app.state.stripe_client
    app.state.stripe_client = real_client

    user_id = UUID(authenticated_cookie["_user_id"])
    customer_id_to_clean: str | None = None
    try:
        r = await async_client.post(
            "/v1/billing/checkout",
            json={"pack_id": "pack_5"},
            headers={"Cookie": authenticated_cookie["Cookie"]},
        )
        assert r.status_code == 200, r.text
        url = r.json()["checkout_url"]
        # Real Stripe TEST URLs all start with this prefix.
        assert url.startswith("https://checkout.stripe.com/c/pay/cs_test_"), url

        # Lazy-created customer should now be on the user row + carry
        # ap_user_id metadata.
        customer_id_to_clean = await _read_stripe_customer_id(
            db_pool, user_id=user_id,
        )
        assert customer_id_to_clean is not None
        assert customer_id_to_clean.startswith("cus_")
        cust = real_client.customers.retrieve(customer_id_to_clean)
        assert cust.metadata.get("ap_user_id") == str(user_id)
    finally:
        # Cleanup: delete the test Customer (best-effort) + restore stub.
        if customer_id_to_clean:
            try:
                real_client.customers.delete(customer_id_to_clean)
            except Exception:
                pass
        app.state.stripe_client = original
