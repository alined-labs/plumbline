"""The citation verifier: a citation stands only if its quote is in the chunk it cites.

Reviewed line by line before merge. It decides what a reader is shown as the law's own
words, so it is deliberately strict and deliberately simple: no fuzzy matching, no model.

A quote verifies when, after both sides are normalized, it is a substring of the text of
the chunk its [n] marker points to. Normalization forgives only what changes no word:
Unicode compatibility forms (NFKC), case, runs of whitespace, invisible format characters,
and the many shapes of quotation marks and dashes. It does not forgive a dropped accent,
an ellipsis standing for omitted words, or a paraphrase: those fail.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from plumbline.core.types import Chunk, Citation

# A span this short is contained in almost any provision, so finding it proves nothing.
MIN_QUOTE_WORDS: Final = 3

_SINGLE: Final = "‘’‚‛′´`"  # ‘ ’ ‚ ‛ ′ ´ `
_DOUBLE: Final = "“”„‟″«»"  # “ ” „ ‟ ″ « »
_DASHES: Final = "‐‑‒–—―−"  # hyphens, en and em dashes, minus
_PUNCTUATION: Final = str.maketrans(
    {**dict.fromkeys(_SINGLE, "'"), **dict.fromkeys(_DOUBLE, '"'), **dict.fromkeys(_DASHES, "-")}
)


class CitedSpan(Protocol):
    """What a model's citation carries (generation.schema.GeneratedCitation fits)."""

    @property
    def n(self) -> int: ...
    @property
    def chunk_id(self) -> str: ...
    @property
    def quote(self) -> str: ...
    @property
    def gloss(self) -> str | None: ...


@dataclass(frozen=True)
class Verification:
    citations: list[Citation]  # every citation that names its source correctly, verified or not
    invalid: int  # citations that failed, for any reason: Answer.invalid_citations

    @property
    def verified(self) -> list[Citation]:
        return [c for c in self.citations if c.verified]


def normalize(text: str) -> str:
    # NFKC first, so compatibility forms (a fullwidth letter, a no-break space, a small em
    # dash) become the plain characters the later steps know. Casefolding can produce
    # characters outside NFKC, hence the second pass.
    text = unicodedata.normalize("NFKC", text)
    text = unicodedata.normalize("NFKC", text.casefold()).translate(_PUNCTUATION)
    # Format characters (soft hyphens, zero-width spaces, byte-order marks) are invisible
    # in the source, so a faithful copy of it may lack them.
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return " ".join(text.split())


def quote_in(quote: str, text: str) -> bool:
    """Whether `quote` appears in `text`, both normalized, and is long enough to matter."""
    needle = normalize(quote)
    return len(needle.split()) >= MIN_QUOTE_WORDS and needle in normalize(text)


def verify(citations: Sequence[CitedSpan], sources: Mapping[int, Chunk]) -> Verification:
    """Check a model's citations against the sources its prompt numbered (n -> chunk).

    A citation is dropped, and counted invalid, when its number names no source, when its
    chunk id is not that source's (the model contradicts itself about what it cites), when
    an earlier citation already used its number (the stream has one citation per [n]), or
    when its quote is empty.
    The rest are kept with `verified` set, and the unverified among them count as invalid
    too, so the stream can show a rejected [n] for what it is.
    """
    kept: list[Citation] = []
    invalid = 0
    seen: set[int] = set()  # every number used so far, kept or dropped
    for cited in citations:
        chunk = sources.get(cited.n)
        repeated = cited.n in seen
        seen.add(cited.n)
        if (
            chunk is None
            or chunk.id != cited.chunk_id
            # A number already used, even by a citation that was dropped: the model said two
            # things about what [n] cites, and the first was wrong.
            or repeated
            or not cited.quote  # nothing to show, and a Citation cannot hold it
        ):
            invalid += 1
            continue
        verified = quote_in(cited.quote, chunk.text)
        if not verified:
            invalid += 1
        kept.append(
            Citation(
                n=cited.n,
                chunk_id=chunk.id,
                ref=chunk.ref,
                label=chunk.label,
                quote=cited.quote,
                gloss=cited.gloss,
                language=chunk.language,
                verified=verified,
                page=chunk.page,
            )
        )
    return Verification(citations=kept, invalid=invalid)


def citation_validity(verified: int, invalid: int) -> float | None:
    """The share of an answer's citations that verified; None when it cites nothing."""
    total = verified + invalid
    return verified / total if total else None


def citation_precision(cited: Collection[str], gold: Collection[str]) -> float | None:
    """The share of the distinct articles an answer cites (verified, as ArticleRef keys)
    that are gold articles; None when it cites none. Two paragraphs of one article are one
    article here, as they are in the retrieval metrics."""
    distinct = set(cited)
    return len(distinct & set(gold)) / len(distinct) if distinct else None
