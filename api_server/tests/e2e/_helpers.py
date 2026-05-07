"""Phase 22c.3 Plan 15 — shared helpers for the SC-03 5-cell e2e gate.

The helpers are deliberately small. The matrix test in
``test_inapp_5x5_matrix.py`` stitches them together to produce the
``e2e-report.json`` exit-gate artifact.

Per the Plan 15 ``key_links`` line 60, the test exercises the
dispatcher adapters end-to-end against real ``ap-recipe-*`` containers
and real OpenRouter HTTP. The runner-side wiring
(``persistent_argv_override``, ``${INAPP_AUTH_TOKEN}`` minting,
``activation_env`` rendering) that ``routes/agent_lifecycle.py::
start_persistent`` does NOT yet implement (flagged in Plans
10/11/12/13/14 SUMMARYs) is reproduced *inside this test fixture* so
the gate is honest about exercising the dispatcher contract switch +
recipe HTTP shape — without coupling the e2e gate to a runner-side
refactor that is documented as follow-up work.

Phase 28 cutover (2026-05-05, commit ``6feb361``) deleted the asyncpg
``dispatcher_loop`` and its per-row handler ``_handle_row``; in-app
message dispatch now goes through the Temporal
``DispatchMessageWorkflow`` (api_server/src/api_server/temporal/
workflows/dispatch_message.py). ``drive_dispatcher_once`` was
rewritten 2026-05-06 (D-30-DEF-01 follow-up) to drive the Phase 28
activities directly via ``temporalio.testing.ActivityEnvironment`` —
no real Temporal server, no mocks. Each activity runs its real body
against the real test infra (Postgres, Docker, OpenRouter) so the
gate's no-mocks invariant is preserved.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx


# ---------------------------------------------------------------------------
# Recipe placeholder rendering — replicates the runner-side gap inline so
# the e2e gate can light up real containers under their inapp shapes.
# ---------------------------------------------------------------------------


def render_placeholders(value: Any, mapping: dict[str, str]) -> Any:
    """Recursively substitute ``${VAR}`` and ``$VAR`` and ``{var}`` tokens.

    Mirrors what the production runner SHOULD do at deploy time when
    ``channel="inapp"`` is selected. Both the bash-style ``${VAR}`` /
    ``$VAR`` and the recipe-template ``{var}`` shapes are supported
    (the recipes mix both — e.g. heredoc bodies use ``${MODEL}`` while
    activation_env uses ``{agent_name}``).
    """
    if isinstance(value, str):
        out = value
        for k, v in mapping.items():
            out = out.replace(f"${{{k}}}", v).replace(f"${k}", v).replace(f"{{{k}}}", v)
        return out
    if isinstance(value, list):
        return [render_placeholders(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: render_placeholders(v, mapping) for k, v in value.items()}
    return value


def get_free_port() -> int:
    """Return a free TCP port the OS lets us bind+release immediately."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# ---------------------------------------------------------------------------
# Container plumbing — direct subprocess docker calls per Route B.
# ---------------------------------------------------------------------------


def docker_inspect_ip(container_id: str, network_name: str) -> str:
    """Return the container's IPv4 on the named docker network.

    Mirrors the production InappRecipeIndex.get_container_ip path. Raises
    RuntimeError if the IP isn't yet visible (cold-boot race) — caller
    can retry.
    """
    out = subprocess.run(
        ["docker", "inspect", container_id], capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"docker inspect failed: {out.stderr.strip()}")
    info = json.loads(out.stdout)[0]
    networks = info.get("NetworkSettings", {}).get("Networks") or {}
    net = networks.get(network_name) or {}
    ip = net.get("IPAddress") or ""
    if not ip:
        raise RuntimeError(
            f"container {container_id[:12]} has no IPAddress on network {network_name}"
        )
    return ip


def docker_logs(container_id: str, tail: int = 200) -> str:
    out = subprocess.run(
        ["docker", "logs", "--tail", str(tail), container_id],
        capture_output=True, text=True, check=False,
    )
    return (out.stdout or "") + "\n" + (out.stderr or "")


