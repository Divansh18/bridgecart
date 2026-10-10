"""Run isolated real-PostgreSQL access tests without printing Secret contents."""

import base64
import json
import os
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = "k3d-bridgecart"
NAMESPACE = "bridgecart"


def main() -> int:
    secret = subprocess.run(
        [
            "kubectl",
            "--context",
            CONTEXT,
            "-n",
            NAMESPACE,
            "get",
            "secret",
            "bridgecart-postgres-credentials",
            "-o",
            "json",
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    if secret.returncode:
        raise RuntimeError("Cannot read local PostgreSQL Secret")
    encoded = json.loads(secret.stdout)["data"]["database-url"]
    database_url = base64.b64decode(encoded).decode()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    forwarded = database_url.replace(
        "@bridgecart-postgres:5432/", f"@127.0.0.1:{port}/"
    )
    if forwarded == database_url:
        raise RuntimeError("PostgreSQL Secret has an unexpected URL host")
    forward = subprocess.Popen(
        [
            "kubectl",
            "--context",
            CONTEXT,
            "-n",
            NAMESPACE,
            "port-forward",
            "--address",
            "127.0.0.1",
            "svc/bridgecart-postgres",
            f"{port}:5432",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(60):
            if forward.poll() is not None:
                raise RuntimeError("PostgreSQL port-forward stopped before tests")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("PostgreSQL port-forward did not become ready")
        environment = os.environ | {"BRIDGECART_TEST_DATABASE_URL": forwarded}
        result = subprocess.run(
            [
                str(ROOT / "backend/.venv/bin/pytest"),
                "-q",
                "backend/tests/integration/test_team_access_postgres.py",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        output = (
            (result.stdout + result.stderr)
            .replace(database_url, "[redacted]")
            .replace(forwarded, "[redacted]")
        )
        print(output, end="")
        return result.returncode
    finally:
        forward.terminate()
        try:
            forward.wait(timeout=5)
        except subprocess.TimeoutExpired:
            forward.kill()
            forward.wait()


if __name__ == "__main__":
    raise SystemExit(main())
