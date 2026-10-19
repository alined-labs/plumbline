"""The structured output: a schema every provider accepts, and strict parsing of replies."""

from typing import Any

import pytest
from pydantic import ValidationError

from plumbline.core.types import AnswerStatus, Jurisdiction
from plumbline.generation.schema import GeneratedAnswer, answer_json_schema

REJECTED_BY_SOME_PROVIDER = {
    "$ref",
    "$defs",
    "title",
    "default",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
}
REPLY: dict[str, Any] = {
    "answer": "The deposit is one month's rent [1].",
    "citations": [
        {
            "n": 1,
            "chunk_id": "lau-36-1",
            "quote": "fianza en metálico en cantidad equivalente a una mensualidad de renta",
            "gloss": "a cash deposit equal to one month's rent",
        }
    ],
    "status": "answered",
    "jurisdictions": ["spain"],
    "confidence": 0.9,
    "abstain_reason": None,
}


def nodes(schema: Any) -> list[dict[str, Any]]:
    if isinstance(schema, dict):
        return [schema, *(n for value in schema.values() for n in nodes(value))]
    if isinstance(schema, list):
        return [n for value in schema for n in nodes(value)]
    return []


def test_the_schema_is_portable() -> None:
    every = nodes(answer_json_schema())
    assert not REJECTED_BY_SOME_PROVIDER & {key for node in every for key in node}
    objects = [n for n in every if n.get("type") == "object"]
    assert len(objects) == 2  # the answer and its citations
    for node in objects:
        assert node["additionalProperties"] is False
        assert node["required"] == list(node["properties"])
    properties = answer_json_schema()["properties"]
    assert properties["abstain_reason"]["type"] == ["string", "null"]
    assert "(maximum 1, minimum 0)" in properties["confidence"]["description"]


def test_a_reply_parses_and_enum_case_does_not_matter() -> None:
    parsed = GeneratedAnswer.model_validate(REPLY)
    assert parsed.citations[0].chunk_id == "lau-36-1"
    shouted = GeneratedAnswer.model_validate(
        REPLY | {"status": "Answered", "jurisdictions": ["Spain"]}
    )
    assert shouted.status is AnswerStatus.ANSWERED
    assert shouted.jurisdictions == [Jurisdiction.SPAIN]


@pytest.mark.parametrize(
    "change",
    [
        {"confidence": 1.5},
        {"citations": [REPLY["citations"][0] | {"n": 0}]},
        {"citations": [REPLY["citations"][0] | {"quote": ""}]},
        {"status": "maybe"},
        {"extra": "field"},
    ],
)
def test_a_reply_outside_the_schema_is_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        GeneratedAnswer.model_validate(REPLY | change)
