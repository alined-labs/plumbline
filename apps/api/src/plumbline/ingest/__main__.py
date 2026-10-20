"""`make ingest` (Lane D): from the corpus manifest to the index, logged per source.

    uv run python -m plumbline.ingest [--source ID ...] [--configs A0 A2 ...] [--parse-only]

1. Parse. Each source's parse is read back from data/processed/ while its hash matches the
   manifest's, and made only when it is missing or stale. A fetch-only source that is not
   on this machine (make fetch) is reported and skipped. Its parse and recordings stay
   under data/corpus/fetched/ (plumbline.ingest.processed), since its text may not be
   redistributed, so in replay mode one this machine never parsed is skipped too.
2. Chunk, embed, index. For each variant of the configurations asked for (A0 and A2, the
   baseline of Gate 1, unless --configs says otherwise) and each parsed source, one job
   (plumbline.ingest.run): the chunker, the embedder through the cache, then the database,
   which this stage first brings to the current schema.

Replay mode (tests, CI, the hub) needs no model server: embeddings come from recordings
under cache/embed/. Record mode needs the embedding server (make up-models, EMBED_URL).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from plumbline.cache import CacheMiss, ResponseCache, get_cache
from plumbline.core.config import EvalConfig, load_configs
from plumbline.core.types import ParsedDocument
from plumbline.corpus.manifest import MANIFEST, Source, load_manifest
from plumbline.db import make_engine, make_sessionmaker
from plumbline.db.migrate import upgrade
from plumbline.ingest.index import Embedder
from plumbline.ingest.parse import DoclingClient, ParseError, parse_source
from plumbline.ingest.plan import UnsupportedConfig, plan_units
from plumbline.ingest.processed import (
    FETCHED,
    PROCESSED,
    local_cache,
    local_processed,
    read_processed,
    write_processed,
)
from plumbline.ingest.run import Indexer, Outcome, run_units
from plumbline.ingest.vision import VisionReader
from plumbline.retrieval.embed import TeiEmbedder
from plumbline.settings import ROOT, Settings, get_settings

log = logging.getLogger("plumbline.ingest")

CONFIGS = ROOT / "evals" / "configs"
DEFAULT_CONFIGS = ("A0", "A2")  # the baseline of Gate 1
EmbedderFactory = Callable[[ResponseCache, str], Embedder]


def main(
    argv: Sequence[str] | None = None,
    *,
    manifest: Path = MANIFEST,
    root: Path = ROOT,
    processed: Path = PROCESSED,
    fetched: Path = FETCHED,
    configs_dir: Path = CONFIGS,
    database_url: str | None = None,
    embedder_factory: EmbedderFactory | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Parse the corpus and index it.")
    parser.add_argument("--source", action="append", help="only this source id (repeatable)")
    parser.add_argument(
        "--configs", nargs="+", default=list(DEFAULT_CONFIGS), help="configurations to index"
    )
    parser.add_argument("--parse-only", action="store_true", help="stop after parsing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    everything = load_manifest(manifest).sources
    sources = everything
    if args.source:
        unknown = set(args.source) - {s.id for s in sources}
        if unknown:
            parser.error(f"not in the manifest: {', '.join(sorted(unknown))}")
        sources = [s for s in everything if s.id in args.source]
    available = load_configs(configs_dir)
    if unknown := set(args.configs) - set(available):
        parser.error(f"no such configuration: {', '.join(sorted(unknown))}")
    settings = get_settings()
    caches = {
        True: get_cache(),  # committed sources: recordings go in git, under cache/
        False: ResponseCache(settings.cache_mode, local_cache(fetched)),  # fetch-only: git-ignored
    }
    documents, outcome = parse_stage(sources, root, processed, fetched, settings, caches)
    log.info(
        "%d sources: %s", len(sources), ", ".join(f"{n} {k}" for k, n in sorted(outcome.items()))
    )
    failed = bool(outcome["failed"])
    if args.parse_only or not documents:
        return 1 if failed else 0
    factory = embedder_factory or (
        lambda cache, model: TeiEmbedder(settings.embed_url, cache, model=model)
    )
    try:
        indexed = asyncio.run(
            index_stage(
                everything,
                documents,
                [available[name] for name in args.configs],
                available,
                database_url or settings.database_url,
                caches,
                factory,
                lambda source: read_parse(source, processed, fetched),
            )
        )
    except UnsupportedConfig as exc:
        parser.error(str(exc))
    return 1 if failed or any(o.status == "failed" for o in indexed) else 0


def parse_stage(
    sources: Sequence[Source],
    root: Path,
    processed: Path,
    fetched: Path,
    settings: Settings,
    caches: Mapping[bool, ResponseCache],
) -> tuple[dict[str, ParsedDocument], Counter[str]]:
    docling = {
        committed: DoclingClient(settings.docling_url, cache) for committed, cache in caches.items()
    }
    vision = {committed: VisionReader(cache) for committed, cache in caches.items()}
    documents: dict[str, ParsedDocument] = {}
    outcome: Counter[str] = Counter()
    for source in sources:
        path = root / source.path
        if not path.exists():
            log.warning(
                "%s: %s is not on this machine (make fetch); skipped", source.id, source.path
            )
            outcome["missing"] += 1
            continue
        folder = processed if source.committed else local_processed(fetched)
        document = read_processed(source, folder)
        status = "reused"
        if document is None:
            try:
                document = parse_source(
                    source, path.read_bytes(), docling[source.committed], vision[source.committed]
                )
            except CacheMiss:
                log.warning(
                    "%s: never parsed on this machine, and replay mode cannot call docling or the"
                    " vision model; parse it once with make up-ingest and CACHE_MODE=record"
                    " make ingest",
                    source.id,
                )
                outcome["unparsed"] += 1
                continue
            except ParseError:
                log.exception("%s: parsing failed", source.id)
                outcome["failed"] += 1
                continue
            write_processed(document, folder)
            status = "parsed"
        outcome[status] += 1
        documents[source.id] = document
        methods = Counter(page.method.value for page in document.pages)
        log.info(
            "%s: %s, %d pages (%s), %d characters",
            source.id,
            status,
            len(document.pages),
            ", ".join(f"{n} {method}" for method, n in sorted(methods.items())),
            len(document.markdown),
        )
    return documents, outcome


def read_parse(source: Source, processed: Path, fetched: Path) -> ParsedDocument:
    """A source's committed or local parse; the index stage runs after the parse stage."""
    document = read_processed(source, processed if source.committed else local_processed(fetched))
    if document is None:
        raise LookupError(f"{source.id} has no current parse: run make ingest")
    return document


