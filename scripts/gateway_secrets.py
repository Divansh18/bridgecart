"""Create local gateway encryption and demo upstream bearer Secrets idempotently."""

import secrets

from cryptography.fernet import Fernet

from backend_secrets import ensure_secret


def main() -> None:
    ensure_secret("bridgecart-upstream-encryption", {"fernet-key": Fernet.generate_key().decode()})
    ensure_secret("bridgecart-inventory-mcp-bearer", {"token": secrets.token_urlsafe(48)})
    ensure_secret("bridgecart-shipping-mcp-bearer", {"token": secrets.token_urlsafe(48)})


if __name__ == "__main__":
    main()
