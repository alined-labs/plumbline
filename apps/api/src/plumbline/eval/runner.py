"""Scoring one configuration on the golden set: pure functions, no I/O.

`run.py` reads the configuration and the golden file, calls the retriever and the answer
pipeline, and writes the results file. This module decides which items a run may touch,
folds an answer's stream into an `EvalResult`, and builds the stamped `EvalRun` with the
metrics of `rag_eval.metrics`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Final, Literal

from plumbline.core.config import EvalConfig
from plumbline.core.types import Answer, AnswerTrace, Retrieved
from rag_eval.metrics import JURISDICTION, MRR, NDCG_10, RECALL_5, RECALL_20, score, summarize
from rag_eval.schema import Category, EvalResult, EvalRun, GoldenItem, RetrievedRef, Split

SplitName = Literal["dev", "test", "all"]

# How many articles a run asks the retriever for: recall@20 is the deepest metric.
DEPTH: Final = 20
RETRIEVAL_METRICS: Final = (RECALL_5, RECALL_20, MRR, NDCG_10, JURISDICTION)


class RunError(ValueError):
    """A run that must not start or cannot finish; the message says why."""


def select_items(
    items: Sequence[GoldenItem],
    split: SplitName,
    *,
    final_test_run: bool,
    test_ids: Collection[str] = (),
) -> list[GoldenItem]:
    """The items a run on `split` evaluates, in file order.

    The test split is scored once, in Phase 13, so it is reachable only through
    ``--split test --final-test-run``: "all" exists for golden files that have no split
    yet (v0), and is refused as soon as a file has test items. An older file may hold
    items that a newer one puts in test (v0's 60 items are in v1, a third of them in its
    test split), so `test_ids`, every id that any golden file or the seeded split of a
    draft puts in test, is refused outside the final run whatever the chosen file says.

    Lease-check items are scored by the lease checker against their leases' expected
    findings, in a table of their own, never as questions.
    """
    if final_test_run and split != "test":
        raise RunError("--final-test-run applies only to --split test")
    if split == "test" and not final_test_run:
        raise RunError("the test split runs once, in Phase 13, with --final-test-run")
    if split == "all" and any(item.split is Split.TEST for item in items):
        raise RunError("this golden file has a test split: run --split dev")
    chosen = list(items) if split == "all" else [i for i in items if i.split.value == split]
    chosen = [i for i in chosen if i.category is not Category.LEASE_CHECK]
    if not chosen:
        present = dict(Counter(item.split.value for item in items))
        raise RunError(f"no question items in split {split!r}; the file has {present}")
    if not final_test_run and (leaked := sorted(i.id for i in chosen if i.id in test_ids)):
        raise RunError(
            f"{len(leaked)} of these items are test items elsewhere (first {leaked[0]}):"
            " the test split runs once, with --final-test-run"
        )
    return chosen


def article_refs(retrieved: Sequence[Retrieved]) -> list[RetrievedRef]:
    """What the answer was given, as articles in rank order, each once at its best place."""
    refs: dict[str, RetrievedRef] = {}
    for hit in retrieved:
        key = hit.chunk.ref.key
        refs.setdefault(key, RetrievedRef(key=key, score=hit.score, chunk_id=hit.chunk.id))
    return list(refs.values())


def answer_result(
    item_id: str, answer: Answer, trace: AnswerTrace, latency_ms: float
) -> EvalResult:
    """One answer, with the retrieval it was written from: its retrieval metrics describe
    the passages the generator read (the configuration's top_k, after any reranking),
    not a separate search. Only verified citations count as cited; the rest arrive as
    invalid_citations, the answer's own count."""
    return EvalResult(
        item_id=item_id,
        retrieved=article_refs(trace.retrieved),
        status=answer.status,
        answer=answer.text.strip(),
        cited=[c.ref.key for c in answer.citations if c.verified],
        invalid_citations=answer.invalid_citations,
        latency_ms=latency_ms,
        cost_usd=trace.cost_usd,
        trace_id=trace.request_id,
    )


def build_run(
    *,
    config: EvalConfig,
    split: SplitName,
    items: Sequence[GoldenItem],
    results: Sequence[EvalResult],
    golden_file: str,
    golden_sha256: str,
    git_sha: str,
    created_at: datetime,
    retrieval_only: bool,
) -> EvalRun:
    """Score every result against its item and stamp the run so it can be rebuilt."""
    if [r.item_id for r in results] != [item.id for item in items]:
        raise RunError("results must cover the selected items, once each, in order")
    scored = [score(item, result) for item, result in zip(items, results, strict=True)]
    if config.retrieval.mode == "none":
        # The long-context baseline retrieves nothing: its retrieval metrics do not
        # apply, and an empty list would otherwise score as a miss on every item.
        blank = dict.fromkeys(RETRIEVAL_METRICS)
        scored = [r.model_copy(update={"metrics": r.metrics | blank}) for r in scored]
    return EvalRun(
        run_id=f"{config.name}-{split}-{created_at:%Y%m%dt%H%M%Sz}".lower(),
        config_name=config.name,
        config_hash=config.config_hash(),
        git_sha=git_sha,
        golden_file=golden_file,
        golden_sha256=golden_sha256,
        split=split,
        created_at=created_at,
        judged=False,  # the calibrated judge (C8) joins the runner in A9
        n_items=len(scored),
        results=scored,
        summary=summarize(scored),
        notes="retrieval only" if retrieval_only else None,
    )
