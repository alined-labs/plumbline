"""The API's tests never touch a developer's database.

A test that needs Postgres asks for the `database_url` fixture and hands the app its
sessions. Every other app is built with the settings' default URL, which on a machine that
has run `make up` and `make ingest` is the real dev database, and the query log, the tier
and the quotas would write into it. So those apps are pointed at a port nothing listens on;
their database features fall back, as they do when Postgres is down.
"""

from __future__ import annotations

import pytest

NOTHING_LISTENS = "postgresql+psycopg://plumbline:plumbline@127.0.0.1:1/none"


@pytest.fixture(autouse=True)
def _no_default_database(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if "database_url" not in request.fixturenames:
        monkeypatch.setenv("DATABASE_URL", NOTHING_LISTENS)
