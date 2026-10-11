"""Admin registry and session-authenticated audit views."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from bridgecart.auth.dependencies import Admin, AdminMutation, Db, SessionUser
from bridgecart.gateway.models import ToolAudit, UpstreamServer
from bridgecart.gateway.security import cipher, validate_credential, validate_url

router = APIRouter(tags=["gateway"])


class ServerInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=500)
    enabled: bool = True
    auth_type: str = "none"
    header_name: str | None = None
    credential: SecretStr | None = None


class ServerEdit(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    auth_type: str | None = None
    header_name: str | None = None
    credential: SecretStr | None = None


def server_view(
    server: UpstreamServer, status: str, reason: str | None, tools: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "id": server.id,
        "name": server.name,
        "url": server.url,
        "enabled": server.enabled,
        "auth_type": server.auth_type,
        "header_name": server.header_name,
        "has_credential": server.credential_encrypted is not None,
        "status": status,
        "reason": reason,
        "tools": tools,
    }


@router.get("/servers")
async def list_servers(request: Request, admin: Admin) -> list[dict[str, object]]:
    catalog = await request.app.state.gateway.catalog()
    return [
        server_view(
            server,
            discovery.status,
            discovery.reason,
            [
                {
                    "name": name,
                    "original_name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "output_schema": tool.output_schema,
                    "annotations": tool.annotations.model_dump(by_alias=True) if tool.annotations else None,
                }
                for name, tool in discovery.tools.items()
            ],
        )
        for server, discovery in catalog
    ]


@router.post("/servers", status_code=201)
async def add_server(body: ServerInput, request: Request, db: Db, admin: AdminMutation) -> dict[str, object]:
    settings = request.app.state.settings
    url = validate_url(body.url, settings)
    secret = body.credential.get_secret_value() if body.credential else None
    validate_credential(body.auth_type, body.header_name, secret)
    existing = await db.scalar(
        select(UpstreamServer).where(UpstreamServer.url == url, UpstreamServer.removed_at.is_(None))
    )
    if existing:
        raise HTTPException(409, "An active registration already uses this URL")
    row = UpstreamServer(
        id=str(uuid.uuid4()),
        name=body.name,
        url=url,
        enabled=body.enabled,
        auth_type=body.auth_type,
        header_name=body.header_name,
        credential_encrypted=cipher(settings).encrypt(secret.encode()) if secret else None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(row)
    await db.commit()
    return server_view(
        row, "Disabled" if not row.enabled else "Unreachable", "not_discovered" if row.enabled else None, []
    )


@router.patch("/servers/{server_id}")
async def edit_server(
    server_id: str, body: ServerEdit, request: Request, db: Db, admin: AdminMutation
) -> dict[str, object]:
    row = await db.get(UpstreamServer, server_id)
    if row is None or row.removed_at is not None:
        raise HTTPException(404, "Server not found")
    settings = request.app.state.settings
    if body.url is not None:
        url = validate_url(body.url, settings)
        existing = await db.scalar(
            select(UpstreamServer).where(
                UpstreamServer.url == url,
                UpstreamServer.id != row.id,
                UpstreamServer.removed_at.is_(None),
            )
        )
        if existing:
            raise HTTPException(409, "An active registration already uses this URL")
        row.url = url
    if body.name is not None:
        row.name = body.name
    if body.enabled is not None:
        row.enabled = body.enabled
    auth_type = body.auth_type if body.auth_type is not None else row.auth_type
    if auth_type not in {"none", "bearer", "header"}:
        raise HTTPException(422, "Unsupported upstream authentication type")
    header_name = body.header_name if "header_name" in body.model_fields_set else row.header_name
    secret = body.credential.get_secret_value() if body.credential else None
    if auth_type == "none":
        validate_credential("none", body.header_name if "header_name" in body.model_fields_set else None, secret)
        row.auth_type, row.header_name, row.credential_encrypted = "none", None, None
    else:
        if secret is None and row.credential_encrypted is None:
            raise HTTPException(422, "Upstream credential is required")
        if secret is not None:
            validate_credential(auth_type, header_name, secret)
            row.credential_encrypted = cipher(settings).encrypt(secret.encode())
        elif auth_type == "header":
            from bridgecart.gateway.security import validate_header

            validate_header(header_name)
        elif header_name:
            raise HTTPException(422, "Header name is only valid for custom-header authentication")
        row.auth_type, row.header_name = auth_type, header_name
    row.updated_at = datetime.now(UTC)
    await db.commit()
    request.app.state.gateway.invalidate(row.id)
    return server_view(
        row, "Disabled" if not row.enabled else "Unreachable", "not_discovered" if row.enabled else None, []
    )


@router.delete("/servers/{server_id}", status_code=204)
async def remove_server(server_id: str, request: Request, db: Db, admin: AdminMutation) -> None:
    row = await db.get(UpstreamServer, server_id)
    if row is None or row.removed_at is not None:
        raise HTTPException(404, "Server not found")
    row.enabled = False
    row.removed_at = datetime.now(UTC)
    row.credential_encrypted = None
    await db.commit()
    request.app.state.gateway.invalidate(row.id)


@router.get("/audit")
async def list_audit(
    db: Db,
    actor: SessionUser,
    page: int = Query(1, ge=1, le=100000),
    per_page: int = Query(20, ge=1, le=100),
    user_id: int | None = Query(None, gt=0),
) -> list[dict[str, object]]:
    if actor.user.role != "admin" and user_id is not None and user_id != actor.user.id:
        raise HTTPException(403, "Cannot view another member's audit")
    scoped_id = user_id if actor.user.role == "admin" else actor.user.id
    query = select(ToolAudit)
    if scoped_id is not None:
        query = query.where(ToolAudit.user_id == scoped_id)
    rows = (
        await db.scalars(
            query.order_by(ToolAudit.started_at.desc(), ToolAudit.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).all()
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "user_email": row.user_email,
            "api_key_id": row.api_key_id,
            "server_id": row.server_id,
            "server_name": row.server_name,
            "original_tool_name": row.original_tool_name,
            "exposed_tool_name": row.exposed_tool_name,
            "started_at": row.started_at,
            "duration_ms": row.duration_ms,
            "outcome": row.outcome,
            "error_category": row.error_category,
        }
        for row in rows
    ]
