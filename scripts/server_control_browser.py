"""Browser-only checks launched by verify_server_control with credentials on stdin."""

import json
import sys
from typing import Any

from playwright.sync_api import sync_playwright

BASE = "http://app.bridgecart.local:8088"


def login(page: Any, email: str, password: str) -> None:
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.get_by_label("Email address").fill(email)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("heading", name="Your workspace at a glance").wait_for(
        timeout=20000
    )


def disabled_chat(
    admin_email: str, admin_password: str, member_email: str, member_password: str
) -> dict[str, str]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--host-resolver-rules=MAP app.bridgecart.local 127.0.0.1"],
        )
        try:
            admin = browser.new_page()
            member = browser.new_page()
            login(admin, admin_email, admin_password)
            login(member, member_email, member_password)
            admin.goto(BASE + "/servers", wait_until="domcontentloaded")
            heading = admin.get_by_role("heading", name="Demo Shipping")
            heading.wait_for()
            assert "Disabled" in heading.locator("xpath=..").inner_text()
            member.goto(BASE + "/chat", wait_until="domcontentloaded")
            member.locator("#chat-message").fill(
                "Check seeded demo inventory for SKU BRIDGECART-DEMO-001. "
                "Can you also estimate standard shipping to PIN 560001 for 1.00 kg? "
                "If that tool is unavailable, say so clearly. Read only: do not create or update anything."
            )
            with member.expect_response(
                lambda response: (
                    response.url.endswith("/api/chat")
                    and response.request.method == "POST"
                ),
                timeout=70000,
            ) as pending:
                member.get_by_role("button", name="Send message").click()
            response = pending.value
            if response.status != 200:
                raise RuntimeError(f"Dashboard chat returned HTTP {response.status}")
            body = response.json()
            assert not any(
                "shipping" in str(trace["server"]).lower() for trace in body["traces"]
            )
            assert any(
                "inventory" in str(trace["server"]).lower() for trace in body["traces"]
            )
            assert "shipping" in body["reply"].lower()
            member.get_by_text("Audit reference:", exact=False).wait_for(timeout=10000)
            return {"correlation_id": str(body["correlation_id"])}
        finally:
            browser.close()


def unreachable(admin_email: str, admin_password: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--host-resolver-rules=MAP app.bridgecart.local 127.0.0.1"],
        )
        try:
            page = browser.new_page()
            login(page, admin_email, admin_password)
            page.goto(BASE + "/servers", wait_until="domcontentloaded")
            heading = page.get_by_role("heading", name="Demo Shipping")
            heading.wait_for(timeout=20000)
            assert "Unreachable" in heading.locator("xpath=..").inner_text()
        finally:
            browser.close()


def main() -> None:
    request = json.load(sys.stdin)
    if request["mode"] == "disabled-chat":
        result = disabled_chat(
            request["admin_email"],
            request["admin_password"],
            request["member_email"],
            request["member_password"],
        )
        print(json.dumps(result))
    elif request["mode"] == "unreachable":
        unreachable(request["admin_email"], request["admin_password"])
        print(json.dumps({"status": "Unreachable"}))
    else:
        raise RuntimeError("Unknown browser check")


if __name__ == "__main__":
    main()
