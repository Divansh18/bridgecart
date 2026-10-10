"""Create local PostgreSQL and initial-admin Secrets without printing values."""

import base64
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

CONTEXT = "k3d-bridgecart"
NAMESPACE = "bridgecart"
DB_SECRET = "bridgecart-postgres-credentials"
ADMIN_SECRET = "bridgecart-initial-admin"


def kubectl(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["kubectl", "--context", CONTEXT, "-n", NAMESPACE, *args],
        capture_output=True,
        check=False,
        timeout=240,
    )


def ensure_secret(name: str, fields: dict[str, str]) -> None:
    found = kubectl("get", "secret", name, "-o", "json")
    if found.returncode == 0:
        stored = json.loads(found.stdout).get("data", {})
        if set(stored) != set(fields):
            raise RuntimeError(f"Existing {name} has unexpected keys")
        for value in stored.values():
            base64.b64decode(value, validate=True)
        print(f"{name}: existing")
        return
    if b"NotFound" not in found.stderr:
        raise RuntimeError(f"Could not inspect {name} (exit {found.returncode})")
    with tempfile.TemporaryDirectory(prefix="bridgecart-backend-secret-") as temporary:
        directory = Path(temporary)
        os.chmod(directory, 0o700)
        command = ["create", "secret", "generic", name]
        for key, value in fields.items():
            path = directory / key
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(value)
            command.append(f"--from-file={key}={path}")
        created = kubectl(*command)
    if created.returncode:
        raise RuntimeError(f"Could not create {name} (exit {created.returncode})")
    print(f"{name}: created")


def main() -> None:
    password = secrets.token_urlsafe(36)
    ensure_secret(
        DB_SECRET,
        {
            "password": password,
            "database-url": f"postgresql+asyncpg://bridgecart:{password}@bridgecart-postgres:5432/bridgecart",
        },
    )
    ensure_secret(
        ADMIN_SECRET,
        {
            "admin-email": "admin@bridgecart.local",
            "admin-password": secrets.token_urlsafe(36),
        },
    )


if __name__ == "__main__":
    main()
