"""The article chunker on every parse of the real corpus this machine has: the committed
parses of Florida and Spain, and the fetch-only Colombian and Dubai parses when `make
fetch` and `make ingest --parse-only` have built them locally (skipped otherwise). The
counts are the sources' own: Lane B counted the articles of each law by hand."""

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from plumbline.chunking.articles import parse_articles
from plumbline.chunking.chunker import chunk_document
from plumbline.core.config import ChunkerConfig
from plumbline.core.types import Chunk, ParsedDocument
from plumbline.ingest.laws import law_name
from plumbline.ingest.processed import FETCHED, PROCESSED, local_processed
from plumbline.settings import ROOT

# Words that only the notes use: the BOE's amendment notes cite the amending norm by its
# reference ("Ref. BOE-A-2019-3108"; amending articles of the laws themselves say "Se
# modifica" too, so those words prove nothing), and the Senate's notes on the Court's
# rulings and the superseded wording they quote.
NOTE_WORDS = re.compile(
    r"Ref\. BOE-A-|^Téngase en cuenta|Corte Constitucional|Texto original de la Ley"
    r"|NOTAS DE VIGENCIA|declarado (IN)?EXEQUIBLE",
    re.MULTILINE,
)
DAYS = [
    date(2001, 1, 1),
    date(2019, 2, 10),
    date(2026, 3, 1),
    date(2026, 10, 5),
    date(2026, 10, 20),
]
# source id: (versions or articles parsed, distinct article ids)
EXPECTED = {
    "es-lau-boe-2026-10-13": (232, 78),
    "es-lph-boe-2026-10-05": (92, 31),
    "fl-stat-83-2026": (40, 40),
    "fl-stat-718-2026": (3, 3),
    "co-ley-820-senado-2026-10-15": (43, 43),
    "co-ley-675-senado-2026-10-15": (87, 87),
    "dubai-law-26-2007-dlp-2024-12-20": (37, 37),
    "dubai-law-33-2008-dlp-2023-08-07": (13, 13),  # 11 restated, its own 1, and "2 #2"
    "dubai-dld-tenancy-guide-2020-02-07": (54, 54),  # Decree 43/2013, Law 33/2008, Law 26/2007
}


def parse(source_id: str) -> ParsedDocument:
    for folder in (PROCESSED, local_processed(FETCHED)):
        if (path := folder / f"{source_id}.json").exists():
            return ParsedDocument.model_validate_json(path.read_text())
    pytest.skip(f"{source_id} is not parsed on this machine (make fetch, then make ingest)")


def article_chunks(doc: ParsedDocument) -> list[Chunk]:
    return chunk_document(doc, ChunkerConfig(kind="article"), law_name=law_name(doc.law))


def test_every_committed_parse_is_counted() -> None:
    committed = {path.stem for path in Path(PROCESSED).glob("*.json")}
    assert committed <= set(EXPECTED)


@pytest.mark.parametrize("source_id", sorted(EXPECTED))
def test_every_article_is_found_once_per_version(source_id: str) -> None:
    doc = parse(source_id)
    articles = parse_articles(doc)
    assert (len(articles), len({a.article for a in articles})) == EXPECTED[source_id]
    for kind in ("article", "fixed"):
        chunk_document(doc, ChunkerConfig(kind=kind), law_name=law_name(doc.law))  # ids unique


@pytest.mark.parametrize("source_id", sorted(EXPECTED))
def test_notes_never_reach_the_indexed_text(source_id: str) -> None:
    found = article_chunks(parse(source_id))
    leaks = [c.label for c in found if NOTE_WORDS.search(c.text)]
    assert leaks == []


@pytest.mark.parametrize("source_id", sorted(EXPECTED))
def test_one_version_of_an_article_applies_on_any_day(source_id: str) -> None:
    articles = [c for c in article_chunks(parse(source_id)) if c.parent_id is None]
    for day in DAYS:
        live = Counter(c.article for c in articles if c.in_force_on(day))
        assert [a for a, n in live.items() if n > 1] == [], day


def test_october_2026_wording_never_answers_a_question_dated_march() -> None:
    found = article_chunks(parse("es-lau-boe-2026-10-13"))
    march = [c for c in found if c.in_force_on(date(2026, 3, 1))]
    assert all(c.effective_from and c.effective_from < date(2026, 3, 1) for c in march)
    assert {c.article for c in march if c.parent_id is None} >= {"9", "10", "36"}


def test_lph_articles_numbered_in_words_have_their_numbers() -> None:
    found = article_chunks(parse("es-lph-boe-2026-10-05"))
    keys = {c.article for c in found}
    assert {str(n) for n in range(1, 25)} <= keys
    assert {"DA única", "DA 1", "DA 2", "DA 3", "DT 1", "DT 2", "DF única"} <= keys
    assert "LPH, art. 21.1" in {c.label for c in found}


def test_colombia_keeps_headingless_and_repealed_articles() -> None:
    ley_820 = {c.article: c for c in article_chunks(parse("co-ley-820-senado-2026-10-15"))}
    assert ley_820["40"].status.value == "repealed"
    assert {a for a, c in ley_820.items() if c.status.value == "repealed"} == {
        "35", "36", "38", "39", "40",
    }  # fmt: skip
    ley_675 = {c.article for c in article_chunks(parse("co-ley-675-senado-2026-10-15"))}
    assert {"60", "84"} <= ley_675


ASOF_CASES = ROOT / "data" / "golden" / "asof_cases.json"


def asof_cases() -> list[dict[str, Any]]:
    if not ASOF_CASES.exists():
        return []
    cases: list[dict[str, Any]] = json.loads(ASOF_CASES.read_text())
    return cases


@pytest.mark.skipif(not ASOF_CASES.exists(), reason="Lane B's as-of cases are not on this branch")
@pytest.mark.parametrize("case", asof_cases(), ids=lambda case: str(case["id"]))
def test_lane_bs_as_of_cases_find_the_version_in_force(case: dict[str, Any]) -> None:
    """Lane B's point-in-time cases, checked against the pinned BOE files by hand: which
    version applies on the day, with a phrase it must contain and phrases it must not."""
    source = next(p.stem for p in PROCESSED.glob(f"{case['law']}-*.json"))
    day = date.fromisoformat(case["as_of"])
    live = [
        c
        for c in article_chunks(parse(source))
        if c.article == case["article"] and c.parent_id is None and c.in_force_on(day)
    ]
    if case["version"] is None:  # not yet enacted on the day, or repealed
        assert live == []
        return
    assert len(live) == 1
    (article,) = live
    assert article.metadata["version_norm"] == case["version"]
    assert str(article.effective_from) == case["effective_from"]
    assert case["present"] in article.text
    assert not [phrase for phrase in case["absent"] if phrase in article.text]


def test_dubai_the_guide_keys_each_law_it_reproduces_and_keeps_its_headings_apart() -> None:
    articles = parse_articles(parse("dubai-dld-tenancy-guide-2020-02-07"))
    laws = Counter(a.article.split(" art. ")[0] for a in articles)
    assert laws == {"Decree 43/2013": 4, "Law 33/2008": 13, "Law 26/2007": 37}
    decree = {a.heading for a in articles if a.article.startswith("Decree")}
    assert not any(a.heading in decree for a in articles if a.article.startswith("Law 33"))
