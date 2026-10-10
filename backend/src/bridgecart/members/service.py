from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bridgecart.auth.models import User


async def list_members(db: AsyncSession) -> list[User]:
    return list((await db.scalars(select(User).where(User.role == "member").order_by(User.id))).all())


async def require_member(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None or user.role != "member":
        raise HTTPException(status_code=404, detail="Member not found")
    return user


async def deactivate_member(db: AsyncSession, user_id: int) -> User:
    user = await require_member(db, user_id)
    user.active = False
    await db.commit()
    return user
