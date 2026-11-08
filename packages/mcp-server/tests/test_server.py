"""The three tools against a stand-in API (httpx.MockTransport), through the SDK's own
in-memory client: what each sends, what each returns, and what the model reads on failure."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp import Client

from plumbline_mcp.server import DEFAULT_API_URL, api_url, build_server

pytestmark = pytest.mark.anyio
OPENAPI = Path(__file__).resolve().parents[2] / "ts-client" / "openapi.json"


def _example(method: str, path: str) -> Any:
    """The API's own example response for an operation, from its OpenAPI schema."""
    operation = json.loads(OPENAPI.read_text())["paths"][path][method]
    content = operation["responses"]["200"]["content"]["application/json"]
    return next(iter(content["examples"].values()))["value"]


Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


@asynccontextmanager
async def _client(handler: Handler, seen: list[httpx.Request]) -> AsyncIterator[Client]:
    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(record)
    async with (
        httpx.AsyncClient(transport=transport, base_url="https://api.test") as http,
        Client(build_server(http)) as client,
    ):
        yield client


async def test_the_three_tools_are_listed_with_their_schemas(seen: list[httpx.Request]) -> None:
    async with _client(lambda r: httpx.Response(500), seen) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == {"search_law", "get_article", "check_clause"}
    assert tools["search_law"].input_schema["required"] == ["query"]
    assert set(tools["check_clause"].input_schema["required"]) == {"clause", "jurisdiction"}
    assert tools["search_law"].output_schema is not None
    assert tools["search_law"].annotations is not None
    assert tools["search_law"].annotations.read_only_hint is True
    assert seen == []  # listing calls nothing


async def test_search_law_passes_the_query_and_returns_the_hits(
    seen: list[httpx.Request],
) -> None:
    example = _example("get", "/api/law/search")
    async with _client(lambda r: httpx.Response(200, json=example), seen) as client:
        result = await client.call_tool(
            "search_law",
            {"query": "deposit", "jurisdiction": "florida", "as_of": "2026-03-01", "k": 2},
        )
    assert not result.is_error
    [request] = seen
    assert request.url.path == "/api/law/search"
    assert dict(request.url.params) == {
        "q": "deposit",
        "k": "2",
        "jurisdiction": "florida",
        "as_of": "2026-03-01",
    }
    assert result.structured_content is not None
    assert result.structured_content["hits"][0]["label"] == example["hits"][0]["label"]


async def test_get_article_escapes_the_id_and_sends_the_quote(seen: list[httpx.Request]) -> None:
    example = _example("get", "/api/chunks/{chunk_id}")
    async with _client(lambda r: httpx.Response(200, json=example), seen) as client:
        result = await client.call_tool(
            "get_article", {"chunk_id": "fl-stat-83-2026:abc/../x", "quote": "15 days"}
        )
    assert not result.is_error
    [request] = seen
    assert request.url.raw_path.decode().startswith("/api/chunks/fl-stat-83-2026:abc%2F..%2Fx?")
    assert request.url.params["quote"] == "15 days"
    assert result.structured_content is not None
    assert result.structured_content["restricted"] is False


async def test_check_clause_posts_the_clause(seen: list[httpx.Request]) -> None:
    example = _example("post", "/api/law/check-clause")
    async with _client(lambda r: httpx.Response(200, json=example), seen) as client:
        result = await client.call_tool(
            "check_clause", {"clause": "Deposit back in 45 days.", "jurisdiction": "florida"}
        )
    assert not result.is_error
    [request] = seen
    assert (request.method, request.url.path) == ("POST", "/api/law/check-clause")
    assert json.loads(request.content) == {
        "clause": "Deposit back in 45 days.",
        "jurisdiction": "florida",
        "as_of": None,
    }
    assert result.structured_content is not None
    assert result.structured_content["finding"]["severity"] == "conflict"


async def test_the_model_reads_the_apis_own_words_on_failure(seen: list[httpx.Request]) -> None:
    problem = {
        "title": "Service Unavailable",
        "status": 503,
        "detail": "This clause can't be checked until it can be redacted.",
        "code": "redaction_refused",
    }

    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json=problem)

    async with _client(refuse, seen) as client:
        result = await client.call_tool(
            "check_clause", {"clause": "John Smith pays.", "jurisdiction": "spain"}
        )
    assert result.is_error
    text = result.content[0].text  # type: ignore[union-attr]
    assert "can't be checked until it can be redacted" in text
    assert "[redaction_refused]" in text
    assert "John Smith" not in text


async def test_an_unreachable_api_is_a_plain_tool_error(seen: list[httpx.Request]) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused to 10.0.0.1", request=request)

    async with _client(down, seen) as client:
        result = await client.call_tool("search_law", {"query": "deposit"})
    assert result.is_error
    text = result.content[0].text  # type: ignore[union-attr]
    assert "could not be reached (ConnectError)" in text
    assert "10.0.0.1" not in text


async def test_bad_arguments_never_reach_the_api(seen: list[httpx.Request]) -> None:
    async with _client(lambda r: httpx.Response(200, json={}), seen) as client:
        for name, arguments in (
            ("search_law", {"query": ""}),
            ("search_law", {"query": "x", "k": 11}),
            ("search_law", {"query": "x", "jurisdiction": "mars"}),
            ("check_clause", {"clause": "x"}),
        ):
            assert (await client.call_tool(name, arguments)).is_error
    assert seen == []


def test_the_api_is_one_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLUMBLINE_API_URL", raising=False)
    assert api_url() == DEFAULT_API_URL == "https://plumbline-api.alinedlabs.co"
    monkeypatch.setenv("PLUMBLINE_API_URL", "http://localhost:8000/")
    assert api_url() == "http://localhost:8000"
