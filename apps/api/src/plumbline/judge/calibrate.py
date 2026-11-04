"""The judge's calibration, end to end: the sheet a person labels, and the agreement table.

`build_sheet` answers the answerable dev items through the pipeline, has the judge give
its verdicts on each answer, and keeps about 100 rows: half the judge passed on both
criteria and half it did not, so TPR and TNR both rest on enough labels. The verdicts
themselves are written nowhere. Every judge call goes through the cache, so `score` gets
the same verdicts back by asking again, from the recordings and at no cost, and the person
labelling never has a file of the judge's opinions within reach.

Dubai's and Colombia's text is fetch-only, so an item the pipeline may answer from it is
answered and judged by a second pipeline and judge (`fetched`) whose recordings go to the
git-ignored fetched cache, and its row goes to the fetched sheet (labels.FETCHED_SHEET).

    python -m plumbline.judge.calibrate score evals/calibration/labelled.jsonl [more sheets]
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Literal

from plumbline.cache import get_cache
from plumbline.core.stream import Question
from plumbline.core.types import AnswerStatus, Jurisdiction
from plumbline.generation.llm import JUDGE_MODEL, client_for
from plumbline.generation.pipeline import Pipeline
from plumbline.ingest.processed import local_cache
from plumbline.judge.calibration import BAR, MIN_LABELS, Agreement, Rate, agreement
from plumbline.judge.judge import PROMPT_VERSION, Judge, source_texts
from plumbline.judge.labels import (
    Candidate,
    CitedQuote,
    LabelRow,
    labelled_pairs,
    read_sheet,
    select,
)
from plumbline.settings import get_settings
from rag_eval.schema import GoldenItem, Split

CRITERIA: tuple[Literal["faithfulness", "correctness"], ...] = ("faithfulness", "correctness")
PUBLIC: Final = frozenset({Jurisdiction.FLORIDA, Jurisdiction.SPAIN})  # text git may hold


def public_only(pipeline: Pipeline, question: str) -> bool:
    """Whether the pipeline can only read public law for this question: it filters by
    jurisdiction, and the detector finds Florida or Spain alone (it finds all four in a
    question naming none). The pipeline's own detector, so the two never disagree."""
    found = set(pipeline.detect(question))
    return pipeline.config.retrieval.jurisdiction_filter and found <= PUBLIC


async def build_sheet(
    items: Sequence[GoldenItem],
    pipeline: Pipeline,
    judge: Judge,
    *,
    config_name: str,
    fetched: tuple[Pipeline, Judge] | None = None,  # the same, recording to the fetched cache
    n: int = 100,
    seed: int = 0,
    concurrency: int = 4,
) -> list[LabelRow]:
    """The labelling sheet: dev items with a reference answer, answered (an abstention has
    nothing to judge, so it is left out), then chosen half likely to pass, half not. With
    no `fetched` pair, items that may read fetch-only law are left out."""
    dev = [i for i in items if i.split is Split.DEV and i.reference_answer]
    limit = asyncio.Semaphore(concurrency)

    async def one(item: GoldenItem) -> Candidate | None:
        restricted = not public_only(pipeline, item.question)
        if restricted and fetched is None:
            return None
        answering, judging = fetched if restricted and fetched else (pipeline, judge)
        async with limit:
            # The law of the lease's signing day, or of the item's date: never today's by default.
            as_of = item.signed_on or item.as_of
            question = Question(text=item.question, as_of=as_of, request_id=f"cal-{item.id}")
            answer, trace = await answering.answer(question, eval_run_id="calibration")
            if answer.status is AnswerStatus.ABSTAINED:
                return None
            row = LabelRow(
                id=item.id,  # replaced by select()
                item_id=item.id,
                config=config_name,
                question=item.question,
                answer=answer.text,
                citations=[
                    CitedQuote(n=c.n, label=c.label, quote=c.quote, gloss=c.gloss)
                    for c in answer.citations
                ],
                sources=source_texts(trace.retrieved),
                reference_answer=item.reference_answer or "",
                restricted=restricted,
            )
            verdicts = await verdicts_for(judging, row)
        return Candidate(row, likely_pass=all(verdicts.values()))

    found = await asyncio.gather(*(one(item) for item in dev))
    return select([c for c in found if c is not None], n=n, seed=seed)


async def verdicts_for(judge: Judge, row: LabelRow) -> dict[str, bool]:
    """The judge's verdicts on one row, from the same inputs every time (so from the cache
    once recorded)."""
    faithful = await judge.faithfulness(row.question, row.answer, row.sources)
    correct = await judge.correctness(row.question, row.answer, row.reference_answer)
    return {"faithfulness": faithful.passed, "correctness": correct.passed}


async def score(
    rows: Sequence[LabelRow], judge: Judge, fetched: Judge | None = None
) -> list[Agreement]:
    """Agreement per criterion between the person's labels and the judge's verdicts. A
    restricted row is judged by `fetched`, the same judge recording to the fetched cache."""
    labelled = [r for r in rows if r.faithfulness is not None or r.correctness is not None]
    if fetched is None and any(r.restricted for r in labelled):
        raise ValueError("restricted rows need the judge on the fetched cache")
    judged = {
        r.id: await verdicts_for(fetched if r.restricted and fetched else judge, r)
        for r in labelled
    }
    return [agreement(c, labelled_pairs(labelled, judged, c)) for c in CRITERIA]


def report(agreements: Sequence[Agreement], model: str, version: str = PROMPT_VERSION) -> str:
    """One Markdown table row per criterion, intervals included, for evals/calibration. The
    bar is met on point estimates; the last column says which lower bounds clear it too,
    since at 50 labels a rate of 0.84 has a lower bound near 0.71."""
    lines = []
    for a in agreements:
        bar = "meets the bar" if a.meets(BAR) else "below the bar"
        if a.meets(BAR, least=1) and not a.meets(BAR):
            bar = f"too few labels (under {MIN_LABELS} a class)"
        row = [version, model, a.criterion, _cell(a.tpr), _cell(a.tnr), bar, _lower(a)]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _lower(agreement: Agreement) -> str:
    """Which rates' 95% lower bounds clear the bar: both, TPR only, TNR only or neither."""
    clear = [
        name
        for name, rate in (("TPR", agreement.tpr), ("TNR", agreement.tnr))
        if rate.total and rate.low >= BAR
    ]
    return {0: "neither", 2: "both"}.get(len(clear), f"{clear[0]} only" if clear else "neither")


def _cell(rate: Rate) -> str:
    if rate.value is None:
        return "no labels"
    return f"{rate.value:.2f} [{rate.low:.2f}, {rate.high:.2f}] ({rate.hits}/{rate.total})"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m plumbline.judge.calibrate")
    commands = parser.add_subparsers(dest="command", required=True)
    scoring = commands.add_parser("score", help="agreement between labels and the judge")
    scoring.add_argument("sheets", type=Path, nargs="+", help="the committed and fetched sheets")
    args = parser.parse_args(argv)
    rows = [row for sheet in args.sheets for row in read_sheet(sheet)]
    judge = Judge()
    fetched = None
    if any(r.restricted for r in rows):
        cache = get_cache(get_settings().cache_mode, local_cache())
        fetched = Judge(client_for(JUDGE_MODEL, cache=cache))
    agreements = asyncio.run(score(rows, judge, fetched))
    print(report(agreements, judge.model))


if __name__ == "__main__":
    main()
