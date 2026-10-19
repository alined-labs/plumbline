import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from plumbline.corpus.manifest import MANIFEST, Manifest, load_manifest
from plumbline.corpus.validate import check_golden, check_sources


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


def test_duplicate_ids_are_refused() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"sources": [source(), source()]})


def test_golden_files_are_validated(tmp_path: Path) -> None:
    golden = tmp_path / "data" / "golden"
    golden.mkdir(parents=True)
    (golden / "golden_v0.jsonl").write_text(json.dumps({"id": "x"}) + "\n", encoding="utf-8")
    assert check_golden(tmp_path)
