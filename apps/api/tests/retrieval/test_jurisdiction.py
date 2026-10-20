from pathlib import Path

import pytest

from plumbline.core.types import Jurisdiction
from plumbline.retrieval.jurisdiction import detect
from plumbline.settings import ROOT
from rag_eval.schema import load_golden

D, S, C, F = Jurisdiction.DUBAI, Jurisdiction.SPAIN, Jurisdiction.COLOMBIA, Jurisdiction.FLORIDA
ALL = [D, S, C, F]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Can my Miami landlord keep my deposit?", [F]),
        ("Does a Miami-Dade or Broward ordinance change the notice period?", [F]),
        ("Can my condo association stop me from renting my unit out?", [F]),
        ("Can the HOA fine my tenant?", [F]),
        ("What does s. 83.49 say about interest on deposits?", [F]),
        ("Rent in Miami, FL: how many days' notice before eviction?", [F]),
        ("How much can my Dubai landlord raise the rent?", [D]),
        ("Does RERA's rental index cap my increase?", [D]),
        ("Do I need Ejari registration for a sublease?", [D]),
        ("Can the DLD cancel my lease?", [D]),
        ("Is the deposit of AED 5,000 refundable under Law No. 26 of 2007?", [D]),
        ("What does the LAU say about lease duration?", [S]),
        ("How many months of fianza can a landlord ask for?", [S]),
        ("My flat in Málaga costs €900 a month; can the rent go up?", [S]),
        ("What does Ley 820 say about deposits?", [C]),
        ("Can my landlord in Bogotá raise the rent above the IPC?", [S, C]),
        ("Is a verbal contrato de arrendamiento valid?", [S, C]),
        ("Compare the notice period in Dubai and Florida.", [D, F]),
        ("How long does a landlord have to return a deposit?", ALL),
    ],
)
def test_detect_names_the_jurisdictions_in_the_question(
    question: str, expected: list[Jurisdiction]
) -> None:
    assert detect(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "Mr Lau rents me a room; what are my rights?",  # a surname, not the LAU
        "A cop came to my door about the lease.",  # a word, not the Colombian peso
        "Rent rose to 1,083.49 dollars this year.",  # a sum, not Fla. Stat. s. 83.49
        "Can my landlord in California keep my deposit?",  # Cali is a prefix here
    ],
)
def test_lookalikes_do_not_count(question: str) -> None:
    assert detect(question) == ALL


GOLDEN = sorted((ROOT / "data" / "golden").glob("golden_v*.jsonl"))


@pytest.mark.skipif(not GOLDEN, reason="no frozen golden file yet")
@pytest.mark.parametrize("path", GOLDEN, ids=[p.name for p in GOLDEN])
def test_no_golden_question_loses_its_jurisdiction(path: Path) -> None:
    # The detector filters retrieval, so it must never drop a jurisdiction the item is
    # about; finding extra ones only costs precision.
    missed = [
        f"{item.id}: {sorted(set(item.jurisdictions) - set(detect(item.question)))}"
        for item in load_golden(path)
        if not set(item.jurisdictions) <= set(detect(item.question))
    ]
    assert not missed, "\n".join(missed)
