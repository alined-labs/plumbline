"""The golden-set and results schema: the contract between the dataset, the harness and
every system scored on it. Frozen: a change is a new schema version, agreed in a brain block.

A golden set is one JSON object per line (``golden_v<N>.jsonl``). Every question is in
English; gold references point at statute articles pinned to an edition of the corpus
manifest, and answerable items carry a reference answer and, once checked, the record of
how they were verified.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final, Literal, Protocol, Self, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

SCHEMA_VERSION: Final = 1


class Jurisdiction(StrEnum):
    DUBAI = "dubai"
    SPAIN = "spain"
    COLOMBIA = "colombia"
    FLORIDA = "florida"


class Language(StrEnum):
    """Language of a source text. Questions and answers are always English."""

    EN = "en"
    ES = "es"


class Category(StrEnum):
    SINGLE_ARTICLE = "single_article"
    MULTI_ARTICLE = "multi_article"
    CROSS_JURISDICTION = "cross_jurisdiction"
    NUMERIC_DATE = "numeric_date"
    OUT_OF_SCOPE = "out_of_scope"
    PARTIAL = "partial"
    LEASE_CHECK = "lease_check"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class SourceType(StrEnum):
    """Where a question came from: paraphrased from an official FAQ or a public forum
    thread (never copied), or written to fill a gap."""

    OFFICIAL_FAQ = "official_faq"
    FORUM = "forum"
    SYNTHETIC = "synthetic"


class Split(StrEnum):
    DEV = "dev"
    TEST = "test"
    UNASSIGNED = "unassigned"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    PARTIAL = "partial"
    ABSTAINED = "abstained"


Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=80)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonEmpty = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ArticleRef(Frozen):
    """One statute article, pinned to the corpus edition it was read in."""

    jurisdiction: Jurisdiction
    law: Slug  # the corpus manifest's law id, for example "fl-stat-83"
    article: Annotated[str, StringConstraints(min_length=1, max_length=40, strip_whitespace=True)]
    paragraph: str | None = None  # finer than the article, for display only: "(3)(a)", "2"
    edition: NonEmpty  # the manifest edition id the text was read in

    @property
    def key(self) -> str:
        """Identity used by the metrics: an article matches across paragraphs and editions."""
        return f"{self.jurisdiction.value}:{self.law}:{self.article}"


class Verification(Frozen):
    """How a gold item was checked against the official text."""

    quoted_text: NonEmpty  # the article text that supports the answer, in its original language
    second_source: NonEmpty  # title and URL of a second source: an official FAQ, a bar pamphlet
    checked_on: date
    checked_by: NonEmpty
    notes: str | None = None


class GoldenItem(Frozen):
    id: Slug  # for example "fl-0007"
    question: Annotated[
        str, StringConstraints(min_length=8, max_length=2000, strip_whitespace=True)
    ]
    source_language: Language  # the language of the gold statute text
    jurisdictions: list[Jurisdiction]
    category: Category
    difficulty: Difficulty
    gold_refs: list[ArticleRef] = Field(default_factory=list)
    reference_answer: str | None = None
    expected_abstain: bool = False
    partial: bool = False
    as_of: date | None = None  # the date the answer must hold on (date-conditional items)
    signed_on: date | None = None  # a lease's signing date, when the rule depends on it
    source_type: SourceType
    source_note: str | None = None  # where the question came from, paraphrased
    split: Split = Split.UNASSIGNED
    lease_id: Slug | None = None  # the synthetic lease a lease-check item reads
    verification: Verification | None = None
    added_in: Annotated[str, StringConstraints(pattern=r"^v[0-9]+$")]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.expected_abstain:
            if self.partial:
                raise ValueError("an item cannot both abstain and be partial")
        else:
            if not self.gold_refs:
                raise ValueError("an answerable item needs at least one gold_ref")
            if not self.reference_answer:
                raise ValueError("an answerable item needs a reference_answer")
            if not self.jurisdictions:
                raise ValueError("an answerable item needs its jurisdictions")
        if (self.category is Category.OUT_OF_SCOPE) != self.expected_abstain:
            raise ValueError("out_of_scope items, and only they, have expected_abstain")
        if (self.category is Category.PARTIAL) != self.partial:
            raise ValueError("partial items, and only they, have partial")
        if self.category is Category.LEASE_CHECK and self.lease_id is None:
            raise ValueError("a lease_check item needs its lease_id")
        if self.category is Category.CROSS_JURISDICTION and len(set(self.jurisdictions)) < 2:
            raise ValueError("a cross_jurisdiction item names at least two jurisdictions")
        missing = {r.jurisdiction for r in self.gold_refs} - set(self.jurisdictions)
        if missing:
            raise ValueError(f"gold_refs cite jurisdictions not listed: {sorted(missing)}")
        return self


class RetrievedRef(Frozen):
    """One retrieved article, as a system under test reports it."""

    key: NonEmpty  # ArticleRef.key of the article the retrieved text belongs to
    score: float
    chunk_id: str | None = None


@runtime_checkable
class Retriever(Protocol):
    """What a system implements to be scored on the retrieval metrics."""

    def retrieve(
        self,
        question: str,
        *,
        k: int,
        jurisdictions: Sequence[Jurisdiction] | None = None,
        as_of: date | None = None,
    ) -> list[RetrievedRef]: ...


class EvalResult(Frozen):
    """The outcome for one golden item under one configuration."""

    item_id: Slug
    retrieved: list[RetrievedRef] = Field(default_factory=list)
    status: AnswerStatus | None = None  # None when only retrieval was evaluated
    answer: str | None = None
    cited: list[str] = Field(default_factory=list)  # ArticleRef keys of verified citations
    invalid_citations: int = Field(default=0, ge=0)
    metrics: dict[str, float | None] = Field(default_factory=dict)  # booleans as 0.0 or 1.0
    latency_ms: float | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    trace_id: str | None = None
    error: str | None = None


class EvalRun(Frozen):
    """A results file: one configuration over one split, stamped so it can be rebuilt."""

    schema_version: Literal[1] = SCHEMA_VERSION
    run_id: Slug
    config_name: NonEmpty
    config_hash: Sha256
    git_sha: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{7,40}(-dirty)?$")]
    golden_file: NonEmpty
    golden_sha256: Sha256
    split: Literal["dev", "test", "all"]
    created_at: datetime
    judged: bool
    n_items: int = Field(ge=0)
    results: list[EvalResult]
    summary: dict[str, float | None] = Field(default_factory=dict)
    notes: str | None = None

    @model_validator(mode="after")
    def _complete(self) -> Self:
        if self.n_items != len(self.results):
            raise ValueError(f"n_items is {self.n_items} but there are {len(self.results)} results")
        ids = [r.item_id for r in self.results]
        if len(ids) != len(set(ids)):
            raise ValueError("an item appears twice in results")
        return self


class GoldenFileError(ValueError):
    """A golden file that does not validate; the message names every bad line."""


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_golden(path: Path) -> list[GoldenItem]:
    """Every item of a golden JSONL file, validated, with unique ids."""
    items: list[GoldenItem] = []
    errors: list[str] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = GoldenItem.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"{path.name}:{number}: {exc}")
            continue
        if item.id in seen:
            errors.append(f"{path.name}:{number}: duplicate id {item.id}")
        seen.add(item.id)
        items.append(item)
    if errors:
        raise GoldenFileError("\n".join(errors))
    return items


def dump_golden(items: Sequence[GoldenItem], path: Path) -> None:
    """Write items as canonical JSONL: one object per line, keys in schema order."""
    lines = (item.model_dump_json(exclude_defaults=False) for item in items)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
