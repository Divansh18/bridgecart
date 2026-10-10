import asyncio

import pytest
from pydantic import ValidationError

from bridgecart.auth.rate_limit import LoginLimiter
from bridgecart.auth.schemas import AcceptInvitationInput, ApiKeyInput, InvitationInput
from bridgecart.auth.security import hash_password, new_token, token_hash, verify_password
from bridgecart.core.config import Settings


def test_password_and_credential_primitives() -> None:
    password = "long private test password"
    encoded = hash_password(password)
    assert password not in encoded
    assert verify_password(password, encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password(password, "malformed")
    raw = new_token("bck_")
    assert raw.startswith("bck_")
    assert raw not in token_hash("api-key", raw)
    assert token_hash("api-key", raw) != token_hash("session", raw)


def test_input_and_cookie_configuration() -> None:
    assert InvitationInput(email=" Member@Example.COM ").email == "member@example.com"
    for invalid in ("bad", "user @example.com"):
        with pytest.raises(ValidationError):
            InvitationInput(email=invalid)
    with pytest.raises(ValidationError):
        AcceptInvitationInput(token="x" * 40, password="short")
    with pytest.raises(ValidationError):
        ApiKeyInput(name="   ")
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+asyncpg://u:p@localhost/db", stage="production")
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+asyncpg://u:p@localhost/db", cookie_samesite="none")


@pytest.mark.asyncio
async def test_login_limiter_is_bounded_and_resets() -> None:
    limiter = LoginLimiter(max_failures=2)
    assert await limiter.allow_attempt("client:user")
    assert await limiter.allow_attempt("client:user")
    assert not await limiter.allow_attempt("client:user")
    assert await limiter.allow_attempt("other:user")
    await limiter.succeeded("client:user")
    assert await limiter.allow_attempt("client:user")
    concurrent = await asyncio.gather(*(limiter.allow_attempt("parallel:user") for _ in range(20)))
    assert sum(concurrent) == 2
