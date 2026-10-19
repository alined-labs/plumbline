"""The rag-eval command line. Lane A grows it into `rag-eval run`; the seed validates files.

rag-eval validate data/golden/golden_v0.jsonl [...]
rag-eval validate-run evals/results/A2/dev.json [...]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from rag_eval.schema import EvalRun, GoldenFileError, load_golden


def _validate_golden(paths: list[Path]) -> int:
    status = 0
    for path in paths:
        try:
            items = load_golden(path)
        except GoldenFileError as exc:
            print(exc, file=sys.stderr)
            status = 1
            continue
        categories = Counter(item.category.value for item in items)
        splits = Counter(item.split.value for item in items)
        print(f"{path}: {len(items)} items; {dict(sorted(categories.items()))}; {dict(splits)}")
    return status


def _validate_runs(paths: list[Path]) -> int:
    status = 0
    for path in paths:
        try:
            run = EvalRun.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            status = 1
            continue
        print(f"{path}: {run.config_name} on {run.split}, {run.n_items} items")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rag-eval", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    golden = sub.add_parser("validate", help="validate golden-set JSONL files")
    golden.add_argument("paths", nargs="+", type=Path)
    runs = sub.add_parser("validate-run", help="validate results JSON files")
    runs.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate_golden(args.paths)
    return _validate_runs(args.paths)


if __name__ == "__main__":
    raise SystemExit(main())
