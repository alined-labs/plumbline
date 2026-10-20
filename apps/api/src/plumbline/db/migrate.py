"""Bringing a database to the current schema, for the places that own one (make ingest on
a developer's machine, the tests). The API never migrates itself: deploy runs
`alembic -c apps/api/alembic.ini upgrade head` before it starts the service."""

from __future__ import annotations

from alembic import command
from alembic.config import Config

from plumbline.settings import ROOT

ALEMBIC_INI = ROOT / "apps" / "api" / "alembic.ini"


def upgrade(url: str, revision: str = "head") -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, revision)
