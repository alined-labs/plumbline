"""Shared fixtures. Frozen: a change needs a brain block.

Tests never call a model: CACHE_MODE is forced to replay before anything reads the
settings, and fixtures build Settings without the developer's .env. Tests that need
Postgres take the `database_url` fixture: a throwaway database on the local Postgres
(`make up`), migrated to head and dropped afterwards. When Postgres is unreachable those
tests skip, unless PLUMBLINE_REQUIRE_DB=1 (the hub and CI) makes that a failure.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from plumbline.api.app import create_app
from plumbline.core.types import CacheMode
from plumbline.settings import Settings, get_settings

os.environ["CACHE_MODE"] = CacheMode.REPLAY.value
API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _replay_only(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CACHE_MODE", CacheMode.REPLAY.value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, cache_mode=CacheMode.REPLAY, stub_delay_ms=0)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def migrate(url: str, revision: str = "head") -> None:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, revision)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    base = make_url(os.environ.get("TEST_DATABASE_URL") or Settings(_env_file=None).database_url)
    name = f"plumbline_test_{secrets.token_hex(4)}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError as exc:
        admin.dispose()
        if os.environ.get("PLUMBLINE_REQUIRE_DB") == "1":
            pytest.fail(f"Postgres is unreachable and PLUMBLINE_REQUIRE_DB=1: {exc}")
        pytest.skip("Postgres is unreachable (make up starts it)")
    url = base.set(database=name).render_as_string(hide_password=False)
    try:
        migrate(url)
        yield url
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
