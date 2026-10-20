# plumbline-mcp

Plumbline's tenancy-law corpus over the [Model Context Protocol](https://modelcontextprotocol.io): the official statutes of Dubai, Spain, Colombia and Florida, searchable from any MCP client (Claude Desktop, Claude Code, an agent of your own). It gives legal information, never legal advice.

| Tool | What it does | Cost to you |
| --- | --- | --- |
| `search_law(query, jurisdiction?, as_of?, k?)` | The provisions that bear on a query, best first, each with its citation label, status, dates and source. Plumbline's own hybrid retrieval answers; no model is called. | none; a daily allowance of searches per address |
| `get_article(chunk_id, quote?)` | The whole article a hit belongs to, as published, with where `quote` sits in it. | none |
| `check_clause(clause, jurisdiction, as_of?)` | One lease clause against the law it touches: a finding (`conflict`, `check`, `note` or `match`) resting on verified quotes, or none when that law does not address it, with the disclaimer. | none to you; it counts against the day's lease checks |

## Run it

```bash
uvx plumbline-mcp                 # once published; from this repository: uv run plumbline-mcp
```

In a client's configuration (Claude Desktop's `claude_desktop_config.json`, for example):

```json
{
  "mcpServers": {
    "plumbline": { "command": "uvx", "args": ["plumbline-mcp"] }
  }
}
```

The server calls Plumbline's public API over HTTPS. One setting chooses which: `PLUMBLINE_API_URL`, `https://plumbline-api.alinedlabs.co` by default; set it to `http://localhost:8000` to use a local API (`make api` in this repository, with `ENVIRONMENT=prod` for real answers).

## What it will not show

Some sources' terms forbid republishing them: the Dubai Legislation Portal's laws and the Dubai Land Department's guide, and the Colombian Senado's annotated compilations. For these, a search hit carries the citation label and a link to the official source, but no text, and `get_article` returns only the passage a quote names. The rule lives in the API, so no client can get around it. See `DATA_LICENSES.md` in the repository.

## The clause you send

`check_clause` sends your clause to Plumbline. There, it is redacted before any model reads it. Until the redactor is live, every clause is refused with `redaction_refused`, and nothing is sent to a model. Plumbline neither stores nor logs the text. Do not send a lease you are not entitled to share.

## Errors

A failure the API explains reaches the model as a tool error in the API's own words, ending with the API's code. The model can then change course:

- `quota_reached`: today's allowance is used up until 00:00 UTC;
- `lease_checks_paused`: the demo tier or today's budget does not run clause checks;
- `redaction_refused`;
- a bad argument, naming the field.

An unreachable API says so, without the address. Anything unexpected is reported only as a failure, and the details stay in the server's log on your machine.

## Development

```bash
uv run pytest packages/mcp-server   # the tools against a stand-in API, through the SDK's in-memory client
```

`tests/test_models.py` holds the package's models to the API's schema (`packages/ts-client/openapi.json`), so a change to a payload fails here first.