def docker_force_remove(container_id: str) -> None:
    subprocess.run(
        ["docker", "rm", "-f", container_id],
        capture_output=True, text=True, check=False,
    )


def wait_for_ready_log(
    container_id: str,
    ready_regex: str,
    timeout_s: float,
    poll_s: float = 1.0,
) -> tuple[bool, str]:
    """Poll ``docker logs`` until ready_regex matches or timeout. Returns (ok, last_logs).

    Also returns False early if the container exits before matching.
    """
    pattern = re.compile(ready_regex)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        logs = docker_logs(container_id, tail=400)
        if pattern.search(logs):
            return True, logs
        # Alive check
        st = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
            capture_output=True, text=True, check=False,
        )
        if (st.stdout or "").strip() != "true":
            return False, logs
        time.sleep(poll_s)
    return False, docker_logs(container_id, tail=400)


# ---------------------------------------------------------------------------
# DB seed — replicates what start_persistent + the dispatcher row JOIN need.
# ---------------------------------------------------------------------------


@dataclass
class SeededInappRow:
    user_id: UUID
    agent_id: UUID
    container_row_id: UUID
    container_id: str
    message_id: UUID


async def seed_inapp_message(
    pool: asyncpg.Pool,
    *,
    recipe_name: str,
    docker_container_id: str,
    inapp_auth_token: str | None,
    content: str,
    model: str = "anthropic/claude-haiku-4.5",
) -> SeededInappRow:
    """Insert users + agent_instances + agent_containers + inapp_messages.

    Mirrors what production code does (post-OAuth login + start_persistent +
    POST /v1/agents/:id/messages). We do it directly here because the
    runner-side wiring is incomplete (see Plan 15 SUMMARY for the gap).
    """
    user_id = uuid4()
    agent_id = uuid4()
    container_row_id = uuid4()
    name = f"e2e-{recipe_name}-{uuid4().hex[:6]}"

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            user_id, f"e2e-{recipe_name}",
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, $3, $4, $5)
            """,
            agent_id, user_id, recipe_name, model, name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status, container_id,
                 inapp_auth_token, ready_at, channel_type)
            VALUES ($1, $2, $3, $4, 'persistent', 'running', $5, $6, NOW(), 'inapp')
            """,
            container_row_id, agent_id, user_id, recipe_name,
            docker_container_id, inapp_auth_token,
        )
        message_id = await conn.fetchval(
            """
            INSERT INTO inapp_messages (agent_id, user_id, content)
            VALUES ($1, $2, $3) RETURNING id
            """,
            agent_id, user_id, content,
        )
    return SeededInappRow(
        user_id=user_id,
        agent_id=agent_id,
        container_row_id=container_row_id,
        container_id=docker_container_id,
        message_id=message_id,
    )


async def fetch_dispatcher_row(
    pool: asyncpg.Pool, message_id: UUID,
) -> asyncpg.Record:
    """Return the row exactly as ``fetch_pending_for_dispatch`` shapes it."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT m.id, m.agent_id, m.user_id, m.content, m.attempts,
                   c.id AS container_row_id, c.container_id, c.container_status,
                   c.ready_at, c.stopped_at, c.recipe_name, c.channel_type,
                   c.inapp_auth_token
            FROM inapp_messages m
            JOIN agent_containers c ON c.agent_instance_id = m.agent_id
            WHERE m.id=$1
            """,
            message_id,
        )
    assert row is not None, f"message {message_id} disappeared"
    return row


