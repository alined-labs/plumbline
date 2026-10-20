import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from plumbline.corpus.manifest import Manifest, Source, load_manifest
from plumbline.corpus.refs import article_exists, article_text, paragraph_text
from plumbline.corpus.validate import check_frozen, check_golden, check_leases, check_versions
from plumbline.settings import ROOT

SOURCES = {source.law: source for source in load_manifest().sources}


@pytest.mark.parametrize(
    ("law", "article", "present"),
    [
        ("fl-stat-83", "83.49", True),
        ("fl-stat-83", "83.5615", True),  # its number follows a footnote mark
        ("fl-stat-83", "83.99", False),
        ("fl-stat-83", "718.112", False),  # a section of the other Florida source
        ("fl-stat-718", "718.112", True),
        ("fl-stat-718", "718.111", False),  # only three sections of the chapter are in the corpus
        ("es-lau", "36", True),
        ("es-lau", "9 bis", True),
        ("es-lau", "99", False),
        ("es-lph", "17", True),  # "Artículo diecisiete"
        ("es-lph", "10", True),
        ("es-lph", "25", False),  # the law has twenty-four articles
        ("es-lph", "diecisiete", False),  # references use numbers
    ],
)
def test_committed_articles_are_found_in_their_pinned_files(
    law: str, article: str, present: bool
) -> None:
    assert article_exists(SOURCES[law], article) is present


def fetch_only(law: str, root: Path, name: str, content: bytes) -> Source:
    row = SOURCES[law].model_dump(mode="json")
    row.update(committed=False, path=f"data/corpus/fetched/{name}", id=f"{law}-test")
    (root / "data" / "corpus" / "fetched").mkdir(parents=True, exist_ok=True)
    (root / "data" / "corpus" / "fetched" / name).write_bytes(content)
    return Source.model_validate(row)


def test_a_source_not_on_this_machine_cannot_be_checked(tmp_path: Path) -> None:
    assert article_exists(SOURCES["co-ley-820"], "16", tmp_path) is None


def test_colombian_articles_read_entities_and_skip_scripts(tmp_path: Path) -> None:
    page = (
        "<p>ART&Iacute;CULO 16. PROHIBICI&Oacute;N DE DEP&Oacute;SITOS.</p>"
        "<p>ART&Iacute;CULO 8o. OBLIGACIONES.</p><script>ARTÍCULO 40. old wording</script>"
    )
    source = fetch_only("co-ley-820", tmp_path, "ley.html", page.encode("cp1252"))
    assert article_exists(source, "16", tmp_path) is True
    assert article_exists(source, "8", tmp_path) is True  # "8o."
    assert article_exists(source, "40", tmp_path) is False  # only an earlier wording, in a script


def test_a_colombian_validity_note_is_kept_in_the_article_text(tmp_path: Path) -> None:
    """The Senado writes "<Artículo derogado ...>" as an entity-escaped note beside the heading.
    A reviewer needs it, so it must survive the removal of tags."""
    page = (
        "<p><a name='39'>ART&Iacute;CULO 39. TR&Aacute;MITE PREFERENTE.</a> "
        "&lt;Art&iacute;culo derogado por el literal c) del art&iacute;culo 626 de la Ley 1564 "
        "de 2012&gt;</p><p>Siguiente</p><p>Disposiciones analizadas por Avance Jur&iacute;dico</p>"
        "<p>ART&Iacute;CULO 40. OTRO.</p>"
    )
    source = fetch_only("co-ley-820", tmp_path, "ley.html", page.encode("cp1252"))
    text = article_text(source, "39", None, tmp_path)
    assert text is not None
    assert "<Artículo derogado por el literal c) del artículo 626 de la Ley 1564 de 2012>" in text
    assert "ARTÍCULO 40" not in text
    assert "Siguiente" not in text
    assert "Avance" not in text


def test_dubai_articles_are_found_in_the_fetched_pdfs_when_they_are_here() -> None:
    cases = [
        ("dubai-law-26-2007", "20", True),
        ("dubai-law-26-2007", "99", False),
        ("dubai-law-33-2008", "13", True),
        ("dubai-law-33-2008", "12", False),  # 33/2008 restates eleven articles, not twelve
        ("dubai-dld-tenancy-guide", "Decree 43/2013 art. 1", True),
        ("dubai-dld-tenancy-guide", "Decree 43/2013 art. 9", False),
        ("dubai-dld-tenancy-guide", "1", False),  # the guide's articles are named by their law
    ]
    found = [article_exists(SOURCES[law], article) for law, article, _ in cases]
    if None in found:
        pytest.skip("the Dubai PDFs are not fetched on this machine")
    assert found == [expected for _, _, expected in cases]


