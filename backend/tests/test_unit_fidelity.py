"""Unit retry policy: never infer a missing temperature unit from context alone."""
from __future__ import annotations

import copy

import pytest
from PIL import Image

from msds.preprocess.unit_fidelity import repair_unit_items


class Recognizer:
    def __init__(self, readings):
        self.readings = readings
        self.calls = 0

    def predict(self, crop):
        text, score = self.readings[self.calls % len(self.readings)]
        self.calls += 1
        return [{"res": {"rec_text": text, "rec_score": score}}]


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "page.png"
    Image.new("RGB", (300, 120), "white").save(path)
    return path


def entries(text="-42 c"):
    return [
        {"text": "끓는점", "box": [10, 30, 70, 50]},
        {"text": text, "box": [100, 30, 220, 50], "confidence": 0.97},
    ]


def test_two_source_crops_can_change_only_unit_and_preserve_original(image):
    original = entries("-42 c (reference 003)")
    snapshot = copy.deepcopy(original)
    recognizer = Recognizer([("-42 °C (reference O03)", 0.93)])
    repaired, audit = repair_unit_items(original, image, recognizer)
    assert original == snapshot
    assert repaired[1]["text"] == "-42 °C (reference 003)"
    assert repaired[1]["raw_ocr_text"] == original[1]["text"]
    assert audit[0]["applied"]
    assert len({tuple(row["crop_box"]) for row in audit[0]["retries"]}) == len(audit[0]["retries"])
    assert len(audit[0]["unit_decisions"][0]["supporting_retry_indices"]) >= 2


@pytest.mark.parametrize("reading,score", [
    ("42 °C", 0.98),   # missing minus sign
    ("-43 °C", 0.99),  # different numeric value
    ("-42 C", 0.99),   # no recognized degree glyph
    ("-42 °c", 0.99),  # upper-case C was not corroborated
    ("-42 °C", 0.84),  # below the confidence threshold
])
def test_no_repair_without_same_signed_number_and_high_score(image, reading, score):
    original = entries()
    repaired, audit = repair_unit_items(original, image, Recognizer([(reading, score)]))
    assert repaired[1]["text"] == original[1]["text"]
    assert not audit[0]["applied"]
    assert audit[0]["needs_review"]


def test_one_supporting_retry_is_insufficient(image):
    class OneHit:
        def __init__(self):
            self.calls = 0

        def predict(self, crop):
            self.calls += 1
            return [{"rec_text": "-42 °C" if self.calls == 1 else "-42 C", "rec_score": 0.99}]

    repaired, audit = repair_unit_items(entries(), image, OneHit())
    assert repaired[1]["text"] == "-42 c"
    assert not audit[0]["applied"]


def test_conflicting_degree_unit_blocks_repair(image):
    repaired, audit = repair_unit_items(
        entries(), image, Recognizer([("-42 °C", 0.97), ("-42 °F", 0.96)]),
    )
    assert repaired[1]["text"] == "-42 c"
    assert audit[0]["unit_decisions"][0]["reason"] == "conflicting_degree_unit"


def test_isotope_dates_model_codes_and_correct_units_do_not_retry():
    inputs = [
        {"text": "14C isotope", "box": [0, 0, 120, 20]},
        {"text": "작성 2026-10-31 C", "box": [0, 30, 120, 50]},
        {"text": "모델 250C", "box": [0, 60, 120, 80]},
        {"text": "온도 -42 °C", "box": [0, 90, 120, 110]},
        {"text": "C10H22", "box": [0, 120, 120, 140]},
    ]
    # No eligible candidate must avoid even opening this nonexistent image.
    repaired, audit = repair_unit_items(inputs, "/does/not/exist.png")
    assert repaired == inputs
    assert audit == []


@pytest.mark.parametrize("text", ["-42 c or -42 c", "-42 c or -42℃"])
def test_repeated_numeric_value_cannot_align_focus_crop(image, text):
    repaired, audit = repair_unit_items(
        entries(text), image, Recognizer([("-42 °C", 0.99)]),
    )
    assert repaired[1]["text"] == text
    assert all(row["reason"] == "repeated_numeric_value" for row in audit[0]["unit_decisions"])


def test_lowercase_degree_c_is_eligible_without_temperature_label(image):
    item = {"text": "(70°c)", "box": [100, 30, 220, 50]}
    repaired, audit = repair_unit_items([item], image, Recognizer([("(70°C)", 0.98)]))
    assert repaired[0]["text"] == "(70°C)"
    assert audit[0]["applied"]


def test_retry_error_is_preserved_and_does_not_guess(image):
    class BrokenRecognizer:
        def predict(self, crop):
            raise RuntimeError("unavailable")

    repaired, audit = repair_unit_items(entries(), image, BrokenRecognizer())
    assert repaired[1]["text"] == "-42 c"
    assert not audit[0]["applied"]
    assert all(row["error"] == "RuntimeError: unavailable" for row in audit[0]["retries"])
