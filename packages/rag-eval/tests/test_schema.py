import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from rag_eval.schema import (
    ArticleRef,
    EvalResult,
    EvalRun,
    GoldenFileError,
    GoldenItem,
    Jurisdiction,
    Verification,
    dump_golden,
    load_golden,
)

REF = {"jurisdiction": "florida", "law": "fl-stat-83", "article": "83.49", "edition": "2026"}


def item(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "fl-0001",
        "question": "How long does a Florida landlord have to return a security deposit?",
        "source_language": "en",
        "jurisdictions": ["florida"],
        "category": "single_article",
        "difficulty": "easy",
        "gold_refs": [REF],
        "reference_answer": "Fifteen days if no claim is made, under s. 83.49(3)(a).",
        "source_type": "official_faq",
        "added_in": "v0",
    }
    row.update(overrides)
    return row


def test_a_complete_item_validates_and_keys_by_article() -> None:
    golden = GoldenItem.model_validate(item())
    assert golden.gold_refs[0].key == "florida:fl-stat-83:83.49"
    assert golden.jurisdictions == [Jurisdiction.FLORIDA]


def test_paragraphs_and_editions_do_not_change_the_key() -> None:
    a = ArticleRef.model_validate(REF)
    b = ArticleRef.model_validate({**REF, "paragraph": "(3)(a)", "edition": "2025"})
    assert a.key == b.key


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"gold_refs": []}, "gold_ref"),
        ({"reference_answer": None}, "reference_answer"),
        ({"expected_abstain": True}, "out_of_scope"),
        ({"category": "out_of_scope"}, "out_of_scope"),
        ({"partial": True}, "partial"),
        ({"category": "lease_check"}, "lease_id"),
        ({"category": "cross_jurisdiction"}, "two jurisdictions"),
        ({"jurisdictions": ["spain"]}, "not listed"),
        ({"question": "short"}, "at least 8"),
        ({"added_in": "0"}, "pattern"),
        ({"surprise": 1}, "Extra inputs"),
    ],
)
def test_inconsistent_items_are_refused(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        GoldenItem.model_validate(item(**overrides))


def test_out_of_scope_items_need_no_refs_or_answer() -> None:
    GoldenItem.model_validate(
        item(
            category="out_of_scope",
            expected_abstain=True,
            gold_refs=[],
            reference_answer=None,
            jurisdictions=[],
        )
    )


CHECKED = {"checked_on": "2026-10-21", "checked_by": "a reviewer"}


def test_a_verification_has_a_second_source_or_says_why_not() -> None:
    exactly_one = "exactly one of second_source and no_second_source"
    with pytest.raises(ValidationError, match=exactly_one):
        Verification.model_validate({**CHECKED, "quoted_text": "x", "notes": "agreed"})
    with pytest.raises(ValidationError, match="at least 1 character"):
        Verification.model_validate({**CHECKED, "quoted_text": "x", "no_second_source": "  "})
    both = {"second_source": "A pamphlet, https://example.org", "no_second_source": "none found"}
    with pytest.raises(ValidationError, match=exactly_one):
        Verification.model_validate({**CHECKED, "quoted_text": "x", **both})
    reason = "None found: the regulator's FAQ does not cover this provision."
    assert Verification.model_validate({**CHECKED, "quoted_text": "x", "no_second_source": reason})


def test_a_verified_item_that_cites_an_article_quotes_it() -> None:
    unquoted = {**CHECKED, "second_source": "A pamphlet, https://example.org"}
    with pytest.raises(ValidationError, match="quotes it in quoted_text"):
        GoldenItem.model_validate(item(verification=unquoted))
    GoldenItem.model_validate(
        item(
            category="out_of_scope",
            expected_abstain=True,
            gold_refs=[],
            reference_answer=None,
            jurisdictions=[],
            verification=unquoted,
        )
    )


def test_load_golden_names_bad_lines_and_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "golden_v0.jsonl"
    rows = [item(), item(), {"id": "broken"}, item(id="fl-0002")]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    with pytest.raises(GoldenFileError) as error:
        load_golden(path)
    assert "golden_v0.jsonl:2: duplicate id fl-0001" in str(error.value)
    assert "golden_v0.jsonl:3:" in str(error.value)


def test_dump_then_load_round_trips(tmp_path: Path) -> None:
    items = [
        GoldenItem.model_validate(item(id=f"fl-000{i}", as_of=date(2026, 1, i))) for i in (1, 2)
    ]
    path = tmp_path / "golden_v1.jsonl"
    dump_golden(items, path)
    assert load_golden(path) == items


def run(results: list[EvalResult], n: int) -> dict[str, Any]:
    return {
        "run_id": "a2-dev-1",
        "config_name": "A2",
        "config_hash": "a" * 64,
        "git_sha": "abc1234",
        "golden_file": "data/golden/golden_v0.jsonl",
        "golden_sha256": "b" * 64,
        "split": "dev",
        "created_at": datetime(2026, 10, 19, tzinfo=UTC),
        "judged": False,
        "n_items": n,
        "results": results,
    }


def test_runs_must_be_complete_and_unique() -> None:
    one = EvalResult(item_id="fl-0001", metrics={"recall@5": 1.0})
    EvalRun.model_validate(run([one], 1))
    with pytest.raises(ValidationError, match="n_items"):
        EvalRun.model_validate(run([one], 2))
    with pytest.raises(ValidationError, match="twice"):
        EvalRun.model_validate(run([one, one], 2))
