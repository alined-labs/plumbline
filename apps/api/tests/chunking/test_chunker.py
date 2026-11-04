"""The chunkers on short excerpts of each corpus. Florida, Spain and Colombia are verbatim
excerpts of the official texts; Dubai's text is never committed, so its fixture is invented
text in the official layout."""

from datetime import date
from functools import cache
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from plumbline.chunking.articles import numbering, parse_articles
from plumbline.chunking.chunker import chunk_document
from plumbline.chunking.profiles import PROFILES
from plumbline.chunking.text import TOKEN, Headers, clean_line, count_tokens, search_text
from plumbline.core.config import ChunkerConfig
from plumbline.core.types import Chunk, Jurisdiction, ParsedDocument, ProvisionStatus

FIXTURES = Path(__file__).parent / "fixtures"
LAW_NAMES = {
    "florida": "Fla. Stat. ch. 83",
    "spain": "LAU",
    "colombia": "Ley 820 de 2003",
    "dubai": "Law No. 26 of 2007",
}
ARTICLE = ChunkerConfig(kind="article")


@cache
def document(name: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json((FIXTURES / f"{name}.json").read_text())


def chunks(
    name: str, config: ChunkerConfig = ARTICLE, headers: Headers = "deterministic"
) -> list[Chunk]:
    return chunk_document(document(name), config, law_name=LAW_NAMES[name], headers=headers)


def parent(found: list[Chunk], article: str) -> Chunk:
    return next(c for c in found if c.article == article and c.parent_id is None)


def labels(found: list[Chunk]) -> list[str]:
    return [c.label for c in found]


def test_florida_sections_keep_their_history_out_of_the_indexed_text() -> None:
    found = chunks("florida")
    section = parent(found, "83.49")
    assert section.heading == "Deposit money or advance rent; duty of landlord and tenant"
    assert section.history is not None
    assert section.history.startswith("History.—s. 1, ch. 69-282")
    assert section.history.endswith("Note.—Former s. 83.261.")
    assert all("History.—" not in c.text_for_search for c in found)
    assert section.context_header == (
        "[Florida | Fla. Stat. ch. 83 | s. 83.49 | Deposit money or advance rent; duty of landlord and tenant]"
    )
    assert labels(found)[:3] == [
        "Fla. Stat. § 83.425",
        "Fla. Stat. § 83.49",
        "Fla. Stat. § 83.49(1)",
    ]


def test_florida_paragraphs_split_down_the_nested_path_when_over_budget() -> None:
    found = chunks("florida", ChunkerConfig(kind="article", max_tokens=200))
    names = labels(found)
    assert "Fla. Stat. § 83.49(3)(b)" in names
    # (1)(a) shares a line: (1) has no words of its own, so its children start at (1)(a).
    assert [n for n in names if n.startswith("Fla. Stat. § 83.60")] == [
        "Fla. Stat. § 83.60",
        "Fla. Stat. § 83.60(1)(a)",
        "Fla. Stat. § 83.60(1)(b)",
        "Fla. Stat. § 83.60(2)",
    ]
    nested = next(c for c in found if c.label == "Fla. Stat. § 83.49(3)(b)")
    assert nested.path == ["s. 83.49", "(3)", "(b)"]


def test_spain_reads_articles_dispositions_and_their_paths() -> None:
    found = chunks("spain")
    assert list(dict.fromkeys(c.article for c in found)) == ["9", "9 bis", "10", "38", "DT 1"]
    article = parent(found, "9")
    assert article.path == ["Título II", "Capítulo II", "Artículo 9"]
    assert article.heading == "Plazo mínimo"
    assert article.history is not None
    assert "Se modifica por el art. 1.4 del Real Decreto-ley 7/2019" in article.history
    assert all("Se modifica" not in c.text for c in found)
    assert labels(found)[1:3] == ["LAU, art. 9.1", "LAU, art. 9.2"]
    assert parent(found, "38").path == ["Título V", "Artículo 38"]
    disposition = parent(found, "DT 1")
    assert disposition.path == ["Disposición transitoria primera"]  # outside every Título
    assert disposition.label == "LAU, DT 1"


def versions(found: list[Chunk], article: str) -> list[tuple[date | None, date | None, str]]:
    return [
        (c.effective_from, c.effective_to, c.status.value)
        for c in found
        if c.article == article and c.parent_id is None
    ]


def test_spain_has_one_chunk_per_version_each_ending_where_the_next_begins() -> None:
    found = chunks("spain")
    assert versions(found, "9") == [
        (date(2019, 3, 6), date(2026, 10, 1), "in_force"),
        (date(2026, 10, 1), date(2026, 10, 2), "in_force"),  # RDL 26/2026, set aside
        (date(2026, 10, 2), date(2026, 10, 8), "in_force"),  # the 2019 wording, restored
        (date(2026, 10, 8), None, "in_force"),  # RDL 29/2026
    ]
    # Repealed in 2001, added back by RDL 26/2026, voided the next day, added back again.
    assert versions(found, "38") == [
        (date(1995, 1, 1), date(2001, 1, 8), "in_force"),
        (date(2001, 1, 8), date(2026, 10, 1), "repealed"),
        (date(2026, 10, 1), date(2026, 10, 2), "in_force"),
        (date(2026, 10, 2), date(2026, 10, 8), "repealed"),
        (date(2026, 10, 8), None, "in_force"),
    ]
    # An unchanged paragraph repeats in every version, under a different id each time.
    assert len({c.id for c in found}) == len(found)
    first = [c for c in found if c.label == "LAU, art. 9.2"]
    assert len(first) == 4
    assert len({c.text for c in first}) == 1
    assert first[0].metadata["version_norm"] == "BOE-A-2019-3108"


def test_spain_dates_a_version_the_boe_left_undated_from_its_note() -> None:
    # The BOE gives art. 10's current version no date; its note says "Se modifica, con
    # efectos de 8 de octubre de 2026, ..., y se modifica, con efectos de 15 de noviembre".
    article = parent(chunks("spain"), "10")
    assert (article.effective_from, article.effective_to) == (date(2026, 10, 8), None)
    assert article.metadata["effective_dated_by"] == "note"
    # RDL 28/2026's wording, quoted in a note for 15 November, is not law text yet.
    assert "incluidas las voluntarias" not in article.text
    assert article.history is not None
    assert "incluidas las voluntarias" in article.history


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 3, 1), date(2019, 3, 6)),  # golden items dated March see the 2019 text
        (date(2026, 10, 1), date(2026, 10, 1)),
        (date(2026, 10, 5), date(2026, 10, 2)),
        (date(2026, 10, 20), date(2026, 10, 8)),
    ],
)
def test_spain_the_as_of_filter_finds_exactly_one_version(day: date, expected: date) -> None:
    live = [c for c in chunks("spain") if c.article == "9" and c.in_force_on(day)]
    assert {c.effective_from for c in live} == {expected}
    assert len([c for c in live if c.parent_id is None]) == 1


