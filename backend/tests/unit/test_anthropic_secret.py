"""The local helper sends key material only through kubectl stdin."""

import base64
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest


def load_helper() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "scripts" / "anthropic_secret.py"
    spec = importlib.util.spec_from_file_location("anthropic_secret", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_uses_stdin_and_never_exposes_key_in_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = load_helper()
    calls: list[tuple[list[str], bytes | None]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((args, kwargs.get("input") if isinstance(kwargs.get("input"), bytes) else None))
        if "get" in args:
            return subprocess.CompletedProcess(args, 1, b"", b"Error from server (NotFound)")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(helper.subprocess, "run", fake_run)
    assert helper.upsert_secret("private-test-value") == "created"
    assert len(calls) == 2
    assert all("private-test-value" not in " ".join(args) for args, _ in calls)
    assert calls[1][0][-3:] == ["create", "-f", "-"]
    manifest = json.loads(calls[1][1] or b"")
    assert base64.b64decode(manifest["data"]["ANTHROPIC_API_KEY"]) == b"private-test-value"


def test_update_preserves_other_secret_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = load_helper()
    existing = {
        "type": "Opaque",
        "metadata": {
            "name": helper.SECRET_NAME,
            "namespace": helper.NAMESPACE,
            "resourceVersion": "27",
            "labels": {"owner": "local"},
            "annotations": {"purpose": "demo"},
        },
        "data": {"keep-me": base64.b64encode(b"untouched").decode(), "ANTHROPIC_API_KEY": "b2xk"},
    }
    calls: list[tuple[list[str], bytes | None]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((args, kwargs.get("input") if isinstance(kwargs.get("input"), bytes) else None))
        if "get" in args:
            return subprocess.CompletedProcess(args, 0, json.dumps(existing).encode(), b"")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(helper.subprocess, "run", fake_run)
    assert helper.upsert_secret("new-private-value") == "updated"
    assert calls[1][0][-3:] == ["replace", "-f", "-"]
    manifest = json.loads(calls[1][1] or b"")
    assert manifest["data"]["keep-me"] == existing["data"]["keep-me"]
    assert manifest["metadata"]["resourceVersion"] == "27"
    assert manifest["metadata"]["labels"] == {"owner": "local"}
    assert manifest["metadata"]["annotations"] == {"purpose": "demo"}
    assert all("new-private-value" not in " ".join(args) for args, _ in calls)


def test_non_opaque_secret_is_not_replaced() -> None:
    helper = load_helper()
    with pytest.raises(RuntimeError, match="mutable Opaque"):
        helper.secret_manifest("test", {"type": "kubernetes.io/dockerconfigjson"})


def test_hidden_prompt_prints_only_secret_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    helper = load_helper()
    monkeypatch.setattr(helper.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(helper.getpass, "getpass", lambda _: "private-test-value")
    monkeypatch.setattr(helper, "upsert_secret", lambda _: "updated")
    helper.main()
    output = capsys.readouterr()
    assert "private-test-value" not in output.out + output.err
    assert output.out.strip() == f"{helper.SECRET_NAME}: updated"
