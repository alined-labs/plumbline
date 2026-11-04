"""The nightly online evaluation: the same tenth of a day on every rerun, a bounded night
whatever the traffic, verdicts on the cited passages only, and a stored score that holds
no question and no answer."""

from __future__ import annotations

import asyncio
import functools
import json
import uuid
from collections.abc import Callable, Coroutine, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, select

from plumbline.api.evals import night
from plumbline.core.types import CacheMode
from plumbline.db import make_engine, make_sessionmaker, make_sync_engine, make_sync_sessionmaker
from plumbline.db.models import (
    PUBLIC_TENANT,
    ChunkRow,
    Document,
    EvalResultRow,
    EvalRunRow,
    QueryRow,
)
from plumbline.security import online_eval
from plumbline.security.online_eval import (
    MAX_JUDGED,
    IndexSources,
    Served,
    evaluate,
    load,
    sample,
    save,
)
from plumbline.settings import Settings

DAY = date(2026, 10, 22)
QUESTION = "Can my landlord keep the deposit for repainting?"


def sync(test: Callable[..., Coroutine[Any, Any, None]]) -> Callable[..., None]:
    @functools.wraps(test)
    def run(*args: Any, **kwargs: Any) -> None:
        asyncio.run(test(*args, **kwargs))

    return run


def served(n: int, chunks: tuple[str, ...] = ("fl:83.49",)) -> list[Served]:
    return [
        Served(f"req-{i}", QUESTION, f"Answer {i} [1].", "A2-claude", "h" * 8, chunks)
        for i in range(n)
    ]


@dataclass
class Verdict:
    passed: bool
    cost_usd: float = 0.002


class Judge:
    def __init__(
        self, fail_on: str = "", model: str = "gemini-3.5-flash-lite", strict: bool = False
    ) -> None:
        self.fail_on, self.model, self.strict = fail_on, model, strict
        self.seen: list[tuple[str, str, list[str]]] = []

    async def faithfulness(self, question: str, answer: str, sources: Sequence[str]) -> Verdict:
        if self.fail_on and self.fail_on in answer:
            raise ValueError("unreadable verdict")
        self.seen.append((question, answer, list(sources)))
        # A strict judge also fails answers ending in 1, so the two disagree on those.
        failing = ("0", "1") if self.strict else ("0",)
        return Verdict(passed=not any(f"{d} [1]" in answer for d in failing))


async def two_sources(item: Served) -> list[str]:
    return [f"Fla. Stat. {c}\nThe text." for c in item.chunk_ids]


async def no_sources(item: Served) -> list[str]:
    return []


def test_the_sample_is_a_tenth_and_the_same_on_every_rerun() -> None:
    day = served(1000)
    chosen = sample(DAY, day)
    assert chosen == sample(DAY, list(reversed(day)))
    assert len(chosen) == MAX_JUDGED  # a tenth of a thousand, cut at the night's bound
    assert sum(online_eval.in_sample(DAY, s.request_id) for s in day) in range(70, 131)


def test_a_quiet_day_still_judges_one_answer_and_an_empty_day_none() -> None:
    assert len(sample(DAY, served(3))) >= 1
    assert sample(DAY, []) == []


@sync
async def test_each_sampled_answer_is_judged_on_its_cited_passages() -> None:
    judge = Judge()
    score = await evaluate(DAY, served(5), two_sources, judge)
    assert score.judged == len(judge.seen) == score.sampled
    question, _, sources = judge.seen[0]
    assert question == QUESTION
    assert sources == ["Fla. Stat. fl:83.49\nThe text."]
    assert score.cost_usd == pytest.approx(0.002 * score.judged)


@sync
async def test_an_answer_with_no_source_or_a_failed_verdict_is_skipped_and_said() -> None:
    nothing = await evaluate(DAY, served(5), no_sources, Judge())
    assert nothing.judged == 0
    assert nothing.skipped == {"no cited source in the index": nothing.sampled}
    assert nothing.rate is None
    broken = await evaluate(DAY, served(5), two_sources, Judge(fail_on="Answer"))
    assert broken.skipped == {"judge failed: ValueError": broken.sampled}


@sync
async def test_the_summary_holds_numbers_and_no_question_or_answer() -> None:
    score = await evaluate(DAY, served(40), two_sources, Judge())
    summary = json.dumps(score.summary())
    assert QUESTION not in summary
    assert "Answer" not in summary
    assert score.summary()["judged"] == score.judged
    low, high = score.summary()["interval_95"]
    assert 0 <= low <= (score.rate or 0) <= high <= 1


def test_only_an_answer_with_text_is_served_and_its_cited_chunks_are_kept_once() -> None:
    row = QueryRow(
        request_id="r1",
        question=QUESTION,
        config_name="A2-claude",
        config_hash="abc",
        answer={"text": " It may not [1][2]. ", "citations": [
            {"chunk_id": "fl:83.49"}, {"chunk_id": "fl:83.49"}, {"chunk_id": "fl:83.51"},
        ]},
    )  # fmt: skip
    item = online_eval.served_from(row)
    assert item is not None
    assert item.answer == "It may not [1][2]."
    assert item.chunk_ids == ("fl:83.49", "fl:83.51")
    assert online_eval.served_from(QueryRow(request_id="r2", question="q", answer=None)) is None


# The database: what the night reads and what it writes.