async def fetch_message_status(
    pool: asyncpg.Pool, message_id: UUID,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT status, last_error, bot_response, attempts, completed_at
            FROM inapp_messages WHERE id=$1
            """,
            message_id,
        )
    assert row is not None
    return dict(row)


async def fetch_inapp_auth_token(
    pool: asyncpg.Pool, container_row_id: UUID,
) -> str | None:
    """Phase 22c.3.1 Plan 01 Task 3 — read the per-session inapp_auth_token.

    The route handler does NOT return the token in the AgentStartResponse
    body (server-side only); the matrix test needs it for the dispatcher
    Bearer header. Direct PG read.
    """
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT inapp_auth_token FROM agent_containers WHERE id=$1",
            container_row_id,
        )


async def fetch_outbound_event(
    pool: asyncpg.Pool, container_row_id: UUID,
) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT seq, kind, payload, published, ts
            FROM agent_events
            WHERE agent_container_id=$1 AND kind='inapp_outbound'
            ORDER BY seq DESC
            LIMIT 1
            """,
            container_row_id,
        )
    if row is None:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {
        "seq": int(row["seq"]),
        "kind": row["kind"],
        "payload": payload,
        "published": bool(row["published"]),
        "ts": row["ts"],
    }


async def assert_status_transitions(
    pool: asyncpg.Pool,
    message_id: UUID,
    expected_terminal: str = "done",
) -> dict[str, Any]:
    """Verify the message reached the expected terminal state.

    The Plan 15 truths only require that ``inapp_messages.status`` reach
    'done' and that an inapp_outbound agent_events row exists for the
    same container_row_id. Intermediate state is implicit (the dispatcher
    persists 'forwarded' before the bot call).
    """
    final = await fetch_message_status(pool, message_id)
    assert final["status"] == expected_terminal, (
        f"expected status={expected_terminal}, got {final['status']!r}, "
        f"last_error={final.get('last_error')!r}"
    )
    if expected_terminal == "done":
        assert final.get("bot_response"), (
            f"expected non-empty bot_response, got {final.get('bot_response')!r}"
        )
    return final


# ---------------------------------------------------------------------------
# Contract sanity — direct unit-style reply parser mirroring dispatcher switch.
# ---------------------------------------------------------------------------


def parse_reply_per_contract(contract: str, raw_dispatcher_response: dict) -> str:
    """Mirror of dispatcher's contract switch — for sanity asserts in tests.

    The matrix test uses the dispatcher's REAL parser (via
    ``forward_to_agent`` activity, which delegates to
    ``services/inapp_dispatcher._dispatch_http_localhost``); this helper
    is exposed for direct-unit callers that want to verify a raw HTTP
    response against the contract before persisting.
    """
    if contract == "openai_compat":
        return raw_dispatcher_response["choices"][0]["message"]["content"]
    if contract == "a2a_jsonrpc":
        return raw_dispatcher_response["result"]["artifacts"][0]["parts"][0]["text"]
    if contract == "zeroclaw_native":
        return raw_dispatcher_response["response"]
    raise ValueError(f"unknown contract: {contract}")


# ---------------------------------------------------------------------------
# OpenRouter key — sourced from real env per Plan 15 truth #8 (D-32 path).
# ---------------------------------------------------------------------------


