"""Database operations for sessions and single-use invitations."""

import asyncio
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bridgecart.auth.models import Invitation, LoginSession, User, utc_now
from bridgecart.auth.security import hash_password, new_token, token_hash, verify_password

INVALID_LOGIN = HTTPException(status_code=401, detail="Invalid credentials")
INVALID_INVITATION = HTTPException(status_code=400, detail="Invitation is invalid or expired")
DUMMY_HASH = hash_password("bridgecart dummy verification only")


async def login(db: AsyncSession, email: str, password: str, ttl_hours: int) -> tuple[User, str, str]:
    user = await db.scalar(select(User).where(User.email == email))
    verified = await asyncio.to_thread(verify_password, password, user.password_hash if user else DUMMY_HASH)
    if user is None or not user.active or not verified:
        raise INVALID_LOGIN
    session_token = new_token("bcs_")
    csrf_token = new_token("bcc_")
    db.add(
        LoginSession(
            user_id=user.id,
            token_hash=token_hash("session", session_token),
            csrf_hash=token_hash("csrf", csrf_token),
            expires_at=utc_now() + timedelta(hours=ttl_hours),
        )
    )
    await db.commit()
    return user, session_token, csrf_token


async def revoke_session(db: AsyncSession, session: LoginSession) -> None:
    session.revoked_at = utc_now()
    await db.commit()


async def create_invitation(db: AsyncSession, email: str, admin_id: int, ttl_hours: int) -> tuple[Invitation, str]:
    if await db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="A member with this email already exists")
    token = new_token("bci_")
    invitation = Invitation(
        email=email,
        token_hash=token_hash("invitation", token),
        created_by=admin_id,
        expires_at=utc_now() + timedelta(hours=ttl_hours),
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return invitation, token


async def accept_invitation(db: AsyncSession, token: str, password: str) -> User:
    invitation = await db.scalar(
        select(Invitation).where(Invitation.token_hash == token_hash("invitation", token)).with_for_update()
    )
    if invitation is None or invitation.accepted_at is not None or invitation.expires_at <= utc_now():
        raise INVALID_INVITATION
    if await db.scalar(select(User.id).where(User.email == invitation.email)) is not None:
        raise INVALID_INVITATION
    user = User(
        email=invitation.email,
        password_hash=await asyncio.to_thread(hash_password, password),
        role="member",
        active=True,
    )
    db.add(user)
    invitation.accepted_at = utc_now()
    await db.commit()
    await db.refresh(user)
    return user
