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


def test_spain_reads_articles_dispositions_and_their_dates() -> None:
    found = chunks("spain")
    # The BOE's index ("Artículo 4") and the preamble are not articles.
    assert [c.article for c in found if c.parent_id is None] == ["9", "9 bis", "DT 1"]
    article = parent(found, "9")
    assert article.path == ["Título II", "Capítulo II", "Artículo 9"]
    assert article.heading == "Plazo mínimo"
    # Amended, and the reader drops the form that names the current version: unknown.
    assert article.effective_from is None
    assert article.history is not None
    assert "Se modifica por el art. 1.4 de la Ley 4/2013" in article.history
    assert "Se modifica" not in article.text
    assert labels(found)[1:3] == ["LAU, art. 9.1", "LAU, art. 9.2"]
    disposition = parent(found, "DT 1")
    assert disposition.path == ["Disposición transitoria primera"]  # outside every Título
    assert disposition.label == "LAU, DT 1"


def test_spain_dates_only_the_current_version() -> None:
    # Verbatim BOE lines around invented English bodies: an amended article with its
    # current-version line, one added once, one added, voided and added again, and one
    # never amended.
    markdown = """##### Artículo 9. Plazo mínimo.
Invented body.
> Se modifica por el art. 1.4 de la Ley 4/2013, de 4 de junio. Ref. BOE-A-2013-5941.
Última actualización, publicada el 07/10/2026, en vigor a partir del 08/10/2026.
##### Artículo 9 bis. Plazo en los arrendamientos de vivienda temporal.
Invented body.
> Se añade por el art. 3.7 del Real Decreto-ley 29/2026, de 6 de octubre. Ref. BOE-A-2026-20823
Texto añadido, publicado el 30/09/2026, en vigor a partir del 01/10/2026.
##### Artículo 10. Prórroga del contrato.
Invented body.
> Se añade por el art. 3.7 del Real Decreto-ley 29/2026, de 6 de octubre. Ref. BOE-A-2026-20823
> Se deja sin efecto la adición de este artículo por Resolución de 2 de octubre de 2026.
> Se añade por el art. 3.7 del Real Decreto-ley 26/2026, de 29 de septiembre. Ref. BOE-A-2026-20266
Texto añadido, publicado el 30/09/2026, en vigor a partir del 01/10/2026.
##### Artículo 11. Desistimiento del contrato.
Invented body.
Texto original, publicado el 25/11/1994, en vigor a partir del 01/01/1995."""
    page = document("spain").pages[0].model_copy(update={"markdown": markdown})
    doc = document("spain").model_copy(update={"pages": [page]})
    found = chunk_document(doc, ARTICLE, law_name="LAU")
    assert [(c.article, c.effective_from) for c in found] == [
        ("9", date(2026, 10, 8)),
        ("9 bis", date(2026, 10, 1)),
        ("10", None),
        ("11", date(1995, 1, 1)),
    ]


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
    windows = chunks("spain", config)
    assert [w.metadata["articles"] for w in windows][:1] == ["9,9 bis"]
    assert windows[0].article == "9"
    assert TOKEN.findall(windows[0].text)[-100:] == TOKEN.findall(windows[1].text)[:100]


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
    doc = document("dubai")
    twice = doc.model_copy(
        update={"pages": [doc.pages[1], doc.pages[1].model_copy(update={"number": 2})]}
    )
    with pytest.raises(ValueError, match="share an id"):
        chunk_document(twice, ARTICLE, law_name="Law No. 26 of 2007")


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