async def index_stage(
    manifest: Sequence[Source],
    documents: Mapping[str, ParsedDocument],
    configs: Sequence[EvalConfig],
    available: Mapping[str, EvalConfig],
    database_url: str,
    caches: Mapping[bool, ResponseCache],
    embedder_factory: EmbedderFactory,
    load_document: Callable[[Source], ParsedDocument],
) -> list[Outcome]:
    """Index the sources the parse stage produced a document for, in the `configs` asked for.
    A worker may meet a job left from an earlier run, for any of the manifest's sources and
    any configuration in `available`, and builds its unit from the job alone."""
    units = plan_units(manifest, documents, configs)
    for unit in units:
        log.info(
            "%s in %s (%s): %d chunks, %d to embed",
            unit.source.id,
            "+".join(unit.configs),
            unit.variant,
            len(unit.chunks),
            len(unit.embedded),
        )
    await asyncio.to_thread(upgrade, database_url)
    engine = make_engine(database_url)
    sessions = make_sessionmaker(engine)
    indexer = Indexer(
        sessions=sessions,
        sources={s.id: s for s in manifest},
        configs=available,
        load_document=load_document,
        embedder_for=lambda source, model: embedder_factory(caches[source.committed], model),
    )
    try:
        outcomes = await run_units(
            sessions, units, indexer, worker=f"ingest@{socket.gethostname()}"
        )
    finally:
        await engine.dispose()
    for outcome in outcomes:
        unit = outcome.unit
        log.info(
            "%s in %s (%s): %s %s",
            unit.source.id,
            "+".join(unit.configs),
            unit.variant,
            outcome.status,
            ", ".join(f"{k} {v}" for k, v in outcome.detail.items() if k != "configs"),
        )
    totals = Counter(o.status for o in outcomes)
    log.info(
        "%d index jobs: %s", len(outcomes), ", ".join(f"{n} {k}" for k, n in sorted(totals.items()))
    )
    return outcomes


if __name__ == "__main__":
    raise SystemExit(main())
