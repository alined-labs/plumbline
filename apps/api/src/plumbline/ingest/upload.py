"""Reading an uploaded lease into text (Lane D, task D7): PDF, DOCX or plain text.

The file is untrusted. Its type comes from its bytes, never from its name or the type the
browser claims. Limits stop a file that is too big, too long or built to inflate (a
DOCX is a zip). A PDF is read from its text layer only: a scan has none, and is refused
with its own code so the page can say so, instead of being sent to a vision model, which
a stranger's lease must not reach unredacted.

Errors carry a stable machine code (`UploadError.code`) that the API's problem details
repeat and the lease page words for the reader.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from typing import Final, Literal

import pypdfium2 as pdfium

from plumbline.ingest.parse import has_text_layer

MAX_BYTES: Final = 10 * 1024 * 1024  # the upload as received
MAX_PAGES: Final = 80  # a lease is a few pages; this is a book
MAX_CHARS: Final = 300_000  # the text we will read, about 100 pages
MAX_XML_BYTES: Final = 30 * 1024 * 1024  # a DOCX's document.xml once inflated
MIN_CHARS: Final = 200  # fewer characters of text than this is not a lease
WORD_NS: Final = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

Code = Literal["unsupported_type", "too_large", "unreadable"]
STATUS: Final[dict[Code, int]] = {"unsupported_type": 415, "too_large": 413, "unreadable": 422}
SUPPORTED: Final = "a PDF, a Word document (DOCX) or plain text"


class UploadError(ValueError):
    def __init__(self, code: Code, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def status(self) -> int:
        return STATUS[self.code]


@dataclass(frozen=True)
class UploadedText:
    text: str
    kind: Literal["pdf", "docx", "text"]
    pages: int | None  # PDF only


def read_upload(data: bytes) -> UploadedText:
    """The lease's text, or an UploadError saying why not."""
    if len(data) > MAX_BYTES:
        raise UploadError("too_large", f"The file is over {MAX_BYTES // (1024 * 1024)} MB.")
    if data.startswith(b"%PDF-"):
        text, pages = _pdf(data)
        return _checked(text, "pdf", pages)
    if data.startswith(b"PK\x03\x04"):
        return _checked(_docx(data), "docx", None)
    return _checked(_plain(data), "text", None)


def _checked(text: str, kind: Literal["pdf", "docx", "text"], pages: int | None) -> UploadedText:
    text = _tidy(text)
    if len(text) > MAX_CHARS:
        raise UploadError("too_large", "The lease is too long to read in one go.")
    if len("".join(text.split())) < MIN_CHARS:
        if kind == "pdf":
            raise UploadError(
                "unreadable",
                "This PDF has no text we can read: it looks like a scan. Upload the original"
                " file, or a text version of the lease.",
            )
        raise UploadError("unreadable", "There is too little text in this file to be a lease.")
    return UploadedText(text, kind, pages)


def _pdf(data: bytes) -> tuple[str, int]:
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:  # corrupt, truncated or password-protected
        raise UploadError("unreadable", "This PDF cannot be opened (is it protected?).") from exc
    try:
        if len(pdf) > MAX_PAGES:
            raise UploadError("too_large", f"The PDF has more than {MAX_PAGES} pages.")
        pages = [pdf[index].get_textpage().get_text_bounded() for index in range(len(pdf))]
        text = "\n\n".join(page.replace("\r\n", "\n").replace("\r", "\n") for page in pages)
        count = len(pages)
    except pdfium.PdfiumError as exc:
        raise UploadError("unreadable", "This PDF cannot be read.") from exc
    finally:
        pdf.close()
    # A scan has pages but no text; one stray character is not a text layer either.
    if not any(has_text_layer(page) for page in pages):
        text = ""
    return text, count


def _docx(data: bytes) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        info = archive.getinfo("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise UploadError("unsupported_type", f"The file is not {SUPPORTED}.") from exc
    # The zip's own sizes can lie, so the inflated stream is read with a cap, not trusted.
    if info.file_size > MAX_XML_BYTES:
        raise UploadError("too_large", "The document is too large to read.")
    with archive.open(info) as stream:
        xml = stream.read(MAX_XML_BYTES + 1)
    if len(xml) > MAX_XML_BYTES:
        raise UploadError("too_large", "The document is too large to read.")
    try:
        root = ET.fromstring(xml)  # noqa: S314 (expat expands no entities recursively)
    except ET.ParseError as exc:
        raise UploadError("unreadable", "This Word document cannot be read.") from exc
    lines = []
    for paragraph in root.iter(f"{WORD_NS}p"):
        parts = []
        for element in paragraph.iter():
            if element.tag == f"{WORD_NS}t" and element.text:
                parts.append(element.text)
            elif element.tag == f"{WORD_NS}tab":
                parts.append("\t")
            elif element.tag in {f"{WORD_NS}br", f"{WORD_NS}cr"}:
                parts.append("\n")
        lines.append("".join(parts))
    return "\n".join(lines)


def _plain(data: bytes) -> str:
    if b"\x00" in data and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise UploadError("unsupported_type", f"The file is not {SUPPORTED}.")
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        if encoding == "utf-16" and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
            continue
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        # cp1252 decodes almost any bytes: the text must still look like text.
        controls = sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t")
        if controls > max(8, len(text) // 100):
            raise UploadError("unsupported_type", f"The file is not {SUPPORTED}.")
        return text
    raise UploadError("unsupported_type", f"The file is not {SUPPORTED}.")


def _tidy(text: str) -> str:
    """Newlines normalized, control characters gone, runs of blank lines folded."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = "".join(char for char in text if char in "\n\t" or ord(char) >= 32)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in text.split("\n"))).strip()
