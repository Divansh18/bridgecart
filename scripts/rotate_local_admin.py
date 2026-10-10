"""Rotate the local demo administrator password without exposing it in argv or logs."""

import base64
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

CONTEXT = "k3d-bridgecart"
NAMESPACE = "bridgecart"
SECRET = "bridgecart-store-credentials"
USER = "bridgecart-admin"


def kubectl(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", "--context", CONTEXT, "-n", NAMESPACE, *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )


def main() -> None:
    password = secrets.token_urlsafe(48)
    patch = {"data": {"wordpress-admin-password": base64.b64encode(password.encode()).decode()}}
    with tempfile.TemporaryDirectory(prefix="bridgecart-rotate-") as temporary:
        path = Path(temporary) / "patch.json"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(patch, handle)
        kubectl("patch", "secret", SECRET, "--type=merge", "--patch-file", str(path))

    php = (
        '$_SERVER["HTTP_HOST"]="shop.bridgecart.local"; '
        '$_SERVER["REQUEST_URI"]="/"; '
        'require "/var/www/html/wp-load.php"; '
        f'$user=get_user_by("login", "{USER}"); '
        'if (!$user) {fwrite(STDERR, "Admin user missing\n"); exit(1);} '
        'wp_set_password(trim(stream_get_contents(STDIN)), $user->ID); '
        'echo "Local admin password rotated\n";'
    )
    kubectl("exec", "-i", "deploy/bridgecart-wordpress", "--", "php", "-r", php, input_text=password)
    print("Local admin credential rotated.")


if __name__ == "__main__":
    main()
