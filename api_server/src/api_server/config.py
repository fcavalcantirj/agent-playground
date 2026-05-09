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

import logging
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_log = logging.getLogger("api_server.config")

# Phase B Plan B-stripe-02 — Stripe placeholder values for AP_ENV=dev. Mirror
# the OAuth ``oauth_X missing in dev; using placeholder`` discipline so a
# fresh local checkout boots without ops setup; prod fail-loud below.
_STRIPE_DEV_PLACEHOLDERS: dict[str, str] = {
    "stripe_api_key":             "sk_test_DEV_PLACEHOLDER",
    "stripe_webhook_secret":      "whsec_DEV_PLACEHOLDER",
    "stripe_price_id_pro_monthly": "price_DEV_PLACEHOLDER_pro_monthly",
    "stripe_price_id_pack_5":      "price_DEV_PLACEHOLDER_pack_5",
    "stripe_price_id_pack_10":     "price_DEV_PLACEHOLDER_pack_10",
    "stripe_price_id_pack_25":     "price_DEV_PLACEHOLDER_pack_25",
    "stripe_price_id_pack_50":     "price_DEV_PLACEHOLDER_pack_50",
    "stripe_price_id_pack_100":    "price_DEV_PLACEHOLDER_pack_100",
}
# Map field name → AP_STRIPE_* env-var alias for the prod fail-loud message.
_STRIPE_FIELD_TO_ENV_ALIAS: dict[str, str] = {
    "stripe_api_key":              "AP_STRIPE_API_KEY",
    "stripe_webhook_secret":       "AP_STRIPE_WEBHOOK_SECRET",
    "stripe_price_id_pro_monthly": "AP_STRIPE_PRICE_ID_PRO_MONTHLY",
    "stripe_price_id_pack_5":      "AP_STRIPE_PRICE_ID_PACK_5",
    "stripe_price_id_pack_10":     "AP_STRIPE_PRICE_ID_PACK_10",
    "stripe_price_id_pack_25":     "AP_STRIPE_PRICE_ID_PACK_25",
    "stripe_price_id_pack_50":     "AP_STRIPE_PRICE_ID_PACK_50",
    "stripe_price_id_pack_100":    "AP_STRIPE_PRICE_ID_PACK_100",
}


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

    # Phase 28 — Temporal client/worker config (D-01..D-05).
    # The worker container reads these to dial the cluster on boot.
    # api_server reads `temporal_host` + `temporal_namespace` to mint
    # the Client used for `start_workflow` calls from POST /messages.
    temporal_host: str = Field(
        "temporal:7233",
        validation_alias="AP_TEMPORAL_HOST",
        description="Temporal frontend host:port (Docker DNS in compose; localhost:7233 if running outside compose).",
    )
    temporal_namespace: str = Field(
        "default",
        validation_alias="AP_TEMPORAL_NAMESPACE",
        description="Temporal namespace. Single namespace per CONTEXT D-03.",
    )
    temporal_task_queue: str = Field(
        "ap-messages",
        validation_alias="AP_TEMPORAL_TASK_QUEUE",
        description="Workflow task queue name. Single queue per CONTEXT D-05.",
    )
    bot_timeout_seconds: float = Field(
        60.0,
        validation_alias="AP_BOT_TIMEOUT_SECONDS",
        description="Per-call bot HTTP timeout. Phase 28 D-12: forward_to_agent activity start_to_close = this + 30s buffer.",
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

    # Phase 25 Wave 5 — Mobile GitHub OAuth credentials. Separate App
    # from the web one because GitHub allows only one callback URL per
    # OAuth App (web => /v1/auth/github/callback, mobile => solvrlabs://oauth/github).
    # Backend exchanges the authorization code for an access_token using
    # these credentials so the secret never lives on the device.
    oauth_github_mobile_client_id: str | None = Field(
        None, validation_alias="AP_OAUTH_GITHUB_MOBILE_CLIENT_ID"
    )
    oauth_github_mobile_client_secret: str | None = Field(
        None, validation_alias="AP_OAUTH_GITHUB_MOBILE_CLIENT_SECRET"
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

    # Phase 31 H6 (D-10, D-13). DSN unset → graceful no-op (D-14).
    sentry_dsn_api: str | None = Field(default=None, validation_alias="AP_SENTRY_DSN_API")

    # Phase 31 D-13. Boot-pinned git SHA for prod-error attribution.
    git_sha: str | None = Field(default=None, validation_alias="GIT_SHA")

    # ------------------------------------------------------------------
    # Phase B (Plan B-stripe-02) — Stripe substrate (D-11, D-19, AMD-01).
    # ------------------------------------------------------------------
    # 8 secrets / price-id config keys. In ``AP_ENV=dev``, missing keys
    # resolve to deterministic placeholders so a fresh checkout boots
    # without ops setup. In ``AP_ENV=prod``, ``_resolve_or_warn_stripe``
    # (model_validator below) raises ``RuntimeError`` listing every
    # missing key — mirrors the OAuth ``_resolve_or_fail`` discipline.
    #
    # Real TEST keys live in ``deploy/.env.prod`` (already populated per
    # Phase B Wave 0). Real prices were minted on 2026-05-08 via the
    # ``stripe-projects`` skill and recorded in
    # ``.planning/phases/B-stripe-paywall/STRIPE-TEST-CATALOG.md``.
    stripe_api_key: str = Field(
        default="", validation_alias="AP_STRIPE_API_KEY"
    )
    stripe_webhook_secret: str = Field(
        default="", validation_alias="AP_STRIPE_WEBHOOK_SECRET"
    )
    stripe_price_id_pro_monthly: str = Field(
        default="", validation_alias="AP_STRIPE_PRICE_ID_PRO_MONTHLY"
    )
    stripe_price_id_pack_5: str = Field(
        default="", validation_alias="AP_STRIPE_PRICE_ID_PACK_5"
    )
    stripe_price_id_pack_10: str = Field(
        default="", validation_alias="AP_STRIPE_PRICE_ID_PACK_10"
    )
    stripe_price_id_pack_25: str = Field(
        default="", validation_alias="AP_STRIPE_PRICE_ID_PACK_25"
    )
    stripe_price_id_pack_50: str = Field(
        default="", validation_alias="AP_STRIPE_PRICE_ID_PACK_50"
    )
    stripe_price_id_pack_100: str = Field(
        default="", validation_alias="AP_STRIPE_PRICE_ID_PACK_100"
    )

    # Phase B UAT regression fix (#13) — Stripe Tax (`automatic_tax: true` on
    # Checkout Session create) is not supported in every account country
    # (e.g. Brazil — see https://stripe.com/docs/tax/supported-countries).
    # Default OFF so a Stripe TEST account in any country can mint a checkout
    # session. Operators in supported countries opt in via
    # AP_STRIPE_AUTOMATIC_TAX_ENABLED=true to let Stripe Tax compute VAT/sales tax.
    stripe_automatic_tax_enabled: bool = Field(
        default=False, validation_alias="AP_STRIPE_AUTOMATIC_TAX_ENABLED"
    )

    @model_validator(mode="after")
    def _substitute_stripe_dev_placeholders(self) -> "Settings":
        """In dev: log a warning per missing AP_STRIPE_* and substitute a
        deterministic placeholder so a fresh checkout boots without ops
        setup. In prod the empty strings are LEFT AS IS — the prod
        fail-loud is the responsibility of ``validate_stripe_config()``,
        which Phase B's StripeClient lifespan service + billing_packs
        module call at construction time. This mirrors the OAuth pattern
        in ``auth/oauth.py::get_oauth`` (deferred fail-loud at service
        construction, not at Settings instantiation) so unrelated tests
        that set ``AP_ENV=prod`` to exercise non-Stripe surfaces don't
        have to set 8 unrelated AP_STRIPE_* placeholders.
        """
        if self.env == "prod":
            # Leave empty strings as-is for explicit prod boot.
            # validate_stripe_config() (called by Phase B services) is
            # the fail-loud gate.
            return self

        # env == "dev" — substitute placeholders + warn (one log line per
        # missing field). pydantic v2 model_validator(mode='after') allows
        # in-place attribute writes on the model instance.
        for field_name in _STRIPE_DEV_PLACEHOLDERS:
            if getattr(self, field_name):
                continue
            placeholder = _STRIPE_DEV_PLACEHOLDERS[field_name]
            object.__setattr__(self, field_name, placeholder)
            _log.warning(
                "config.stripe_missing_in_dev",
                extra={
                    "field": field_name,
                    "env_alias": _STRIPE_FIELD_TO_ENV_ALIAS[field_name],
                    "placeholder": placeholder,
                },
            )
        return self

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


def validate_stripe_config(settings: Settings) -> None:
    """Phase B Plan B-stripe-02 — fail-loud check for production Stripe config.

    Raises ``RuntimeError`` listing every empty ``AP_STRIPE_*`` field when
    ``settings.env == 'prod'``. Mirrors the OAuth ``get_oauth(settings)``
    discipline: Settings instantiation stays optional (so dev boots without
    ops setup AND unrelated prod tests don't have to mint Stripe placeholders),
    but services that actually need Stripe call this validator at construction
    time. In dev the validator is a no-op (the model_validator
    ``_substitute_stripe_dev_placeholders`` already filled in deterministic
    placeholders). Phase B's StripeClient lifespan service + billing_packs
    module are the canonical callers.

    For test ergonomics: callable with arbitrary AP_ENV — the prod fail-loud
    is the only branch that raises; dev / unset env returns silently.
    """
    if settings.env != "prod":
        return
    missing = [
        f for f in _STRIPE_DEV_PLACEHOLDERS
        if not getattr(settings, f)
    ]
    if not missing:
        return
    env_aliases = sorted(_STRIPE_FIELD_TO_ENV_ALIAS[f] for f in missing)
    raise RuntimeError(
        "AP_STRIPE_* required in prod; missing: " + ", ".join(env_aliases)
    )
