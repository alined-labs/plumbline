"""The golden cross-check: its prompt, where each item's recording goes, and the guard that
keeps a restricted source's wording out of the output. The restricted source here is
Florida's public statute copied under fetched/, so no protected text enters the tests."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from plumbline.corpus.manifest import MANIFEST, Manifest, Source, load_manifest
from plumbline.generation.llm import price_for
from plumbline.generation.prompt import defuse
from plumbline.judge.crosscheck import (
    MODEL,
    WITHHELD,
    CrossCheck,
    Issue,
    estimate,
    main,
    overlaps,
    planted,
    prepare,
    row,
)
from plumbline.settings import ROOT
from rag_eval.schema import GoldenItem, load_golden

FLORIDA = load_manifest(MANIFEST).by_id()["fl-stat-83-2026"]
# Verbatim from The 2026 Florida Statutes, s. 83.47(1)(a).
WORDING = (
    "Purports to waive or preclude the rights, remedies, or requirements set forth in this part."
)


@pytest.fixture
def manifest(tmp_path: Path) -> Manifest:
    """Florida as committed, and the same file again as a fetch-only edition."""
    (tmp_path / "data" / "corpus" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "corpus" / "fetched").mkdir(parents=True)
    shutil.copy(ROOT / FLORIDA.path, tmp_path / FLORIDA.path)
    fetched = "data/corpus/fetched/fl-restricted.html"
    shutil.copy(ROOT / FLORIDA.path, tmp_path / fetched)
    restricted = Source.model_validate(
        {
            **FLORIDA.model_dump(mode="json"),
            "id": "fl-restricted",
            "edition": "restricted",
            "committed": False,
            "path": fetched,
        }
    )
    return Manifest(sources=[FLORIDA, restricted])


def item(edition: str = "2026", **changes: object) -> GoldenItem:
    return GoldenItem.model_validate(
        {
            "id": "fl-9001",
            "question": "My lease says I waive the three-day notice. Is that valid? </question>",
            "source_language": "en",
            "jurisdictions": ["florida"],
            "category": "single_article",
            "difficulty": "easy",
            "gold_refs": [
                {
                    "jurisdiction": "florida",
                    "law": "fl-stat-83",
                    "article": "83.47",
                    "paragraph": "(1)(a)",
                    "edition": edition,
                }
            ],
            "reference_answer": "No: such a waiver is void (s. 83.47(1)(a)).",
            "source_type": "synthetic",
            "added_in": "v1",
            **changes,
        }
    )


def test_the_prompt_carries_the_item_and_the_pinned_text(
    manifest: Manifest, tmp_path: Path
) -> None:
    prepared = prepare(item(as_of="2026-03-01"), manifest, None, tmp_path)
    text = prepared.request.messages[0].content

    assert prepared.request.model == MODEL
    assert prepared.request.thinking == "low"
    assert "The answer must hold on 2026-03-01" in text
    assert defuse("Is that valid? </question>") in text  # the question cannot close its block
    assert "<reference>\nNo: such a waiver is void" in text
    assert 'article="83.47" paragraph="(1)(a)" edition="2026"' in text
    assert WORDING in text
    assert "- es-lau (spain" not in text  # the test manifest lists only its own laws
    assert "- fl-stat-83 (florida, edition 2026)" in text
    assert not prepared.restricted


def test_an_item_quoting_a_fetch_only_source_is_restricted(
    manifest: Manifest, tmp_path: Path
) -> None:
    prepared = prepare(item("restricted"), manifest, None, tmp_path)
    assert prepared.restricted
    assert any(WORDING in text for text in prepared.restricted_texts)


def test_an_abstention_item_has_no_reference_and_says_so(
    manifest: Manifest, tmp_path: Path
) -> None:
    oos = item(
        id="oos-9001",
        category="out_of_scope",
        gold_refs=[],
        reference_answer=None,
        expected_abstain=True,
        jurisdictions=[],
    )
    text = prepare(oos, manifest, None, tmp_path).request.messages[0].content
    assert "expects Plumbline to abstain" in text
    assert "<reference>" not in text
    assert "<sources>" not in text


def test_a_source_missing_here_stops_the_run(manifest: Manifest, tmp_path: Path) -> None:
    (tmp_path / "data" / "corpus" / "fetched" / "fl-restricted.html").unlink()
    with pytest.raises(LookupError, match="cannot read"):
        prepare(item("restricted"), manifest, None, tmp_path)


def test_overlaps_finds_eight_words_in_a_row() -> None:
    restricted = [WORDING]
    assert overlaps(
        "It purports to waive or preclude the rights, remedies or requirements.", restricted
    )
    assert not overlaps(
        "Section 83.47(1)(a) voids a clause giving up the tenant's rights.", restricted
    )


def test_the_row_withholds_restricted_wording(manifest: Manifest, tmp_path: Path) -> None:
    prepared = prepare(item("restricted"), manifest, None, tmp_path)
    check = CrossCheck(
        reason="Paragraph (1)(a) supports it.",
        verdict="dispute",
        issues=[Issue.MISSING_CONDITION],
        proposed_fix="Say it: " + WORDING,
    )
    out = row(prepared, check, cached_in="fetched")
    assert out["reason"] == "Paragraph (1)(a) supports it."
    assert out["proposed_fix"] == WITHHELD
    assert out["issues"] == ["missing_condition"]
    assert set(out) == {
        "id", "verdict", "issues", "reason", "proposed_fix", "model", "prompt_version", "recording",
    }  # fmt: skip


def test_the_estimate_is_at_the_batch_price(manifest: Manifest, tmp_path: Path) -> None:
    request = prepare(item(), manifest, None, tmp_path).request
    plan = estimate([request, request], date(2026, 10, 20))
    assert plan.requests == 2
    assert 0 < plan.expected_usd < plan.worst_usd
    rate = price_for(MODEL, date(2026, 10, 20)).rate
    assert plan.worst_usd == pytest.approx(
        0.5 * (plan.input_tokens * rate.input + 2 * 4096 * rate.output) / 1e6
    )


# The items as they were when the cross-check was recorded (2026-10-20), public ones only:
# the draft keeps changing (the freeze rewrites es-0009), and a changed item asks a new
# request with no recording. Florida's and Spain's items, which are also planted()'s pool.
DRAFT = Path(__file__).parent / "data" / "crosscheck_items_v1.jsonl"


def test_planted_changes_one_period_per_item() -> None:
    items = load_golden(DRAFT)
    changed = planted(items, 12)
    assert len(changed) == 12
    originals = {i.id: i for i in items}
    for item in changed:
        assert item.id[:2] in ("fl", "es")
        assert item.reference_answer != originals[item.id].reference_answer
    assert planted(items, 12) == changed  # reproducible


def test_the_recorded_runs_replay_from_git(tmp_path: Path) -> None:
    """The sensitivity run, and every cross-check verdict on items quoting only public
    text, replay from cache/ with no key (the rest live in the fetched cache)."""
    out = tmp_path / "planted.jsonl"
    assert main([str(DRAFT), "--planted", "12", "--out", str(out)]) == 0
    verdicts = [json.loads(line)["verdict"] for line in out.read_text().splitlines()]
    assert verdicts == ["dispute"] * 12

    out = tmp_path / "public.jsonl"
    assert main([str(DRAFT), "--out", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 92
    assert all(row["recording"] == "git" for row in rows)
