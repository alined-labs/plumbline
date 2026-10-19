"""Check that every relative link in the repository's Markdown resolves to a file or a
folder (anchors are not checked). Standard library only: `make check-docs`."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SKIP = ("http://", "https://", "mailto:", "#", "computer://")


def markdown_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],  # noqa: S607 - git from PATH
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / line for line in out.splitlines() if line]


def broken_links(path: Path) -> list[str]:
    problems = []
    in_code = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        for target in LINK.findall(line):
            if target.startswith(SKIP):
                continue
            file_part = target.split("#", 1)[0]
            if file_part and not (path.parent / file_part).exists():
                problems.append(f"{path.relative_to(ROOT)}:{number}: {target}")
    return problems


def main() -> int:
    problems = [p for f in markdown_files() for p in broken_links(f)]
    for problem in problems:
        print(f"broken link: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("docs ok: every relative link resolves")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
