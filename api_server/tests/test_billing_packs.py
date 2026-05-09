"""Phase B Plan B-stripe-02 — billing_packs unit tests.

PACKS is the single source of truth for the Phase B credit-pack catalog
(D-06). The catalog lives ONLY in api_server — mobile + web fetch via
``GET /v1/billing/packs`` (Wave 2 will ship that route). Per
``feedback_dumb_client_no_mocks.md``: NO client mirrors this list.

Tests verify:

  * 5 packs exposed in known order ($5, $10, $25, $50, $100) — D-06
  * Pack ids match the canonical id set — D-06
  * credit_cents == usd_amount_cents per pack — D-07 (1:1 grant)
  * stripe_price_id is read from Settings — wiring contract

No DB. No Stripe. Pure module-level data assertions; module reads
``stripe_price_id_pack_*`` from Settings at import time.
"""
from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture
def fresh_packs(monkeypatch):
    """Reload ``services.billing_packs`` so the module-level PACKS tuple
    picks up the test-time Settings env. The module's PACKS is built at
    import via ``_build_packs()`` reading ``get_settings()``; reloading
    re-runs ``_build_packs``.

    Reloads ONLY the billing_packs module (not config) because the config
    module reload during test runs is fragile — other already-imported
    modules hold references to the original Settings class.
    ``importlib.reload(billing_packs)`` is enough: ``_build_packs``
    re-imports and calls ``get_settings()`` against the live env.
    """
    # Strip every AP_STRIPE_* so the dev placeholder branch fires
    # deterministically regardless of the host shell.
    for k in list(os.environ.keys()):
        if k.startswith("AP_STRIPE_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")

    from api_server.services import billing_packs as bp
    importlib.reload(bp)
    return bp


def test_packs_module_exposes_5_packs_in_known_order(fresh_packs):
    """D-06: exactly 5 packs in $5 → $100 ascending order."""
    packs = fresh_packs.PACKS
    assert isinstance(packs, tuple), f"PACKS must be a tuple, got {type(packs)}"
    assert len(packs) == 5, f"expected 5 packs, got {len(packs)}"
    expected_order = ("pack_5", "pack_10", "pack_25", "pack_50", "pack_100")
    actual_order = tuple(p.id for p in packs)
    assert actual_order == expected_order, (
        f"pack order drift: {actual_order} != {expected_order}"
    )


def test_pack_ids_match_d_06_set(fresh_packs):
    """D-06 catalog: { pack_5, pack_10, pack_25, pack_50, pack_100 }."""
    packs = fresh_packs.PACKS
    ids = {p.id for p in packs}
    assert ids == {"pack_5", "pack_10", "pack_25", "pack_50", "pack_100"}


def test_pack_usd_amounts_match_dollar_labels(fresh_packs):
    """Each pack's ``usd_amount_cents`` matches its label."""
    packs = fresh_packs.PACKS
    expected = {
        "pack_5":   ("$5",   500),
        "pack_10":  ("$10",  1000),
        "pack_25":  ("$25",  2500),
        "pack_50":  ("$50",  5000),
        "pack_100": ("$100", 10000),
    }
    for p in packs:
        label, amount = expected[p.id]
        assert p.label == label, f"{p.id} label = {p.label!r}, expected {label!r}"
        assert p.usd_amount_cents == amount, (
            f"{p.id} usd_amount_cents = {p.usd_amount_cents}, expected {amount}"
        )


def test_credit_cents_equals_usd_amount_cents_per_d_07(fresh_packs):
    """D-07: top-up grant is 1:1 USD→credit. The markup lives in
    ``cost_weights.ap_multiplier`` on the DEBIT side, never on the CREDIT
    grant side.
    """
    for p in fresh_packs.PACKS:
        assert p.credit_cents == p.usd_amount_cents, (
            f"{p.id}: credit_cents ({p.credit_cents}) != "
            f"usd_amount_cents ({p.usd_amount_cents}) — D-07 invariant broken"
        )


def test_packs_pull_stripe_price_id_from_settings(fresh_packs):
    """Each pack's ``stripe_price_id`` matches the Settings field for that pack.

    In dev (no AP_STRIPE_PRICE_ID_PACK_* env), the model_validator
    ``_substitute_stripe_dev_placeholders`` fills deterministic
    placeholders that contain ``PLACEHOLDER`` and the pack id substring.
    """
    packs = fresh_packs.PACKS
    for p in packs:
        assert p.stripe_price_id, f"{p.id} stripe_price_id is empty"
        # Dev placeholder shape: "price_DEV_PLACEHOLDER_pack_<n>"
        assert "PLACEHOLDER" in p.stripe_price_id.upper(), (
            f"{p.id} stripe_price_id = {p.stripe_price_id!r} — "
            "expected dev placeholder substring"
        )
        # The pack-specific suffix is in the placeholder.
        assert p.id in p.stripe_price_id, (
            f"{p.id} stripe_price_id = {p.stripe_price_id!r} — "
            f"expected pack id {p.id!r} substring"
        )


def test_get_pack_lookup(fresh_packs):
    """get_pack(id) returns the matching Pack or None."""
    bp = fresh_packs
    p = bp.get_pack("pack_25")
    assert p is not None
    assert p.id == "pack_25"
    assert p.usd_amount_cents == 2500

    assert bp.get_pack("nonexistent") is None
    assert bp.get_pack("") is None


def test_pack_dataclass_is_frozen(fresh_packs):
    """``Pack`` is a frozen dataclass — instances are immutable.

    Mirrors ``services.proxy_dispatcher.UpstreamSpec`` shape; protects the
    catalog from accidental mutation at runtime.
    """
    p = fresh_packs.PACKS[0]
    with pytest.raises((AttributeError, Exception)):
        p.usd_amount_cents = 999  # type: ignore[misc]
