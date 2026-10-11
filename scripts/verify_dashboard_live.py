"""Milestone-five browser acceptance against the existing local release.

Reads the already-created admin Secret in memory. Never prints credential values.
Creates one named test member and key, revokes the key, and deactivates the member.
Restores the inventory upstream in a finally block after a temporary disable.
"""

import base64
import json
import secrets
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://app.bridgecart.local:8088"
SCREENSHOTS = Path("/private/tmp/bridgecart-dashboard-screenshots")


def admin_credentials() -> tuple[str, str]:
    data = json.loads(subprocess.check_output([
        "kubectl", "--context", "k3d-bridgecart", "-n", "bridgecart", "get", "secret",
        "bridgecart-initial-admin", "-o", "json",
    ], stderr=subprocess.DEVNULL))
    fields = data["data"]
    return tuple(base64.b64decode(fields[key]).decode() for key in ("admin-email", "admin-password"))


def main() -> None:
    email, admin_password = admin_credentials()
    member_email = f"milestone5-ui-{secrets.token_hex(4)}@bridgecart.local"
    member_password = "UI-test-" + secrets.token_urlsafe(20)
    SCREENSHOTS.mkdir(exist_ok=True)
    member_id = None
    key_id = None
    upstream_id = None
    upstream_disabled = False
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--host-resolver-rules=MAP app.bridgecart.local 127.0.0.1, MAP api.bridgecart.local 127.0.0.1"
        ])
        admin_context = browser.new_context(viewport={"width": 1440, "height": 900}, permissions=["clipboard-read", "clipboard-write"])
        admin = admin_context.new_page()
        try:
            admin.goto(BASE + "/login", wait_until="networkidle")
            admin.get_by_label("Email address").fill(email)
            admin.get_by_label("Password", exact=True).fill(admin_password)
            admin.get_by_role("button", name="Sign in").click()
            admin.get_by_role("heading", name="Your workspace at a glance").wait_for(timeout=20000)
            assert admin.get_by_text("Connected servers").count() > 0
            prior_members = admin.evaluate("async () => (await fetch('/api/members')).json()")
            for prior in prior_members:
                if not prior["active"] or not prior["email"].startswith("milestone5-ui-"):
                    continue
                prior_keys = admin.evaluate("async (id) => (await fetch(`/api/members/${id}/api-keys`)).json()", prior["id"])
                assert all(key["name"] == "Milestone 5 UI verification" for key in prior_keys if not key["revoked_at"])
                for key in prior_keys:
                    if key["revoked_at"]:
                        continue
                    result = admin.evaluate("""async ({userId, keyId}) => {
                      const csrf = decodeURIComponent(document.cookie.split('; ').find(x => x.startsWith('bridgecart_csrf=')).split('=')[1]);
                      return (await fetch(`/api/members/${userId}/api-keys/${keyId}`, {method: 'DELETE', headers: {'X-CSRF-Token': csrf}})).status;
                    }""", {"userId": prior["id"], "keyId": key["id"]})
                    assert result == 204
                result = admin.evaluate("""async (id) => {
                  const csrf = decodeURIComponent(document.cookie.split('; ').find(x => x.startsWith('bridgecart_csrf=')).split('=')[1]);
                  return (await fetch(`/api/members/${id}/deactivate`, {method: 'POST', headers: {'X-CSRF-Token': csrf}})).status;
                }""", prior["id"])
                assert result == 200
                print(f"Cleaned up prior interrupted dashboard test member ID: {prior['id']}")
            admin.screenshot(path=str(SCREENSHOTS / "overview-desktop.png"), full_page=True)

            admin.get_by_role("button", name="Servers", exact=True).click()
            admin.get_by_role("heading", name="Servers", exact=True).wait_for()
            upstreams = admin.evaluate("async () => (await fetch('/api/servers')).json()")
            assert len(upstreams) >= 3
            assert all(row["status"] in {"Connected", "Unreachable", "Disabled"} for row in upstreams)
            assert all("credential" not in row for row in upstreams)
            inventory = next(row for row in upstreams if "inventory" in row["name"].lower())
            upstream_id = inventory["id"]
            assert inventory["status"] == "Connected" and inventory["tools"]
            card = admin.locator("section").filter(has=admin.get_by_role("heading", name=inventory["name"], exact=True))
            card.get_by_role("button", name="Exposed tools").click()
            assert card.get_by_text(inventory["tools"][0]["original_name"], exact=False).count() > 0
            card.get_by_role("button", name="Edit").click()
            editor = admin.get_by_role("dialog", name=f"Edit {inventory['name']}")
            assert editor.get_by_label("Stored credential").input_value() == "keep"
            assert editor.get_by_label("New credential").count() == 0
            editor.get_by_label("Stored credential").select_option("replace")
            assert editor.get_by_label("New credential").count() == 1
            admin.keyboard.press("Escape")
            assert editor.count() == 0
            admin.screenshot(path=str(SCREENSHOTS / "servers-desktop.png"), full_page=True)

            admin.get_by_role("button", name="Members", exact=True).click()
            admin.get_by_label("Member email").fill(member_email)
            admin.get_by_role("button", name="Create invitation").click()
            invitation_link = admin.get_by_label("Private invitation link").input_value()
            assert invitation_link.startswith(BASE + "/accept-invitation?token=")

            member_context = browser.new_context(viewport={"width": 390, "height": 844}, permissions=["clipboard-read", "clipboard-write"])
            member = member_context.new_page()
            member.goto(invitation_link, wait_until="networkidle")
            member.get_by_label("New password").fill(member_password)
            member.get_by_label("Confirm password").fill(member_password)
            member.get_by_role("button", name="Create account").click()
            member.get_by_text("Invitation accepted.", exact=False).wait_for()
            member.get_by_label("Email address").fill(member_email)
            member.get_by_label("Password", exact=True).fill(member_password)
            member.get_by_role("button", name="Sign in").click()
            member.get_by_role("heading", name="Your workspace at a glance").wait_for()
            assert member.get_by_role("button", name="Members", exact=True).count() == 0
            denied = member.evaluate("async () => (await fetch('/api/members')).status")
            assert denied == 403
            safe_catalog = member.evaluate("async () => (await fetch('/api/servers/catalog')).json()")
            assert safe_catalog and all("url" not in row and "has_credential" not in row for row in safe_catalog)
            member.screenshot(path=str(SCREENSHOTS / "overview-mobile.png"), full_page=True)
            member.get_by_role("button", name="Open navigation").click()
            member.get_by_role("button", name="API keys").click()
            member.get_by_label("Key name").fill("Milestone 5 UI verification")
            member.get_by_role("button", name="Create key").click()
            raw = member.get_by_label("New API key, shown once").input_value()
            assert raw.startswith("bck_")
            member.get_by_role("button", name="Copy new API key").click()
            member.get_by_text("Copied", exact=True).wait_for()
            listed = member.evaluate("async () => (await fetch('/api/api-keys')).json()")
            key = next(row for row in listed if row["name"] == "Milestone 5 UI verification")
            key_id = key["id"]
            assert "key" not in key and raw not in str(listed)
            assert member.evaluate("(raw) => [...Object.values(localStorage), ...Object.values(sessionStorage), location.href].every(value => !value.includes(raw))", raw)
            member.get_by_role("button", name="I saved the key").click()
            assert member.get_by_label("New API key, shown once").count() == 0
            member.get_by_role("button", name="Revoke", exact=True).click()
            member.keyboard.press("Escape")
            assert member.get_by_role("alertdialog").count() == 0
            member.get_by_role("button", name="Revoke", exact=True).click()
            member.get_by_role("alertdialog").get_by_role("button", name="Revoke key").click()
            member.get_by_text("Revoked", exact=True).wait_for()
            member.reload(wait_until="networkidle")
            assert member.get_by_label("New API key, shown once").count() == 0
            member.get_by_role("button", name="Open navigation").click()
            member.get_by_role("button", name="Audit log").click()
            member.get_by_role("heading", name="Audit log").wait_for()
            member.get_by_text("No activity on this page").wait_for()
            member.get_by_role("button", name="Open navigation").click()
            member.get_by_role("button", name="Sign out").click()
            member.get_by_role("button", name="Sign in").wait_for()
            member_context.close()

            admin.get_by_role("button", name="Servers", exact=True).click()
            card = admin.locator("section").filter(has=admin.get_by_role("heading", name=inventory["name"], exact=True))
            card.get_by_role("button", name="Disable").click()
            upstream_disabled = True
            card.get_by_text("Disabled", exact=True).wait_for()
            card.get_by_role("button", name="Exposed tools").click()
            assert card.get_by_text("No tools currently available.").count() > 0
            card.get_by_role("button", name="Enable").click()
            upstream_disabled = False
            card.get_by_text("Connected", exact=True).wait_for()
            assert card.get_by_text(inventory["tools"][0]["original_name"], exact=False).count() > 0

            admin.get_by_role("button", name="Audit log").click()
            admin.get_by_role("heading", name="Audit log").wait_for()
            admin.locator("tbody tr").first.wait_for()
            admin.screenshot(path=str(SCREENSHOTS / "audit-desktop.png"), full_page=True)
            admin.get_by_role("button", name="Members", exact=True).click()
            members = admin.evaluate("async () => (await fetch('/api/members')).json()")
            new_member = next(row for row in members if row["email"] == member_email)
            member_id = new_member["id"]
            row = admin.get_by_text(member_email, exact=True).locator("..").locator("..")
            row.get_by_role("button", name="Deactivate").click()
            admin.get_by_role("alertdialog").get_by_role("button", name="Deactivate member").click()
            admin.get_by_text("Inactive", exact=False).first.wait_for()
            admin.get_by_role("button", name="Sign out").click()
            admin.get_by_role("button", name="Sign in").wait_for()
            print(f"Browser flows passed. Test member ID: {member_id}; revoked key ID: {key_id}; inventory server ID: {upstream_id}.")
            print(f"Screenshots: {SCREENSHOTS}")
        finally:
            if upstream_disabled and upstream_id:
                # Restore even if a UI assertion fails. Uses the existing admin session.
                token = admin_context.cookies()
                csrf = next((cookie["value"] for cookie in token if cookie["name"] == "bridgecart_csrf"), None)
                if csrf:
                    response = admin_context.request.patch(
                        BASE + f"/api/servers/{upstream_id}",
                        data=json.dumps({"enabled": True}),
                        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
                    )
                    if response.status != 200:
                        print("WARNING: inventory restoration requires manual attention")
            browser.close()


if __name__ == "__main__":
    main()
