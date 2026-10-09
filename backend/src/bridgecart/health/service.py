from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def database_is_ready(engine: AsyncEngine, timeout: float) -> bool:
    import asyncio

    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except (Exception, TimeoutError):
        return False
    return True