MANIFEST = Manifest.model_validate(
    {"sources": [s.model_dump(mode="json") for s in SOURCES.values()]}
)


def golden_line(**overrides: Any) -> str:
    row: dict[str, Any] = {
        "id": "es-9001",
        "question": "How much deposit may a Spanish landlord ask for?",
        "source_language": "es",
        "jurisdictions": ["spain"],
        "category": "single_article",
        "difficulty": "easy",
        "gold_refs": [
            {
                "jurisdiction": "spain",
                "law": "es-lau",
                "article": "36",
                "edition": SOURCES["es-lau"].edition,
            }
        ],
        "reference_answer": "One month's rent.",
        "source_type": "synthetic",
        "added_in": "v0",
    }
    row.update(overrides)
    return json.dumps(row)


def golden_root(tmp_path: Path, line: str) -> Path:
    folder = tmp_path / "data" / "golden"
    folder.mkdir(parents=True)
    # The sources live in the real corpus: look articles up there, not in an empty folder.
    (tmp_path / "data" / "corpus").symlink_to(ROOT / "data" / "corpus")
    (folder / "golden_v0.jsonl").write_text(line + "\n", encoding="utf-8")
    return tmp_path


def article(number: str, law: str = "es-lau", edition: str | None = None) -> dict[str, str]:
    source = SOURCES[law]
    return {
        "jurisdiction": source.jurisdiction.value,
        "law": law,
        "article": number,
        "edition": edition or source.edition,
    }


def test_a_gold_reference_to_a_real_article_passes(tmp_path: Path) -> None:
    assert check_golden(golden_root(tmp_path, golden_line()), MANIFEST) == []


@pytest.mark.parametrize(
    ("ref", "problem"),
    [
        (article("361"), "article 361 is not in es-lau-boe-2026-10-13"),
        (article("36", edition="boe-2020-01-01"), "edition boe-2020-01-01 is not in the manifest"),
        (article("36", law="es-lph"), "article 36 is not in es-lph-boe-2026-10-05"),
        ({**article("36"), "jurisdiction": "colombia"}, "is not colombia law"),
    ],
)
def test_a_gold_reference_that_does_not_exist_is_refused(
    tmp_path: Path, ref: dict[str, str], problem: str
) -> None:
    # Both jurisdictions are listed, so the item itself is valid and only the reference is wrong.
    line = golden_line(jurisdictions=["spain", "colombia"], gold_refs=[ref])
    root = golden_root(tmp_path, line)
    [found] = check_golden(root, MANIFEST)
    assert "es-9001" in found
    assert problem in found


def lease_root(tmp_path: Path, **overrides: Any) -> Path:
    leases = tmp_path / "data" / "leases"
    leases.mkdir(parents=True)
    (leases / "es-lease-09.md").write_text(
        "# Lease\n\n- Signed on: 2026-02-01\n\n## Clause 5. Deposit\n\nA deposit of two months.\n",
        encoding="utf-8",
    )
    finding = {
        "clause": "5",
        "quote": "deposit of two months",
        "issue": "One month only.",
        "violates": article("36"),
    }
    lease = {
        "lease_id": "es-lease-09",
        "jurisdiction": "spain",
        "signed_on": "2026-02-01",
        "findings": [finding],
    }
    (leases / "expected_findings.json").write_text(
        json.dumps({"version": 1, "leases": [lease]}), encoding="utf-8"
    )
    fields = {"category": "lease_check", "lease_id": "es-lease-09", "signed_on": "2026-02-01"}
    return golden_root(tmp_path, golden_line(**{**fields, **overrides}))


def test_a_lease_check_item_that_matches_its_lease_passes(tmp_path: Path) -> None:
    assert check_golden(lease_root(tmp_path), MANIFEST) == []
    assert check_leases(MANIFEST, tmp_path) == []


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        ({"lease_id": "es-lease-10"}, "there is no lease es-lease-10"),
        ({"signed_on": "2026-03-01"}, "the lease was signed 2026-02-01"),
        (
            {"gold_refs": [article("17")]},
            "spain:es-lau:17 is not an article es-lease-09's findings cite",
        ),
    ],
)
def test_a_lease_check_item_must_agree_with_its_lease(
    tmp_path: Path, overrides: dict[str, Any], problem: str
) -> None:
    [found] = check_golden(lease_root(tmp_path, **overrides), MANIFEST)
    assert problem in found


def test_the_committed_drafts_are_consistent_with_the_corpus_and_the_leases() -> None:
    assert check_golden(ROOT, load_manifest()) == []


