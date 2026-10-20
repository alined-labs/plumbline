from datetime import date
from pathlib import Path

import pytest

from plumbline.corpus.leases import load_expected
from plumbline.corpus.manifest import load_manifest
from plumbline.corpus.review import main, render_item
from plumbline.settings import ROOT
from rag_eval.schema import GoldenItem, load_golden

DRAFTS = ROOT / "data" / "golden" / "drafts" / "golden_v0.jsonl"
MANIFEST = load_manifest()


def item(**overrides: object) -> GoldenItem:
    row: dict[str, object] = {
        "id": "fl-9001",
        "question": "How much notice ends a month-to-month tenancy in Florida?",
        "source_language": "en",
        "jurisdictions": ["florida"],
        "category": "single_article",
        "difficulty": "easy",
        "gold_refs": [
            {
                "jurisdiction": "florida",
                "law": "fl-stat-83",
                "article": "83.57",
                "paragraph": "(3)",
                "edition": "2026",
            }
        ],
        "reference_answer": "At least 30 days.",
        "source_type": "synthetic",
        "source_note": "Synthetic: a test.",
        "added_in": "v0",
    }
    return GoldenItem.model_validate({**row, **overrides})


def test_an_item_is_shown_beside_the_pinned_text_of_its_article() -> None:
    sheet = render_item(item(), MANIFEST, None)
    assert "## fl-9001 · single_article · easy" in sheet
    assert "**Reference answer.** At least 30 days." in sheet
    assert "### florida:fl-stat-83:83.57 (edition 2026), paragraph (3)" in sheet
    assert "**Cited paragraph (3)**" in sheet
    assert "> (3) When the tenancy is from month to month" in sheet
    assert "> 83.57 Termination of tenancy without specific term" in sheet


def test_a_dated_item_shows_the_wording_in_force_that_day() -> None:
    gold = {"jurisdiction": "spain", "law": "es-lau", "article": "9", "edition": "boe-2026-10-13"}
    sheet = render_item(
        item(jurisdictions=["spain"], gold_refs=[gold], signed_on=date(2019, 2, 10)),
        MANIFEST,
        None,
    )
    assert "**Signed on** 2019-02-10" in sheet
    assert "[BOE-A-2019-799, in force from 20190124]" in sheet


def test_a_long_article_is_cut_where_asked_and_a_missing_one_is_said() -> None:
    assert "**The article begins**" in render_item(item(), MANIFEST, None, chars=40)
    whole = render_item(item(), MANIFEST, None, chars=0)
    assert "**The article**" in whole
    assert " …" not in whole
    missing = item(gold_refs=[{**item().gold_refs[0].model_dump(mode="json"), "article": "83.99"}])
    assert "*Article 83.99 is not in fl-stat-83-2026.*" in render_item(missing, MANIFEST, None)


def test_a_lease_check_item_shows_the_planted_findings_it_relies_on() -> None:
    drafts = {draft.id: draft for draft in load_golden(DRAFTS)}
    sheet = render_item(drafts["fl-0009"], MANIFEST, load_expected())
    assert "**Lease.** `data/leases/fl-lease-01.md`" in sheet
    assert "### The lease's planted findings for these articles (fl-lease-01)" in sheet
    assert "- Clause 9: “The Tenant waives all rights" in sheet


def test_an_out_of_scope_item_is_marked_as_one_to_abstain_on() -> None:
    drafts = {draft.id: draft for draft in load_golden(DRAFTS)}
    assert "**Expected:** abstain (out of scope)." in render_item(
        drafts["oos-0001"], MANIFEST, None
    )


def test_the_command_prints_a_sheet_and_refuses_an_unknown_item(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([str(DRAFTS), "--item", "fl-0001", "--chars", "200"]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("# Review sheet for golden_v0.jsonl")
    assert "## fl-0001 · single_article · easy" in printed
    assert "## fl-0002" not in printed
    assert main([str(DRAFTS), "--item", "fl-9999"]) == 1
    assert "no item fl-9999" in capsys.readouterr().err


def test_a_golden_file_path_may_be_anywhere(tmp_path: Path) -> None:
    copy = tmp_path / "golden_copy.jsonl"
    copy.write_text(DRAFTS.read_text(encoding="utf-8"), encoding="utf-8")
    assert main([str(copy), "--item", "oos-0002"]) == 0
