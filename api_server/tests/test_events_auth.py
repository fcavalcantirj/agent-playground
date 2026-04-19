"""Phase 22b-05 Task 1 — errors.py extension + Task 3 — full auth matrix.

This file is populated across two tasks:
- Task 1: Unit tests for the two new ErrorCode constants (this commit).
- Task 3: Integration tests that hit GET /v1/agents/:id/events with
  various Authorization shapes (next commit).
"""
from api_server.models.errors import ErrorCode, make_error_envelope


def test_concurrent_poll_limit_constant():
    assert ErrorCode.CONCURRENT_POLL_LIMIT == "CONCURRENT_POLL_LIMIT"


def test_event_stream_unavailable_constant():
    assert ErrorCode.EVENT_STREAM_UNAVAILABLE == "EVENT_STREAM_UNAVAILABLE"


def test_concurrent_poll_limit_maps_to_rate_limit_type():
    envelope = make_error_envelope(
        ErrorCode.CONCURRENT_POLL_LIMIT,
        "another long-poll is already active for this agent",
        param="agent_id",
        category=None,
    )
    assert envelope["error"]["code"] == "CONCURRENT_POLL_LIMIT"
    assert envelope["error"]["type"] == "rate_limit_error"
    assert envelope["error"]["param"] == "agent_id"


def test_event_stream_unavailable_maps_to_infra_type():
    envelope = make_error_envelope(
        ErrorCode.EVENT_STREAM_UNAVAILABLE,
        "watcher dead",
        param=None,
        category=None,
    )
    assert envelope["error"]["code"] == "EVENT_STREAM_UNAVAILABLE"
    assert envelope["error"]["type"] == "infra_error"