def test_a_committed_article_reads_as_it_was_pinned() -> None:
    text = article_text(SOURCES["fl-stat-83"], "83.57")
    assert text is not None
    assert text.startswith("83.57 Termination of tenancy without specific term")
    assert "not less than 30 days’ notice prior to the end of any monthly period" in text
    assert article_text(SOURCES["fl-stat-83"], "83.99") is None


@pytest.mark.parametrize(
    ("day", "norm", "wording"),
    [
        (
            date(2019, 2, 10),
            "BOE-A-2019-799",
            "inferior a tres años",
        ),  # Congress repealed the change
        (date(2019, 4, 1), "BOE-A-2019-3108", "inferior a cinco años"),
        (None, "BOE-A-2026-20823", "inferior a cinco años"),  # the edition's own date
    ],
)
def test_a_spanish_article_is_read_as_it_stood_on_the_date(
    day: date | None, norm: str, wording: str
) -> None:
    text = article_text(SOURCES["es-lau"], "9", day)
    assert text is not None
    assert text.splitlines()[0].startswith(f"[{norm}, in force from ")
    assert wording in text
    assert "Se modifica" not in text  # the BOE's amendment notes are not the law


@pytest.mark.parametrize(
    ("day", "header"),
    [
        (date(2026, 10, 1), "[BOE-A-2026-20266, in force from 20261001]"),  # RDL 26/2026
        (date(2026, 10, 5), "[BOE-A-2026-20526, in force from 20261002]"),  # set aside by Congress
        # The last version has no fecha_vigencia; its note dates RDL 29/2026's wording.
        (date(2026, 10, 8), "[BOE-A-2026-20822, in force from 20261008]"),
        (None, "[BOE-A-2026-20822, in force from 20261008]"),
    ],
)
def test_a_version_without_its_date_takes_it_from_its_note(day: date | None, header: str) -> None:
    text = article_text(SOURCES["es-lau"], "10", day)
    assert text is not None
    assert text.splitlines()[0] == header
    restored = "Si llegada la fecha de vencimiento del contrato, o de cualquiera"
    assert (restored in text) is (day == date(2026, 10, 5))


def test_the_property_horizontal_law_is_read_by_the_number_lawyers_cite() -> None:
    text = article_text(SOURCES["es-lph"], "17")
    assert text is not None
    assert "Artículo diecisiete." in text
    assert "tres quintas partes" in text


def test_colombian_and_dubai_articles_are_read_when_fetched() -> None:
    colombian = article_text(SOURCES["co-ley-820"], "16")
    restated = article_text(SOURCES["dubai-law-33-2008"], "2")
    if colombian is None or restated is None:
        pytest.skip("the fetch-only sources are not on this machine")
    assert colombian.startswith("ARTÍCULO 16. PROHIBICIÓN DE DEPÓSITOS Y CAUCIONES REALES.")
    assert "CAPITULO V" not in colombian  # the next heading is not part of the article
    assert restated.count("Article (2)") == 2  # the restated definitions, then the closing article


@pytest.mark.parametrize(
    ("law", "article", "paragraph", "starts", "ends_before"),
    [
        ("fl-stat-718", "718.116", "(11)", "(11)(a) If the unit is occupied by a tenant", "(12)"),
        ("fl-stat-718", "718.112", "(2)(k)", "(k) Transfer fees.", "(l)"),
        ("fl-stat-83", "83.49", "(3)(a)", "(a) Upon the vacating of the premises", "(b) Unless"),
        ("fl-stat-83", "83.67", "(1)", "(1) A landlord of any dwelling unit", "(2) A landlord"),
        ("es-lau", "36", "5", "5. Las partes podrán pactar", "6. Quedan exceptuadas"),
        ("es-lau", "5", "e)", "e) La cesión temporal de uso", "Disposición"),
        ("es-lph", "17", "12", "12. El acuerdo expreso", "13."),
    ],
)
def test_a_cited_paragraph_is_cut_from_its_marker_to_the_next_of_its_kind(
    law: str, article: str, paragraph: str, starts: str, ends_before: str
) -> None:
    text = article_text(SOURCES[law], article)
    assert text is not None
    excerpt = paragraph_text(text, paragraph)
    assert excerpt is not None
    assert excerpt.startswith(starts)
    assert ends_before not in excerpt


def test_paragraphs_may_be_listed_and_may_be_absent() -> None:
    text = article_text(SOURCES["fl-stat-83"], "83.67")
    assert text is not None
    both = paragraph_text(text, "(1), (6)")
    assert both is not None
    assert both.count("\n---\n") == 1
    assert both.startswith("(1) A landlord")
    assert "(6) A landlord who violates" in both
    assert paragraph_text(text, "(99)") is None
    assert paragraph_text(text, "") is None


