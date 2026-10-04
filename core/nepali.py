"""Karmi — Nepali (Devanagari) language pack.

Everything a homeowner reads is generated from this module. Two rules govern
it:

* Real, natural Nepali, Nepali first — a homeowner in Kathmandu must be able
  to read every sentence without a translator. English follows where a field
  carries both audiences.
* Karmi never asserts a violation. Sentences state what the drawing and the
  photos show, and ask the reader to verify ("कृपया जाँच गर्नुहोस्").

Dependency-free (stdlib only) so the diff engine, the report renderer and
tests can import it without side effects.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# digits
# --------------------------------------------------------------------------- #
_ASCII_TO_DEVANAGARI = str.maketrans("0123456789", "०१२३४५६७८९")
_DEVANAGARI_TO_ASCII = str.maketrans("०१२३४५६७८९", "0123456789")


def to_devanagari_digits(s: str) -> str:
    """'1.5 m' -> '१.५ m'."""
    return str(s).translate(_ASCII_TO_DEVANAGARI)


def to_ascii_digits(s: str) -> str:
    """'१.५' -> '1.5' (inverse of :func:`to_devanagari_digits`)."""
    return str(s).translate(_DEVANAGARI_TO_ASCII)


_NUMBER_RE = re.compile(r"[0-9][0-9.,]*")


def extract_numbers(text: str) -> list[str]:
    """Canonical numeric tokens in ``text`` — used to guard against numbers
    invented by an AI rewrite.

    Both '1.50' and '१.५०' canonicalise to '1.5'; '1,000' to '1000'.
    """
    out: list[str] = []
    for tok in _NUMBER_RE.findall(to_ascii_digits(text or "")):
        tok = tok.rstrip(".,")
        if not tok:
            continue
        try:
            out.append(f"{float(tok.replace(',', '')):g}")
        except ValueError:
            out.append(tok)
    return out


# --------------------------------------------------------------------------- #
# number / dimension formatting
# --------------------------------------------------------------------------- #
def _format_number_np(value: float, decimals: int = 1) -> str:
    v = float(value)
    s = f"{v:.{decimals}f}".rstrip("0").rstrip(".")
    if s in ("", "-") or (v != 0.0 and float(s) == 0.0):
        # value would collapse to "0" at this precision — show more digits
        s = f"{v:.{decimals + 2}f}".rstrip("0").rstrip(".")
    if s in ("", "-") or float(s) == 0.0:
        s = "0"
    return to_devanagari_digits(s)


def format_dimension_np(metres: float | None, *, unit: str = "मिटर", decimals: int = 1) -> str:
    """Render a length the way a homeowner reads it: 1.5 -> '१.५ मिटर'."""
    if metres is None:
        return "थाहा छैन"
    num = _format_number_np(float(metres), decimals)
    return f"{num} {unit}" if unit else num


def format_area_np(m2: float | None, *, unit: str = "वर्गमिटर", decimals: int = 1) -> str:
    """12.3 -> '१२.३ वर्गमिटर'."""
    if m2 is None:
        return "थाहा छैन"
    num = _format_number_np(float(m2), decimals)
    return f"{num} {unit}" if unit else num


def format_percent_np(fraction: float | None, *, decimals: int = 1) -> str:
    """0.333 -> '३३.३%'."""
    if fraction is None:
        return "थाहा छैन"
    return _format_number_np(float(fraction) * 100.0, decimals) + "%"


def format_confidence_np(value: float | None) -> str:
    """0.85 -> '०.८५'."""
    if value is None:
        return "थाहा छैन"
    return _format_number_np(float(value), 2)


# --------------------------------------------------------------------------- #
# element / room names
# --------------------------------------------------------------------------- #
ELEMENT_NAMES_NP: dict[str, str] = {
    "wall": "भित्ता",
    "window": "झ्याल",
    "door": "ढोका",
    "vent": "भेन्ट",
    "opening": "ढोका/झ्याल",
    "room": "कोठा",
    "stair": "सिँढी",
    "kitchen": "भान्सा",
    "bathroom": "शौचालय",
    "bedroom": "शयनकक्ष",
    "living": "बैठक",
    "setback": "सेटब्याक",
    "roof": "छाना",
    "foundation": "जग",
    "column": "स्तम्भ",
    "floor": "भुइँ",
    "slab": "स्ल्याब",
    "other": "अन्य भाग",
    "unknown": "अज्ञात भाग",
}

# room label keywords (English plan text -> Nepali). Longest keys win because
# dict order puts the specific ones first.
ROOM_KEYWORDS_NP: dict[str, str] = {
    "bedroom": "शयनकक्ष",
    "bed": "शयनकक्ष",
    "kitchen": "भान्सा",
    "bathroom": "शौचालय",
    "bath": "शौचालय",
    "toilet": "शौचालय",
    "living": "बैठक",
    "lounge": "बैठक",
    "hall": "बैठक",
    "dining": "भोजन कक्ष",
    "stair": "सिँढी",
    "store": "भण्डार",
    "storage": "भण्डार",
    "balcony": "बाल्कनी",
    "parking": "पार्किङ",
    "porch": "पोर्च",
    "veranda": "बरन्डा",
    "room": "कोठा",
}


def element_name_np(kind_or_name: str | None) -> str:
    """Look up an element name in Nepali; unknown names pass through unchanged."""
    if not kind_or_name:
        return ELEMENT_NAMES_NP["unknown"]
    key = str(kind_or_name).lower().strip()
    return ELEMENT_NAMES_NP.get(key, str(kind_or_name))


def room_name_np(name: str | None) -> str | None:
    """'BEDROOM 1' -> 'शयनकक्ष १'; None when the name is unrecognised."""
    if not name:
        return None
    low = str(name).lower()
    for key, np in ROOM_KEYWORDS_NP.items():
        if key in low:
            nums = re.findall(r"\d+", low)
            return np + ((" " + to_devanagari_digits(nums[0])) if nums else "")
    return None


# --------------------------------------------------------------------------- #
# severity / status / stage words
# --------------------------------------------------------------------------- #
SEVERITY_NP: dict[str, str] = {
    "info": "जानकारी",
    "low": "कम",
    "medium": "मध्यम",
    "high": "उच्च",
}
SEVERITY_EN: dict[str, str] = {
    "info": "info",
    "low": "low",
    "medium": "medium",
    "high": "high",
}

STATUS_NP: dict[str, str] = {
    "matched": "मिल्यो",
    "differs": "फरक देखिन्छ",
    "missing": "साइटमा भेटिएन",
    "unexpected": "नक्सामा भेटिएन",
    "unverifiable": "यकिन भएन",
    "not_covered": "जाँच हुन सकेन",
}
STATUS_EN: dict[str, str] = {
    "matched": "matched",
    "differs": "differs",
    "missing": "missing on site",
    "unexpected": "not in the drawing",
    "unverifiable": "unverifiable",
    "not_covered": "not checked",
}

STAGE_NP: dict[str, str] = {
    "unknown": "अज्ञात",
    "site": "साइट तयारी",
    "foundation": "जग",
    "columns": "स्तम्भ",
    "walls": "भित्ता",
    "slab": "स्ल्याब",
    "roof": "छाना",
    "finishing": "फिनिशिङ",
    "complete": "सम्पन्न",
}
STAGE_EN: dict[str, str] = {
    "unknown": "unknown",
    "site": "site preparation",
    "foundation": "foundation",
    "columns": "columns",
    "walls": "walls",
    "slab": "slab",
    "roof": "roof",
    "finishing": "finishing",
    "complete": "complete",
}

ORIENTATION_NP: dict[str, str] = {
    "horizontal": "तेर्सो",
    "vertical": "ठाडो",
    "diagonal": "तिर्यक",
}


def _enum_key(value) -> str:
    return str(getattr(value, "value", value) or "").lower()


def severity_np(severity) -> str:
    return SEVERITY_NP.get(_enum_key(severity), _enum_key(severity))


def severity_en(severity) -> str:
    return SEVERITY_EN.get(_enum_key(severity), _enum_key(severity))


def status_np(status) -> str:
    return STATUS_NP.get(_enum_key(status), _enum_key(status))


def status_en(status) -> str:
    return STATUS_EN.get(_enum_key(status), _enum_key(status))


def stage_np(stage) -> str:
    return STAGE_NP.get(_enum_key(stage), _enum_key(stage))


def stage_en(stage) -> str:
    return STAGE_EN.get(_enum_key(stage), _enum_key(stage))


def orientation_np(orientation: str | None) -> str:
    return ORIENTATION_NP.get(str(orientation or "").lower(), str(orientation or ""))


def and_join_np(items) -> str:
    """Nepali enumeration: ['भित्ता', 'झ्याल', 'ढोका'] -> 'भित्ता, झ्याल र ढोका'."""
    items = [str(i) for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " र " + items[-1]


# --------------------------------------------------------------------------- #
# measure words
# --------------------------------------------------------------------------- #
MEASURE_NP: dict[str, str] = {
    "length": "लम्बाइ",
    "width": "चौडाइ",
    "area": "क्षेत्रफल",
    "dimension": "नाप",
}
MEASURE_EN: dict[str, str] = {
    "length": "length",
    "width": "width",
    "area": "area",
    "dimension": "size",
}


# --------------------------------------------------------------------------- #
# sentence templates — one per delta, one per verify item
# --------------------------------------------------------------------------- #
# placeholders: {element} {measure} {expected} {observed} {pct}
DELTA_TEMPLATES_NP: dict[str, str] = {
    "matched": "{element} नक्साअनुसार मिल्यो (फरक {pct})।",
    "differs": (
        "नक्साअनुसार {element}को {measure} {expected} छ; साइटमा {observed} देखियो "
        "(लगभग {pct} फरक)। फरक हुन सक्छ, कृपया जाँच गर्नुहोस्।"
    ),
    "missing": (
        "{element} नक्सामा छ, तर साइटको तस्बिरमा भेटिएन — बनिसकेको छैन वा तस्बिरमा "
        "परेको छैन। कृपया जाँच गर्नुहोस्।"
    ),
    "not_covered": (
        "{element} नक्सामा छ, तर साइटका तस्बिरहरूले यो भाग समेटेका छैनन् — त्यसैले "
        "यसको तुलना गर्न सकिएन। यसलाई \"बनेको छैन\" नठान्नुहोस्; यो भागको तस्बिर "
        "वा नाप भेटिएपछि पुनः जाँच गर्न सकिन्छ।"
    ),
    "unexpected": (
        "नक्सामा भेटिएको छैन, तर साइटमा {element} देखियो। कृपया नक्सासँग मिलाएर "
        "जाँच गर्नुहोस्।"
    ),
    "unverifiable": (
        "{element} स्वचालित रूपमा तुलना गर्न सकिएन। कृपया नक्सासँग सिधै मिलाएर "
        "जाँच गर्नुहोस्।"
    ),
}
DELTA_TEMPLATES_EN: dict[str, str] = {
    "matched": "{element} matches the drawing (difference {pct}).",
    "differs": (
        "According to the drawing the {measure} of {element} is {expected}; the site "
        "evidence suggests {observed} (about {pct} difference). This may differ — "
        "please verify."
    ),
    "missing": (
        "{element} is in the drawing but was not found in the site photos — it may not "
        "be built yet or may not be visible. Please verify."
    ),
    "not_covered": (
        "{element} is in the drawing, but the site photos do not cover this part — so it "
        "could not be compared. Do not read this as \"not built\"; it can be checked once "
        "a photo or measurement of this part is available."
    ),
    "unexpected": (
        "{element} was seen on site but was not matched in the drawing. Please check it "
        "against the drawing."
    ),
    "unverifiable": (
        "{element} could not be compared automatically. Please check it directly "
        "against the drawing."
    ),
}

# placeholders: {element} {measure} {expected} {observed}
VERIFY_ITEM_NP: dict[str, str] = {
    "differs": "{element}को {measure} जाँच्नुहोस् (नक्सा: {expected}; साइट: {observed})।",
    "missing": "{element} बनेको छ कि छैन जाँच्नुहोस् — तस्बिरमा भेटिएन।",
    "unexpected": "साइटमा देखिएको {element} नक्सासँग मिल्छ कि मिल्दैन जाँच्नुहोस्।",
    "unverifiable": "{element} नक्सासँग सिधै मिलाएर जाँच्नुहोस्।",
    "not_covered": "{element} तस्बिरमा परेको छैन — यो भाग जाँच्न सकिएन।",
}
VERIFY_ITEM_EN: dict[str, str] = {
    "differs": "Check the {measure} of {element} (drawing: {expected}; site: {observed}).",
    "missing": "Check whether {element} has been built — it was not found in the photos.",
    "unexpected": "Check whether {element} seen on site matches the drawing.",
    "unverifiable": "Check {element} directly against the drawing.",
    "not_covered": "{element} was not covered by the photos — this part could not be checked.",
}
VERIFY_WHY_NP: dict[str, str] = {
    "differs": "नक्सामा {expected} छ, साइटमा {observed} देखियो।",
    "missing": "नक्सामा यो भाग छ, तर साइटको तस्बिरमा भेटिएन।",
    "unexpected": "साइटमा देखियो, तर नक्सासँग मिलेन।",
    "unverifiable": "यो प्रकारको भाग स्वचालित तुलनामा समावेश हुँदैन।",
    "not_covered": "साइटका तस्बिरले सबै भाग समेटेका छैनन्, त्यसैले यसको तुलना गर्न सकिएन।",
}
VERIFY_WHY_EN: dict[str, str] = {
    "differs": "The drawing shows {expected}; the site evidence suggests {observed}.",
    "missing": "This element is in the drawing but was not found in the site photos.",
    "unexpected": "It was seen on site but was not matched in the drawing.",
    "unverifiable": "This element type is not part of the automatic comparison.",
    "not_covered": "The site photos do not cover every part of the building, so this one could not be compared.",
}
VERIFY_HOW_NP = (
    "यो भागको स्पष्ट तस्बिर खिच्नुहोस् वा पुनः नाप्नुहोस्, र आफ्नो इन्जिनियर वा "
    "पालिकाको प्राविधिकसँग जाँच गराउनुहोस्।"
)
VERIFY_HOW_EN = (
    "Take a clear photo of this part or re-measure it, then have your engineer or the "
    "municipality's technician check it."
)

# a matched pair whose dimension could not be computed on one side
UNVERIFIABLE_NO_MEASURE_NP = (
    "{element} मिल्यो, तर एकातर्फ नाप भेटिएन, त्यसैले नापको तुलना गर्न सकिएन। "
    "कृपया आँखाले जाँच गर्नुहोस्।"
)
UNVERIFIABLE_NO_MEASURE_EN = (
    "{element} was matched, but one side has no comparable measurement — no size check "
    "was possible. Please verify visually."
)

# --------------------------------------------------------------------------- #
# weak-evidence lines
# --------------------------------------------------------------------------- #
WEAK_EVIDENCE_NP = (
    "प्रमाण कमजोर छ (विश्वास {confidence}, {threshold} भन्दा कम) — यो अनुमानित हो, "
    "कृपया जाँच गर्नुहोस्।"
)
WEAK_EVIDENCE_EN = (
    "The evidence is weak (confidence {confidence}, below {threshold}) — treat this as "
    "an estimate and verify."
)
WEAK_CAPPED_NP = "प्रमाण कमजोर भएकोले यो बुँदाको गम्भीरता घटाइएको छ।"
WEAK_CAPPED_EN = "Because the evidence is weak, this item's severity was capped."


def weak_evidence_np(confidence: float, *, threshold: float = 0.50, capped: bool = False) -> str:
    base = WEAK_EVIDENCE_NP.format(
        confidence=format_confidence_np(confidence), threshold=format_confidence_np(threshold)
    )
    return f"{base} {WEAK_CAPPED_NP}" if capped else base


def weak_evidence_en(confidence: float, *, threshold: float = 0.50, capped: bool = False) -> str:
    base = WEAK_EVIDENCE_EN.format(
        confidence=f"{float(confidence):.2f}", threshold=f"{float(threshold):.2f}"
    )
    return f"{base} {WEAK_CAPPED_EN}" if capped else base


# --------------------------------------------------------------------------- #
# narration templates (3-6 short lines)
# --------------------------------------------------------------------------- #
NARRATION_NP: dict[str, str] = {
    "intro": "यो प्रतिवेदनले स्वीकृत नक्सा र साइटका तस्बिरहरूबीचको तुलना देखाउँछ।",
    "totals": "जम्मा {total} वटा भाग तुलना गरियो; {matched} वटा नक्सासँग मिले।",
    "verify": "जाँच गर्नुपर्ने {verify} वटा बुँदा भेटिए — तलको सूची हेर्नुहोस्।",
    "verify_none": "यो रनमा जाँच गर्नुपर्ने खासै बुँदा भेटिएन।",
    "high": "{high} वटा बुँदामा ठूलो फरक हुन सक्छ — ध्यान दिनुहोस्।",
    "missing": "{missing} वटा भाग साइटमा भेटिएन; {unexpected} वटा भाग नक्सासँग मिलेन।",
    "limits": "केही कुरा यकिन गर्न सकिएन — तल 'यो रनले यकिन गर्न नसकेका कुरा' हेर्नुहोस्।",
}
NARRATION_EN: dict[str, str] = {
    "intro": "This report compares the approved drawing with the site photos.",
    "totals": "{total} elements were compared; {matched} matched the drawing.",
    "verify": "{verify} items need your verification — see the list below.",
    "verify_none": "Nothing needs your verification in this run.",
    "high": "{high} item(s) may differ substantially — please pay attention.",
    "missing": "{missing} element(s) were not found on site; {unexpected} could not be matched in the drawing.",
    "limits": "Some things could not be determined — see the limits section below.",
}

# --------------------------------------------------------------------------- #
# limits — honest statements about what a run could NOT determine
# (rendered as "Nepali — English" by the diff engine)
# --------------------------------------------------------------------------- #
LIMITS_NP: dict[str, str] = {
    "empty": "तुलना गर्न मिल्ने भाग भेटिएन — नक्सा वा साइट डेटा खाली छ।",
    "no_photos": "कुनै साइट तस्बिर भेटिएन, त्यसैले तुलना सीमित छ।",
    "no_scale": "साइट तस्बिरमा स्केल सन्दर्भ भेटिएन — साइटका नापहरू अनुमानित हुन्।",
    "drawing_scale": "नक्साको स्केल यकिन भएन — नक्साबाट निकालिएका नापहरू अनुमानित हुन्।",
    "raster": "नक्सा रास्टर वा स्क्यानबाट पढिएकोले भित्ता र कोठाको जोडाइ अनुमानित हो।",
    "stage": "साइट {stage_np} चरणमा देखियो — त्यसपछिका चरणका भागहरू अझै नबनेको हुन सक्छ।",
    "no_north": "नक्सामा उत्तर दिशा भेटिएन — दिशा सम्बन्धी तुलना गरिएको छैन।",
    "dims_unused": (
        "नक्सामा लेखिएका नापहरू (dimensions) यो तुलनामा प्रयोग गरिएको छैन — तुलना "
        "ज्यामितीय मोडेलमा आधारित छ।"
    ),
    "uncomparable": (
        "स्तम्भ, छाना, सेटब्याक जस्ता केही भाग नक्सा मोडेलमा नभएकोले स्वचालित तुलना "
        "गर्न सकिएन — ती जाँच्ने सूचीमा छन्।"
    ),
    "weak": (
        "केही बुँदा कमजोर प्रमाणमा आधारित छन् (विश्वास ०.५० भन्दा कम) — तिनको "
        "गम्भीरता घटाइएको छ।"
    ),
    "coverage": (
        "साइटका तस्बिरले नक्साका {total} भागमध्ये {covered} भाग मात्र समेटेका छन् — "
        "बाँकी {uncovered} भाग जाँच्न सकिएन। ती भागको तस्बिर वा नाप थप्नुभयो भने "
        "तुलनामा समावेश हुनेछ।"
    ),
    "baseline": (
        "यो स्वचालित तुलना हो, कानुनी प्रमाण होइन — शंका लागेमा आफ्नो इन्जिनियर वा "
        "पालिकासँग जाँच गराउनुहोस्।"
    ),
}
LIMITS_EN: dict[str, str] = {
    "empty": "No comparable elements were found — the drawing or the site data was empty.",
    "no_photos": "No site photos were provided, so the comparison is limited.",
    "no_scale": "No scale reference was found in the site photos — site sizes are approximate.",
    "drawing_scale": "The drawing scale could not be confirmed — drawing dimensions are approximate.",
    "raster": "The drawing was read from a raster or scan, so wall and room topology is approximate.",
    "stage": "The site appears to be at the {stage_en} stage — later-stage elements may simply not be built yet.",
    "no_north": "No north direction was found in the drawing — no orientation-dependent comparison was made.",
    "dims_unused": "Written dimensions in the drawing were not used — the comparison is based on the geometry model only.",
    "uncomparable": "Some element types (e.g. column, roof, setback) are not part of the drawing model, so they could not be compared automatically — they are in the verify list.",
    "weak": "Some items rest on weak evidence (confidence below 0.50) — their severity was capped.",
    "coverage": "The site photos cover only {covered} of {total} drawn elements — the remaining {uncovered} could not be checked at all. Add photos or measurements of those parts to include them.",
    "baseline": "This is an automated comparison, not legal evidence — when in doubt, verify with your engineer or the municipality.",
}


__all__ = [
    "to_devanagari_digits",
    "to_ascii_digits",
    "extract_numbers",
    "format_dimension_np",
    "format_area_np",
    "format_percent_np",
    "format_confidence_np",
    "ELEMENT_NAMES_NP",
    "ROOM_KEYWORDS_NP",
    "element_name_np",
    "room_name_np",
    "SEVERITY_NP",
    "SEVERITY_EN",
    "STATUS_NP",
    "STATUS_EN",
    "STAGE_NP",
    "STAGE_EN",
    "ORIENTATION_NP",
    "severity_np",
    "severity_en",
    "status_np",
    "status_en",
    "stage_np",
    "stage_en",
    "orientation_np",
    "and_join_np",
    "MEASURE_NP",
    "MEASURE_EN",
    "DELTA_TEMPLATES_NP",
    "DELTA_TEMPLATES_EN",
    "VERIFY_ITEM_NP",
    "VERIFY_ITEM_EN",
    "VERIFY_WHY_NP",
    "VERIFY_WHY_EN",
    "VERIFY_HOW_NP",
    "VERIFY_HOW_EN",
    "UNVERIFIABLE_NO_MEASURE_NP",
    "UNVERIFIABLE_NO_MEASURE_EN",
    "WEAK_EVIDENCE_NP",
    "WEAK_EVIDENCE_EN",
    "weak_evidence_np",
    "weak_evidence_en",
    "NARRATION_NP",
    "NARRATION_EN",
    "LIMITS_NP",
    "LIMITS_EN",
]