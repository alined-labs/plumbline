"""The nightly online evaluation (P8b): a tenth of yesterday's production answers, judged
for faithfulness against the passages they cite, so the live site has a quality number
beside the offline ones on /evals.

Production answers have no gold reference, so only faithfulness is judged: is every
statement of law in the answer supported by the sources it cites? The sources are the
cited chunks, read back from the index the answer was served from (its configuration's
variant). The site answers on Claude, so the verdict that counts comes from a judge of
another family: Gemini Flash-Lite, the one validated for Claude-generated answers on
constructed labels (judge/judge.py's prompt, Lane C's C9), with Claude Haiku beside it as
a second opinion and their agreement reported. Both run live and are never recorded:
the questions are the public's, and nothing of them goes into cache/ or a log. Their
spend is counted on the same daily counters as the site's own, so the kill switch sees
it, and the run stops at MAX_JUDGED answers whatever the traffic.

The sample is a hash of the day and the request id, so a rerun of the same day judges the
same answers, and an answer cannot be steered into or out of the sample by its asker.
The night's score is one row in eval_runs (run id `online-<day>`, golden file `production`;
the table's splits are the golden set's, so it is `all`), with
one eval_results row per judged answer holding the verdict only: no question, no answer.

    python -m plumbline.security.online_eval                    # yesterday, UTC
    python -m plumbline.security.online_eval --day 2026-10-22 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Final, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.core.types import CacheMode
from plumbline.db.models import PUBLIC_TENANT, ChunkRow, EvalResultRow, EvalRunRow, QueryRow
from plumbline.db.session import tenant_session
from rag_eval.schema import AnswerStatus
from rag_eval.stats import wilson_interval

log = logging.getLogger("plumbline.online_eval")

SHARE: Final = 0.10  # of the day's answers (PLAN.md, operations 7)
MAX_JUDGED: Final = 30  # whatever the traffic: at most about US$0.32 a night
PRIMARY_JUDGE: Final = "gemini-3.5-flash-lite"  # another family than the served Claude
SECOND_JUDGE: Final = "claude-haiku-5-5"
# Per answer, both judges, rounded up: each reads the answer and its cited passages, a
# few thousand tokens, and writes a short reasoning; Flash-Lite about US$0.0004 (Lane C),
# Haiku under US$0.01; the recorded judgements cost less.
EST_COST_USD: Final = 0.0105
JUDGED_STATUSES: Final = (AnswerStatus.ANSWERED.value, AnswerStatus.PARTIAL.value)


@dataclass(frozen=True)
class Served:
    """One production answer, as the queries table keeps it."""

    request_id: str
    question: str
    answer: str
    config_name: str | None
    config_hash: str | None
    chunk_ids: tuple[str, ...]


@dataclass
class Score:
    day: date
    answered: int  # the day's answers that could be judged
    sampled: int
    judged: int = 0
    passed: int = 0
    judge: str = PRIMARY_JUDGE
    second_judge: str | None = None
    second_judged: int = 0  # of the judged answers, those the second judge also judged
    second_passed: int = 0
    agreed: int = 0  # answers both judged the same way
    cost_usd: float = 0.0
    skipped: dict[str, int] = field(default_factory=dict)  # why, and how many
    verdicts: dict[str, bool] = field(default_factory=dict)  # request id -> passed

    @property
    def rate(self) -> float | None:
        return self.passed / self.judged if self.judged else None

    def summary(self) -> dict[str, Any]:
        low, high = wilson_interval(self.passed, self.judged)
        return {
            "day": self.day.isoformat(),
            "answered": self.answered,
            "sampled": self.sampled,
            "judged": self.judged,
            "faithful": self.passed,
            "faithfulness": self.rate,
            "interval_95": [low, high] if self.judged else None,
            "judge": self.judge,
            "second_judge": self._second(),
            "cost_usd": round(self.cost_usd, 6),
            "skipped": self.skipped,
        }

    def _second(self) -> dict[str, Any] | None:
        if self.second_judge is None:
            return None
        n = self.second_judged
        return {
            "model": self.second_judge,
            "judged": n,
            "faithful": self.second_passed,
            "faithfulness": self.second_passed / n if n else None,
            "agreement": self.agreed / n if n else None,
        }


class Judging(Protocol):
    """What the run needs of judge.judge.Judge."""

    model: str

    async def faithfulness(self, question: str, answer: str, sources: Sequence[str]) -> Any: ...


Sources = Callable[[Served], Awaitable[list[str]]]  # the cited passages' text, in order


def in_sample(day: date, request_id: str, share: float = SHARE) -> bool:
    digest = hashlib.sha256(f"{day.isoformat()}:{request_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") < share * 2**64


def sample(day: date, served: Sequence[Served], share: float = SHARE) -> list[Served]:
    """A tenth of the day's answers, at least one when there are any, at most MAX_JUDGED.
    The cut takes the lowest hashes, so it is the same answers on every rerun."""
    if not served:
        return []
    chosen = [s for s in served if in_sample(day, s.request_id, share)] or [served[0]]
    chosen.sort(key=lambda s: hashlib.sha256(f"{day}:{s.request_id}".encode()).digest())
    return chosen[:MAX_JUDGED]


async def evaluate(
    day: date,
    served: Sequence[Served],
    sources: Sources,
    judge: Judging,
    second: Judging | None = None,
) -> Score:
    """The primary judge's verdict is the score; the second judge's is reported beside it,
    and an answer it fails to judge is left out of its count only."""
    chosen = sample(day, served)
    score = Score(
        day=day,
        answered=len(served),
        sampled=len(chosen),
        judge=judge.model,
        second_judge=second.model if second else None,
    )
    skipped: Counter[str] = Counter()
    for item in chosen:
        texts = await sources(item)
        if not texts:
            skipped["no cited source in the index"] += 1
            continue
        try:
            verdict = await judge.faithfulness(item.question, item.answer, texts)
        except Exception as exc:  # one bad verdict must not lose the night's others
            skipped[f"judge failed: {type(exc).__name__}"] += 1
            continue
        score.judged += 1
        score.passed += bool(verdict.passed)
        score.cost_usd += float(verdict.cost_usd)
        score.verdicts[item.request_id] = bool(verdict.passed)
        if second is None:
            continue
        try:
            other = await second.faithfulness(item.question, item.answer, texts)
        except Exception as exc:
            skipped[f"second judge failed: {type(exc).__name__}"] += 1
            continue
        score.second_judged += 1
        score.second_passed += bool(other.passed)
        score.agreed += bool(other.passed) == bool(verdict.passed)
        score.cost_usd += float(other.cost_usd)
    score.skipped = dict(skipped)
    return score


def served_from(row: QueryRow) -> Served | None:
    answer: Mapping[str, Any] = row.answer or {}
    text = str(answer.get("text") or "").strip()
    if not text:
        return None
    citations = answer.get("citations") or []
    ids = tuple(dict.fromkeys(str(c["chunk_id"]) for c in citations if c.get("chunk_id")))
    return Served(row.request_id, row.question, text, row.config_name, row.config_hash, ids)


async def load(sessions: async_sessionmaker[AsyncSession], day: date) -> list[Served]:
    start = datetime.combine(day, time(0), tzinfo=UTC)
    query = (
        select(QueryRow)
        .where(QueryRow.created_at >= start, QueryRow.created_at < start + timedelta(days=1))
        .where(QueryRow.status.in_(JUDGED_STATUSES), QueryRow.error.is_(None))
        .order_by(QueryRow.created_at)
    )
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        rows = (await session.scalars(query)).all()
    return [s for row in rows if (s := served_from(row)) is not None]


class IndexSources:
    """The cited chunks' text from the variant the answer's configuration searches, as
    judge.source_texts gives the judge offline: the label, then the text."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], variants: Mapping[str, str]
    ) -> None:
        self.sessions, self.variants = sessions, variants  # configuration name -> variant

    async def __call__(self, served: Served) -> list[str]:
        variant = self.variants.get(served.config_name or "")
        if variant is None or not served.chunk_ids:
            return []
        query = select(ChunkRow.id, ChunkRow.label, ChunkRow.text).where(
            ChunkRow.variant == variant, ChunkRow.id.in_(served.chunk_ids)
        )
        async with tenant_session(self.sessions, PUBLIC_TENANT) as session:
            found = {row.id: f"{row.label}\n{row.text}" for row in await session.execute(query)}
        return [found[i] for i in served.chunk_ids if i in found]