def test_a_bracketed_letter_also_finds_a_list_set_as_letter_and_full_stop() -> None:
    """The DLD guide sets Decree 43/2013's bands as "a.", "c.", "d." (and a stray "b." that is
    really the end of a's sentence), while a reference cites "(d)"."""
    text = (
        "Article (1)\n"
        "a. no rent increase, where the rent is up to ten percent\n(10%)\n"
        "b. less than the average;\n"
        "c. five percent of the rent, where it is eleven\npercent less;\n"
        "d. ten percent of the rent,\nwhere it is 21% to 30% less;\n"
        "e. fifteen percent of the rent."
    )
    assert (
        paragraph_text(text, "(d)") == "d. ten percent of the rent,\nwhere it is 21% to 30% less;"
    )
    assert (
        paragraph_text(text, "(a)")
        == "a. no rent increase, where the rent is up to ten percent\n(10%)"
    )
    assert paragraph_text(text, "(a), (b)") is not None
    assert paragraph_text(text, "(z)") is None


def drafts_root(tmp_path: Path, **files: list[str]) -> Path:
    drafts = tmp_path / "data" / "golden" / "drafts"
    drafts.mkdir(parents=True)
    for name, lines in files.items():
        (drafts / f"{name}.jsonl").write_text("".join(f"{line}\n" for line in lines))
    return tmp_path


def test_a_later_draft_keeps_the_items_of_an_earlier_one(tmp_path: Path) -> None:
    one, two = golden_line(id="es-9001"), golden_line(id="es-9002", added_in="v1")
    root = drafts_root(tmp_path, golden_v0=[one], golden_v1=[one, two])
    assert check_versions(root) == []


def test_the_split_and_the_verification_may_differ_between_drafts(tmp_path: Path) -> None:
    signed = {
        "quoted_text": "x",
        "second_source": "y",
        "checked_on": "2026-10-20",
        "checked_by": "h",
    }
    plain = golden_line()
    marked = golden_line(split="test", verification=signed)
    assert check_versions(drafts_root(tmp_path, golden_v0=[plain], golden_v1=[marked])) == []


@pytest.mark.parametrize(
    ("later", "problem"),
    [
        (
            golden_line(reference_answer="Two months' rent."),
            "es-9001 differs from golden_v0.jsonl in reference_answer",
        ),
        (golden_line(difficulty="hard", added_in="v1"), "in added_in, difficulty"),
        (golden_line(id="es-9002", added_in="v1"), "es-9001 from golden_v0.jsonl is missing"),
    ],
)
def test_a_later_draft_that_changes_or_drops_an_earlier_item_is_refused(
    tmp_path: Path, later: str, problem: str
) -> None:
    root = drafts_root(tmp_path, golden_v0=[golden_line()], golden_v1=[later])
    [found] = check_versions(root)
    assert problem in found


SIGNED = {"quoted_text": "x", "second_source": "y", "checked_on": "2026-10-20", "checked_by": "h"}


def frozen_root(tmp_path: Path, name: str, *lines: str) -> Path:
    folder = tmp_path / "data" / "golden"
    folder.mkdir(parents=True)
    (folder / name).write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return tmp_path


def test_a_finished_frozen_file_passes(tmp_path: Path) -> None:
    line = golden_line(verification=SIGNED, split="dev", added_in="v1")
    assert check_frozen(frozen_root(tmp_path, "golden_v1.jsonl", line)) == []


@pytest.mark.parametrize(
    ("name", "fields", "problem"),
    [
        ("golden_v0.jsonl", {}, "frozen but not verified"),
        ("golden_v1.jsonl", {"verification": SIGNED}, "frozen without a dev or test split"),
        (
            "golden_v1.jsonl",
            {"verification": SIGNED, "split": "dev", "added_in": "v2"},
            "added in v2, after this version",
        ),
    ],
)
def test_an_unfinished_frozen_file_is_refused(
    tmp_path: Path, name: str, fields: dict[str, Any], problem: str
) -> None:
    [found] = check_frozen(frozen_root(tmp_path, name, golden_line(**fields)))
    assert problem in found


def test_a_frozen_v0_may_have_no_split(tmp_path: Path) -> None:
    line = golden_line(verification=SIGNED, added_in="v0")
    assert check_frozen(frozen_root(tmp_path, "golden_v0.jsonl", line)) == []


def test_a_draft_is_not_held_to_a_frozen_files_promises(tmp_path: Path) -> None:
    folder = tmp_path / "data" / "golden" / "drafts"
    folder.mkdir(parents=True)
    (folder / "golden_v1.jsonl").write_text(golden_line() + "\n", encoding="utf-8")
    assert check_frozen(tmp_path) == []
