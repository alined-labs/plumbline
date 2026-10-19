"""The parser: HTML read in code, PDFs page by page through docling (replayed from
cache/parse/), the text-layer check, and the committed parses in data/processed/."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from plumbline.cache import ResponseCache
from plumbline.core.types import CacheMode, ParseMethod
from plumbline.corpus.manifest import Source
from plumbline.ingest import html
from plumbline.ingest.parse import (
    DOCLING,
    DOCLING_VERSION,
    DoclingClient,
    ParseError,
    coverage,
    parse_source,
)
from plumbline.settings import ROOT

from .pdfs import STATUTE, make_pdf

SENATE_HTML = (  # a Colombian Senate page, in Windows-1252
    b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1">'
    b'</head><body><div id="aj_data"><p><a class="bookmarkaj" name="9">ART\xcdCULO 9o.'
    b" OBLIGACIONES DEL ARRENDATARIO.</a> Son obligaciones del arrendatario:</p>"
    b"</div></body></html>"
)
SENATE_URL = "https://www.secretariasenado.gov.co/senado/basedoc/ley_0820_2003.html"


def _source(data: bytes, fmt: str = "pdf", url: str = "https://www.boe.es/a.pdf") -> Source:
    return Source.model_validate(
        {
            "id": "es-lau-test",
            "law": "es-lau",
            "title": "Ley de Arrendamientos Urbanos",
            "jurisdiction": "spain",
            "language": "es",
            "url": url,
            "edition": "boe-2026-10-07",
            "retrieved_on": date(2026, 10, 19),
            "sha256": hashlib.sha256(data).hexdigest(),
            "format": fmt,
            "license_basis": "test",
            "committed": True,
            "path": f"data/corpus/raw/es-lau-test.{fmt}",
        }
    )


def _offline() -> httpx.Client:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected call to {request.url}")

    return httpx.Client(transport=httpx.MockTransport(refuse))


def _fake_docling(
    tmp_path: Path, answer: dict[str, Any], seen: list[dict[str, Any]] | None = None
) -> DoclingClient:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, json=answer)

    client = httpx.Client(transport=httpx.MockTransport(handle))
    return DoclingClient("http://docling", ResponseCache(CacheMode.RECORD, tmp_path), client)


def test_the_docling_version_is_the_one_compose_runs() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert f"docling-serve-cpu:v{DOCLING_VERSION}" in compose


def test_a_pdf_replays_docling_page_by_page_and_keeps_its_blank_page() -> None:
    docling = DoclingClient(
        "http://docling", ResponseCache(CacheMode.REPLAY, ROOT / "cache"), _offline()
    )
    document = parse_source(_source(STATUTE), STATUTE, docling)
    assert document.parser == DOCLING
    assert [(p.number, p.method) for p in document.pages] == [
        (1, ParseMethod.TEXT_LAYER),
        (2, ParseMethod.TEXT_LAYER),
        (3, ParseMethod.TEXT_LAYER),
    ]
    assert [p.markdown for p in document.pages] == [
        "Artículo 1. Objeto.\n\n1. La presente ley regula el arrendamiento de fincas urbanas.\n"
        "2. Se aplica en todo el territorio del Estado.",
        "",
        "Artículo 2. Plazo mínimo. La duración del arrendamiento será libremente pactada por"
        " las partes.",
    ]


def test_docling_gets_one_page_of_the_file_per_call(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    answer = {"status": "success", "document": {"md_content": "x"}, "errors": []}
    _fake_docling(tmp_path, answer, seen).page_markdown(STATUTE, "f" * 64, 3)
    (body,) = seen
    assert body["options"]["page_range"] == [3, 3]
    assert body["options"]["do_ocr"] is False
    assert base64.b64decode(body["sources"][0]["base64_string"]) == STATUTE


def test_a_page_docling_thins_out_keeps_its_text_layer(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # docling once filed a statute line under page furniture and dropped it.
    data = make_pdf([["Artículo 2. Plazo mínimo.", "La duración será libremente pactada."]])
    answer = {"status": "success", "document": {"md_content": "Artículo 2. Plazo mínimo."}}
    with caplog.at_level(logging.WARNING):
        document = parse_source(_source(data), data, _fake_docling(tmp_path, answer))
    assert document.pages[0].markdown == (
        "Artículo 2. Plazo mínimo.\nLa duración será libremente pactada."
    )
    assert "keeps the raw text layer (lost: duración la libremente pactada será)" in caplog.text


def test_a_failed_conversion_is_an_error(tmp_path: Path) -> None:
    answer = {"status": "failure", "document": {"md_content": None}, "errors": ["boom"]}
    with pytest.raises(ParseError, match="docling failed on page 1"):
        parse_source(_source(STATUTE), STATUTE, _fake_docling(tmp_path, answer))


def test_an_html_source_is_one_page_read_without_docling() -> None:
    source = _source(SENATE_HTML, "html", SENATE_URL)
    document = parse_source(
        source,
        SENATE_HTML,
        DoclingClient(
            "http://docling", ResponseCache(CacheMode.REPLAY, ROOT / "cache"), _offline()
        ),
    )
    assert document.parser == html.READER
    assert [(p.number, p.method) for p in document.pages] == [(1, ParseMethod.HTML)]
    assert document.markdown == (
        "ARTÍCULO 9o. OBLIGACIONES DEL ARRENDATARIO. Son obligaciones del arrendatario:"
    )


def test_a_file_that_is_not_the_manifests_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match="sha256"):
        parse_source(_source(STATUTE), STATUTE + b"\n", _fake_docling(tmp_path, {}))


def test_a_format_without_a_reader_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match="no reader for txt"):
        parse_source(_source(b"text", "txt"), b"text", _fake_docling(tmp_path, {}))


def test_coverage_counts_repeated_words() -> None:
    assert coverage("el plazo y el precio", "el plazo y precio") == pytest.approx(0.8)
    assert coverage("", "anything") == 1.0


def test_a_running_header_docling_drops_is_not_lost_law(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The header repeats on every page; on the short last page it is most of the words.
    header = "Law No. (26) of 2007 Regulating the Relationship between Landlords and Tenants"
    pages = [
        [header, f"Page {n} of 3", f"Article ({n}) The Landlord shall keep the property safe."]
        for n in (1, 2, 3)
    ]
    data = make_pdf(pages)
    body = "Article (3) The Landlord shall keep the property safe."
    answer = {"status": "success", "document": {"md_content": body}}
    with caplog.at_level(logging.WARNING):
        document = parse_source(_source(data), data, _fake_docling(tmp_path, answer))
    assert document.pages[2].markdown == body
    assert "keeps the raw text layer" not in caplog.text
