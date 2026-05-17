"""2026-05-17 — Bug #1: canonical_email helper tests.

Pure-function tests for the dot-collapse + privacy-relay-nullify
transform. No DB, no async, no fixtures.
"""
from __future__ import annotations

import pytest

from api_server.auth.canonical import canonical_email


# --- Gmail-specific dot-collapse -----------------------------------------


def test_gmail_dot_collapse():
    """Gmail treats dots in the local part as cosmetic."""
    assert canonical_email("a.b.c@gmail.com") == "abc@gmail.com"


def test_gmail_no_dots_unchanged():
    assert canonical_email("abc@gmail.com") == "abc@gmail.com"


def test_gmail_uppercase_normalized():
    assert canonical_email("Abc@Gmail.com") == "abc@gmail.com"


def test_gmail_whitespace_stripped():
    assert canonical_email("  abc@gmail.com  ") == "abc@gmail.com"


def test_gmail_plus_suffix_stripped():
    """`+tag` is a virtual address that maps to the bare local part."""
    assert canonical_email("a.b+work@gmail.com") == "ab@gmail.com"
    assert canonical_email("user+anything@gmail.com") == "user@gmail.com"


def test_googlemail_collapses_to_gmail():
    """`googlemail.com` is Gmail's secondary domain (UK/DE) — same inbox."""
    assert canonical_email("a.b@googlemail.com") == "ab@gmail.com"


# --- Non-Gmail providers preserve dots ------------------------------------


def test_outlook_dots_preserved():
    """outlook.com treats dots as significant — DO NOT strip."""
    assert canonical_email("a.b@outlook.com") == "a.b@outlook.com"


def test_proton_dots_preserved():
    assert canonical_email("a.b@proton.me") == "a.b@proton.me"


def test_custom_domain_dots_preserved():
    """Self-hosted / company domains may treat dots as significant."""
    assert canonical_email("first.last@solvr.dev") == "first.last@solvr.dev"


# --- Apple privacy relay returns None -------------------------------------


def test_apple_privacy_relay_returns_none():
    """Relay addresses rotate per app — never a stable human identifier."""
    assert canonical_email("abc123@privaterelay.appleid.com") is None
    assert canonical_email("XYZ@privaterelay.appleid.com") is None


def test_apple_privacy_relay_case_insensitive():
    assert canonical_email("abc@PRIVATERELAY.appleid.com") is None


# --- Edge cases -----------------------------------------------------------


def test_none_returns_none():
    assert canonical_email(None) is None


def test_empty_string_returns_none():
    assert canonical_email("") is None


def test_only_whitespace_returns_none():
    assert canonical_email("   ") is None


def test_malformed_no_at_passes_through():
    """Defensive: no `@` → pass through lowercased. Upsert layer
    will reject it but the canonicalizer is non-error."""
    assert canonical_email("not-an-email") == "not-an-email"


def test_idempotent():
    """canonical_email(canonical_email(x)) == canonical_email(x)."""
    for v in [
        "a.b.c@gmail.com",
        "a.b+work@gmail.com",
        "a.b@googlemail.com",
        "a.b@outlook.com",
        "First.Last@Solvr.Dev",
    ]:
        once = canonical_email(v)
        twice = canonical_email(once)
        assert once == twice, f"not idempotent: {v!r} → {once!r} → {twice!r}"


def test_specific_real_user_case():
    """The bug-driving real case from prod 2026-05-17:
    felipe.cavalcanti.rj@gmail.com (Google + magic-link) AND
    felipecavalcantirj@gmail.com (GitHub) are the same Gmail inbox.
    canonical_email must collapse both to the same string."""
    a = canonical_email("felipe.cavalcanti.rj@gmail.com")
    b = canonical_email("felipecavalcantirj@gmail.com")
    assert a == b == "felipecavalcantirj@gmail.com"
