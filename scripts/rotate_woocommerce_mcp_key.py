#!/usr/bin/env python3
"""Rotate the local dedicated WooCommerce API key without printing credentials."""

import base64
import json
import secrets
import subprocess
from pathlib import Path

from provision_woocommerce_mcp import kubectl

ROOT = Path(__file__).resolve().parents[1]
NAME = "bridgecart-woocommerce-api"


def must_run(*args: str, input_bytes: bytes | None = None) -> bytes:
    result = kubectl(*args, input_bytes=input_bytes)
    if result.returncode:
        raise RuntimeError(f"Credential rotation failed during {args[0]} (exit {result.returncode})")
    return result.stdout


def main() -> None:
    resource = json.loads(must_run("get", "secret", NAME, "-o", "json"))
    assert resource["metadata"]["name"] == NAME
    assert set(resource["data"]) == {"consumer-key", "consumer-secret"}
    old_key = base64.b64decode(resource["data"]["consumer-key"]).decode()
    new_key = "ck_" + secrets.token_hex(32)
    new_secret = "cs_" + secrets.token_hex(20)
    php = (ROOT / "scripts/provision_woocommerce_mcp.php").read_text().removeprefix("<?php\n")
    must_run("exec", "-i", "deploy/bridgecart-wordpress", "--", "php", "-r", php,
             input_bytes=json.dumps({"key": new_key, "secret": new_secret}).encode())
    resource["data"]["consumer-key"] = base64.b64encode(new_key.encode()).decode()
    resource["data"]["consumer-secret"] = base64.b64encode(new_secret.encode()).decode()
    resource.pop("status", None)
    must_run("replace", "-f", "-", input_bytes=json.dumps(resource).encode())
    must_run("rollout", "restart", "deployment/bridgecart-woocommerce-mcp")
    must_run("rollout", "status", "deployment/bridgecart-woocommerce-mcp", "--timeout=120s")
    revoke_php = '''require "/var/www/html/wp-load.php";
    $key = trim(stream_get_contents(STDIN));
    $user = get_user_by("login", "bridgecart-mcp");
    global $wpdb;
    $table = $wpdb->prefix . "woocommerce_api_keys";
    $hashed = wc_api_hash($key);
    $row = $wpdb->get_row($wpdb->prepare("SELECT key_id, user_id FROM {$table} WHERE consumer_key = %s", $hashed));
    if (!$row || !$user || (int) $row->user_id !== (int) $user->ID) { exit(1); }
    if ($wpdb->delete($table, array("key_id" => $row->key_id), array("%d")) !== 1) { exit(1); }
    echo "revoked\\n";'''
    must_run("exec", "-i", "deploy/bridgecart-wordpress", "--", "php", "-r", revoke_php,
             input_bytes=old_key.encode())
    print("New dedicated API key is active; previous key revoked. No key values printed.")


if __name__ == "__main__":
    main()
