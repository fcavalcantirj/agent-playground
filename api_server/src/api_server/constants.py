"""Process-wide constants shared across plans.

Phase 22c-06: ``ANONYMOUS_USER_ID`` has been removed. Every route now
resolves ``user_id`` from the authenticated session cookie via
``auth.deps.require_user`` (plan 22c-05); no single-tenant placeholder
constant remains. Deletion is the forcing function that turns any
residual reference into an ``ImportError`` (T-22c-20 mitigation).
"""
from __future__ import annotations

# Phase 22b-04: sysadmin bypass for event-stream auth (D-15).
# Per-laptop / per-deploy state — mirrors AP_CHANNEL_MASTER_KEY discipline.
# NEVER committed to .env* files. Route handler (Plan 22b-05) reads the
# VALUE at handler time via os.environ.get(AP_SYSADMIN_TOKEN_ENV).
AP_SYSADMIN_TOKEN_ENV = "AP_SYSADMIN_TOKEN"

__all__ = ["AP_SYSADMIN_TOKEN_ENV"]
