"""Idempotent initial admin creation after migrations; reads Secret-backed env vars."""

import asyncio
import os

from sqlalchemy import func, select

from bridgecart.auth.models import User
from bridgecart.auth.schemas import EmailModel
from bridgecart.auth.security import hash_password
from bridgecart.core.config import Settings
from bridgecart.db.session import create_session_factory


async def provision() -> str:
    email = EmailModel(email=os.environ["BRIDGECART_INITIAL_ADMIN_EMAIL"]).email
    password = os.environ["BRIDGECART_INITIAL_ADMIN_PASSWORD"]
    if len(password) < 16 or len(password) > 128:
        raise RuntimeError("Initial admin password must contain 16..128 characters")
    settings = Settings()  # type: ignore[call-arg]
    engine, factory = create_session_factory(settings)
    try:
        async with factory() as db:
            existing = await db.scalar(select(User).where(User.email == email))
            if existing:
                if existing.role != "admin" or not existing.active:
                    raise RuntimeError("Configured initial admin is not an active admin")
                return "existing"
            count = await db.scalar(select(func.count()).select_from(User))
            if count:
                raise RuntimeError("Users already exist; initial admin cannot be changed by bootstrap")
            db.add(User(email=email, password_hash=await asyncio.to_thread(hash_password, password), role="admin"))
            await db.commit()
            return "created"
    finally:
        await engine.dispose()


def main() -> None:
    print("Initial admin:", asyncio.run(provision()))


if __name__ == "__main__":
    main()
