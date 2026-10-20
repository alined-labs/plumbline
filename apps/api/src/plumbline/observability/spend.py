"""What the recordings cost: the spend in cache/ and in the fetched cache, per provider and
model, and the check every lane runs before a paid run.

    uv run python -m plumbline.observability.spend
    uv run python -m plumbline.observability.spend --plan 0.40   # exit 1 if it would cross

Each recording carries the cost_usd its client computed when it was made, so the tally is
a sum of files, not a re-pricing (a Batch API recording must carry its own, halved,
price). A recording found in two folders (a checkout's cache/ and a copy of it) counts once, by
its key. Only this machine's folders are read: another machine's unpushed recordings are
invisible here, which is why every done entry also states what its recordings cost.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from plumbline.ingest.processed import local_cache
from plumbline.settings import get_settings

# The Gemini budget: US$4.73 was left on 2026-10-20 with no top-up coming, and the lanes
# together stop at US$4.50 recorded, keeping the rest for what the tally cannot see.
GEMINI_STOP_USD: Final = 4.50

# Local models (TEI, docling-serve) cost nothing; their recordings still count as calls.
_PREFIXES: Final = (("gemini", "gemini"), ("claude", "anthropic"), ("gpt", "openai"))


@dataclass(frozen=True)
class Recording:
    key: str
    kind: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class Line:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, recording: Recording) -> None:
        self.calls += 1
        self.input_tokens += recording.input_tokens
        self.output_tokens += recording.output_tokens
        self.cost_usd += recording.cost_usd


def provider_of(model: str, request: object) -> str:
    """The request's own provider field (LLM recordings have one), else the model's family."""
    if isinstance(request, dict) and isinstance(request.get("provider"), str):
        return str(request["provider"])
    for prefix, provider in _PREFIXES:
        if model.startswith(prefix):
            return provider
    return "local"


def read(path: Path) -> Recording | None:
    """One recording's metadata; None for a file that is not one. Never the text."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or "key" not in raw:
        return None
    model = str(raw.get("model", ""))
    return Recording(
        key=str(raw["key"]),
        kind=str(raw.get("kind", "")),
        provider=provider_of(model, raw.get("request")),
        model=model,
        input_tokens=int(raw.get("input_tokens", 0)),
        output_tokens=int(raw.get("output_tokens", 0)),
        cost_usd=float(raw.get("cost_usd", 0.0)),
    )


def scan(directories: Iterable[Path]) -> list[Recording]:
    """Every recording under these folders, each key once. A missing folder is empty."""
    seen: dict[str, Recording] = {}
    for directory in directories:
        for path in sorted(directory.glob("*/*/*.json")):
            recording = read(path)
            if recording is not None:
                seen.setdefault(recording.key, recording)
    return list(seen.values())


def tally(recordings: Iterable[Recording]) -> dict[tuple[str, str], Line]:
    """One line per (provider, model), sorted."""
    lines: dict[tuple[str, str], Line] = {}
    for recording in recordings:
        lines.setdefault((recording.provider, recording.model), Line()).add(recording)
    return dict(sorted(lines.items()))


def spent(lines: dict[tuple[str, str], Line], provider: str) -> float:
    return sum(line.cost_usd for (p, _), line in lines.items() if p == provider)


def render(lines: dict[tuple[str, str], Line]) -> str:
    rows = [
        f"{'provider':<10} {'model':<28} {'calls':>6} {'in tok':>11} {'out tok':>10} {'USD':>9}"
    ]
    for (provider, model), line in lines.items():
        rows.append(
            f"{provider:<10} {model:<28} {line.calls:>6} {line.input_tokens:>11,} "
            f"{line.output_tokens:>10,} {line.cost_usd:>9.4f}"
        )
    rows.extend(
        f"{provider + ' total':<39} {'':>6} {'':>11} {'':>10} {spent(lines, provider):>9.4f}"
        for provider in sorted({p for p, _ in lines})
    )
    return "\n".join(rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plumbline.observability.spend",
        description="Sum the recorded spend per provider and model; check a run against the stop.",
    )
    parser.add_argument(
        "--dir",
        action="append",
        type=Path,
        metavar="PATH",
        help="a recordings folder to read (repeatable); default: cache/ and the fetched cache",
    )
    parser.add_argument(
        "--plan",
        type=float,
        default=0.0,
        metavar="USD",
        help="the expected cost of the run about to start; exit 1 if it would cross the stop",
    )
    parser.add_argument(
        "--provider", default="gemini", help="the provider the stop applies to (gemini)"
    )
    parser.add_argument(
        "--stop", type=float, default=GEMINI_STOP_USD, metavar="USD", help="the stop (4.50)"
    )
    args = parser.parse_args(argv)
    directories = args.dir or [get_settings().cache_dir, local_cache()]
    lines = tally(scan(directories))
    print(render(lines))
    total = spent(lines, args.provider)
    after = total + args.plan
    print(
        f"\n{args.provider}: US${total:.4f} recorded of the US${args.stop:.2f} stop"
        + (f"; with this run's US${args.plan:.4f}, US${after:.4f}" if args.plan else "")
        + f"; US${args.stop - after:.4f} left"
    )
    if after > args.stop:
        print(f"refused: the run would cross the {args.provider} stop", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
