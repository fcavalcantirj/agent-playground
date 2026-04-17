"""Runtime settings via ``pydantic-settings``.

Loaded from environment on each ``get_settings()`` call. ``AP_ENV`` gates
``/docs`` exposure (D-10 — only on in dev). ``AP_MAX_CONCURRENT_RUNS`` bounds
the per-app ``asyncio.Semaphore`` created by ``main.create_app``'s lifespan.

Env variables:

- ``DATABASE_URL`` (no ``AP_`` prefix — industry convention)
- ``AP_ENV`` = ``dev`` | ``prod``  (default ``dev``)
- ``AP_MAX_CONCURRENT_RUNS`` = int (default 2)
- ``AP_RECIPES_DIR`` = path (default ``recipes``)
- ``AP_TRUSTED_PROXY`` = bool (default False — when True, trust
  ``X-Forwarded-For``; Caddy sits in front in prod)

No dotenv magic. Compose / systemd / the deploy shim is the single source
of env truth.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,       # compose-provided env only; no dotenv magic
        extra="ignore",
        case_sensitive=False,
    )

    # Not AP_ prefixed — industry convention.
    database_url: str = Field(..., validation_alias="DATABASE_URL")

    # AP_-prefixed knobs.
    env: Literal["dev", "prod"] = Field("dev", validation_alias="AP_ENV")
    max_concurrent_runs: int = Field(
        2, validation_alias="AP_MAX_CONCURRENT_RUNS"
    )
    recipes_dir: Path = Field(
        Path("recipes"), validation_alias="AP_RECIPES_DIR"
    )
    # When True, trust X-Forwarded-For (Caddy is in front). Default False
    # for safety — set True only when the deploy topology makes sense.
    trusted_proxy: bool = Field(
        False, validation_alias="AP_TRUSTED_PROXY"
    )


def get_settings() -> Settings:
    """Return a fresh Settings snapshot from the current environment."""
    return Settings()
