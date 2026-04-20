"""``GET /v1/agents`` — list the logged user's deployed agents.

Phase 22c (plan 22c-06): protected by ``require_user``. The session cookie
is resolved by ``SessionMiddleware`` (plan 22c-04) into
``request.state.user_id``; ``require_user`` returns a 401 ``JSONResponse``
inline when the cookie is missing / expired / revoked, otherwise it
returns the authenticated ``UUID`` which is passed straight into
``list_agents`` as the WHERE-clause predicate (defense-in-depth cross-user
isolation — see ``services/run_store.py::list_agents``).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth.deps import require_user
from ..models.agents import AgentListResponse, AgentSummary
from ..services.run_store import list_agents

router = APIRouter()


@router.get("/agents", response_model=AgentListResponse)
async def list_user_agents(request: Request):
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        rows = await list_agents(conn, user_id)
    return AgentListResponse(agents=[AgentSummary(**r) for r in rows])
