"""Phase 22-02 — channel credential encryption.

Minimal package marker. Public API lives in ``age_cipher``.
"""
from __future__ import annotations

from .age_cipher import decrypt_channel_config, encrypt_channel_config

__all__ = ["encrypt_channel_config", "decrypt_channel_config"]
