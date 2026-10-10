"""Create only the BridgeCart k3d cluster after checking local state."""

import json
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = "k3d-bridgecart"


def run(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=capture)


def main() -> int:
    run("docker", "info", "--format", "{{.ServerVersion}}", capture=True)
    clusters = json.loads(run("k3d", "cluster", "list", "-o", "json", capture=True).stdout)
    if any(cluster["name"] == "bridgecart" for cluster in clusters):
        print("BridgeCart cluster already exists; reusing it without changes.")
        run("kubectl", "--context", CONTEXT, "get", "nodes")
        return 0

    for port in (6550, 8088):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError as exc:
                print(f"Port {port} is unavailable; no cluster was created: {exc}", file=sys.stderr)
                return 1

    run("k3d", "cluster", "create", "--config", str(ROOT / "deploy/k3d/cluster.yaml"))
    run("kubectl", "--context", CONTEXT, "get", "nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
