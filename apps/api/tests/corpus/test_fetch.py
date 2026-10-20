import re
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest

from plumbline.core.types import Jurisdiction, Language
from plumbline.corpus.fetch import (
    SOURCES,
    Declared,
    FetchError,
    check,
    download,
    element,
    fetch,
    sha256,
)
from plumbline.corpus.manifest import Manifest, load_manifest
from plumbline.settings import ROOT

URL = "https://www.leg.state.fl.us/statutes/chapter83"
PART_II = b'<div class="Part"><div class="Title">PART II</div>'
STATUTE = PART_II + b'<div class="Section">83.49 Deposit money.</div></div>'


def page(statute: bytes = STATUTE, day: bytes = b"October 19, 2026") -> bytes:
    """A publisher's page: a header that changes daily around the statute's markup."""
    return (
        b"<html><body><div class='Header'>" + day + b"</div>"
        b'<div class="Part"><div class="Title">PART I</div></div>'
        + statute
        + b'<div class="Part"><div class="Title">PART III</div></div></body></html>'
    )


PART = Declared(
    id="fl-stat-83-2026",
    law="fl-stat-83",
    title="Florida Statutes 2026, chapter 83, part II",
    jurisdiction=Jurisdiction.FLORIDA,
    language=Language.EN,
    url=URL,
    edition="2026",
    format="html",
    license_basis="Public domain (government edicts doctrine)",
    committed=True,
    keep=(PART_II,),
)
PDF = replace(PART, id="dubai-law-26-2007", format="pdf", committed=False, keep=())
DAY = date(2026, 10, 19)


def serve(pages: dict[str, bytes]) -> httpx.Client:
    """A client that answers from `pages`, with a 404 for any other URL."""

    def answer(request: httpx.Request) -> httpx.Response:
        body = pages.get(str(request.url))
        return httpx.Response(404) if body is None else httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(answer), follow_redirects=True)


def offline() -> httpx.Client:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected download of {request.url}")

    return httpx.Client(transport=httpx.MockTransport(refuse))


def pinned(source: Declared, content: bytes) -> Manifest:
    return Manifest(sources=[source.row(sha256(content), DAY)])


def test_element_cuts_the_marked_element_byte_for_byte() -> None:
    assert element(page(), PART_II) == STATUTE


@pytest.mark.parametrize(
    ("html", "marker"),
    [
        (page(), b'<div class="Part"><div class="Title">PART IV</div>'),  # absent
        (page() + STATUTE, PART_II),  # twice: which one is meant?
        (PART_II + b"<div>never closed</div>", PART_II),
        (page(), b"PART II"),  # not a start tag
    ],
)
def test_element_refuses_an_ambiguous_cut(html: bytes, marker: bytes) -> None:
    with pytest.raises(FetchError):
        element(html, marker)


def test_a_new_source_is_downloaded_cut_and_pinned(tmp_path: Path) -> None:
    manifest, problems = fetch(
        [PART], Manifest(sources=[]), serve({URL: page()}), root=tmp_path, today=DAY
    )
    assert problems == []
    [row] = manifest.sources
    assert (tmp_path / row.path).read_bytes() == STATUTE + b"\n"
    assert row == PART.row(sha256(STATUTE + b"\n"), DAY)
    assert row.path == "data/corpus/raw/fl-stat-83-2026.html"


def test_files_on_disk_are_checked_and_never_downloaded(tmp_path: Path) -> None:
    content = STATUTE + b"\n"
    manifest = pinned(PART, content)
    file = tmp_path / PART.path
    file.parent.mkdir(parents=True)
    file.write_bytes(content)
    assert fetch([PART], manifest, offline(), root=tmp_path) == (manifest, [])
    file.write_bytes(content.replace(b"83.49", b"83.50"))
    [problem] = fetch([PART], manifest, offline(), root=tmp_path)[1]
    assert "the manifest pins" in problem


def test_a_missing_fetch_only_file_is_kept_only_if_it_matches(tmp_path: Path) -> None:
    pdf = b"%PDF-1.7 Law No. 26 of 2007"
    assert fetch([PDF], pinned(PDF, pdf), serve({URL: pdf}), root=tmp_path)[1] == []
    assert (tmp_path / "data/corpus/fetched/dubai-law-26-2007.pdf").read_bytes() == pdf

    elsewhere = tmp_path / "fresh"
    changed = serve({URL: pdf + b" amended"})
    [problem] = fetch([PDF], pinned(PDF, pdf), changed, root=elsewhere)[1]
    assert "the publisher changed it" in problem
    assert not (elsewhere / PDF.path).exists()


