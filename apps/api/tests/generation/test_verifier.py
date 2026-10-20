"""The citation verifier: what normalization forgives and what it does not, which citations
are dropped, the metrics, and properties over generated text."""

from dataclasses import dataclass

import pytest
from hypothesis import given
from hypothesis import strategies as st

from plumbline.core.types import Chunk, Jurisdiction, Language
from plumbline.generation.verifier import (
    citation_precision,
    citation_validity,
    normalize,
    quote_in,
    verify,
)

# Verbatim from The 2026 Florida Statutes, s. 83.49(3)(a), and the LAU, art. 36.1 (BOE
# consolidated text updated 2026-10-07), both read on 2026-10-19.
FLORIDA = (
    "Upon the vacating of the premises for termination of the rental agreement, if the "
    "landlord does not intend to impose a claim on the security deposit, the landlord must "
    "return the security deposit, together with interest if otherwise required, within 15 "
    "days after the termination of the rental agreement. If the landlord intends to impose "
    "a claim on the deposit, the landlord must, within 30 days after the termination of the "
    "rental agreement, provide the tenant written notice by certified mail to the tenant’s "
    "last known mailing address"
)
SPAIN = (
    "A la celebración del contrato será obligatoria la exigencia y prestación de fianza en "
    "metálico en cantidad equivalente a una mensualidad de renta en el arrendamiento de "
    "viviendas y de dos en el arrendamiento para uso distinto del de vivienda."
)


@dataclass(frozen=True)
class Cited:
    n: int
    chunk_id: str
    quote: str
    gloss: str | None = None


def chunk(id: str, text: str, language: Language = Language.EN) -> Chunk:
    return Chunk(
        id=id,
        document_id=id,
        jurisdiction=Jurisdiction.SPAIN if language is Language.ES else Jurisdiction.FLORIDA,
        law="lau" if language is Language.ES else "fl-stat-83",
        language=language,
        edition="2026",
        article="36" if language is Language.ES else "83.49",
        label=id,
        text=text,
        text_for_search=text,
    )


SOURCES = {1: chunk("fl", FLORIDA), 2: chunk("lau", SPAIN, Language.ES)}


@pytest.mark.parametrize(
    "quote",
    [
        "The landlord MUST return the security deposit,\n  together with interest",
        "by certified mail to the tenant's last known mailing address",  # ' for ’
        "the tenant’s last known mailing address",  # a no-break space
        "fianza en metálico en cantidad equivalente a una mensualidad de renta",
        "ＡＧＲＥＥＭＥＮＴ. If the landlord intends",  # fullwidth letters, NFKC
    ],
)
def test_normalization_forgives_what_changes_no_word(quote: str) -> None:
    assert quote_in(quote, FLORIDA + " " + SPAIN)


def test_quotation_marks_dashes_and_invisible_characters() -> None:
    text = "The term runs from 1 January – 31 December, the «fianza» included."
    assert quote_in('from 1 January - 31 December, the "fianza" included', text)
    assert quote_in("the security deposit", "return the security de­posit, together")


@pytest.mark.parametrize(
    "quote",
    [
        "A la celebracion del contrato sera obligatoria",  # accents dropped
        "the landlord must return the security deposit ... within 15 days",  # an ellipsis
        "the landlord has to give the deposit back within 15 days",  # a paraphrase
        "the landlord",  # too short to prove anything
        "   ",
        "the landlord must, within 3",  # a number cut short: "within 30 days"
        "en el arrendamiento de vivienda",  # a word cut short: "viviendas"
        "andlord does not intend",  # a word's start cut off
    ],
)
def test_normalization_does_not_forgive_a_changed_word(quote: str) -> None:
    assert not quote_in(quote, FLORIDA + " " + SPAIN)


