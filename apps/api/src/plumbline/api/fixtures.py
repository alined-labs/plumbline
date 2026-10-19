"""Contract fixtures the front end tests against: the exact bytes /api/ask streams for a
fixed question from the stub pipeline. `make openapi` writes them beside the schema, and
a test fails when they drift.

    uv run python -m plumbline.api.fixtures > packages/ts-client/fixtures/ask-stub.sse
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from plumbline.api.stream import ui_message_stream
from plumbline.core.stream import Question
from plumbline.generation.stub import StubPipeline

QUESTION = "Can my landlord keep my deposit?"


async def _render() -> str:
    question = Question(text=QUESTION, request_id="req_fixture")
    stream = ui_message_stream(StubPipeline(delay_ms=0).stream(question), message_id="msg_fixture")
    return "".join([part async for part in stream])


def stub_stream() -> str:
    return asyncio.run(_render())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print or check the stub stream fixture.")
    parser.add_argument("--check", type=Path, help="fail when this file differs")
    args = parser.parse_args(argv)
    text = stub_stream()
    if args.check is None:
        sys.stdout.write(text)
        return 0
    if args.check.read_text(encoding="utf-8") != text:
        print(f"{args.check} is stale: run make openapi", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
