"""Model output is never served or rendered as HTML (AGENTS.md 20: it may carry an attack
planted in a statute page or a lease). The API answers in JSON, server-sent events, problem
details and PNG only; the front end renders answers through react-markdown with raw HTML
skipped, and writes HTML itself in one place, its theme script, which holds no data.
These read the code as it is, so a new route or component that breaks the rule fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.routing import APIRoute

from plumbline.api.app import create_app
from plumbline.settings import ROOT, Settings

WEB = ROOT / "apps" / "web" / "src"
ALLOWED_TYPES = frozenset(
    {"application/json", "application/problem+json", "text/event-stream", "image/png"}
)
# Ways to put a string into the page as markup, in React or the DOM.
SINKS = re.compile(
    r"dangerouslySetInnerHTML|\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML|document\.write"
    r"|createContextualFragment|rehype-raw"
)
# The one place the front end writes markup itself: the theme script, a constant.
ALLOWED_SINKS = {("app/layout.tsx", "dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }}")}


def _sources() -> list[Path]:
    return [
        path
        for path in sorted(WEB.rglob("*.ts*"))
        if not re.search(r"\.(test|spec)\.tsx?$", path.name)
    ]


def test_no_route_answers_in_html() -> None:
    app = create_app(Settings(_env_file=None))
    schema = app.openapi()
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            for status, response in operation.get("responses", {}).items():
                for media_type in response.get("content", {}):
                    assert media_type in ALLOWED_TYPES, (method, path, status, media_type)
    for route in app.routes:
        if isinstance(route, APIRoute):
            assert "html" not in route.response_class.__name__.lower(), route.path


def test_the_front_end_writes_markup_only_in_its_theme_script() -> None:
    found = set()
    for path in _sources():
        for line in path.read_text(encoding="utf-8").splitlines():
            if SINKS.search(line):
                found.add(
                    (
                        path.relative_to(WEB).as_posix(),
                        line.strip().removeprefix("<script ").removesuffix(" />"),
                    )
                )
    assert found <= ALLOWED_SINKS, found - ALLOWED_SINKS


def test_every_markdown_renderer_skips_raw_html() -> None:
    renderers = [p for p in _sources() if 'from "react-markdown"' in p.read_text(encoding="utf-8")]
    assert renderers, "no react-markdown renderer found: update this test"
    for path in renderers:
        source = path.read_text(encoding="utf-8")
        assert "<Markdown" in source, path
        # Each <Markdown ...> element's props, up to its closing ">".
        for props in re.findall(r"<Markdown\b([^>]*)>", source):
            assert re.search(r"\bskipHtml\b", props), path
            assert "allowedElements" in props, path
