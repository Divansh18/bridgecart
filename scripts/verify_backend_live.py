"""Verify the local API, then replace only its pod and recheck persistent records."""

import base64
import json
import secrets
import time

import httpx
from backend_secrets import ensure_secret, kubectl

MEMBER_EMAIL = "milestone4a-member@bridgecart.local"
MEMBER_SECRET = "bridgecart-demo-member"
HOST = "api.bridgecart.local"


def secret_value(name: str, key: str) -> str:
    result = kubectl("get", "secret", name, "-o", "json")
    if result.returncode:
        raise RuntimeError(f"Cannot inspect {name}")
    return base64.b64decode(json.loads(result.stdout)["data"][key]).decode()


def checked(response: httpx.Response, status: int) -> dict[str, object]:
    if response.status_code != status:
        raise RuntimeError(
            f"API verification failed at {response.request.url.path}: HTTP {response.status_code}"
        )
    return response.json() if response.content else {}


def client() -> httpx.Client:
    return httpx.Client(
        base_url="http://127.0.0.1:8088", headers={"Host": HOST}, timeout=10
    )


def login(connection: httpx.Client, email: str, password: str) -> str:
    checked(
        connection.post("/auth/login", json={"email": email, "password": password}), 200
    )
    return connection.cookies["bridgecart_csrf"]


def run() -> None:
    admin_email = secret_value("bridgecart-initial-admin", "admin-email")
    admin_password = secret_value("bridgecart-initial-admin", "admin-password")
    ensure_secret(MEMBER_SECRET, {"member-password": secrets.token_urlsafe(36)})
    member_password = secret_value(MEMBER_SECRET, "member-password")
    sensitive = [admin_password, member_password]
    with client() as admin, client() as member:
        admin_csrf = login(admin, admin_email, admin_password)
        members = checked(admin.get("/members"), 200)
        assert isinstance(members, list)
        existing = next(
            (item for item in members if item["email"] == MEMBER_EMAIL), None
        )
        if existing is None:
            invitation = checked(
                admin.post(
                    "/invitations",
                    headers={"X-CSRF-Token": admin_csrf},
                    json={"email": MEMBER_EMAIL},
                ),
                201,
            )
            token = str(invitation["token"])
            sensitive.append(token)
            accepted = checked(
                member.post(
                    "/auth/invitations/accept",
                    json={"token": token, "password": member_password},
                ),
                201,
            )
            member_id = int(accepted["id"])
        else:
            member_id = int(existing["id"])
        member_csrf = login(member, MEMBER_EMAIL, member_password)
        sensitive.extend(
            [admin.cookies["bridgecart_session"], member.cookies["bridgecart_session"]]
        )
        own_keys = checked(member.get("/api-keys"), 200)
        assert isinstance(own_keys, list)
        own = next(
            (item for item in own_keys if item["name"] == "milestone4a-live-member"),
            None,
        )
        if own is None:
            created = checked(
                member.post(
                    "/api-keys",
                    headers={"X-CSRF-Token": member_csrf},
                    json={"name": "milestone4a-live-member"},
                ),
                201,
            )
            sensitive.append(str(created["key"]))
            own_id = int(created["id"])
        else:
            own_id = int(own["id"])
        admin_keys = checked(admin.get(f"/members/{member_id}/api-keys"), 200)
        assert isinstance(admin_keys, list)
        assert all("key" not in item for item in admin_keys)
        if not any(
            item["name"] == "milestone4a-live-admin-issued" for item in admin_keys
        ):
            issued = checked(
                admin.post(
                    f"/members/{member_id}/api-keys",
                    headers={"X-CSRF-Token": admin_csrf},
                    json={"name": "milestone4a-live-admin-issued"},
                ),
                201,
            )
            sensitive.append(str(issued["key"]))
        assert all("key" not in item for item in checked(member.get("/api-keys"), 200))  # type: ignore[arg-type]
        old_pod = kubectl(
            "get", "pods", "-l", "app.kubernetes.io/component=backend", "-o", "json"
        )
        if old_pod.returncode:
            raise RuntimeError("Cannot inspect backend pod")
        pods = json.loads(old_pod.stdout)["items"]
        if (
            len(pods) != 1
            or pods[0]["metadata"]["labels"].get("app.kubernetes.io/instance")
            != "bridgecart"
        ):
            raise RuntimeError("Backend pod ownership check failed")
        pod_name = pods[0]["metadata"]["name"]
        before_logs = kubectl("logs", pod_name, "--since=20m")
        if before_logs.returncode or any(
            value.encode() in before_logs.stdout for value in sensitive
        ):
            raise RuntimeError("Backend log credential scan failed")
        deleted = kubectl("delete", "pod", pod_name, "--wait=false")
        if deleted.returncode:
            raise RuntimeError("Could not replace backend pod")
        gone = kubectl("wait", "--for=delete", f"pod/{pod_name}", "--timeout=180s")
        if gone.returncode:
            raise RuntimeError("Old backend pod did not terminate")
        rollout = kubectl(
            "rollout", "status", "deployment/bridgecart-backend", "--timeout=180s"
        )
        if rollout.returncode:
            raise RuntimeError("Backend did not become ready after pod replacement")
        # Ingress endpoint can lag rollout readiness briefly.
        for _ in range(20):
            try:
                with client() as check_admin, client() as check_member:
                    login(check_admin, admin_email, admin_password)
                    login(check_member, MEMBER_EMAIL, member_password)
                    later_members = checked(check_admin.get("/members"), 200)
                    later_keys = checked(check_member.get("/api-keys"), 200)
                    assert isinstance(later_members, list) and isinstance(
                        later_keys, list
                    )
                    assert any(item["id"] == member_id for item in later_members)
                    assert any(item["id"] == own_id for item in later_keys)
                    assert all("key" not in item for item in later_keys)
                    sensitive.extend(
                        [
                            check_admin.cookies["bridgecart_session"],
                            check_member.cookies["bridgecart_session"],
                        ]
                    )
                    break
            except (httpx.HTTPError, RuntimeError):
                time.sleep(1)
        else:
            raise RuntimeError(
                "Persistent member/key check failed after pod replacement"
            )
        after_logs = kubectl("logs", "deployment/bridgecart-backend", "--since=20m")
        if after_logs.returncode or any(
            value.encode() in after_logs.stdout for value in sensitive
        ):
            raise RuntimeError("Backend log credential scan failed after replacement")
        print(
            f"Live admin/member flow passed; member ID {member_id}, member key ID {own_id}; backend pod replacement retained both; credential log scans passed."
        )


if __name__ == "__main__":
    run()
