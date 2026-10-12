"""Cookie and CSRF authenticated, bounded chat endpoint."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from bridgecart.auth.dependencies import CsrfUser
from bridgecart.chat.service import chat_turn

router = APIRouter(prefix="/chat", tags=["chat"])


class HistoryMessage(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=2000)


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=10)


@router.post("")
async def send_chat(body: ChatInput, request: Request, actor: CsrfUser) -> dict[str, object]:
    if request.headers.get("content-length", "0").isdigit() and int(request.headers.get("content-length", "0")) > 32768:
        raise HTTPException(413, "Chat request is too large")
    if any(item.role not in {"user", "assistant"} for item in body.history):
        raise HTTPException(422, "Invalid chat history role")
    if not body.message.strip():
        raise HTTPException(422, "Chat message must not be blank")
    if request.app.state.gateway is None or getattr(request.app.state, "chat_client", None) is None:
        raise HTTPException(503, "Chat is not configured")
    return await chat_turn(request.app, actor, body.message, body.history)
