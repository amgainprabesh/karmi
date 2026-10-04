"""Karmi — comparison engine: approved drawing vs as-built evidence.

``diff_scene(scene, observed, ai=None)`` compares the two machine-readable
models element by element and returns a :class:`~core.schema.DiffReport` full
of items to VERIFY — never assertions of violation.

Matching order (deterministic)
------------------------------
1. An observed element whose ``matches_scene_id`` names a scene element is
   paired with it directly — explicit wins.
2. Otherwise geometry decides, scene element by scene element:
   * walls   — length within ±WALL_LENGTH_TOL (15%) *and* compatible
               orientation (only enforced when the observed side states one),
   * openings — compatible kind first, then nearest width within
               ±OPENING_WIDTH_TOL (50%; a 1.5 m window built at 1.0 m is
               still the same window, and the delta is the product),
   * rooms   — area within ±ROOM_AREA_TOL (20%).
3. A scene element that never matches is MISSING ("in the drawing, not found
   on site"); a comparable observed element that never matches is
   UNEXPECTED. Both are verify items, never accusations. Element kinds the
   scene model cannot express (column / slab / roof / setback, generic
   "other") are reported UNVERIFIABLE with an explicit reason instead —
   calling an observed roof "unexpected" would be a claim this run cannot
   make.

Severity thresholds (relative difference on the primary dimension)
------------------------------------------------------------------
    <=  5%   -> info      (within tolerance; the pair is reported MATCHED)
    <= 12%   -> low
    <= 25%   -> medium
    >  25%   -> high
Exposed as DIFF_INFO_MAX / DIFF_LOW_MAX / DIFF_MEDIUM_MAX so they are
tunable and testable. Unmatched elements get a kind-based severity
(MISSING_SEVERITY / UNEXPECTED_SEVERITY).

Honesty rules
-------------
* ``delta.confidence`` = min(confidence of the scene side, confidence of the
  observed side). Below CONFIDENCE_CAP (0.50) the severity is capped at
  "low" and the reason says, explicitly, that the evidence is weak.
* ``report.limits`` always lists what this run could NOT determine.
* ``narrate()`` fills narration from deterministic templates; an injected
  ``ai`` (open-weight provider, e.g. anything exposing ``complete(prompt)``)
  may rewrite the Nepali only, and its output is rejected — template kept,
  warning added — if it introduces numbers that were not computed here.
"""

from __future__ import annotations

import math
import re
from typing import Any

from core import nepali
from core.schema import (
    Delta,
    DeltaStatus,
    DiffReport,
    ElementKind,
    ObservedElement,
    ObservedState,
    Opening,
    OpeningKind,
    Room,
    SceneGraph,
    Severity,
    SourceKind,
    Stage,
    VerifyItem,
    Wall,
)

# --------------------------------------------------------------------------- #
# tunables (documented in the module docstring)
# --------------------------------------------------------------------------- #
DIFF_INFO_MAX = 0.05      # <= 5%   -> info / matched
DIFF_LOW_MAX = 0.12       # <= 12%  -> low
DIFF_MEDIUM_MAX = 0.25    # <= 25%  -> medium;  > 25% -> high
CONFIDENCE_CAP = 0.50     # below this, severity is capped at "low"
WALL_LENGTH_TOL = 0.15    # wall length match window (±15%)
OPENING_WIDTH_TOL = 0.50  # opening width match window (±50%)
ROOM_AREA_TOL = 0.20      # room area match window (±20%)
ORIENTATION_TOL_DEG = 25.0

#: Coverage guard — absence of evidence is not evidence of absence.
#: If the site evidence could only be compared against fewer than this share of the
#: drawn elements, the site is only *partially documented*. An unmatched drawn
#: element is then reported as "not checked" (UNVERIFIABLE, low severity) instead of
#: "missing on site" (MISSING, high severity), and a limit line states the coverage.
#: Rationale: a handful of photos of one facade must never make the report claim that
#: seven walls are absent — that would frighten a homeowner with a false finding.
COVERAGE_SPARSE_RATIO = 0.50

SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.INFO,
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
)

# severity of an unmatched element, by element type
MISSING_SEVERITY: dict[str, Severity] = {
    "wall": Severity.HIGH,
    "opening": Severity.MEDIUM,
    "room": Severity.MEDIUM,
}
UNEXPECTED_SEVERITY: dict[str, Severity] = {
    "wall": Severity.HIGH,
    "opening": Severity.MEDIUM,
    "room": Severity.MEDIUM,
}

# observed kinds that the scene graph can express (wall / opening / room-like)
_UNCOMPARABLE_OBSERVED_KINDS = (
    ElementKind.COLUMN,
    ElementKind.SLAB,
    ElementKind.ROOF,
    ElementKind.SETBACK,
)

# approx_size key aliases — extraction agents may use any of these
_LENGTH_KEYS = ("length", "length_m", "len", "l")
_WIDTH_KEYS = ("width", "width_m", "w")
_HEIGHT_KEYS = ("height", "height_m", "h")
_AREA_KEYS = ("area", "area_m2", "area_sqm", "area_m²", "floor_area")
_ORIENTATION_KEYS = ("orientation_deg", "angle_deg", "orientation", "angle", "bearing_deg")

_MEASURE_BY_TYPE = {"wall": "length", "opening": "width", "room": "area"}
_KEYS_BY_MEASURE = {"length": _LENGTH_KEYS, "width": _WIDTH_KEYS, "area": _AREA_KEYS}


