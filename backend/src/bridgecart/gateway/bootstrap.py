"""Seed the three chart-managed upstreams once; never replace admin edits."""

import asyncio
import os
import uuid

from bridgecart.auth.models import utc_now
from bridgecart.core.config import get_settings
from bridgecart.db.session import create_session_factory
from bridgecart.gateway.models import UpstreamServer
from bridgecart.gateway.security import cipher, validate_url

SEEDS = (
    ("woocommerce", "WooCommerce", "BRIDGECART_SEED_WOOCOMMERCE_TOKEN"),
    ("inventory", "Demo Inventory", "BRIDGECART_SEED_INVENTORY_TOKEN"),
    ("shipping", "Demo Shipping", "BRIDGECART_SEED_SHIPPING_TOKEN"),
)


async def bootstrap() -> None:
    settings = get_settings()
    if not settings.gateway_enabled:
        return
    urls = settings.gateway_allowed_urls.split(",")
    if len(urls) < len(SEEDS):
        raise RuntimeError("Expected at least three approved seed URLs")
    engine, factory = create_session_factory(settings)
    try:
        async with factory() as db:
            for (slug, name, env_name), url in zip(SEEDS, urls[: len(SEEDS)], strict=True):
                identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, "bridgecart/" + slug))
                if await db.get(UpstreamServer, identifier) is not None:
                    continue
                token = os.environ.get(env_name)
                if not token:
                    raise RuntimeError("Missing configured upstream seed credential")
                now = utc_now()
                db.add(
                    UpstreamServer(
                        id=identifier,
                        name=name,
                        url=validate_url(url, settings),
                        enabled=True,
                        auth_type="bearer",
                        header_name=None,
                        credential_encrypted=cipher(settings).encrypt(token.encode()),
                        created_at=now,
                        updated_at=now,
                    )
                )
            await db.commit()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(bootstrap())
