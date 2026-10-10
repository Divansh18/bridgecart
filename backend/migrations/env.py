import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from bridgecart.auth import models  # noqa: F401  Register model metadata for Alembic.
from bridgecart.core.config import get_settings
from bridgecart.db.base import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", str(get_settings().database_url).replace("%", "%%"))
target_metadata = Base.metadata


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=str(get_settings().database_url), target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async_migrations())
