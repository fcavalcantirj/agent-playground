"""``GET /v1/agents`` — list the logged user's deployed agents.

Phase 20 surface. Phase 19's auth model still resolves to a single
``ANONYMOUS_USER_ID`` (Phase 21+ wires real session resolution); the route
already calls ``ANONYMOUS_USER_ID`` so when sessions land later, only the
resolution helper changes — the query stays valid.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..constants import ANONYMOUS_USER_ID
from ..models.agents import AgentListResponse, AgentSummary
from ..services.run_store import list_agents

router = APIRouter()


@router.get("/agents", response_model=AgentListResponse)
async def list_user_agents(request: Request) -> AgentListResponse:
    pool = request.app.state.db
    async with pool.acquire() as conn:
        rows = await list_agents(conn, ANONYMOUS_USER_ID)
    return AgentListResponse(agents=[AgentSummary(**r) for r in rows])
