"""Registry input policy and encrypted upstream credentials."""

import ipaddress
import re
import socket
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from fastapi import HTTPException

from bridgecart.core.config import Settings

SAFE_HEADER = re.compile(r"^X-[A-Za-z0-9-]{1,76}$")
FORBIDDEN_HEADERS = {
    "host",
    "connection",
    "content-length",
    "transfer-encoding",
    "upgrade",
    "proxy-authorization",
    "proxy-authenticate",
    "te",
    "trailer",
    "keep-alive",
    "authorization",
    "cookie",
    "set-cookie",
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
}


def _public_https_destination(host: str, scheme: str, port: int | None) -> bool:
    try:
        # libc accepts abbreviated/hex IPv4 forms that ipaddress rejects (for example 127.1).
        socket.inet_aton(host)
    except OSError:
        pass
    else:
        return False
    labels = host.split(".")
    return (
        scheme == "https"
        and port in (None, 443)
        and len(labels) >= 2
        and not host.endswith(
            (".local", ".localhost", ".internal", ".svc", ".cluster.local", ".test", ".invalid", ".example", ".arpa")
        )
        and all(len(label) <= 63 and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) for label in labels)
    )


def validate_url(value: str, settings: Settings) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise HTTPException(422, "IP-literal upstream URLs are forbidden")
        internal = (
            parsed.scheme in {"http", "https"}
            and host.split(".")[0].endswith("-mcp")
            and bool(re.fullmatch(r"[a-z0-9.-]+", host))
            and parsed.port is not None
            and parsed.path == "/mcp"
            and value in settings.gateway_allowed_urls.split(",")
        )
        public = settings.gateway_allow_public_https and _public_https_destination(host, parsed.scheme, parsed.port)
        safe = (
            bool(host)
            and host != "localhost"
            and parsed.username is None
            and parsed.password is None
            and parsed.path not in ("", "/")
            and not parsed.query
            and not parsed.fragment
            and (internal or public)
        )
    except ValueError:
        safe = False
    if not safe:
        raise HTTPException(422, "Upstream URL is not an approved MCP destination")
    return value


def validate_header(name: str | None) -> str:
    if (
        not name
        or not SAFE_HEADER.fullmatch(name)
        or name.lower() in FORBIDDEN_HEADERS
        or name.lower().startswith(("x-forwarded-", "x-original-", "x-rewrite-"))
        or name.lower() == "x-http-method-override"
    ):
        raise HTTPException(422, "Unsafe upstream header name")
    return name


def validate_credential(auth_type: str, header_name: str | None, credential: str | None) -> None:
    if auth_type not in {"none", "bearer", "header"}:
        raise HTTPException(422, "Unsupported upstream authentication type")
    if auth_type == "none" and (header_name or credential):
        raise HTTPException(422, "No credential is permitted for this authentication type")
    if auth_type != "none" and not credential:
        raise HTTPException(422, "Upstream credential is required")
    if auth_type == "header":
        validate_header(header_name)
    elif header_name:
        raise HTTPException(422, "Header name is only valid for custom-header authentication")
    if credential and (len(credential) > 1024 or any(c in credential for c in "\r\n\0")):
        raise HTTPException(422, "Invalid upstream credential")


def cipher(settings: Settings) -> Fernet:
    if settings.upstream_encryption_key is None:
        raise RuntimeError("Upstream encryption key is missing")
    return Fernet(settings.upstream_encryption_key.get_secret_value().encode())
