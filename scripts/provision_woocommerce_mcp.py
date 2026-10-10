#!/usr/bin/env python3
"""Create or reuse local MCP Secrets, then bind the REST key to a dedicated Woo user."""

import base64
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = "k3d-bridgecart"
NAMESPACE = "bridgecart"
API_SECRET = "bridgecart-woocommerce-api"
BEARER_SECRET = "bridgecart-mcp-bearer"


def kubectl(*args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["kubectl", "--context", CONTEXT, "-n", NAMESPACE, *args],
        input=input_bytes, capture_output=True, check=False, timeout=60,
    )


def ensure_secret(name: str, data: dict[str, str]) -> dict[str, str]:
    found = kubectl("get", "secret", name, "-o", "json")
    if found.returncode == 0:
        decoded = json.loads(found.stdout)["data"]
        if set(decoded) != set(data):
            raise RuntimeError(f"{name} has unexpected keys; inspect it manually")
        return {key: base64.b64decode(decoded[key]).decode() for key in data}
    # A failed GET can mean more than NotFound; check the reason without echoing Secrets.
    if b"NotFound" not in found.stderr:
        raise RuntimeError(f"Could not inspect {name}: kubectl exited {found.returncode}")
    with tempfile.TemporaryDirectory(prefix="bridgecart-mcp-secret-") as directory:
        os.chmod(directory, 0o700)
        command = ["create", "secret", "generic", name]
        for key, value in data.items():
            path = Path(directory) / key
            path.write_text(value)
            path.chmod(0o600)
            command.append(f"--from-file={key}={path}")
        created = kubectl(*command)
    if created.returncode:
        raise RuntimeError(f"Could not create {name}: kubectl exited {created.returncode}")
    return data


def main() -> None:
    api = ensure_secret(API_SECRET, {
        "consumer-key": "ck_" + secrets.token_hex(32),
        # WooCommerce stores consumer_secret in a char(43) column (cs_ + 40 hex).
        "consumer-secret": "cs_" + secrets.token_hex(20),
    })
    ensure_secret(BEARER_SECRET, {"token": secrets.token_urlsafe(48)})
    php = (ROOT / "scripts/provision_woocommerce_mcp.php").read_text().removeprefix("<?php\n")
    payload = json.dumps({"key": api["consumer-key"], "secret": api["consumer-secret"]}).encode()
    result = kubectl("exec", "-i", "deploy/bridgecart-wordpress", "--", "php", "-r", php,
                     input_bytes=payload)
    if result.returncode:
        known_errors = (
            "WooCommerce is not active",
            "Credential input is invalid",
            "Could not create dedicated WooCommerce user",
            "Dedicated user has an unexpected role",
            "Existing WooCommerce key has unexpected ownership or permissions",
            "Existing WooCommerce key secret differs from Kubernetes Secret",
            "Could not attach WooCommerce key",
        )
        diagnostic = next(
            (message for message in known_errors if message.encode() in result.stderr),
            "WordPress command failed; inspect pod availability and events",
        )
        raise RuntimeError(
            f"WooCommerce credential provisioning failed (exit {result.returncode}): "
            + diagnostic
        )
    status = result.stdout.decode(errors="replace").strip()
    if status not in {"created", "existing"}:
        raise RuntimeError("WooCommerce credential provisioning returned unexpected output")
    print("MCP Secrets are present; dedicated WooCommerce key:", status)


if __name__ == "__main__":
    main()
