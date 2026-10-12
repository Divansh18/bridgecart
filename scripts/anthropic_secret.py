"""Privately create or update the local Anthropic API Secret.

The key travels to kubectl on stdin, never in a command argument or file.
"""

import base64
import getpass
import json
import subprocess
import sys
import warnings
from typing import Any

CONTEXT = "k3d-bridgecart"
NAMESPACE = "bridgecart"
SECRET_NAME = "bridgecart-anthropic-api"
SECRET_KEY = "ANTHROPIC_API_KEY"


def kubectl(*args: str, input_data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["kubectl", "--context", CONTEXT, "-n", NAMESPACE, *args],
        input=input_data,
        capture_output=True,
        check=False,
        timeout=30,
    )


def secret_manifest(key: str, existing: dict[str, Any] | None) -> dict[str, Any]:
    encoded = base64.b64encode(key.encode("utf-8")).decode("ascii")
    metadata: dict[str, Any] = {"name": SECRET_NAME, "namespace": NAMESPACE}
    data: dict[str, str] = {}
    if existing is not None:
        if existing.get("type") != "Opaque" or existing.get("immutable"):
            raise RuntimeError("Existing Anthropic Secret is not a mutable Opaque Secret")
        source_metadata = existing.get("metadata", {})
        if source_metadata.get("name") != SECRET_NAME or source_metadata.get("namespace") != NAMESPACE:
            raise RuntimeError("Existing Anthropic Secret identity does not match")
        for field in ("resourceVersion", "labels", "annotations", "finalizers", "ownerReferences"):
            if field in source_metadata:
                metadata[field] = source_metadata[field]
        if "resourceVersion" not in metadata:
            raise RuntimeError("Existing Anthropic Secret has no resource version")
        data = dict(existing.get("data") or {})
    data[SECRET_KEY] = encoded
    return {"apiVersion": "v1", "kind": "Secret", "metadata": metadata, "type": "Opaque", "data": data}


def upsert_secret(key: str) -> str:
    found = kubectl("get", "secret", SECRET_NAME, "-o", "json")
    if found.returncode == 0:
        existing = json.loads(found.stdout)
        action = "replace"
    elif b"NotFound" in found.stderr:
        existing = None
        action = "create"
    else:
        raise RuntimeError(f"Could not inspect Anthropic Secret (exit {found.returncode})")
    manifest = secret_manifest(key, existing)
    result = kubectl(action, "-f", "-", input_data=json.dumps(manifest).encode("utf-8"))
    if result.returncode:
        raise RuntimeError(f"Could not {action} Anthropic Secret (exit {result.returncode})")
    return "updated" if existing is not None else "created"


def main() -> None:
    if not sys.stdin.isatty():
        raise RuntimeError("Run this helper in an interactive terminal")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        key = getpass.getpass("ANTHROPIC_API_KEY: ")
    if not key or any(character.isspace() or ord(character) < 32 for character in key):
        raise RuntimeError("API key must be nonempty and contain no whitespace or control characters")
    print(f"{SECRET_NAME}: {upsert_secret(key)}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired, getpass.GetPassWarning, EOFError, KeyboardInterrupt) as exc:
        if isinstance(exc, (RuntimeError, subprocess.TimeoutExpired)):
            print(f"Anthropic Secret setup failed: {exc}", file=sys.stderr)
        else:
            print("Anthropic Secret setup cancelled; no key was submitted", file=sys.stderr)
        raise SystemExit(1) from None
