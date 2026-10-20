"""The results tables, built from committed results files and nothing else.

    python -m plumbline.eval.report --split dev --default A2

Reads evals/results/<config>/<split>.json (EvalRun files) and writes
evals/results/report-<split>.json, which /evals and the README read, and
evals/results/tables-<split>.md, the README's tables as docs/results-table.md designs them:

- a cell is the mean over the items where the metric applies, as a percentage, with its
  95% interval: `71 (62–79)`, from rag_eval.metrics.summarize (Wilson for proportions,
  a seeded percentile bootstrap for means of fractions);
- a difference is paired over the items both systems were scored on: a paired bootstrap
  of the mean difference, in points, and for 0-or-1 metrics the exact McNemar p-value
  beside it. It counts as an effect only when its interval excludes zero and it is at
  least 5 points; anything else is reported as noise;
- a slice by jurisdiction counts a cross-jurisdiction item under each jurisdiction it
  names, and is descriptive.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from plumbline.corpus.split import assign_splits
from plumbline.settings import ROOT
from rag_eval.metrics import (
    ABSTENTION,
    CITATION_PRECISION,
    FALSE_ABSTENTION,
    PROPORTIONS,
    RECALL_5,
    summarize,
)
from rag_eval.schema import EvalResult, EvalRun, GoldenItem, load_golden
from rag_eval.stats import mcnemar_exact, paired_bootstrap

RESULTS: Final = ROOT / "evals" / "results"
CORRECTNESS: Final = "correctness"  # the judge's verdict (rag_eval.metrics.JUDGED)
EFFECT: Final = 0.05  # differences under 5 points are reported as noise
# Table 1's rows, in order: (metric, label, higher is better).
HEADLINE: Final = (
    (CORRECTNESS, "Answer correct (judged)", True),
    (RECALL_5, "Recall@5 (articles)", True),
    (CITATION_PRECISION, "Citation precision", True),
    (ABSTENTION, "Abstains when out of scope", True),
    (FALSE_ABSTENTION, "Abstains when answerable (lower is better)", False),
)
COMPARED: Final = (CORRECTNESS, RECALL_5, CITATION_PRECISION, ABSTENTION)
SLICED: Final = (CORRECTNESS, RECALL_5, CITATION_PRECISION)
DRAFT_NOTE: Final = "draft golden file"


@dataclass(frozen=True)
class Cell:
    mean: float | None
    low: float | None
    high: float | None
    n: int

    def text(self) -> str:
        if self.mean is None or self.low is None or self.high is None:
            return "—"
        return f"{100 * self.mean:.0f} ({100 * self.low:.0f}–{100 * self.high:.0f})"


@dataclass(frozen=True)
class Difference:
    metric: str
    mean: float
    low: float
    high: float
    n: int
    p_value: float | None  # exact McNemar, for 0-or-1 metrics

    @property
    def effect(self) -> bool:
        return (self.low > 0 or self.high < 0) and abs(self.mean) >= EFFECT

    def text(self) -> str:
        cell = f"{100 * self.mean:+.0f} ({100 * self.low:+.0f} to {100 * self.high:+.0f})"
        if self.p_value is not None:
            cell += f", p = {self.p_value:.2f}"
        return cell if self.effect else f"{cell}, noise"


def cell(results: Sequence[EvalResult], metric: str) -> Cell:
    summary = summarize(results)
    if metric not in summary:
        return Cell(None, None, None, 0)
    n = summary.get(f"{metric}.n") or 0.0
    return Cell(summary[metric], summary[f"{metric}.low"], summary[f"{metric}.high"], int(n))


def difference(a: EvalRun, b: EvalRun, metric: str) -> Difference | None:
    """b minus a, over the items both were scored on."""
    first = {r.item_id: r.metrics.get(metric) for r in a.results}
    pairs = [
        (x, y)
        for r in b.results
        if (y := r.metrics.get(metric)) is not None and (x := first.get(r.item_id)) is not None
    ]
    if not pairs:
        return None
    xs, ys = [x for x, _ in pairs], [y for _, y in pairs]
    boot = paired_bootstrap(xs, ys)
    p = (
        mcnemar_exact([x == 1.0 for x in xs], [y == 1.0 for y in ys]).p_value
        if metric in PROPORTIONS or metric == CORRECTNESS
        else None
    )
    return Difference(metric, boot.mean, boot.low, boot.high, boot.n, p)


def slices(run: EvalRun, items: Mapping[str, GoldenItem]) -> dict[str, list[EvalResult]]:
    """Results by each jurisdiction an item names, and by the language of its sources."""
    out: dict[str, list[EvalResult]] = {}
    for result in run.results:
        item = items[result.item_id]
        for jurisdiction in item.jurisdictions:
            out.setdefault(jurisdiction.value, []).append(result)
        out.setdefault(f"{item.source_language.value}-sources", []).append(result)
    return out


def load_runs(split: str, results: Path = RESULTS) -> dict[str, EvalRun]:
    runs = {}
    for path in sorted(results.glob(f"*/{split}.json")):
        run = EvalRun.model_validate_json(path.read_text())
        runs[run.config_name] = run
    return runs


def golden_items(run: EvalRun) -> dict[str, GoldenItem]:
    items = load_golden(ROOT / run.golden_file)
    if run.notes and DRAFT_NOTE in run.notes:
        items = assign_splits(items, len(items) // 3)
    return {item.id: item for item in items}


def build(
    runs: Mapping[str, EvalRun], *, default: str, naive: str, long_context: str
) -> dict[str, object]:
    """The report: headline cells per configuration, paired differences of the default
    against both baselines, and the default's slices."""
    report: dict[str, object] = {
        "configs": {
            name: {
                "config_hash": run.config_hash,
                "git_sha": run.git_sha,
                "golden_file": run.golden_file,
                "golden_sha256": run.golden_sha256,
                "judged": run.judged,
                "n_items": run.n_items,
                "notes": run.notes,
                "cells": {m: asdict(cell(run.results, m)) for m, _, _ in HEADLINE},
            }
            for name, run in runs.items()
        }
    }
    if default in runs:
        report["differences"] = {
            base: {
                m: asdict(d) | {"effect": d.effect}
                for m in COMPARED
                if (d := difference(runs[base], runs[default], m)) is not None
            }
            for base in (naive, long_context)
            if base in runs
        }
        items = golden_items(runs[default])
        report["slices"] = {
            name: {m: asdict(cell(results, m)) for m in SLICED}
            for name, results in sorted(slices(runs[default], items).items())
        }
    return report


