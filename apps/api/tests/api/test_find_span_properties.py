"""Properties of chunks.find_span, which marks a citation's quote in its article ignoring case
and whitespace and answers in characters of the article's own text. Spanish accents and
letters whose case-folded form is longer (ß folds to ss) are in the alphabet on purpose."""

from __future__ import annotations

from hypothesis import assume, given
from hypothesis import strategies as st

from plumbline.api.chunks import find_span

LETTERS = "abcdefghijklmnñopqrstuvwxyzáéíóúüABCÑÁÉß0123456789.,;()§"
SPACES = " \n\t "
text_st = st.text(alphabet=LETTERS + SPACES, min_size=1, max_size=200)


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


@st.composite
def text_and_quote(draw: st.DrawFn) -> tuple[str, str]:
    """A text and a quote: random, or cut from the text's case-folded form, which can start
    or end inside a letter that folds to two."""
    text = draw(text_st)
    if draw(st.booleans()):
        return text, draw(text_st)
    folded = text.casefold()
    start = draw(st.integers(0, len(folded) - 1))
    end = draw(st.integers(start + 1, len(folded)))
    return text, folded[start:end]


@given(text_and_quote())
def test_what_it_marks_is_the_quote(pair: tuple[str, str]) -> None:
    text, quote = pair
    span = find_span(text, quote)
    if span is None:
        return
    assert 0 <= span.start < span.end <= len(text)
    marked = normalized(text[span.start : span.end])
    wanted = normalized(quote)
    # The mark holds the quote, and no more than a whole character can add: a quote may
    # begin or end inside a letter that folds to two (the "s" of "ß"), and a mark covers
    # whole characters, so at most one extra folded character at each end.
    assert wanted in marked
    assert len(marked) - len(wanted) <= 2
    # The mark starts and ends on the quote's own characters, never on a space.
    assert not text[span.start].isspace()
    assert not text[span.end - 1].isspace()


@given(text_st, st.data())
def test_a_quote_taken_from_the_text_is_found(text: str, data: st.DataObject) -> None:
    start = data.draw(st.integers(0, len(text) - 1))
    end = data.draw(st.integers(start + 1, len(text)))
    quote = text[start:end]
    assume(normalized(quote))
    span = find_span(text, quote)
    assert span is not None
    assert normalized(quote) in normalized(text[span.start : span.end])
    # The first whole-word match: never after the place the quote was taken from, when that
    # place cuts no word in two.
    first = start + (len(quote) - len(quote.lstrip()))
    last = start + len(quote.rstrip()) - 1
    cuts_start = first > 0 and text[first - 1].isalnum() and text[first].isalnum()
    cuts_end = last < len(text) - 1 and text[last + 1].isalnum() and text[last].isalnum()
    if not (cuts_start or cuts_end):
        assert span.start <= first


@given(text_st, st.data())
def test_spacing_and_case_in_the_quote_do_not_matter(text: str, data: st.DataObject) -> None:
    start = data.draw(st.integers(0, len(text) - 1))
    end = data.draw(st.integers(start + 1, len(text)))
    quote = text[start:end]
    assume(normalized(quote))
    respaced = "\n  ".join(quote.split())
    assert find_span(text, respaced) == find_span(text, quote)
    assert find_span(text, quote.upper()) == find_span(text, quote.casefold())


@given(text_st, st.text(alphabet=SPACES, max_size=5))
def test_a_blank_quote_marks_nothing(text: str, quote: str) -> None:
    assert find_span(text, quote) is None


def test_a_letter_that_folds_to_two_is_marked_whole() -> None:
    text = "Die Straße, 15 días"
    span = find_span(text, "STRASSE, 15")
    assert span is not None
    assert text[span.start : span.end] == "Straße, 15"


def test_a_quote_inside_a_folded_letter_marks_the_whole_letter() -> None:
    # Half of "ß" (casefold "ss") cannot be marked on its own; the letter is marked whole.
    span = find_span("aß b", "s b")
    assert span is not None
    assert "aß b"[span.start : span.end] == "ß b"


def test_the_mark_is_the_occurrence_the_verifier_accepts() -> None:
    # "3 days" first appears inside "30 days", which the verifier refuses as a quote.
    text = "Within 30 days, or 3 days after notice."
    span = find_span(text, "3 days")
    assert span is not None
    assert (span.start, text[span.start : span.end]) == (text.index("or 3") + 3, "3 days")
    # With no whole-word occurrence, the first one is still marked.
    inside = find_span("Within 30 days.", "0 days")
    assert inside is not None
    assert "Within 30 days."[inside.start : inside.end] == "0 days"
