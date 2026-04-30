"""Phase 22c.3 — verify Settings.redis_url resolves AP_REDIS_URL env var.

Pure unit test (no DB, no network, no FastAPI app) — runs in the DEFAULT
pytest invocation (no ``api_integration`` marker). Mirrors the structure of
``tests/config/test_oauth_state_secret_fail_loud.py``.

D-08 + D-11 wire-up: Settings.redis_url is the single source of env-driven
config for the Redis client construction performed in subsequent waves
(outbox pump publishes; SSE handler subscribes).

Defaults to the compose-network hostname (``redis://redis:6379/0``); host-
venv test fixtures override via ``monkeypatch.setenv("AP_REDIS_URL", ...)``
to point at the host-port mapping in ``deploy/docker-compose.local.yml``.
"""
from __future__ import annotations

import pytest

from api_server.config import Settings


def test_redis_url_default(monkeypatch):
    """No AP_REDIS_URL env → Settings.redis_url == compose default."""
    monkeypatch.delenv("AP_REDIS_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    s = Settings()
    assert s.redis_url == "redis://redis:6379/0"


def test_redis_url_env_override(monkeypatch):
    """AP_REDIS_URL set → Settings.redis_url resolves from env."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("AP_REDIS_URL", "redis://localhost:6379/9")
    s = Settings()
    assert s.redis_url == "redis://localhost:6379/9"


def test_redis_url_alias_case_insensitive(monkeypatch):
    """Lowercase ap_redis_url resolves too (Settings has case_sensitive=False)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.delenv("AP_REDIS_URL", raising=False)
    monkeypatch.setenv("ap_redis_url", "redis://lowercase:6379/0")
    s = Settings()
    assert s.redis_url == "redis://lowercase:6379/0"
