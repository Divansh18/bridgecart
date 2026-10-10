from fastapi import APIRouter, HTTPException, Request, Response

from bridgecart.auth import service
from bridgecart.auth.dependencies import CsrfUser, Db, SessionUser
from bridgecart.auth.models import User
from bridgecart.auth.schemas import AcceptInvitationInput, LoginInput

router = APIRouter(prefix="/auth", tags=["auth"])


def user_view(user: User) -> dict[str, object]:
    return {"id": user.id, "email": user.email, "role": user.role, "active": user.active}


@router.post("/login")
async def login(body: LoginInput, request: Request, response: Response, db: Db) -> dict[str, object]:
    limiter = request.app.state.login_limiter
    key = f"{request.client.host if request.client else 'unknown'}:{body.email}"
    if not await limiter.allow_attempt(key):
        raise HTTPException(status_code=429, detail="Too many login attempts; try again later")
    user, session_token, csrf_token = await service.login(
        db, body.email, body.password, request.app.state.settings.session_ttl_hours
    )
    await limiter.succeeded(key)
    settings = request.app.state.settings
    cookie_options = {
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "max_age": settings.session_ttl_hours * 3600,
        "path": "/",
    }
    response.set_cookie("bridgecart_session", session_token, httponly=True, **cookie_options)
    response.set_cookie("bridgecart_csrf", csrf_token, httponly=False, **cookie_options)
    return {"user": user_view(user)}


@router.post("/logout")
async def logout(response: Response, db: Db, actor: CsrfUser) -> dict[str, str]:
    await service.revoke_session(db, actor.session)
    response.delete_cookie("bridgecart_session", path="/")
    response.delete_cookie("bridgecart_csrf", path="/")
    return {"status": "logged_out"}


@router.get("/me")
async def me(actor: SessionUser) -> dict[str, object]:
    return user_view(actor.user)


@router.post("/invitations/accept", status_code=201)
async def accept_invitation(body: AcceptInvitationInput, db: Db) -> dict[str, object]:
    user = await service.accept_invitation(db, body.token, body.password)
    return user_view(user)
