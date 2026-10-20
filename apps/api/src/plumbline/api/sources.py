"""Source pages for the citation panel (Lane D): page images and where a quote sits on them.

    GET /api/sources/{source_id}/pages/{n}.png?scale=1|2|3      page n at 150, 300 or 450 dpi
    GET /api/sources/{source_id}/pages/{n}/boxes?quote=...      the quote's boxes on page n

Boxes are fractions of the page from its top left, so the browser draws them over a render
at any scale. An unknown source or page is 404, and so is a source without pages (HTML or
XML). A fetch-only source this machine has not fetched (make fetch) gets a labelled
placeholder image and no boxes. Renders stay in a small LRU cache.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Final

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi import Path as PathParam
from pydantic import BaseModel, Field

from plumbline.corpus.manifest import Manifest, Source
from plumbline.ingest.render import (
    PDFIUM_LOCK,
    page_count,
    placeholder_png,
    quote_boxes,
    render_png,
)

DPI: Final = {1: 150, 2: 300, 3: 450}
RENDERS_KEPT: Final = 32  # a 450-dpi page is about 1 MB


class PageBox(BaseModel):
    x0: float = Field(ge=0, le=1)
    y0: float = Field(ge=0, le=1)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)


class QuoteBoxes(BaseModel):
    source_id: str
    page: int
    available: bool  # False: the source is not on this machine, so nothing was searched
    found: bool
    boxes: list[PageBox]


class Corpus:
    """The manifest's sources and their files on this machine. The manifest is read when a
    route first needs it, not when the app starts: the API image carries no data/ (it is
    mounted where the server runs), and a server without a corpus must still start and
    answer its other routes."""

    def __init__(self, manifest: Callable[[], Manifest], root: Path) -> None:
        self._manifest = manifest
        self._sources: dict[str, Source] | None = None
        self._root = root
        self._files: dict[str, bytes] = {}
        self._renders: OrderedDict[tuple[str, int, int], bytes] = OrderedDict()
        self._lock = threading.Lock()

    def pdf(self, source_id: str) -> tuple[Source, bytes | None]:
        """The source, and its PDF when this machine has it; 404 for anything else."""
        source = self._source(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="No such source.")
        if source.format != "pdf":
            raise HTTPException(status_code=404, detail="This source has no pages.")
        with self._lock:
            if source_id not in self._files:
                path = self._root / source.path
                if not path.exists():
                    return source, None
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != source.sha256:
                    raise HTTPException(status_code=409, detail="The file is not the manifest's.")
                self._files[source_id] = data
            return source, self._files[source_id]

    def _source(self, source_id: str) -> Source | None:
        if self._sources is None:  # two threads may both read it; they read the same file
            try:
                self._sources = self._manifest().by_id()
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=503, detail="The corpus is not on this server."
                ) from exc
        return self._sources.get(source_id)

    def render(self, source_id: str, data: bytes, page: int, dpi: int) -> bytes:
        key = (source_id, page, dpi)
        with self._lock:
            if key in self._renders:
                self._renders.move_to_end(key)
                return self._renders[key]
        with PDFIUM_LOCK:
            if not 1 <= page <= page_count(data):
                raise HTTPException(status_code=404, detail="No such page.")
            png = render_png(data, page, dpi)
        with self._lock:
            self._renders[key] = png
            while len(self._renders) > RENDERS_KEPT:
                self._renders.popitem(last=False)
        return png


router = APIRouter(prefix="/api/sources", tags=["sources"])
Page = Annotated[int, PathParam(ge=1)]
Scale = Annotated[int, Query(ge=1, le=3, description="1, 2 or 3: 150, 300 or 450 dpi")]


def _corpus(request: Request) -> Corpus:
    corpus: Corpus = request.app.state.corpus
    return corpus


@router.get(
    "/{source_id}/pages/{n}.png",
    response_class=Response,
    responses={
        200: {
            "description": "The page as a PNG; a labelled placeholder when the source is not on"
            " this server.",
            "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def page_image(request: Request, source_id: str, n: Page, scale: Scale = 1) -> Response:
    corpus = _corpus(request)
    source, data = corpus.pdf(source_id)
    if data is None:
        with PDFIUM_LOCK:
            png = placeholder_png(f"Not on this server: {source.title} (make fetch)", DPI[scale])
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})
    png = corpus.render(source_id, data, n, DPI[scale])
    # A page image changes only with its file, so the file's hash makes a lasting ETag.
    etag = f'"{source.sha256[:16]}-{n}-{scale}"'
    headers = {"Cache-Control": "public, max-age=86400", "ETag": etag}
    return Response(png, media_type="image/png", headers=headers)


@router.get("/{source_id}/pages/{n}/boxes")
def page_boxes(
    request: Request,
    source_id: str,
    n: Page,
    quote: Annotated[str, Query(min_length=1, max_length=2000)],
) -> QuoteBoxes:
    source, data = _corpus(request).pdf(source_id)
    if data is None:
        return QuoteBoxes(source_id=source.id, page=n, available=False, found=False, boxes=[])
    with PDFIUM_LOCK:
        if not 1 <= n <= page_count(data):
            raise HTTPException(status_code=404, detail="No such page.")
        boxes = quote_boxes(data, n, quote)
    return QuoteBoxes(
        source_id=source.id,
        page=n,
        available=True,
        found=bool(boxes),
        boxes=[PageBox(**box._asdict()) for box in boxes],
    )
