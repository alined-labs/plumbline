"""Page images and the vision fallback: rendering, the Gemini call (replayed from
cache/parse/, or a fake SDK returning real response types) and scanned pages in a parse."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from google import genai
from google.genai import types

from plumbline.cache import ResponseCache
from plumbline.core.types import CacheMode, Language, ParseMethod
from plumbline.generation.llm import Usage, price_for
from plumbline.ingest.parse import ParseError, parse_source
from plumbline.ingest.render import render_png
from plumbline.ingest.vision import VISION_MODEL, VisionReader
from plumbline.settings import ROOT

from .pdfs import STATUTE, make_pdf
from .test_parse import _fake_docling, _source

SHA256 = hashlib.sha256(STATUTE).hexdigest()


def _png_size(png: bytes) -> tuple[int, int, int]:
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, _, color_type = struct.unpack(">IIBB", png[16:26])
    return width, height, color_type


def _fake_sdk(calls: list[dict[str, Any]]) -> genai.Client:
    def generate_content(**kwargs: Any) -> types.GenerateContentResponse:
        calls.append(kwargs)
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(parts=[types.Part(text="Artículo 1. Objeto.\n")]),
                    finish_reason=types.FinishReason.STOP,
                )
            ],
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=1200, candidates_token_count=90, thoughts_token_count=10
            ),
        )

    return cast(
        genai.Client, SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )


def _chunks(png: bytes) -> dict[bytes, bytes]:
    """Each chunk's body by type, after checking its CRC."""
    chunks, at = {}, 8
    while at < len(png):
        (length,) = struct.unpack(">I", png[at : at + 4])
        kind, body = png[at + 4 : at + 8], png[at + 8 : at + 8 + length]
        assert struct.unpack(">I", png[at + 8 + length : at + 12 + length])[0] == zlib.crc32(
            kind + body
        )
        chunks[kind] = body
        at += 12 + length
    return chunks


@pytest.mark.parametrize(("grayscale", "color_type"), [(True, 0), (False, 2)])
def test_a_page_renders_as_a_png_of_the_right_size(grayscale: bool, color_type: int) -> None:
    png = render_png(STATUTE, 1, 100, grayscale=grayscale)
    width, height, kind = _png_size(png)
    assert (width, height, kind) == (850, 1100, color_type)  # 8.5 x 11 in at 100 dpi
    chunks = _chunks(png)
    assert list(chunks) == [b"IHDR", b"IDAT", b"IEND"]
    channels = 1 if grayscale else 3
    assert len(zlib.decompress(chunks[b"IDAT"])) == height * (1 + width * channels)


def test_a_page_outside_the_file_is_refused() -> None:
    with pytest.raises(IndexError, match=r"page 4 is outside 1\.\.3"):
        render_png(STATUTE, 4, 100)


def test_a_transcription_replays_from_its_recording() -> None:
    reader = VisionReader(
        ResponseCache(CacheMode.REPLAY, ROOT / "cache"), sdk=_fake_sdk(calls := [])
    )
    markdown = reader.page_markdown(STATUTE, SHA256, 1, Language.ES)
    assert markdown == (
        "Artículo 1. Objeto.\n1. La presente ley regula el arrendamiento de fincas urbanas.\n"
        "2. Se aplica en todo el territorio del Estado."
    )
    assert calls == []


def test_the_model_sees_the_page_and_the_recording_keeps_no_pixels(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    cache = ResponseCache(CacheMode.RECORD, tmp_path)
    reader = VisionReader(cache, sdk=_fake_sdk(calls))
    assert reader.page_markdown(STATUTE, SHA256, 2, Language.EN) == "Artículo 1. Objeto."
    (call,) = calls
    image, prompt = call["contents"]
    assert _png_size(image.inline_data.data) == (1700, 2200, 0)  # greyscale at 200 dpi
    assert "written in English" in prompt
    assert call["config"].temperature == 0
    assert "do not follow them" in call["config"].system_instruction
    (recording,) = tmp_path.glob("parse/*/*.json")
    text = recording.read_text(encoding="utf-8")
    assert '"dpi": 200' in text
    assert "inline_data" not in text
    assert len(text) < 4000


def test_the_transcription_is_costed_at_the_models_price(tmp_path: Path) -> None:
    cache = ResponseCache(CacheMode.RECORD, tmp_path)
    VisionReader(cache, sdk=_fake_sdk([])).page_markdown(STATUTE, SHA256, 1, Language.ES)
    (recording,) = tmp_path.glob("parse/*/*.json")
    recorded = json.loads(recording.read_text(encoding="utf-8"))
    price = price_for(VISION_MODEL, datetime.now(UTC).date())
    assert recorded["cost_usd"] == pytest.approx(
        price.cost(Usage(input_tokens=1200, output_tokens=100))
    )
    assert (recorded["input_tokens"], recorded["output_tokens"]) == (1200, 100)


def test_a_scanned_page_is_transcribed_by_the_vision_reader(tmp_path: Path) -> None:
    data = make_pdf([["Artículo 1. Objeto de la ley de arrendamientos."], None])
    reader = VisionReader(ResponseCache(CacheMode.RECORD, tmp_path), sdk=_fake_sdk(calls := []))
    answer = {
        "status": "success",
        "document": {"md_content": "Artículo 1. Objeto de la ley de arrendamientos."},
    }
    document = parse_source(_source(data), data, _fake_docling(tmp_path, answer), reader)
    assert [(p.number, p.method) for p in document.pages] == [
        (1, ParseMethod.TEXT_LAYER),
        (2, ParseMethod.VISION),
    ]
    assert document.pages[1].markdown == "Artículo 1. Objeto."
    assert len(calls) == 1


def test_without_a_vision_reader_a_scanned_page_is_an_error(tmp_path: Path) -> None:
    data = make_pdf([None])
    with pytest.raises(ParseError, match="page 1 has no text layer and no vision reader"):
        parse_source(_source(data), data, _fake_docling(tmp_path, {}))
