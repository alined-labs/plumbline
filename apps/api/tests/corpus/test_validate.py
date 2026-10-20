import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from plumbline.corpus.manifest import MANIFEST, Manifest, load_manifest
from plumbline.corpus.validate import (
    LICENCES,
    check_editions,
    check_golden,
    check_licences,
    check_sources,
    check_unlisted,
)


def source(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "fl-stat-83-2026",
        "law": "fl-stat-83",
        "title": "Florida Statutes, Chapter 83, Part II",
        "jurisdiction": "florida",
        "language": "en",
        "url": "https://www.flsenate.gov/Laws/Statutes/2026/Chapter83/PART_II",
        "edition": "2026",
        "retrieved_on": "2026-10-19",
        "sha256": "0" * 64,
        "format": "html",
        "license_basis": "Public domain (government edicts doctrine)",
        "committed": True,
        "path": "data/corpus/raw/fl-stat-83-2026.html",
    }
    row.update(overrides)
    return row


def test_the_committed_manifest_validates() -> None:
    load_manifest(MANIFEST)


def test_committed_sources_must_exist_and_match(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "corpus" / "raw"
    raw.mkdir(parents=True)
    (raw / "fl-stat-83-2026.html").write_bytes(b"<p>83.49</p>")
    good = hashlib.sha256(b"<p>83.49</p>").hexdigest()
    ok = Manifest.model_validate({"sources": [source(sha256=good)]})
    assert check_sources(ok, tmp_path) == []
    bad = Manifest.model_validate({"sources": [source()]})
    assert "sha256" in check_sources(bad, tmp_path)[0]
    missing = Manifest.model_validate({"sources": [source(path="data/corpus/raw/none.html")]})
    assert "missing" in check_sources(missing, tmp_path)[0]


def test_fetch_only_sources_may_be_absent(tmp_path: Path) -> None:
    row = source(committed=False, path="data/corpus/fetched/dubai-law-26-2007.pdf", format="pdf")
    assert check_sources(Manifest.model_validate({"sources": [row]}), tmp_path) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"committed": False},  # fetch-only, but under raw/
        {"path": "data/corpus/fetched/x.html"},  # committed, but under fetched/
        {"url": "http://example.org/law"},
        {"jurisdiction": "texas"},
    ],
)
def test_bad_rows_are_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"sources": [source(**overrides)]})


def test_only_a_host_without_https_may_use_http() -> None:
    senado = "http://www.secretariasenado.gov.co/senado/basedoc/ley_0820_2003.html"
    row = source(url=senado, parts=[senado.replace(".html", "_pr001.html")])
    Manifest.model_validate({"sources": [row]})
    with pytest.raises(ValidationError, match="must be https"):
        Manifest.model_validate({"sources": [source(parts=["http://example.org/part.js"])]})


def test_duplicate_ids_are_refused() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"sources": [source(), source()]})


def test_a_law_has_one_source_per_edition() -> None:
    twin = source(id="fl-stat-83-2026-copy", path="data/corpus/raw/copy.html")
    both = Manifest.model_validate({"sources": [source(), twin]})  # the model allows it
    assert check_editions(both) == [
        "fl-stat-83 2026: more than one source for the same law and edition"
    ]
    later = source(id="fl-stat-83-2027", edition="2027", path="data/corpus/raw/2027.html")
    assert check_editions(Manifest.model_validate({"sources": [source(), later]})) == []
    assert check_editions(load_manifest()) == []


def test_every_source_needs_its_licence_row() -> None:
    manifest = Manifest.model_validate({"sources": [source()]})
    row = "| `fl-stat-83-2026` | Online Sunshine | `Public domain (government edicts doctrine)` |"
    assert check_licences(manifest, f"# Data licences\n{row}\n") == []
    assert "no row" in check_licences(manifest, "| `fl-stat-718-2026` | ... |")[0]
    wrong = row.replace("Public domain", "Public record")
    assert "does not give the basis" in check_licences(manifest, wrong)[0]


def test_the_committed_licences_cover_every_source() -> None:
    assert check_licences(load_manifest(), LICENCES.read_text(encoding="utf-8")) == []


def test_files_under_raw_need_a_manifest_row(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "corpus" / "raw"
    raw.mkdir(parents=True)
    (raw / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    (raw / "fl-stat-83-2026.html").write_bytes(b"<p>83.49</p>")
    manifest = Manifest.model_validate({"sources": [source()]})
    assert check_unlisted(manifest, tmp_path) == []
    (raw / "stray.html").write_bytes(b"<p>no licence</p>")
    assert check_unlisted(manifest, tmp_path) == [
        "data/corpus/raw/stray.html: under raw/ but in no manifest row"
    ]


def test_golden_files_are_validated(tmp_path: Path) -> None:
    golden = tmp_path / "data" / "golden"
    golden.mkdir(parents=True)
    (golden / "golden_v0.jsonl").write_text(json.dumps({"id": "x"}) + "\n", encoding="utf-8")
    assert check_golden(tmp_path)


def test_other_lists_beside_the_golden_files_are_not_read_as_golden(tmp_path: Path) -> None:
    drafts = tmp_path / "data" / "golden" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "second_sources_v1.jsonl").write_text('{"id": "x"}\n', encoding="utf-8")
    assert check_golden(tmp_path) == []
