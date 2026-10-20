"""The labelling sheet for the judge's calibration: dev answers a person labels pass or fail.

The sheet, evals/calibration/to_label.jsonl, holds one answer per line with what a person
needs to label it: the question, the answer, its citations, the sources it was written
from and the reference answer, with the labels empty. It never shows the judge's verdict,
so the labels cannot lean on it. About half the rows are answers likely to pass and half
likely to fail, by a signal known before any label (the caller's: a first judge run, or
signs such as invalid citations), so both TPR and TNR have enough labels behind them.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from plumbline.core.types import Frozen

Label = Literal["pass", "fail"]


class CitedQuote(Frozen):
    n: int = Field(ge=1)
    label: str
    quote: str
    gloss: str | None = None


class LabelRow(Frozen):
    id: str  # "cal-001", in the order the person labels them
    item_id: str  # the golden item the answer is for
    config: str  # the configuration that wrote the answer
    question: str
    answer: str
    citations: list[CitedQuote] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)  # each source's label, then its text
    reference_answer: str
    # For the person: is every statement of law supported by the sources?
    faithfulness: Label | None = None
    # For the person: does the answer state the reference's rule?
    correctness: Label | None = None
    notes: str | None = None


@dataclass(frozen=True)
class Candidate:
    row: LabelRow
    likely_pass: bool


def select(candidates: Sequence[Candidate], n: int = 100, seed: int = 0) -> list[LabelRow]:
    """n rows, half likely to pass and half likely to fail where the candidates allow it
    (a short half is filled from the other), drawn reproducibly from the seed, shuffled so
    the halves cannot be told apart, and numbered in labelling order."""
    rng = random.Random(seed)  # noqa: S311  # a reproducible sample, not a secret
    passing = [c.row for c in candidates if c.likely_pass]
    failing = [c.row for c in candidates if not c.likely_pass]
    rng.shuffle(passing)
    rng.shuffle(failing)
    take_passing = min(len(passing), max(n // 2, n - len(failing)))
    chosen = passing[:take_passing] + failing[: n - take_passing]
    rng.shuffle(chosen)
    return [row.model_copy(update={"id": f"cal-{i:03d}"}) for i, row in enumerate(chosen, 1)]


def write_sheet(rows: Sequence[LabelRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row.model_dump(mode="json"), ensure_ascii=False) for row in rows]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def read_sheet(path: Path) -> list[LabelRow]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(LabelRow.model_validate_json(line))
        except ValidationError as exc:
            raise ValueError(f"{path.name}, line {number}: {exc}") from exc
    return rows


def labelled_pairs(
    rows: Sequence[LabelRow],
    judged: Mapping[str, Mapping[str, bool]],  # row id -> criterion -> the judge passed it
    criterion: Literal["faithfulness", "correctness"],
) -> list[tuple[bool, bool]]:
    """(person passed, judge passed) for every row the person labelled on this criterion
    and the judge scored, the input calibration.agreement expects."""
    pairs = []
    for row in rows:
        label = getattr(row, criterion)
        verdict = judged.get(row.id, {}).get(criterion)
        if label is not None and verdict is not None:
            pairs.append((label == "pass", verdict))
    return pairs
