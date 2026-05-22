"""Phase B Plan B-stripe-02 — atomic credit-ledger helpers.

Three caller-owned-tx helpers:

  * ``debit_user``       — deduct cost_cents from balance; idempotent on
                           UNIQUE(reference_id, reference_type).
  * ``credit_user``      — top-up / refund / admin_writeoff; idempotent
                           on the same UNIQUE.
  * ``record_tier_change`` — D-26 audit row; balance unchanged; idempotent
                           on stripe_event_id.

D-17 ledger-as-truth: ``credit_transactions`` is the only source of
truth; ``credit_balances.balance_cents`` is a denormalized cache rebuilt
by every helper from ``SUM(amount_cents)``. Mirrors MSV
``poken_service.go:180``.

Concurrency proof (Wave 0 spike-c, ``tests/_spikes/spike_c_atomic_ledger.py``):
the naive ``INSERT debit row → UPDATE balance = SUM(...)`` pattern at
Postgres READ COMMITTED does NOT serialize. Each transaction's INSERT
is visible to siblings only AFTER commit; the SUM subquery in each
transaction's UPDATE evaluates against its own snapshot and misses
concurrent inserts → lost cache updates.

Defense (this module): ``_lock_balance_row`` issues
``SELECT 1 FROM credit_balances WHERE user_id = $1 FOR UPDATE`` BEFORE
the INSERT. Concurrent debit transactions serialize on that row lock;
by the time each transaction reads SUM, every prior transaction has
committed (their lock release is what woke us up). Mirrors MSV
``poken_service.go:180`` row-lock-then-read discipline.

Caller-owned-tx contract (mirrors ``services.usage_recorder.record_usage``):
the caller MUST be inside ``async with conn.transaction(): ...``. The
helpers do NOT commit. Idempotency on retry: on
``asyncpg.UniqueViolationError`` for the (reference_id, reference_type)
partial UNIQUE index, the helper RETURNS the originally-debited /
existing-balance value WITHOUT propagating the exception — this is what
makes the activity-retry path correct (Phase 28 D-22 + Phase B Wave 4
debit_balance activity body).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import asyncpg


_LOCK_BALANCE_SQL = (
    "SELECT 1 FROM credit_balances WHERE user_id = $1 FOR UPDATE"
)


async def _ensure_balance_row(
    conn: asyncpg.Connection, user_id: UUID,
) -> None:
    """Idempotent UPSERT of the cache row (PK on user_id).

    Phase B's first debit / first topup hits the path where the user has
    no ``credit_balances`` row yet (Free / Pro users never had one;
    Ultra users get one on first top-up). Without an INSERT-or-IGNORE,
    the subsequent UPDATE would no-op against zero rows and the cache
    would silently disagree with the ledger. This bootstraps the row at
    balance=0 so the SELECT FOR UPDATE + UPDATE path is safe to run.
    """
    await conn.execute(
        "INSERT INTO credit_balances (user_id, balance_cents) "
        "VALUES ($1, 0) ON CONFLICT (user_id) DO NOTHING",
        user_id,
    )


async def _lock_balance_row(
    conn: asyncpg.Connection, user_id: UUID,
) -> None:
    """Take the per-user row lock (spike-c-proven serialization point).

    Concurrent helpers acting on the same user serialize here. Releasing
    the lock requires the transaction to commit, so all prior INSERTs
    are visible to the post-lock-acquire SUM rebuild (no lost updates).
    """
    await conn.execute(_LOCK_BALANCE_SQL, user_id)


async def _rebuild_balance_from_ledger(
    conn: asyncpg.Connection, user_id: UUID,
) -> int:
    """SUM-from-ledger rebuild — single statement caches drift away (D-17).

    Post-lock; safe to call inside the caller's transaction.
    """
    new_balance = await conn.fetchval(
        "UPDATE credit_balances "
        "   SET balance_cents = ( "
        "          SELECT COALESCE(SUM(amount_cents), 0) "
        "          FROM credit_transactions WHERE user_id = $1), "
        "       updated_at = NOW() "
        " WHERE user_id = $1 RETURNING balance_cents",
        user_id,
    )
    if new_balance is None:
        # Balance row absent — caller skipped _ensure_balance_row.
        # Defensive: rebuild via SELECT and re-insert. Should never fire
        # in normal Phase B flows; the helpers below always call
        # _ensure_balance_row before this.
        new_balance = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_cents), 0)::BIGINT "
            "FROM credit_transactions WHERE user_id = $1",
            user_id,
        )
    return int(new_balance)


async def debit_user(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    cost_cents: int,
    reference_id: str,
    reference_type: str,
) -> Decimal:
    """Insert a kind='debit' ledger row + rebuild the balance cache.

    Caller MUST be inside ``conn.transaction()``. Returns Decimal-USD
    (cents/100) regardless of which path is taken (fresh insert vs
    idempotent retry on UniqueViolationError).

    Idempotent on UNIQUE(reference_id, reference_type) — the partial
    index on ``credit_transactions`` raises asyncpg.UniqueViolationError
    on a duplicate INSERT; the helper catches and returns the same
    Decimal value (the caller — typically the Phase 28 / Phase B
    debit_balance activity — has already debited the user; a retry
    must not double-debit).
    """
    await _ensure_balance_row(conn, user_id)
    await _lock_balance_row(conn, user_id)
    # Savepoint around the INSERT so a UNIQUE-violation aborts only the
    # savepoint, not the outer caller's transaction. asyncpg's nested
    # ``conn.transaction()`` opens a SAVEPOINT — same shape as
    # ``services.usage_recorder.record_usage`` (caller-owned-tx + nested
    # savepoint for defensive failure isolation).
    try:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO credit_transactions "
                "  (user_id, kind, amount_cents, reference_id, reference_type) "
                "  VALUES ($1, 'debit', $2, $3, $4)",
                user_id, -abs(cost_cents), reference_id, reference_type,
            )
    except asyncpg.UniqueViolationError:
        # Idempotent retry: the row already exists from a prior commit;
        # the balance cache already reflects it. Return the originally-
        # debited Decimal so the caller (Phase 28 activity) sees a
        # consistent result. The savepoint rollback above kept the
        # outer transaction healthy — we can keep using ``conn``.
        return Decimal(abs(cost_cents)) / Decimal(100)
    await _rebuild_balance_from_ledger(conn, user_id)
    return Decimal(abs(cost_cents)) / Decimal(100)


async def credit_user(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    kind: str,
    amount_cents: int,
    reference_id: str,
    reference_type: str,
) -> int:
    """Insert a positive-amount credit row + rebuild the balance cache.

    ``kind`` MUST be one of ('topup', 'refund', 'admin_writeoff'). The
    'debit' kind is owned by ``debit_user``; passing it raises
    ValueError (defense-in-depth — keeps the kind-routing intent explicit
    at the call site).

    Returns the new balance cache value (BIGINT cents) post-INSERT, or —
    on UniqueViolationError — the existing cached balance (idempotent
    retry path; the prior call already settled).

    Caller MUST be inside ``conn.transaction()``.
    """
    if kind not in ("topup", "refund", "admin_writeoff"):
        raise ValueError(
            f"credit_user kind must be one of ('topup','refund','admin_writeoff'), "
            f"got: {kind!r} — use debit_user for debits"
        )
    await _ensure_balance_row(conn, user_id)
    await _lock_balance_row(conn, user_id)
    # Savepoint around the INSERT — same defensive isolation as debit_user.
    try:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO credit_transactions "
                "  (user_id, kind, amount_cents, reference_id, reference_type) "
                "  VALUES ($1, $2, $3, $4, $5)",
                user_id, kind, amount_cents, reference_id, reference_type,
            )
    except asyncpg.UniqueViolationError:
        # Idempotent retry path. Cache reflects the prior settlement.
        return await conn.fetchval(
            "SELECT balance_cents FROM credit_balances WHERE user_id = $1",
            user_id,
        )
    return await _rebuild_balance_from_ledger(conn, user_id)


async def record_tier_change(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    from_tier: str,
    to_tier: str,
    stripe_event_id: str | None = None,
    revenuecat_event_id: str | None = None,
) -> None:
    """Insert a kind='tier_change', amount_cents=0 audit row (D-26).

    Balance unchanged. The transition itself (UPDATE users.tier) is the
    webhook handler's responsibility (D-04 — webhook is the sole tier
    writer); this helper only records the audit trail.

    Idempotent on UNIQUE(reference_id, reference_type). The discriminator
    distinguishes Stripe events from RevenueCat (IAP) events:

      * stripe_event_id      → reference_type='stripe_event'   (web subs)
      * revenuecat_event_id  → reference_type='revenuecat_event' (iOS/Android IAP)

    Exactly one of the two MUST be provided. The existing partial UNIQUE
    on (reference_id, reference_type) — added in migration 014 — handles
    cross-source idempotency without a schema change: a Stripe replay
    can't collide with an RC replay because the reference_type differs.

    Caller MUST be inside ``conn.transaction()``.

    Note: ``from_tier`` and ``to_tier`` are accepted but NOT persisted in
    a separate column — Phase B keeps the audit trail in the existing
    ledger schema (D-26 — no separate audit_log table). The webhook
    handler logs the from/to transition; the ledger row's reference_id
    lets ops cross-reference the upstream payload if a per-event from→to
    lookup is needed.
    """
    # Defensive validation — caller may pass unknown tier strings if a
    # future webhook payload surprises us; raise so we surface the issue
    # early rather than silently store nonsense.
    valid_tiers = ("free", "pro", "ultra")
    if from_tier not in valid_tiers or to_tier not in valid_tiers:
        raise ValueError(
            f"record_tier_change: from_tier={from_tier!r} to_tier={to_tier!r} "
            f"— both must be in {valid_tiers}"
        )
    # Exactly one event-source — caller bug if both or neither provided.
    if (stripe_event_id is None) == (revenuecat_event_id is None):
        raise ValueError(
            "record_tier_change: exactly one of stripe_event_id or "
            "revenuecat_event_id must be provided"
        )
    if stripe_event_id is not None:
        reference_id, reference_type = stripe_event_id, "stripe_event"
    else:
        reference_id, reference_type = revenuecat_event_id, "revenuecat_event"
    # Savepoint around the INSERT — UNIQUE-violation rollback aborts only
    # the savepoint, not the outer webhook-handler transaction. Same
    # defensive isolation as debit_user / credit_user.
    try:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO credit_transactions "
                "  (user_id, kind, amount_cents, reference_id, reference_type) "
                "  VALUES ($1, 'tier_change', 0, $2, $3)",
                user_id, reference_id, reference_type,
            )
    except asyncpg.UniqueViolationError:
        # Already audited — webhook is being retried after a 5xx blip.
        # No-op: balance is unchanged and the prior audit row stands.
        pass
