"""Streaming one field out of JSON: what it emits joins to the field, however it is cut."""

import json
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from plumbline.generation.jsonstream import FieldStream


def feed_all(pieces: list[str], field: str = "answer") -> tuple[list[str], FieldStream]:
    stream = FieldStream(field)
    return [stream.feed(piece) for piece in pieces], stream


def test_text_arrives_before_the_object_closes() -> None:
    emitted, stream = feed_all(['{"status": "answered", "answ', 'er": "The dep', "osit"])
    assert emitted == ["", "The dep", "osit"]
    assert not stream.done
    assert stream.feed('", "confidence": 0.9}') == ""
    assert stream.done


def test_escapes_cut_anywhere_decode_whole() -> None:
    emitted, stream = feed_all(
        ['{"answer": "a \\', '"quoted\\" \\u00', "e9 \\ud83d", "\\ude00 \\n", '"}']
    )
    assert "".join(emitted) == 'a "quoted" é 😀 \n'
    assert stream.done


def test_lookalike_keys_are_not_the_field() -> None:
    text = json.dumps(
        {
            "abstain_reason": 'It said "answer": "decoy one"',
            "citations": [{"answer": "decoy two", "quote": "x"}],
            "answer": "the real one",
        }
    )
    assert "".join(feed_all([text])[0]) == "the real one"


def test_a_missing_field_emits_nothing() -> None:
    emitted, stream = feed_all(['{"status": "abstained", "citations": []}'])
    assert emitted == [""]
    assert not stream.done


DECOYS: dict[str, Any] = {
    "abstain_reason": 'He wrote "answer": "decoy" here',
    "citations": [{"n": 1, "answer": "decoy", "quote": '\\ " \n'}],
    "confidence": 0.5,
    "status": "answered",
}


@given(
    answer=st.text(),
    order=st.permutations([*DECOYS, "answer"]),
    ascii_only=st.booleans(),
    indent=st.sampled_from([None, 2]),
    data=st.data(),
)
def test_any_answer_cut_anywhere_round_trips(
    answer: str, order: list[str], ascii_only: bool, indent: int | None, data: st.DataObject
) -> None:
    obj = {key: answer if key == "answer" else DECOYS[key] for key in order}
    text = json.dumps(obj, ensure_ascii=ascii_only, indent=indent)
    cuts = sorted(data.draw(st.lists(st.integers(0, len(text)), max_size=12)))
    pieces = [text[a:b] for a, b in zip([0, *cuts], [*cuts, len(text)], strict=True)]
    emitted, stream = feed_all(pieces)
    assert "".join(emitted) == answer
    assert stream.done
