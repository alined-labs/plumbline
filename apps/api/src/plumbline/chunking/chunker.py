"""The two chunkers: article-aware (configurations A1 onwards) and fixed-size (A0).

Both read the same text, each article's opening line and its body with the notes left
out, so the ablation between them changes only where chunks begin and end.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from collections.abc import Iterator, Sequence
from itertools import accumulate, groupby

from plumbline.chunking.articles import Article, Paragraph, paragraph_tree, parse_articles
from plumbline.chunking.profiles import PROFILES
from plumbline.chunking.text import (
    TOKEN,
    Headers,
    chunk_id,
    context_header,
    count_tokens,
    search_text,
)
from plumbline.core.config import ChunkerConfig
from plumbline.core.types import Chunk, MetadataValue, ParsedDocument

Piece = tuple[tuple[str, ...], str]  # paragraph markers, text


def chunk_document(
    doc: ParsedDocument, config: ChunkerConfig, *, law_name: str, headers: Headers = "none"
) -> list[Chunk]:
    """Every chunk of one parsed source. `law_name` is how headers and labels name the
    law ("LAU", "Ley 820 de 2003", "Law No. 26 of 2007", "Fla. Stat. ch. 83")."""
    articles = parse_articles(doc)
    if config.kind == "fixed":
        chunks = _fixed(doc, articles, config, law_name, headers)
    else:
        chunks = [
            c for a in articles for c in _article(doc, a, config.max_tokens, law_name, headers)
        ]
    if len({c.id for c in chunks}) != len(chunks):
        raise ValueError(f"{doc.source_id}: two chunks share an id; is an article there twice?")
    return chunks


def _article(
    doc: ParsedDocument, article: Article, budget: int, law_name: str, headers: Headers
) -> list[Chunk]:
    """The article as the parent chunk, and its numbered paragraphs as children that
    cover its text once, in order: the lines before its first paragraph, then each
    paragraph. An article without numbered paragraphs is its own only chunk, unless it
    is over the budget, when it is cut between lines."""
    profile = PROFILES[doc.jurisdiction]
    validity = "\n".join(article.validity) or None
    # A repealed Colombian article shows no text, only its marker: the chunk keeps the
    # marker as its text, so the article can still be looked up and its status shown.
    text = "\n".join(article.body) or validity
    if not text:
        return []
    header = context_header(doc.jurisdiction, law_name, article.name, article.heading)
    path = [*article.divisions, article.name]
    # Unchanged paragraphs repeat in every BOE version: the version keeps their ids apart.
    version = [f"version {article.version.block} {article.version.norm}"] if article.version else []

    def chunk(markers: tuple[str, ...], body: str, parent_id: str | None) -> Chunk:
        return Chunk(
            id=chunk_id(doc.source_id, [*path, *markers, *version], body),
            document_id=doc.source_id,
            parent_id=parent_id,
            jurisdiction=doc.jurisdiction,
            law=doc.law,
            language=doc.language,
            edition=doc.edition,
            article=article.article,
            path=[*path, *markers],
            label=profile.label(law_name, article.article, markers),
            heading=article.heading,
            text=body,
            text_for_search=search_text(body, header, None, headers),
            context_header=header,
            effective_from=article.effective_from,
            effective_to=article.effective_to,
            status=article.status,
            validity_note=validity,
            history="\n".join(article.notes) or None,
            page=article.page,
            metadata=_version_metadata(article),
        )

    parent = chunk((), text, None)
    tree = paragraph_tree(article.body, profile.levels)
    pieces: list[Piece] = []
    if tree.children:
        pieces = [((), part) for part in _pack(tree.lines, budget)]
        pieces += [piece for child in tree.children for piece in _pieces(child, budget)]
    elif count_tokens(text) > budget:
        parts = list(_pack(tree.lines, budget))
        # One part is the parent again (a single line over the budget): no children.
        pieces = [((), part) for part in parts] if len(parts) > 1 else []
    return [parent, *(chunk(markers, body, parent.id) for markers, body in pieces)]


def _version_metadata(article: Article) -> dict[str, MetadataValue]:
    if article.version is None:
        return {}
    return {
        "version_block": article.version.block,
        "version_norm": article.version.norm,
        "effective_dated_by": article.version.dated_by,
    }


def _pieces(node: Paragraph, budget: int) -> Iterator[Piece]:
    """A paragraph whole when it fits the budget; otherwise its own lines, then each
    sub-paragraph the same way. This is how a long (3) becomes (3)(a), (3)(b)..."""
    if count_tokens(node.text()) <= budget:
        yield node.markers, node.text()
        return
    yield from ((node.markers, part) for part in _pack(node.lines, budget))
    for child in node.children:
        yield from _pieces(child, budget)


def _pack(lines: Sequence[str], budget: int) -> Iterator[str]:
    """Consecutive lines joined into parts within the budget; a line longer than the
    budget is a part of its own, never cut mid-sentence."""
    part: list[str] = []
    size = 0
    for line in lines:
        tokens = count_tokens(line)
        if part and size + tokens > budget:
            yield "\n".join(part)
            part, size = [], 0
        part.append(line)
        size += tokens
    if part:
        yield "\n".join(part)


def _fixed(
    doc: ParsedDocument,
    articles: Sequence[Article],
    config: ChunkerConfig,
    law_name: str,
    headers: Headers,
) -> list[Chunk]:
    """Windows of `max_tokens` tokens, `overlap_tokens` shared between neighbours, over
    the articles' text joined in order. A window spans articles, but a chunk names one:
    the article most of its tokens come from (the earlier one on a tie), whose label,
    status and dates it takes. metadata["articles"] lists every article it touches.
    A window never spans two validity periods: the windows restart wherever the dates
    change, so a window of the LAU never mixes its 1994 and its 2026 wording."""
    if config.max_tokens - config.overlap_tokens <= 0:
        raise ValueError("overlap_tokens must be smaller than max_tokens")
    chunks: list[Chunk] = []
    for _, run in groupby(articles, key=lambda a: (a.effective_from, a.effective_to)):
        chunks += _windows(doc, list(run), config, law_name, headers, first_window=len(chunks))
    return chunks


def _windows(
    doc: ParsedDocument,
    articles: Sequence[Article],
    config: ChunkerConfig,
    law_name: str,
    headers: Headers,
    first_window: int,
) -> list[Chunk]:
    step = config.max_tokens - config.overlap_tokens
    texts = ["\n".join([article.opening, *article.body]) for article in articles]
    full = "\n\n".join(texts)
    starts = list(accumulate((len(text) + 2 for text in texts[:-1]), initial=0))
    spans = [match.span() for match in TOKEN.finditer(full)]
    owners = [bisect_right(starts, start) - 1 for start, _ in spans]
    chunks: list[Chunk] = []
    for window, first in enumerate(range(0, len(spans), step), start=first_window):
        last = min(first + config.max_tokens, len(spans)) - 1
        text = full[spans[first][0] : spans[last][1]]
        owner = articles[Counter(owners[first : last + 1]).most_common(1)[0][0]]
        touched = dict.fromkeys(articles[i].article for i in owners[first : last + 1])
        header = context_header(doc.jurisdiction, law_name, owner.name, owner.heading)
        path = [*owner.divisions, owner.name]
        metadata: dict[str, MetadataValue] = {
            "articles": ",".join(touched),
            "window": window,
            **_version_metadata(owner),
        }
        chunks.append(
            Chunk(
                id=chunk_id(doc.source_id, [*path, f"window {window}"], text),
                document_id=doc.source_id,
                jurisdiction=doc.jurisdiction,
                law=doc.law,
                language=doc.language,
                edition=doc.edition,
                article=owner.article,
                path=path,
                label=PROFILES[doc.jurisdiction].label(law_name, owner.article, ()),
                heading=owner.heading,
                text=text,
                text_for_search=search_text(text, header, None, headers),
                context_header=header,
                effective_from=owner.effective_from,
                effective_to=owner.effective_to,
                status=owner.status,
                page=owner.page,
                metadata=metadata,
            )
        )
        if last == len(spans) - 1:
            break
    return chunks