def test_check_ignores_the_wrapper_and_reports_a_changed_text() -> None:
    manifest = pinned(PART, STATUTE + b"\n")
    next_day = serve({URL: page(day=b"October 20, 2026")})
    assert check([PART], manifest, next_day) == []
    amended = serve({URL: page(statute=STATUTE.replace(b"Deposit", b"Advance"))})
    [problem] = check([PART], manifest, amended)
    assert "different text" in problem


def test_a_changed_declaration_waits_for_a_repin(tmp_path: Path) -> None:
    manifest = pinned(PART, STATUTE + b"\n")
    renamed = replace(PART, title="Florida Statutes 2026, chapter 83, part II (renamed)")
    [problem] = fetch([renamed], manifest, offline(), root=tmp_path)[1]
    assert "--repin fl-stat-83-2026" in problem
    later = date(2026, 11, 2)
    repinned, problems = fetch(
        [renamed],
        manifest,
        serve({URL: page()}),
        root=tmp_path,
        repin=frozenset({PART.id}),
        today=later,
    )
    assert problems == []
    assert repinned.sources == [renamed.row(sha256(STATUTE + b"\n"), later)]


def test_rows_nobody_declares_are_kept_and_reported(tmp_path: Path) -> None:
    manifest = pinned(PDF, b"%PDF")
    kept, problems = fetch([], manifest, offline(), root=tmp_path)
    assert kept == manifest
    assert problems == [
        "dubai-law-26-2007: in the manifest but not declared in plumbline.corpus.fetch"
    ]


def test_a_redirect_to_another_host_is_refused() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.leg.state.fl.us":
            return httpx.Response(302, headers={"Location": "https://mirror.example.org/83"})
        return httpx.Response(200, content=page())

    client = httpx.Client(transport=httpx.MockTransport(answer), follow_redirects=True)
    with pytest.raises(FetchError, match="another host"):
        download(client, PART)


def test_an_api_gets_the_accept_header_it_needs() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        xml = request.headers["accept"] == "application/xml"
        return httpx.Response(200, content=b"<response/>") if xml else httpx.Response(400)

    client = httpx.Client(transport=httpx.MockTransport(answer))
    record = replace(PART, format="xml", keep=(), accept="application/xml")
    assert download(client, record) == b"<response/>"
    with pytest.raises(FetchError, match="400"):
        download(client, replace(record, accept=None))


def test_the_manifest_pins_exactly_the_declared_sources() -> None:
    manifest = load_manifest()
    assert [row.id for row in manifest.sources] == [source.id for source in SOURCES]
    for source, row in zip(SOURCES, manifest.sources, strict=True):
        assert source.row(row.sha256, row.retrieved_on) == row


def test_each_law_has_one_source_per_edition() -> None:
    editions = [(source.law, source.edition) for source in SOURCES]
    assert len(editions) == len(set(editions))


def section_numbers(path: str) -> list[str]:
    html = (ROOT / path).read_text(encoding="utf-8")
    return re.findall(
        r'<div class="Section">(?:<sup>.*?</sup>)?<span class="SectionNumber">([0-9.]+)', html
    )


def test_the_florida_cuts_hold_the_sections_their_notes_name() -> None:
    part_ii = section_numbers("data/corpus/raw/fl-stat-83-2026.html")
    assert part_ii[0] == "83.40"
    assert part_ii[-1] == "83.684"
    assert {"83.47", "83.49", "83.425", "83.5615", "83.56", "83.60"} <= set(part_ii)
    assert all(83.40 <= float(n) < 83.7 for n in part_ii)  # nothing from parts I or III
    assert section_numbers("data/corpus/raw/fl-stat-718-2026.html") == [
        "718.110",
        "718.112",
        "718.116",
    ]


def test_each_boe_record_is_the_edition_it_is_pinned_as() -> None:
    """The record's own update date is the consolidation date, so a re-pin that caught a
    newer consolidation fails here until it is declared as the new edition."""
    boe = [row for row in load_manifest().sources if row.url.host == "www.boe.es"]
    assert {row.law for row in boe} == {"es-lau", "es-lph"}
    for row in boe:
        xml = (ROOT / row.path).read_text(encoding="utf-8")
        updated = re.search(r"<fecha_actualizacion>(\d{4})(\d{2})(\d{2})T", xml)
        assert updated is not None
        assert row.consolidated_on == date(*map(int, updated.groups()))
        assert row.edition == f"boe-{row.consolidated_on.isoformat()}"
