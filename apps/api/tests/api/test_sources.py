"""Page images and quote boxes over a corpus of fixture PDFs: one on disk, one fetch-only
source that is not, and an HTML source without pages."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from plumbline.api import restricted, sources
from plumbline.api.app import create_app
from plumbline.api.sources import Corpus
from plumbline.core.types import CacheMode
from plumbline.corpus.manifest import Manifest
from plumbline.settings import Settings

from ..ingest.pdfs import STATUTE


def _source(source_id: str, data: bytes, fmt: str, *, committed: bool) -> dict[str, Any]:
    folder = "raw" if committed else "fetched"
    return {
        "id": source_id,
        "law": "dubai-law-26-2007",
        "title": "Law No. 26 of 2007",
        "jurisdiction": "dubai",
        "language": "en",
        "url": "https://dubailand.gov.ae/law.pdf",
        "edition": "2007",
        "retrieved_on": date(2026, 10, 19).isoformat(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "format": fmt,
        "license_basis": "test",
        "committed": committed,
        "path": f"data/corpus/{folder}/{source_id}.{fmt}",
    }


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    raw = tmp_path / "data" / "corpus" / "raw"
    fetched = tmp_path / "data" / "corpus" / "fetched"
    raw.mkdir(parents=True)
    fetched.mkdir()
    (raw / "statute.pdf").write_bytes(STATUTE)
    (fetched / "licensed.pdf").write_bytes(STATUTE)  # fetched here, and not ours to republish
    manifest = Manifest.model_validate(
        {
            "sources": [
                _source("statute", STATUTE, "pdf", committed=True),
                _source("licensed", STATUTE, "pdf", committed=False),
                _source("gone", b"%PDF", "pdf", committed=True),  # committed, but not on disk
                _source("chapter", b"<html/>", "html", committed=True),
            ]
        }
    )
    settings = Settings(_env_file=None, cache_mode=CacheMode.REPLAY)
    with TestClient(create_app(settings, corpus=Corpus(lambda: manifest, tmp_path))) as test_client:
        yield test_client


def _png_size(png: bytes) -> tuple[int, int]:
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])
    return width, height


@pytest.mark.parametrize(("scale", "width"), [(1, 1275), (2, 2550)])  # 8.5 in at 150, 300 dpi
def test_a_page_renders_at_each_scale(client: TestClient, scale: int, width: int) -> None:
    response = client.get("/api/sources/statute/pages/1.png", params={"scale": scale})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert abs(_png_size(response.content)[0] - width) <= 1  # PDFium rounds up
    assert response.headers["etag"].endswith(f'-1-{scale}"')


def test_a_render_is_made_once(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    real = sources.render_png

    def counted(data: bytes, page: int, dpi: int, **kwargs: Any) -> bytes:
        calls.append(page)
        return real(data, page, dpi, **kwargs)

    monkeypatch.setattr(sources, "render_png", counted)
    first = client.get("/api/sources/statute/pages/3.png").content
    assert client.get("/api/sources/statute/pages/3.png").content == first
    assert calls == [3]


@pytest.mark.parametrize(
    "path",
    [
        "/api/sources/statute/pages/4.png",  # the file has three pages
        "/api/sources/statute/pages/4/boxes?quote=x",
        "/api/sources/nowhere/pages/1.png",
        "/api/sources/chapter/pages/1.png",  # HTML: no pages
    ],
)
def test_what_does_not_exist_is_404(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_page_zero_and_an_unknown_scale_are_refused(client: TestClient) -> None:
    assert client.get("/api/sources/statute/pages/0.png").status_code == 422
    assert client.get("/api/sources/statute/pages/1.png?scale=4").status_code == 422


def test_a_quote_over_a_line_break_gets_a_box_per_line(client: TestClient) -> None:
    quote = "regula el arrendamiento de fincas urbanas.\n2. Se aplica"
    body = client.get("/api/sources/statute/pages/1/boxes", params={"quote": quote}).json()
    assert (body["available"], body["found"], len(body["boxes"])) == (True, True, 2)
    first, second = body["boxes"]
    assert first["y0"] < second["y0"]  # the second line is lower on the page
    assert all(0 <= box[k] <= 1 for box in body["boxes"] for k in ("x0", "y0", "x1", "y1"))


def test_a_quote_that_is_not_on_the_page_finds_nothing(client: TestClient) -> None:
    body = client.get("/api/sources/statute/pages/3/boxes", params={"quote": "Objeto"}).json()
    assert (body["found"], body["boxes"]) == (False, [])


def test_a_source_not_on_this_machine_gets_a_placeholder(client: TestClient) -> None:
    image = client.get("/api/sources/gone/pages/7.png")
    assert image.status_code == 200
    width, height = _png_size(image.content)
    assert max(abs(width - 1275), abs(height - 1650)) <= 1  # US letter at 150 dpi
    assert image.headers["cache-control"] == "no-store"
    body = client.get("/api/sources/gone/pages/7/boxes", params={"quote": "x"}).json()
    assert (body["available"], body["found"]) == (False, False)


def test_a_source_whose_terms_forbid_republishing_it_is_never_shown(client: TestClient) -> None:
    real = client.get("/api/sources/statute/pages/1.png")
    held_back = client.get("/api/sources/licensed/pages/1.png")  # the same file, fetched here
    assert held_back.status_code == 200
    assert held_back.content != real.content  # a placeholder, not the page
    assert held_back.headers["cache-control"] == "no-store"
    body = client.get("/api/sources/licensed/pages/1/boxes", params={"quote": "Objeto"}).json()
    assert (body["available"], body["found"], body["boxes"]) == (False, False, [])
    assert "licensed" not in client.app.state.corpus._files  # its file was not even read


def test_the_switch_for_consent_is_the_only_gate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(restricted, "SHOW_IN_FULL", True)
    shown = client.get("/api/sources/licensed/pages/1.png")
    assert shown.content == client.get("/api/sources/statute/pages/1.png").content


def test_a_server_without_a_corpus_starts_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    # The deployed image has no data/ (it is mounted where the server runs), so reading the
    # manifest at start-up would stop the container before it could answer anything.
    def missing() -> Manifest:
        raise FileNotFoundError("data/corpus/manifest.json")

    monkeypatch.setattr("plumbline.api.app.load_manifest", missing)
    settings = Settings(_env_file=None, cache_mode=CacheMode.REPLAY)
    with TestClient(create_app(settings)) as bare:
        response = bare.get("/api/sources/statute/pages/1.png")
    assert response.status_code == 503
    assert response.json()["detail"] == "The corpus is not on this server."
