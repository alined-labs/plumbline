"""Every error is problem details (RFC 9457), and the schema says so."""

from __future__ import annotations

from collections.abc import Iterator
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from plumbline.api.app import create_app
from plumbline.api.problems import ApiError
from plumbline.core.types import CacheMode
from plumbline.settings import Settings

PROBLEM = "application/problem+json"


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, cache_mode=CacheMode.REPLAY, admin_token=SecretStr("t" * 16)
    )
    app = create_app(settings)

    @app.get("/api/test-boom")
    def boom() -> None:
        raise RuntimeError("secret internals: /srv/plumbline/config")

    @app.get("/api/test-coded")
    def coded() -> None:
        raise ApiError(429, "quota_reached", "Come back tomorrow.", headers={"Retry-After": "30"})

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_an_unknown_route_is_a_404_problem(client: TestClient) -> None:
    response = client.get("/api/nowhere")
    assert response.headers["content-type"] == PROBLEM
    assert response.json() == {"type": "about:blank", "title": "Not Found", "status": 404}


def test_an_invalid_body_lists_each_field(client: TestClient) -> None:
    response = client.post("/api/ask", json={"messages": []})
    body = response.json()
    assert (response.status_code, response.headers["content-type"]) == (422, PROBLEM)
    assert (body["title"], body["detail"]) == (HTTPStatus(422).phrase, "The request is not valid.")
    assert body["errors"][0]["loc"] == ["body", "messages"]


def test_a_routes_own_detail_and_headers_survive(client: TestClient) -> None:
    response = client.get("/api/admin/jobs")
    assert response.json()["detail"] == "A valid admin token is required."
    assert response.headers["www-authenticate"] == "Bearer"


def test_an_unexpected_error_says_nothing_about_internals(client: TestClient) -> None:
    response = client.get("/api/test-boom")
    assert (response.status_code, response.headers["content-type"]) == (500, PROBLEM)
    assert "internals" not in response.text
    assert response.json()["detail"] == "Something went wrong on our side. Please try again."


def test_the_schema_documents_problems_on_every_operation(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            default = operation["responses"]["default"]["content"]
            assert default == {PROBLEM: {"schema": {"$ref": "#/components/schemas/Problem"}}}, (
                f"{method} {path}"
            )
    assert "HTTPValidationError" not in schema["components"]["schemas"]


def test_a_coded_error_carries_its_code_and_headers(client: TestClient) -> None:
    response = client.get("/api/test-coded")
    assert (response.status_code, response.headers["content-type"]) == (429, PROBLEM)
    assert response.headers["retry-after"] == "30"
    assert response.json() == {
        "type": "about:blank",
        "title": "Too Many Requests",
        "status": 429,
        "detail": "Come back tomorrow.",
        "code": "quota_reached",
    }


def test_an_error_without_a_code_has_none(client: TestClient) -> None:
    assert "code" not in client.get("/api/nowhere").json()
    assert "code" not in client.get("/api/admin/jobs").json()


def test_the_schema_lists_the_codes(client: TestClient) -> None:
    schemas = client.get("/api/openapi.json").json()["components"]["schemas"]
    code = schemas["Problem"]["properties"]["code"]
    listed = {
        value
        for branch in code["anyOf"]
        for value in [*branch.get("enum", []), *([branch["const"]] if "const" in branch else [])]
    }
    assert listed == {
        "quota_reached",
        "unsupported_type",
        "too_large",
        "unreadable",
        "not_found",
        "lease_checks_paused",
        "busy",
        "redaction_refused",
        "law_not_indexed",
    }
