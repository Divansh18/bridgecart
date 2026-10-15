"""Checks for the local Secret bootstrap boundary without touching Kubernetes."""

import base64
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]


def provisioner() -> ModuleType:
    path = ROOT / "scripts/provision_woocommerce_mcp.py"
    spec = importlib.util.spec_from_file_location("bridgecart_provisioner_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_secret_is_reused_without_create(monkeypatch: pytest.MonkeyPatch) -> None:
    module = provisioner()
    stored = {"consumer-key": "ck_existing", "consumer-secret": "cs_existing"}
    encoded = {key: base64.b64encode(value.encode()).decode() for key, value in stored.items()}
    calls: list[tuple[str, ...]] = []

    def fake_kubectl(*args: str, **_: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps({"data": encoded}).encode(), b"")

    monkeypatch.setattr(module, "kubectl", fake_kubectl)
    assert module.ensure_secret("existing-secret", stored) == stored
    assert calls == [("get", "secret", "existing-secret", "-o", "json")]


@pytest.mark.parametrize("returncode", [0, 1])
def test_provisioner_never_forwards_untrusted_process_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], returncode: int
) -> None:
    module = provisioner()
    credential = "ck_sensitive_test_value"

    def fake_ensure(name: str, _: dict[str, str]) -> dict[str, str]:
        if name == module.API_SECRET:
            return {"consumer-key": credential, "consumer-secret": "cs_sensitive_test_value"}
        return {"token": "bearer_sensitive_test_value"}

    def fake_kubectl(*args: str, **_: Any) -> subprocess.CompletedProcess[bytes]:
        if returncode == 0:
            return subprocess.CompletedProcess(args, 0, b"existing\n" + credential.encode(), b"")
        return subprocess.CompletedProcess(args, 1, b"", credential.encode() + b" unexpected error")

    monkeypatch.setattr(module, "ensure_secret", fake_ensure)
    monkeypatch.setattr(module, "kubectl", fake_kubectl)
    with pytest.raises(RuntimeError) as caught:
        module.main()
    assert credential not in str(caught.value)
    assert credential not in capsys.readouterr().out
