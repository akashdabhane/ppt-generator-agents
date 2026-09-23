"""Alembic environment. The database URL comes from app settings (backend/.env), or `-x url=...` on the CLI."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import settings
from app.database.session import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tables managed outside the ORM (the pgvector adapter creates its own) must never be touched by migrations
UNMANAGED_TABLES = {"pgvector_embeddings"}


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and name in UNMANAGED_TABLES)


def _url() -> str:
    url = context.get_x_argument(as_dictionary=True).get("url") or config.attributes.get("url") or settings.DATABASE_URL
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, render_as_batch=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:  # called from app.database.migrate with an open connection
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True,
                          include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()
        return

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as conn:
        # render_as_batch lets ALTERs work on SQLite too
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True,
                          include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
