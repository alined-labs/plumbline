"""The parsed corpus: data/processed/<source_id>.json holds one ParsedDocument per source,
committed, so every lane rebuilds the index without docling, a vision model or a key.

A fetch-only source (Dubai's laws, Colombia's Senate pages) may not be redistributed, and
its parse holds its whole text, as do its docling and vision recordings. So its parse and
its recordings stay under data/corpus/fetched/, which git ignores, next to the file
itself: a machine indexes it after make fetch, and parses it once there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from plumbline.core.types import ParsedDocument
from plumbline.corpus.manifest import Source
from plumbline.ingest.parse import parser_for
from plumbline.settings import ROOT

PROCESSED: Final = ROOT / "data" / "processed"
FETCHED: Final = ROOT / "data" / "corpus" / "fetched"  # fetch-only sources, never committed


def local_processed(fetched: Path = FETCHED) -> Path:
    return fetched / "processed"


def local_cache(fetched: Path = FETCHED) -> Path:
    return fetched / "cache"


def processed_path(source_id: str, directory: Path = PROCESSED) -> Path:
    return directory / f"{source_id}.json"


def write_processed(document: ParsedDocument, directory: Path = PROCESSED) -> Path:
    path = processed_path(document.source_id, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document.model_dump_json(indent=1) + "\n", encoding="utf-8")
    return path


def read_processed(source: Source, directory: Path = PROCESSED) -> ParsedDocument | None:
    """The parse of `source` kept in `directory`, or None when there is none or it is
    stale: made from a different file (the source's hash changed) or by a different reader
    (a reader's version, or docling's, moved on)."""
    path = processed_path(source.id, directory)
    if not path.exists():
        return None
    document = ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))
    current = document.sha256 == source.sha256 and document.parser == parser_for(source)
    return document if current else None
