"""Cookie-only UI access and reusable bearer API-key access are separate."""

import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bridgecart.auth.models import ApiKey, LoginSession, User, utc_now
from bridgecart.auth.security import token_hash
from bridgecart.db.session import get_db_session

Db = Annotated[AsyncSession, Depends(get_db_session)]


@dataclass
class SessionActor:
    user: User
    session: LoginSession


async def current_session(request: Request, db: Db) -> SessionActor:
    raw = request.cookies.get("bridgecart_session")
    if not raw or not raw.startswith("bcs_"):
        raise HTTPException(status_code=401, detail="Authentication required")
    row = await db.execute(
        select(LoginSession, User)
        .join(User, User.id == LoginSession.user_id)
        .where(LoginSession.token_hash == token_hash("session", raw))
    )
    found = row.one_or_none()
    if found is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    session, user = found
    if session.revoked_at is not None or session.expires_at <= utc_now() or not user.active:
        raise HTTPException(status_code=401, detail="Authentication required")
    return SessionActor(user=user, session=session)


SessionUser = Annotated[SessionActor, Depends(current_session)]


async def csrf_session(
    request: Request,
    actor: SessionUser,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> SessionActor:
    cookie = request.cookies.get("bridgecart_csrf")
    if not cookie or not x_csrf_token or not hmac.compare_digest(cookie, x_csrf_token):
        raise HTTPException(status_code=403, detail="CSRF verification failed")
    if not hmac.compare_digest(actor.session.csrf_hash, token_hash("csrf", x_csrf_token)):
        raise HTTPException(status_code=403, detail="CSRF verification failed")
    return actor


CsrfUser = Annotated[SessionActor, Depends(csrf_session)]


async def admin_session(actor: SessionUser) -> SessionActor:
    if actor.user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return actor


Admin = Annotated[SessionActor, Depends(admin_session)]


async def admin_mutation(actor: CsrfUser) -> SessionActor:
    if actor.user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return actor


AdminMutation = Annotated[SessionActor, Depends(admin_mutation)]


async def authenticate_api_key(authorization: str | None, db: AsyncSession) -> User:
    """Reusable for the future gateway; checks revocation and user activity per request."""
    if not authorization or not authorization.startswith("Bearer bck_"):
        raise HTTPException(status_code=401, detail="Invalid API key")
    raw = authorization.removeprefix("Bearer ")
    row = await db.execute(
        select(ApiKey, User)
        .join(User, User.id == ApiKey.user_id)
        .where(ApiKey.token_hash == token_hash("api-key", raw))
    )
    found = row.one_or_none()
    if found is None or found[0].revoked_at is not None or not found[1].active:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return found[1]
