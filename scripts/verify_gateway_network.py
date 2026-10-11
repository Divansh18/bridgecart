"""Probe upstream ingress and demo-service database egress using owned Pods."""

import json
import secrets
import subprocess

from backend_secrets import kubectl


def probe(pod: str, host: str, port: int, *, expect_blocked: bool) -> None:
    code = (
        "import socket,sys; "
        "s=socket.socket(); s.settimeout(3); "
        "sys.exit(0 if s.connect_ex((sys.argv[1],int(sys.argv[2])))==0 else 1)"
    )
    result = kubectl("exec", pod, "--", "/app/.venv/bin/python", "-c", code, host, str(port))
    if (result.returncode != 0) != expect_blocked:
        raise RuntimeError(f"Unexpected network path: {pod} -> {host}:{port}")


def main() -> None:
    name = "bridgecart-gateway-deny-" + secrets.token_hex(3)
    existing = kubectl("get", "pod", name, "-o", "json")
    if existing.returncode == 0 or b"NotFound" not in existing.stderr:
        raise RuntimeError("Temporary Pod name is not safely available")
    created = kubectl(
        "run", name, "--restart=Never", "--image=bridgecart/inventory-mcp:0.5.0",
        "--labels=bridgecart.dev/temporary-owner=milestone-four-b", "--command", "--",
        "/app/.venv/bin/python", "-c", "import time; time.sleep(300)",
    )
    if created.returncode:
        raise RuntimeError("Could not create temporary network probe Pod")
    observed = kubectl("get", "pod", name, "-o", "json")
    if observed.returncode:
        raise RuntimeError("Could not inspect temporary network probe Pod")
    identity = json.loads(observed.stdout)
    uid = identity["metadata"]["uid"]
    if identity["metadata"]["labels"].get("bridgecart.dev/temporary-owner") != "milestone-four-b":
        raise RuntimeError("Temporary Pod ownership label is missing")
    try:
        ready = kubectl("wait", "--for=condition=Ready", "pod/" + name, "--timeout=120s")
        if ready.returncode:
            raise RuntimeError("Temporary network probe Pod did not become Ready")
        for host, port in (
            ("bridgecart-woocommerce-mcp", 8001),
            ("bridgecart-inventory-mcp", 8002),
            ("bridgecart-shipping-mcp", 8003),
        ):
            probe(name, host, port, expect_blocked=True)
        print("Unlabeled temporary Pod was denied direct TCP access to all three MCP Services.")
        for pod in ("deployment/bridgecart-inventory-mcp", "deployment/bridgecart-shipping-mcp"):
            for host, port in (("bridgecart-postgres", 5432), ("bridgecart-mariadb", 3306)):
                probe(pod, host, port, expect_blocked=True)
        print("Inventory and shipping Pods were denied direct TCP access to both databases.")
    finally:
        current = kubectl("get", "pod", name, "-o", "json")
        if current.returncode == 0:
            item = json.loads(current.stdout)
            if item["metadata"]["uid"] == uid and item["metadata"]["labels"].get(
                "bridgecart.dev/temporary-owner"
            ) == "milestone-four-b":
                deleted = kubectl("delete", "pod", name, "--wait=true")
                if deleted.returncode:
                    raise RuntimeError("Temporary network probe Pod cleanup failed")
                print("Removed owned temporary network probe Pod.")


if __name__ == "__main__":
    main()
