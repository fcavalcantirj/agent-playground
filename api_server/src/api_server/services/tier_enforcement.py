"""Phase B Plan B-stripe-07 — D-05 entitlement enforcement helpers.

Two surfaces gate behavior on ``users.tier`` (set by the Stripe webhook
per D-04 — webhook is sole writer):

1. ``agent.create`` — active-agent slot count cap (free=1 / pro=5 /
   ultra=∞). Enforced by :func:`check_can_create_agent` invoked from
   ``routes/agent_lifecycle.py::start_agent`` BEFORE the runner spawn.
2. ``messages.list`` — per-tier retention window (free=7d / pro=30d /
   ultra=unlimited). Enforced by :func:`retention_window_days` consumed
   from ``routes/agent_messages.py::get_messages``; the SQL store
   accepts a ``since`` parameter and adds a ``created_at >= $N`` clause
   when not None.

Single source of truth — a future "raise pro to 10 agents" or "shrink
free retention to 3d" change updates ONE constant here. No duplicated
catalogs in routes / tests / mobile (per CLAUDE.md golden rule #2 dumb
client + ``feedback_dumb_client_no_mocks.md``).

Status counting (D-05 + D-15 alignment):

* ``starting`` and ``running`` count as ACTIVE — they consume a slot.
* ``stopping``, ``stopped``, ``start_failed``, ``crashed`` do NOT count
  — the slot is released the moment the container leaves the active set.
* ``auto_paused`` (introduced in migration 014 for D-15 Pro→Free
  downgrades) does NOT count — paused agents are explicitly the bucket
  D-15 carves out for "user gets to keep them but they're frozen until
  re-upgrade".

The active-status set is enumerated in :data:`_ACTIVE_STATUSES`. The
underlying CHECK constraint (``ck_agent_containers_status``) defines the
universe of valid values; this module's enumeration is the strict subset
that consumes a tier slot.

Race protection: :func:`check_can_create_agent` opens with
``SELECT tier FROM users WHERE id=$1 FOR UPDATE`` so a concurrent caller
holding a transaction blocks until the first commits. Combined with the
``ix_agent_containers_agent_instance_running`` partial unique index, this
makes it impossible for two concurrent ``/start`` calls on a free-cap=1
user to both land an active row.
"""
from __future__ import annotations

from typing import Final
from uuid import UUID

import asyncpg


# ---------------------------------------------------------------------------
# Per-tier limits — D-05 single source of truth
# ---------------------------------------------------------------------------

# Active-agent slot cap per tier. Ultra is "effectively infinite" — int
# rather than ``math.inf`` because the count comparison is integer-typed
# (asyncpg's COUNT returns int). The 10M ceiling comfortably exceeds any
# user's plausible agent collection while leaving COUNT(*) cheap.
_TIER_AGENT_CAP: Final[dict[str, int]] = {
    "free": 1,
    "pro": 5,
    "ultra": 10_000_000,
}

# Message retention window per tier in days. ``None`` for ultra signals
# "no retention filter" — the messages.list handler must NOT add a
# ``created_at >=`` clause for ultra users.
_TIER_RETENTION_DAYS: Final[dict[str, int | None]] = {
    "free": 7,
    "pro": 30,
    "ultra": None,
}

# Container statuses that consume a tier slot. See module docstring for
# rationale. Ordered for stable SQL ``IN (...)`` text — no semantic
# meaning to the order itself.
_ACTIVE_STATUSES: Final[tuple[str, ...]] = ("starting", "running")


def agent_cap_for_tier(tier: str) -> int:
    """Active-agent slot cap for ``tier``.

    Unknown tier (typo, future migration drift) safely falls back to the
    most-restrictive value (free's cap = 1) so a misconfigured user can't
    accidentally bypass the gate.
    """
    return _TIER_AGENT_CAP.get(tier, _TIER_AGENT_CAP["free"])


def retention_window_days(tier: str) -> int | None:
    """Message retention window in days for ``tier``.

    Returns ``None`` for unlimited retention (ultra). Unknown tier falls
    back to free's 7-day window — same safe-default principle as the cap
    helper.
    """
    if tier in _TIER_RETENTION_DAYS:
        return _TIER_RETENTION_DAYS[tier]
    return _TIER_RETENTION_DAYS["free"]


async def check_can_create_agent(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
) -> tuple[bool, int, str]:
    """Return ``(allowed, current_active_count, tier)`` for a user.

    The caller MUST be inside a transaction so the row-level lock taken
    by ``SELECT tier FROM users WHERE id=$1 FOR UPDATE`` survives until
    the caller commits. This is what prevents two concurrent ``/start``
    requests from both passing the cap check on a free-cap=1 user.

    Behavior:

    * Reads ``users.tier`` (locking the row).
    * Counts ``agent_containers`` rows for ``user_id`` whose
      ``container_status`` is in :data:`_ACTIVE_STATUSES`.
    * Returns ``(count < cap_for_tier, count, tier)``.

    Defensive: if no users row matches ``user_id``, returns
    ``(False, 0, 'free')``. In normal flow ``require_user`` already
    proved the user exists; this defense covers a row deleted between
    auth resolve and this call (extremely rare).
    """
    tier = await conn.fetchval(
        "SELECT tier FROM users WHERE id = $1 FOR UPDATE",
        user_id,
    )
    if tier is None:
        return (False, 0, "free")

    # Build placeholders for the IN clause: $2, $3, ... matching the
    # length of _ACTIVE_STATUSES (currently 2 values; future-proof).
    placeholders = ", ".join(
        f"${i + 2}" for i in range(len(_ACTIVE_STATUSES))
    )
    # 2026-05-17 — count distinct logical agents, NOT distinct containers.
    # D-05 (.planning/phases/B-stripe-paywall/CONTEXT.md:37-39) intent is
    # "free=1 active agent" — a logical agent_instance, not a docker container.
    # Hermes (and any future recipe with multi-channel gateway-daemon mode)
    # legitimately spawns multiple agent_containers rows per logical agent
    # (one per channel). The previous COUNT(*) implementation counted those
    # rows as separate slots, blocking the mobile orchestrator's 2-step
    # inapp→telegram flow on free tier (cap=1). Switching to
    # COUNT(DISTINCT agent_instance_id) aligns the cap with the design
    # intent and unblocks multi-channel agents without changing the cap
    # value for any tier.
    count = await conn.fetchval(
        f"SELECT COUNT(DISTINCT agent_instance_id)::int FROM agent_containers "
        f"WHERE user_id = $1 "
        f"AND container_status IN ({placeholders})",
        user_id, *_ACTIVE_STATUSES,
    )
    cap = agent_cap_for_tier(tier)
    return (int(count) < cap, int(count), tier)


__all__ = [
    "agent_cap_for_tier",
    "retention_window_days",
    "check_can_create_agent",
]