def test_spain_only_the_line_after_a_version_marker_opens_an_article() -> None:
    markdown = """<!-- plumbline:version block=aprimero norm=X published=1960-07-23 effective=1960-08-12 -->
##### Artículo primero.
An invented body that quotes another law:
Artículo 2. An invented quoted heading.
<!-- plumbline:version block=aveintiuno norm=X published=1960-07-23 effective=1960-08-12 -->
##### Artículo veintiuno. Impago de los gastos comunes.
1. An invented paragraph.
<!-- plumbline:version block=da norm=X published=1999-04-08 effective=1999-04-28 -->
#### DISPOSICIÓN ADICIONAL
An invented body.
<!-- plumbline:version block=da-2 norm=X published=2025-01-03 effective= -->
##### Disposición adicional duodécima.
An invented body without a dated note."""
    found = parse_articles(spanish(markdown))
    assert [(a.article, a.name, a.heading) for a in found] == [
        ("1", "Artículo 1", None),
        ("21", "Artículo 21", "Impago de los gastos comunes"),
        ("DA única", "Disposición adicional única", None),
        ("DA 12", "Disposición adicional duodécima", None),
    ]
    assert found[0].body[-1] == "Artículo 2. An invented quoted heading."
    # No date and no dated note: the day it was published is the earliest it can apply.
    assert found[3].effective_from == date(2025, 1, 3)
    with pytest.raises(ValueError, match="opens no article"):
        parse_articles(spanish(markdown.replace("##### Artículo primero.", "Invented line.")))


