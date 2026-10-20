"""The index stage's plan: which chunks a variant holds, which of them get a vector, and a
hash that follows everything a job writes. Uses the committed Florida chapter 83 parse."""

from __future__ import annotations

import pytest

from plumbline.core.config import EvalConfig, load_configs
from plumbline.core.types import ParsedDocument, ParsedPage
from plumbline.corpus.manifest import Source, load_manifest
from plumbline.ingest.laws import law_name
from plumbline.ingest.plan import UnsupportedConfig, leaves, plan_all, plan_unit, plan_units
from plumbline.ingest.processed import read_processed
from plumbline.settings import ROOT

CONFIGS = load_configs(ROOT / "evals" / "configs")


@pytest.fixture(scope="module")
def florida() -> tuple[Source, ParsedDocument]:
    source = load_manifest().by_id()["fl-stat-83-2026"]
    document = read_processed(source)
    assert document is not None
    return source, document


def _configs(*names: str) -> list[EvalConfig]:
    return [CONFIGS[name] for name in names]


def test_configurations_that_differ_only_in_search_share_a_unit(
    florida: tuple[Source, ParsedDocument],
) -> None:
    source, document = florida
    units = plan_units([source], {source.id: document}, _configs("A1", "A2", "A3", "A4"))
    assert [unit.configs for unit in units] == [("A1", "A2", "A3"), ("A4",)]
    assert len({unit.variant for unit in units}) == 2  # A4 adds the deterministic header


def test_a_fixed_chunker_and_an_article_chunker_are_two_variants(
    florida: tuple[Source, ParsedDocument],
) -> None:
    source, document = florida
    fixed, article = plan_units([source], {source.id: document}, _configs("A0", "A2"))
    assert fixed.variant != article.variant
    assert len(article.chunks) > len(fixed.chunks)
    assert len(fixed.embedded) == len(fixed.chunks)  # every fixed chunk is a leaf


def test_only_leaves_are_embedded(florida: tuple[Source, ParsedDocument]) -> None:
    source, document = florida
    (unit,) = plan_units([source], {source.id: document}, _configs("A2"))
    parents = {chunk.parent_id for chunk in unit.chunks if chunk.parent_id}
    assert parents
    assert all(chunk.id not in parents for chunk in unit.embedded)
    assert len(unit.embedded) == len(unit.chunks) - len(parents)
    assert [chunk.id for chunk in unit.embedded] == [chunk.id for chunk in leaves(unit.chunks)]


def test_the_hash_is_stable_and_follows_the_source_text(
    florida: tuple[Source, ParsedDocument],
) -> None:
    source, document = florida
    config = CONFIGS["A2"]
    first = plan_unit(source, document, config, ["A2"])
    assert plan_unit(source, document, config, ["A2"]).content_hash == first.content_hash
    first_page = document.pages[0]
    edited = ParsedPage(
        number=first_page.number,
        method=first_page.method,
        markdown=first_page.markdown.replace("Short title.", "Short title (amended)."),
    )
    changed = document.model_copy(update={"pages": [edited, *document.pages[1:]]})
    assert plan_unit(source, changed, config, ["A2"]).content_hash != first.content_hash


def test_a_configuration_that_needs_llm_headers_is_refused(
    florida: tuple[Source, ParsedDocument],
) -> None:
    source, document = florida
    with pytest.raises(UnsupportedConfig, match="A5 asks for LLM headers"):
        plan_unit(source, document, CONFIGS["A5"], ["A5"])


def test_a_law_without_a_short_name_is_refused() -> None:
    assert law_name("es-lau") == "LAU"
    with pytest.raises(ValueError, match="no short name for law 'xx-law'"):
        law_name("xx-law")


TWICE = """83.50 The same section.—

(1) The identical paragraph.

History.—s. 1, ch. 1.

83.50 The same section.—

(1) The identical paragraph.

History.—s. 1, ch. 1.
"""


def test_a_source_the_chunker_cannot_read_is_reported_and_the_others_planned(
    florida: tuple[Source, ParsedDocument],
) -> None:
    source, document = florida
    nameless = source.model_copy(update={"id": "xx-source", "law": "xx-law"})
    documents = {
        source.id: document,
        nameless.id: document.model_copy(update={"source_id": "xx-source"}),
    }
    units, unplanned = plan_all([nameless, source], documents, _configs("A2"))
    assert [unit.source.id for unit in units] == [source.id]
    assert [(u.source.id, u.configs) for u in unplanned] == [("xx-source", ("A2",))]
    assert "no short name for law 'xx-law'" in unplanned[0].error
    with pytest.raises(ValueError, match="xx-source: no short name"):  # the strict form
        plan_units([nameless], documents, _configs("A2"))


def test_a_source_that_chunks_in_one_variant_still_gets_that_one(
    florida: tuple[Source, ParsedDocument],
) -> None:
    # The same section twice gives two chunks one id under the article chunker, and is
    # nothing to the fixed one.
    source, document = florida
    twice = document.model_copy(
        update={"pages": [document.pages[0].model_copy(update={"markdown": TWICE})]}
    )
    units, unplanned = plan_all([source], {source.id: twice}, _configs("A0", "A2"))
    assert [unit.configs for unit in units] == [("A0",)]
    assert [u.configs for u in unplanned] == [("A2",)]
    assert "two chunks share an id" in unplanned[0].error


def test_a_configuration_that_cannot_be_built_is_still_an_error_not_a_skip(
    florida: tuple[Source, ParsedDocument],
) -> None:
    source, document = florida
    with pytest.raises(UnsupportedConfig):
        plan_all([source], {source.id: document}, _configs("A5"))
