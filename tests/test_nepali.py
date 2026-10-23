"""``core.nepali`` — Devanagari numerals, unit formatting and label translation.

Why this matters: the Nepali report is the homeowner-facing output. A wrong
digit here is a wrong number in front of the person who paid for the house,
and the AI-narration guard (``core.diff._validate_narration``) relies on
``extract_numbers`` to spot invented figures in both scripts.
"""

from __future__ import annotations

import re

import pytest

from conftest import require

nepali = require("core.nepali")
schema = require("core.schema")

DEVANAGARI = re.compile(r"[\u0900-\u097F]")


# --------------------------------------------------------------------------- #
# digits
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "ascii_text, np_text",
    [
        ("0123456789", "०१२३४५६७८९"),
        ("1.5", "१.५"),
        ("33.3%", "३३.३%"),
        ("W7 is 1.50 m", "W७ is १.५० m"),
        ("", ""),
    ],
)
def test_digit_conversion_round_trips(ascii_text, np_text):
    assert nepali.to_devanagari_digits(ascii_text) == np_text
    assert nepali.to_ascii_digits(np_text) == ascii_text


def test_non_digit_text_is_left_alone():
    text = "भित्ता W — wall"
    assert nepali.to_ascii_digits(nepali.to_devanagari_digits(text)) == text


def test_extract_numbers_reads_both_scripts_as_ascii():
    found = nepali.extract_numbers("drawing 1.50 m; site १ मिटर (३३.३%)")
    assert "1.5" in found or "1.50" in found
    assert "1" in found
    assert "33.3" in found
    assert all(not DEVANAGARI.search(tok) for tok in found), f"tokens should be ASCII: {found}"


def test_extract_numbers_on_text_without_numbers_is_empty():
    assert nepali.extract_numbers("कृपया जाँच गर्नुहोस्") == []


# --------------------------------------------------------------------------- #
# unit formatting
# --------------------------------------------------------------------------- #
def test_format_dimension_uses_devanagari_and_metres():
    assert nepali.format_dimension_np(1.5) == "१.५ मिटर"
    assert nepali.format_dimension_np(2.0) == "२ मिटर"  # trailing .0 dropped


def test_format_area_and_percent():
    assert nepali.format_area_np(21.6) == "२१.६ वर्गमिटर"
    assert nepali.format_percent_np(0.333) == "३३.३%"


@pytest.mark.parametrize("fn", ["format_dimension_np", "format_area_np", "format_percent_np", "format_confidence_np"])
def test_formatters_tolerate_none(fn):
    out = getattr(nepali, fn)(None)
    assert isinstance(out, str) and out, f"{fn}(None) should return a non-empty 'unknown' label"


def test_format_confidence_is_two_decimals():
    assert nepali.format_confidence_np(0.75) == "०.७५"


# --------------------------------------------------------------------------- #
# labels
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "fn, enum_name",
    [("severity_np", "Severity"), ("status_np", "DeltaStatus"), ("stage_np", "Stage")],
)
def test_every_enum_member_has_a_nepali_label(fn, enum_name):
    """A new enum value must not ship untranslated."""
    translate = getattr(nepali, fn)
    for member in getattr(schema, enum_name):
        label = translate(member)
        assert label and DEVANAGARI.search(label), f"{fn}({member.value!r}) -> {label!r}"


@pytest.mark.parametrize(
    "fn, enum_name",
    [("severity_en", "Severity"), ("status_en", "DeltaStatus"), ("stage_en", "Stage")],
)
def test_every_enum_member_has_an_english_label(fn, enum_name):
    translate = getattr(nepali, fn)
    for member in getattr(schema, enum_name):
        assert translate(member), f"{fn}({member.value!r}) is empty"


def test_room_names_translate_and_unknown_names_do_not_crash():
    assert nepali.room_name_np("BEDROOM 1") == "शयनकक्ष १"
    assert nepali.room_name_np("Kitchen") == "भान्सा"
    assert nepali.room_name_np("ZZZ") is None
    assert nepali.room_name_np(None) is None


def test_element_names():
    assert nepali.element_name_np("window") == "झ्याल"
    assert nepali.element_name_np("door") == "ढोका"
    assert DEVANAGARI.search(nepali.element_name_np(None))


def test_and_join_uses_nepali_conjunction():
    assert nepali.and_join_np(["a", "b", "c"]) == "a, b र c"
    assert nepali.and_join_np(["a"]) == "a"
    assert nepali.and_join_np([]) == ""


# --------------------------------------------------------------------------- #
# honesty: weak-evidence sentences
# --------------------------------------------------------------------------- #
def test_weak_evidence_sentence_below_threshold():
    np_txt = nepali.weak_evidence_np(0.3, threshold=0.5)
    en_txt = nepali.weak_evidence_en(0.3, threshold=0.5)
    assert "०.३" in np_txt and DEVANAGARI.search(np_txt)
    assert "0.30" in en_txt and "0.50" in en_txt


def test_weak_evidence_capped_suffix_is_appended():
    plain = nepali.weak_evidence_en(0.3, threshold=0.5)
    capped = nepali.weak_evidence_en(0.3, threshold=0.5, capped=True)
    assert capped.startswith(plain) and len(capped) > len(plain)


@pytest.mark.parametrize("confidence", [0.5, 0.75, 0.9, 1.0])
def test_weak_evidence_never_claims_below_threshold_when_it_is_not(confidence):
    """Regression: weak_evidence_*(0.9) used to say 'confidence 0.90, below 0.50'."""
    assert nepali.weak_evidence_np(confidence, threshold=0.5) == ""
    assert nepali.weak_evidence_en(confidence, threshold=0.5) == ""
