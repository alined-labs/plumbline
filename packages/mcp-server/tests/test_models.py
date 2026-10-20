"""The package's models against the API's schema: same fields, so a change to a payload in
the API fails here before a published server misreads it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from plumbline_mcp import models

OPENAPI = Path(__file__).resolve().parents[2] / "ts-client" / "openapi.json"
MIRRORED = [
    models.ArticleRef,
    models.SourceLink,
    models.LawHit,
    models.LawSearch,
    models.Span,
    models.PublishedArticle,
    models.ChunkArticle,
    models.Citation,
    models.Finding,
    models.ClauseResult,
]


@pytest.mark.parametrize("model", MIRRORED, ids=lambda m: m.__name__)
def test_each_model_has_the_apis_fields(model: type[BaseModel]) -> None:
    schemas = json.loads(OPENAPI.read_text())["components"]["schemas"]
    api = schemas[model.__name__]
    assert set(model.model_fields) == set(api["properties"])
    # A field the API always sends is one the model requires or defaults.
    assert set(api.get("required", [])) <= set(model.model_fields)


def test_the_examples_parse() -> None:
    paths = json.loads(OPENAPI.read_text())["paths"]
    for path, method, model in (
        ("/api/law/search", "get", models.LawSearch),
        ("/api/chunks/{chunk_id}", "get", models.ChunkArticle),
        ("/api/law/check-clause", "post", models.ClauseResult),
    ):
        content = paths[path][method]["responses"]["200"]["content"]["application/json"]
        for example in content["examples"].values():
            model.model_validate(example["value"])
