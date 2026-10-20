"""The jurisdiction detector: which of the four jurisdictions a question names.

Questions are in English and name places, institutions, laws, currencies and local legal
terms. Each term below is evidence for one jurisdiction, or for two when both use it
(Spain and Colombia share most Spanish legal vocabulary). A question that names none gets
all four: retrieval then searches everything rather than filter out the right law
because a question was vague. Extra jurisdictions cost precision only; a missing one
would hide the answer, so terms err towards matching.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

from plumbline.core.types import Jurisdiction

DUBAI, SPAIN, COLOMBIA, FLORIDA = (
    Jurisdiction.DUBAI,
    Jurisdiction.SPAIN,
    Jurisdiction.COLOMBIA,
    Jurisdiction.FLORIDA,
)

# Accents are stripped from the question before matching, so terms are written without
# them. Terms match whole words in any case.
# fmt: off
TERMS: Final[dict[tuple[Jurisdiction, ...], tuple[str, ...]]] = {
    (FLORIDA,): (
        "florida", "floridian", "miami", "miami-dade", "dade county", "broward", "palm beach",
        "boca raton", "fort lauderdale", "ft. lauderdale", "hialeah", "coral gables", "doral",
        "brickell", "orlando", "tampa", "jacksonville", "tallahassee", "gainesville",
        "key west", "condo association", "condominium association", "homeowners association",
        "homeowners' association", "hoa", "fla. stat.", "florida statutes", "chapter 83",
        "chapter 718",
    ),
    (DUBAI,): (
        "dubai", "emirate", "emirates", "emirati", "united arab emirates", "uae", "rera",
        "ejari", "dld", "dubai land department", "rent disputes centre", "rental disputes centre",
        "rent disputes center", "rental disputes center", "rdsc", "dewa", "dirham", "dirhams",
        "jumeirah", "deira", "business bay", "al barsha", "jlt", "jvc",
    ),
    (SPAIN,): (
        "spain", "spanish", "espana", "madrid", "barcelona", "valencia", "seville", "sevilla",
        "malaga", "bilbao", "zaragoza", "alicante", "palma", "mallorca", "majorca", "ibiza",
        "catalonia", "catalunya", "andalusia", "basque country", "canary islands", "balearic",
        "ley de arrendamientos urbanos", "arrendamientos urbanos", "ley de vivienda", "fianza",
        "comunidad de propietarios", "real decreto", "lph", "euro", "euros",
    ),
    (COLOMBIA,): (
        "colombia", "colombian", "bogota", "medellin", "cali", "barranquilla", "bucaramanga",
        "pereira", "santa marta", "antioquia", "cundinamarca", "ley 820", "ley 675",
        "canon de arrendamiento", "codeudor", "smmlv", "smlmv", "colombian pesos",
    ),
    (SPAIN, COLOMBIA): (
        "arrendamiento", "arrendamientos", "arrendador", "arrendatario", "inquilino",
        "propiedad horizontal", "ipc", "cartagena", "codigo civil",
    ),
}
# fmt: on
# Acronyms that are also ordinary words or names count only in capitals: "Lau" is a
# surname, "cop" a word.
CAPITALS: Final[dict[Jurisdiction, tuple[str, ...]]] = {
    FLORIDA: ("FL",),
    DUBAI: ("AED",),
    SPAIN: ("LAU", "BOE", "NIE", "INE"),
    COLOMBIA: ("COP", "DANE"),
}
# Statute numbers: "s. 83.49", "§ 718.116", a bare "83.56"; "Law No. (26) of 2007";
# "Ley 29/1994".
NUMBERS: Final[dict[Jurisdiction, str]] = {
    FLORIDA: r"(?:§\s*|s\.\s*|section\s+)?(?:83|718)\.\d{2,3}",
    DUBAI: r"law no\.?\s*\(?(?:26|33)\)?\s+of\s+(?:2007|2008)",
    SPAIN: r"ley\s+(?:29/1994|49/1960|12/2023)",
}


def _words(terms: tuple[str, ...]) -> str:
    return r"(?<!\w)(?:" + "|".join(re.escape(t) for t in terms) + r")(?!\w)"


RULES: Final[list[tuple[re.Pattern[str], tuple[Jurisdiction, ...]]]] = [
    *((re.compile(_words(terms), re.IGNORECASE), found) for found, terms in TERMS.items()),
    *((re.compile(_words(terms)), (found,)) for found, terms in CAPITALS.items()),
    *(
        (re.compile(rf"(?<![\w.]){number}(?!\w)", re.IGNORECASE), (found,))
        for found, number in NUMBERS.items()
    ),
    (re.compile("€"), (SPAIN,)),  # the only euro jurisdiction of the four; "€500" has no word edge
]


def detect(question: str) -> list[Jurisdiction]:
    """The jurisdictions the question names, in a fixed order; all four if it names none."""
    plain = "".join(
        c for c in unicodedata.normalize("NFKD", question) if not unicodedata.combining(c)
    )
    found = {j for pattern, names in RULES if pattern.search(plain) for j in names}
    return [j for j in Jurisdiction if j in found] or list(Jurisdiction)
