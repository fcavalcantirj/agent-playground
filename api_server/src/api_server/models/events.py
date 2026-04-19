"""Phase 22b-02 — Pydantic models for ``agent_events`` (D-05, D-06, D-08).

Per-kind typed payloads with ``ConfigDict(extra="forbid")`` enforce
D-06 ("metadata only — never the user-visible message contents") at
parse time: a payload that arrives carrying any non-declared field
(message contents, raw responses, free-form text) is rejected BEFORE
:func:`api_server.services.event_store.insert_agent_event` is reached,
so a leak cannot transit through to disk.

The four payload classes mirror the four CHECK-constraint kinds in
``agent_events``:

  - ``reply_sent``    -> :class:`ReplySentPayload`
  - ``reply_failed``  -> :class:`ReplyFailedPayload`
  - ``agent_ready``   -> :class:`AgentReadyPayload`
  - ``agent_error``   -> :class:`AgentErrorPayload`

The :data:`KIND_TO_PAYLOAD` map is the single dispatch point — the
watcher pipeline parses ``payload_dict`` against ``KIND_TO_PAYLOAD[kind]``
before INSERT; the long-poll handler reads back projected JSONB and
serializes through :class:`AgentEvent` / :class:`AgentEventsResponse`.

The read-side :class:`AgentEvent` keeps ``payload`` typed as ``dict``
rather than the per-kind union — read projections are loose by design
(historical rows may have been written by an earlier shape; readers
should not crash). Strictness lives at the WRITE boundary, where the
watcher constructs the payload and ``KIND_TO_PAYLOAD`` validates.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

VALID_KINDS: set[str] = {
    "reply_sent",
    "reply_failed",
    "agent_ready",
    "agent_error",
}


class ReplySentPayload(BaseModel):
    """Captured when the watcher sees the agent emit a successful reply.

    D-06: ``length_chars`` is a coarse metric (count, not the contents).
    The matched regex group is measured then discarded by the watcher;
    no message contents reach this payload class.
    """

    model_config = ConfigDict(extra="forbid")

    chat_id: str = Field(..., min_length=1, max_length=64)
    length_chars: int = Field(..., ge=0)
    captured_at: datetime


class ReplyFailedPayload(BaseModel):
    """Captured when a reply attempt errors out at the agent layer.

    ``chat_id`` is optional because some failure modes (e.g. agent crash
    mid-send) do not produce a chat id. ``reason`` is a classification
    string ("rate-limited", "auth-error", "model-overload") — never the
    raw error contents. The watcher is responsible for mapping a free-form
    error log line to one of a small set of classifications upstream.
    """

    model_config = ConfigDict(extra="forbid")

    chat_id: str | None = Field(default=None, max_length=64)
    reason: str = Field(..., min_length=1, max_length=256)
    captured_at: datetime


class AgentReadyPayload(BaseModel):
    """Captured when the recipe's ``ready_log_regex`` matches.

    ``ready_log_line`` is the full matched line, truncated to 512 chars.
    Optional because some recipes do not surface a ready line and the
    watcher synthesizes a ready event from container-status transition
    instead.
    """

    model_config = ConfigDict(extra="forbid")

    ready_log_line: str | None = Field(default=None, max_length=512)
    captured_at: datetime


class AgentErrorPayload(BaseModel):
    """Captured for every ERROR/FATAL line the recipe declares matching.

    ``severity`` is restricted to the two upstream levels we care about
    — WARN/INFO are noise. ``detail`` is the matched log line, capped
    at 512 chars. The watcher is responsible for credential redaction
    BEFORE this payload is built (T-22b-02-05 — transferred to Plan
    22b-03).
    """

    model_config = ConfigDict(extra="forbid")

    severity: str = Field(..., pattern=r"^(ERROR|FATAL)$")
    detail: str = Field(..., min_length=1, max_length=512)
    captured_at: datetime


KIND_TO_PAYLOAD: dict[str, type[BaseModel]] = {
    "reply_sent": ReplySentPayload,
    "reply_failed": ReplyFailedPayload,
    "agent_ready": AgentReadyPayload,
    "agent_error": AgentErrorPayload,
}


class AgentEvent(BaseModel):
    """Read-side projection of a single ``agent_events`` row.

    ``payload`` is loose ``dict`` (not the per-kind union): read-path
    rows may have been written by an earlier shape, and the long-poll
    handler should not crash on a soft-schema drift. Strict validation
    happens at the WRITE boundary via :data:`KIND_TO_PAYLOAD`.
    """

    seq: int
    kind: str
    payload: dict
    correlation_id: str | None = None
    ts: datetime


class AgentEventsResponse(BaseModel):
    """Envelope for ``GET /v1/agents/:id/events``.

    ``next_since_seq`` is the caller's follow-up cursor — set to the
    largest ``seq`` returned in ``events`` or to the request's
    ``since_seq`` when ``events`` is empty. ``timed_out`` is ``True``
    when the long-poll wait expired before any event arrived; clients
    should re-poll with the unchanged ``next_since_seq``.
    """

    agent_id: UUID
    events: list[AgentEvent] = Field(default_factory=list)
    next_since_seq: int
    timed_out: bool = False


__all__ = [
    "VALID_KINDS",
    "KIND_TO_PAYLOAD",
    "ReplySentPayload",
    "ReplyFailedPayload",
    "AgentReadyPayload",
    "AgentErrorPayload",
    "AgentEvent",
    "AgentEventsResponse",
]
