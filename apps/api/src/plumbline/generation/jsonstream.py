"""One string field of a JSON object, decoded while the model is still writing the object.

Structured output arrives as JSON text in pieces, and the reader should see the answer as
it is written, not when the object closes. `FieldStream` follows the JSON's structure, so a
key inside a nested object, or text that merely looks like a key inside another string,
never matches. It finds the top-level key it was given wherever the provider puts it, and
decodes that string's characters, escapes included, as they arrive. What it emits joins to
exactly what json.loads gives for the field; the complete object is still parsed and
validated at the end, so this is only ever a preview of text that is checked later.
"""

from __future__ import annotations

import json


class FieldStream:
    def __init__(self, field: str) -> None:
        self.field = field
        self.done = False  # the field's closing quote has been read
        self._pending = ""  # an escape sequence cut off at the end of a piece
        self._depth = 0  # 1 inside the top-level object
        self._in_string = False
        self._expect_key = False  # the next string at depth 1 is a key
        self._key: list[str] | None = None  # the raw text of the key being read
        self._last_key: str | None = None
        self._in_field = False

    def feed(self, piece: str) -> str:
        """The field's text decoded from this piece: empty when the piece holds none."""
        text, self._pending = self._pending + piece, ""
        out: list[str] = []
        i = 0
        while i < len(text):
            char = text[i]
            if not self._in_string:
                self._structure(char)
                i += 1
            elif char == "\\":
                length = _escape_length(text, i)
                if length is None:  # the rest of the escape is in the next piece
                    self._pending = text[i:]
                    break
                self._string_part(text[i : i + length], out)
                i += length
            elif char == '"':
                self._close_string()
                i += 1
            else:
                self._string_part(char, out)
                i += 1
        return "".join(out)

    def _structure(self, char: str) -> None:
        if char == '"':
            self._in_string = True
            if self._depth == 1 and self._expect_key:
                self._key, self._expect_key = [], False
            elif self._depth == 1 and self._last_key == self.field and not self.done:
                self._in_field = True
        elif char in "{[":
            self._depth += 1
            self._expect_key = char == "{" and self._depth == 1
        elif char in "}]":
            self._depth -= 1
        elif char == "," and self._depth == 1:
            self._expect_key, self._last_key = True, None

    def _string_part(self, part: str, out: list[str]) -> None:
        if self._key is not None:
            self._key.append(part)
        elif self._in_field:
            out.append(part if len(part) == 1 else json.loads(f'"{part}"'))

    def _close_string(self) -> None:
        self._in_string = False
        if self._key is not None:
            self._last_key, self._key = json.loads('"' + "".join(self._key) + '"'), None
        elif self._in_field:
            self._in_field, self.done = False, True


def _escape_length(text: str, i: int) -> int | None:
    """The length of the escape sequence at text[i], or None if it runs past the end. A
    \\u escape of a high surrogate takes its low surrogate along, so the pair decodes as
    one character."""
    if i + 1 >= len(text):
        return None
    if text[i + 1] != "u":
        return 2
    if i + 6 > len(text):
        return None
    if not 0xD800 <= int(text[i + 2 : i + 6], 16) <= 0xDBFF:
        return 6
    if i + 8 > len(text):
        return None
    if text[i + 6 : i + 8] != "\\u":
        return 6  # a lone high surrogate, which json.loads also accepts
    return 12 if i + 12 <= len(text) else None
