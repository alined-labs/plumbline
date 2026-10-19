"""The committed OpenAPI schema is what the browser's types are generated from, so it must
match the app exactly (`make openapi` rewrites it)."""

from plumbline.api.app import create_app
from plumbline.api.openapi import render
from plumbline.settings import ROOT, Settings

COMMITTED = ROOT / "packages" / "ts-client" / "openapi.json"


def test_the_committed_schema_is_current() -> None:
    current = render(create_app(Settings(_env_file=None)))
    assert COMMITTED.read_text(encoding="utf-8") == current, "stale: run make openapi"


def test_stream_payloads_are_components() -> None:
    schemas = create_app(Settings(_env_file=None)).openapi()["components"]["schemas"]
    for name in ("Citation", "AnswerSummary", "TraceSummary", "StatusEvent", "StreamError"):
        assert name in schemas


def test_the_committed_stream_fixture_is_current() -> None:
    from plumbline.api.fixtures import stub_stream

    fixture = ROOT / "packages" / "ts-client" / "fixtures" / "ask-stub.sse"
    assert fixture.read_text(encoding="utf-8") == stub_stream(), "stale: run make openapi"