def test_a_quote_matches_whole_words_only() -> None:
    text = "El arrendador notificará al arrendatario; el arrendador no podrá exigirla."
    assert not quote_in("el arrendador no", "el arrendador notificará al arrendatario")
    # The first place the quote occurs cuts a word, a later one does not: it verifies.
    assert quote_in("el arrendador no", text)
    # An edge that is punctuation is a boundary of its own.
    assert quote_in('"the security deposit,', 'return "the security deposit, together')
    assert quote_in("83.49(3)(a) of the statutes", "s. 83.49(3)(a) of the statutes")


def test_verify_keeps_good_citations_and_counts_every_failure() -> None:
    citations = [
        Cited(1, "fl", "within 15 days after the termination"),
        Cited(2, "lau", "fianza en metálico", gloss="a cash deposit"),
        Cited(2, "lau", "una mensualidad de renta en el arrendamiento"),  # [2] again: dropped
        Cited(1, "lau", "within 30 days after the termination"),  # [1] is not "lau": dropped
        Cited(3, "fl", "within 30 days after the termination"),  # no source 3: dropped
        Cited(1, "fl", ""),  # dropped
    ]
    result = verify(citations, SOURCES)
    assert [(c.n, c.verified) for c in result.citations] == [(1, True), (2, True)]
    assert result.invalid == 4
    spanish = result.citations[1]
    assert (spanish.gloss, spanish.language, spanish.ref.key) == (
        "a cash deposit",
        Language.ES,
        "spain:lau:36",
    )


def test_an_unverified_quote_is_kept_flagged_and_counted() -> None:
    result = verify([Cited(1, "fl", "the landlord may keep the deposit")], SOURCES)
    assert [c.verified for c in result.citations] == [False]
    assert result.verified == []
    assert result.invalid == 1


def test_the_metrics() -> None:
    assert citation_validity(3, 1) == 0.75
    assert citation_validity(0, 0) is None
    assert citation_precision(["fl:a:1", "fl:a:1", "fl:a:2"], {"fl:a:1"}) == 0.5
    assert citation_precision([], {"fl:a:1"}) is None


# Words of precomposed letters (a combining accent cut from its letter would change the
# letter, a real difference) with the punctuation normalization must forgive.
WORD = st.builds(
    str.__add__,
    st.text("abcñéAB", min_size=1, max_size=6),
    st.text(".,’'“\"«»–-\u00ad", max_size=2),
)
SEPARATOR = st.sampled_from([" ", "  ", "\n", "\u00a0", " \u00ad"])


@given(st.text(max_size=60))
def test_normalize_is_idempotent(text: str) -> None:
    assert normalize(normalize(text)) == normalize(text)


@given(st.lists(WORD, min_size=3, max_size=20), st.data())
def test_a_copied_span_verifies_however_it_is_restyled(
    words: list[str], data: st.DataObject
) -> None:
    text = words[0] + "".join(data.draw(SEPARATOR) + word for word in words[1:])
    start = data.draw(st.integers(0, len(words) - 3))
    span = " ".join(words[start : data.draw(st.integers(start + 3, len(words)))])
    restyled = data.draw(st.sampled_from([str.upper, str.lower, str.swapcase]))(span)
    for plain, fancy in data.draw(st.permutations([("'", "’"), ('"', "«"), ("-", "–")])):
        restyled = restyled.replace(plain, fancy)
    restyled = restyled.replace(" ", data.draw(SEPARATOR))
    assert quote_in(restyled, text)
    assert not quote_in(restyled + " zq", text)  # z and q are not in the alphabet


@given(
    st.lists(
        st.builds(
            Cited,
            n=st.integers(0, 3),
            chunk_id=st.sampled_from(["fl", "lau", "other"]),
            quote=st.sampled_from(["", "within 15 days after", "fianza en metálico", "x y z"]),
        ),
        max_size=8,
    )
)
def test_every_citation_is_verified_or_counted_invalid(citations: list[Cited]) -> None:
    result = verify(citations, SOURCES)
    assert len(result.verified) + result.invalid == len(citations)
    assert len({c.n for c in result.citations}) == len(result.citations)
