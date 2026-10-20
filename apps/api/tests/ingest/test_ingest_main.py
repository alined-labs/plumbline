"""`python -m plumbline.ingest`, on a manifest of its own, and the committed parses."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from plumbline.cache import ResponseCache
from plumbline.core.types import CacheMode
from plumbline.corpus.manifest import load_manifest
from plumbline.ingest import html
from plumbline.ingest.__main__ import main
from plumbline.ingest.parse import DoclingClient, parse_source
from plumbline.ingest.processed import read_processed, write_processed
from plumbline.settings import ROOT

from .pdfs import make_pdf

PAGE = (
    b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1">'
    b'</head><body><div id="aj_data"><p><a class="bookmarkaj" name="9">ART\xcdCULO 9o.'
    b" OBLIGACIONES DEL ARRENDATARIO.</a> Son obligaciones del arrendatario:</p>"
    b"</div></body></html>"
)


def _source(
    source_id: str, data: bytes, *, committed: bool = True, fmt: str = "html"
) -> dict[str, Any]:
    folder = "raw" if committed else "fetched"
    return {
        "id": source_id,
        "law": "co-ley-820",
        "title": "Ley 820 de 2003",
        "jurisdiction": "colombia",
        "language": "es",
        "url": "https://www.secretariasenado.gov.co/senado/basedoc/ley_0820_2003.html",
        "edition": "2026-10-15",
        "retrieved_on": date(2026, 10, 19).isoformat(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "format": fmt,
        "license_basis": "test",
        "committed": committed,
        "path": f"data/corpus/{folder}/{source_id}.{fmt}",
    }


@pytest.fixture
def corpus(tmp_path: Path) -> dict[str, Path]:
    """A manifest with one committed source and one fetch-only source not on disk."""
    raw = tmp_path / "data" / "corpus" / "raw"
    raw.mkdir(parents=True)
    (raw / "co-ley-820-test.html").write_bytes(PAGE)
    manifest = tmp_path / "manifest.json"
    sources = [_source("co-ley-820-test", PAGE), _source("dubai-test", b"pdf", committed=False)]
    manifest.write_text(json.dumps({"version": 1, "sources": sources}), encoding="utf-8")
    return {
        "root": tmp_path,
        "manifest": manifest,
        "processed": tmp_path / "processed",
        "fetched": tmp_path / "data" / "corpus" / "fetched",
    }


def _run(corpus: dict[str, Path], *argv: str) -> int:
    return main(list(argv), **corpus)


def test_a_source_is_parsed_once_then_reused(
    corpus: dict[str, Path], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        assert _run(corpus) == 0
    assert "co-ley-820-test: parsed, 1 pages (1 html)" in caplog.text
    assert "dubai-test: data/corpus/fetched/dubai-test.html is not on this machine" in caplog.text
    assert "2 sources: 1 missing, 1 parsed" in caplog.text
    written = corpus["processed"] / "co-ley-820-test.json"
    first = written.read_text(encoding="utf-8")
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert _run(corpus, "--source", "co-ley-820-test") == 0
    assert "1 sources: 1 reused" in caplog.text
    assert written.read_text(encoding="utf-8") == first


def test_a_fetch_only_source_is_parsed_where_git_never_sees_it(corpus: dict[str, Path]) -> None:
    # Dubai's and Colombia's sources may not be redistributed, and a parse holds the text.
    fetched = corpus["fetched"]
    fetched.mkdir(parents=True)
    manifest = json.loads(corpus["manifest"].read_text(encoding="utf-8"))
    manifest["sources"][1] = _source("dubai-test", PAGE, committed=False)
    corpus["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    (fetched / "dubai-test.html").write_bytes(PAGE)
    assert _run(corpus, "--source", "dubai-test") == 0
    assert (fetched / "processed" / "dubai-test.json").exists()
    assert not (corpus["processed"] / "dubai-test.json").exists()


def test_a_parse_of_an_older_file_is_redone(corpus: dict[str, Path]) -> None:
    _run(corpus)
    written = corpus["processed"] / "co-ley-820-test.json"
    stale = json.loads(written.read_text(encoding="utf-8"))
    stale["sha256"] = "0" * 64
    written.write_text(json.dumps(stale), encoding="utf-8")
    assert _run(corpus) == 0
    assert json.loads(written.read_text(encoding="utf-8"))["sha256"] != "0" * 64


def test_a_parse_by_an_older_reader_is_redone(corpus: dict[str, Path]) -> None:
    _run(corpus)
    written = corpus["processed"] / "co-ley-820-test.json"
    old = json.loads(written.read_text(encoding="utf-8"))
    old["parser"] = "plumbline html 1"  # the same file, read by a reader since replaced
    written.write_text(json.dumps(old), encoding="utf-8")
    assert _run(corpus) == 0
    assert json.loads(written.read_text(encoding="utf-8"))["parser"] == html.READER


def test_an_unknown_source_is_refused(corpus: dict[str, Path]) -> None:
    with pytest.raises(SystemExit):
        _run(corpus, "--source", "nowhere")


def test_a_committed_parse_is_reused_only_for_the_same_file(tmp_path: Path) -> None:
    manifest = load_manifest(ROOT / "data" / "corpus" / "manifest.json")
    source = next(s for s in manifest.sources if s.format == "html")
    document = read_processed(source)
    assert document is not None
    write_processed(document, tmp_path)
    assert read_processed(source, tmp_path) == document
    assert read_processed(source.model_copy(update={"sha256": "0" * 64}), tmp_path) is None


def test_every_committed_parse_is_what_its_source_gives_today() -> None:
    """data/processed is current: the readers that need no service rebuild it exactly. A
    fetch-only source has no committed parse, and its file is not on a clean runner."""
    docling = DoclingClient("http://docling", ResponseCache(CacheMode.REPLAY, ROOT / "cache"))
    for source in load_manifest(ROOT / "data" / "corpus" / "manifest.json").sources:
        if not source.committed or source.format not in {"html", "xml"}:
            continue
        committed = read_processed(source)
        assert committed is not None, f"{source.id}: no current parse; run make ingest"
        rebuilt = parse_source(source, (ROOT / source.path).read_bytes(), docling)
        assert rebuilt == committed, f"{source.id}: stale; run make ingest"


def test_a_scanned_page_goes_to_the_vision_reader(
    corpus: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    data = make_pdf([["Artículo 1. Objeto de la ley de arrendamientos urbanos."], None])
    (corpus["root"] / "data" / "corpus" / "raw" / "scan-test.pdf").write_bytes(data)
    corpus["manifest"].write_text(
        json.dumps({"version": 1, "sources": [_source("scan-test", data, fmt="pdf")]}),
        encoding="utf-8",
    )

    class FakeVision:
        def __init__(self, cache: object) -> None:
            pass

        def page_markdown(self, data: bytes, sha256: str, page: int, language: object) -> str:
            return f"Transcribed page {page}."

    def docling(self: DoclingClient, data: bytes, sha256: str, page: int) -> str:
        return "Artículo 1. Objeto de la ley de arrendamientos urbanos."

    monkeypatch.setattr("plumbline.ingest.__main__.VisionReader", FakeVision)
    monkeypatch.setattr(DoclingClient, "page_markdown", docling)
    assert _run(corpus) == 0
    parsed = json.loads((corpus["processed"] / "scan-test.json").read_text(encoding="utf-8"))
    assert [(p["method"], p["markdown"][:11]) for p in parsed["pages"]] == [
        ("text_layer", "Artículo 1."),
        ("vision", "Transcribed"),
    ]
