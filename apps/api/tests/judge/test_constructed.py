"""Constructed labels: which items each kind is built from, what the writer is shown, the
labels each kind carries, and the agreement file /evals reads."""

import asyncio
import json
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import types as genai_types

from plumbline.cache import ResponseCache
from plumbline.core.types import CacheMode
from plumbline.corpus.manifest import MANIFEST, load_manifest
from plumbline.corpus.refs import article_text
from plumbline.generation.llm import GeminiClient, LLMRequest, LLMResult, Usage
from plumbline.judge.constructed import (
    COUNTS,
    LABELS,
    PUBLIC_LAWS,
    ConstructedRow,
    SourceRef,
    agreement_json,
    build,
    candidates,
    declined,
    read_rows,
    rows,
    score,
    score_batch,
    turned_quote,
    writer_request,
)
from plumbline.judge.judge import Judge
from rag_eval.schema import ArticleRef, GoldenItem

MANIFEST_ = load_manifest(MANIFEST)
State = genai_types.JobState
FLORIDA = ("83.47", "83.49", "83.56", "83.57", "83.60")


def item(n: int, place: str = "fl", **changes: object) -> GoldenItem:
    law, jurisdiction, edition = {
        "fl": ("fl-stat-83", "florida", "2026"),
        "du": ("dubai-law-26-2007", "dubai", "dlp-2024-12-20"),
    }[place]
    article = FLORIDA[n % len(FLORIDA)] if place == "fl" else str(5 + n % 3)
    body: dict[str, object] = {
        "id": f"{place}-{n:04d}",
        "question": f"Question number {n} about a lease?",
        "source_language": "en",
        "jurisdictions": [jurisdiction],
        "category": "single_article",
        "difficulty": "easy",
        "gold_refs": [
            {"jurisdiction": jurisdiction, "law": law, "article": article, "edition": edition}
        ],
        "reference_answer": f"Rule {n}: within 15 days, under article {article}.",
        "source_type": "synthetic",
        "split": "dev",
        "added_in": "v1",
    }
    return GoldenItem.model_validate(body | changes)


def out_of_scope(n: int) -> GoldenItem:
    return item(
        n,
        id=f"oos-{n:04d}",
        category="out_of_scope",
        gold_refs=[],
        reference_answer=None,
        expected_abstain=True,
        jurisdictions=[],
    )


