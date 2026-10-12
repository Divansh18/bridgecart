"""Short-lived, session-bound credentials for the server-side chat MCP client."""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bridgecart.auth.dependencies import SessionActor
from bridgecart.auth.models import LoginSession, User, utc_now
from bridgecart.core.config import Settings

LIFETIME_SECONDS = 120


@dataclass
class DelegatedActor:
    user: User
    session_id: int
    correlation_id: str


def _signing_key(settings: Settings) -> bytes:
    if settings.upstream_encryption_key is None:
        raise RuntimeError("Gateway delegation is not configured")
    root = base64.urlsafe_b64decode(settings.upstream_encryption_key.get_secret_value())
    return hmac.digest(root, b"bridgecart-chat-delegation-v1", hashlib.sha256)


def issue_delegation(settings: Settings, actor: SessionActor, correlation_id: str) -> str:
    expires = min(int(time.time()) + LIFETIME_SECONDS, int(actor.session.expires_at.timestamp()))
    body = json.dumps(
        {"v": 1, "u": actor.user.id, "s": actor.session.id, "e": expires, "c": correlation_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(body).rstrip(b"=")
    signature = hmac.digest(_signing_key(settings), encoded, hashlib.sha256)
    return "bcd_" + encoded.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


async def authenticate_delegation(token: str, settings: Settings, db: AsyncSession) -> DelegatedActor:
    invalid = HTTPException(401, "Invalid delegated credential")
    if not token.startswith("bcd_") or len(token) > 1024:
        raise invalid
    try:
        encoded, signature = token[4:].split(".", 1)
        expected = hmac.digest(_signing_key(settings), encoded.encode(), hashlib.sha256)
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise invalid
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if (
            payload.get("v") != 1
            or type(payload.get("u")) is not int
            or type(payload.get("s")) is not int
            or type(payload.get("e")) is not int
            or type(payload.get("c")) is not str
            or len(payload["c"]) != 36
            or payload["e"] <= int(time.time())
        ):
            raise invalid
    except (ValueError, KeyError, TypeError, UnicodeError, AttributeError):
        raise invalid from None
    row = await db.execute(
        select(LoginSession, User)
        .join(User, User.id == LoginSession.user_id)
        .where(LoginSession.id == payload["s"], User.id == payload["u"])
    )
    found = row.one_or_none()
    if found is None or found[0].revoked_at is not None or found[0].expires_at <= utc_now() or not found[1].active:
        raise invalid
    return DelegatedActor(user=found[1], session_id=found[0].id, correlation_id=payload["c"])
