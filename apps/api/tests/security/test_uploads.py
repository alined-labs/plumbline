"""Uploads as an attacker sends them (P3): a Word document whose XML expands or reaches for
a local file, and a lease whose text must never reach a log line or a response header.
The limits themselves (10 MB, the types, 413, 415, 422, 429, 503) are Lane D's tests in
tests/api/test_check_lease.py and tests/ingest/test_upload.py; these are the attacks."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import zipfile
from pathlib import Path

import httpx
import pytest

from plumbline.api.app import create_app
from plumbline.api.lease_stub import StubLeaseChecker
from plumbline.api.quota import COOKIE, MemoryCounter
from plumbline.core.types import CacheMode, DemoTier
from plumbline.db import make_engine, make_sessionmaker
from plumbline.ingest.upload import UploadError, read_upload
from plumbline.settings import Settings

pytestmark = pytest.mark.anyio
WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NO_DATABASE = "postgresql+psycopg://plumbline:plumbline@127.0.0.1:1/none"
# Invented, and distinctive enough that any copy of them in a log is found.
NAME, EMAIL = "Ottoline Brackwater-Szabo", "ottoline.bsz@example.org"


def _docx(document: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _document(doctype: str, text: str) -> str:
    body = f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
    return f'{doctype}<w:document xmlns:w="{WORD}">{body}</w:document>'


def test_a_word_document_that_expands_its_entities_is_refused_at_once() -> None:
    # Ten levels of ten: a gigabyte of "lol" from a document of a few hundred bytes.
    levels = [f'<!ENTITY e0 "{"lol" * 10}">']
    levels += [f'<!ENTITY e{n} "{f"&e{n - 1};" * 10}">' for n in range(1, 10)]
    data = _docx(_document(f"<!DOCTYPE d [{''.join(levels)}]>", "&e9;"))
    started = time.monotonic()
    with pytest.raises(UploadError) as refused:
        read_upload(data)
    assert refused.value.code == "unreadable"
    assert time.monotonic() - started < 2


def test_a_word_document_never_reads_a_file_it_points_to(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("CANARY-7f3a", encoding="utf-8")
    doctype = f'<!DOCTYPE d [<!ENTITY x SYSTEM "{secret.as_uri()}">]>'
    clause = "Clause 1. &x; The Tenant pays the rent on the first day of each month."
    # The parser resolves no external entity, so the reference is undefined and the file
    # is refused whole: its text, and so the file's, never reaches redaction or a model.
    with pytest.raises(UploadError) as refused:
        read_upload(_docx(_document(doctype, clause)))
    assert refused.value.code == "unreadable"
    assert "CANARY" not in str(refused.value)


async def test_the_lease_never_reaches_a_log_line_or_a_header(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(
        _env_file=None, cache_mode=CacheMode.REPLAY, demo_tier=DemoTier.FULL, stub_delay_ms=0
    )
    app = create_app(
        settings,
        sessions=make_sessionmaker(make_engine(NO_DATABASE)),
        counter=MemoryCounter(),
        lease_checker=StubLeaseChecker(delay_ms=0),
    )
    lease = "\n".join(
        f"Clause {n}. The Tenant, {NAME} ({EMAIL}), shall pay the rent on the first day of"
        " each month, and the Landlord shall keep the dwelling fit to live in."
        for n in range(1, 5)
    )
    caplog.set_level(logging.DEBUG)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post(
            "/api/check-lease", content=lease.encode(), headers={"Content-Type": "text/plain"}
        )
        assert started.status_code == 202, started.text
        owner = client.cookies[COOKIE].rsplit(".", 1)[0]
        run = app.state.runs.get(started.json()["id"], owner)
        while not run.ended:
            await asyncio.wait_for(run.wait(len(run.events)), 5)
    headers = " ".join(f"{k}: {v}" for k, v in started.headers.items())
    for leaked in (NAME, EMAIL):
        assert leaked not in caplog.text
        assert leaked not in headers
        assert leaked not in started.text
