"""Phase 28 activity — forward_to_agent.

Class-bound activity that forwards the user message to the agent
container's inapp HTTP endpoint and captures the bot reply plus the
downstream payloads (usage_input / event_input / mark_done_input)
that subsequent activities consume.

The body REUSES ``services/inapp_dispatcher._dispatch_http_localhost``
verbatim — the 3-way contract switch (openai_compat / a2a_jsonrpc /
zeroclaw_native) is the load-bearing core and copying it here would
risk drift. The activity wraps the existing function with:

  1. Recipe lookup via the worker's ``recipe_index``.
  2. Container-IP discovery via the same index.
  3. Activity-internal transport-error retry budget ``[0, 1s, 2s, 4s]``
     per CONTEXT D-11. The workflow's outer ``maximum_attempts=1`` is
     intentional — the activity owns the transport-retry semantics.
  4. Terminal classification: every error path (recipe missing,
     container dead, bot 4xx/5xx, parse error, transport budget
     exhausted) raises ``ApplicationError(type='<error_type>',
     non_retryable=True)``. The workflow's
     ``_classify_forward_failure`` recovers the type back into the
     AP error_type taxonomy.

The ``ForwardResult`` returned on success carries:

- ``reply``: bot reply text.
- ``raw_response``: opaque dict for ops debugging.
- ``usage_input``: payload for ``record_usage`` activity (UUIDs
  stringified per Temporal JSON serialization rules).
- ``event_input``: payload for ``emit_inapp_outbound`` activity (no-op
  in Phase 28 per RESEARCH §7 R2; kept for shape parity).
- ``mark_done_input``: payload for ``mark_message_done`` activity.

Type-hint note: ``inp`` is annotated as ``Any`` per the activity-stub
discipline locked in Plan 03; @activity.defn calls
``typing.get_type_hints`` at decoration time, forcing forward-ref
resolution. Workflow-side annotation in ``DispatchMessageWorkflow.run``
is the canonical record. ``ForwardResult`` is safe to import at
runtime because ``types.py`` is dependency-free.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ...services.inapp_dispatcher import (
    _dispatch_http_localhost,
    _dispatch_websocket_chat,
)
from ..workflows.types import ForwardResult


def _coerce_inp(inp: Any) -> Any:
    """Normalize ``inp`` so attribute access works.

    Mirror of ``check_container_ready._coerce_inp``. Temporal's default
    JSON converter deserializes the ``DispatchMessageInput`` dataclass
    into a plain dict because the activity's runtime type-hint is
    ``Any`` (the activity-stub discipline that sidesteps the workflows
    ↔ activities circular import at @activity.defn decoration time).
    Wrap dicts in a ``SimpleNamespace`` so the rest of the function
    reads naturally; dataclass / namespace inputs pass through.
    """
    if isinstance(inp, dict):
        return SimpleNamespace(**inp)
    return inp


class ForwardActivities:
    """Class-bound holder for the bot-forward activity.

    The worker (Plan 04 Task 2) instantiates this once with the
    process-wide asyncpg pool, the shared ``httpx.AsyncClient``, and the
    ``InappRecipeIndex``; then registers ``self.forward_to_agent`` on
    the Worker's activities list.
    """

    def __init__(
        self,
        *,
        db_pool: Any,
        bot_http_client: httpx.AsyncClient,
        recipe_index: Any,
    ) -> None:
        self.db_pool = db_pool
        self.bot_http_client = bot_http_client
        self.recipe_index = recipe_index

    @activity.defn(name="forward_to_agent")
    async def forward_to_agent(self, inp: Any) -> ForwardResult:
        """Forward the message; return ForwardResult on success or
        raise ApplicationError(non_retryable=True) on terminal failure.
        """
        inp = _coerce_inp(inp)
        attempt = activity.info().attempt
        activity.logger.info(
            "phase28.forward_to_agent.attempt",
            extra={"message_id": inp.message_id, "attempt": attempt},
        )

        # 1. Recipe lookup — None means recipe lacks channels.inapp.
        inapp = self.recipe_index.get_inapp_block(inp.recipe_name)
        if inapp is None:
            raise ApplicationError(
                "recipe_lacks_inapp_channel",
                type="recipe_lacks_inapp_channel",
                non_retryable=True,
            )

        # 2. Container IP discovery — RuntimeError means dead/missing.
        try:
            container_ip = self.recipe_index.get_container_ip(inp.container_id)
        except RuntimeError:
            raise ApplicationError(
                "container_dead",
                type="container_dead",
                non_retryable=True,
            )

        # 3. Build a dict-shaped row matching ``_dispatch_http_localhost``'s
        #    expected input shape. ``_dispatch_http_localhost`` accepts
        #    asyncpg.Record OR dict-like rows (see the ``_row_get`` helper
        #    in inapp_dispatcher.py:263-275); a plain dict is fine.
        row = {
            "id": UUID(inp.message_id),
            "user_id": UUID(inp.user_id),
            "agent_id": UUID(inp.agent_id),
            "container_row_id": UUID(inp.container_row_id),
            "container_id": inp.container_id,
            "recipe_name": inp.recipe_name,
            "agent_model": inp.agent_model,
            "content": inp.content,
            "inapp_auth_token": inp.inapp_auth_token,
            "attempts": attempt,
        }

        # 4. Activity-internal transport-error retry [0, 1s, 2s, 4s] per
        #    CONTEXT D-11. HTTP 4xx/5xx + RuntimeError fail terminal
        #    immediately; only ConnectError + ReadTimeout retry.
        last_error: Exception | None = None
        for retry_idx, backoff_s in enumerate([0.0, 1.0, 2.0, 4.0]):
            if backoff_s > 0:
                await asyncio.sleep(backoff_s)
            try:
                # Pick the transport-specific dispatcher. Both raise the
                # same exception family (httpx.ConnectError /
                # httpx.ReadTimeout for transient errors, RuntimeError
                # for terminal protocol/parse failures, RuntimeError
                # "bot_5xx:<code>" for handshake-rejected upgrades) so
                # the surrounding except arms below stay uniform.
                if inapp.transport == "websocket_chat":
                    reply, raw = await _dispatch_websocket_chat(
                        row,
                        inapp,
                        container_ip,
                        timeout_seconds=inp.bot_timeout_seconds,
                    )
                else:
                    reply, raw = await _dispatch_http_localhost(
                        self.bot_http_client,
                        row,
                        inapp,
                        container_ip,
                        timeout_seconds=inp.bot_timeout_seconds,
                    )
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_error = e
                if retry_idx == 3:
                    raise ApplicationError(
                        "bot_timeout",
                        type="bot_timeout",
                        non_retryable=True,
                    )
                continue
            except httpx.HTTPStatusError as e:
                # 4xx + 5xx — both terminal (user can't fix either).
                raise ApplicationError(
                    f"bot_5xx:{e.response.status_code}",
                    type="bot_5xx",
                    non_retryable=True,
                )
            except RuntimeError as e:
                # Parse-failure family: ``openai_compat_parse_error``,
                # ``a2a_parse_error``, ``zeroclaw_parse_error``,
                # ``unknown_contract:...``, ``a2a_error:...``. Map the
                # leading colon-prefix back to the workflow's expected
                # ApplicationError.type so _classify_forward_failure
                # recovers a stable taxonomy entry.
                msg = str(e)
                err_type = msg.split(":", 1)[0] if msg else "internal_error"
                raise ApplicationError(
                    msg,
                    type=err_type,
                    non_retryable=True,
                )
            except (httpx.RequestError, ValueError):
                # ValueError covers httpx ``resp.json()`` decode failure
                # (json.JSONDecodeError subclasses ValueError).
                # RequestError covers connection-level errors not in the
                # narrow ConnectError/ReadTimeout bucket above.
                raise ApplicationError(
                    "bot_invalid_response",
                    type="bot_invalid_response",
                    non_retryable=True,
                )
            else:
                # Success — return ForwardResult with the dicts each
                # downstream activity expects. UUIDs stringified for
                # Temporal JSON serialization safety; the consuming
                # activity (``record_usage``) re-parses with UUID(s).
                return ForwardResult(
                    reply=reply,
                    raw_response=raw,
                    usage_input={
                        "user_id": inp.user_id,
                        "agent_instance_id": inp.agent_id,
                        "message_id": inp.message_id,
                        "contract": inapp.contract,
                        "provider": inapp.provider,
                        "model": inp.agent_model,
                        "response": raw,
                        "source": "inapp",
                    },
                    event_input={
                        "container_row_id": inp.container_row_id,
                        "agent_id": inp.agent_id,
                        "user_id": inp.user_id,
                        "reply": reply,
                        "message_id": inp.message_id,
                    },
                    mark_done_input={
                        "message_id": inp.message_id,
                        "container_row_id": inp.container_row_id,
                        "user_id": inp.user_id,
                        "agent_id": inp.agent_id,
                        "bot_response": reply,
                    },
                )

        # Unreachable — the inner ``raise`` on retry_idx==3 always fires
        # before this line. Kept for type-checker comfort.
        raise ApplicationError(
            "bot_timeout",
            type="bot_timeout",
            non_retryable=True,
        )


@activity.defn(name="forward_to_agent")
async def forward_to_agent(inp: Any) -> ForwardResult:
    """Module-level placeholder kept for the workflow file's import path.

    Workers register ``ForwardActivities.forward_to_agent`` (the bound
    method); this top-level function fails loudly so a misconfigured
    worker is detected immediately rather than silently passing.
    """
    raise NotImplementedError(
        "Workers register ForwardActivities.forward_to_agent "
        "(bound method); the module-level function is an import-path "
        "placeholder only."
    )