def spanish(markdown: str) -> ParsedDocument:
    page = document("spain").pages[0].model_copy(update={"markdown": markdown})
    return document("spain").model_copy(update={"pages": [page]})


def test_colombia_validity_markers_set_the_status_and_stay_verbatim() -> None:
    found = chunks("colombia")
    repealed = parent(found, "35")
    assert repealed.status is ProvisionStatus.REPEALED
    assert repealed.validity_note is not None
    assert repealed.validity_note.startswith(
        "<Artículo derogado por el literal c) del artículo 626"
    )
    partly = parent(found, "12")
    assert partly.status is ProvisionStatus.IN_FORCE
    assert partly.validity_note == "<Inciso 3o. INEXEQUIBLE>\n<Inciso 5o. INEXEQUIBLE>"
    assert "INEXEQUIBLE" not in partly.text
    # The note boxes' headings carry no law.
    assert all("Jurisprudencia Vigencia" not in c.text for c in found)


def test_colombia_struck_down_words_never_reach_the_index() -> None:
    article = parent(chunks("colombia"), "37")
    assert article.heading == "PAGO DE SERVICIOS"
    assert article.text.startswith("el demandado deberá presentar la prueba")
    assert article.text.endswith("que acrediten su pago.")
    for struck in ("Cualquiera que fuere", "cosas o usos conexos", "treinta (30) días"):
        assert struck not in article.text_for_search


def test_colombia_numerals_and_paragrafo() -> None:
    found = chunks("colombia")
    assert parent(found, "8").heading == "OBLIGACIONES DEL ARRENDADOR"
    names = [c.label for c in found if c.article == "8"]
    assert names[-2:] == ["Ley 820 de 2003, art. 8, num. 5", "Ley 820 de 2003, art. 8, parágrafo"]


def test_dubai_headings_sit_above_articles_and_carry_over() -> None:
    found = [c for c in chunks("dubai") if c.parent_id is None]
    assert [(c.article, c.heading, c.page) for c in found] == [
        ("1", "Title", 1),
        ("4", "Lease Contract", 1),
        ("5", "Term of Lease Contract", 1),
        ("6", "Term of Lease Contract", 1),
        ("25", "Termination", 2),
    ]
    assert "Termination" not in found[3].text  # a heading is not its predecessor's text
    assert labels(chunks("dubai"))[-2:] == [
        "Law No. 26 of 2007, Art. 25(1)",
        "Law No. 26 of 2007, Art. 25(2)",
    ]


def test_colombia_quoted_notes_and_superseded_wording_are_never_law_text() -> None:
    # The Senate's notes, which the reader quotes, around invented words; and articles
    # whose text starts right after the number, as Ley 820 art. 40 and Ley 675 art. 60 do.
    extra = """
> Corte Constitucional
> - Inciso 3o. declarado INEXEQUIBLE por la Corte Constitucional mediante Sentencia C-670-04.
> Texto original de la Ley 820 de 2003:
> <INCISO 3o.> Invented superseded words.
ARTÍCULO 40. <Artículo derogado por el literal c) del artículo 626 de la Ley 1564 de 2012>
ARTÍCULO 60. Invented text that starts straight after the number."""
    doc = document("colombia")
    page = doc.pages[0].model_copy(update={"markdown": doc.pages[0].markdown + extra})
    found = chunk_document(
        doc.model_copy(update={"pages": [page]}), ARTICLE, law_name="Ley 820 de 2003"
    )
    assert all("Corte Constitucional" not in c.text for c in found)
    assert all("Invented superseded" not in c.text_for_search for c in found)
    assert parent(found, "37").history is not None
    assert "Texto original de la Ley 820 de 2003:" in (parent(found, "37").history or "")
    repealed = parent(found, "40")
    assert (repealed.heading, repealed.status) == (None, ProvisionStatus.REPEALED)
    assert parent(found, "60").text == "Invented text that starts straight after the number."


