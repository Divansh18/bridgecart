from fastapi import APIRouter, Request

from bridgecart.auth import service as auth_service
from bridgecart.auth.dependencies import Admin, AdminMutation, Db
from bridgecart.auth.routes import user_view
from bridgecart.auth.schemas import InvitationInput
from bridgecart.members import service

router = APIRouter(tags=["members"])


@router.post("/invitations", status_code=201)
async def invite(body: InvitationInput, request: Request, db: Db, admin: AdminMutation) -> dict[str, object]:
    invitation, token = await auth_service.create_invitation(
        db, body.email, admin.user.id, request.app.state.settings.invitation_ttl_hours
    )
    return {"id": invitation.id, "email": invitation.email, "token": token, "expires_at": invitation.expires_at}


@router.get("/members")
async def members(db: Db, admin: Admin) -> list[dict[str, object]]:
    return [user_view(user) for user in await service.list_members(db)]


@router.post("/members/{user_id}/deactivate")
async def deactivate(user_id: int, db: Db, admin: AdminMutation) -> dict[str, object]:
    return user_view(await service.deactivate_member(db, user_id))
