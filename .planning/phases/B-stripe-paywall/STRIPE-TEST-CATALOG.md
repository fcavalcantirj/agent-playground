# Stripe TEST Catalog — Solvr Labs

> **TEST mode only.** Account: `acct_1Rbog8IXnB0o3aa1`. Minted 2026-05-08 via `stripe` CLI (host).
> Price IDs and Product IDs are non-secret (public-listable on Checkout pages). API keys + webhook secret live in `deploy/.env.prod` only.
> Live-mode catalog will need separate minting against the live Stripe account when H7 (Hetzner deploy) lands.

## Recurring (subscription)

| Tier | Product | Price | Amount | Interval | Lookup key |
|---|---|---|---|---|---|
| Pro | `prod_UTwohcwU4l1MYM` | `price_1TUyuwIXnB0o3aa1aygLWOfm` | $12.00 (1200¢) | month | `ap_pro_monthly` |

**Pro Product metadata:**
- `ap_tier=pro`
- `ap_agent_slots=5`
- `ap_retention_days=30`

## One-time (Ultra credit packs)

| Pack | Product | Price | Amount | Lookup key |
|---|---|---|---|---|
| $5 | `prod_UTwlPyU6KTX8D7` | `price_1TUyriIXnB0o3aa1cj5j4LPP` | 500¢ | `ap_pack_5usd` |
| $10 | `prod_UTwlB4cBezi9DP` | `price_1TUyrkIXnB0o3aa1TRgn0LtT` | 1000¢ | `ap_pack_10usd` |
| $25 | `prod_UTwlL69jMQdIgW` | `price_1TUyrmIXnB0o3aa1yJghgnpy` | 2500¢ | `ap_pack_25usd` |
| $50 | `prod_UTwlYDtW3eAs3G` | `price_1TUyroIXnB0o3aa1rs0hmXzJ` | 5000¢ | `ap_pack_50usd` |
| $100 | `prod_UTwliidITX3Hlk` | `price_1TUyrqIXnB0o3aa1ZZvbxaKY` | 10000¢ | `ap_pack_100usd` |

**Each pack Product carries metadata:**
- `ap_pack_id=pack_{N}usd`
- `ap_credit_cents={N*100}`

## Mapping for `services/billing_packs.py::PACKS` (Plan 02)

The hardcoded code-side `PACKS` constant pulls from env:

```python
PACKS = [
  {"id": "pack_5usd",   "label": "$5",   "usd_amount_cents": 500,   "credit_cents": 500,   "stripe_price_id": settings.AP_STRIPE_PRICE_ID_PACK_5USD},
  {"id": "pack_10usd",  "label": "$10",  "usd_amount_cents": 1000,  "credit_cents": 1000,  "stripe_price_id": settings.AP_STRIPE_PRICE_ID_PACK_10USD},
  {"id": "pack_25usd",  "label": "$25",  "usd_amount_cents": 2500,  "credit_cents": 2500,  "stripe_price_id": settings.AP_STRIPE_PRICE_ID_PACK_25USD},
  {"id": "pack_50usd",  "label": "$50",  "usd_amount_cents": 5000,  "credit_cents": 5000,  "stripe_price_id": settings.AP_STRIPE_PRICE_ID_PACK_50USD},
  {"id": "pack_100usd", "label": "$100", "usd_amount_cents": 10000, "credit_cents": 10000, "stripe_price_id": settings.AP_STRIPE_PRICE_ID_PACK_100USD},
]
```

Per CONTEXT D-07: `credit_cents == usd_amount_cents` (1:1 grant; markup lives in `cost_weights.ap_multiplier` on debit).

## Lookup-key recovery (if env var loss)

```bash
stripe prices list --lookup-keys ap_pack_5usd ap_pack_10usd ap_pack_25usd ap_pack_50usd ap_pack_100usd ap_pro_monthly | jq -r '.data[] | "\(.lookup_key)\t\(.id)"'
```

## Re-creation script (idempotent via lookup_key)

If TEST account is rotated, the bash logic from the original mint session can be re-run; lookup_key collisions trigger an existing-resource update rather than duplicate creation. See `git log --grep="docs(B-stripe-paywall): mint" -p` for the original commands.
