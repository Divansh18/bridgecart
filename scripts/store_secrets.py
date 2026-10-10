"""Create local development credentials without placing secret values in argv or logs."""

import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

CONTEXT = "k3d-bridgecart"
NAMESPACE = "bridgecart"
NAME = "bridgecart-store-credentials"
KEYS = [
    "mariadb-root-password",
    "mariadb-password",
    "wordpress-admin-password",
    "wordpress-auth-key",
    "wordpress-secure-auth-key",
    "wordpress-logged-in-key",
    "wordpress-nonce-key",
    "wordpress-auth-salt",
    "wordpress-secure-auth-salt",
    "wordpress-logged-in-salt",
    "wordpress-nonce-salt",
]


def kubectl(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", "--context", CONTEXT, *args],
        check=False,
        text=True,
        capture_output=capture,
    )


def main() -> int:
    namespace = kubectl("get", "namespace", NAMESPACE, capture=True)
    if namespace.returncode != 0:
        created = kubectl("create", "namespace", NAMESPACE)
        if created.returncode != 0:
            return created.returncode

    existing = kubectl("-n", NAMESPACE, "get", "secret", NAME, "-o", "json", capture=True)
    if existing.returncode == 0:
        present = set(json.loads(existing.stdout).get("data", {}))
        missing = set(KEYS) - present
        if missing:
            print(f"Existing Secret is missing required keys: {', '.join(sorted(missing))}")
            return 1
        print(f"Secret {NAMESPACE}/{NAME} already exists; keeping its credentials.")
        return 0

    with tempfile.TemporaryDirectory(prefix="bridgecart-secrets-") as temporary:
        directory = Path(temporary)
        arguments = ["-n", NAMESPACE, "create", "secret", "generic", NAME]
        for key in KEYS:
            path = directory / key
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(secrets.token_urlsafe(48))
            arguments.append(f"--from-file={key}={path}")
        created = kubectl(*arguments)
    return created.returncode


if __name__ == "__main__":
    raise SystemExit(main())
