"""The site and the API on two hosts (production: plumbline.alinedlabs.co calls
plumbline-api.alinedlabs.co). The browser sends the visitor cookie only on a credentialed
request the API's CORS answer allows, for the site's exact origin; the cookie itself stays
the API host's own."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Response

from plumbline.api.app import create_app
from plumbline.api.quota import COOKIE, MemoryCounter, Visitor, set_visitor_cookie
from plumbline.core.types import CacheMode
from plumbline.db import make_engine, make_sessionmaker
from plumbline.settings import Settings

SITE = "https://plumbline.alinedlabs.co"
NO_DATABASE = "postgresql+psycopg://nobody@127.0.0.1:1/none"

pytestmark = pytest.mark.anyio


def _app() -> FastAPI:
    settings = Settings(_env_file=None, cache_mode=CacheMode.REPLAY, cors_origins=[SITE])
    sessions = make_sessionmaker(make_engine(NO_DATABASE))
    return create_app(settings, sessions=sessions, counter=MemoryCounter())


async def _preflight(origin: str, path: str = "/api/ask") -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.options(
            path,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )


async def test_the_site_may_send_its_cookie_to_the_api() -> None:
    for path in ("/api/ask", "/api/feedback", "/api/check-lease"):
        response = await _preflight(SITE, path)
        assert response.status_code == 200
        # The exact origin, never "*": a browser drops credentials on a wildcard.
        assert response.headers["access-control-allow-origin"] == SITE
        assert response.headers["access-control-allow-credentials"] == "true"
        assert "content-type" in response.headers["access-control-allow-headers"].lower()


async def test_no_other_origin_may() -> None:
    for origin in ("https://evil.example", "http://plumbline.alinedlabs.co", "null"):
        response = await _preflight(origin)
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers


def test_the_production_cookie_is_the_api_hosts_own() -> None:
    response = Response()
    settings = Settings(_env_file=None, environment="prod")
    set_visitor_cookie(response, Visitor(id="v1", cookie="v1.sig"), settings)
    cookie = response.headers["set-cookie"]
    attributes = {part.strip().split("=")[0].lower() for part in cookie.split(";")}
    assert cookie.startswith(f"{COOKIE}=v1.sig")
    assert {"httponly", "secure", "samesite", "path", "max-age"} <= attributes
    # Host-only: no Domain, so no other subdomain of alinedlabs.co receives it. The site and
    # the API share that registrable domain, so Lax still lets the site's fetches carry it.
    assert "domain" not in attributes
    assert "samesite=lax" in cookie.lower()
    assert "path=/api" in cookie.lower()
