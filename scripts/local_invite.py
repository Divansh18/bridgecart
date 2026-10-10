"""Private local invitation handoff; tokens go to a 0600 file, never stdout."""

import argparse
import getpass
import os
from pathlib import Path

from verify_backend_live import checked, client, login, secret_value


def create(email: str, destination: Path) -> None:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output, client() as admin:
            csrf = login(
                admin,
                secret_value("bridgecart-initial-admin", "admin-email"),
                secret_value("bridgecart-initial-admin", "admin-password"),
            )
            invitation = checked(
                admin.post(
                    "/invitations",
                    headers={"X-CSRF-Token": csrf},
                    json={"email": email},
                ),
                201,
            )
            output.write(str(invitation["token"]) + "\n")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    print(
        f"Invitation for {email} saved privately to {destination}; expires at {invitation['expires_at']}."
    )


def accept(source: Path) -> None:
    if source.stat().st_mode & 0o077:
        raise RuntimeError("Invitation file must not be readable by group or others")
    token = source.read_text().strip()
    password = getpass.getpass("New member password (12..128 characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise RuntimeError("Passwords did not match")
    with client() as anonymous:
        user = checked(
            anonymous.post(
                "/auth/invitations/accept", json={"token": token, "password": password}
            ),
            201,
        )
    print(
        f"Invitation accepted for {user['email']}; remove the used token file when ready."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create_command = commands.add_parser("create")
    create_command.add_argument("email")
    create_command.add_argument("token_file", type=Path)
    accept_command = commands.add_parser("accept")
    accept_command.add_argument("token_file", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        create(args.email, args.token_file)
    else:
        accept(args.token_file)


if __name__ == "__main__":
    main()
