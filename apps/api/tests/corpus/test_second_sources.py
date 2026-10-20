"""The list of second sources for the golden v1 drafts stays in step with the draft."""

from __future__ import annotations

import json
import re
from pathlib import Path

from plumbline.settings import ROOT
from rag_eval.schema import load_golden

DRAFTS = ROOT / "data" / "golden" / "drafts"
SOURCES = DRAFTS / "second_sources_v1.jsonl"
FIELDS = {"id", "second_source", "notes"}


def rows(path: Path) -> list[dict[str, str | None]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_every_draft_item_has_one_record_in_order() -> None:
    items = load_golden(DRAFTS / "golden_v1.jsonl")
    assert [row["id"] for row in rows(SOURCES)] == [item.id for item in items]


def test_each_record_names_a_source_with_its_address_or_says_why_not() -> None:
    items = {item.id: item for item in load_golden(DRAFTS / "golden_v1.jsonl")}
    for row in rows(SOURCES):
        assert set(row) == FIELDS, row["id"]
        notes, source = row["notes"], row["second_source"]
        assert notes, row["id"]
        assert notes.startswith("Second source, read on "), row["id"]
        if source is None:
            # Nothing is invented to fill the field: the notes say what was searched, or that
            # an out-of-scope item has nothing to compare.
            assert "official secondary source found" in notes.lower() or "Out of scope" in notes
        else:
            assert re.search(r"https://\S+", source), row["id"]
        if "Out of scope" in notes:
            assert items[str(row["id"])].expected_abstain, row["id"]
