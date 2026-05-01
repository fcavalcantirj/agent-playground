"""Pydantic shapes for ``GET /v1/agents`` — the logged user's agents.

Mirrors the ``agent_instances`` table after migration 002 plus a
LATERAL-joined ``last_verdict`` from the most recent linked run.

Phase 22-05 extends this module with persistent-mode lifecycle request +
response shapes:

- ``AgentStartRequest`` / ``AgentStartResponse`` — body + result of
  ``POST /v1/agents/:id/start``.
- ``AgentStopResponse`` — result of ``POST /v1/agents/:id/stop``.
- ``AgentStatusResponse`` — result of ``GET /v1/agents/:id/status``;
  every container field is Optional so the "no container yet" case can
  respond 200 with a degenerate shape rather than 404.
- ``AgentChannelPairRequest`` / ``AgentChannelPairResponse`` — body +
  result of ``POST /v1/agents/:id/channels/:cid/pair`` (openclaw only
  today, generic by schema).

BYOK discipline is enforced at the route layer (see
``routes/agent_lifecycle.py``): Bearer LLM keys + ``channel_inputs``
secrets are local variables in the handler, never land on these models
after the response is built.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentSummary(BaseModel):
    id: UUID
    name: str
    recipe_name: str
    model: str
    personality: str | None = None
    created_at: datetime
    last_run_at: datetime | None = None
    total_runs: int
    last_verdict: str | None = None
    last_category: str | None = None
    last_run_id: str | None = None


class AgentListResponse(BaseModel):
    agents: list[AgentSummary]


# ---------------------------------------------------------------------------
# Phase 22-05: persistent-mode lifecycle shapes
# ---------------------------------------------------------------------------


class AgentStartRequest(BaseModel):
    """Body for ``POST /v1/agents/:id/start``.

    BYOK shape matches ``RunRequest`` in ``models/runs.py``: the Bearer
    header carries the LLM ``api_key`` (same discipline as ``/v1/runs``),
    and the body carries the CHANNEL creds (bot_token, allowed_user_id,
    ...). ``extra="forbid"`` rejects inline-YAML + unknown fields at parse
    time (V5 input validation).

    ``channel`` must match a key in ``recipe["channels"]``; the route
    handler validates the value against the recipe's ``channels`` block
    after parse. The regex restricts to lowercase + digits + ``-`` / ``_``
    so path-traversal and SQL-injection shapes are rejected before the
    route handler sees them.

    ``channel_inputs`` is a flat dict[str, str] — no nesting. Each
    ``required_user_input`` entry in the recipe maps to one key (the
    ``env`` field, e.g. ``TELEGRAM_BOT_TOKEN``). The runner's env-file
    pattern passes each entry straight to the container; values longer
    than 8 chars are redacted from every exception surface.
    """

    model_config = ConfigDict(extra="forbid")

    channel: str = Field(
        ...,
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9_-]+$",
    )
    channel_inputs: dict[str, str] = Field(default_factory=dict)
    boot_timeout_s: int | None = Field(None, ge=30, le=600)


class AgentStartResponse(BaseModel):
    """Response body for a successful ``/start``.

    Every field is non-null on the success path (Pydantic rejects
    ``None`` into the UUID + datetime fields). The route handler only
    returns this model AFTER ``execute_persistent_start`` returns a
    ``PASS`` verdict AND ``write_agent_container_running`` has flipped
    the DB row to ``status='running'``.
    """

    agent_id: UUID
    container_row_id: UUID
    container_id: str
    container_status: str  # "running" on success
    channel: str
    ready_at: datetime
    boot_wall_s: float
    health_check_ok: bool
    health_check_kind: str
    # Phase 22c.3.1 (D-31, AC-11): pre_start telemetry. Populated when
    # ``run_cell_persistent`` ran any pre_start_commands (zeroclaw inapp =
    # the canonical case); ``None`` for the legacy / no-pre-start path.
    pre_start_wall_s: float | None = None


class AgentStatusResponse(BaseModel):
    """Response body for ``GET /v1/agents/:id/status``.

    Every container-side field is Optional to handle "agent exists, no
    container row yet" (degenerate but valid) — the route returns this
    model with only ``agent_id`` set + the rest NULL. G5 (spike-11): the
    ``http_code`` and ``ready`` fields are populated ONLY when the
    recipe declares ``health_check.kind == "http"``. ``log_tail`` is the
    last 50 lines of ``docker logs`` combined stdout+stderr.
    """

    agent_id: UUID
    container_row_id: UUID | None = None
    container_id: str | None = None
    container_status: str | None = None
    channel: str | None = None
    ready_at: datetime | None = None
    boot_wall_s: float | None = None
    runtime_running: bool = False
    runtime_exit_code: int | None = None
    # G5 (spike-11): populated only when recipe.health_check.kind == "http".
    http_code: int | None = None
    ready: bool | None = None
    log_tail: list[str] = Field(default_factory=list)
    last_error: str | None = None


class AgentStopResponse(BaseModel):
    """Response body for ``POST /v1/agents/:id/stop``.

    ``force_killed`` is G3 (spike-07): ``True`` when the recipe's
    ``sigterm_handled=false`` branch fires (e.g. nanobot which ignores
    SIGTERM) OR when the SIGTERM + poll window expires and the runner
    falls back to ``docker rm -f``. Clients can surface this as a UI
    signal ("gracefully stopped" vs "force-killed").
    """

    agent_id: UUID
    container_row_id: UUID
    container_id: str
    stopped_gracefully: bool
    force_killed: bool = False
    exit_code: int
    stop_wall_s: float


class AgentChannelPairRequest(BaseModel):
    """Body for ``POST /v1/agents/:id/channels/:cid/pair``.

    ``code`` is the short pairing code the user's messaging app emitted
    (e.g. 4-char Telegram pairing code from openclaw). Strict alnum
    pattern keeps the value safe to substitute into an argv list via
    ``str.replace("$CODE", code)`` — ``$`` is not in the allowed set so
    recursive substitution is impossible.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        ...,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9]+$",
    )


class AgentChannelPairResponse(BaseModel):
    """Response body for ``POST /v1/agents/:id/channels/:cid/pair``.

    G4 (spike-10): ``wall_s`` is a client-facing alias for
    ``wall_time_s`` so frontends can render elapsed-time read-outs
    without deserializing two different numeric paths. The route
    populates both from the same runner reading.
    """

    agent_id: UUID
    channel: str
    exit_code: int
    stdout_tail: str
    stderr_tail: str
    wall_time_s: float
    wall_s: float  # G4: alias — client-facing elapsed-time readout
