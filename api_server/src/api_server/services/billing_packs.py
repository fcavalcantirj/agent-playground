"""Phase B Plan B-stripe-02 — credit-pack catalog (D-06 single SOT in api_server).

Module-level frozen tuple of 5 ``Pack`` dataclasses; mirrors the
``services.proxy_dispatcher.PROVIDERS`` discipline (immutable at module
import; one place to add a 6th pack — no refactor).

Per ``feedback_dumb_client_no_mocks.md`` + CLAUDE.md golden rule #2:
this catalog lives ONLY here. Mobile + web fetch via
``GET /v1/billing/packs`` (Wave 2 will ship the route). NO client
mirrors this list locally.

D-07 invariant: ``credit_cents == usd_amount_cents`` for every pack
(1:1 USD→credit grant). The Phase B markup vehicle is
``cost_weights.ap_multiplier`` on the DEBIT side, never on the credit
grant side. Avoiding the MSV "75% post-facto discount hybrid"
anti-pattern.

The 5 ``stripe_price_id`` values are pulled from Settings at module
import. In dev with no AP_STRIPE_* env vars set, the Settings
``_substitute_stripe_dev_placeholders`` model_validator fills
deterministic placeholders ("price_DEV_PLACEHOLDER_pack_<n>"). In prod
the values must be real ``price_*`` ids minted in the Stripe dashboard
— ``validate_stripe_config(settings)`` from a Phase B service is the
fail-loud gate.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import get_settings


@dataclass(frozen=True)
class Pack:
    """Immutable per-pack descriptor.

    Mirrors ``services.proxy_dispatcher.UpstreamSpec`` shape (frozen
    dataclass + module-level tuple) so the catalog is pickled-into-cache
    safe and immune to runtime mutation.

    Field shape:

      id              "pack_5" .. "pack_100" — stable across releases (used
                      in Stripe Checkout session metadata + GET /v1/billing/packs
                      response + mobile route nav).
      label           "$5" .. "$100" — display string for UI; D-23 USD-only.
      usd_amount_cents int — USD price the user pays Stripe (line-item amount).
      credit_cents    int — credits granted on successful payment. D-07
                      invariant: credit_cents == usd_amount_cents.
      stripe_price_id str — Stripe Price object id (price_*); the
                      Checkout line_item references this. Sourced from
                      Settings.stripe_price_id_pack_*.
    """
    id: str
    label: str
    usd_amount_cents: int
    credit_cents: int
    stripe_price_id: str


def _build_packs() -> tuple[Pack, ...]:
    """Construct the 5-pack tuple from current Settings."""
    s = get_settings()
    return (
        Pack("pack_5",   "$5",   500,   500,   s.stripe_price_id_pack_5),
        Pack("pack_10",  "$10",  1000,  1000,  s.stripe_price_id_pack_10),
        Pack("pack_25",  "$25",  2500,  2500,  s.stripe_price_id_pack_25),
        Pack("pack_50",  "$50",  5000,  5000,  s.stripe_price_id_pack_50),
        Pack("pack_100", "$100", 10000, 10000, s.stripe_price_id_pack_100),
    )


# Built once at module import. Re-importing the module re-runs
# ``_build_packs()`` and re-reads Settings — useful for tests that need
# to swap Stripe price ids via monkeypatch.setenv.
PACKS: tuple[Pack, ...] = _build_packs()


def get_pack(pack_id: str) -> Pack | None:
    """Return the matching Pack, or None if pack_id is unknown."""
    return next((p for p in PACKS if p.id == pack_id), None)
