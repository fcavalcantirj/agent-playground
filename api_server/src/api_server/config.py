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
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # --- Redis (Phase 22c.3) ---
    # Pub/Sub fan-out for inapp chat events (D-08 + D-11). Compose default
    # points at the ``redis`` service in deploy/docker-compose.prod.yml.
    # Tests override via monkeypatch.setenv("AP_REDIS_URL",
    # "redis://localhost:6379/0") to talk to the host-port mapping in
    # deploy/docker-compose.local.yml. The outbox pump publishes here;
    # the SSE handler subscribes here. Single source of env-driven config
    # for Redis client construction.
    redis_url: str = Field(
        "redis://redis:6379/0", validation_alias="AP_REDIS_URL"
    )

    # Phase 22c.3-09 follow-up: docker bridge network where the api_server
    # and the per-user agent containers share IPs. The InappRecipeIndex
    # needs the network name to look up a container's IP for HTTP dispatch
    # via NetworkSettings.Networks[<name>].IPAddress. Default matches the
    # compose project ``deploy`` (deploy_default). Tests can override via
    # AP_DOCKER_NETWORK to point at the testcontainer bridge.
    docker_network_name: str = Field(
        "deploy_default", validation_alias="AP_DOCKER_NETWORK"
    )

    # --- OAuth (Phase 22c) ---
    # Google OAuth2 (OIDC). Test-users mode in dev; confidential client creds
    # required in prod. Fail-loud happens in ``auth/oauth.py::get_oauth()`` —
    # Settings instantiation itself stays optional so dev boots without
    # credentials. Mirrors ``AP_CHANNEL_MASTER_KEY`` discipline
    # (``crypto/age_cipher.py::_master_key``).
    oauth_google_client_id: str | None = Field(
        None, validation_alias="AP_OAUTH_GOOGLE_CLIENT_ID"
    )
    oauth_google_client_secret: str | None = Field(
        None, validation_alias="AP_OAUTH_GOOGLE_CLIENT_SECRET"
    )
    oauth_google_redirect_uri: str | None = Field(
        None, validation_alias="AP_OAUTH_GOOGLE_REDIRECT_URI"
    )

    # GitHub OAuth (non-OIDC). Same discipline.
    oauth_github_client_id: str | None = Field(
        None, validation_alias="AP_OAUTH_GITHUB_CLIENT_ID"
    )
    oauth_github_client_secret: str | None = Field(
        None, validation_alias="AP_OAUTH_GITHUB_CLIENT_SECRET"
    )
    oauth_github_redirect_uri: str | None = Field(
        None, validation_alias="AP_OAUTH_GITHUB_REDIRECT_URI"
    )

    # Phase 23 (D-23): Mobile native-SDK Google sign-in client IDs.
    # Google Cloud Console issues SEPARATE client IDs per platform
    # (Android, iOS) — both are different from oauth_google_client_id
    # (the web client). The mobile JWT verifier accepts tokens whose
    # ``aud`` claim matches ANY entry in this list (verified by spike A1
    # — google.oauth2.id_token.verify_oauth2_token's ``audience``
    # parameter accepts list[str] and matches any element).
    # NOT a credential — these IDs ship in the mobile app binary and
    # are not secret. Default [] so dev boots without ops setup.
    # Env shape: AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS=android-id.apps...,ios-id.apps...
    # ``NoDecode`` annotation tells pydantic-settings NOT to JSON-decode
    # the env value as a complex type — our field_validator below does
    # the CSV split instead (pydantic-settings v2's default complex
    # decoding would JSON-parse the raw string and reject "a.com,b.com"
    # as invalid JSON).
    oauth_google_mobile_client_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias="AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS",
    )

    # Starlette SessionMiddleware signing secret (AMD-07).
    # Required in prod; dev uses a fixed fallback so local tests boot
    # without ops setup.
    oauth_state_secret: str | None = Field(
        None, validation_alias="AP_OAUTH_STATE_SECRET"
    )

    # Frontend origin for post-OAuth 302s (D-22c-FE-03 plan gap, smoke-surfaced).
    # The API issues RedirectResponse to /dashboard and /login?error=... after
    # the OAuth callback; those resolve against the request host (port 8000),
    # not the frontend (port 3000), unless we prefix with an absolute URL.
    frontend_base_url: str = Field(
        "http://localhost:3000", validation_alias="AP_FRONTEND_BASE_URL"
    )

    # Phase 23 (D-23): CSV → list[str] pre-validator for mobile client IDs.
    # pydantic-settings v2's CSV detection is library-version-dependent;
    # this validator guarantees correct parsing regardless. Idempotent for
    # programmatic list inputs (Settings(oauth_google_mobile_client_ids=[...])
    # in tests).
    @field_validator("oauth_google_mobile_client_ids", mode="before")
    @classmethod
    def _split_mobile_client_ids_csv(cls, v):
        """Parse comma-separated string into list[str]; idempotent for
        list inputs; trims whitespace and drops empty entries."""
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v


def get_settings() -> Settings:
    """Return a fresh Settings snapshot from the current environment."""
    return Settings()
