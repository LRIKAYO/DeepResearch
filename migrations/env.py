import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from researchflow.backend.projects import Base
from researchflow.backend import research_sessions  # noqa: F401


config = context.config
target_metadata = Base.metadata


def require_database_url() -> str:
    database_url = os.getenv("RESEARCHFLOW_DATABASE_URL")
    if not database_url:
        raise RuntimeError("Missing required environment variable: RESEARCHFLOW_DATABASE_URL")
    return database_url


def run_migrations_offline() -> None:
    context.configure(
        url=require_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = require_database_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
