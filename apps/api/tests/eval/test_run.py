"""End to end: the runner's command line over a fixture golden file, with a fake retriever
and the seed's stub pipeline standing in for the system."""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from plumbline.core.config import EvalConfig, load_config
from plumbline.eval.run import Streamed, known_test_ids, main
from plumbline.generation.stub import StubPipeline
from plumbline.settings import ROOT
from rag_eval.schema import EvalRun, Jurisdiction, RetrievedRef, file_sha256

GOLDEN = Path(__file__).parent / "fixtures" / "golden_fixture.jsonl"
DEPOSIT = "florida:fl-stat-83:83.49"
REPAIRS = "florida:fl-stat-83:83.60"
# What the fake retriever returns per question, by a word in it.
RANKINGS = {"Florida": [REPAIRS, DEPOSIT], "Spanish": [], "abstain": [REPAIRS]}


class FakeRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[int, Sequence[Jurisdiction] | None, date | None]] = []

    def retrieve(
        self,
        question: str,
        *,
        k: int,
        jurisdictions: Sequence[Jurisdiction] | None = None,
        as_of: date | None = None,
    ) -> list[RetrievedRef]:
        self.calls.append((k, jurisdictions, as_of))
        keys = next((keys for word, keys in RANKINGS.items() if word in question), [])
        return [RetrievedRef(key=key, score=1 / n) for n, key in enumerate(keys, start=1)]


def stub(config: EvalConfig) -> Streamed:
    return Streamed(StubPipeline(delay_ms=0))


def run(
    tmp_path: Path,
    *args: str,
    retriever: FakeRetriever | None = None,
    golden: Path = GOLDEN,
) -> int:
    fake = retriever or FakeRetriever()
    argv = ["--golden", str(golden), "--results-dir", str(tmp_path), *args]
    # An empty golden folder: the repository's own drafts put other items in test.
    empty = tmp_path / "golden"
    empty.mkdir(exist_ok=True)
    return main(
        argv, retriever_factory=lambda config: fake, pipeline_factory=stub, golden_dir=empty
    )


def read(tmp_path: Path, config: str, split: str) -> EvalRun:
    return EvalRun.model_validate_json((tmp_path / config / f"{split}.json").read_text())


def test_a_retrieval_only_run_writes_a_stamped_results_file(tmp_path: Path) -> None:
    fake = FakeRetriever()
    assert (
        run(tmp_path, "--config", "A2", "--split", "dev", "--retrieval-only", retriever=fake) == 0
    )
    result = read(tmp_path, "A2", "dev-retrieval")
    assert result.config_hash == load_config(ROOT / "evals/configs/A2.yaml").config_hash()
    assert result.golden_sha256 == file_sha256(GOLDEN)
    assert result.golden_file == "apps/api/tests/eval/fixtures/golden_fixture.jsonl"
    assert result.n_items == 3  # the test item stays untouched
    assert result.judged is False
    assert result.notes == "retrieval only"
    # Depth 20, no jurisdictions handed over, and the item's as-of date passed through.
    assert fake.calls == [(20, None, None), (20, None, date(2024, 3, 1)), (20, None, None)]
    # Recall@5 is 1 then 0 on the two answerable items; the out-of-scope one has no gold.
    assert result.summary["recall@5"] == 0.5
    assert result.summary["recall@5.n"] == 2.0
    assert result.summary["mrr"] == 0.25
    assert result.summary["jurisdiction@5"] == 0.5  # 1.0 for Florida, 0.0 for Dubai
    assert result.results[0].metrics["abstention_accuracy"] is None


def test_a_full_run_scores_the_answer_and_never_searches_on_its_own(tmp_path: Path) -> None:
    fake = FakeRetriever()
    assert run(tmp_path, "--config", "A2", "--split", "dev", retriever=fake) == 0
    assert fake.calls == []  # the retrieval scored is the one the answer was written from
    by_id = {r.item_id: r for r in read(tmp_path, "A2", "dev").results}
    # The stub abstains on questions containing "abstain" and cites its invented Stub Act.
    assert by_id["du-0001"].metrics["abstention_accuracy"] == 1.0
    assert by_id["fl-0001"].metrics["false_abstention"] == 0.0
    assert by_id["fl-0001"].cited == ["florida:stub-act:1"]
    assert by_id["fl-0001"].metrics["citation_validity"] == 1.0
    assert by_id["fl-0001"].metrics["citation_precision"] == 0.0
    assert by_id["fl-0001"].trace_id == "eval-fl-0001"


