"""The OpenAPI schema, plus the payloads of the event streams (the answer's data parts and
an ingestion job's events) as components, so the browser's types come from one generated
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

from plumbline.api.schemas import JobEventView
from plumbline.core.stream import AnswerSummary, StatusEvent, StreamError, TraceSummary
from plumbline.core.types import Citation

if TYPE_CHECKING:
    from fastapi import FastAPI

STREAM_MODELS = (StatusEvent, Citation, AnswerSummary, TraceSummary, StreamError, JobEventView)


def build_openapi(app: FastAPI) -> dict[str, Any]:
    schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        routes=app.routes,
    )
    _, defs = models_json_schema(
        [(model, "serialization") for model in STREAM_MODELS],
        ref_template="#/components/schemas/{model}",
    )
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, definition in defs.get("$defs", {}).items():
        components.setdefault(name, definition)
    return schema


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
