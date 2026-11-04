"""One router per module, each registered at start-up (api/app.py's ROUTERS): a module
whose router is left out would serve nothing, and nothing else would notice."""

from __future__ import annotations

import importlib
import pkgutil

from fastapi import APIRouter

import plumbline.api
from plumbline.api.app import ROUTERS


def test_every_module_router_is_registered() -> None:
    found: dict[str, APIRouter] = {}
    for info in pkgutil.iter_modules(plumbline.api.__path__):
        module = importlib.import_module(f"plumbline.api.{info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            found[info.name] = router
    assert found, "no module routers found"
    registered = {id(router) for router in ROUTERS}
    missing = sorted(name for name, router in found.items() if id(router) not in registered)
    assert missing == []
    assert len(registered) == len(ROUTERS) == len(found)  # each once, and nothing else
