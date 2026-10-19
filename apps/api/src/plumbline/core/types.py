"""Shared types: the contract between ingestion, retrieval, generation, the API and the
evaluation. Frozen: a change needs a brain block and `hub allow`.

Enumerations shared with the benchmark (jurisdictions, languages, answer status) are
defined once in `rag_eval.schema` and re-exported here, so the published harness and the
system can never disagree on them.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from rag_eval.schema import (
    AnswerStatus,
    ArticleRef,
    EvalResult,
    EvalRun,
    GoldenItem,
    Jurisdiction,
    Language,
    RetrievedRef,
)

__all__ = [
    "Answer",
    "AnswerStatus",
    "AnswerTrace",
    "ArticleRef",
    "CacheMode",
    "Chunk",
    "Citation",
    "DemoTier",
    "EvalResult",
    "EvalRun",
    "Frozen",
    "GoldenItem",
    "Jurisdiction",
    "Language",
    "MetadataValue",
    "ParseMethod",
    "ParsedDocument",
    "ParsedPage",
    "ProvisionStatus",
    "RetrievalScores",
    "Retrieved",
    "RetrievedRef",
]

NonEmpty = Annotated[str, StringConstraints(min_length=1)]
MetadataValue = str | int | float | bool | None


class Frozen(BaseModel):
    # Serialized payloads always carry every field, so their schema says so: the
    # browser's generated types then need no optional checks on stream data parts.
    model_config = ConfigDict(
        frozen=True, extra="forbid", json_schema_serialization_defaults_required=True
    )


class ProvisionStatus(StrEnum):
    """Validity of a provision on the edition's date. Colombian "Nota de vigencia" and
    INEXEQUIBLE markers map onto these values; the original note is kept in validity_note."""

    IN_FORCE = "in_force"
    REPEALED = "repealed"
    STRUCK_DOWN = "struck_down"


class DemoTier(StrEnum):
    """The degradation ladder: full (premium route on), free (free-tier models only),
    static (the static export serving stored answers)."""

    FULL = "full"
    FREE = "free"
    STATIC = "static"


class CacheMode(StrEnum):
    """How model calls use cache/: replay reads only (tests, the hub, CI); record calls the
    model on a miss and writes the recording; live calls on a miss and writes nothing."""

    REPLAY = "replay"
    RECORD = "record"
    LIVE = "live"


class ParseMethod(StrEnum):
    HTML = "html"  # a structured web source (BOE, Online Sunshine), read without a parser model
    TEXT_LAYER = "text_layer"  # a PDF page with a text layer, through docling
    OCR = "ocr"  # docling's OCR, for a scanned page
    VISION = "vision"  # a vision model's Markdown, for a page neither could read


class ParsedPage(Frozen):
    number: int = Field(ge=1)
    method: ParseMethod
    markdown: str


class ParsedDocument(Frozen):
    """A source after parsing: what the chunker reads. The ingest job writes one per
    source to data/processed/<source_id>.json, so chunking and indexing replay without
    running the parser."""

    source_id: NonEmpty  # the manifest's Source.id
    law: NonEmpty
    jurisdiction: Jurisdiction
    language: Language
    edition: NonEmpty
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]  # of the source file
    parser: NonEmpty  # what produced it, with its version: "docling-serve 1.37.0"
    pages: list[ParsedPage] = Field(min_length=1)  # in order; an HTML source is one page

    @property
    def markdown(self) -> str:
        return "\n\n".join(page.markdown for page in self.pages)


class Chunk(Frozen):
    """A retrievable unit of statute text: an article, or a numbered paragraph of one."""

    id: NonEmpty
    document_id: NonEmpty  # the corpus manifest's source id
    parent_id: str | None = None  # the article chunk a paragraph belongs to; None for an article
    jurisdiction: Jurisdiction
    law: NonEmpty  # the manifest's law id, as in ArticleRef.law
    language: Language
    edition: NonEmpty
    article: NonEmpty  # the bare article id: "25", "83.49", "9"
    path: list[str] = Field(default_factory=list)  # e.g. ["Título II", "Artículo 9", "1"]
    label: NonEmpty  # how a citation names it: "Fla. Stat. § 83.49(3)(a)"
    heading: str | None = None
    text: NonEmpty  # the source text, for display
    text_for_search: NonEmpty  # context header plus text: what is embedded and indexed
    context_header: str = ""  # "[Florida | Fla. Stat. ch. 83 | s. 83.49 | Deposit money]"
    context_header_llm: str | None = None  # the LLM-written header (configuration A5)
    effective_from: date | None = None
    effective_to: date | None = None  # exclusive; None while in force
    status: ProvisionStatus = ProvisionStatus.IN_FORCE
    validity_note: str | None = None  # the source's own validity note, verbatim
    history: str | None = None  # Florida's "History." line, kept out of the embedded text
    page: int | None = Field(default=None, ge=1)  # 1-based page in the source PDF
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _dates(self) -> Chunk:
        if self.effective_from and self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self

    @property
    def ref(self) -> ArticleRef:
        return ArticleRef(
            jurisdiction=self.jurisdiction, law=self.law, article=self.article, edition=self.edition
        )

    def in_force_on(self, day: date) -> bool:
        """Whether this text applied on `day` (the as-of filter)."""
        if self.status is not ProvisionStatus.IN_FORCE:
            return False
        if self.effective_from and day < self.effective_from:
            return False
        return not (self.effective_to and day >= self.effective_to)


class RetrievalScores(Frozen):
    dense: float | None = None
    bm25: float | None = None
    rrf: float | None = None
    rerank: float | None = None
    dense_rank: int | None = Field(default=None, ge=1)
    bm25_rank: int | None = Field(default=None, ge=1)


class Retrieved(Frozen):
    chunk: Chunk
    rank: int = Field(ge=1)
    score: float  # the score the final ranking used
    scores: RetrievalScores = Field(default_factory=RetrievalScores)

    def as_ref(self) -> RetrievedRef:
        return RetrievedRef(key=self.chunk.ref.key, score=self.score, chunk_id=self.chunk.id)


class Citation(Frozen):
    """One [n] marker in an answer and the span it quotes."""

    n: int = Field(ge=1)
    chunk_id: NonEmpty
    ref: ArticleRef
    label: NonEmpty
    quote: NonEmpty  # the cited span, verbatim, in the source language
    gloss: str | None = None  # English gloss when the source is not English
    language: Language
    verified: bool  # the verifier found the quote, normalized, inside the retrieved chunk
    page: int | None = Field(default=None, ge=1)


class Answer(Frozen):
    text: str
    status: AnswerStatus
    citations: list[Citation] = Field(default_factory=list)
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)
    as_of: date | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    abstain_reason: str | None = None
    invalid_citations: int = Field(default=0, ge=0)  # citations the verifier dropped


class AnswerTrace(Frozen):
    """Everything needed to explain, cost and replay one answer."""

    request_id: NonEmpty
    config_name: NonEmpty
    config_hash: NonEmpty
    route: NonEmpty  # the router's choice: "fast", "strong", "premium", "stub"
    model: NonEmpty
    tier: DemoTier
    retrieved: list[Retrieved] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)  # retrieve, rerank, generate, verify
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    cached: bool = False  # every model call came from cache/
    eval_run_id: str | None = None
    trace_url: str | None = None  # the Langfuse trace, when tracing is on
