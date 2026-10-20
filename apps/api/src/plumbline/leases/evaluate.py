"""The lease checker's evaluation: every synthetic lease (data/leases) checked as the site
checks an upload, then scored against its answer key (scoring.py), per lease and pooled.

The search is a configuration's (A2-claude by default, the one the API serves), the model
the route's, and each lease is read under the law in force on the day it was signed. Leases
under Dubai's or Colombian law are checked against that law's text, which is fetch-only, so
their recordings go to the git-ignored fetched cache; the rest record into cache/.

    uv run python -m plumbline.leases.evaluate [--lease fl-lease-01 ...] [--out FILE.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from plumbline.cache import get_cache
from plumbline.core.config import load_config
from plumbline.core.types import Jurisdiction, Language
from plumbline.corpus.leases import ExpectedLease, load_expected
from plumbline.db import make_sync_engine, make_sync_sessionmaker
from plumbline.generation.llm import PREMIUM_MODEL, client_for
from plumbline.generation.router import SyntheticOnlyRedactor, Upload
from plumbline.ingest.processed import local_cache
from plumbline.leases.checker import LeaseCheck, check_lease
from plumbline.leases.scoring import LeaseScore, Pooled, pooled, score_lease
from plumbline.retrieval.embed import TeiEmbedder
from plumbline.retrieval.retriever import Retriever
from plumbline.settings import ROOT, get_settings

LEASES: Final = ROOT / "data" / "leases"
CONFIGS: Final = ROOT / "evals" / "configs"
FETCH_ONLY: Final = frozenset({Jurisdiction.DUBAI, Jurisdiction.COLOMBIA})


@dataclass(frozen=True)
class Evaluation:
    scores: list[LeaseScore]
    pooled: dict[str, Pooled]
    invalid_citations: int
    cost_usd: float


async def evaluate(
    leases: Sequence[ExpectedLease], check: Callable[[ExpectedLease], Awaitable[LeaseCheck]]
) -> Evaluation:
    """Check every lease, one after another (each check runs its clauses in parallel)."""
    checks = [await check(lease) for lease in leases]
    scores = [score_lease(lease, c.findings) for lease, c in zip(leases, checks, strict=True)]
    return Evaluation(
        scores=scores,
        pooled=pooled(scores),
        invalid_citations=sum(c.invalid_citations for c in checks),
        cost_usd=sum(c.cost_usd for c in checks),
    )


def report(evaluation: Evaluation) -> str:
    """A Markdown table: one row per lease, then the pooled rates with 95% intervals."""
    lines = [
        "| Lease | Caught | On the clause | True flags | Lookalikes flagged | Precision | Recall |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {s.lease_id} | {s.caught}/{s.planted} | {s.on_clause}/{s.planted} "
        f"| {s.true_flags}/{s.flags} "
        f"| {s.lawful_flagged}/{s.lawful} | {_share(s.precision)} | {_share(s.recall)} |"
        for s in evaluation.scores
    )
    rates = evaluation.pooled
    on_clause = sum(s.on_clause for s in evaluation.scores)
    planted = sum(s.planted for s in evaluation.scores)
    lines.append(
        f"| all | {_rate(rates['recall'])} | {on_clause}/{planted} | {_rate(rates['precision'])} "
        f"| {_rate(rates['lookalikes_flagged'])} | | |"
    )
    return "\n".join(lines)


def _share(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _rate(rate: Pooled) -> str:
    return f"{rate.hits}/{rate.total} = {_share(rate.value)} [{rate.low:.2f}, {rate.high:.2f}]"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m plumbline.leases.evaluate")
    parser.add_argument("--config", default="A2-claude", help="whose search the checker uses")
    parser.add_argument("--model", default=PREMIUM_MODEL, help="the model that checks")
    parser.add_argument("--lease", action="append", default=[], metavar="ID", help="only these")
    parser.add_argument("--out", type=Path, help="write the scores as JSON")
    args = parser.parse_args(argv)
    settings = get_settings()
    config = load_config(CONFIGS / f"{args.config}.yaml")
    leases = [x for x in load_expected().leases if not args.lease or x.lease_id in args.lease]
    caches = {
        False: get_cache(settings.cache_mode, settings.cache_dir),
        True: get_cache(settings.cache_mode, local_cache()),
    }
    sessions = make_sync_sessionmaker(make_sync_engine(settings.database_url))
    model = config.retrieval.embedding_model
    searches = {
        restricted: Retriever(config, sessions, TeiEmbedder(settings.embed_url, cache, model=model))
        for restricted, cache in caches.items()
    }

    async def check(lease: ExpectedLease) -> LeaseCheck:
        restricted = lease.jurisdiction in FETCH_ONLY
        text = (LEASES / f"{lease.lease_id}.md").read_text(encoding="utf-8")
        return await check_lease(
            Upload(text=text, language=Language.EN, synthetic=True),
            redactor=SyntheticOnlyRedactor(),
            search=searches[restricted],
            client=client_for(args.model, cache=caches[restricted]),
            jurisdiction=lease.jurisdiction,
            as_of=lease.signed_on,
            model=args.model,
        )

    evaluation = asyncio.run(evaluate(leases, check))
    print(report(evaluation))
    print(
        f"{len(leases)} leases on {args.config} with {args.model}: "
        f"{evaluation.invalid_citations} invalid citations, US${evaluation.cost_usd:.4f}",
        file=sys.stderr,
    )
    if args.out:
        body = {
            "config": args.config,
            "model": args.model,
            "leases": [asdict(s) for s in evaluation.scores],
            "pooled": {name: asdict(rate) for name, rate in evaluation.pooled.items()},
            "invalid_citations": evaluation.invalid_citations,
            "cost_usd": round(evaluation.cost_usd, 4),
        }
        args.out.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
