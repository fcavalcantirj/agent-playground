"""Phase 27 — read-side endpoints for BYOK usage visibility.

Two endpoints:

  GET /v1/usage/summary
    Powers the AppBar USD ticker (mobile + web). Returns total USD +
    message count + per-agent breakdown. Hot path — fires on every
    screen mount; the user-ticker index is set up for index-only scan.

  GET /v1/agents/:agent_id/usage
    Powers the per-agent breakdown screen. Returns cumulative aggregates
    + last 7d daily series + last 30d daily series. Pattern A ownership
    check (``WHERE id=$1 AND user_id=$2``) so a 404 hides the
    "doesn't-exist vs not-yours" distinction.

Per CLAUDE.md golden rule #2 (strengthened 2026-05-04 — applies to EVERY
client): all aggregation is server-side. Mobile/web/CLI clients receive
ready-to-render JSON and `setState` it directly. NO client-side SUM,
NO client-side GROUP BY, NO client-side cost-rate lookup.

USD values are returned as **strings** (D-14) — Pydantic with
``cost_usd: str`` field types coerces ``Decimal`` to JSON string
automatically, avoiding float precision loss across language
boundaries (Dart's double, JS Number).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth.deps import require_user
from ..models.errors import ErrorCode, make_error_envelope
from ..services import usage_query


_log = logging.getLogger("api_server.usage")
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class AgentBreakdownEntry(BaseModel):
    """One row in /v1/usage/summary.by_agent."""

    agent_id: UUID
    agent_name: str
    recipe_name: str
    model: str
    cost_usd: str
    message_count: int
    last_activity: datetime | None


class UsageSummaryResponse(BaseModel):
    """Body for GET /v1/usage/summary — the AppBar ticker payload."""

    total_usd: str
    message_count: int
    by_agent: list[AgentBreakdownEntry]


class AgentCumulative(BaseModel):
    """Cumulative aggregates for /v1/agents/:id/usage."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: str
    message_count: int
    last_activity: datetime | None


class AgentSeriesEntry(BaseModel):
    """One day-bucket in series_7d / series_30d. ``day`` is UTC."""

    day: date
    cost_usd: str
    tokens: int
    message_count: int


class AgentUsageResponse(BaseModel):
    """Body for GET /v1/agents/:agent_id/usage — the per-agent screen."""

    agent_id: UUID
    cumulative: AgentCumulative
    series_7d: list[AgentSeriesEntry]
    series_30d: list[AgentSeriesEntry]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _err(
    status: int,
    code: str,
    message: str,
    *,
    param: str | None = None,
    category: str | None = None,
) -> JSONResponse:
    """Mirror runs.py::_err — single source of truth for the envelope."""
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(
            code, message, param=param, category=category
        ),
    )


def _decimal_to_str(value: Decimal | int | None) -> str:
    """Coerce DB-returned NUMERIC / int / None to a JSON-stable string.

    Empty-state aggregate paths return ``Decimal('0')``; older asyncpg
    occasionally surfaces aggregate sums as int (the integer 0) before
    a NUMERIC cast lands. The route normalizes both shapes to ``"0"``.
    """
    if value is None:
        return "0"
    return str(value)


def _project_breakdown(row: dict[str, Any]) -> AgentBreakdownEntry:
    return AgentBreakdownEntry(
        agent_id=row["agent_id"],
        agent_name=row["agent_name"],
        recipe_name=row["recipe_name"],
        model=row["model"],
        cost_usd=_decimal_to_str(row["cost_usd"]),
        message_count=row["message_count"],
        last_activity=row["last_activity"],
    )


def _project_series(row: dict[str, Any]) -> AgentSeriesEntry:
    return AgentSeriesEntry(
        day=row["day"],
        cost_usd=_decimal_to_str(row["cost_usd"]),
        tokens=row["tokens"],
        message_count=row["message_count"],
    )


# ---------------------------------------------------------------------------
# GET /v1/usage/summary
# ---------------------------------------------------------------------------


@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(request: Request):
    """Return total USD + message count + per-agent breakdown for the user."""
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        total_usd, message_count = await usage_query.fetch_user_total(conn, user_id)
        by_agent_rows = await usage_query.fetch_user_by_agent(conn, user_id)

    return UsageSummaryResponse(
        total_usd=_decimal_to_str(total_usd),
        message_count=message_count,
        by_agent=[_project_breakdown(r) for r in by_agent_rows],
    )


# ---------------------------------------------------------------------------
# GET /v1/agents/:agent_id/usage
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}/usage", response_model=AgentUsageResponse)
async def get_agent_usage(agent_id: UUID, request: Request):
    """Return cumulative + 7d + 30d series for one agent owned by the user."""
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        # Pattern A — single round-trip ownership check; 404 hides
        # "exists vs yours" so cross-tenant probing leaks nothing.
        owns = await conn.fetchval(
            "SELECT 1 FROM agent_instances WHERE id = $1 AND user_id = $2",
            agent_id, user_id,
        )
        if owns is None:
            return _err(
                404,
                ErrorCode.AGENT_NOT_FOUND,
                f"agent {agent_id} not found",
                param="agent_id",
            )

        cumulative_row = await usage_query.fetch_agent_cumulative(conn, agent_id)
        series_7d_rows = await usage_query.fetch_agent_series(conn, agent_id, days=7)
        series_30d_rows = await usage_query.fetch_agent_series(conn, agent_id, days=30)

    return AgentUsageResponse(
        agent_id=agent_id,
        cumulative=AgentCumulative(
            input_tokens=cumulative_row["input_tokens"],
            output_tokens=cumulative_row["output_tokens"],
            cache_read_tokens=cumulative_row["cache_read_tokens"],
            cache_creation_tokens=cumulative_row["cache_creation_tokens"],
            cost_usd=_decimal_to_str(cumulative_row["cost_usd"]),
            message_count=cumulative_row["message_count"],
            last_activity=cumulative_row["last_activity"],
        ),
        series_7d=[_project_series(r) for r in series_7d_rows],
        series_30d=[_project_series(r) for r in series_30d_rows],
    )


__all__ = ["router"]