# --------------------------------------------------------------------------- #
# small numeric helpers
# --------------------------------------------------------------------------- #
def severity_for_relative_diff(rel: float) -> Severity:
    """Map a relative difference to a severity using the documented thresholds."""
    if rel <= DIFF_INFO_MAX:
        return Severity.INFO
    if rel <= DIFF_LOW_MAX:
        return Severity.LOW
    if rel <= DIFF_MEDIUM_MAX:
        return Severity.MEDIUM
    return Severity.HIGH


def _rel_diff(observed: float, expected: float) -> float:
    exp = abs(float(expected))
    if exp < 1e-9:
        return 0.0 if abs(float(observed)) < 1e-9 else 1.0
    return abs(float(observed) - float(expected)) / exp


def _severity_rank(sev: Severity) -> int:
    try:
        return SEVERITY_ORDER.index(sev)
    except ValueError:
        return 0


def _cap_severity(sev: Severity) -> Severity:
    """Cap severity at 'low' (info and low pass through unchanged)."""
    return sev if _severity_rank(sev) <= _severity_rank(Severity.LOW) else Severity.LOW


def _fmt_measure(measure: str, value: float | None) -> str | None:
    if value is None:
        return None
    if measure == "area":
        return f"{float(value):.1f} m²"
    return f"{float(value):.2f} m"


def _fmt_measure_np(measure: str, value: float | None) -> str | None:
    if value is None:
        return None
    if measure == "area":
        return nepali.format_area_np(float(value), decimals=1)
    return nepali.format_dimension_np(float(value), decimals=2)


