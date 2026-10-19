"""Alembic environment: migrations run synchronously over psycopg 3 against the URL in
the settings (or the one a test fixture passes as `sqlalchemy.url`)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from plumbline.settings import get_settings

config = context.config
url = config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_offline() -> None:
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
