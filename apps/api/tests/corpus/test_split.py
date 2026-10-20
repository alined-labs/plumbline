"""The seeded, stratified dev/test split of a golden file."""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

import pytest

from plumbline.corpus.split import (
    SEED,
    assign_splits,
    category_of,
    drop_after_split,
    language_of,
    main,
    place_of,
    report,
)
from plumbline.settings import ROOT
from rag_eval.schema import (
    ArticleRef,
    Category,
    Difficulty,
    GoldenItem,
    Jurisdiction,
    Language,
    SourceType,
    Split,
    load_golden,
)

DRAFT = ROOT / "data" / "golden" / "drafts" / "golden_v1.jsonl"


def make_item(
    number: int, category: Category, places: list[Jurisdiction], language: Language
) -> GoldenItem:
    abstain = category is Category.OUT_OF_SCOPE
    refs = [
        ArticleRef(jurisdiction=place, law="a-law", article=str(number), edition="e1")
        for place in places
    ]
    return GoldenItem(
        id=f"t-{number:04d}",
        question=f"A question numbered {number}?",
        source_language=language,
        jurisdictions=[] if abstain else places,
        category=category,
        difficulty=Difficulty.MEDIUM,
        gold_refs=[] if abstain else refs,
        reference_answer=None if abstain else "An answer.",
        expected_abstain=abstain,
        partial=category is Category.PARTIAL,
        lease_id="a-lease" if category is Category.LEASE_CHECK else None,
        source_type=SourceType.SYNTHETIC,
        added_in="v1",
    )


def make_items(count: int = 90) -> list[GoldenItem]:
    """A mixed set: every third item a comparison, every ninth out of scope, two languages."""
    spread = [Jurisdiction.FLORIDA, Jurisdiction.SPAIN, Jurisdiction.COLOMBIA, Jurisdiction.DUBAI]
    items = []
    for number in range(count):
        language = Language.ES if number % 2 else Language.EN
        if number % 9 == 0:
            items.append(make_item(number, Category.OUT_OF_SCOPE, [], language))
        elif number % 3 == 0:
            items.append(make_item(number, Category.CROSS_JURISDICTION, spread[:2], language))
        elif number % 5 == 0:
            items.append(make_item(number, Category.LEASE_CHECK, [spread[number % 4]], language))
        else:
            items.append(make_item(number, Category.SINGLE_ARTICLE, [spread[number % 4]], language))
    return items


def test_the_split_has_the_sizes_asked_for_and_keeps_every_other_field() -> None:
    items = make_items()
    split = assign_splits(items, 30)
    assert Counter(item.split for item in split) == {Split.DEV: 60, Split.TEST: 30}
    assert [item.id for item in split] == [item.id for item in items]
    for before, after in zip(items, split, strict=True):
        assert after.model_dump(exclude={"split"}) == before.model_dump(exclude={"split"})


def test_each_category_gets_its_share_of_test_to_within_one_item() -> None:
    items = make_items()
    split = assign_splits(items, 30)
    for category in Category:
        group = [item for item in split if item.category is category]
        if group:
            test = sum(item.split is Split.TEST for item in group)
            assert abs(test - len(group) / 3) < 1, category


def test_the_split_is_the_same_whatever_the_order_of_the_lines() -> None:
    items = make_items()
    shuffled = items[:]
    random.Random(7).shuffle(shuffled)
    first = {item.id: item.split for item in assign_splits(items, 30)}
    second = {item.id: item.split for item in assign_splits(shuffled, 30)}
    assert first == second


def test_the_seed_decides_which_items_and_the_same_seed_decides_the_same() -> None:
    items = make_items()
    one = {item.id: item.split for item in assign_splits(items, 30, "one")}
    again = {item.id: item.split for item in assign_splits(items, 30, "one")}
    other = {item.id: item.split for item in assign_splits(items, 30, "other")}
    assert one == again
    assert one != other
    # A different seed moves items but never the number of test items in a category.
    for category in Category:
        ids = {item.id for item in items if item.category is category}
        assert sum(one[i] is Split.TEST for i in ids) == sum(other[i] is Split.TEST for i in ids)


def test_a_set_with_a_split_already_is_not_cut_again() -> None:
    split = assign_splits(make_items(), 30)
    with pytest.raises(ValueError, match="already split"):
        assign_splits(split, 30)