GUIDE = """Chapter III
Invented introduction to the legislation below.
Decree No. (43) of 2013
Determining Invented Increases
Having reviewed:
Law No. (16) of 2007 Establishing an invented agency;
Definitions
Article (1)
a. An invented clause.
Article (2)
An invented article.
Law No. (33) of 2008 Amending
Law No. (26) of 2007
Having reviewed:
Law No. (26) of 2007 Regulating an invented relationship;
Amendment
Article (1)
The invented articles below replace the old ones.
Article (2)
An invented restated definition.
Article (4)
An invented restated article.
Commencement
Article (2)
This invented law comes into force.
Law No. (26) of 2007
Title
Article (1)
An invented title article."""


def dubai(markdown: str, law: str) -> ParsedDocument:
    page = document("dubai").pages[0].model_copy(update={"markdown": markdown})
    return document("dubai").model_copy(update={"law": law, "pages": [page]})


def test_dubai_a_reproduced_law_keys_its_articles_by_law_and_occurrence() -> None:
    doc = dubai(GUIDE, "dubai-dld-tenancy-guide")
    found = chunk_document(doc, ARTICLE, law_name="DLD Tenancy Guide")
    assert [c.article for c in found if c.parent_id is None] == [
        "Decree 43/2013 art. 1",
        "Decree 43/2013 art. 2",
        "Law 33/2008 art. 1",
        "Law 33/2008 art. 2",
        "Law 33/2008 art. 4",
        "Law 33/2008 art. 2 #2",
        "Law 26/2007 art. 1",
    ]
    assert found[0].label == "DLD Tenancy Guide, Decree 43/2013 art. 1"
    assert found[0].heading == "Definitions"
    # The next law's title and recitals are not the end of the article before it.
    assert parent(found, "Decree 43/2013 art. 2").text == "An invented article."


def test_dubai_an_amending_law_keeps_its_own_numbers_and_numbers_a_repeat() -> None:
    own = GUIDE[GUIDE.index("Law No. (33)") : GUIDE.index("Law No. (26) of 2007\nTitle")]
    found = parse_articles(dubai(own, "dubai-law-33-2008"))
    assert [a.article for a in found] == ["1", "2", "4", "2 #2"]
    assert found[-1].name == "Article 2 #2"


@settings(max_examples=40, deadline=None)
@given(st.sampled_from(sorted(LAW_NAMES)), st.integers(min_value=64, max_value=1200))
def test_children_cover_their_parent_once_at_any_budget(name: str, budget: int) -> None:
    found = chunks(name, ChunkerConfig(kind="article", max_tokens=budget), headers="none")
    for article in (c for c in found if c.parent_id is None):
        children = [c for c in found if c.parent_id == article.id]
        if children:
            assert "\n".join(c.text for c in children) == article.text
        for child in children:
            # Over budget only when a single line is: lines are never cut.
            assert count_tokens(child.text) <= budget or "\n" not in child.text


@pytest.mark.parametrize("name", sorted(LAW_NAMES))
def test_fixed_windows_cover_the_same_text_without_loss(name: str) -> None:
    windows = chunks(name, ChunkerConfig(kind="fixed", max_tokens=300, merge_parent=False))
    assert all(count_tokens(w.text) <= 300 for w in windows)
    # Without overlap, every token of the articles' openings and bodies is in one window.
    articles = parse_articles(document(name))
    total = sum(count_tokens("\n".join([a.opening, *a.body])) for a in articles)
    assert sum(count_tokens(w.text) for w in windows) == total
    for window in windows:
        assert window.article in str(window.metadata["articles"]).split(",")


