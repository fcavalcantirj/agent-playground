"""Phase 22c.3-04 Task 1 — Pydantic per-kind payloads for the 3 new
``agent_events`` kinds (D-12 / D-24 / D-13).

Pure unit tests (no DB). Three new classes mirror the four prior payloads
in shape, but per D-22 they DO carry user-visible content (``content``,
``bot_response``-shaped fields) — ``ConfigDict(extra="forbid")`` is still
enforced as defense-in-depth against accidental field additions, NOT as
the privacy boundary it was for the prior 4 kinds.

Coverage matrix (10 tests):

  * ``test_inapp_inbound_valid``                          — happy path
  * ``test_inapp_inbound_rejects_extra_field``            — extra='forbid'
  * ``test_inapp_inbound_rejects_empty_content``          — min_length=1
  * ``test_inapp_inbound_rejects_wrong_source``           — pattern=user
  * ``test_inapp_outbound_valid``                         — happy path
  * ``test_inapp_outbound_rejects_user_source``           — pattern=agent
  * ``test_inapp_outbound_failed_valid``                  — every error_type
  * ``test_inapp_outbound_failed_rejects_unknown_error_type`` — pattern enum
  * ``test_kind_to_payload_dispatch``                     — class identity
  * ``test_valid_kinds_set``                              — VALID_KINDS extension
  * ``test_valid_kinds_extension_does_not_break_existing`` — D-02 regression
  * ``test_inapp_inbound_kind_in_kinds_filter``           — D-14 router whitelist
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# inapp_inbound — content from user → bot
# ---------------------------------------------------------------------------


def test_inapp_inbound_valid():
    from api_server.models.events import InappInboundPayload

    p = InappInboundPayload(
        content="hi",
        source="user",
        from_user_id=uuid4(),
        captured_at=datetime.now(timezone.utc),
    )
    assert p.content == "hi"
    assert p.source == "user"


def test_inapp_inbound_rejects_extra_field():
    """``ConfigDict(extra='forbid')`` defends against accidental field drift."""
    from api_server.models.events import InappInboundPayload

    with pytest.raises(ValidationError):
        InappInboundPayload(
            content="hi",
            source="user",
            from_user_id=uuid4(),
            captured_at=datetime.now(timezone.utc),
            extra="evil",
        )


def test_inapp_inbound_rejects_empty_content():
    from api_server.models.events import InappInboundPayload

    with pytest.raises(ValidationError):
        InappInboundPayload(
            content="",
            source="user",
            from_user_id=uuid4(),
            captured_at=datetime.now(timezone.utc),
        )


def test_inapp_inbound_rejects_wrong_source():
    """``source`` is constrained to literal ``user`` for inbound events."""
    from api_server.models.events import InappInboundPayload

    with pytest.raises(ValidationError):
        InappInboundPayload(
            content="hi",
            source="agent",  # WRONG — inbound is always source=user
            from_user_id=uuid4(),
            captured_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# inapp_outbound — content from bot → user (the bot's reply)
# ---------------------------------------------------------------------------


def test_inapp_outbound_valid():
    from api_server.models.events import InappOutboundPayload

    p = InappOutboundPayload(
        content="hello back",
        source="agent",
        captured_at=datetime.now(timezone.utc),
    )
    assert p.content == "hello back"
    assert p.source == "agent"


def test_inapp_outbound_rejects_user_source():
    """``source`` is constrained to literal ``agent`` for outbound events."""
    from api_server.models.events import InappOutboundPayload

    with pytest.raises(ValidationError):
        InappOutboundPayload(
            content="hello",
            source="user",  # WRONG — outbound is always source=agent
            captured_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# inapp_outbound_failed — error envelope when the bot can't reply
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error_type",
    [
        "bot_5xx",
        "bot_timeout",
        "bot_empty",
        "container_dead",
        "recipe_no_inapp_channel",
        "container_not_ready",
        "recipe_missing",
        "reaper_timeout",
        "internal",
    ],
)
def test_inapp_outbound_failed_valid(error_type: str):
    """Each of the 9 documented error_type values constructs cleanly."""
    from api_server.models.events import InappOutboundFailedPayload

    p = InappOutboundFailedPayload(
        error_type=error_type,
        message="something broke",
        retry_count=0,
        captured_at=datetime.now(timezone.utc),
    )
    assert p.error_type == error_type
    assert p.retry_count == 0


def test_inapp_outbound_failed_rejects_unknown_error_type():
    from api_server.models.events import InappOutboundFailedPayload

    with pytest.raises(ValidationError):
        InappOutboundFailedPayload(
            error_type="unknown_thing",
            message="something broke",
            retry_count=0,
            captured_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Dispatch + VALID_KINDS extension
# ---------------------------------------------------------------------------


def test_kind_to_payload_dispatch():
    """``KIND_TO_PAYLOAD`` resolves each new kind to its payload class."""
    from api_server.models.events import (
        KIND_TO_PAYLOAD,
        InappInboundPayload,
        InappOutboundFailedPayload,
        InappOutboundPayload,
    )

    assert KIND_TO_PAYLOAD["inapp_inbound"] is InappInboundPayload
    assert KIND_TO_PAYLOAD["inapp_outbound"] is InappOutboundPayload
    assert KIND_TO_PAYLOAD["inapp_outbound_failed"] is InappOutboundFailedPayload


def test_valid_kinds_set():
    """All 3 new kinds are members of ``VALID_KINDS``."""
    from api_server.models.events import VALID_KINDS

    assert "inapp_inbound" in VALID_KINDS
    assert "inapp_outbound" in VALID_KINDS
    assert "inapp_outbound_failed" in VALID_KINDS


def test_valid_kinds_extension_does_not_break_existing():
    """D-02 regression: pre-existing 4 kinds still parse via KIND_TO_PAYLOAD."""
    from api_server.models.events import KIND_TO_PAYLOAD, VALID_KINDS

    pre_existing = {"reply_sent", "reply_failed", "agent_ready", "agent_error"}
    for k in pre_existing:
        assert k in VALID_KINDS, f"existing kind {k} disappeared from VALID_KINDS"
        assert k in KIND_TO_PAYLOAD, f"existing kind {k} disappeared from KIND_TO_PAYLOAD"

    # 4 prior + 3 new = 7 total.
    assert len(VALID_KINDS) == 7
    assert len(KIND_TO_PAYLOAD) == 7


def test_inapp_inbound_kind_in_kinds_filter():
    """D-14: ``GET /v1/agents/:id/events?kinds=inapp_inbound`` must pass the
    V13 whitelist gate. The router checks membership in ``VALID_KINDS`` before
    accepting the query-param value; missing membership would 400 the request.
    """
    from api_server.models.events import VALID_KINDS

    # Concrete check from the plan's ``<behavior>`` block.
    assert "inapp_inbound" in VALID_KINDS
