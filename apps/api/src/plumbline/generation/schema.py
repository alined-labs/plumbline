"""The answer's structured output: the JSON a model returns for one question.

The model writes the answer in English with [n] markers, where n is the number of the
source it relies on, and one citation per cited source: a span copied from that source in
its own language and, when that language is not English, an English gloss. The verifier
checks every quote against its chunk before anything reaches the reader.

`answer_json_schema()` is what the providers enforce while decoding: this model's JSON
Schema made portable across Gemini, Claude and OpenAI's strict mode. It has no $refs,
every object is closed and lists every property as required (nullable where the model
allows None), and numeric and length bounds move into the descriptions, because Claude
rejects them as keywords. Pydantic still enforces those bounds when the response is parsed.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import Field, field_validator

from plumbline.core.types import AnswerStatus, Frozen, Jurisdiction

# Keywords some provider rejects: dropped (labels) or folded into the description (bounds).
_DROPPED: Final = frozenset({"title", "default"})
_BOUNDS: Final = frozenset(
    {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength"}
    | {"minItems", "maxItems", "pattern"}
)


class GeneratedCitation(Frozen):
    n: int = Field(ge=1, description="The source's number, as in the answer's [n] markers.")
    chunk_id: str = Field(min_length=1, description="The id attribute of that source.")
    quote: str = Field(
        min_length=1,
        description="The one sentence or clause that supports the answer, copied exactly "
        "from the source's text in its original language.",
    )
    gloss: str | None = Field(
        description="An English translation of the quote when the source is not in "
        "English; null when it is."
    )


class GeneratedAnswer(Frozen):
    answer: str = Field(
        description="The answer in English, with a [n] marker after each statement of law."
    )
    citations: list[GeneratedCitation] = Field(
        description="One citation for each source the answer cites."
    )
    status: AnswerStatus = Field(
        description="answered, partial (the sources answer only part) or abstained (they "
        "do not answer it, or it is outside the indexed tenancy law)."
    )
    jurisdictions: list[Jurisdiction] = Field(
        description="The jurisdictions whose law the answer relies on."
    )
    confidence: float = Field(
        ge=0, le=1, description="How fully the quoted text supports the answer."
    )
    abstain_reason: str | None = Field(
        description="For partial or abstained: what the sources do not answer, in one "
        "plain English sentence. Null when answered."
    )

    @field_validator("status", "jurisdictions", mode="before")
    @classmethod
    def _lowercase(cls, value: Any) -> Any:
        # Claude documents that enum values may come back in another capitalization.
        if isinstance(value, str):
            return value.lower()
        if isinstance(value, list):
            return [v.lower() if isinstance(v, str) else v for v in value]
        return value


def answer_json_schema() -> dict[str, Any]:
    raw = GeneratedAnswer.model_json_schema()
    return _portable(raw, raw.get("$defs", {}))


def _portable(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:  # inline the definition; the node's own keys (a description) win
        target = defs[node["$ref"].rsplit("/", 1)[-1]]
        return _portable({**target, **{k: v for k, v in node.items() if k != "$ref"}}, defs)
    variants = node.get("anyOf", [])
    nullable = [v for v in variants if v != {"type": "null"}]
    if len(variants) == 2 and len(nullable) == 1 and isinstance(nullable[0].get("type"), str):
        # X | None as a type array, the one nullable form every provider documents.
        rest = {k: v for k, v in node.items() if k != "anyOf"}
        merged = {**nullable[0], **rest, "type": [nullable[0]["type"], "null"]}
        return _portable(merged, defs)
    out: dict[str, Any] = {}
    bounds: list[str] = []
    for key, value in node.items():
        if key in _DROPPED or key == "$defs":
            continue
        if key in _BOUNDS:
            bounds.append(f"{key} {value}")
        elif key == "properties":
            out[key] = {name: _portable(prop, defs) for name, prop in value.items()}
        elif key == "items":
            out[key] = _portable(value, defs)
        elif key == "anyOf":
            out[key] = [_portable(variant, defs) for variant in value]
        else:
            out[key] = value
    if out.get("type") == "object":
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}))
    if bounds:
        out["description"] = f"{out.get('description', '')} ({', '.join(bounds)})".strip()
    return out