async def save(
    sessions: async_sessionmaker[AsyncSession], score: Score, served: Sequence[Served]
) -> str:
    """The night's row and one verdict per judged answer; a rerun replaces both."""
    run_id = f"online-{score.day.isoformat()}"
    configs = Counter((s.config_name or "", s.config_hash or "") for s in served)
    (name, config_hash), _ = configs.most_common(1)[0] if configs else (("", ""), 0)
    async with tenant_session(sessions, PUBLIC_TENANT) as session:
        existing = await session.get(EvalRunRow, run_id)
        if existing is not None:
            await session.delete(existing)  # its results go with it (ON DELETE CASCADE)
            await session.flush()
        session.add(
            EvalRunRow(
                run_id=run_id,
                schema_version=1,
                config_name=name or "unknown",
                config_hash=config_hash or "unknown",
                git_sha=os.environ.get("GIT_SHA", "unknown"),
                golden_file="production",
                split="all",  # eval_runs allows dev, test and all only
                judged=True,
                n_items=score.judged,
                summary=score.summary(),
                notes=f"{SHARE:.0%} sample of the day's answers, faithfulness only",
                created_at=datetime.now(UTC),
            )
        )
        await session.flush()
        session.add_all(
            EvalResultRow(run_id=run_id, item_id=request_id, metrics={"faithful": passed})
            for request_id, passed in score.verdicts.items()
        )
    return run_id


