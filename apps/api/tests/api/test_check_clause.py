"""POST /api/law/check-clause: one clause, under the lease check's rules (tier, budget,
allowance, redaction first), with the lease checker's disclaimer."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from plumbline.api import answering
from plumbline.api.app import create_app
from plumbline.api.lease_stub import StubLeaseChecker
from plumbline.api.leases import LeaseChecker
from plumbline.api.quota import MemoryCounter
from plumbline.core.types import CacheMode, DemoTier, Jurisdiction
from plumbline.corpus.leases import lease_disclaimer
from plumbline.db import make_engine, make_sessionmaker
from plumbline.generation.router import (
    MemorySpendMeter,
    RedactionRefused,
    SyntheticOnlyRedactor,
    Upload,
)
from plumbline.settings import Settings

pytestmark = pytest.mark.anyio
NO_DATABASE = "postgresql+psycopg://nobody@127.0.0.1:1/none"
CLAUSE = "The Landlord will return the security deposit within 45 days after move-out."


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, cache_mode=CacheMode.REPLAY, stub_delay_ms=0, **values)


def _app(checker: LeaseChecker | None = None, **settings: Any) -> FastAPI:
    return create_app(
        _settings(**settings),
        sessions=make_sessionmaker(make_engine(NO_DATABASE)),
        counter=MemoryCounter(),
        lease_checker=checker,
    )


async def _post(app: FastAPI, body: dict[str, Any], times: int = 1) -> list[httpx.Response]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return [await client.post("/api/law/check-clause", json=body) for _ in range(times)]


async def test_a_clause_gets_a_finding_and_the_disclaimer() -> None:
    [response] = await _post(_app(), {"clause": CLAUSE, "jurisdiction": "florida"})
    assert response.status_code == 200
    body = response.json()
    assert body["finding"]["clause_text"] == CLAUSE
    assert body["finding"]["citations"][0]["verified"] is True
    assert body["disclaimer"] == lease_disclaimer()
    assert (body["jurisdiction"], body["as_of"]) == ("florida", None)
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" in response.headers


async def test_bounds_on_the_request() -> None:
    app = _app()
    for body in (
        {"jurisdiction": "florida"},
        {"clause": "", "jurisdiction": "florida"},
        {"clause": "x" * 4001, "jurisdiction": "florida"},
        {"clause": CLAUSE},
        {"clause": CLAUSE, "jurisdiction": "mars"},
    ):
        [response] = await _post(app, body)
        assert response.status_code == 422


async def test_a_clause_counts_as_a_lease_check() -> None:
    app = _app(daily_questions_per_ip=10)  # one lease check a day
    first, second = await _post(app, {"clause": CLAUSE, "jurisdiction": "florida"}, times=2)
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == "quota_reached"


async def test_off_the_full_tier_clauses_are_paused() -> None:
    [response] = await _post(
        _app(demo_tier=DemoTier.FREE), {"clause": CLAUSE, "jurisdiction": "florida"}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "lease_checks_paused"


class _NeverCalled:
    def __call__(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("no model may be called")


def _claude(redactor: Any, client_for_model: Any = None) -> answering.ClaudeLeaseChecker:
    settings = _settings()
    meter = MemorySpendMeter()
    return answering.ClaudeLeaseChecker(
        router=answering.router_for(settings, meter),
        meter=meter,
        redactor=redactor,
        search=None,  # type: ignore[arg-type]  # check_clause is replaced or never reached
        client_for_model=client_for_model or _NeverCalled(),
    )


async def test_an_unredacted_clause_never_reaches_a_model() -> None:
    # Until Presidio's redactor lands, the stand-in refuses every reader's text.
    [response] = await _post(
        _app(_claude(SyntheticOnlyRedactor())), {"clause": CLAUSE, "jurisdiction": "florida"}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "redaction_refused"
    assert CLAUSE not in response.text


async def test_the_claude_checker_checks_the_redacted_clause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Redactor:
        def redact(self, upload: Upload) -> str:
            if "John" in upload.text:
                return upload.text.replace("John Smith", "[NAME]")
            raise RedactionRefused("nothing to say")

    calls: list[dict[str, Any]] = []

    async def check(number: str, text: str, language: Any, **kwargs: Any) -> Any:
        calls.append({"number": number, "text": text, **kwargs})

        class Checked:
            finding = None

        return Checked()

    monkeypatch.setattr(answering, "check_clause", check)
    checker = _claude(
        Redactor(), client_for_model=lambda model, **kw: SimpleNamespace(provider="anthropic")
    )
    route = await checker.route(DemoTier.FULL)
    finding = await checker.clause(
        "John Smith pays the deposit.",
        route,
        jurisdiction=Jurisdiction.SPAIN,
        as_of=date(2026, 1, 2),
    )
    assert finding is None
    [call] = calls
    assert call["text"] == "[NAME] pays the deposit."  # the model reads only the redacted text
    assert (call["jurisdiction"], call["as_of"]) == (Jurisdiction.SPAIN, date(2026, 1, 2))
    assert call["model"].startswith("claude-")


async def test_a_paused_server_pauses_clauses_too() -> None:
    [response] = await _post(
        _app(answering.PausedLeaseChecker()), {"clause": CLAUSE, "jurisdiction": "florida"}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "lease_checks_paused"


def test_the_stub_is_a_lease_checker() -> None:
    checker: LeaseChecker = StubLeaseChecker()
    assert callable(checker.clause)


async def test_a_clause_under_law_the_index_lacks_is_refused() -> None:
    checker = _claude(SyntheticOnlyRedactor())
    checker._indexed = lambda: frozenset({Jurisdiction.FLORIDA, Jurisdiction.SPAIN})
    assert await checker.indexed() == {Jurisdiction.FLORIDA, Jurisdiction.SPAIN}
    [response] = await _post(_app(checker), {"clause": CLAUSE, "jurisdiction": "dubai"})
    assert response.status_code == 503
    assert response.json()["code"] == "law_not_indexed"
    # Indexed law goes on to redaction, which refuses a reader's text until P2.
    [indexed] = await _post(_app(checker), {"clause": CLAUSE, "jurisdiction": "spain"})
    assert indexed.json()["code"] == "redaction_refused"
