"""Pydantic shapes for ``GET /v1/agents`` — the logged user's agents.

Mirrors the ``agent_instances`` table after migration 002 plus a
LATERAL-joined ``last_verdict`` from the most recent linked run.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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