@pytest.fixture(autouse=True)
def fetch_only_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dubai's law is fetch-only, so CI has no copy of it: these tests read a stand-in for
    every fetch-only article, on every machine alike, and the pinned text for the rest."""

    def read(source: Any, article: str, as_of: Any, root: Path) -> str | None:
        if source.law.startswith(PUBLIC_LAWS):
            return article_text(source, article, as_of, root)
        return f"Stand-in text of article {article}, long enough to be no stub. " * 3

    monkeypatch.setattr("plumbline.judge.constructed.article_text", read)


ITEMS = [item(n) for n in range(80)] + [item(n, "du") for n in range(30)]
ITEMS += [out_of_scope(n) for n in range(15)]


def test_each_kind_draws_from_items_it_can_be_built_on() -> None:
    pools = candidates(ITEMS)
    assert all(i.expected_abstain for i in pools["answered_out_of_scope"])
    assert all(i.gold_refs[0].law == "fl-stat-83" for i in pools["invented_quote"])
    assert all(i.id.startswith("fl-") for i in pools["unsupported_claim"])
    assert all(len(i.gold_refs) == 1 for i in pools["wrong_article"])
    assert candidates(ITEMS) == pools  # reproducible


def test_a_quote_is_turned_against_the_text() -> None:
    text = "(3) The landlord shall not enter the unit except with the tenant's consent."
    quote, turned = turned_quote(text) or ("", "")
    assert quote == "The landlord shall enter the unit except with the tenant's consent."
    assert turned == "'shall not' turned into 'shall'"
    assert turned_quote("Short. No modal verb appears anywhere in this sentence here.") is None


def test_declined_changes_are_recognised() -> None:
    assert declined("none: I did not add the invented sentence")
    assert declined("I declined the requested change")
    assert not declined("Changed the notice period from 90 to 60 days.")


def test_the_writer_never_sees_restricted_text() -> None:
    dubai = item(1, "du")
    for kind in ("correct", "wrong_number", "wrong_jurisdiction", "wrong_article"):
        text = writer_request(kind, dubai, MANIFEST_, "Spain").messages[0].content
        assert "<sources>" not in text
        assert "dubai-law-26-2007 article 6" in text  # the label only
    florida = item(1)
    text = writer_request("unsupported_claim", florida, MANIFEST_, "Spain").messages[0].content
    assert "<sources>" in text
    assert "83.49" in text
    assert "security deposit" in text.lower()
    assert (
        "as if the question had been asked about Spain"
        in writer_request("wrong_jurisdiction", florida, MANIFEST_, "Spain").messages[0].content
    )


class Writer:
    """Writes every row, but declines the planted error on every third item it is asked."""

    provider = "fake"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        change = "none: I declined" if self.calls % 3 == 0 else "one thing"
        reply = json.dumps({"answer": "An answer [1].", "change": change})
        return LLMResult(reply, request.model, Usage(), 0.0, 1, "end_turn", True, "k")

    async def stream(self, request: LLMRequest) -> AsyncIterator[str | LLMResult]:
        raise NotImplementedError
        yield


def test_build_labels_every_row_by_its_kind() -> None:
    built = asyncio.run(build(ITEMS, Writer(), MANIFEST_))
    assert [r.id for r in built] == [f"con-{n:03d}" for n in range(1, 101)]
    assert Counter(r.kind for r in built) == COUNTS
    assert len({r.item_id for r in built}) == 100
    planted = ("wrong_number", "wrong_jurisdiction", "unsupported_claim", "answered_out_of_scope")
    assert not any(r.change and declined(r.change) for r in built if r.kind in planted)
    for row in built:
        assert (row.faithfulness, row.correctness) == LABELS[row.kind]
        if row.kind == "wrong_article":
            chosen = next(i for i in ITEMS if i.id == row.item_id)
            assert row.sources[0].ref.article != chosen.gold_refs[0].article
            assert row.sources[0].ref.law == chosen.gold_refs[0].law
        if row.kind == "answered_out_of_scope":
            assert row.sources == []
            assert "abstain" in row.reference_answer
        assert (row.change is None) == (row.kind in ("correct", "wrong_article"))
        if row.kind == "invented_quote":
            assert ' says: "' in row.answer
            assert "turned into" in (row.change or "")


def test_rows_read_the_pinned_text_of_the_sources_named() -> None:
    ref = ArticleRef(jurisdiction="florida", law="fl-stat-83", article="83.49", edition="2026")
    row = ConstructedRow(
        id="con-001",
        item_id="fl-0001",
        kind="correct",
        question="When is my deposit returned?",
        answer="Within 15 days [1].",
        sources=[SourceRef(ref=ref)],
        reference_answer="Within 15 days.",
        faithfulness="pass",
        correctness="pass",
    )
    (sheet,) = rows([row], MANIFEST_)
    assert sheet.sources[0].startswith("[1] Florida Statutes 2026")
    assert "within 15 days after the termination" in sheet.sources[0]
    assert sheet.config == "constructed:correct"


class Verdicts:
    """A judge model that passes everything: TPR 1, TNR 0."""

    provider = "fake"

    async def complete(self, request: LLMRequest) -> LLMResult:
        reply = json.dumps({"reasoning": "fine", "verdict": "pass"})
        return LLMResult(reply, request.model, Usage(), 0.002, 1, "end_turn", False, "k")

    async def stream(self, request: LLMRequest) -> AsyncIterator[str | LLMResult]:
        raise NotImplementedError
        yield


def test_score_counts_each_criterion_on_its_labels_and_the_file_has_lane_es_shape() -> None:
    built = asyncio.run(build(ITEMS, Writer(), MANIFEST_))
    florida_only = [r for r in built if all(s.ref.law.startswith("fl-") for s in r.sources)]
    scored = asyncio.run(score(rows(florida_only, MANIFEST_), Judge(client=Verdicts())))
    faithfulness, correctness = scored.agreements
    assert faithfulness.tpr.value == 1.0
    assert faithfulness.tnr.value == 0.0
    labelled = [r for r in florida_only if r.correctness is not None]
    assert correctness.tpr.total + correctness.tnr.total == len(labelled)
    assert scored.cost_usd == pytest.approx(0.004 * len(florida_only))

    body = agreement_json(scored.agreements, "claude-haiku-5-5", scored.cost_usd)
    assert body["bar"] == 0.8
    (constructed,) = body["sets"]  # type: ignore[misc]
    assert constructed["labels"] == "constructed"
    first = constructed["criteria"][0]
    assert first["criterion"] == "faithfulness"
    assert set(first["tpr"]) == {"hits", "total", "low", "high"}


def test_the_committed_rows_replay_from_git_where_their_sources_are_public() -> None:
    """Every verdict behind the published table that may be committed is in cache/: the
    rows citing only Florida and Spain replay with no key (Dubai's and Colombia's
    faithfulness verdicts live in the fetched cache)."""
    constructed = read_rows()
    assert len(constructed) == 100
    public = [r for r in constructed if all(s.ref.law.startswith(PUBLIC_LAWS) for s in r.sources)]
    scored = asyncio.run(score(rows(public, MANIFEST_), Judge()))
    faithfulness, correctness = scored.agreements
    assert faithfulness.tpr.total + faithfulness.tnr.total == len(public)
    assert correctness.tpr.total > 0


class Jobs:
    """Gemini's job API for score_batch: every verdict a pass, every job done at once."""

    def __init__(self) -> None:
        self.sent: list[list[dict[str, Any]]] = []

    def create(self, *, model: str, src: list[dict[str, Any]], config: Any) -> Any:
        self.sent.append(src)
        return genai_types.BatchJob(name=f"batches/{len(self.sent)}", state=State.JOB_STATE_PENDING)

    def get(self, *, name: str) -> Any:
        verdict = json.dumps({"reasoning": "fine", "verdict": "pass"})
        responses = [
            genai_types.InlinedResponse(
                metadata=r["metadata"],
                response=genai_types.GenerateContentResponse(
                    candidates=[
                        genai_types.Candidate(
                            content=genai_types.Content(
                                role="model", parts=[genai_types.Part(text=verdict)]
                            )
                        )
                    ],
                    usage_metadata=genai_types.GenerateContentResponseUsageMetadata(
                        prompt_token_count=100, candidates_token_count=10
                    ),
                ),
            )
            for r in self.sent[int(name.split("/")[1]) - 1]
        ]
        return genai_types.BatchJob(
            name=name,
            state=State.JOB_STATE_SUCCEEDED,
            dest=genai_types.BatchJobDestination(inlined_responses=responses),
        )


def test_a_gemini_judge_scores_in_batches_with_restricted_faithfulness_kept_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = Jobs()
    monkeypatch.setattr(GeminiClient, "_client", lambda self: SimpleNamespace(batches=jobs))
    built = asyncio.run(build(ITEMS, Writer(), MANIFEST_))
    florida = [r for r in built if all(s.ref.law.startswith("fl-") for s in r.sources)][:6]
    sheet = rows(florida, MANIFEST_)
    restricted = frozenset({sheet[0].id})  # as if it quoted Dubai's text
    caches = {
        "git": ResponseCache(CacheMode.RECORD, tmp_path / "git"),
        "fetched": ResponseCache(CacheMode.RECORD, tmp_path / "fetched"),
    }
    scored = score_batch(sheet, "gemini-3.5-flash-lite", caches, restricted)

    assert [len(job) for job in jobs.sent] == [11, 1]  # git first, then the fetched job
    assert scored.verdicts == {row.id: {"faithfulness": True, "correctness": True} for row in sheet}
    faithfulness, _ = scored.agreements
    assert faithfulness.tpr.total + faithfulness.tnr.total == len(sheet)
    assert len(list((tmp_path / "fetched").glob("llm/*/*.json"))) == 1
    assert scored.cost_usd > 0
