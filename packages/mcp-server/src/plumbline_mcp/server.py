"""Plumbline's corpus over the Model Context Protocol: three tools, over stdio, that call the
public API (PLUMBLINE_API_URL, https://plumbline-api.alinedlabs.co by default).

- search_law: the provisions that bear on a query, ready to cite; no model is called.
- get_article: the whole article a provision belongs to, with a quote located in it.
- check_clause: one lease clause against the law it touches, on Plumbline's lease checker.

What the tools return is legal information, never legal advice. The licence rule is the
API's, so a client cannot get around it: a source whose terms forbid republishing it (the
Dubai and Colombian texts) is never shown beyond the passage a quote names. Every failure
the API explains (a quota, a paused service, a bad argument) reaches the model as a tool
error in the API's own words, so it can change course; anything else is a crash, whose
details stay in the server's log.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Annotated, Any, Final
from urllib.parse import quote as quote_path

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from plumbline_mcp.models import ChunkArticle, ClauseResult, Jurisdiction, LawSearch

DEFAULT_API_URL: Final = "https://plumbline-api.alinedlabs.co"
TIMEOUT_S: Final = 120.0  # a clause check is a model call over retrieved law
INSTRUCTIONS: Final = (
    "Plumbline searches the official tenancy law of Dubai, Spain, Colombia and Florida. Cite "
    "a provision by its label and quote only its text; a hit marked restricted has no text "
    "to quote, so link its source instead. What these tools return is legal information, "
    "not legal advice."
)


def api_url() -> str:
    return os.environ.get("PLUMBLINE_API_URL", DEFAULT_API_URL).rstrip("/")


async def _call(client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> Any:
    try:
        response = await client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise ToolError(f"Plumbline's API could not be reached ({type(exc).__name__}).") from None
    if response.is_success:
        return response.json()
    raise ToolError(_explain(response))


def _explain(response: httpx.Response) -> str:
    """The API's own sentence for a failure (problem details), or its status."""
    try:
        problem = response.json()
    except ValueError:
        problem = {}
    detail = problem.get("detail") if isinstance(problem, dict) else None
    code = problem.get("code") if isinstance(problem, dict) else None
    text = detail if isinstance(detail, str) and detail else f"HTTP {response.status_code}"
    if response.status_code == 422 and isinstance(problem, dict) and problem.get("errors"):
        fields = ", ".join(".".join(map(str, e.get("loc", []))) for e in problem["errors"])
        text = f"{text} ({fields})"
    return f"{text} [{code}]" if isinstance(code, str) else text


READ_ONLY: Final = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=True)


def build_server(client: httpx.AsyncClient) -> MCPServer:
    """The server, calling the API through `client` (whose base_url is the API's)."""
    mcp = MCPServer("plumbline", instructions=INSTRUCTIONS)

    @mcp.tool(title="Search the law", annotations=READ_ONLY)
    async def search_law(
        query: Annotated[str, Field(min_length=1, max_length=1000, description="In English.")],
        jurisdiction: Annotated[
            Jurisdiction | None, Field(description="One jurisdiction; all four when absent.")
        ] = None,
        as_of: Annotated[
            date | None, Field(description="The law in force on this date; today when absent.")
        ] = None,
        k: Annotated[int, Field(ge=1, le=10, description="How many provisions.")] = 5,
    ) -> LawSearch:
        """The provisions of Dubai, Spain, Colombia or Florida tenancy law that bear on a
        query, best first, each with its citation label and source."""
        params: dict[str, str | int] = {"q": query, "k": k}
        if jurisdiction:
            params["jurisdiction"] = jurisdiction
        if as_of:
            params["as_of"] = as_of.isoformat()
        return LawSearch.model_validate(
            await _call(client, "GET", "/api/law/search", params=params)
        )

    @mcp.tool(title="Read an article", annotations=READ_ONLY)
    async def get_article(
        chunk_id: Annotated[str, Field(min_length=1, description="A hit's chunk_id.")],
        quote: Annotated[
            str | None,
            Field(max_length=2000, description="A passage to locate in the article."),
        ] = None,
    ) -> ChunkArticle:
        """The whole article a provision belongs to, as published, with where `quote` sits
        in it. For a restricted source, only the quoted passage."""
        params = {"quote": quote} if quote else {}
        path = f"/api/chunks/{quote_path(chunk_id, safe=':')}"
        return ChunkArticle.model_validate(await _call(client, "GET", path, params=params))

    @mcp.tool(
        title="Check a lease clause",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def check_clause(
        clause: Annotated[str, Field(min_length=1, max_length=4000, description="One clause.")],
        jurisdiction: Annotated[Jurisdiction, Field(description="The law the lease is under.")],
        as_of: Annotated[
            date | None, Field(description="When the lease was signed; today when absent.")
        ] = None,
    ) -> ClauseResult:
        """How one lease clause compares with the law it touches: a finding resting on
        verified quotes, or none when that law does not address it. The clause is redacted
        before any model reads it, and refused if it cannot be. Counts against the day's
        lease checks. The finding's clause_number is always "1": number the clause yourself."""
        body = ClauseBody(clause=clause, jurisdiction=jurisdiction, as_of=as_of)
        data = await _call(
            client, "POST", "/api/law/check-clause", json=body.model_dump(mode="json")
        )
        return ClauseResult.model_validate(data)

    return mcp


class ClauseBody(BaseModel):
    clause: str
    jurisdiction: Jurisdiction
    as_of: date | None


def main() -> None:
    """The stdio server: `plumbline-mcp`, or `python -m plumbline_mcp`."""
    import anyio

    async def serve() -> None:
        async with httpx.AsyncClient(
            base_url=api_url(),
            timeout=TIMEOUT_S,
            headers={"User-Agent": "plumbline-mcp"},
        ) as client:
            await build_server(client).run_stdio_async()

    anyio.run(serve)