def load_openrouter_key_from_env_local() -> str | None:
    """Source OPENROUTER_API_KEY from environment or .env.local.

    Plan 15 says the key flows from the test user's OAuth-completed
    session row. In Route B we plumb that the same way: the test
    fixture inserts an oauth_sessions row carrying this value AND we
    inject it directly into the recipe container's activation_env. Both
    paths exercise the same upstream OpenRouter HTTP call.
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    # Best-effort fallback: read .env.local at the repo root.
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    env_local = os.path.join(repo_root, ".env.local")
    if os.path.exists(env_local):
        with open(env_local) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


# ---------------------------------------------------------------------------
# Inapp dispatch driver — Phase 28 activity-environment harness.
# ---------------------------------------------------------------------------
#
# Phase 28 cutover (commit ``6feb361``) deleted ``services/inapp_dispatcher::
# _handle_row`` and ``dispatcher_loop`` in favour of the Temporal
# ``DispatchMessageWorkflow``. ``drive_dispatcher_once`` rewritten 2026-05-06
# (D-30-DEF-01) to drive the same activities the workflow drives, in the
# same order, against the same real infra (asyncpg pool, httpx client,
# docker-aware recipe_index). No real Temporal server is needed — the
# ``temporalio.testing.ActivityEnvironment`` runner executes each activity
# body inline. Pattern lifted verbatim from
# ``tests/temporal/test_forward_to_agent_activity.py`` (the existing Phase
# 28 unit-test convention).
#
# Why this is faithful to the production workflow rather than a shortcut:
#
# - Each activity runs its REAL code (real recipe lookup, real container-IP
#   discovery, real bot HTTP, real ``_dispatch_http_localhost``, real
#   asyncpg writes, real atomic mark_done + agent_event dual-write).
# - Activity order matches ``DispatchMessageWorkflow.run`` step-for-step:
#   check_container_ready → forward_to_agent → record_usage (best-effort) →
#   emit_inapp_outbound (best-effort) → mark_message_done (load-bearing).
# - ApplicationError handling mirrors the workflow's
#   ``_classify_forward_failure`` minimally — pull ``.type`` off the
#   exception and route to ``mark_message_failed`` so the message row
#   transitions to a terminal state.
# - The activity-internal retry budgets (e.g. forward_to_agent's
#   ``[0,1s,2s,4s]`` transport-error loop) still fire because they live
#   INSIDE the activity body that ActivityEnvironment runs.
#
# Skipped vs. workflow:
#
# - debit_balance: D-22 no-op stub. Skipped here for noise; covered by
#   unit tests under tests/temporal/.
# - workflow-level retry policies: ActivityEnvironment.run executes each
#   body once. The workflow's outer ``maximum_attempts=5`` on
#   ``check_container_ready`` and ``mark_message_done`` is therefore not
#   reproduced — but those branches are exercised by the dedicated
#   activity tests, and the e2e gate's no-mocks invariant is what we're
#   protecting here, not retry semantics.


def _build_dispatch_input(row: asyncpg.Record, bot_timeout_seconds: float) -> Any:
    """Build the workflow input the activities expect (matches Plan 28-06 shape).

    The production route at ``routes/agent_messages.py:255-266`` builds
    exactly this dict — UUIDs stringified for Temporal JSON serialization
    safety. We use a ``SimpleNamespace`` so the activity bodies' attribute
    access (``inp.message_id`` etc.) works without needing to import the
    workflow's ``DispatchMessageInput`` dataclass (which would pull the
    workflow file's sandbox-pass-through machinery into the test).
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        message_id=str(row["id"]),
        user_id=str(row["user_id"]),
        agent_id=str(row["agent_id"]),
        container_row_id=str(row["container_row_id"]),
        container_id=row["container_id"],
        recipe_name=row["recipe_name"],
        # The dispatcher row JOIN doesn't carry the agent_instances.model
        # column. Read it lazily below if needed; for the matrix gate the
        # contract_model_name override on the recipe_index is what gets
        # used by the openai_compat adapter, so this field is mostly an
        # audit-trail column for record_usage.
        agent_model=row.get("agent_model") if isinstance(row, dict) else None,
        content=row["content"],
        inapp_auth_token=row["inapp_auth_token"],
        bot_timeout_seconds=bot_timeout_seconds,
    )


async def _fetch_agent_model(pool: asyncpg.Pool, agent_id: UUID) -> str | None:
    """Read agent_instances.model — the dispatcher JOIN doesn't carry it."""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT model FROM agent_instances WHERE id = $1", agent_id
        )


