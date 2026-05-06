"""Phase 28 Plan 28-07 Task 3 — POST /messages route-level Temporal integration.

Per Plan 28-07 frontmatter (must_have truths line for this file):

  tests/temporal/test_route_starts_workflow.py covers: POST /messages
  returns 202; ``app.state.temporal_client.start_workflow`` was called
  with ``id=msg-{user_id}-{message_id}`` (user-scoped per D-08);
  WorkflowAlreadyStartedError → still 202.

This test sits at the ROUTE layer — it exercises the start_workflow
call wiring and the workflow-id format, NOT the workflow body. The
workflow body has dedicated coverage in
``tests/temporal/test_dispatch_message_workflow.py`` (Task 1 of this
same plan, which uses a real ``WorkflowEnvironment.start_time_skipping``).

Why an ``AsyncMock`` for ``app.state.temporal_client`` is acceptable
HERE (and not a CLAUDE.md Golden Rule #1 violation):

* The real Temporal client is a thick gRPC consumer; its end-to-end
  contract is already covered by Task 1's WorkflowEnvironment-backed
  workflow tests (real Temporal Server). The thing this test exists
  to lock in is the route's CALL SHAPE: which args/kwargs flow into
  ``start_workflow``, and the route's behavior when the SDK raises
  ``WorkflowAlreadyStartedError``. Asserting against an ``AsyncMock``
  is the smallest test surface that proves both — booting another
  WorkflowEnvironment per-test here would multiply test wall time
  with no signal gain over Task 1.
* Postgres remains real (testcontainers) per the rest of the route
  test suite — the route's DB writes (insert_pending +
  set_workflow_id) are exercised end-to-end against migrated PG.

Coverage matrix (3 tests):

  * ``test_post_message_starts_workflow_with_user_scoped_id``
      Asserts ``id=msg-{user_id}-{message_id}`` (D-08 revised).
  * ``test_post_message_workflow_already_started_returns_202``
      Asserts WorkflowAlreadyStartedError side-effect → still 202
      (preserves Idempotency-Key replay semantics).
  * ``test_post_message_passes_dispatch_input_fields``
      Asserts the DispatchMessageInput dataclass fields are populated
      from the right request + DB sources (content, container_id,
      recipe_name, etc.).
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from temporalio.exceptions import WorkflowAlreadyStartedError

from api_server.temporal.workflows.dispatch_message import (
    DispatchMessageInput,
    DispatchMessageWorkflow,
)


pytestmark = [pytest.mark.api_integration]


async def _seed_agent_with_container(
    pool, user_id: str, *, recipe_name: str | None = None,
    model: str = "anthropic/claude-3.5-sonnet",
    inapp_auth_token: str | None = None,
) -> tuple[UUID, str, str]:
    """Seed an agent_instance + a running agent_container row.

    Returns ``(agent_id, container_id_str, recipe_name_str)`` so the
    test can later assert the workflow input picked them up.
    """
    agent_id = uuid4()
    container_row_id = uuid4()
    docker_container_id = f"deadbeef{uuid4().hex[:24]}"
    recipe_name = recipe_name or f"recipe-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, $3, $4, $5)
            """,
            agent_id, UUID(user_id), recipe_name, model, name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status, container_id,
                 inapp_auth_token, ready_at)
            VALUES ($1, $2, $3, $4, 'persistent', 'running', $5, $6, NOW())
            """,
            container_row_id, agent_id, UUID(user_id), recipe_name,
            docker_container_id, inapp_auth_token,
        )
    return agent_id, docker_container_id, recipe_name


async def test_post_message_starts_workflow_with_user_scoped_id(
    async_client_no_temporal, db_pool, authenticated_cookie,
):
    """D-08 revised — workflow id is ``msg-{user_id}-{message_id}``.

    The route MUST call ``temporal_client.start_workflow`` with this
    user-scoped id so Temporal UI search ``msg-{user_id}-*`` lists every
    workflow for that user (defense-in-depth against cross-user
    mis-dispatch).
    """
    user_id = authenticated_cookie["_user_id"]
    agent_id, _container_id, _recipe = await _seed_agent_with_container(
        db_pool, user_id,
    )

    fake_temporal = AsyncMock()
    async_client_no_temporal._app.state.temporal_client = fake_temporal  # type: ignore[attr-defined]

    r = await async_client_no_temporal.post(
        f"/v1/agents/{agent_id}/messages",
        headers={
            "Cookie": authenticated_cookie["Cookie"],
            "Idempotency-Key": str(uuid4()),
        },
        json={"content": "hi"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    message_id = body["message_id"]

    fake_temporal.start_workflow.assert_called_once()
    args, kwargs = fake_temporal.start_workflow.call_args
    # D-08 revised: ``msg-{user_id}-{message_id}``.
    assert kwargs["id"] == f"msg-{user_id}-{message_id}", (
        f"workflow id format violates D-08: got {kwargs['id']!r}"
    )
    # Also positional first arg is the workflow.run reference.
    assert args[0] is DispatchMessageWorkflow.run


async def test_post_message_workflow_already_started_returns_202(
    async_client_no_temporal, db_pool, authenticated_cookie,
):
    """``WorkflowAlreadyStartedError`` from the SDK MUST surface as 202.

    REJECT_DUPLICATE policy is in force; same-Idempotency-Key replays
    that bypass the request-layer middleware (e.g. middleware cache
    eviction) must still receive a stable 202 — NOT a 500. Preserves
    the fast-ack contract for retried clients.
    """
    user_id = authenticated_cookie["_user_id"]
    agent_id, _container_id, _recipe = await _seed_agent_with_container(
        db_pool, user_id,
    )

    fake_temporal = AsyncMock()
    fake_temporal.start_workflow.side_effect = WorkflowAlreadyStartedError(
        workflow_id="msg-dup", workflow_type="DispatchMessageWorkflow",
    )
    async_client_no_temporal._app.state.temporal_client = fake_temporal  # type: ignore[attr-defined]

    r = await async_client_no_temporal.post(
        f"/v1/agents/{agent_id}/messages",
        headers={
            "Cookie": authenticated_cookie["Cookie"],
            "Idempotency-Key": str(uuid4()),
        },
        json={"content": "hi"},
    )
    assert r.status_code == 202, r.text  # NOT 500 — replay path
    body = r.json()
    assert body["status"] == "pending"
    # The route still inserted the inapp_messages row and attempted the
    # workflow start before the SDK raised — call_count is 1.
    assert fake_temporal.start_workflow.call_count == 1


async def test_post_message_passes_dispatch_input_fields(
    async_client_no_temporal, db_pool, authenticated_cookie,
):
    """The DispatchMessageInput carried by start_workflow has the right shape.

    Locks in the route → workflow input contract: content, container_id,
    recipe_name, agent_model, inapp_auth_token are all populated from
    the request + DB, and the message_id matches the body's
    ``message_id`` (so the workflow correlates back to the row).
    """
    user_id = authenticated_cookie["_user_id"]
    agent_id, container_id, recipe_name = await _seed_agent_with_container(
        db_pool, user_id,
        recipe_name="hermes-route-test",
        model="anthropic/claude-3.5-sonnet",
        inapp_auth_token="tok-deadbeef",
    )

    fake_temporal = AsyncMock()
    async_client_no_temporal._app.state.temporal_client = fake_temporal  # type: ignore[attr-defined]

    r = await async_client_no_temporal.post(
        f"/v1/agents/{agent_id}/messages",
        headers={
            "Cookie": authenticated_cookie["Cookie"],
            "Idempotency-Key": str(uuid4()),
        },
        json={"content": "hello-shape-test"},
    )
    assert r.status_code == 202, r.text
    message_id = r.json()["message_id"]

    fake_temporal.start_workflow.assert_called_once()
    args, kwargs = fake_temporal.start_workflow.call_args
    # The route calls: start_workflow(WF.run, DispatchMessageInput(...), id=..., task_queue=..., ...)
    # → args[0] is the workflow.run reference, args[1] is the input dataclass.
    assert len(args) >= 2, (
        "expected positional (workflow.run, DispatchMessageInput, ...); "
        f"got args={args!r}"
    )
    inp = args[1]
    assert isinstance(inp, DispatchMessageInput), (
        f"second positional must be DispatchMessageInput, got {type(inp)!r}"
    )
    assert inp.message_id == message_id
    assert inp.user_id == user_id
    assert inp.agent_id == str(agent_id)
    assert inp.container_id == container_id
    assert inp.recipe_name == recipe_name
    assert inp.agent_model == "anthropic/claude-3.5-sonnet"
    assert inp.content == "hello-shape-test"
    assert inp.inapp_auth_token == "tok-deadbeef"
    # bot_timeout_seconds comes from settings; just assert positive.
    assert inp.bot_timeout_seconds > 0
    # task_queue + execution_timeout sealed at start time per D-13.
    assert "task_queue" in kwargs
    assert "execution_timeout" in kwargs
