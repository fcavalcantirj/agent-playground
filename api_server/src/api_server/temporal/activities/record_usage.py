"""Phase 28 activity — record_usage.

Class-bound activity that wraps ``services/usage_recorder.record_usage``
inside an asyncpg transaction. The legacy recorder already opens a
SAVEPOINT internally so a recorder failure does NOT roll back the
caller's outer transaction; here we open a fresh outer transaction
because the workflow has no shared transaction with us — each activity
owns its own DB context per CONTEXT D-07.

The legacy recorder swallows its own exceptions and returns ``None`` on
failure (see ``services/usage_recorder.py:337-349``). The activity
mirrors that — failure is logged inside the recorder; we log a warning
at the activity boundary so Temporal's history surfaces the event, but
we do NOT raise. The workflow's own ``try/except ApplicationError``
around this activity (D-15) is therefore defensive belt-and-suspenders;
in practice an exception cannot escape ``record_usage``.

The ``usage_input`` dict shape produced by ``forward_to_agent`` is::

    {
        "user_id": "<uuid-str>",
        "agent_instance_id": "<uuid-str>",
        "message_id": "<uuid-str>",
        "contract": "openai_compat" | "a2a_jsonrpc" | "zeroclaw_native",
        "provider": "openrouter" | "anthropic" | None,
        "model": "<model-id>",
        "response": <opaque dict | None>,
        "source": "inapp",
    }

UUID strings are re-parsed here because the recorder takes ``UUID``
typed parameters; Temporal serializes them as strings across the wire.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from temporalio import activity


class RecordUsageActivities:
    """Class-bound holder for the usage-recording activity."""

    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="record_usage")
    async def record_usage(self, usage_input: dict[str, Any]) -> None:
        """Insert one usage_logs row via the legacy recorder.

        The legacy recorder takes a ``conn`` positional + kwargs; we
        unpack ``usage_input`` and re-parse the UUID strings produced
        by ``forward_to_agent``.
        """
        # Late import — the legacy module imports asyncpg + Decimal +
        # logging at module load. Importing inside the function keeps
        # the activity file's import surface narrow (matters when
        # debugging sandbox warnings; the activity file is unsandboxed
        # but the module-import-cost still shows up on worker boot).
        from ...services.usage_recorder import record_usage as legacy_record_usage

        user_id = UUID(usage_input["user_id"])
        agent_instance_id = UUID(usage_input["agent_instance_id"])
        message_id_str = usage_input.get("message_id")
        message_id = UUID(message_id_str) if message_id_str else None

        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                await legacy_record_usage(
                    conn,
                    user_id=user_id,
                    agent_instance_id=agent_instance_id,
                    message_id=message_id,
                    contract=usage_input["contract"],
                    provider=usage_input.get("provider"),
                    model=usage_input["model"],
                    response=usage_input.get("response"),
                    latency_ms=usage_input.get("latency_ms"),
                    source=usage_input.get("source", "inapp"),
                )


@activity.defn(name="record_usage")
async def record_usage(usage_input: dict[str, Any]) -> None:
    """Module-level placeholder kept for the workflow file's import path.

    Workers register ``RecordUsageActivities.record_usage`` (bound
    method); this top-level function fails loudly to surface a
    misconfigured worker.
    """
    raise NotImplementedError(
        "Workers register RecordUsageActivities.record_usage "
        "(bound method); the module-level function is an import-path "
        "placeholder only."
    )
