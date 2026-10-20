"""How each law is named in a chunk's header and label ("Fla. Stat. ch. 83", "LAU").

Until the corpus manifest carries a short citation name per source (asked of Lane B in the
brain's B8 note), the names live here, keyed by the manifest's `law`. A law without one is
an error, never a guess: its name would be in every header and every citation.
"""

from __future__ import annotations

from typing import Final

LAW_NAMES: Final = {
    "fl-stat-83": "Fla. Stat. ch. 83",
    "fl-stat-718": "Fla. Stat. ch. 718",
    "es-lau": "LAU",
    "es-lph": "LPH",
    "co-ley-820": "Ley 820 de 2003",
    "co-ley-675": "Ley 675 de 2001",
    "dubai-law-26-2007": "Law No. 26 of 2007",
    "dubai-law-33-2008": "Law No. 33 of 2008",
    "dubai-dld-tenancy-guide": "DLD Tenancy Guide",
}


def law_name(law: str) -> str:
    try:
        return LAW_NAMES[law]
    except KeyError:
        raise ValueError(
            f"no short name for law {law!r}: add it to plumbline.ingest.laws"
        ) from None
