"""Canonical-email helper.

2026-05-17 — Bug #1 (account fragmentation). One human signing in via
Google, GitHub, and magic-link should produce ONE ``users`` row, not
three. The current `(provider, sub)`-only dedup is insufficient because:

  * GitHub returns whatever primary email the user set on GitHub. For
    Gmail addresses that's often the dot-free form (`abc@gmail.com`)
    even when Google + magic-link see the dotted form
    (`a.b.c@gmail.com`). Same inbox; different string.
  * Apple privacy-relay rotates a random `*@privaterelay.appleid.com`
    per sign-in attempt — never a stable proxy for the real human.

The fix has two parts:

  * **canonical_email(value)** (this file): collapse provider-specific
    representations into a single string.
      - Lowercase + strip.
      - For ``@gmail.com`` / ``@googlemail.com``: strip dots from the
        LOCAL part (`a.b@gmail.com` → `ab@gmail.com`). Gmail treats
        dots as cosmetic; no other major provider does, so the
        normalization is scoped to Gmail explicitly.
      - For ``@privaterelay.appleid.com``: return None — relay
        addresses are not stable identifiers; Apple sign-ins link
        only by `(provider, sub)` per Apple's design.
      - For everything else: return the lowercase+stripped form
        verbatim.

  * **users.canonical_email + user_identities** (migration 016): add
    a join table for (provider, sub) → user_id and a UNIQUE column
    for the canonicalized email, then rewrite ``upsert_user`` to
    link-or-create by canonical_email.

This module is the pure-function part — no DB, no async, no imports
beyond the stdlib. Tests at ``tests/auth/test_canonical.py``.
"""
from __future__ import annotations


_GMAIL_DOMAINS = ("gmail.com", "googlemail.com")
_PRIVACY_RELAY_DOMAIN = "privaterelay.appleid.com"


def canonical_email(value: str | None) -> str | None:
    """Return the canonical form of ``value`` for cross-provider dedup.

    Returns None for inputs that cannot serve as a stable per-human
    identifier (None / empty / Apple privacy-relay).

    The transform is idempotent — calling canonical_email on its own
    output yields the same string.
    """
    if value is None:
        return None
    stripped = value.strip().lower()
    if not stripped:
        return None
    # Apple's privacy relay rotates per-app; never a stable identifier.
    if stripped.endswith("@" + _PRIVACY_RELAY_DOMAIN):
        return None
    # Gmail-specific: collapse dots in the local part. Other providers
    # treat dots as significant — leave those alone.
    if "@" not in stripped:
        # Malformed email; pass through unchanged (the upsert layer
        # will refuse a non-@ string anyway, but we don't error here).
        return stripped
    local, _, domain = stripped.partition("@")
    if domain in _GMAIL_DOMAINS:
        local = local.replace(".", "")
        # Also strip the +tag suffix Gmail uses as a virtual address —
        # `a.b+work@gmail.com` and `ab@gmail.com` are the same inbox.
        local = local.split("+", 1)[0]
        domain = "gmail.com"  # also normalize googlemail.com → gmail.com
    return f"{local}@{domain}"


__all__ = ["canonical_email"]
