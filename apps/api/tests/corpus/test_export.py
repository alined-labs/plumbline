"""The folder the maintainer publishes as the golden set's dataset."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from plumbline.corpus.export import (
    MARKER,
    WITHHELD,
    ExportError,
    build,
    main,
    second_source_of,
    statistics,
    unpublishable,
    withhold_quotes,
)
from plumbline.corpus.manifest import load_manifest
from plumbline.settings import ROOT
from rag_eval.schema import (
    ArticleRef,
    Category,
    Difficulty,
    GoldenItem,
    Jurisdiction,
    SourceType,
    Split,
    Verification,
    dump_golden,
    load_golden,
)

MANIFEST = load_manifest()
EDITIONS = {source.law: source.edition for source in MANIFEST.sources}
QUOTE = "A quoted passage of the statute."


def ref(jurisdiction: Jurisdiction, law: str, article: str) -> ArticleRef:
    return ArticleRef(jurisdiction=jurisdiction, law=law, article=article, edition=EDITIONS[law])


FLORIDA = ref(Jurisdiction.FLORIDA, "fl-stat-83", "83.49")
SPAIN = ref(Jurisdiction.SPAIN, "es-lau", "36")
DUBAI = ref(Jurisdiction.DUBAI, "dubai-law-26-2007", "20")
COLOMBIA = ref(Jurisdiction.COLOMBIA, "co-ley-820", "16")


def item(
    number: int,
    refs: list[ArticleRef],
    *,
    verified: bool = True,
    split: Split = Split.DEV,
) -> GoldenItem:
    places = sorted({r.jurisdiction for r in refs}, key=lambda place: place.value)
    category = Category.CROSS_JURISDICTION if len(places) > 1 else Category.SINGLE_ARTICLE
    return GoldenItem(
        id=f"t-{number:04d}",
        question=f"A question numbered {number}?",
        source_language="en",
        jurisdictions=places,
        category=category,
        difficulty=Difficulty.MEDIUM,
        gold_refs=refs,
        reference_answer="An answer.",
        source_type=SourceType.SYNTHETIC,
        split=split,
        verification=Verification(
            quoted_text=QUOTE,
            second_source="A second source, https://example.org",
            checked_on=date(2026, 10, 20),
            checked_by="the maintainer",
        )
        if verified
        else None,
        added_in="v1",
    )


def golden_file(tmp_path: Path, items: list[GoldenItem]) -> Path:
    path = tmp_path / "golden_v9.jsonl"
    dump_golden(items, path)
    return path


def published_items() -> list[GoldenItem]:
    return [
        item(1, [FLORIDA], split=Split.DEV),
        item(2, [SPAIN], split=Split.TEST),
        item(3, [DUBAI], split=Split.DEV),
        item(4, [COLOMBIA], split=Split.TEST),
        item(5, [FLORIDA, DUBAI], split=Split.DEV),
    ]


def test_a_quote_is_kept_only_when_every_source_is_redistributed() -> None:
    kept = withhold_quotes(item(1, [FLORIDA, SPAIN]), MANIFEST)
    assert kept.verification is not None
    assert kept.verification.quoted_text == QUOTE
    for refs in ([DUBAI], [COLOMBIA], [FLORIDA, DUBAI]):
        held = withhold_quotes(item(2, refs), MANIFEST)
        assert held.verification is not None
        assert held.verification.quoted_text == WITHHELD
        assert held.verification.second_source == "A second source, https://example.org"


def test_a_source_the_manifest_does_not_know_counts_as_not_redistributed() -> None:
    unknown = ref(Jurisdiction.FLORIDA, "fl-stat-83", "83.49").model_copy(
        update={"edition": "1999"}
    )
    held = withhold_quotes(item(1, [unknown]), MANIFEST)
    assert held.verification is not None
    assert held.verification.quoted_text == WITHHELD


def test_an_unverified_item_has_nothing_to_withhold() -> None:
    assert withhold_quotes(item(1, [DUBAI], verified=False), MANIFEST).verification is None


def test_a_draft_is_not_ready_to_publish() -> None:
    problems = unpublishable(
        [item(1, [FLORIDA], verified=False), item(2, [SPAIN], split=Split.UNASSIGNED)]
    )
    assert problems == ["t-0001: not verified", "t-0002: no split"]


def test_the_folder_holds_the_files_the_card_promises(tmp_path: Path) -> None:
    out = tmp_path / "golden-v9"
    files = build(golden_file(tmp_path, published_items()), out)
    names = {path.relative_to(out).as_posix() for path in files}
    assert {
        "README.md",
        "LICENSE.md",
        "CHANGELOG.md",
        "DATA_LICENSES.md",
        "corpus_manifest.json",
        "golden_v9.jsonl",
        "dev.jsonl",
        "test.jsonl",
        "leases/expected_findings.json",
        "leases/fl-lease-01.md",
        "SHA256SUMS",
    } <= names
    assert "leases/README.md" not in names
    assert [i.id for i in load_golden(out / "dev.jsonl")] == ["t-0001", "t-0003", "t-0005"]
    assert [i.id for i in load_golden(out / "test.jsonl")] == ["t-0002", "t-0004"]


def test_the_published_file_withholds_what_the_licences_forbid(tmp_path: Path) -> None:
    out = tmp_path / "golden-v9"
    build(golden_file(tmp_path, published_items()), out)
    quotes = {
        i.id: i.verification.quoted_text
        for i in load_golden(out / "golden_v9.jsonl")
        if i.verification
    }
    assert quotes == {
        "t-0001": QUOTE,
        "t-0002": QUOTE,
        "t-0003": WITHHELD,
        "t-0004": WITHHELD,
        "t-0005": WITHHELD,
    }
    # The quote of a redistributed source is in the file twice (items 1 and 2), nothing else is.
    text = (out / "golden_v9.jsonl").read_text(encoding="utf-8")
    assert text.count(QUOTE) == 2
    assert text.count(WITHHELD) == 3


def test_the_card_gets_its_statistics_and_the_checksums_match(tmp_path: Path) -> None:
    out = tmp_path / "golden-v9"
    build(golden_file(tmp_path, published_items()), out)
    card = (out / "README.md").read_text(encoding="utf-8")
    assert MARKER not in card
    assert "| single_article | 2 | 2 | 4 |" in card
    assert "| cross_jurisdiction | 1 | 0 | 1 |" in card
    assert "5 items, 0 of them dated." in card
    for line in (out / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", maxsplit=1)
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    assert "SHA256SUMS" not in (out / "SHA256SUMS").read_text(encoding="utf-8")


def test_a_draft_is_refused_unless_asked_for(tmp_path: Path) -> None:
    draft = golden_file(tmp_path, [item(1, [FLORIDA], verified=False, split=Split.UNASSIGNED)])
    with pytest.raises(ExportError, match="is a draft"):
        build(draft, tmp_path / "one")
    build(draft, tmp_path / "two", draft=True)
    assert (tmp_path / "two" / "README.md").is_file()


def test_an_existing_folder_is_not_overwritten(tmp_path: Path) -> None:
    out = tmp_path / "golden-v9"
    out.mkdir()
    with pytest.raises(ExportError, match="exists already"):
        build(golden_file(tmp_path, published_items()), out)


def test_a_file_that_does_not_validate_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "x"}\n', encoding="utf-8")
    with pytest.raises(ExportError, match=r"bad\.jsonl:1"):
        build(bad, tmp_path / "out")


def test_the_committed_card_has_the_line_for_its_statistics() -> None:
    assert MARKER in (ROOT / "data" / "golden" / "DATASET_CARD.md").read_text(encoding="utf-8")


def test_the_command_reports_and_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    golden = golden_file(tmp_path, published_items())
    assert main([str(golden), str(tmp_path / "out")]) == 0
    assert "wrote" in capsys.readouterr().out
    assert main([str(golden), str(tmp_path / "out")]) == 1
    assert "exists already" in capsys.readouterr().err


def test_statistics_count_every_item_once() -> None:
    text = statistics(published_items())
    assert "| florida | 1 | 0 | 1 |" in text
    assert "| several | 1 | 0 | 1 |" in text
    assert "| synthetic | 5 |" in text
    assert "| v1 | 5 |" in text
    assert "| found | 5 |" in text


def test_the_card_counts_items_without_a_second_source() -> None:
    found = item(1, [FLORIDA])
    assert second_source_of(found) == "found"
    assert second_source_of(item(2, [FLORIDA], verified=False)) == "not verified"
    # A verification may lack a second source once the schema allows it (its notes say why);
    # built here without validation, to count it before that change lands.
    assert found.verification is not None
    bare = Verification.model_construct(**{**found.verification.__dict__, "second_source": None})
    none_found = found.model_copy(update={"verification": bare})
    assert second_source_of(none_found) == "none found"
    out_of_scope = none_found.model_copy(update={"expected_abstain": True})
    assert second_source_of(out_of_scope) == "not applicable (out of scope)"