VARIANT = "0e1ine0e1ine"


@pytest.fixture
def owner(database_url: str) -> Iterator[Engine]:
    engine = make_sync_engine(database_url)
    yield engine
    engine.dispose()


def _seed(owner: Engine, tag: str) -> None:
    document = Document(
        id=f"online-{tag}",
        tenant_id=PUBLIC_TENANT,
        law="fl-stat-83",
        jurisdiction="florida",
        language="en",
        edition="test",
        sha256="0" * 64,
        parser="test",
        page_count=1,
    )
    chunk = ChunkRow(
        variant=VARIANT,
        id=f"online-{tag}:83.49",
        tenant_id=PUBLIC_TENANT,
        document_id=document.id,
        jurisdiction="florida",
        law="fl-stat-83",
        language="en",
        edition="test",
        article="83.49",
        label="Fla. Stat. 83.49",
        text="The landlord shall hold the deposit.",
        text_for_search="The landlord shall hold the deposit.",
    )
    at = datetime(DAY.year, DAY.month, DAY.day, 12, tzinfo=UTC)

    def query(request_id: str, status: str, day: datetime = at) -> QueryRow:
        citations = [{"chunk_id": chunk.id}]
        return QueryRow(
            tenant_id=PUBLIC_TENANT,
            request_id=request_id,
            question=QUESTION,
            tier="full",
            status=status,
            config_name="A2-claude",
            config_hash="abc",
            answer={"text": "It must be held [1].", "citations": citations},
            created_at=day,
        )

    with make_sync_sessionmaker(owner)() as session, session.begin():
        session.add(document)
        session.flush()
        session.add_all(
            [
                chunk,
                query(f"{tag}-answered", "answered"),
                query(f"{tag}-abstained", "abstained"),
                query(f"{tag}-yesterday", "answered", datetime(2026, 10, 21, 23, tzinfo=UTC)),
            ]
        )


@pytest.mark.db
@sync
async def test_a_night_reads_the_days_answers_and_stores_only_verdicts(
    database_url: str, owner: Engine
) -> None:
    tag = uuid.uuid4().hex[:8]
    _seed(owner, tag)
    engine = make_engine(database_url)
    sessions = make_sessionmaker(engine)
    try:
        day = [s for s in await load(sessions, DAY) if s.request_id.startswith(tag)]
        assert [s.request_id for s in day] == [f"{tag}-answered"]  # not abstained, not the 21st
        sources = IndexSources(sessions, {"A2-claude": VARIANT})
        assert await sources(day[0]) == ["Fla. Stat. 83.49\nThe landlord shall hold the deposit."]
        score = await evaluate(DAY, day, sources, Judge())
        run_id = await save(sessions, score, day)
        await save(sessions, score, day)  # a rerun replaces the night
    finally:
        await engine.dispose()
    with make_sync_sessionmaker(owner)() as session:
        run = session.get(EvalRunRow, run_id)
        assert run is not None
        assert (run.golden_file, run.split, run.n_items) == ("production", "all", 1)
        results = session.scalars(select(EvalResultRow).where(EvalResultRow.run_id == run_id))
        stored = [(r.item_id, r.metrics, r.answer) for r in results]
    assert stored == [(f"{tag}-answered", {"faithful": True}, None)]
    assert QUESTION not in json.dumps(run.summary)


@sync
async def test_the_second_judge_is_reported_beside_the_first_and_never_changes_the_score() -> None:
    alone = await evaluate(DAY, served(40), two_sources, Judge())
    both = await evaluate(
        DAY, served(40), two_sources, Judge(), second=Judge(model="claude-haiku-5-5", strict=True)
    )
    assert (both.judged, both.passed) == (alone.judged, alone.passed)
    second = both.summary()["second_judge"]
    assert second["model"] == "claude-haiku-5-5"
    assert second["judged"] == both.judged
    assert second["faithful"] <= both.passed
    assert second["agreement"] == pytest.approx(
        (both.judged - (both.passed - second["faithful"])) / both.judged
    )
    assert both.summary()["judge"] == "gemini-3.5-flash-lite"
    assert alone.summary()["second_judge"] is None


@sync
async def test_a_second_judge_that_fails_costs_only_its_own_count() -> None:
    score = await evaluate(
        DAY, served(5), two_sources, Judge(), second=Judge(fail_on="Answer", model="haiku")
    )
    assert score.judged == score.sampled
    assert score.summary()["second_judge"]["judged"] == 0
    assert score.skipped == {"second judge failed: ValueError": score.sampled}


def test_the_night_refuses_any_cache_mode_but_live(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, cache_mode=CacheMode.RECORD)
    monkeypatch.setattr("plumbline.settings.get_settings", lambda: settings)
    with pytest.raises(SystemExit, match="CACHE_MODE=live"):
        asyncio.run(online_eval.run(DAY, dry_run=False))


@sync
async def test_the_stored_summary_is_the_shape_the_public_route_reads() -> None:
    score = await evaluate(DAY, served(40), two_sources, Judge(), second=Judge(model="haiku"))
    row = EvalRunRow(run_id=f"online-{DAY}", config_name="A2-claude", summary=score.summary())
    shown = night(row)
    assert shown is not None
    assert (shown.day, shown.judged, shown.faithful) == (DAY, score.judged, score.passed)
