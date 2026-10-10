from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bridgecart.auth.models import ApiKey, User, utc_now
from bridgecart.auth.security import new_token, token_hash


def key_view(key: ApiKey) -> dict[str, object]:
    return {
        "id": key.id,
        "user_id": key.user_id,
        "name": key.name,
        "prefix": key.prefix,
        "created_at": key.created_at,
        "revoked_at": key.revoked_at,
    }


async def issue(db: AsyncSession, user: User, creator: User, name: str) -> tuple[ApiKey, str]:
    if not user.active:
        raise HTTPException(status_code=409, detail="Member is inactive")
    raw = new_token("bck_")
    key = ApiKey(
        user_id=user.id,
        created_by=creator.id,
        name=name,
        token_hash=token_hash("api-key", raw),
        prefix=raw[:12],
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return key, raw


async def list_for_user(db: AsyncSession, user_id: int) -> list[ApiKey]:
    return list((await db.scalars(select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.id))).all())


async def revoke(db: AsyncSession, user_id: int, key_id: int) -> None:
    key = await db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if key.revoked_at is None:
        key.revoked_at = utc_now()
        await db.commit()