def _variants() -> dict[str, str]:
    from plumbline.api.search import CONFIGS
    from plumbline.core.config import load_configs
    from plumbline.retrieval.index import variant_key

    return {name: variant_key(config) for name, config in load_configs(CONFIGS).items()}


async def run(day: date, dry_run: bool) -> dict[str, Any]:
    from redis.asyncio import Redis

    from plumbline.db import make_engine, make_sessionmaker
    from plumbline.generation.llm import client_for
    from plumbline.generation.router import MeteredClient, RedisSpendMeter
    from plumbline.judge.judge import Judge
    from plumbline.settings import get_settings

    settings = get_settings()
    if settings.cache_mode is not CacheMode.LIVE and not dry_run:
        # Record would write the public's questions, and the Dubai and Colombian text
        # their answers quote, into cache/; replay has nothing recorded to judge with.
        raise SystemExit(f"online evaluation runs with CACHE_MODE=live, not {settings.cache_mode}")
    engine = make_engine(settings.database_url)
    sessions = make_sessionmaker(engine)
    try:
        served = await load(sessions, day)
        planned = len(sample(day, served))
        # Every run states its expected cost before it starts.
        log.info(
            "online evaluation of %s: %d answers, %d to judge on %s and %s, expected at most"
            " US$%.2f",
            day,
            len(served),
            planned,
            PRIMARY_JUDGE,
            SECOND_JUDGE,
            planned * EST_COST_USD,
        )
        if dry_run:
            return {"day": day.isoformat(), "answered": len(served), "to_judge": planned}
        meter = RedisSpendMeter(Redis.from_url(settings.redis_url))
        judges = [
            Judge(client=MeteredClient(client_for(model), meter), model=model)
            for model in (PRIMARY_JUDGE, SECOND_JUDGE)
        ]
        sources = IndexSources(sessions, _variants())
        score = await evaluate(day, served, sources, judges[0], second=judges[1])
        await save(sessions, score, served)
        return score.summary()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m plumbline.security.online_eval")
    parser.add_argument("--day", type=date.fromisoformat, help="UTC day; default yesterday")
    parser.add_argument("--dry-run", action="store_true", help="count and price, judge nothing")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    day = args.day or datetime.now(UTC).date() - timedelta(days=1)
    print(json.dumps(asyncio.run(run(day, args.dry_run)), sort_keys=True))


if __name__ == "__main__":
    main()
