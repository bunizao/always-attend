import pathlib
import sys

import pytest

SYS_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_PATH = SYS_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from core.submit import _build_candidate_codes, _extract_slot_label, _normalize_slot_text


def test_normalize_slot_text_handles_synonyms():
    assert _normalize_slot_text("Laboratory 5") == "lab 05"
    assert _normalize_slot_text("Lab-3") == "lab 03"
    assert _normalize_slot_text("Tutorial 2") == "tut 02"


def test_extract_slot_label_removes_course_prefix():
    raw = "FIT1043 Laboratory 05\nWed 10:00"
    assert _extract_slot_label(raw, "FIT1043").lower().startswith("laboratory")


@pytest.mark.parametrize(
    "used,expected",
    [
        (set(), ["B1", "A1", "C1"]),
        ({"B1"}, ["A1", "C1"]),
    ],
)
def test_build_candidate_codes_respects_priority_and_usage(used, expected):
    slot_code_map = {"lab 05": ["B1"]}
    ordered_codes = ["B1", "A1", "C1"]
    candidates = _build_candidate_codes("lab 05", slot_code_map, ordered_codes, used)
    assert candidates == expected
