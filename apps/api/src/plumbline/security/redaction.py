"""Redaction: what every real upload passes before any model sees it (the Redactor that
generation.router declares and the lease checker calls first).

Presidio finds the personal data, with spaCy's medium English or Spanish model for names
and places and pattern recognizers for identifiers; each span becomes a typed placeholder
such as <PERSON> or <ES_NIF>. What it keeps, as agreed with Lane C, is what the lease
checker reads the law against:

- amounts, periods and dates exactly as written ("EUR 1,150", "within 60 days", "signed
  on 2026-03-01"): no date or money recognizer runs, and a date goes only when birth
  wording comes right before it ("born on", "fecha de nacimiento");
- clause headings ("## Clause 5. Deposit", "Cláusula quinta."): a span that reaches into
  one is cut back to the part outside it, so a heading never ends up inside a placeholder;
- the jurisdictions' names and the parties' roles, which identify no one and tell the
  model which law governs.

Names come from three places, since the medium models miss many invented ones: the model's
people and places, its organisations when they look like names (_ORG_WORDS), and the
names a lease gives its parties after their roles; a name found once is then redacted
wherever else it appears. References to the law ("Law No. (33) of 2008") are protected
like headings. Identifier patterns run whatever the upload's language, since an English lease under
Spanish law still carries a Spanish NIF. A failure anywhere raises RedactionRefused: an
upload is never passed on half-redacted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Final

from presidio_analyzer import (
    AnalyzerEngine,
    EntityRecognizer,
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
    RecognizerResult,
)
from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngineProvider
from presidio_analyzer.predefined_recognizers import (
    CreditCardRecognizer,
    EmailRecognizer,
    EsNieRecognizer,
    EsNifRecognizer,
    IbanRecognizer,
    IpRecognizer,
    PhoneRecognizer,
    UsPassportRecognizer,
    UsSsnRecognizer,
)

from plumbline.core.types import Language
from plumbline.generation.router import RedactionRefused, Upload

LANGUAGES: Final = ("en", "es")
MODELS: Final = {"en": "en_core_web_md", "es": "es_core_news_md"}

# Below this a name or place from the model is left alone: spaCy's medium models score
# their entities at Presidio's default 0.85, so this drops only the weak pattern hits.
MIN_SCORE: Final = 0.4

# Public names the model needs to see: they identify no one.
KEEP: Final = (
    "Florida",
    "Dubai",
    "Emirate of Dubai",
    "United Arab Emirates",
    "UAE",
    "United States",
    "USA",
    "Spain",
    "España",
    "Colombia",
    "Landlord",
    "Tenant",
    "Co-signer",
    "Arrendador",
    "Arrendatario",
    "Codeudor",
    "Premises",
    "Dubai Municipality",
    "Dubai Land Department",
    "Real Estate Regulatory Agency",
    "Rental Disputes Center",
    "Ejari",
)
# Matched whole and in any case: "dubai" in a lease id is still Dubai.
_KEEP: Final = r"^(?:" + "|".join(re.escape(word) for word in KEEP) + r")$"

# spaCy's medium models take many invented names for organisations ("Ignatius
# Fairweather-Mbeki", "Heron Gate"). An organisation span becomes a <NAME> when it looks
# like a name: two to four capitalised words and none of the words that mark a company, a
# public body or a law, which stay because the checker quotes them ("Florida Statutes",
# "Pelican Reach Rentals LLC"). Single words ("Tenant", "Utilities") are never names here.
_ORG_WORDS: Final = frozenset(
    [
        "llc",
        "l.l.c.",
        "inc",
        "inc.",
        "ltd",
        "ltd.",
        "corp",
        "co.",
        "company",
        "s.a.",
        "s.a.s.",
        "s.l.",
        "s.l.u.",
        "holdings",
        "group",
        "rentals",
        "properties",
        "realty",
        "homes",
        "trust",
        "bank",
        "savings",
        "association",
        "condominium",
        "inversiones",
        "inmobiliaria",
        "municipality",
        "department",
        "authority",
        "agency",
        "center",
        "centre",
        "court",
        "statutes",
        "statute",
        "law",
        "ley",
        "código",
        "codigo",
        "decree",
        "act",
        "chapter",
        "article",
        "section",
        "part",
        "fianza",
    ]
)
_CAPITALISED: Final = re.compile(r"^[A-ZÁÉÍÓÚÑ][\w'’.-]*$")

# A clause label with its number or ordinal ("Clause 5.", "Cláusula quinta.", "Article 9",
# "Section 4(b)"). Only the label: the rest of a heading line is redacted like any text, so
# "## Clause 5. John Smith" loses the name.
_HEADING: Final = re.compile(
    r"\b(?:clause|cl[aá]usula|article|art[ií]culo|section|secci[oó]n)\s+"
    r"(?:\d+[\w.()-]*|[a-záéíóúñ]+(?=[.:]))[.:]?",
    re.IGNORECASE,
)
# A reference to the law, which the checker reads the lease against and the models take for
# names: "Law No. (33) of 2008", "Ley 820 de 2003", "Decree No. 43", "Chapter 83, Florida
# Statutes", "s. 83.49(3)". Never inside a redaction either.
_LEGAL: Final = re.compile(
    r"\b(?:federal\s+)?(?:law|ley|decree|decreto|real\s+decreto|chapter|cap[ií]tulo)"
    r"\s+(?:no\.?\s*|n\.?º\s*|number\s+)?\(?\d+[\w/.-]*\)?(?:\s+(?:of|de)\s+\d{4})?"
    r"|\bs\.\s*\d+\.\d+[\w()]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    entity: str


class ContextRecognizer(EntityRecognizer):
    """An identifier recognized only after the words that introduce it: the regex's
    `value` groups are the spans, so "cédula 1.020.345.678" loses the number and keeps the
    word, and a bare number elsewhere (an amount, a clause) is never taken for one."""

    def __init__(self, entity: str, regex: str, language: str, flags: int = re.IGNORECASE) -> None:
        self.regex = re.compile(regex, flags)
        super().__init__(
            supported_entities=[entity],
            supported_language=language,
            name=f"{entity.title()}Recognizer_{language}",
        )

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: NlpArtifacts | None = None
    ) -> list[RecognizerResult]:
        entity = self.supported_entities[0]
        return [
            RecognizerResult(entity, m.start(group), m.end(group), 0.9)
            for m in self.regex.finditer(text)
            for group, value in m.groupdict().items()
            if group.startswith("value") and value
        ]


_DATE: Final = (
    r"(?:\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:de\s+)?[a-záéíóú]+\.?,?\s+(?:de\s+)?\d{4}"
    r"|[a-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})"
)
_CONTEXT: Final = {
    # A date right after birth wording; any other date is the lease's own and stays.
    "DATE_OF_BIRTH": (
        r"\b(?:born(?:\s+on)?|date\s+of\s+birth|d\.?o\.?b\.?|birth\s*date"
        r"|nacid[oa](?:\s+el)?|fecha\s+de\s+nacimiento)[\s:,]*(?P<value>" + _DATE + ")"
    ),
    # Colombia's cédula de ciudadanía (or de extranjería), written "C.C. 1.020.345.678".
    "CO_CEDULA": (
        r"(?:\bc[eé]dula(?:\s+de\s+(?:ciudadan[ií]a|extranjer[ií]a))?|\bC\.\s?[CE]\.|\bCC\b"
        r"|\bNIT\b|\bidentity\s+card)"
        r"[\s:,]*(?:(?:no\.?|n\.?º|number|n[uú]mero)[\s:]*)?(?P<value>\d[\d.\- ]{4,14}\d)"
    ),
    # A passport number after the word, in any country's letters-and-digits form.
    "PASSPORT": (
        r"\b(?:passport|pasaporte)(?:\s+(?:no\.?|number|n[uú]mero))?[\s:,]*"
        r"(?P<value>[A-Z]{0,3}\d{6,9})"
    ),
}

# A party named after its role, as a lease introduces it ("Tenant: Tobias Wren-Calloway",
# "Arrendador (landlord): ..."): the name is the capitalised words after the colon. The
# label matches in any case ("TENANT:" in a signature block) and the name in capitals too,
# but each word must start with a capital, so "the Tenant: the leased flat" is no name.
_NAME: Final = r"[A-ZÁÉÍÓÚÑ][\w'’-]+(?:[ ][A-ZÁÉÍÓÚÑ][\w'’-]+){1,4}"
_PARTY: Final = (
    r"\b(?i:Landlords?|Tenants?|Co-?signers?|Guarantors?|Lessor|Lessee|Arrendador|Arrendataria?"
    r"|Arrendatario|Codeudora?|Fiadora?)(?:\s*\([^)\n]*\))?(?:,\s*a natural person)?\s*:\s*"
    r"(?P<value>" + _NAME + r")(?:\s+(?:and|y)\s+(?P<value2>" + _NAME + r"))?"
)

_PATTERNS: Final = {
    # The UAE's Emirates ID: 784, the birth year, seven digits and a check digit.
    "AE_EMIRATES_ID": [Pattern("emirates id", r"\b784-?\d{4}-?\d{7}-?\d\b", 0.9)],
    # A street address: a street word and its name and number (Spanish and Colombian
    # style, "Calle del Yarumo Blanco No. 8-15"), or a number before a street name and its
    # suffix (US style, "4410 Gilded Ibis Lane"). The city after it is a place name.
    "ADDRESS": [
        Pattern(
            "street first",
            r"\b(?:calle|avenida|av\.|carrera|cra\.|transversal|diagonal|paseo|plaza|ronda"
            r"|camino|travesía|street|road)\s+(?:[\wÁÉÍÓÚÑáéíóúñ'-]+\s+){0,5}?"
            r"(?:no\.?\s*|n\.?º\s*|#\s*)?\d+[a-z]?(?:\s*-\s*\d+)?\b",
            0.6,
        ),
        Pattern(
            "number first",
            r"\b\d{1,6}\s+(?:[A-Z][\w'-]*\s+){1,4}(?:street|st|avenue|ave|road|rd|drive|dr"
            r"|boulevard|blvd|lane|ln|court|ct|way|place|pl|terrace|circle|highway|hwy|parkway|pkwy"
            r"|row|mews|crescent|walk|trail|square|sq)\b\.?",
            0.6,
        ),
    ],
}

# What Presidio's built-in recognizers find; the model's names and places come on top.
_BUILTIN: Final = (
    EmailRecognizer,
    PhoneRecognizer,
    IbanRecognizer,
    CreditCardRecognizer,
    IpRecognizer,
    EsNifRecognizer,
    EsNieRecognizer,
    UsSsnRecognizer,
    UsPassportRecognizer,
)
ENTITIES: Final = sorted(
    {"PERSON", "LOCATION", "ORGANIZATION", *_CONTEXT, *_PATTERNS}
    | {e for r in _BUILTIN for e in r().supported_entities}
)


def _recognizers(language: str) -> Iterable[EntityRecognizer]:
    for builtin in _BUILTIN:
        yield builtin(supported_language=language)
    for entity, regex in _CONTEXT.items():
        yield ContextRecognizer(entity, regex, language)
    yield ContextRecognizer("PERSON", _PARTY, language, flags=0)
    for entity, patterns in _PATTERNS.items():
        yield PatternRecognizer(
            supported_entity=entity,
            patterns=patterns,
            supported_language=language,
            name=f"{entity.title()}Recognizer_{language}",
            global_regex_flags=re.IGNORECASE | re.MULTILINE,
        )


@cache
def analyzer() -> AnalyzerEngine:
    """Built once per process: loading both spaCy models takes a few seconds."""
    nlp = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": lang, "model_name": MODELS[lang]} for lang in LANGUAGES],
        }
    ).create_engine()
    registry = RecognizerRegistry(supported_languages=list(LANGUAGES))
    registry.load_predefined_recognizers(languages=list(LANGUAGES), nlp_engine=nlp)
    # Keep only the model's names and places from the predefined set; every identifier
    # recognizer is ours, registered for both languages.
    registry.recognizers = [
        r for r in registry.recognizers if type(r).__name__ == "SpacyRecognizer"
    ]
    for lang in LANGUAGES:
        for recognizer in _recognizers(lang):
            registry.add_recognizer(recognizer)
    return AnalyzerEngine(nlp_engine=nlp, registry=registry, supported_languages=list(LANGUAGES))


def find(text: str, language: Language) -> list[Span]:
    """The spans to redact, sorted, merged where they overlap, and cut around headings."""
    results = analyzer().analyze(
        text=text,
        language=language.value,
        entities=ENTITIES,
        score_threshold=MIN_SCORE,
        allow_list=[_KEEP],
        allow_list_match="regex",
        regex_flags=re.IGNORECASE,
    )
    protected = [
        (m.start(), m.end()) for pattern in (_HEADING, _LEGAL) for m in pattern.finditer(text)
    ]
    spans = [
        piece
        for r in results
        if (entity := _entity(r.entity_type, text[r.start : r.end])) is not None
        for piece in _outside(Span(r.start, r.end, entity), protected, text)
    ]
    return _merge(spans + _elsewhere(spans, text, protected))


def _elsewhere(
    spans: Sequence[Span], text: str, protected: Sequence[tuple[int, int]]
) -> list[Span]:
    """Every other place a name found once appears: a model that misses "Priyanka
    Osei-Lindqvist" in the signatures has her from the parties' line, in any case
    ("PRIYANKA OSEI-LINDQVIST"). Only names of two words or more, so a lone first name
    never spreads to every word that shares it."""
    names = {text[s.start : s.end]: s.entity for s in spans if s.entity in ("PERSON", "NAME")}
    found = []
    for name, entity in names.items():
        if len(name.split()) < 2:
            continue
        for m in re.finditer(re.escape(name), text, re.IGNORECASE):
            found += _outside(Span(m.start(), m.end(), entity), protected, text)
    return found


def _entity(found: str, words: str) -> str | None:
    """The placeholder for what a recognizer found, or None to leave it: an organisation
    stays unless it looks like a name (see _ORG_WORDS)."""
    if found != "ORGANIZATION":
        return found
    tokens = words.split()
    named = 2 <= len(tokens) <= 4 and all(_CAPITALISED.match(t) for t in tokens)
    if named and not any(t.casefold().rstrip(",") in _ORG_WORDS for t in tokens):
        return "NAME"
    return None


def apply(text: str, spans: Sequence[Span]) -> str:
    out, at = [], 0
    for span in spans:
        out += [text[at : span.start], f"<{span.entity}>"]
        at = span.end
    return "".join([*out, text[at:]])


def _outside(span: Span, protected: Sequence[tuple[int, int]], text: str) -> list[Span]:
    """The parts of a span outside every protected range, trimmed of spaces and
    punctuation; a part with no letter or digit left is dropped."""
    pieces = [(span.start, span.end)]
    for p_start, p_end in protected:
        pieces = [
            part
            for start, end in pieces
            for part in ((start, min(end, p_start)), (max(start, p_end), end))
            if part[0] < part[1]
        ]
    kept = []
    for start, end in pieces:
        while start < end and not text[start].isalnum():
            start += 1
        while end > start and not text[end - 1].isalnum():
            end -= 1
        if start < end:
            kept.append(Span(start, end, span.entity))
    return kept


def _merge(spans: Iterable[Span]) -> list[Span]:
    """Overlapping spans become one, named for the longer: a street address that holds a
    place name is one <ADDRESS>, not an address with a <LOCATION> inside it."""
    merged: list[Span] = []
    for span in sorted(spans, key=lambda s: (s.start, -s.end)):
        if merged and span.start < merged[-1].end:
            last = merged[-1]
            longer = last if last.end - last.start >= span.end - span.start else span
            merged[-1] = Span(last.start, max(last.end, span.end), longer.entity)
        else:
            merged.append(span)
    return merged


class PresidioRedactor:
    """generation.router.Redactor over Presidio. A synthetic lease is redacted like any
    other upload: the planted findings must survive it, and the tests hold them to that."""

    def redact(self, upload: Upload) -> str:
        try:
            return apply(upload.text, find(upload.text, upload.language))
        except Exception:  # any failure refuses the upload; nothing passes unredacted
            raise RedactionRefused("The upload could not be redacted.") from None