async def drive_dispatcher_once(
    pool: asyncpg.Pool,
    recipe_index: Any,
    message_id: UUID,
    bot_timeout_seconds: float = 600.0,
) -> None:
    """Drive a single in-app message through the Phase 28 activities.

    Mirrors ``DispatchMessageWorkflow.run`` step-for-step using
    ``temporalio.testing.ActivityEnvironment`` against the real test
    infra. No respx, no mocks. The bot HTTP client is a real
    ``httpx.AsyncClient``; activities resolve real container IPs via the
    supplied ``recipe_index`` and post to real recipe containers, which
    in turn call real OpenRouter upstream.

    The signature is preserved for caller compatibility with Plan 22c.3
    Plan 15 (the matrix test imports this function by name).
    """
    # Late imports: the activities pull asyncpg/httpx/docker; keeping
    # them function-local keeps the helpers' module surface narrow.
    from temporalio.exceptions import ApplicationError
    from temporalio.testing import ActivityEnvironment

    from api_server.temporal.activities.check_container_ready import (
        ReadinessActivities,
    )
    from api_server.temporal.activities.emit_inapp_outbound import (
        emit_inapp_outbound as emit_inapp_outbound_fn,
    )
    from api_server.temporal.activities.forward_to_agent import (
        ForwardActivities,
    )
    from api_server.temporal.activities.mark_message_done import MarkActivities
    from api_server.temporal.activities.mark_message_failed import (
        MarkFailedActivities,
    )
    from api_server.temporal.activities.record_usage import (
        RecordUsageActivities,
    )

    row = await fetch_dispatcher_row(pool, message_id)
    inp = _build_dispatch_input(row, bot_timeout_seconds)
    # asyncpg.Record exposes .get only on dicts; agent_model lives on
    # agent_instances, not on the dispatcher row, so resolve it now.
    if not getattr(inp, "agent_model", None):
        inp.agent_model = await _fetch_agent_model(pool, row["agent_id"])

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(bot_timeout_seconds, connect=5.0)
    ) as bot_http_client:
        readiness = ReadinessActivities(db_pool=pool)
        forward = ForwardActivities(
            db_pool=pool,
            bot_http_client=bot_http_client,
            recipe_index=recipe_index,
        )
        record = RecordUsageActivities(db_pool=pool)
        mark_done = MarkActivities(db_pool=pool)
        mark_failed = MarkFailedActivities(db_pool=pool)

        env = ActivityEnvironment()

        # ---- Step 1: readiness gate ----
        ready = await env.run(readiness.check_container_ready, inp)
        if not ready:
            await env.run(
                mark_failed.mark_message_failed,
                (inp.message_id, "container_not_ready"),
            )
            return

        # ---- Step 2: forward to agent (the bot HTTP call) ----
        try:
            forward_result = await env.run(forward.forward_to_agent, inp)
        except ApplicationError as e:
            error_type = getattr(e, "type", None) or (
                str(e.args[0]) if e.args else "internal_error"
            )
            await env.run(
                mark_failed.mark_message_failed,
                (inp.message_id, error_type),
            )
            return

        if not forward_result.reply or not forward_result.reply.strip():
            await env.run(
                mark_failed.mark_message_failed,
                (inp.message_id, "bot_empty"),
            )
            return

        # ---- Step 3a: record_usage (best-effort, matches workflow D-15) ----
        try:
            await env.run(record.record_usage, forward_result.usage_input)
        except Exception:  # noqa: BLE001 — best-effort per workflow contract
            pass

        # ---- Step 3c: emit_inapp_outbound (best-effort, no-op activity) ----
        # Skip Step 3b (debit_balance) — D-22 no-op stub, not load-bearing
        # for the e2e gate.
        try:
            await env.run(emit_inapp_outbound_fn, forward_result.event_input)
        except Exception:  # noqa: BLE001 — best-effort per workflow contract
            pass

        # ---- Step 3d: mark_message_done (load-bearing, D-10) ----
        # Failure here propagates: a stuck-forwarded row breaks the
        # gate's status='done' assertion, which is the right surface for
        # an operator to investigate.
        await env.run(mark_done.mark_message_done, forward_result.mark_done_input)


__all__ = [
    "render_placeholders",
    "get_free_port",
    "docker_inspect_ip",
    "docker_logs",
    "docker_force_remove",
    "wait_for_ready_log",
    "SeededInappRow",
    "seed_inapp_message",
    "fetch_dispatcher_row",
    "fetch_message_status",
    "fetch_inapp_auth_token",
    "fetch_outbound_event",
    "assert_status_transitions",
    "parse_reply_per_contract",
    "load_openrouter_key_from_env_local",
    "drive_dispatcher_once",
]
