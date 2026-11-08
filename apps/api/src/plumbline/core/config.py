"""The configuration schema: one YAML file per configuration under evals/configs/, hashed so
every result names exactly what produced it. Frozen: a change needs a brain block.

The hash covers everything that changes the system's behaviour (chunker, retrieval,
generation) and nothing that only labels or schedules it (name, description, judged), so
two files with the same settings share their cached results.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

ConfigName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")]
# The retrieval score an abstention threshold reads (core.types.RetrievalScores).
AbstainScore = Literal["rerank", "dense"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChunkerConfig(_Frozen):
    kind: Literal["fixed", "article"]
    max_tokens: int = Field(default=800, ge=64, le=8192)
    overlap_tokens: int = Field(default=0, ge=0, le=1024)
    # Retrieve numbered paragraphs, hand generation their whole parent article.
    merge_parent: bool = True


class RetrievalConfig(_Frozen):
    mode: Literal["dense", "bm25", "hybrid", "none"]  # none: the long-context baseline
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    rrf_k: int = Field(default=60, ge=1)
    candidates: int = Field(default=50, ge=1, le=500)  # per retriever, before fusion
    top_k: int = Field(default=8, ge=1, le=50)  # what generation receives
    rerank: Literal["none", "local", "cohere"] = "none"
    rerank_candidates: int = Field(default=20, ge=1, le=200)
    headers: Literal["none", "deterministic", "llm", "both"] = "none"  # both: A5 onwards
    cross_lingual_rewrite: bool = False  # rewrite English questions into Spanish for BM25
    jurisdiction_filter: bool = True
    as_of_filter: bool = True


class GenerationConfig(_Frozen):
    route: Literal["fast", "strong", "premium"] = "fast"
    long_context: bool = False  # the whole relevant law in one call, no retrieval
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_output_tokens: int = Field(default=1024, ge=64, le=8192)
    abstain_threshold: float | None = None  # the top score below which the answer abstains
    # Which score the threshold reads: the reranker's where a configuration reranks (offline
    # only, ADR-0005), else the top dense similarity. Not RRF: it is a function of ranks
    # alone (2/61 whenever a passage leads both lists, relevant or not), so it cannot say
    # that nothing is close enough. Nor BM25, whose scores do not compare across queries.
    abstain_score: AbstainScore = "rerank"


class EvalConfig(_Frozen):
    name: ConfigName
    description: str
    chunker: ChunkerConfig
    retrieval: RetrievalConfig
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    judged: bool = False  # run the judge on generation (costs money); retrieval metrics always run

    @model_validator(mode="after")
    def _threshold_has_its_score(self) -> Self:
        """A threshold on a score the configuration never produces would never fire."""
        generation, retrieval = self.generation, self.retrieval
        if generation.abstain_threshold is None:
            return self
        if generation.abstain_score == "rerank" and retrieval.rerank == "none":
            raise ValueError(
                f"{self.name}: abstain_threshold reads the rerank score, but nothing reranks; "
                "name the score it reads with abstain_score"
            )
        dense = retrieval.mode in ("dense", "hybrid") and not generation.long_context
        if generation.abstain_score == "dense" and not dense:
            raise ValueError(
                f"{self.name}: abstain_threshold reads the dense score, but this "
                "configuration searches no dense index"
            )
        return self

    def config_hash(self) -> str:
        behaviour = self.model_dump(mode="json", exclude={"name", "description", "judged"})
        canonical = json.dumps(behaviour, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_config(path: Path) -> EvalConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = EvalConfig.model_validate(raw)
    if config.name != path.stem:
        raise ValueError(f"{path}: name {config.name!r} must match the file name")
    return config


def load_configs(directory: Path) -> dict[str, EvalConfig]:
    """Every configuration in a directory, by name."""
    return {p.stem: load_config(p) for p in sorted(directory.glob("*.yaml"))}
