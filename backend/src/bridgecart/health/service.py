from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def database_is_ready(engine: AsyncEngine, timeout: float) -> bool:
    import asyncio

    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as connection:
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                if revision != "20261012_01":
                    return False
    except (Exception, TimeoutError):
        return False
    return True
