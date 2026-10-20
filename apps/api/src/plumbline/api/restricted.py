"""What the public API may show of a source whose terms forbid republishing it (Lane D).

The fetch-only sources are the Dubai Legislation Portal's laws and the Dubai Land
Department's guide ("personal use or research only, no redistribution") and the Senado's
annotated compilations (the editor's notes are protected). Whether a public demo may show
even a short span of the Dubai texts is open until the publisher's consent is sought
(DATA_LICENSES.md), so until then the routes that serve the text of a source show no more
of these than the passage a citation quotes: no whole article, no heading, no editor's
note and no page image. A source outside the manifest is treated the same way.

When consent exists, flip SHOW_IN_FULL and say so in DATA_LICENSES.md.
"""

from __future__ import annotations

from typing import Final

from plumbline.corpus.manifest import Source

SHOW_IN_FULL: Final = False


def is_restricted(source: Source | None) -> bool:
    """True when the API must show no more of `source` than the passage a citation quotes."""
    return source is None or not (source.committed or SHOW_IN_FULL)
