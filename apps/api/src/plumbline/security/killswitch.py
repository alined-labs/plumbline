"""The kill switch: the daily spend counters take the demo tier down the ladder before the
money runs out, and bring it back the next UTC day (ADR-0011).

The public site answers and checks leases on Claude whatever the tier (api/answering.py's
SERVED_ROUTE), and production's one Gemini key is on a billed project (ADR-0007), so the
free tier still spends on both: it only stops lease checks and the premium route. Only the
static tier stops all spending. Hence the same two steps for each provider with a cap:

- free, once it has spent FREE_AT of its daily cap: lease checks stop while ordinary
  questions still get answers;
- static, once it has spent its whole cap: no model is called until the next UTC day.

Claude's spend on answers and lease checks reaches these counters through the API's
MeteredClient, and the API also refuses a live answer itself once Anthropic's cap is
spent, so the cap holds between two checks.

The switch only lowers the tier during a day. When it lowers it, it remembers the tier it
replaced; on a later UTC day, with the counters back under the thresholds, it restores
that tier, unless someone has set the tier by hand since (then the hand wins). It reads the
same Redis counters as the router's MeteredClient and writes the tier through the same
settings row as the admin route, which every API worker rereads within ten seconds.

Run as its own service (deploy/compose.prod.yaml):

    python -m plumbline.security.killswitch            # check every 30 s
    python -m plumbline.security.killswitch --once     # one check, then exit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final, Protocol

from redis.asyncio import Redis

from plumbline.core.types import DemoTier
from plumbline.generation.router import SpendMeter, utc_today

log = logging.getLogger("plumbline.killswitch")

FREE_AT: Final = 0.8  # share of Gemini's daily cap at which the tier drops to free
LADDER: Final = (DemoTier.FULL, DemoTier.FREE, DemoTier.STATIC)  # from most to least spend
MARK_KEY: Final = "killswitch:lowered"
INTERVAL_S: Final = 30.0


class TierSwitch(Protocol):
    """The demo tier's store (api.tier.TierStore has this shape)."""

    async def current(self) -> DemoTier: ...

    async def set(self, tier: DemoTier) -> object: ...


class Marks(Protocol):
    """Where the switch remembers what it lowered: one small JSON value."""

    async def get(self) -> str | None: ...

    async def put(self, value: str) -> None: ...

    async def clear(self) -> None: ...


@dataclass(frozen=True)
class Lowered:
    previous: DemoTier  # the tier the switch replaced
    to: DemoTier  # the tier it set
    on: date  # the UTC day it did

    def dump(self) -> str:
        return json.dumps({"previous": self.previous, "to": self.to, "on": self.on.isoformat()})

    @classmethod
    def load(cls, raw: str) -> Lowered:
        data = json.loads(raw)
        return cls(DemoTier(data["previous"]), DemoTier(data["to"]), date.fromisoformat(data["on"]))


def ceiling(spending: Mapping[str, float], caps: Mapping[str, float]) -> DemoTier:
    """The highest tier today's spend still allows: static once any provider has spent its
    cap, free once any has spent FREE_AT of it. A provider with no cap or a cap of 0 is
    off, so its spend is not looked at (the router never routes to it)."""
    tier = DemoTier.FULL
    for provider in ("gemini", "anthropic"):
        cap, spent = caps.get(provider, 0.0), spending.get(provider, 0.0)
        if cap > 0 and spent >= cap:
            return DemoTier.STATIC
        if cap > 0 and spent >= FREE_AT * cap:
            tier = DemoTier.FREE
    return tier


def lower(a: DemoTier, b: DemoTier) -> DemoTier:
    return max(a, b, key=LADDER.index)


class KillSwitch:
    def __init__(
        self,
        meter: SpendMeter,
        caps: Mapping[str, float],
        tiers: TierSwitch,
        marks: Marks,
        today: Callable[[], date] = utc_today,
    ) -> None:
        self.meter, self.caps, self.tiers, self.marks, self.today = meter, caps, tiers, marks, today

    async def check(self) -> DemoTier:
        """One check: lower the tier if today's spend calls for it, or restore yesterday's
        lowering once the counters have reset. Returns the tier it leaves in place."""
        spent = {p: await self.meter.spent_today(p) for p in ("gemini", "anthropic")}
        allowed = ceiling(spent, self.caps)
        current = await self.tiers.current()
        raw = await self.marks.get()
        mark = Lowered.load(raw) if raw else None

        if mark is not None and current is not mark.to:
            # Someone set the tier by hand after the switch lowered it: theirs stands.
            await self.marks.clear()
            mark = None
        if mark is not None and mark.on < self.today():
            restored = lower(mark.previous, allowed)
            if restored is not current:
                await self.tiers.set(restored)
                log.warning("kill switch: a new UTC day, tier %s restored to %s", current, restored)
            await self.marks.clear()
            current = restored
            if restored is not mark.previous:  # still over a threshold: remember what to restore
                await self.marks.put(Lowered(mark.previous, restored, self.today()).dump())
            return current

        target = lower(current, allowed)
        if target is not current:
            await self.tiers.set(target)
            previous = mark.previous if mark is not None else current
            await self.marks.put(Lowered(previous, target, self.today()).dump())
            log.warning(
                "kill switch: spend today %s against caps %s, tier %s lowered to %s",
                {p: round(v, 4) for p, v in spent.items()},
                dict(self.caps),
                current,
                target,
            )
        return target


class RedisMarks:
    def __init__(self, redis: Redis, key: str = MARK_KEY) -> None:
        self.redis, self.key = redis, key

    async def get(self) -> str | None:
        value = await self.redis.get(self.key)
        return value.decode() if isinstance(value, bytes) else value

    async def put(self, value: str) -> None:
        await self.redis.set(self.key, value)

    async def clear(self) -> None:
        await self.redis.delete(self.key)


async def run(once: bool, interval: float = INTERVAL_S) -> None:
    # Imported here: the service wiring, which the unit tests replace with fakes.
    from plumbline.api.tier import TierStore
    from plumbline.db import make_engine, make_sessionmaker
    from plumbline.generation.router import RedisSpendMeter
    from plumbline.settings import get_settings

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    engine = make_engine(settings.database_url)
    caps = {
        "gemini": settings.gemini_daily_cap_usd,
        "anthropic": settings.anthropic_daily_cap_usd,
    }
    switch = KillSwitch(
        RedisSpendMeter(redis),
        caps,
        # A TTL of 0: the switch always reads the tier as it is now.
        TierStore(make_sessionmaker(engine), settings.demo_tier, clock=_never_cached()),
        RedisMarks(redis),
    )
    log.info("kill switch: watching the spend counters, caps %s", caps)
    try:
        while True:
            try:
                await switch.check()
            except Exception:  # keep watching: a failed check must not end the watch
                log.exception("kill switch: the check failed")
                if once:
                    raise
            if once:
                return
            await asyncio.sleep(interval)
    finally:
        await redis.aclose()
        await engine.dispose()


def _never_cached() -> Callable[[], float]:
    """A clock that jumps an hour on every reading, so TierStore's cache never applies."""
    ticks = iter(range(0, 10**12, 3600))
    return lambda: float(next(ticks))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m plumbline.security.killswitch")
    parser.add_argument("--once", action="store_true", help="check once, then exit")
    parser.add_argument("--interval", type=float, default=INTERVAL_S, help="seconds between checks")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run(args.once, args.interval))


if __name__ == "__main__":
    main()
