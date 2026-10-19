"""Run one configuration over one split of the golden set.

    python -m plumbline.eval.run --config A2 --split dev [--retrieval-only]

Writes the stamped `EvalRun` to evals/results/<config>/<split>.json, or to
<split>-retrieval.json for a retrieval-only run. This module does the I/O (files, git, the
retriever, the answer pipeline); `runner.py` decides and scores.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from plumbline.core.config import EvalConfig, load_config
from plumbline.core.stream import (
    AnswerPipeline,
    AnswerSummary,
    Question,
    StreamError,
    TextDelta,
    TraceSummary,
)
from plumbline.core.types import Answer, AnswerTrace, Citation
from plumbline.corpus.split import assign_splits
from plumbline.eval.runner import DEPTH, RunError, answer_result, build_run, select_items
from plumbline.generation.pipeline import PipelineError
from plumbline.settings import ROOT
from rag_eval.schema import EvalResult, GoldenItem, Retriever, Split, file_sha256, load_golden

RetrieverFactory = Callable[[EvalConfig], Retriever]
PipelineFactory = Callable[[EvalConfig], "EvalPipeline"]
CONFIGS = ROOT / "evals" / "configs"
GOLDEN = ROOT / "data" / "golden"


class EvalPipeline(Protocol):
    """What a full run needs: the whole answer and its trace, with the passages the
    generator read (generation.pipeline.Pipeline.answer)."""

    async def answer(self, question: Question) -> tuple[Answer, AnswerTrace]: ...


@dataclass
class Streamed:
    """EvalPipeline over a bare event stream (the seed's stub): its answer, and a trace
    with no retrieved passages, since a stream does not carry them."""

    pipeline: AnswerPipeline

    async def answer(self, question: Question) -> tuple[Answer, AnswerTrace]:
        text: list[str] = []
        citations: list[Citation] = []
        summary: AnswerSummary | None = None
        trace: TraceSummary | None = None
        async for event in self.pipeline.stream(question):
            match event:
                case StreamError():
                    raise RunError(f"the pipeline failed: {event.message}")
                case TextDelta():
                    text.append(event.text)
                case Citation():
                    citations.append(event)
                case AnswerSummary():
                    summary = event
                case TraceSummary():
                    trace = event
        if summary is None or trace is None:
            raise RunError("the stream ended without its answer summary and trace")
        answer = Answer(
            text="".join(text),
            status=summary.status,
            citations=citations,
            invalid_citations=summary.invalid_citations,
        )
        return answer, AnswerTrace(**trace.model_dump())


def no_retriever(config: EvalConfig) -> Retriever:
    raise RunError(f"{config.name}: no retriever is wired yet (hybrid retrieval lands in A5)")


def no_pipeline(config: EvalConfig) -> EvalPipeline:
    raise RunError(f"{config.name}: no answer pipeline is wired; run with --retrieval-only")


def as_of(item: GoldenItem) -> date | None:
    """The day the law is read on: the question's date, or a lease's signing date."""
    return item.as_of or item.signed_on


def known_test_ids(golden: Path = GOLDEN) -> set[str]:
    """Every id that a frozen golden file puts in test, and those the newest draft will put
    there when it is frozen (a third, plumbline.corpus.split's seeded split). Only the
    newest draft counts: an older one (v0) was folded into it, and its own seeded split,
    over fewer items, would mark other ids."""
    ids: set[str] = set()
    frozen = {_version(p): p for p in golden.glob("golden_v*.jsonl")}
    for path in frozen.values():
        ids |= {i.id for i in load_golden(path) if i.split is Split.TEST}
    drafts = {_version(p): p for p in (golden / "drafts").glob("golden_v*.jsonl")}
    if drafts and (newest := max(drafts)) not in frozen:
        items = load_golden(drafts[newest])
        if all(i.split is Split.UNASSIGNED for i in items):
            items = assign_splits(items, len(items) // 3)
        ids |= {i.id for i in items if i.split is Split.TEST}
    return ids


def _version(path: Path) -> int:
    found = re.fullmatch(r"golden_v(\d+)\.jsonl", path.name)
    if found is None:
        raise RunError(f"not a golden file name: {path.name}")
    return int(found[1])


def latest_golden(directory: Path) -> Path:
    """The highest-numbered frozen golden file, golden_v<N>.jsonl."""
    versions = {
        int(match[1]): path
        for path in directory.glob("golden_v*.jsonl")
        if (match := re.fullmatch(r"golden_v(\d+)\.jsonl", path.name))
    }
    if not versions:
        raise RunError(f"no frozen golden file in {directory}; pass --golden")
    return versions[max(versions)]


def git_sha() -> str:
    """HEAD, with -dirty when anything but results files is uncommitted: a run writes
    results, so they never count, while code, configurations and recordings do."""

    def git(*args: str) -> str:
        return subprocess.run(  # noqa: S603 - fixed git subcommands, no user input
            ["git", *args],  # noqa: S607 - git from PATH
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    dirty = git("status", "--porcelain", "--", ".", ":(exclude)evals/results")
    return git("rev-parse", "HEAD") + ("-dirty" if dirty else "")


async def evaluate(
    items: Sequence[GoldenItem], retriever: Retriever | None, pipeline: EvalPipeline | None
) -> list[EvalResult]:
    """For every item, one at a time: a full run scores the answer and the passages its
    generator read; a retrieval-only run scores a search at depth 20. The item's
    jurisdictions are labels, never inputs: the system detects them, so a detection error
    lowers the metrics instead of being handed the answer."""
    results: list[EvalResult] = []
    for item in items:
        started = time.perf_counter()
        if pipeline is None:
            refs = (
                retriever.retrieve(item.question, k=DEPTH, as_of=as_of(item)) if retriever else []
            )
            elapsed = (time.perf_counter() - started) * 1000
            results.append(EvalResult(item_id=item.id, retrieved=refs, latency_ms=elapsed))
            continue
        question = Question(text=item.question, as_of=as_of(item), request_id=f"eval-{item.id}")
        try:
            answer, trace = await pipeline.answer(question)
        except (RunError, PipelineError) as exc:
            raise RunError(f"{item.id}: {exc}") from exc
        elapsed = (time.perf_counter() - started) * 1000
        results.append(answer_result(item.id, answer, trace, elapsed))
    return results


def _relative(path: Path) -> str:
    resolved = path.resolve()
    return (resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved).as_posix()


def main(
    argv: Sequence[str] | None = None,
    *,
    retriever_factory: RetrieverFactory = no_retriever,
    pipeline_factory: PipelineFactory = no_pipeline,
    golden_dir: Path = GOLDEN,
) -> int:
    parser = argparse.ArgumentParser(prog="plumbline.eval.run", description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, help="a configuration name, such as A2")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--retrieval-only", action="store_true", help="skip generation")
    parser.add_argument("--final-test-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--golden", type=Path, help="default: the newest data/golden/golden_v<N>.jsonl"
    )
    parser.add_argument("--results-dir", type=Path, default=ROOT / "evals" / "results")
    args = parser.parse_args(argv)
    try:
        config_path = CONFIGS / f"{args.config}.yaml"
        if not config_path.is_file():
            raise RunError(f"no configuration {args.config} in {_relative(CONFIGS)}")
        config = load_config(config_path)
        golden = args.golden or latest_golden(golden_dir)
        # Stamped before the run: the golden file as it was read, and the commit as it was
        # before a recording run adds files to the tree.
        golden_sha256, commit = file_sha256(golden), git_sha()
        items = select_items(
            load_golden(golden),
            args.split,
            final_test_run=args.final_test_run,
            test_ids=known_test_ids(golden_dir),
        )
        folder = args.results_dir / config.name
        out = folder / f"{args.split}{'-retrieval' if args.retrieval_only else ''}.json"
        if args.final_test_run and list(folder.glob("test*.json")):
            raise RunError(f"{config.name} already ran on test: it runs once per configuration")
        no_retrieval = config.retrieval.mode == "none"
        if no_retrieval and args.retrieval_only:
            raise RunError(f"{config.name} retrieves nothing: run it without --retrieval-only")
        retriever = None if no_retrieval or not args.retrieval_only else retriever_factory(config)
        pipeline = None if args.retrieval_only else pipeline_factory(config)
        results = asyncio.run(evaluate(items, retriever, pipeline))
        if file_sha256(golden) != golden_sha256:
            raise RunError(f"{_relative(golden)} changed during the run")
    except RunError as exc:
        print(f"plumbline.eval.run: {exc}", file=sys.stderr)
        return 2
    run = build_run(
        config=config,
        split=args.split,
        items=items,
        results=results,
        golden_file=_relative(golden),
        golden_sha256=golden_sha256,
        git_sha=commit,
        created_at=datetime.now(UTC),
        retrieval_only=args.retrieval_only,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"{_relative(out)}: {config.name} on {args.split}, {run.n_items} items, {run.git_sha}")
    # Summary keys are a metric's name, or the name plus .low, .high or .n.
    for name in (key for key, mean in run.summary.items() if "." not in key and mean is not None):
        low, high, n = (run.summary[f"{name}.{part}"] for part in ("low", "high", "n"))
        print(f"  {name:20} {run.summary[name]:.3f}  [{low:.3f}, {high:.3f}]  n={n:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
