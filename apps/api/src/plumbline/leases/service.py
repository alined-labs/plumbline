"""The lease checker as /api/check-lease runs it: the same two methods as the API's
stand-in (api/lease_stub.py), so the route swaps one for the other and nothing else.

`route` asks the shared Router, which refuses lease checks off the full tier (uploads go
only to billed models that do not train on them). `stream` runs the checker on the
route's model through a metered client, so every live call counts against the provider's
daily cap like an answer's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import date

from plumbline.cache import ResponseCache
from plumbline.core.types import DemoTier, Jurisdiction
from plumbline.generation.llm import LLMClient, client_for
from plumbline.generation.pipeline import ChunkSearch
from plumbline.generation.router import (
    Kind,
    MeteredClient,
    Redactor,
    Route,
    Router,
    SpendMeter,
    Upload,
)
from plumbline.leases.checker import LeaseEvent, stream_check


class LeaseChecker:
    def __init__(
        self,
        *,
        router: Router,
        meter: SpendMeter,
        redactor: Redactor,
        search: ChunkSearch,
        cache: ResponseCache | None = None,  # default: the settings' cache
        client_for_model: Callable[..., LLMClient] = client_for,
    ) -> None:
        self.router = router
        self.meter = meter
        self.redactor = redactor
        self.search = search
        self.cache = cache
        self.client_for_model = client_for_model

    async def route(self, tier: DemoTier) -> Route:
        return await self.router.route(Kind.LEASE_CHECK, tier=tier)

    def stream(
        self,
        upload: Upload,
        route: Route,
        *,
        jurisdiction: Jurisdiction | None,
        as_of: date | None,
    ) -> AsyncIterator[LeaseEvent]:
        kwargs = {"cache": self.cache} if self.cache is not None else {}
        client = MeteredClient(self.client_for_model(route.model, **kwargs), self.meter)
        return stream_check(
            upload,
            redactor=self.redactor,
            search=self.search,
            client=client,
            jurisdiction=jurisdiction,
            as_of=as_of,
            model=route.model,
        )
