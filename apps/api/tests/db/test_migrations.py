import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.db


def test_migrations_install_the_search_extensions(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        installed = set(connection.execute(text("SELECT extname FROM pg_extension")).scalars())
    engine.dispose()
    assert {"vector", "pg_search"} <= installed
