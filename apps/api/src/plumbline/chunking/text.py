"""Text helpers shared by both chunkers: the token count, line cleanup, stable ids and the
text that is embedded and indexed."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Literal

from plumbline.core.types import Jurisdiction

Headers = Literal["none", "deterministic", "llm", "both"]

# A token is a run of word characters or one other non-space character. This stands in
# for the embedding model's tokenizer, which would need a download and a dependency: the
# regex runs offline and gives the same count on every machine. It undercounts Qwen3's
# subword tokens; measured on the official texts through TEI's /tokenize (2026-10-19),
# one regex token is 1.06 to 1.22 model tokens in English and 1.50 in Spanish, so an
# 800-token chunk is at most about 1,200 model tokens, far below the server's 4,096 cap.
TOKEN = re.compile(r"\w+|[^\w\s]")


def count_tokens(text: str) -> int:
    return sum(1 for _ in TOKEN.finditer(text))


def clean_line(line: str) -> str:
    """A Markdown line as plain text: quote and heading marks, list bullets, bold marks
    and backslash escapes go, and runs of spaces fold. Strikethrough (~~) stays: in the
    Colombian texts it marks words the Constitutional Court struck down."""
    line = re.sub(r"^(>\s*)+", "", line.strip())  # the BOE's notes arrive as quotes
    line = re.sub(r"^#{1,6}\s+|^[-*+]\s+", "", line)
    line = re.sub(r"\\([\\`*_{}\[\]()<>#+.!|-])", r"\1", line.replace("**", ""))
    return " ".join(line.split())


def chunk_id(source_id: str, path: Sequence[str], text: str) -> str:
    """The same source, place and text give the same id, on any machine and any run."""
    digest = hashlib.sha256("\x1f".join([source_id, *path, text]).encode("utf-8"))
    return f"{source_id}:{digest.hexdigest()[:16]}"


def context_header(
    jurisdiction: Jurisdiction, law_name: str, article: str, heading: str | None
) -> str:
    """The deterministic header: [Jurisdiction | Law | Article | Heading]."""
    parts = [jurisdiction.value.capitalize(), law_name, article, heading or ""]
    return "[" + " | ".join(part for part in parts if part) + "]"


def search_text(text: str, header: str, llm_header: str | None, headers: Headers) -> str:
    """What is embedded and indexed under a configuration's `headers` setting. The LLM
    header is written after chunking (A10), so asking for it before then is an error."""
    if headers == "none":
        return text
    if headers == "deterministic":
        return f"{header}\n{text}"
    if not llm_header:
        raise ValueError(f"headers={headers!r} needs the LLM header, which A10 writes")
    return f"{llm_header}\n{text}" if headers == "llm" else f"{header}\n{llm_header}\n{text}"
