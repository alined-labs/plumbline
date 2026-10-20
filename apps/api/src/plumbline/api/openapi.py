"""The OpenAPI schema, with an example for every operation (api/examples.py), plus the payloads of the event streams (the answer's data parts, an
ingestion job's events and a lease check's) as components, so the browser's types come from one generated
file (packages/ts-client).

    uv run python -m plumbline.api.openapi > packages/ts-client/openapi.json
    uv run python -m plumbline.api.openapi --check packages/ts-client/openapi.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi.openapi.utils import get_openapi
from pydantic.json_schema import models_json_schema

from plumbline.api.examples import add_examples
from plumbline.api.problems import MEDIA_TYPE, Problem
from plumbline.api.schemas import JobEventView, LeaseDoneEvent, LeaseFailedEvent, LeaseStageEvent
from plumbline.core.stream import AnswerSummary, StatusEvent, StreamError, TraceSummary
from plumbline.core.types import Citation
from plumbline.leases.schema import Finding

if TYPE_CHECKING:
    from fastapi import FastAPI

STREAM_MODELS = (
    StatusEvent,
    Citation,
    AnswerSummary,
    TraceSummary,
    StreamError,
    JobEventView,
    LeaseStageEvent,
    Finding,
    LeaseDoneEvent,
    LeaseFailedEvent,
)
PROBLEM_REF = {"$ref": "#/components/schemas/Problem"}
# FastAPI documents its own validation error body, which plumbline.api.problems replaces.
FASTAPI_ERRORS = ("HTTPValidationError", "ValidationError")


def build_openapi(app: FastAPI) -> dict[str, Any]:
    schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        routes=app.routes,
    )
    _, defs = models_json_schema(
        [(model, "serialization") for model in (*STREAM_MODELS, Problem)],
        ref_template="#/components/schemas/{model}",
    )
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, definition in defs.get("$defs", {}).items():
        components.setdefault(name, definition)
    _problems_everywhere(schema)
    add_examples(schema)
    for name in FASTAPI_ERRORS:
        components.pop(name, None)
    return schema


def _problems_everywhere(schema: dict[str, Any]) -> None:
    """Every operation answers its errors as problem details (plumbline.api.problems)."""
    content = {MEDIA_TYPE: {"schema": PROBLEM_REF}}
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            responses = operation.setdefault("responses", {})
            if "422" in responses:  # FastAPI's own text is replaced; a route's own is kept
                own = responses["422"].get("description", "")
                responses["422"] = {
                    "description": own
                    if own != "Validation Error"
                    else "The request is not valid.",
                    "content": content,
                }
            responses["default"] = {
                "description": "An error, as problem details (RFC 9457).",
                "content": content,
            }


def render(app: FastAPI) -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    from plumbline.api.app import create_app
    from plumbline.settings import Settings

    parser = argparse.ArgumentParser(description="Print or check the OpenAPI schema.")
    parser.add_argument("--check", type=Path, help="fail when this file differs from the schema")
    args = parser.parse_args(argv)
    text = render(create_app(Settings(_env_file=None)))
    if args.check is None:
        sys.stdout.write(text)
        return 0
    if args.check.read_text(encoding="utf-8") != text:
        print(f"{args.check} is stale: run make openapi", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
