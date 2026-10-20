"""Contextual headers for one law's chunks, as indexing needs them (configurations A5, A6).

`headers.write_headers` writes the model's sentences; this module decides what it is shown
and what is done with the answer:

- The context is the law as it stands on `as_of` (today when indexing): one version of each
  article, in order. The LAU with every version since 1994 runs to about 150,000 tokens,
  ten times the current text, and an older version is situated well enough by the law it
  belongs to now.
- A text is described once. Unchanged paragraphs repeat in every BOE version, and a header
  depends only on the text and its law, so each distinct (label, text) is sent once and
  its header shared, which halves the LAU's calls.
- The chunks come back with context_header_llm set and text_for_search rebuilt for the
  configuration's `headers` setting, ready for ingest.index_document.

Claude Haiku 5.5 writes them (Anthropic's study used a Claude model). Every call goes
through the client's cache, so indexing replays them; for a fetch-only source, the
caller passes a client on the fetched cache.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Final

from plumbline.chunking.text import Headers, search_text
from plumbline.core.types import Chunk
from plumbline.generation.llm import JUDGE_MODEL, LLMClient
from plumbline.retrieval.headers import write_headers

HEADER_MODEL: Final = JUDGE_MODEL  # claude-haiku-5-5: the cheap Claude, not the generator


def law_text(chunks: Sequence[Chunk], as_of: date) -> str:
    """The law's articles in force on `as_of`, in the chunker's order, each under its
    label."""
    return "\n\n".join(
        f"{c.label}\n{c.text}" for c in chunks if c.parent_id is None and c.in_force_on(as_of)
    )


async def contextualize(
    chunks: Sequence[Chunk],
    client: LLMClient,
    *,
    headers: Headers,
    as_of: date,
    model: str = HEADER_MODEL,
) -> list[Chunk]:
    """The chunks of one law, in order, with their LLM header and search text."""
    if headers not in ("llm", "both"):
        raise ValueError(f"headers={headers!r} has no LLM header to write")
    if len({c.law for c in chunks}) > 1:
        raise ValueError("contextualize one law at a time: the law is the context")
    distinct = list({(c.label, c.text): c for c in chunks}.values())
    written = await write_headers(law_text(chunks, as_of), distinct, client, model=model)
    by_text = {(c.label, c.text): c.context_header_llm for c in written}
    out: list[Chunk] = []
    for chunk in chunks:
        llm = by_text[(chunk.label, chunk.text)]
        out.append(
            chunk.model_copy(
                update={
                    "context_header_llm": llm,
                    "text_for_search": search_text(chunk.text, chunk.context_header, llm, headers),
                }
            )
        )
    return out
