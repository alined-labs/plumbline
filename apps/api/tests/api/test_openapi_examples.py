"""Every operation of the API carries an example in the OpenAPI schema (api/examples.py),
built from the model the schema names, and the streams' examples are what the encoders
write."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic import BaseModel

from plumbline.api.app import create_app
from plumbline.api.examples import ASK_EVENTS, ASK_MESSAGE_ID, ASK_STREAM, EXAMPLES
from plumbline.api.stream import ui_message_stream
from plumbline.core.stream import StreamEvent
from plumbline.settings import Settings

# What a reader can be shown as text or JSON; an image is described, not exemplified.
SHOWN = ("application/json", "text/event-stream", "text/plain")


def _schema() -> dict[str, Any]:
    return create_app(Settings(_env_file=None)).openapi()


def _operations(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        f"{method.upper()} {path}": operation
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
    }


def test_every_operation_has_an_example_and_every_example_an_operation() -> None:
    assert set(_operations(_schema())) == set(EXAMPLES)


def test_every_body_response_and_parameter_shows_its_example() -> None:
    missing: list[str] = []
    for name, operation in _operations(_schema()).items():
        body = operation.get("requestBody", {}).get("content", {})
        if body and not any("examples" in body[m] for m in SHOWN if m in body):
            missing.append(f"{name}: request body")
        success = sorted(code for code in operation["responses"] if code.startswith("2"))
        for media, content in operation["responses"][success[0]].get("content", {}).items():
            if media in SHOWN and "examples" not in content:
                missing.append(f"{name}: {success[0]} {media}")
        missing += [
            f"{name}: parameter {p['name']}"
            for p in operation.get("parameters", [])
            if "example" not in p
        ]
    assert missing == []


def _ref(schema: dict[str, Any]) -> str | None:
    if "$ref" in schema:
        return str(schema["$ref"]).rsplit("/", 1)[-1]
    if schema.get("type") == "array":
        return _ref(schema["items"])
    return None


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_each_json_example_is_the_model_the_schema_names(name: str) -> None:
    operation = _operations(_schema())[name]
    example = EXAMPLES[name]
    shown: list[tuple[dict[str, Any], object]] = []
    body = operation.get("requestBody", {}).get("content", {}).get("application/json")
    if body is not None:
        shown.append((body["schema"], example.request))
    success = sorted(code for code in operation["responses"] if code.startswith("2"))[0]
    content = operation["responses"][success].get("content", {}).get("application/json")
    if content is not None and "schema" in content:
        shown.append((content["schema"], example.response))
    for schema, value in shown:
        model = value[0] if isinstance(value, list) else value
        assert isinstance(model, BaseModel), f"{name}: a JSON example must be a model"
        assert _ref(schema) == type(model).__name__, name


async def _events() -> AsyncIterator[StreamEvent]:
    for event in ASK_EVENTS:
        yield event


@pytest.mark.anyio
async def test_the_answer_stream_example_is_what_the_encoder_writes() -> None:
    written = "".join(
        [part async for part in ui_message_stream(_events(), message_id=ASK_MESSAGE_ID)]
    )
    assert written == ASK_STREAM
