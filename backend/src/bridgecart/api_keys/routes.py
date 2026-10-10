from fastapi import APIRouter

from bridgecart.api_keys import service
from bridgecart.auth.dependencies import Admin, AdminMutation, CsrfUser, Db, SessionUser
from bridgecart.auth.schemas import ApiKeyInput
from bridgecart.members.service import require_member

router = APIRouter(tags=["api-keys"])


@router.post("/api-keys", status_code=201)
async def create_own(body: ApiKeyInput, db: Db, actor: CsrfUser) -> dict[str, object]:
    key, raw = await service.issue(db, actor.user, actor.user, body.name)
    return service.key_view(key) | {"key": raw}


@router.get("/api-keys")
async def list_own(db: Db, actor: SessionUser) -> list[dict[str, object]]:
    return [service.key_view(key) for key in await service.list_for_user(db, actor.user.id)]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_own(key_id: int, db: Db, actor: CsrfUser) -> None:
    await service.revoke(db, actor.user.id, key_id)


@router.post("/members/{user_id}/api-keys", status_code=201)
async def create_for_member(user_id: int, body: ApiKeyInput, db: Db, admin: AdminMutation) -> dict[str, object]:
    member = await require_member(db, user_id)
    key, raw = await service.issue(db, member, admin.user, body.name)
    return service.key_view(key) | {"key": raw}


@router.get("/members/{user_id}/api-keys")
async def list_for_member(user_id: int, db: Db, admin: Admin) -> list[dict[str, object]]:
    await require_member(db, user_id)
    return [service.key_view(key) for key in await service.list_for_user(db, user_id)]


@router.delete("/members/{user_id}/api-keys/{key_id}", status_code=204)
async def revoke_for_member(user_id: int, key_id: int, db: Db, admin: AdminMutation) -> None:
    await require_member(db, user_id)
    await service.revoke(db, user_id, key_id)
