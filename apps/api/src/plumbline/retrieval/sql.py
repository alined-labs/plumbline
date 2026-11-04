"""Search the chunks table in one SQL statement: exact cosine search, BM25, or both fused by
Reciprocal Rank Fusion, with every filter inside the statement.

Each leg ranks the chunks that pass the filters and keeps its best `candidates`; the
hybrid statement fuses the two lists as `fusion.rrf` does, key for key: the sum of
1 / (k + rank) over the legs a chunk is in, ties broken by its best rank, then its id.

- The legs search leaves only (the chunks with an embedding: paragraphs, and articles
  without paragraphs); generation gets whole articles from the parent merge after this.
- Dense is exact: row_number() over every row that passes the filters computes every
  distance, so no approximate index can change the order.
- BM25 searches the English field with the question and the Spanish field with its
  Spanish form (the rewrite, when the configuration has one; else the question, whose
  article numbers and names still match). The fields' expressions must repeat migration
  0004's literally, and an alias is a type modifier, not a parameter, so they are fixed
  text here. One query scores both fields, so their scores share one ranking.
- The as-of filter keeps the text that applied on the day: effective_from <= day <
  effective_to, a null meaning open-ended, and status in force. A day is always given:
  without one, superseded wording would answer beside the current one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from plumbline.core.types import Jurisdiction, Language

Mode = Literal["dense", "bm25", "hybrid"]

_EN: Final = "(CASE WHEN language = 'en' THEN text_for_search END)::pdb.alias('search_en')"
_ES: Final = "(CASE WHEN language = 'es' THEN text_for_search END)::pdb.alias('search_es')"


@dataclass(frozen=True)
class Filters:
    variant: str
    as_of: date
    jurisdictions: Sequence[Jurisdiction] | None = None  # None: every jurisdiction
    languages: Sequence[Language] | None = None  # None: both languages


@dataclass(frozen=True)
class SqlHit:
    """A leaf chunk the statement returned, best first, with each leg's rank and score."""

    id: str
    dense_rank: int | None
    dense: float | None  # cosine similarity
    bm25_rank: int | None
    bm25: float | None
    rrf: float | None  # hybrid only

    @property
    def score(self) -> float:
        """The score its ranking used: RRF when fused, else its one leg's."""
        for value in (self.rrf, self.dense, self.bm25):
            if value is not None:
                return value
        raise ValueError(f"{self.id} has no score")


def search(
    session: Session,
    mode: Mode,
    filters: Filters,
    *,
    vector: Sequence[float] | None,
    query: str,
    spanish_query: str | None,
    candidates: int,
    rrf_k: int,
) -> list[SqlHit]:
    """The leaves that match, best first: at most `candidates` per leg."""
    if mode != "bm25" and vector is None:
        raise ValueError(f"{mode} search needs the question's embedding")
    params: dict[str, object] = {
        "variant": filters.variant,
        "as_of": filters.as_of,
        "candidates": candidates,
        "k": rrf_k,
        "vector": _vector(vector) if vector is not None else None,
        "query": query,
        "spanish_query": spanish_query or query,
    }
    where = _where(filters, params)
    rows = session.execute(text(statement(mode, where)), params)
    return [SqlHit(*row) for row in rows]


def statement(mode: Mode, where: str) -> str:
    """The statement's text. Only this module's fixed fragments are joined into it (the
    fields, and `_where`'s clauses); every value is a bind parameter."""
    dense = f"""dense AS (
        SELECT id, 1 - (embedding <=> CAST(:vector AS vector)) AS score,
               row_number() OVER (ORDER BY embedding <=> CAST(:vector AS vector), id) AS rank
        FROM chunks WHERE {where}
        ORDER BY rank LIMIT :candidates)"""  # noqa: S608
    bm25 = f"""bm25 AS (
        SELECT id, pdb.score(key)::float8 AS score,
               row_number() OVER (ORDER BY pdb.score(key) DESC, id) AS rank
        FROM chunks WHERE ({_EN} ||| :query OR {_ES} ||| :spanish_query) AND {where}
        ORDER BY rank LIMIT :candidates)"""  # noqa: S608
    if mode == "dense":
        return f"""WITH {dense}
        SELECT id, rank, score, NULL::bigint, NULL::float8, NULL::float8 FROM dense
        ORDER BY rank"""  # noqa: S608
    if mode == "bm25":
        return f"""WITH {bm25}
        SELECT id, NULL::bigint, NULL::float8, rank, score, NULL::float8 FROM bm25
        ORDER BY rank"""  # noqa: S608
    # A leg a chunk is missing from adds 0. Each term is a float8 division and the sum one
    # float8 addition, which is fusion.rrf's exactly rounded sum for two legs.
    return f"""WITH {dense}, {bm25}
        SELECT COALESCE(d.id, b.id) AS id, d.rank, d.score, b.rank, b.score,
               COALESCE(1::float8 / (:k + d.rank), 0) + COALESCE(1::float8 / (:k + b.rank), 0)
                   AS rrf
        FROM dense d FULL JOIN bm25 b ON b.id = d.id
        ORDER BY rrf DESC, LEAST(d.rank, b.rank), id"""  # noqa: S608


def _where(filters: Filters, params: dict[str, object]) -> str:
    clauses = [
        "variant = :variant",
        "embedding IS NOT NULL",  # leaves only: a parent with paragraphs has no embedding
        "status = 'in_force'",
        "(effective_from IS NULL OR effective_from <= :as_of)",
        "(effective_to IS NULL OR :as_of < effective_to)",
    ]
    if filters.jurisdictions is not None:
        clauses.append("jurisdiction = ANY(:jurisdictions)")
        params["jurisdictions"] = [j.value for j in filters.jurisdictions]
    if filters.languages is not None:
        clauses.append("language = ANY(:languages)")
        params["languages"] = [language.value for language in filters.languages]
    return " AND ".join(clauses)


def _vector(values: Sequence[float]) -> str:
    """pgvector's text form; repr keeps every float exactly."""
    return "[" + ",".join(repr(float(v)) for v in values) + "]"
