"""Pydantic models + ``Category`` enum for ``/v1/runs`` endpoints.

The ``Category`` enum is a VERBATIM mirror of ``tools/run_recipe.py`` lines
66-86. Any drift between the server's category values and the runner's
would silently break clients that rely on ``error.category`` mapping —
this file is the single source of truth on the API side and MUST match
``run_recipe.Category`` byte-for-byte.

Downstream:

- Plan 19-05 imports ``Category`` to mirror runner categories into error
  envelopes (e.g. ``RUNNER_TIMEOUT`` error carries ``category=TIMEOUT``).
- Plan 20 (frontend) consumes the OpenAPI schema produced by
  ``RunResponse`` — ``category`` is typed as ``str`` intentionally so the
  set of live + reserved values stays extensible as new verdict categories
  are added in future phases (Phase 15 ``STOCHASTIC``, etc.).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Category(str, Enum):
    """Phase 10 verdict category enum — verbatim mirror of ``run_recipe.Category``.

    Subclasses ``str`` (not ``enum.StrEnum``) so members auto-coerce to
    strings during JSON emission on Python 3.10+.
    """

    # Live (9) — the runner will emit exactly one of these per run.
    PASS = "PASS"
    ASSERT_FAIL = "ASSERT_FAIL"
    INVOKE_FAIL = "INVOKE_FAIL"
    BUILD_FAIL = "BUILD_FAIL"
    PULL_FAIL = "PULL_FAIL"
    CLONE_FAIL = "CLONE_FAIL"
    TIMEOUT = "TIMEOUT"
    LINT_FAIL = "LINT_FAIL"
    INFRA_FAIL = "INFRA_FAIL"
    # Reserved (2) — schema enum only; runner never emits these in Phase 10.
    STOCHASTIC = "STOCHASTIC"   # reserved — Phase 15 (multi-run determinism)
    SKIP = "SKIP"               # reserved — later UX phase (known_incompatible SKIP)


class RunRequest(BaseModel):
    """Request body for ``POST /v1/runs``.

    ``extra="forbid"`` rejects inline recipe YAML + any other unknown field
    at schema-parse time (V5 input validation + CONTEXT.md D-07 "no inline
    recipe YAML accepted"). ``recipe_name`` pattern rejects SQL-injection
    and path-traversal shapes before the route handler sees them.
    """

    model_config = ConfigDict(extra="forbid")

    recipe_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        # Recipe filenames are lowercase with hyphens/underscores;
        # anything else is almost certainly hostile input.
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    prompt: str | None = Field(None, max_length=16384)
    model: str = Field(..., min_length=1, max_length=128)
    no_lint: bool = False
    no_cache: bool = False
    metadata: dict[str, Any] | None = None


class RunResponse(BaseModel):
    """Response body for a single run — straight passthrough of the runner's
    ``details`` dict plus the two IDs the route handler mints + two timestamps.

    Field names mirror ``run_cell()``'s ``details`` dict exactly (per
    PATTERNS.md §runner_bridge) so frontend type-gen against OpenAPI stays
    stable across plans.
    """

    run_id: str
    agent_instance_id: str
    recipe: str
    model: str
    prompt: str
    pass_if: str | None = None
    verdict: str
    category: str
    detail: str | None = None
    exit_code: int | None = None
    wall_time_s: float | None = None
    filtered_payload: str | None = None
    stderr_tail: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class RunGetResponse(RunResponse):
    """Response body for ``GET /v1/runs/{id}`` — identical shape to ``RunResponse``.

    A separate class is kept so if/when the GET path grows extra fields
    (pagination, related events, etc.) it stays independent of POST.
    """

    pass