def markdown(
    runs: Mapping[str, EvalRun], *, default: str, naive: str, long_context: str, split: str
) -> str:
    names = [(naive, "Naive RAG"), (long_context, "Long context"), (default, "Plumbline")]
    present = [(c, label) for c, label in names if c in runs]
    lines = [
        f"<!-- Generated by python -m plumbline.eval.report --split {split}; do not edit. -->",
        "",
        "| Metric, 95% interval | " + " | ".join(f"{label} ({c})" for c, label in present) + " |",
        "| --- |" + " --- |" * len(present),
    ]
    for metric, label, _ in HEADLINE:
        cells = [cell(runs[c].results, metric).text() for c, _ in present]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    if default in runs:
        lines += [
            "",
            f"| {default} minus | " + " | ".join(COMPARED) + " |",
            "| --- |" + " --- |" * len(COMPARED),
        ]
        for base in (naive, long_context):
            if base in runs:
                diffs = [difference(runs[base], runs[default], m) for m in COMPARED]
                lines.append(
                    f"| {base} | " + " | ".join(d.text() if d else "—" for d in diffs) + " |"
                )
    lines += [
        "",
        "Each cell is a percentage with its 95% interval; a difference is in points, paired, and marked noise unless its interval excludes zero and it is at least 5 points.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None, *, results: Path = RESULTS) -> int:
    parser = argparse.ArgumentParser(
        prog="plumbline.eval.report", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--split", default="dev", choices=["dev", "test"])
    parser.add_argument("--default", default="A2", help="the configuration Plumbline answers with")
    parser.add_argument("--naive", default="A0")
    parser.add_argument("--long-context", default="LC")
    args = parser.parse_args(argv)
    runs = load_runs(args.split, results)
    if not runs:
        print(f"no results files for {args.split} under {results}")
        return 2
    kwargs = {"default": args.default, "naive": args.naive, "long_context": args.long_context}
    report = build(runs, **kwargs)
    (results / f"report-{args.split}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (results / f"tables-{args.split}.md").write_text(markdown(runs, split=args.split, **kwargs))
    print(f"report-{args.split}.json and tables-{args.split}.md: {', '.join(sorted(runs))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
