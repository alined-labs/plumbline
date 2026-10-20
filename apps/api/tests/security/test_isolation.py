"""Tenant isolation, checked on the migrated schema's catalog rather than table by table, so
a migration that adds a table cannot leave it out: every table with a tenant_id is under
forced row-level security with policies keyed on current_tenant(), the application's role
cannot bypass them, and every table it may write without a tenant_id is one we chose.
Lane D's tests in tests/db show the policies at work on rows; these keep them complete.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from plumbline.db.session import APP_ROLE

pytestmark = pytest.mark.db

# Tables the application writes that hold no tenant's data: the demo tier and other
# server settings, and the evaluation runs, which are about the system, not a visitor.
UNTENANTED_WRITABLE = frozenset({"settings", "eval_runs", "eval_results"})


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


def _tenant_tables(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.scalars(
                text(
                    "SELECT table_name FROM information_schema.columns"
                    " WHERE table_schema = 'public' AND column_name = 'tenant_id'"
                    " AND table_name <> 'tenants' ORDER BY table_name"
                )
            )
        )


def test_every_tenant_table_is_under_forced_row_level_security(engine: Engine) -> None:
    tables = _tenant_tables(engine)
    assert {"documents", "chunks", "queries", "feedback"} <= set(tables)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
                " WHERE relname = ANY(:tables) AND relkind = 'r'"
            ),
            {"tables": tables},
        ).all()
    assert {name for name, *_ in rows} == set(tables)
    for name, enabled, forced in rows:
        assert enabled, name
        assert forced, name


def test_every_policy_is_keyed_on_the_current_tenant(engine: Engine) -> None:
    tables = _tenant_tables(engine)
    with engine.connect() as connection:
        policies = connection.execute(
            text(
                "SELECT tablename, policyname, cmd, qual, with_check FROM pg_policies"
                " WHERE schemaname = 'public' AND tablename = ANY(:tables)"
            ),
            {"tables": tables},
        ).all()
    for table in tables:
        own = [p for p in policies if p.tablename == table]
        assert any(p.cmd in ("SELECT", "ALL") for p in own), f"{table}: no read policy"
        for policy in own:
            # A read may add the public corpus; every rule still names the current tenant.
            assert "current_tenant()" in (policy.qual or policy.with_check or ""), policy
            if policy.cmd in ("INSERT", "UPDATE", "ALL"):
                assert "current_tenant()" in (policy.with_check or ""), policy


def test_the_application_role_cannot_bypass_the_policies(engine: Engine) -> None:
    with engine.connect() as connection:
        superuser, bypass = connection.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :role"),
            {"role": APP_ROLE},
        ).one()
    assert not superuser
    assert not bypass


def test_the_application_writes_no_untenanted_table_we_did_not_choose(engine: Engine) -> None:
    tenant_tables = set(_tenant_tables(engine))
    with engine.connect() as connection:
        writable = set(
            connection.scalars(
                text(
                    "SELECT DISTINCT table_name FROM information_schema.role_table_grants"
                    " WHERE grantee = :role AND table_schema = 'public'"
                    " AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE')"
                ),
                {"role": APP_ROLE},
            )
        )
    assert writable - tenant_tables == UNTENANTED_WRITABLE
