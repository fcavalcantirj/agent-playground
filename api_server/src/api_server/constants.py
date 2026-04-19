"""Process-wide constants shared across plans.

Defining ``ANONYMOUS_USER_ID`` here (instead of in ``services/run_store.py``
or elsewhere) gives Plans 04 and 05 a common import source, so they can both
run in Wave 3 without touching each other's files. This is the
file-ownership contract that unblocks Wave 3 parallelism.

The literal UUID matches the row seeded by ``alembic/versions/001_baseline.py``
— changing one without the other breaks foreign-key resolution on every
inbound request.
"""
from __future__ import annotations

from uuid import UUID

ANONYMOUS_USER_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")

# Phase 22b-04: sysadmin bypass for event-stream auth (D-15).
# Per-laptop / per-deploy state — mirrors AP_CHANNEL_MASTER_KEY discipline.
# NEVER committed to .env* files. Route handler (Plan 22b-05) reads the
# VALUE at handler time via os.environ.get(AP_SYSADMIN_TOKEN_ENV).
AP_SYSADMIN_TOKEN_ENV = "AP_SYSADMIN_TOKEN"

__all__ = ["ANONYMOUS_USER_ID", "AP_SYSADMIN_TOKEN_ENV"]
