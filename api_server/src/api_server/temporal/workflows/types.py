"""Shared workflow/activity dataclasses.

Temporal serializes activity inputs/outputs as JSON. All cross-boundary
fields must be primitive-or-dict — UUID/datetime/Decimal are
stringified before crossing the wire.

This module is intentionally tiny and dependency-free so it can be
imported from BOTH the workflow file (sandbox-restricted) AND the
activity files (unrestricted) without sandbox warnings.

Frozen-dataclass discipline (CONTEXT D-09 — Go-portable shape):

- All cross-process structs are frozen dataclasses.
- ``dict[str, Any]`` opaque payloads use ``field(default_factory=dict)``
  so the dataclass remains hashable and equality-checkable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ForwardResult:
    """Output of the ``forward_to_agent`` activity (Plan 04 fills body).

    Carries the bot reply plus the opaque payloads that downstream
    activities consume. The workflow does NOT introspect the payload
    fields — it forwards them verbatim to ``record_usage``,
    ``emit_inapp_outbound``, and ``mark_message_done``. This keeps the
    workflow body deterministic (no dict introspection / branching on
    payload shape) and matches MSV's pattern of opaque
    activity-to-activity payload pass-through.

    Fields:

    - ``reply``: bot reply text. Empty/whitespace-only triggers a
      ``bot_empty`` terminal failure in the workflow body.
    - ``raw_response``: opaque dict for ops debugging. Downstream
      activities ignore this field.
    - ``usage_input``: payload consumed by ``record_usage`` activity.
    - ``event_input``: payload consumed by ``emit_inapp_outbound``.
    - ``mark_done_input``: payload consumed by ``mark_message_done``.
    """

    reply: str
    raw_response: dict[str, Any] | None = None
    usage_input: dict[str, Any] = field(default_factory=dict)
    event_input: dict[str, Any] = field(default_factory=dict)
    mark_done_input: dict[str, Any] = field(default_factory=dict)
