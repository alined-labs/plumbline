"""Calibration: agreement with intervals, and the labelling sheet."""

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from plumbline.judge.calibration import agreement
from plumbline.judge.labels import (
    Candidate,
    LabelRow,
    labelled_pairs,
    read_sheet,
    select,
    write_sheet,
)
from rag_eval.stats import wilson_interval


def test_tpr_and_tnr_count_the_right_answers() -> None:
    person = [True, True, True, False, False]
    judge = [True, True, False, False, True]
    result = agreement("correctness", list(zip(person, judge, strict=True)))
    assert (result.tpr.hits, result.tpr.total, result.tnr.hits, result.tnr.total) == (2, 3, 1, 2)
    assert (result.tpr.low, result.tpr.high) == wilson_interval(2, 3)
    assert not result.meets()


def test_the_bar_needs_both_rates_and_labels_behind_them() -> None:
    perfect = agreement("faithfulness", [(True, True)] * 45 + [(False, False)] * 20)
    assert perfect.meets()
    few = agreement("faithfulness", [(True, True)] * 45 + [(False, False)] * 5)
    assert few.tnr.low < 0.6  # five labels: right, but far from proven
    assert not few.meets()
    assert not agreement("faithfulness", [(True, True)] * 50).meets()  # no failed answers
    lenient = agreement("faithfulness", [(True, True)] * 50 + [(False, True)] * 50)
    assert (lenient.tpr.value, lenient.tnr.value, lenient.meets()) == (1.0, 0.0, False)


@given(st.lists(st.tuples(st.booleans(), st.booleans()), max_size=60))
def test_every_rate_sits_inside_its_interval(pairs: list[tuple[bool, bool]]) -> None:
    result = agreement("correctness", pairs)
    for rate in (result.tpr, result.tnr):
        assert 0 <= rate.hits <= rate.total
        if rate.value is not None:
            # wilson_interval misses 0 and 1 by float error (2.8e-17 at k = 0): Lane A's.
            assert rate.low - 1e-12 <= rate.value <= rate.high + 1e-12
    assert result.tpr.total + result.tnr.total == len(pairs)


def row(item: str, **labels: str) -> LabelRow:
    return LabelRow(
        id="x",
        item_id=item,
        config="A2",
        question="How long does my landlord have to return my deposit?",
        answer="Within 15 days if the landlord makes no claim [1].",
        reference_answer="Within 15 days if the landlord makes no claim on it.",
        **labels,
    )


@pytest.mark.parametrize(
    ("passing", "failing", "expected"),
    [(80, 80, (50, 50)), (80, 30, (70, 30)), (20, 90, (20, 80)), (10, 20, (10, 20))],
)
def test_selection_balances_and_fills_a_short_half(
    passing: int, failing: int, expected: tuple[int, int]
) -> None:
    candidates = [Candidate(row(f"p-{i}"), True) for i in range(passing)]
    candidates += [Candidate(row(f"f-{i}"), False) for i in range(failing)]
    chosen = select(candidates, n=100, seed=7)
    picked_pass = sum(r.item_id.startswith("p-") for r in chosen)
    assert (picked_pass, len(chosen) - picked_pass) == expected
    assert [r.id for r in chosen] == [f"cal-{i:03d}" for i in range(1, len(chosen) + 1)]
    assert select(candidates, n=100, seed=7) == chosen  # reproducible from the seed


def test_the_sheet_round_trips_and_names_a_bad_line(tmp_path: Path) -> None:
    sheet = tmp_path / "to_label.jsonl"
    rows = [row("fl-0001"), row("es-0002", faithfulness="pass", correctness="fail")]
    write_sheet(rows, sheet)
    assert read_sheet(sheet) == rows
    assert "judge" not in sheet.read_text(encoding="utf-8")  # the labeller never sees it
    broken = json.loads(sheet.read_text(encoding="utf-8").splitlines()[0]) | {
        "correctness": "maybe"
    }
    sheet.write_text(json.dumps(broken) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        read_sheet(sheet)


def test_pairs_keep_only_rows_both_sides_scored() -> None:
    rows = [
        row("a", correctness="pass").model_copy(update={"id": "cal-001"}),
        row("b", correctness="fail").model_copy(update={"id": "cal-002"}),
        row("c").model_copy(update={"id": "cal-003"}),  # not labelled
        row("d", correctness="pass").model_copy(update={"id": "cal-004"}),  # not judged
    ]
    judged = {
        "cal-001": {"correctness": True},
        "cal-002": {"correctness": True},
        "cal-003": {"correctness": False},
    }
    assert labelled_pairs(rows, judged, "correctness") == [(True, True), (False, True)]