def test_fixed_windows_overlap_and_name_their_majority_article() -> None:
    config = ChunkerConfig(kind="fixed", max_tokens=800, overlap_tokens=100, merge_parent=False)
    windows = chunks("florida", config)
    assert [w.metadata["articles"] for w in windows][:1] == ["83.425,83.49"]
    assert windows[0].article == "83.49"
    assert TOKEN.findall(windows[0].text)[-100:] == TOKEN.findall(windows[1].text)[:100]


def test_fixed_windows_never_span_two_validity_periods() -> None:
    config = ChunkerConfig(kind="fixed", max_tokens=800, merge_parent=False)
    windows = chunks("spain", config)
    by_article = [w for w in windows if w.metadata["articles"] == "9"]
    assert [w.effective_from for w in by_article][:2] == [date(2019, 3, 6), date(2026, 10, 1)]
    assert len({w.id for w in windows}) == len(windows)
    for window in windows:
        assert window.metadata["version_block"] in {"a9", "a9-2", "a10", "a38", "dtprimera"}


def test_ids_are_stable_and_follow_the_text() -> None:
    assert [c.id for c in chunks("spain")] == [c.id for c in chunks("spain")]
    edited = document("dubai").model_copy(deep=True)
    page = edited.pages[1].model_copy(
        update={"markdown": edited.pages[1].markdown.replace("ninety", "sixty")}
    )
    changed = edited.model_copy(update={"pages": [edited.pages[0], page]})
    before = {c.label: c.id for c in chunks("dubai")}
    after = {c.label: c.id for c in chunk_document(changed, ARTICLE, law_name="Law No. 26 of 2007")}
    assert before["Law No. 26 of 2007, Art. 25(2)"] != after["Law No. 26 of 2007, Art. 25(2)"]
    assert before["Law No. 26 of 2007, Art. 25(1)"] == after["Law No. 26 of 2007, Art. 25(1)"]


def test_an_article_parsed_twice_is_an_error() -> None:
    doc = document("florida")
    twice = doc.model_copy(
        update={"pages": [doc.pages[0], doc.pages[0].model_copy(update={"number": 2})]}
    )
    with pytest.raises(ValueError, match="share an id"):
        chunk_document(twice, ARTICLE, law_name="Fla. Stat. ch. 83")


def test_search_text_follows_the_headers_setting() -> None:
    assert search_text("text", "[h]", None, "none") == "text"
    assert search_text("text", "[h]", None, "deterministic") == "[h]\ntext"
    assert search_text("text", "[h]", "llm", "both") == "[h]\nllm\ntext"
    with pytest.raises(ValueError, match="A10"):
        search_text("text", "[h]", None, "llm")


def test_tokens_lines_and_markers() -> None:
    assert count_tokens("Artículo 9.") == 3
    assert count_tokens("s. 83.49(3)") == 8
    assert clean_line("## Artículo 9\\. Plazo mínimo.") == "Artículo 9. Plazo mínimo."
    assert clean_line("**ARTÍCULO 8o. OBLIGACIONES.** Son") == "ARTÍCULO 8o. OBLIGACIONES. Son"
    assert clean_line("- (a) Hold the money") == "(a) Hold the money"
    assert clean_line("> Se modifica por la Ley 4/2013") == "Se modifica por la Ley 4/2013"
    assert clean_line("pago de los servicios ~~cosas~~") == "pago de los servicios ~~cosas~~"
    florida = PROFILES[Jurisdiction.FLORIDA].levels
    assert numbering("(1)(a) In an action", florida) == [(0, "(1)"), (1, "(a)")]
    assert numbering("1.5 percent of the rent", florida) == []
