#!/usr/bin/env python3
"""Run a bounded MCP client smoke check in a temporary, policy-allowed Pod."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ["kubectl", "--context", "k3d-bridgecart", "-n", "bridgecart"]
NAME = "bridgecart-mcp-verify"


def run(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(BASE + list(args), text=True, capture_output=True, timeout=timeout)


def main() -> None:
    order_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if order_id is not None and order_id < 1:
        raise ValueError("order ID must be positive")
    existing = run("get", "pod", NAME, "-o", "json")
    if existing.returncode == 0:
        raise RuntimeError(f"{NAME} already exists; inspect it before running this temporary check")
    if "NotFound" not in existing.stderr:
        raise RuntimeError("Could not determine temporary Pod ownership")
    manifest = ROOT / "scripts/mcp_verify_pod.yaml"
    created = subprocess.run(BASE + ["apply", "-f", str(manifest)], check=True, capture_output=True)
    assert created.returncode == 0
    pod = run("get", "pod", NAME, "-o", "json")
    if pod.returncode:
        raise RuntimeError("Temporary verification Pod was not readable")
    identity = json.loads(pod.stdout)
    uid = identity["metadata"]["uid"]
    if identity["metadata"]["labels"].get("bridgecart.dev/temporary-owner") != "milestone-three":
        raise RuntimeError("Temporary Pod ownership label is missing")
    try:
        commands = [
            ("wait", "--for=condition=Ready", f"pod/{NAME}", "--timeout=90s"),
            ("cp", str(ROOT / "scripts/mcp_incluster_verify.py"), f"{NAME}:/tmp/verify.py"),
            ("exec", NAME, "--", "/app/.venv/bin/python", "/tmp/verify.py", "auth"),
            ("exec", NAME, "--", "/app/.venv/bin/python", "/tmp/verify.py", "catalog"),
        ]
        if order_id is not None:
            commands.extend([
                ("exec", NAME, "--", "/app/.venv/bin/python", "/tmp/verify.py", "orders"),
                ("exec", NAME, "--", "/app/.venv/bin/python", "/tmp/verify.py", "get", str(order_id)),
            ])
        for args in commands:
            outcome = run(*args)
            if outcome.returncode:
                raise RuntimeError(f"Verification command failed: {args[0]} (exit {outcome.returncode})")
            if args[0] == "exec":
                print(outcome.stdout.strip())
    finally:
        current = run("get", "pod", NAME, "-o", "json")
        if current.returncode == 0:
            observed = json.loads(current.stdout)
            if observed["metadata"]["uid"] == uid and observed["metadata"]["labels"].get(
                "bridgecart.dev/temporary-owner"
            ) == "milestone-three":
                deleted = run("delete", "pod", NAME, "--wait=true")
                if deleted.returncode:
                    raise RuntimeError("Temporary verification Pod cleanup failed")
                print("Removed owned temporary MCP verification Pod")


if __name__ == "__main__":
    main()
