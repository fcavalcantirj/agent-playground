"""Pydantic response models for user-scoped routes (Phase 22c).

Mirrors ``frontend/lib/api.ts::SessionUser`` so the frontend's existing
type surface can consume ``GET /v1/users/me`` without a type change
(D-22c-MIG-01: ``display_name`` is the column-authoritative name — no
separate ``users.name`` column was added).
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SessionUserResponse(BaseModel):
    """Shape returned by ``GET /v1/users/me``.

    Matches ``frontend/lib/api.ts::SessionUser`` (``id``, ``email?``,
    ``display_name``, ``avatar_url?``, ``provider?``) plus ``created_at``
    for parity with the users table row — the dashboard layout can show
    "member since" without a second round-trip.

    ``from_attributes=True`` lets routes construct the model from an
    asyncpg ``Record`` via ``**dict(row)``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None = None
    display_name: str
    avatar_url: str | None = None
    provider: str | None = None
    created_at: datetime
