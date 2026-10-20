"""The as-of cases hold against the pinned BOE files: on each date, the version named is the one
in force, its wording is there, and the wording of the versions around it is not."""

from __future__ import annotations

import json
from datetime import date
from xml.etree import ElementTree

import pytest
from pydantic import BaseModel, ConfigDict

from plumbline.corpus.manifest import load_manifest
from plumbline.corpus.refs import LPH_ORDINALS, article_text
from plumbline.settings import ROOT

CASES = ROOT / "data" / "golden" / "asof_cases.json"
SOURCES = {(s.law, s.edition): s for s in load_manifest().sources}


class AsOfCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    law: str
    edition: str
    article: str
    as_of: date
    version: str | None  # the BOE norm whose wording is in force; None: no article that day
    effective_from: date | None
    present: str | None
    absent: list[str]
    why: str


def load() -> list[AsOfCase]:
    return [AsOfCase.model_validate(row) for row in json.loads(CASES.read_text(encoding="utf-8"))]


def test_ids_are_unique_and_every_case_says_why() -> None:
    cases = load()
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.why for case in cases)


@pytest.mark.parametrize("case", load(), ids=lambda case: case.id)
def test_the_case_holds_against_the_pinned_text(case: AsOfCase) -> None:
    text = article_text(SOURCES[(case.law, case.edition)], case.article, case.as_of)
    if case.version is None:
        assert text is None
        return
    assert text is not None
    assert case.effective_from is not None
    assert case.effective_from <= case.as_of
    since = case.effective_from.strftime("%Y%m%d")
    assert text.splitlines()[0] == f"[{case.version}, in force from {since}]"
    assert case.present is not None
    assert case.present in text
    for wording in case.absent:
        assert wording not in text


def block_text(case: AsOfCase) -> str:
    """Everything the BOE file holds for the article: every version and every note."""
    source = SOURCES[(case.law, case.edition)]
    name = LPH_ORDINALS[int(case.article) - 1] if case.law == "es-lph" else case.article
    root = ElementTree.fromstring((ROOT / source.path).read_bytes())  # noqa: S314 (pinned file)
    for block in root.iter("bloque"):
        if block.get("titulo") == f"Artículo {name}":
            return " ".join("".join(block.itertext()).split())
    return ""


@pytest.mark.parametrize("case", load(), ids=lambda case: case.id)
def test_what_must_be_absent_is_in_the_file_on_another_date(case: AsOfCase) -> None:
    # A case whose absent wording is nowhere in the file would pass whatever a filter did.
    held = block_text(case)
    for wording in case.absent:
        assert wording in held
