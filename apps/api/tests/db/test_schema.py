"""Migration 0002: it reverses cleanly, its checks list every enum value, and row-level
security keeps tenants apart."""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from plumbline.core.stream import AnswerStatus
from plumbline.core.types import DemoTier, Jurisdiction, Language, ProvisionStatus

pytestmark = pytest.mark.db

API_DIR = Path(__file__).resolve().parents[2]
TABLES = {
    "tenants",
    "documents",
    "chunks",
    "ingestion_jobs",
    "queries",
    "eval_runs",
    "eval_results",
    "settings",
}
PUBLIC = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _migration() -> ModuleType:
    path = API_DIR / "migrations" / "versions" / "0002_schema.py"
    spec = importlib.util.spec_from_file_location("migration_0002", path)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


def _tables(engine: Engine) -> set[str]:
    engine.dispose()  # a fresh connection sees the schema the migration just changed
    return set(inspect(engine).get_table_names())


def test_migrations_upgrade_downgrade_and_upgrade_again(database_url: str, engine: Engine) -> None:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    assert _tables(engine) >= TABLES
    command.downgrade(config, "base")
    assert not _tables(engine) & TABLES
    command.upgrade(config, "head")
    assert _tables(engine) >= TABLES


@pytest.mark.parametrize(
    ("constant", "enum"),
    [
        ("JURISDICTIONS", Jurisdiction),
        ("LANGUAGES", Language),
        ("PROVISION_STATUSES", ProvisionStatus),
        ("TIERS", DemoTier),
        ("ANSWER_STATUSES", AnswerStatus),
    ],
)
def test_the_checks_list_every_enum_value(constant: str, enum: type[StrEnum]) -> None:
    written = getattr(_migration(), constant)
    assert written == "(" + ", ".join(f"'{member.value}'" for member in enum) + ")"


@pytest.fixture
def tenants(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """Two tenants, each with one document, beside one public document."""
    alice, bob = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as connection:
        for tenant in (alice, bob):
            connection.execute(
                text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'Test')"),
                {"id": tenant, "slug": f"t-{tenant.hex}"},
            )
        for tenant in (PUBLIC, alice, bob):
            connection.execute(
                text(
                    "INSERT INTO documents (id, tenant_id, law, jurisdiction, language, edition,"
                    " sha256, parser, page_count) VALUES (:id, :tenant, 'fl-stat-83', 'florida',"
                    " 'en', '2026', repeat('0', 64), 'test', 1)"
                ),
                {"id": f"doc-{uuid.uuid4().hex}", "tenant": tenant},
            )
    return alice, bob


def _act_as(connection: Connection, tenant: uuid.UUID | None) -> None:
    """What the application does at the start of every transaction."""
    connection.execute(text("SET LOCAL ROLE plumbline_app"))
    if tenant:
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant)}
        )


def _visible_tenants(connection: Connection) -> set[uuid.UUID]:
    return set(connection.execute(text("SELECT tenant_id FROM documents")).scalars())


def _insert_query(connection: Connection, tenant: uuid.UUID) -> None:
    connection.execute(
        text(
            "INSERT INTO queries (tenant_id, request_id, question, tier)"
            " VALUES (:tenant, :request, 'q', 'full')"
        ),
        {"tenant": tenant, "request": f"req_{uuid.uuid4().hex}"},
    )


def _insert_is_refused(engine: Engine, acting: uuid.UUID | None, owner: uuid.UUID) -> None:
    with engine.connect() as connection:
        _act_as(connection, acting)
        with pytest.raises(DBAPIError, match="row-level security"):
            _insert_query(connection, owner)
        connection.rollback()


def test_a_tenant_sees_its_own_rows_and_the_public_corpus_only(
    engine: Engine, tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    alice, bob = tenants
    with engine.begin() as connection:
        _act_as(connection, alice)
        assert _visible_tenants(connection) == {alice, PUBLIC}
    with engine.begin() as connection:
        _act_as(connection, bob)
        assert alice not in _visible_tenants(connection)


def test_a_tenant_writes_its_own_rows_only(
    engine: Engine, tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    alice, bob = tenants
    with engine.begin() as connection:
        _act_as(connection, bob)
        _insert_query(connection, bob)
    _insert_is_refused(engine, bob, alice)
    # The public corpus and other tenants' rows match nothing for an update.
    with engine.begin() as connection:
        _act_as(connection, bob)
        updated = connection.execute(
            text("UPDATE documents SET parser = 'tampered' WHERE tenant_id IN (:a, :p)"),
            {"a": alice, "p": PUBLIC},
        )
        assert updated.rowcount == 0


def test_without_a_tenant_only_the_public_corpus_is_readable_and_nothing_is_writable(
    engine: Engine, tenants: tuple[uuid.UUID, uuid.UUID]
) -> None:
    with engine.begin() as connection:
        _act_as(connection, None)
        assert _visible_tenants(connection) == {PUBLIC}
    _insert_is_refused(engine, None, PUBLIC)
