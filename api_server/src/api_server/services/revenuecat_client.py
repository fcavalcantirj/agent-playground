"""RevenueCat client — thin REST wrapper for IAP integration.

Sibling to ``stripe_client.py``. The bulk of RevenueCat integration is
webhook-driven (RC POSTs to ``/v1/billing/revenuecat/webhook`` on every
purchase/renewal/cancellation/refund), so this client is intentionally
small: it only exists for the "reconcile on app foreground" path where
mobile pings the server to confirm a freshly-completed IAP has been
credited.

T-B-LK mitigation (secret never logged): we log only
``api_key_prefix=settings.revenuecat_api_key_backend[:7]`` (e.g.
``rcb_sec_``); never the full key.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import Settings

_log = logging.getLogger("api_server.revenuecat_client")

# RevenueCat v2 REST API base URL — stable since 2023.
_RC_BASE_URL = "https://api.revenuecat.com/v2"


def validate_revenuecat_config(settings: Settings) -> None:
    """Fail-loud check when prod boots without RC config.

    Mirrors ``validate_stripe_config`` shape: prod with empty
    ``revenuecat_api_key_backend`` or ``revenuecat_webhook_secret`` is a
    deploy error and we want loud-fail at boot rather than at first
    purchase. Dev / web-only deploys skip this check entirely — the
    IAP webhook route also runs a request-time auth-header check that
    400s when ``revenuecat_webhook_secret`` is empty, so an unset RC in
    dev is safe at runtime too.
    """
    if settings.env != "prod":
        return
    missing: list[str] = []
    if not settings.revenuecat_api_key_backend:
        missing.append("AP_REVENUECAT_API_KEY_BACKEND")
    if not settings.revenuecat_webhook_secret:
        missing.append("AP_REVENUECAT_WEBHOOK_SECRET")
    if missing:
        raise RuntimeError(
            "AP_REVENUECAT_* required in prod when IAP is enabled; "
            "missing: " + ", ".join(missing)
        )


def build_revenuecat_client(settings: Settings) -> "RevenueCatClient":
    """Construct a process-wide RevenueCat client.

    No-op when ``revenuecat_api_key_backend`` is empty — the returned
    client's methods will return None / raise RuntimeError on use, but
    the webhook route still works (it auths via ``webhook_secret`` and
    parses the POST body directly without an API round-trip).
    """
    validate_revenuecat_config(settings)
    return RevenueCatClient(settings.revenuecat_api_key_backend)


class RevenueCatClient:
    """Minimal RevenueCat REST client.

    Only the methods we actually need land here — resist the temptation to
    mirror the full RC SDK surface (mirror ``stripe_client.py`` discipline).
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._enabled = bool(api_key)
        if self._enabled:
            _log.info(
                "revenuecat_client.init",
                extra={"api_key_prefix": api_key[:7]},
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def get_subscriber(self, app_user_id: str) -> dict[str, Any] | None:
        """GET /subscribers/{app_user_id} — current subscription/entitlement state.

        Returns the parsed JSON body on 200, None on 404 (subscriber not
        found is expected for fresh users). Other non-2xx statuses raise
        httpx.HTTPStatusError so the caller can surface a 502 to the
        client.
        """
        if not self._enabled:
            raise RuntimeError(
                "RevenueCatClient.get_subscriber called but client is "
                "disabled (revenuecat_api_key_backend is empty)"
            )
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{_RC_BASE_URL}/subscribers/{app_user_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=headers)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
