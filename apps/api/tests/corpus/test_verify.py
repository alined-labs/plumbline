"""Writing verification records into a golden file from a list."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from plumbline.corpus.manifest import load_manifest
from plumbline.corpus.verify import (
    Record,
    RecordError,
    apply_records,
    load_records,
    main,
    quote_in,
)
from rag_eval.schema import GoldenItem, Verification, dump_golden, load_golden

MANIFEST = load_manifest()
DAY = date(2026, 10, 20)
FLORIDA = {
    "jurisdiction": "florida",
    "law": "fl-stat-83",
    "article": "83.57",
    "paragraph": "(3)",
    "edition": "2026",
}
DEPOSIT = {
    "jurisdiction": "spain",
    "law": "es-lau",
    "article": "36",
    "paragraph": "5",
    "edition": "boe-2026-10-13",
}
# Added to LAU art. 36.5 by RDL 29/2026, in force from 2026-10-08.
NEW_WORDING = "En ningún caso podrá exigirse al arrendatario la contratación de seguros de impago"


def item(**overrides: object) -> GoldenItem:
    row: dict[str, object] = {
        "id": "fl-9001",
        "question": "How much notice ends a month-to-month tenancy in Florida?",
        "source_language": "en",
        "jurisdictions": ["florida"],
        "category": "single_article",
        "difficulty": "easy",
        "gold_refs": [FLORIDA],
        "reference_answer": "At least 30 days.",
        "source_type": "synthetic",
        "source_note": "Synthetic: a test.",
        "added_in": "v1",
    }
    return GoldenItem.model_validate({**row, **overrides})


def spanish(**overrides: object) -> GoldenItem:
    return item(
        id="es-9001",
        question="How large may an additional guarantee be in Spain?",
        source_language="es",
        jurisdictions=["spain"],
        gold_refs=[DEPOSIT],
        reference_answer="Two months' rent.",
        **overrides,
    )


def out_of_scope() -> GoldenItem:
    return item(
        id="oos-9001",
        question="Can I evict a tenant in Ontario?",
        jurisdictions=[],
        category="out_of_scope",
        gold_refs=[],
        reference_answer=None,
        expected_abstain=True,
    )


def record(**fields: object) -> Record:
    return Record.model_validate(
        {"id": "fl-9001", "second_source": "A pamphlet, https://x"} | fields
    )


def apply(items: list[GoldenItem], *records: Record, replace: bool = False) -> list[GoldenItem]:
    return apply_records(items, list(records), "a checker", DAY, MANIFEST, replace=replace)


def test_a_missing_quote_is_taken_from_the_cited_paragraph() -> None:
    [verified] = apply([item()], record())
    assert verified.verification is not None
    assert verified.verification.quoted_text.startswith("[fl-stat-83 art. 83.57 (3)] (3) When")
    assert "month to month" in verified.verification.quoted_text
    assert verified.verification.checked_by == "a checker"
    assert verified.verification.checked_on == DAY
    assert verified.verification.second_source == "A pamphlet, https://x"


def test_a_given_quote_is_kept_when_the_pinned_text_has_it() -> None:
    quote = "When the tenancy is from month to month, by giving not less than 30 days' notice"
    [verified] = apply([item()], record(quoted_text=quote, notes="Read in full."))
    assert verified.verification is not None
    assert verified.verification.quoted_text == quote
    assert verified.verification.notes == "Read in full."


def test_a_quote_with_a_gap_is_found_piece_by_piece_in_order() -> None:
    text = "one two three four five"
    assert quote_in("one two … four five", text)
    assert quote_in("two [...] five", text)
    assert quote_in("one\n  two", text)
    assert quote_in("30 days' notice", "30 days’ notice")
    assert not quote_in("four … two", text)
    assert not quote_in("one three", text)


def test_a_quote_not_in_the_statute_stops_every_record() -> None:
    items = [item(), spanish()]
    with pytest.raises(RecordError, match="fl-9001: quoted_text is not in the pinned text"):
        apply(items, record(quoted_text="by giving 15 days' notice"), record(id="es-9001"))


def test_a_dated_item_is_checked_against_the_wording_in_force_that_day() -> None:
    [undated] = apply([spanish()], record(id="es-9001", quoted_text=NEW_WORDING))
    assert undated.verification is not None
    with pytest.raises(RecordError, match="as it stood on 2026-02-01"):
        apply([spanish(signed_on="2026-02-01")], record(id="es-9001", quoted_text=NEW_WORDING))
    [dated] = apply([spanish(signed_on="2026-02-01")], record(id="es-9001"))
    assert dated.verification is not None
    assert "cualquier tipo de garantía" in dated.verification.quoted_text
    assert "[BOE-" not in dated.verification.quoted_text


def test_an_item_without_references_needs_its_own_quote() -> None:
    with pytest.raises(RecordError, match="cites no article"):
        apply([out_of_scope()], record(id="oos-9001"))
    note = "No indexed source covers Ontario."
    [verified] = apply([out_of_scope()], record(id="oos-9001", quoted_text=note))
    assert verified.verification is not None
    assert verified.verification.quoted_text == note


def test_a_source_that_is_not_on_this_machine_is_reported(tmp_path: Path) -> None:
    with pytest.raises(RecordError, match="is not on this machine; run `make fetch`"):
        apply_records([item()], [record()], "a checker", DAY, MANIFEST, root=tmp_path)


def test_unknown_duplicate_and_unattributed_records_are_refused() -> None:
    with pytest.raises(RecordError) as caught:
        apply_records(
            [item(), spanish()],
            [record(id="xx-0001"), record(), record(), record(id="es-9001")],
            None,
            DAY,
            MANIFEST,
        )
    message = str(caught.value)
    assert "xx-0001: no such item in the file" in message
    assert "fl-9001: two records for the same item" in message
    assert "fl-9001: no checked_by" in message
    assert "es-9001: no checked_by" in message


def test_a_verified_item_is_rewritten_only_on_request() -> None:
    [first] = apply([item()], record())
    with pytest.raises(RecordError, match="already verified"):
        apply([first], record(second_source="Another"))
    [second] = apply([first], record(second_source="Another"), replace=True)
    assert second.verification is not None
    assert second.verification.second_source == "Another"


def test_a_record_s_own_checker_and_date_win() -> None:
    [verified] = apply([item()], record(checked_by="the human", checked_on="2026-10-21"))
    assert verified.verification == Verification(
        quoted_text=verified.verification.quoted_text if verified.verification else "",
        second_source="A pamphlet, https://x",
        checked_on=date(2026, 10, 21),
        checked_by="the human",
    )


def test_a_record_with_an_unknown_field_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"id": "fl-9001", "second_source": "x", "checker": "me"}\n')
    with pytest.raises(RecordError, match=r"records\.jsonl:1"):
        load_records(path)


def write_files(tmp_path: Path, *records: dict[str, object]) -> tuple[Path, Path]:
    golden, listing = tmp_path / "golden.jsonl", tmp_path / "records.jsonl"
    dump_golden([item(), spanish()], golden)
    listing.write_text("".join(json.dumps(r) + "\n" for r in records))
    return golden, listing


def test_the_command_rewrites_only_the_verified_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    golden, listing = write_files(tmp_path, {"id": "es-9001", "second_source": "BOE"})
    before = golden.read_text().splitlines()
    assert (
        main([str(golden), str(listing), "--checked-by", "me", "--checked-on", "2026-10-20"]) == 0
    )
    after = golden.read_text().splitlines()
    assert after[0] == before[0]
    assert after[1] != before[1]
    [_, verified] = load_golden(golden)
    assert verified.verification is not None
    assert verified.verification.checked_on == DAY
    assert "verified 1 of 2 items" in capsys.readouterr().out


def test_a_dry_run_or_a_bad_record_leaves_the_file_as_it_was(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    golden, listing = write_files(
        tmp_path, {"id": "es-9001", "second_source": "BOE"}, {"id": "zz-0001", "second_source": "x"}
    )
    before = golden.read_bytes()
    assert main([str(golden), str(listing), "--checked-by", "me"]) == 1
    assert "zz-0001: no such item" in capsys.readouterr().err
    assert golden.read_bytes() == before
    listing.write_text('{"id": "es-9001", "second_source": "BOE"}\n')
    assert main([str(golden), str(listing), "--checked-by", "me", "--dry-run"]) == 0
    assert "would verify 1 of 2 items" in capsys.readouterr().out
    assert golden.read_bytes() == before
