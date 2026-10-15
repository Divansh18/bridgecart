import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from woocommerce_mcp.config import Settings


class StoreError(Exception):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _enc(value: object) -> str:
    return quote(str(value), safe="~-._")


def oauth_parameters(
    method: str, public_url: str, path: str, params: Mapping[str, str], key: str, secret: str
) -> dict[str, str]:
    signed = dict(params)
    signed.update(
        oauth_consumer_key=key,
        oauth_nonce=secrets.token_hex(16),
        oauth_timestamp=str(int(time.time())),
        oauth_signature_method="HMAC-SHA256",
    )
    normalized = "&".join(f"{_enc(k)}={_enc(v)}" for k, v in sorted(signed.items()))
    base = "&".join((_enc(method.upper()), _enc(public_url + path), _enc(normalized)))
    digest = hmac.new((secret + "&").encode(), base.encode(), hashlib.sha256).digest()
    signed["oauth_signature"] = base64.b64encode(digest).decode()
    return signed


class WooClient:
    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings = settings
        self.http = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(settings.request_timeout, connect=settings.connect_timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            follow_redirects=False,
            trust_env=False,
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[Any, int]:
        query = dict(params or {})
        headers: dict[str, str] = {"Accept": "application/json"}
        key = self.settings.consumer_key.get_secret_value()
        secret = self.settings.consumer_secret.get_secret_value()
        if self.settings.api_base_url.startswith("http://"):
            # WooCommerce signs with is_ssl()'s scheme. Internal WordPress HTTP
            # requires http even when its public storefront uses HTTPS.
            signature_url = self.settings.public_url.replace("https://", "http://", 1)
            signed = oauth_parameters(method, signature_url, path, query, key, secret)
            headers["Authorization"] = "OAuth " + ", ".join(
                f'{name}="{_enc(value)}"'
                for name, value in signed.items()
                if name.startswith("oauth_")
            )
        else:
            token = base64.b64encode(f"{key}:{secret}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        try:
            response = await self.http.request(
                method, self.settings.api_base_url + path, params=query, json=body, headers=headers
            )
        except httpx.TimeoutException as exc:
            if method.upper() != "GET":
                raise StoreError(
                    "Write timed out; it may have succeeded. Inspect WooCommerce before retrying."
                ) from exc
            raise StoreError("WooCommerce request timed out") from exc
        except httpx.RequestError as exc:
            if method.upper() != "GET":
                raise StoreError(
                    "Write may have succeeded. Inspect WooCommerce before retrying."
                ) from exc
            raise StoreError("WooCommerce is unavailable") from exc
        if response.status_code in (401, 403):
            raise StoreError(
                "WooCommerce API authentication or permission failed", status=response.status_code
            )
        if response.status_code == 404:
            raise StoreError("WooCommerce resource was not found", status=404)
        if response.status_code >= 500:
            raise StoreError(
                f"WooCommerce is unavailable (HTTP {response.status_code})",
                status=response.status_code,
            )
        if response.status_code >= 400:
            raise StoreError(
                f"WooCommerce API returned HTTP {response.status_code}", status=response.status_code
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise StoreError("WooCommerce returned an invalid JSON response") from exc
        return data, int(response.headers.get("X-WP-Total", "0"))