# --------------------------------------------------------------------------- #
# reading the two models
# --------------------------------------------------------------------------- #
def _prov_confidence(obj: Any) -> float:
    """Confidence of an element — or of a bare Provenance passed directly."""
    prov = getattr(obj, "provenance", None)
    if prov is None:
        prov = obj
    try:
        return max(0.0, min(1.0, float(getattr(prov, "confidence", 0.0) or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _obs_measure(oe: ObservedElement, keys: tuple[str, ...]) -> float | None:
    size = getattr(oe, "approx_size", None) or {}
    for key in keys:
        raw = size.get(key)
        if raw is None or isinstance(raw, bool):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _obs_orientation(oe: ObservedElement) -> float | None:
    size = getattr(oe, "approx_size", None) or {}
    for key in _ORIENTATION_KEYS:
        raw = size.get(key)
        if raw is None or isinstance(raw, bool):
            continue
        try:
            return float(raw) % 180.0
        except (TypeError, ValueError):
            continue
    return None


def _wall_angle_deg(w: Wall) -> float:
    return math.degrees(math.atan2(w.end[1] - w.start[1], w.end[0] - w.start[0])) % 180.0


def _wall_orientation(w: Wall) -> str:
    a = _wall_angle_deg(w)
    if a < 10.0 or a > 170.0:
        return "horizontal"
    if 80.0 <= a <= 100.0:
        return "vertical"
    return "diagonal"


def _angle_gap(a: float, b: float) -> float:
    d = abs((a - b) % 180.0)
    return min(d, 180.0 - d)


def _orientation_ok(w: Wall, oe: ObservedElement) -> bool:
    """Walls match on orientation too — but only when the observed side states one."""
    obs_deg = _obs_orientation(oe)
    if obs_deg is None:
        return True
    return _angle_gap(_wall_angle_deg(w), obs_deg) <= ORIENTATION_TOL_DEG


def _obs_opening_kind(oe: ObservedElement) -> OpeningKind:
    hint = (getattr(oe, "location_hint", None) or "").lower()
    if "window" in hint or "झ्याल" in hint:
        return OpeningKind.WINDOW
    if "door" in hint or "ढोका" in hint:
        return OpeningKind.DOOR
    if "vent" in hint or "भेन्ट" in hint:
        return OpeningKind.VENT
    return OpeningKind.UNKNOWN


def _opening_kinds_ok(scene_kind: OpeningKind, obs_kind: OpeningKind) -> bool:
    if obs_kind == OpeningKind.UNKNOWN or scene_kind == OpeningKind.UNKNOWN:
        return True
    return scene_kind == obs_kind


def _room_area(r: Room) -> float | None:
    if r.area_m2 and r.area_m2 > 0:
        return float(r.area_m2)
    poly = list(r.polygon or [])
    if len(poly) >= 3:
        area = 0.0
        for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
            area += x1 * y2 - x2 * y1
        area = abs(area) / 2.0
        return area if area > 0 else None
    return None


def _scene_measure(t: str, obj: Any) -> float | None:
    if t == "wall":
        return float(obj.length)
    if t == "opening":
        return float(obj.width) if obj.width and obj.width > 0 else None
    if t == "room":
        return _room_area(obj)
    return None


def _is_room_like(oe: ObservedElement) -> bool:
    return oe.kind == ElementKind.OTHER and _obs_measure(oe, _AREA_KEYS) is not None


def _observed_comparable(oe: ObservedElement) -> bool:
    if oe.kind in (ElementKind.WALL, ElementKind.OPENING):
        return True
    return _is_room_like(oe)


def _describe_obs_size(oe: ObservedElement) -> str | None:
    parts: list[str] = []
    for label, keys, unit in (
        ("length", _LENGTH_KEYS, "m"),
        ("width", _WIDTH_KEYS, "m"),
        ("height", _HEIGHT_KEYS, "m"),
        ("area", _AREA_KEYS, "m²"),
    ):
        value = _obs_measure(oe, keys)
        if value is not None:
            parts.append(f"{label} {value:.2f} {unit}")
    return ", ".join(parts) or None


# --------------------------------------------------------------------------- #
# labels
# --------------------------------------------------------------------------- #
def _label_scene(t: str, obj: Any, *, np: bool) -> str:
    if t == "wall":
        orientation = _wall_orientation(obj)
        if np:
            return f"भित्ता ({nepali.orientation_np(orientation)}, {obj.id})"
        return f"wall ({orientation}, {obj.id})"
    if t == "opening":
        kind_np = nepali.element_name_np(getattr(obj.kind, "value", obj.kind))
        kind_en = str(getattr(obj.kind, "value", obj.kind))
        if obj.wall_id:
            return f"{kind_np} (भित्ता {obj.wall_id})" if np else f"{kind_en} on wall {obj.wall_id}"
        return f"{kind_np} ({obj.id})" if np else f"{kind_en} ({obj.id})"
    # room
    name_np = nepali.room_name_np(obj.name)
    if np:
        return name_np or f"कोठा ({obj.id})"
    return f"room '{obj.name}'" if obj.name else f"room ({obj.id})"


def _label_observed(oe: ObservedElement, *, np: bool) -> str:
    loc = getattr(oe, "location_hint", None) or oe.id
    if oe.kind == ElementKind.OPENING:
        kind = _obs_opening_kind(oe)
        key = kind.value if kind != OpeningKind.UNKNOWN else "opening"
        if str(loc).strip().lower() == key:  # hint repeats the kind — use the id
            loc = oe.id
        return f"{nepali.element_name_np(key)} ({loc})" if np else f"{key} ({loc})"
    if oe.kind == ElementKind.WALL:
        return f"भित्ता ({loc})" if np else f"wall ({loc})"
    if _is_room_like(oe):
        return f"कोठा ({loc})" if np else f"room ({loc})"
    name = nepali.element_name_np(getattr(oe.kind, "value", oe.kind))
    kind = str(getattr(oe.kind, "value", oe.kind))
    return f"{name} ({loc})" if np else f"{kind} ({loc})"


# --------------------------------------------------------------------------- #
# candidate scoring (used by the geometric matching pass)
# --------------------------------------------------------------------------- #
def _candidate_rel(t: str, obj: Any, oe: ObservedElement) -> float | None:
    """Relative difference if this observed element can be this scene element,
    else None. ``inf`` means "compatible but no comparable measurement"."""
    if t == "wall":
        if oe.kind != ElementKind.WALL:
            return None
        obs_len = _obs_measure(oe, _LENGTH_KEYS)
        if obs_len is None:
            return None
        rel = _rel_diff(obs_len, obj.length)
        if rel > WALL_LENGTH_TOL:
            return None
        if not _orientation_ok(obj, oe):
            return None
        return rel
    if t == "opening":
        if oe.kind != ElementKind.OPENING:
            return None
        if not _opening_kinds_ok(obj.kind, _obs_opening_kind(oe)):
            return None
        obs_w = _obs_measure(oe, _WIDTH_KEYS)
        if obs_w is not None and obj.width is not None:
            rel = _rel_diff(obs_w, obj.width)
            if rel > OPENING_WIDTH_TOL:
                return None
            return rel
        return float("inf")
    if t == "room":
        if not _is_room_like(oe):
            return None
        area = _room_area(obj)
        obs_area = _obs_measure(oe, _AREA_KEYS)
        if area is None or obs_area is None:
            return None
        rel = _rel_diff(obs_area, area)
        if rel > ROOM_AREA_TOL:
            return None
        return rel
    return None


# --------------------------------------------------------------------------- #
# delta builders — every one returns (Delta, ctx) where ctx carries the
# extra strings the verify-item templates need.
# --------------------------------------------------------------------------- #
def _weak_suffixes(confidence: float, raw: Severity) -> tuple[str, str]:
    capped = _severity_rank(raw) > _severity_rank(Severity.LOW)
    np_txt = nepali.weak_evidence_np(confidence, threshold=CONFIDENCE_CAP, capped=capped)
    en_txt = nepali.weak_evidence_en(confidence, threshold=CONFIDENCE_CAP, capped=capped)
    return np_txt, en_txt


def _pair_delta(did: str, t: str, obj: Any, oe: ObservedElement) -> tuple[Delta, dict[str, Any]]:
    measure = _MEASURE_BY_TYPE[t]
    exp_v = _scene_measure(t, obj)
    obs_v = _obs_measure(oe, _KEYS_BY_MEASURE[measure])
    confidence = min(_prov_confidence(obj), _prov_confidence(oe))
    weak = confidence < CONFIDENCE_CAP
    label_en = _label_scene(t, obj, np=False)
    label_np = _label_scene(t, obj, np=True)
    expected = _fmt_measure(measure, exp_v)
    observed = _fmt_measure(measure, obs_v)
    expected_np = _fmt_measure_np(measure, exp_v)
    observed_np = _fmt_measure_np(measure, obs_v)

    if exp_v is not None and obs_v is not None:
        rel = _rel_diff(obs_v, exp_v)
        raw = severity_for_relative_diff(rel)
        status = DeltaStatus.MATCHED if raw == Severity.INFO else DeltaStatus.DIFFERS
        severity = _cap_severity(raw) if weak else raw
        pct = f"{rel:.1%}"
        pct_np = nepali.format_percent_np(rel, decimals=1)
        reason_np = nepali.DELTA_TEMPLATES_NP[status.value].format(
            element=label_np,
            measure=nepali.MEASURE_NP[measure],
            expected=expected_np or "",
            observed=observed_np or "",
            pct=pct_np,
        )
        reason = nepali.DELTA_TEMPLATES_EN[status.value].format(
            element=label_en,
            measure=nepali.MEASURE_EN[measure],
            expected=expected or "",
            observed=observed or "",
            pct=pct,
        )
    else:
        status = DeltaStatus.UNVERIFIABLE
        raw = Severity.LOW
        severity = raw
        reason_np = nepali.UNVERIFIABLE_NO_MEASURE_NP.format(element=label_np)
        reason = nepali.UNVERIFIABLE_NO_MEASURE_EN.format(element=label_en)

    if weak:
        weak_np, weak_en = _weak_suffixes(confidence, raw)
        reason_np = f"{reason_np} {weak_np}"
        reason = f"{reason} {weak_en}"

    delta = Delta(
        id=did,
        element=label_en,
        scene_ref=getattr(obj, "id", None),
        observed_ref=oe.id,
        status=status,
        expected=expected,
        observed=observed,
        severity=severity,
        confidence=round(confidence, 4),
        reason=reason,
        reason_np=reason_np,
    )
    ctx: dict[str, Any] = {
        "status": status.value,
        "element_np": label_np,
        "element_en": label_en,
        "measure_np": nepali.MEASURE_NP[measure],
        "measure_en": nepali.MEASURE_EN[measure],
        "expected_np": expected_np,
        "observed_np": observed_np,
        "expected": expected,
        "observed": observed,
        "weak": weak,
        "confidence": confidence,
    }
    return delta, ctx


def _missing_delta(
    did: str, t: str, obj: Any, *, sparse: bool = False
) -> tuple[Delta, dict[str, Any]]:
    """An unmatched drawn element.

    ``sparse=True`` means the site evidence does not cover enough of the building for
    "not found in the photos" to mean anything — so the honest report is "could not be
    checked", not "missing". Severity drops to LOW and the wording says why.
    """
    measure = _MEASURE_BY_TYPE[t]
    exp_v = _scene_measure(t, obj)
    confidence = _prov_confidence(obj)
    weak = confidence < CONFIDENCE_CAP
    label_en = _label_scene(t, obj, np=False)
    label_np = _label_scene(t, obj, np=True)

    if sparse:
        severity = Severity.LOW
        reason_np = nepali.DELTA_TEMPLATES_NP["not_covered"].format(element=label_np)
        reason = nepali.DELTA_TEMPLATES_EN["not_covered"].format(element=label_en)
        status = DeltaStatus.UNVERIFIABLE
        status_key = "not_covered"
    else:
        raw = MISSING_SEVERITY.get(t, Severity.MEDIUM)
        severity = _cap_severity(raw) if weak else raw
        reason_np = nepali.DELTA_TEMPLATES_NP["missing"].format(element=label_np)
        reason = nepali.DELTA_TEMPLATES_EN["missing"].format(element=label_en)
        if weak:
            weak_np, weak_en = _weak_suffixes(confidence, raw)
            reason_np = f"{reason_np} {weak_np}"
            reason = f"{reason} {weak_en}"
        status = DeltaStatus.MISSING
        status_key = "missing"

    delta = Delta(
        id=did,
        element=label_en,
        scene_ref=getattr(obj, "id", None),
        observed_ref=None,
        status=status,
        expected=_fmt_measure(measure, exp_v),
        observed=None,
        severity=severity,
        confidence=round(confidence, 4),
        reason=reason,
        reason_np=reason_np,
    )
    ctx: dict[str, Any] = {
        "status": status_key,
        "element_np": label_np,
        "element_en": label_en,
        "measure_np": nepali.MEASURE_NP[measure],
        "measure_en": nepali.MEASURE_EN[measure],
        "expected_np": _fmt_measure_np(measure, exp_v),
        "observed_np": None,
        "expected": _fmt_measure(measure, exp_v),
        "observed": None,
        "weak": weak,
        "confidence": confidence,
    }
    return delta, ctx


def _observed_only_delta(did: str, oe: ObservedElement) -> tuple[Delta, dict[str, Any]]:
    confidence = _prov_confidence(oe)
    weak = confidence < CONFIDENCE_CAP
    label_en = _label_observed(oe, np=False)
    label_np = _label_observed(oe, np=True)

    if _observed_comparable(oe):
        status = DeltaStatus.UNEXPECTED
        key = "room" if _is_room_like(oe) else ("wall" if oe.kind == ElementKind.WALL else "opening")
        measure = _MEASURE_BY_TYPE[key]
        raw = UNEXPECTED_SEVERITY.get(key, Severity.MEDIUM)
        severity = _cap_severity(raw) if weak else raw
        obs_v = _obs_measure(oe, _KEYS_BY_MEASURE[measure])
        observed = _fmt_measure(measure, obs_v)
        observed_np = _fmt_measure_np(measure, obs_v)
        reason_np = nepali.DELTA_TEMPLATES_NP["unexpected"].format(element=label_np)
        reason = nepali.DELTA_TEMPLATES_EN["unexpected"].format(element=label_en)
    else:
        status = DeltaStatus.UNVERIFIABLE
        measure = "dimension"
        raw = Severity.LOW
        severity = raw
        observed = _describe_obs_size(oe)
        observed_np = observed
        reason_np = nepali.DELTA_TEMPLATES_NP["unverifiable"].format(element=label_np)
        reason = nepali.DELTA_TEMPLATES_EN["unverifiable"].format(element=label_en)

    if weak:
        weak_np, weak_en = _weak_suffixes(confidence, raw)
        reason_np = f"{reason_np} {weak_np}"
        reason = f"{reason} {weak_en}"

    delta = Delta(
        id=did,
        element=label_en,
        scene_ref=None,
        observed_ref=oe.id,
        status=status,
        expected=None,
        observed=observed,
        severity=severity,
        confidence=round(confidence, 4),
        reason=reason,
        reason_np=reason_np,
    )
    ctx: dict[str, Any] = {
        "status": status.value,
        "element_np": label_np,
        "element_en": label_en,
        "measure_np": nepali.MEASURE_NP[measure],
        "measure_en": nepali.MEASURE_EN[measure],
        "expected_np": None,
        "observed_np": observed_np,
        "expected": None,
        "observed": observed,
        "weak": weak,
        "confidence": confidence,
    }
    return delta, ctx


def _make_verify(vid: str, delta: Delta, ctx: dict[str, Any]) -> VerifyItem:
    status = ctx["status"]
    fmt = {
        "element": ctx["element_np"],
        "measure": ctx["measure_np"],
        "expected": ctx["expected_np"] or "—",
        "observed": ctx["observed_np"] or "—",
    }
    item_np = nepali.VERIFY_ITEM_NP.get(status, nepali.VERIFY_ITEM_NP["unverifiable"]).format(**fmt)
    item = nepali.VERIFY_ITEM_EN.get(status, nepali.VERIFY_ITEM_EN["unverifiable"]).format(
        element=ctx["element_en"],
        measure=ctx["measure_en"],
        expected=ctx["expected"] or "—",
        observed=ctx["observed"] or "—",
    )
    why_np = nepali.VERIFY_WHY_NP.get(status, nepali.VERIFY_WHY_NP["unverifiable"]).format(
        expected=ctx["expected_np"] or "—", observed=ctx["observed_np"] or "—"
    )
    why_en = nepali.VERIFY_WHY_EN.get(status, nepali.VERIFY_WHY_EN["unverifiable"]).format(
        expected=ctx["expected"] or "—", observed=ctx["observed"] or "—"
    )
    if ctx["weak"]:
        why_np = f"{why_np} {nepali.weak_evidence_np(ctx['confidence'], threshold=CONFIDENCE_CAP)}"
        why_en = f"{why_en} {nepali.weak_evidence_en(ctx['confidence'], threshold=CONFIDENCE_CAP)}"
    return VerifyItem(
        id=vid,
        item=item,
        item_np=item_np,
        why=f"{why_np} — {why_en}",
        how=f"{nepali.VERIFY_HOW_NP} — {nepali.VERIFY_HOW_EN}",
        severity=delta.severity,
        delta_ref=delta.id,
    )


# --------------------------------------------------------------------------- #
# limits
# --------------------------------------------------------------------------- #
def _build_limits(
    scene: SceneGraph,
    observed: ObservedState,
    deltas: list[Delta],
    *,
    matched: int = 0,
    total: int = 0,
) -> list[str]:
    out: list[str] = []

    def add(key: str, **fmt: Any) -> None:
        np_txt = nepali.LIMITS_NP[key].format(**fmt)
        en_txt = nepali.LIMITS_EN[key].format(**fmt)
        out.append(f"{np_txt} — {en_txt}")

    if not deltas:
        add("empty")
    if not observed.captures and not observed.elements:
        add("no_photos")

    meta = observed.meta or {}
    has_scale = bool(meta.get("known_dimension_m")) or any(
        str(getattr(sr, "kind", "unknown")) != "unknown" and float(getattr(sr, "value", 0) or 0) > 0
        for sr in observed.scale_refs
    )
    if not has_scale:
        add("no_scale")

    if scene.scale_m_per_unit is None or _prov_confidence(scene.scale_provenance) < 0.5:
        add("drawing_scale")
    if scene.source_kind in (SourceKind.RASTER_PDF, SourceKind.SCAN):
        add("raster")
    if observed.stage not in (Stage.UNKNOWN, Stage.COMPLETE):
        add("stage", stage_np=nepali.stage_np(observed.stage), stage_en=nepali.stage_en(observed.stage))
    if scene.north_deg is None:
        add("no_north")
    if scene.dimensions:
        add("dims_unused")
    if any(oe.kind in _UNCOMPARABLE_OBSERVED_KINDS for oe in observed.elements) or any(
        oe.kind == ElementKind.OTHER and not _is_room_like(oe) for oe in observed.elements
    ):
        add("uncomparable")
    if any((d.confidence or 0.0) < CONFIDENCE_CAP for d in deltas):
        add("weak")

    # coverage — only worth stating when the site evidence is genuinely partial
    if total > 0 and matched < total:
        add("coverage", covered=matched, total=total, uncovered=total - matched)

    add("baseline")  # always last, always present
    return out


# --------------------------------------------------------------------------- #
# narration
# --------------------------------------------------------------------------- #
_NARRATION_SYSTEM = (
    "तपाईं कर्मी (Karmi) का लागि नेपाली भाषा सम्पादक हुनुहुन्छ। घरधनीले पढ्ने सरल, "
    "स्वाभाविक नेपाली लेख्नुहुन्छ। कुनै पनि संख्या, नाप वा तथ्य परिवर्तन वा थप "
    "गर्नुहुन्न। 'उल्लंघन' वा 'गल्ती' जस्ता शब्द प्रयोग गर्नुहुन्न — सधैँ जाँच गर्न "
    "आग्रह गर्नुहुन्छ।"
)


def _narration_prompt(lines: list[str]) -> str:
    return (
        f"तलका {len(lines)} हरफहरू घरधनीका लागि सरल र स्वाभाविक नेपालीमा पुनर्लेखन "
        "गर्नुहोस्।\nनियम:\n"
        "- हरफको संख्या उस्तै राख्नुहोस् (हरेक हरफ एउटै लाइनमा)।\n"
        "- कुनै संख्या, नाप वा तथ्य थप्नु, हटाउनु वा बदल्नु हुँदैन।\n"
        "- कुनै नयाँ जानकारी थप्नु हुँदैन; जाँच गर्न आग्रह गर्ने शैली राख्नुहोस्।\n\n"
        "हरफहरू:\n" + "\n".join(lines)
    )


def _coerce_ai_text(out: Any) -> str | None:
    if isinstance(out, str):
        return out if out.strip() else None
    if isinstance(out, (list, tuple)):
        text = "\n".join(str(x) for x in out if str(x).strip())
        return text or None
    if isinstance(out, dict):
        for key in ("text", "content", "message", "output"):
            if isinstance(out.get(key), str) and out[key].strip():
                return out[key]
    return None


def _call_ai_text(ai: Any, prompt: str, system: str) -> tuple[str | None, str | None]:
    """Best-effort call of an injected open-weight provider.

    Duck-typed on purpose (the provider layer is a separate workstream):
    tries ``complete`` / ``generate`` / ``chat`` / ``rewrite`` / ``narrate``.
    Returns ``(text, None)`` or ``(None, reason)`` — never raises.
    """
    errors: list[str] = []
    for name in ("complete", "generate", "chat", "rewrite", "narrate"):
        fn = getattr(ai, name, None)
        if not callable(fn):
            continue
        try:
            if name == "chat":
                out = fn([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
            else:
                try:
                    out = fn(prompt, system=system)
                except TypeError:
                    out = fn(prompt)
            text = _coerce_ai_text(out)
            if text:
                return text, None
            errors.append(f"{name}() returned no usable text")
        except Exception as exc:  # noqa: BLE001 — an optional hook must never break the run
            errors.append(f"{name}() failed: {type(exc).__name__}: {exc}")
    return None, "; ".join(errors) if errors else "no usable ai method"


def _parse_ai_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in str(text).splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"^(?:[-*•‣]+|\d{1,3}[.)]|[०-९]{1,3}[.)])\s*", "", s).strip()
        if s:
            lines.append(s)
    return lines


def _allowed_numbers(report: DiffReport, template_lines: list[str]) -> set[str]:
    chunks: list[str] = list(template_lines) + list(report.narration_en) + list(report.limits)
    for d in report.deltas:
        chunks.append(f"{d.expected or ''} {d.observed or ''} {d.reason or ''} {d.reason_np or ''}")
    for v in report.verify_list:
        chunks.append(f"{v.item} {v.item_np or ''} {v.why or ''} {v.how or ''}")
    allowed: set[str] = set()
    for chunk in chunks:
        allowed.update(nepali.extract_numbers(chunk))
    return allowed


def _validate_narration(candidate: list[str], template_lines: list[str], report: DiffReport) -> list[str]:
    problems: list[str] = []
    if len(candidate) != len(template_lines):
        problems.append(f"expected {len(template_lines)} lines, got {len(candidate)}")
    if not (3 <= len(candidate) <= 6):
        problems.append(f"line count {len(candidate)} is outside 3..6")
    allowed = _allowed_numbers(report, template_lines)
    for i, line in enumerate(candidate, 1):
        if len(line) > 240:
            problems.append(f"line {i} is too long")
        if not re.search(r"[\u0900-\u097F]", line):
            problems.append(f"line {i} contains no Devanagari text")
        bad = [tok for tok in nepali.extract_numbers(line) if tok not in allowed]
        if bad:
            problems.append(f"line {i} introduces unverified number(s): {', '.join(bad)}")
    return problems


def narrate(report: DiffReport, *, ai: Any = None) -> DiffReport:
    """Fill ``narration_np`` and ``narration_en`` with 3-6 short plain lines.

    The deterministic template version always works. When ``ai`` is injected
    it may rewrite the NEPALI lines for fluency; the rewrite is kept only if
    it has the same line count, stays Nepali, and contains no numeric token
    that the diff did not compute. Otherwise the template is kept and a
    warning is recorded in ``report.meta``.
    """
    report.recount()
    summary = report.summary or {}
    total = int(summary.get("total", 0))
    matched = int(summary.get("matched", 0))
    verify = int(summary.get("verify_items", 0))
    high = int(summary.get("high", 0))
    missing = sum(1 for d in report.deltas if d.status == DeltaStatus.MISSING)
    unexpected = sum(1 for d in report.deltas if d.status == DeltaStatus.UNEXPECTED)
    dev = nepali.to_devanagari_digits

    np_lines: list[str] = [
        nepali.NARRATION_NP["intro"],
        nepali.NARRATION_NP["totals"].format(total=dev(str(total)), matched=dev(str(matched))),
    ]
    if verify:
        np_lines.append(nepali.NARRATION_NP["verify"].format(verify=dev(str(verify))))
    else:
        np_lines.append(nepali.NARRATION_NP["verify_none"])
    if high:
        np_lines.append(nepali.NARRATION_NP["high"].format(high=dev(str(high))))
    if missing or unexpected:
        np_lines.append(
            nepali.NARRATION_NP["missing"].format(
                missing=dev(str(missing)), unexpected=dev(str(unexpected))
            )
        )
    np_lines.append(nepali.NARRATION_NP["limits"])

    en_lines: list[str] = [
        nepali.NARRATION_EN["intro"],
        nepali.NARRATION_EN["totals"].format(total=total, matched=matched),
    ]
    if verify:
        en_lines.append(nepali.NARRATION_EN["verify"].format(verify=verify))
    else:
        en_lines.append(nepali.NARRATION_EN["verify_none"])
    if high:
        en_lines.append(nepali.NARRATION_EN["high"].format(high=high))
    if missing or unexpected:
        en_lines.append(
            nepali.NARRATION_EN["missing"].format(missing=missing, unexpected=unexpected)
        )
    en_lines.append(nepali.NARRATION_EN["limits"])

    report.narration_np = list(np_lines)
    report.narration_en = list(en_lines)

    ai_info: dict[str, Any] = {"used": False, "provider": None, "reason": None}
    if ai is None:
        ai_info["reason"] = "no ai injected — deterministic templates"
        report.meta = report.meta or {}
        report.meta["ai"] = ai_info
        return report

    ai_info["provider"] = getattr(ai, "name", None) or type(ai).__name__

    # Respect the provider protocol's cheap readiness check (never raises).
    available = getattr(ai, "available", None)
    if callable(available):
        try:
            if not available():
                ai_info["reason"] = "provider reports itself unavailable — deterministic templates"
                report.meta = report.meta or {}
                report.meta["ai"] = ai_info
                return report
        except Exception:  # noqa: BLE001 — available() must never break the run
            pass

    text, error = _call_ai_text(ai, _narration_prompt(np_lines), _NARRATION_SYSTEM)
    if text is None:
        ai_info["reason"] = f"ai call failed: {error}"
        _warn(report, f"AI narration rewrite failed ({error}); deterministic template kept.")
    else:
        candidate = _parse_ai_lines(text)
        problems = _validate_narration(candidate, np_lines, report)
        if problems:
            ai_info["reason"] = "rejected: " + "; ".join(problems)
            _warn(
                report,
                "AI narration rewrite rejected (" + "; ".join(problems) + "); deterministic template kept.",
            )
        else:
            report.narration_np = candidate
            ai_info["used"] = True
            ai_info["reason"] = "accepted — numbers validated against the computed report"
    report.meta = report.meta or {}
    report.meta["ai"] = ai_info
    return report


def _warn(report: DiffReport, message: str) -> None:
    report.meta = report.meta or {}
    warnings = report.meta.setdefault("warnings", [])
    if isinstance(warnings, list):
        warnings.append(message)


# --------------------------------------------------------------------------- #
# the main entry point
# --------------------------------------------------------------------------- #
def diff_scene(
    scene: SceneGraph,
    observed: ObservedState,
    *,
    ai: Any = None,
) -> DiffReport:
    """Compare the approved drawing with the as-built evidence.

    Deterministic; never raises on empty data; never asserts a violation.
    """
    if not isinstance(scene, SceneGraph):
        scene = SceneGraph()
    if not isinstance(observed, ObservedState):
        observed = ObservedState()

    report = DiffReport(
        scene_file=scene.source_file,
        observed_files=[c.file for c in observed.captures if getattr(c, "file", None)],
    )
    warnings: list[str] = []

    # ---- canonical ordering: walls, then openings, then rooms ----------- #
    scene_items: list[tuple[str, Any]] = []
    for w in scene.walls:
        scene_items.append(("wall", w))
    for o in scene.openings:
        scene_items.append(("opening", o))
    for r in scene.rooms:
        scene_items.append(("room", r))
    rank: dict[str, int] = {}
    by_id: dict[str, tuple[str, Any]] = {}
    for i, (t, obj) in enumerate(scene_items):
        rank.setdefault(f"{t}:{obj.id}", i)
        by_id.setdefault(obj.id, (t, obj))

    obs_items: list[ObservedElement] = list(observed.elements)
    used_scene: set[str] = set()
    used_obs: set[int] = set()
    pairs: list[tuple[str, Any, ObservedElement]] = []

    # ---- 1a. explicit matches win --------------------------------------- #
    for idx, oe in enumerate(obs_items):
        sid = getattr(oe, "matches_scene_id", None)
        if not sid:
            continue
        target = by_id.get(sid)
        if target is None:
            warnings.append(
                f"observed element '{oe.id}' claims scene id '{sid}', which does not exist in this drawing model"
            )
            continue
        t, obj = target
        skey = f"{t}:{obj.id}"
        if skey in used_scene:
            continue
        used_scene.add(skey)
        used_obs.add(idx)
        pairs.append((t, obj, oe))

    # ---- 1b. geometric matching ------------------------------------------ #
    # Global best-first assignment. Collect every viable candidate pair, sort by
    # relative difference, then assign greedily. The obvious alternative — walking the
    # scene element by element and taking each one's best remaining partner — is
    # order-dependent and gets the wrong answer: a 1.5 m observed window can be paired
    # with a 1.2 m drawn window (25% off) while the 1.5 m drawn window further along
    # the same wall is left unmatched, turning a perfect match into a false finding.
    candidates: list[tuple[float, int, int]] = []  # (rel, scene_index, observed_index)
    for si, (t, obj) in enumerate(scene_items):
        if f"{t}:{obj.id}" in used_scene:
            continue
        for idx, oe in enumerate(obs_items):
            if idx in used_obs:
                continue
            rel = _candidate_rel(t, obj, oe)
            if rel is not None:
                candidates.append((rel, si, idx))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))

    for _rel, si, idx in candidates:
        t, obj = scene_items[si]
        skey = f"{t}:{obj.id}"
        if skey in used_scene or idx in used_obs:
            continue
        used_scene.add(skey)
        used_obs.add(idx)
        pairs.append((t, obj, obs_items[idx]))

    pairs.sort(key=lambda p: rank.get(f"{p[0]}:{p[1].id}", 1_000_000))

    # ---- coverage guard -------------------------------------------------- #
    # How much of the drawing did the site evidence actually touch? With only a few
    # photos, "not found in the photos" carries no information — see COVERAGE_SPARSE_RATIO.
    n_scene = len(scene_items)
    coverage = (len(pairs) / n_scene) if n_scene else 1.0
    sparse = n_scene > 0 and coverage < COVERAGE_SPARSE_RATIO
    if sparse:
        warnings.append(
            f"site evidence covers only {len(pairs)} of {n_scene} drawn elements "
            f"({coverage:.0%}) — unmatched drawn elements are reported as 'not checked' "
            f"rather than 'missing', because their absence from the photos is not evidence "
            f"that they are absent from the building"
        )

    # ---- build deltas ---------------------------------------------------- #
    deltas: list[Delta] = []
    contexts: list[dict[str, Any]] = []
    seq = 0

    for t, obj, oe in pairs:
        seq += 1
        delta, ctx = _pair_delta(f"d{seq:03d}", t, obj, oe)
        deltas.append(delta)
        contexts.append(ctx)

    for t, obj in scene_items:
        skey = f"{t}:{obj.id}"
        if skey in used_scene:
            continue
        seq += 1
        delta, ctx = _missing_delta(f"d{seq:03d}", t, obj, sparse=sparse)
        deltas.append(delta)
        contexts.append(ctx)

    for idx, oe in enumerate(obs_items):
        if idx in used_obs:
            continue
        seq += 1
        delta, ctx = _observed_only_delta(f"d{seq:03d}", oe)
        deltas.append(delta)
        contexts.append(ctx)

    report.deltas = deltas

    # ---- verify list: every non-matched delta (+ any high-severity one) -- #
    verify_list: list[VerifyItem] = []
    vseq = 0
    for delta, ctx in zip(deltas, contexts):
        if delta.status == DeltaStatus.MATCHED and delta.severity != Severity.HIGH:
            continue
        vseq += 1
        verify_list.append(_make_verify(f"v{vseq:03d}", delta, ctx))
    report.verify_list = verify_list

    # ---- limits ---------------------------------------------------------- #
    report.limits = _build_limits(
        scene, observed, deltas, matched=len(pairs), total=n_scene
    )

    # ---- meta ------------------------------------------------------------ #
    report.meta = {
        "thresholds": {
            "diff_info_max": DIFF_INFO_MAX,
            "diff_low_max": DIFF_LOW_MAX,
            "diff_medium_max": DIFF_MEDIUM_MAX,
            "confidence_cap": CONFIDENCE_CAP,
            "coverage_sparse_ratio": COVERAGE_SPARSE_RATIO,
            "wall_length_tol": WALL_LENGTH_TOL,
            "opening_width_tol": OPENING_WIDTH_TOL,
            "room_area_tol": ROOM_AREA_TOL,
        },
        "matched_pairs": len(pairs),
        "coverage": round(coverage, 4),
        "coverage_sparse": sparse,
        "missing": sum(1 for d in deltas if d.status == DeltaStatus.MISSING),
        "unexpected": sum(1 for d in deltas if d.status == DeltaStatus.UNEXPECTED),
        "unverifiable": sum(1 for d in deltas if d.status == DeltaStatus.UNVERIFIABLE),
    }
    if warnings:
        report.meta["warnings"] = warnings

    report.recount()
    narrate(report, ai=ai)
    report.recount()
    return report


__all__ = [
    "diff_scene",
    "narrate",
    "severity_for_relative_diff",
    "DIFF_INFO_MAX",
    "DIFF_LOW_MAX",
    "DIFF_MEDIUM_MAX",
    "CONFIDENCE_CAP",
    "WALL_LENGTH_TOL",
    "OPENING_WIDTH_TOL",
    "ROOM_AREA_TOL",
    "ORIENTATION_TOL_DEG",
    "MISSING_SEVERITY",
    "UNEXPECTED_SEVERITY",
]