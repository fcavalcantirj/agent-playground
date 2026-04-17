"""ULID helpers — thin wrapper over ``python-ulid`` for consistency.

Provides a single import path for ``new_run_id()`` and ``is_valid_ulid(s)``
so Plan 19-04's route handler and any future caller can mint / validate
ULIDs without duplicating the Crockford base32 regex.

Why ULIDs (not UUIDs) for ``runs.id``: time-sortable 26-char strings make
``SELECT * FROM runs ORDER BY id DESC`` cheap + deterministic without a
secondary timestamp index. See CONTEXT.md D-06 (runs.id TEXT, ULID-shaped).
"""
from __future__ import annotations

import re

from ulid import ULID

# Crockford base32 alphabet: 0-9 + A-Z minus I, L, O, U (26 chars, case-insensitive).
_CROCKFORD = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def new_run_id() -> str:
    """Return a freshly-minted 26-character Crockford base32 ULID string."""
    return str(ULID())


def is_valid_ulid(s: str) -> bool:
    """Return True iff ``s`` is a 26-char Crockford base32 ULID string.

    Robust to case (ULIDs are case-insensitive by spec); rejects any
    non-string input or wrong length without throwing.
    """
    if not isinstance(s, str) or len(s) != 26:
        return False
    return bool(_CROCKFORD.match(s.upper()))