def test_a_test_size_the_set_cannot_give_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot put"):
        assign_splits(make_items(9), 10)
    with pytest.raises(ValueError, match="cannot put"):
        assign_splits(make_items(9), -1)


def test_ids_must_be_unique() -> None:
    items = make_items(6)
    with pytest.raises(ValueError, match="unique"):
        assign_splits([*items, items[0]], 2)


def test_a_comparison_is_one_place_and_a_question_with_no_place_is_another() -> None:
    items = make_items(12)
    places = {item.id: place_of(item) for item in items}
    assert places["t-0003"] == "several"
    assert places["t-0000"] == "none"
    assert places["t-0001"] == "spain"
    assert category_of(items[3]) == "cross_jurisdiction"
    assert language_of(items[1]) == "es"


def test_the_command_reports_and_writes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from rag_eval.schema import dump_golden

    source, target = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    dump_golden(make_items(), source)
    assert main([str(source), "--test", "30"]) == 0
    assert not target.exists()
    assert main([str(source), str(target), "--test", "30"]) == 0
    written = load_golden(target)
    assert sum(item.split is Split.TEST for item in written) == 30
    printed = capsys.readouterr().out
    assert "| category | dev | test | all |" in printed
    assert "| single_article |" in printed
    # The default is a third of the file.
    assert main([str(source), str(target)]) == 0
    assert sum(item.split is Split.TEST for item in load_golden(target)) == 30
    # A file that already has a split is refused.
    assert main([str(target)]) == 1
    assert "already split" in capsys.readouterr().err


def test_the_report_counts_every_item_once() -> None:
    split = assign_splits(make_items(), 30)
    table = report(split)
    for title in ("category", "place", "language"):
        assert f"| {title} | dev | test | all |" in table
    totals = [int(line.split("|")[4]) for line in table.splitlines() if line.startswith("| en ")]
    assert totals == [sum(item.source_language is Language.EN for item in split)]


@pytest.mark.skipif(not DRAFT.is_file(), reason="the v1 draft is not on this branch")
def test_the_v1_draft_splits_into_120_and_60_with_every_category_in_both() -> None:
    items = load_golden(DRAFT)
    assert len(items) == 180
    split = assign_splits(items, 60, SEED)
    assert Counter(item.split for item in split) == {Split.DEV: 120, Split.TEST: 60}
    for category in Category:
        group = [item for item in split if item.category is category]
        assert {item.split for item in group} == {Split.DEV, Split.TEST}, category
        assert abs(sum(item.split is Split.TEST for item in group) - len(group) / 3) < 1
    for key in (place_of, language_of):
        for name in {key(item) for item in split}:
            group = [item for item in split if key(item) == name]
            test = sum(item.split is Split.TEST for item in group)
            assert abs(test - len(group) / 3) <= 3, name


def test_dropped_items_leave_after_the_split_so_the_others_keep_their_side() -> None:
    items = make_items()
    split = assign_splits(items, 30)
    gone = [split[0].id, split[1].id]
    kept = drop_after_split(split, gone)
    assert [item.id for item in kept] == [item.id for item in split[2:]]
    assert {item.id: item.split for item in kept} == {item.id: item.split for item in split[2:]}
    with pytest.raises(ValueError, match="not in the file: zz-0001"):
        drop_after_split(split, ["zz-0001"])


def test_the_command_drops_after_splitting(tmp_path: Path) -> None:
    from rag_eval.schema import dump_golden

    source, whole, frozen = tmp_path / "in.jsonl", tmp_path / "all.jsonl", tmp_path / "out.jsonl"
    items = make_items()
    dump_golden(items, source)
    assert main([str(source), str(whole), "--test", "30"]) == 0
    gone = [items[0].id, items[5].id]
    args = [str(source), str(frozen), "--test", "30", "--drop", gone[0], "--drop", gone[1]]
    assert main(args) == 0
    sides = {item.id: item.split for item in load_golden(whole)}
    written = load_golden(frozen)
    assert len(written) == len(items) - 2
    assert all(item.split is sides[item.id] for item in written)
    assert main([str(source), str(frozen), "--drop", "zz-0001"]) == 1