def test_the_long_context_baseline_has_no_retrieval_metrics(tmp_path: Path) -> None:
    fake = FakeRetriever()
    assert run(tmp_path, "--config", "LC", "--split", "dev", retriever=fake) == 0
    summary = read(tmp_path, "LC", "dev").summary
    assert summary["recall@5"] is None
    assert summary["recall@5.n"] == 0.0
    assert summary["abstention_accuracy"] == 1.0
    assert fake.calls == []
    assert run(tmp_path, "--config", "LC", "--split", "dev", "--retrieval-only") == 2


def test_the_test_split_is_refused_without_the_final_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeRetriever()
    assert (
        run(tmp_path, "--config", "A2", "--split", "test", "--retrieval-only", retriever=fake) == 2
    )
    assert "once, in Phase 13" in capsys.readouterr().err
    assert fake.calls == []
    assert not (tmp_path / "A2").exists()  # no results file written


def test_the_final_test_run_happens_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ("--config", "A2", "--split", "test", "--final-test-run", "--retrieval-only")
    assert run(tmp_path, *args) == 0
    assert read(tmp_path, "A2", "test-retrieval").n_items == 1
    assert run(tmp_path, *args) == 2
    assert run(tmp_path, *[a for a in args if a != "--retrieval-only"]) == 2
    assert "runs once per configuration" in capsys.readouterr().err


def test_an_unknown_configuration_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tmp_path, "--config", "Z9", "--split", "dev") == 2
    assert "no configuration Z9" in capsys.readouterr().err


def test_without_a_retriever_the_run_says_what_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--golden", str(GOLDEN), "--results-dir", str(tmp_path), "--config", "A2"]
    assert main([*argv, "--retrieval-only"], golden_dir=tmp_path) == 2
    assert "lands in A5" in capsys.readouterr().err


def test_a_lease_signing_date_is_the_day_the_law_is_read(tmp_path: Path) -> None:
    signed = tmp_path / "signed.jsonl"
    lines = GOLDEN.read_text().splitlines()
    signed.write_text(
        lines[0].replace('"split": "dev"', '"split": "dev", "signed_on": "2026-02-01"') + "\n"
    )
    fake = FakeRetriever()
    assert (
        run(
            tmp_path,
            "--config",
            "A2",
            "--split",
            "dev",
            "--retrieval-only",
            retriever=fake,
            golden=signed,
        )
        == 0
    )
    assert fake.calls == [(20, None, date(2026, 2, 1))]


def test_an_item_the_drafts_put_in_test_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "golden"
    folder.mkdir()
    test_item = GOLDEN.read_text().splitlines()[0].replace('"split": "dev"', '"split": "test"')
    (folder / "golden_v9.jsonl").write_text(test_item + "\n")
    argv = ["--golden", str(GOLDEN), "--results-dir", str(tmp_path), "--config", "A2"]
    fake = FakeRetriever()
    assert (
        main([*argv, "--retrieval-only"], retriever_factory=lambda c: fake, golden_dir=folder) == 2
    )
    assert fake.calls == []


def test_only_the_newest_draft_marks_test_items(tmp_path: Path) -> None:
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    dev = GOLDEN.read_text().splitlines()[0]
    test = dev.replace('"split": "dev"', '"split": "test"')
    (drafts / "golden_v0.jsonl").write_text(test + "\n")
    assert known_test_ids(tmp_path) == {"fl-0001"}  # the only draft, so the newest
    (drafts / "golden_v1.jsonl").write_text(dev + "\n")
    assert known_test_ids(tmp_path) == set()  # v0 is superseded by v1, which has no test item
    (tmp_path / "golden_v0.jsonl").write_text(test + "\n")
    assert known_test_ids(tmp_path) == {"fl-0001"}  # a frozen file always counts
