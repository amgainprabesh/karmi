"""Karmi — site photos → observed state (the AS-BUILT building).

This module answers one question honestly: *what does the site look like right
now, and how sure are we?* It never guesses.

Paths
-----
* **Deterministic path (always available, no AI, no network).** Every photo
  becomes a ``Capture`` with an EXIF/``mtime`` timestamp, a ``view`` guessed
  from filename tokens (front / back / side / rear / interior / aerial) and a
  ``stage`` from ``stage_hint`` or a filename token (foundation / columns /
  walls / slab / roof / finishing / ...). No hint and no token → stage stays
  ``unknown`` **with a warning** — never a guessed stage.
* **Sidecars (the honest fallback).** A human measured it: a small JSON file
  next to the photo (``photo.jpg.json``) or passed via ``sidecars={photo: path}``
  can supply hand-entered elements, measurements and scale references.
* **AI path (optional).** When ``ai`` is provided and ``available()``, photos
  go through ``core.ai.vision.observe_photos`` (open-weight VLM only). AI
  elements carry provenance ``source='ai_vision'`` and their confidence is
  CLAMPED to <= 0.7 — a photograph cannot justify more. Low-confidence items
  are echoed into ``warnings`` as items for human verification.

Honesty rules (never violated)
------------------------------
* No AI and no sidecar measurements → captures + warnings + an empty element
  list. That is a valid, honest result.
* Without any scale reference, absolute sizes are unavailable: a warning is
  added and every element's confidence is capped at ``NO_SCALE_CONFIDENCE_CAP``.
* Karmi reports *items to verify*, never "violations".

Sidecar schema (all fields optional except ``elements``/``scale_refs`` bodies)::

    {
      "photo": "front.jpg",                      // informational
      "taken_at": "2026-06-08T10:30:00+05:45",   // ISO; wins over EXIF/mtime
      "view": "front",                           // front|side|rear|interior|aerial
      "stage": "walls",                          // site|foundation|columns|walls|
                                                 // slab|roof|finishing|complete
      "notes": "free text",
      "elements": [
        {
          "kind": "wall",                        // wall|opening|column|slab|roof|
                                                 // setback|other
          "approx_size": {"length": 9.8, "height": 2.7, "thickness": 0.23},
          "location_hint": "front (south) facade",
          "matches_scene_id": "W01",             // optional link to the scene graph
          "confidence": 0.85,                    // optional, default 0.8
          "evidence": "tape measure, 5 m steel tape"
        }
      ],
      "scale_refs": [
        {"kind": "door_height",                  // brick_course|door_height|
                                                 // user_dimension|known_object
         "value": 2.05, "unit": "m", "confidence": 0.9,
         "evidence": "main door frame height"}
      ]
    }

CLI::

    python -m core.observe fixtures/photos
    python -m core.observe fixtures/photos --known-dimension 9.8 --stage-hint walls
    python -m core.observe photo.jpg --json
    python -m core.observe photos/ --ai          # uses KARMI_AI_* configuration
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.schema import (
    Capture,
    ElementKind,
    ObservedElement,
    ObservedState,
    Provenance,
    ScaleRef,
    Stage,
)

# --------------------------------------------------------------------------- #
# documented constants — honesty knobs, not magic numbers
# --------------------------------------------------------------------------- #
AI_CONFIDENCE_CAP = 0.7        # a photograph cannot justify more than this
LOW_CONFIDENCE = 0.5           # below this, the item is echoed for human verification
NO_SCALE_CONFIDENCE_CAP = 0.3  # without any scale reference, absolute sizes are unavailable
SIDECAR_DEFAULT_CONFIDENCE = 0.8
STAGE_SIDECAR_CONFIDENCE = 0.9
STAGE_HINT_CONFIDENCE = 0.8
STAGE_TOKEN_CONFIDENCE = 0.5

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")

_VIEW_TOKENS = {
    "front": "front",
    "back": "rear",
    "rear": "rear",
    "side": "side",
    "interior": "interior",
    "inside": "interior",
    "aerial": "aerial",
    "top": "aerial",
    "drone": "aerial",
}

_STAGE_TOKENS = {
    "site": Stage.SITE,
    "foundation": Stage.FOUNDATION,
    "footing": Stage.FOUNDATION,
    "footings": Stage.FOUNDATION,
    "columns": Stage.COLUMNS,
    "column": Stage.COLUMNS,
    "pillar": Stage.COLUMNS,
    "pillars": Stage.COLUMNS,
    "walls": Stage.WALLS,
    "wall": Stage.WALLS,
    "brickwork": Stage.WALLS,
    "masonry": Stage.WALLS,
    "slab": Stage.SLAB,
    "lintel": Stage.SLAB,
    "ceiling": Stage.SLAB,
    "roof": Stage.ROOF,
    "roofing": Stage.ROOF,
    "truss": Stage.ROOF,
    "finishing": Stage.FINISHING,
    "plaster": Stage.FINISHING,
    "paint": Stage.FINISHING,
    "tiling": Stage.FINISHING,
    "complete": Stage.COMPLETE,
    "completed": Stage.COMPLETE,
    "finished": Stage.COMPLETE,
}

_KIND_ALIASES = {
    "door": ElementKind.OPENING,
    "window": ElementKind.OPENING,
    "vent": ElementKind.OPENING,
    "pillar": ElementKind.COLUMN,
    "beam": ElementKind.SLAB,
    "compound_wall": ElementKind.WALL,
    "boundary_wall": ElementKind.WALL,
    "stair": ElementKind.OTHER,
    "foundation": ElementKind.OTHER,
}

_SCALE_REF_KINDS = ("brick_course", "door_height", "user_dimension", "known_object", "unknown")
_SCALE_REF_UNITS = ("m", "mm", "ft")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _f(raw: Any) -> float | None:
    """Best-effort float coercion for values coming from JSON."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        m = re.search(r"-?\d+(?:[.,]\d+)?", raw.replace(" ", ""))
        if not m:
            return None
        try:
            return float(m.group().replace(",", "."))
        except ValueError:
            return None
    return None


def _tokens(path: Path) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", path.stem.lower()) if t]


def _parse_stage(raw: Any) -> Stage | None:
    if raw is None:
        return None
    if isinstance(raw, Stage):
        return raw
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return Stage(s)
    except ValueError:
        pass
    return _STAGE_TOKENS.get(s)


def _view_from_tokens(path: Path) -> str | None:
    for token in _tokens(path):
        if token in _VIEW_TOKENS:
            return _VIEW_TOKENS[token]
    return None


def _stage_from_tokens(path: Path) -> Stage | None:
    for token in _tokens(path):
        if token in _STAGE_TOKENS:
            return _STAGE_TOKENS[token]
    return None


def _coerce_kind(raw: Any) -> ElementKind:
    if isinstance(raw, ElementKind):
        return raw
    s = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return ElementKind(s)
    except ValueError:
        pass
    return _KIND_ALIASES.get(s, ElementKind.OTHER)


def _coerce_size(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    allowed = ("length", "width", "height", "thickness", "depth", "diameter", "span", "area")
    for key, value in raw.items():
        name = str(key).strip().lower().replace(" ", "_")
        f = _f(value)
        if name in allowed and f is not None:
            out[name] = f
    return out


def _exif_taken_at(path: Path) -> str | None:
    """DateTimeOriginal (falling back to DateTimeDigitized / DateTime), or None."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            exif = im.getexif()
            for tag in (36867, 36868, 306):
                raw = exif.get(tag)
                if raw:
                    s = str(raw).strip()
                    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                        try:
                            return datetime.strptime(s, fmt).isoformat(timespec="seconds")
                        except ValueError:
                            continue
    except Exception:  # noqa: BLE001 — EXIF is best-effort, never fatal
        return None
    return None


def _mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def _ts_key(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _latest_capture(captures: Sequence[Capture]) -> Capture:
    """Latest capture by timestamp; captures without timestamps sort by input order.

    A capture with a real timestamp always beats one without; ties go to the
    later entry (uploads are usually appended in shooting order).
    """
    best = captures[0]
    best_key = _ts_key(best.taken_at)
    for cap in captures[1:]:
        key = _ts_key(cap.taken_at)
        if key is None:
            if best_key is None:
                best = cap  # no timestamps anywhere: last in input order wins
            continue
        if best_key is None or key >= best_key:
            best, best_key = cap, key
    return best


# --------------------------------------------------------------------------- #
# deterministic capture construction
# --------------------------------------------------------------------------- #
def _build_capture(photo: str | Path, stage_hint: str | None, warnings: list[str]) -> Capture:
    p = Path(photo)
    taken_at: str | None = None
    if p.is_file():
        taken_at = _exif_taken_at(p) or _mtime_iso(p)
    else:
        warnings.append(f"{p.name}: file not found — capture recorded without a timestamp.")

    hint_stage = _parse_stage(stage_hint)
    if stage_hint is not None and str(stage_hint).strip() and hint_stage is None:
        warnings.append(
            f"Stage hint {stage_hint!r} is not a recognised stage — ignored. "
            f"Expected one of: {', '.join(s.value for s in Stage)}."
        )

    token_stage = _stage_from_tokens(p)
    stage = Stage.UNKNOWN
    confidence = 0.0
    source = "default"
    evidence: str | None = None
    if hint_stage is not None:
        stage, confidence, source = hint_stage, STAGE_HINT_CONFIDENCE, "user_supplied"
        evidence = "stage from user-supplied stage hint"
    elif token_stage is not None:
        stage, confidence, source = token_stage, STAGE_TOKEN_CONFIDENCE, "user_supplied"
        evidence = f"stage from filename token in {p.name!r}"
    else:
        warnings.append(
            f"{p.name}: construction stage unknown — no stage hint and no stage token in the "
            "filename. Add --stage-hint or rename the photo (e.g. 'front_walls.jpg')."
        )

    view = _view_from_tokens(p) or "unknown"
    return Capture(
        file=str(photo),
        taken_at=taken_at,
        stage=stage,
        stage_confidence=_clamp(confidence),
        view=view,  # type: ignore[arg-type] — one of the schema literals
        provenance=Provenance(source=source, confidence=_clamp(confidence), evidence=evidence),  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# sidecars
# --------------------------------------------------------------------------- #
def _sidecar_path_for(photo: Path) -> Path | None:
    primary = photo.parent / (photo.name + ".json")  # photo.jpg.json
    if primary.is_file():
        return primary
    secondary = photo.with_suffix(".json")  # photo.json
    if secondary.is_file():
        return secondary
    return None


def _find_sidecar(photo: Path, sidecars: Mapping[str, Any] | None) -> Path | None:
    if sidecars:
        for key in (str(photo), photo.name, photo.stem):
            if key in sidecars:
                return Path(str(sidecars[key]))
    return _sidecar_path_for(photo)


def _apply_sidecar(
    cap: Capture,
    data: Mapping[str, Any],
    photo_name: str,
    elements: list[ObservedElement],
    scale_refs: list[ScaleRef],
    warnings: list[str],
    meta_notes: list[dict[str, str]],
) -> None:
    def _p(msg: str) -> str:
        return f"{photo_name}: {msg}"

    taken = data.get("taken_at")
    if isinstance(taken, str) and taken.strip():
        cap.taken_at = taken.strip()

    view_raw = data.get("view")
    if view_raw is not None:
        s = str(view_raw).strip().lower()
        mapped = _VIEW_TOKENS.get(s)
        if mapped:
            cap.view = mapped  # type: ignore[assignment]
        elif s not in ("unknown", ""):
            warnings.append(_p(f"sidecar view {view_raw!r} not recognised — ignored."))

    stage_raw = data.get("stage")
    stage = _parse_stage(stage_raw)
    if stage is not None:
        conf = _f(data.get("stage_confidence"))
        cap.stage = stage
        cap.stage_confidence = _clamp(conf if conf is not None else STAGE_SIDECAR_CONFIDENCE)
        cap.provenance = Provenance(
            source="user_supplied",
            confidence=cap.stage_confidence,
            evidence=f"hand-entered sidecar for {photo_name}",
        )
    elif stage_raw is not None and str(stage_raw).strip():
        warnings.append(_p(f"sidecar stage {stage_raw!r} not recognised — ignored."))

    notes = data.get("notes")
    if isinstance(notes, str) and notes.strip():
        meta_notes.append({"photo": photo_name, "notes": notes.strip()})

    for raw in data.get("elements") or []:
        if not isinstance(raw, dict):
            warnings.append(_p("sidecar element is not an object — skipped."))
            continue
        conf = _f(raw.get("confidence"))
        el = ObservedElement(
            id=f"obs-{len(elements) + 1:03d}",
            kind=_coerce_kind(raw.get("kind")),
            approx_size=_coerce_size(raw.get("approx_size")),
            location_hint=(str(raw["location_hint"]).strip() if raw.get("location_hint") else None),
            matches_scene_id=(str(raw["matches_scene_id"]).strip() if raw.get("matches_scene_id") else None),
            provenance=Provenance(
                source="user_supplied",
                confidence=_clamp(conf if conf is not None else SIDECAR_DEFAULT_CONFIDENCE),
                evidence=str(raw.get("evidence") or f"hand-entered sidecar ({photo_name})"),
            ),
        )
        elements.append(el)

    for raw in data.get("scale_refs") or []:
        if not isinstance(raw, dict):
            continue
        value = _f(raw.get("value"))
        if value is None or value <= 0:
            warnings.append(_p("sidecar scale_ref without a usable value — ignored."))
            continue
        kind = str(raw.get("kind") or "unknown").strip().lower()
        if kind not in _SCALE_REF_KINDS:
            kind = "unknown"
        unit = str(raw.get("unit") or "m").strip().lower()
        if unit not in _SCALE_REF_UNITS:
            unit = "m"
        conf = _f(raw.get("confidence"))
        scale_refs.append(
            ScaleRef(
                kind=kind,  # type: ignore[arg-type]
                value=value,
                unit=unit,  # type: ignore[arg-type]
                provenance=Provenance(
                    source="user_supplied",
                    confidence=_clamp(conf if conf is not None else SIDECAR_DEFAULT_CONFIDENCE),
                    evidence=str(raw.get("evidence") or f"hand-entered sidecar ({photo_name})"),
                ),
            )
        )


# --------------------------------------------------------------------------- #
# AI merge
# --------------------------------------------------------------------------- #
def _merge_ai(
    captures: list[Capture],
    ai: Any,
    stage_hint: str | None,
    elements: list[ObservedElement],
    scale_refs: list[ScaleRef],
    warnings: list[str],
) -> dict[str, Any] | None:
    """Run the AI observation (if usable) and merge it. Never raises."""
    provider_name = getattr(ai, "name", "?")
    model_name = getattr(ai, "model", "?")
    try:
        usable = bool(ai.available())
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"AI provider availability check failed ({exc}) — continuing without AI.")
        return None
    if not usable:
        if str(provider_name).lower() not in ("none", "null", ""):
            warnings.append(
                f"AI provider {provider_name!r} is configured but not available — "
                "continuing without AI (deterministic result)."
            )
        return None

    try:
        from core.ai.vision import observe_photos

        data = observe_photos([c.file for c in captures], provider=ai, hint=stage_hint)
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the pipeline
        warnings.append(f"AI photo observation failed ({exc}) — continuing with the deterministic result.")
        return None

    warnings.extend(str(w) for w in data.get("warnings", []))

    by_file = {c.file: c for c in captures}
    by_name = {Path(c.file).name: c for c in captures}
    for ai_cap in data.get("captures", []):
        cap = by_file.get(str(ai_cap.get("file"))) or by_name.get(Path(str(ai_cap.get("file"))).name)
        if cap is None:
            continue
        ai_stage = _parse_stage(ai_cap.get("stage")) or Stage.UNKNOWN
        ai_conf = _clamp(_f(ai_cap.get("stage_confidence")) or 0.0, 0.0, AI_CONFIDENCE_CAP)
        if cap.stage == Stage.UNKNOWN and ai_stage != Stage.UNKNOWN:
            cap.stage = ai_stage
            cap.stage_confidence = ai_conf
            cap.provenance = Provenance(
                source="ai_vision",
                confidence=ai_conf,
                evidence=f"AI stage classification ({model_name})",
            )
        elif ai_stage != Stage.UNKNOWN and ai_stage != cap.stage:
            warnings.append(
                f"{Path(cap.file).name}: the stage hint/filename says {cap.stage.value!r} but AI vision "
                f"sees {ai_stage.value!r} (confidence {ai_conf:.2f}) — verify on site."
            )
        ai_view = ai_cap.get("view")
        if cap.view == "unknown" and ai_view and ai_view != "unknown":
            cap.view = ai_view  # type: ignore[assignment]

    for ai_el in data.get("elements", []):
        conf = _clamp(_f(ai_el.get("confidence")) or 0.0, 0.0, AI_CONFIDENCE_CAP)
        source_file = str(ai_el.get("file") or "")
        evidence = ai_el.get("evidence") or "AI vision observation"
        elements.append(
            ObservedElement(
                id=f"obs-{len(elements) + 1:03d}",
                kind=_coerce_kind(ai_el.get("kind")),
                approx_size=_coerce_size(ai_el.get("approx_size")),
                location_hint=(str(ai_el["location_hint"]).strip() if ai_el.get("location_hint") else None),
                provenance=Provenance(
                    source="ai_vision",
                    confidence=conf,
                    evidence=f"{Path(source_file).name or 'photo'} — {evidence}",
                ),
            )
        )

    for ai_ref in data.get("scale_refs", []):
        value = _f(ai_ref.get("value"))
        if value is None or value <= 0:
            continue
        kind = str(ai_ref.get("kind") or "unknown")
        if kind not in _SCALE_REF_KINDS:
            kind = "unknown"
        unit = str(ai_ref.get("unit") or "m")
        if unit not in _SCALE_REF_UNITS:
            unit = "m"
        conf = _clamp(_f(ai_ref.get("confidence")) or 0.0, 0.0, AI_CONFIDENCE_CAP)
        source_file = str(ai_ref.get("file") or "")
        scale_refs.append(
            ScaleRef(
                kind=kind,  # type: ignore[arg-type]
                value=value,
                unit=unit,  # type: ignore[arg-type]
                provenance=Provenance(
                    source="ai_vision",
                    confidence=conf,
                    evidence=f"AI vision estimate from {Path(source_file).name or 'photo'}",
                ),
            )
        )

    return {
        "provider": provider_name,
        "model": model_name,
        "captures": len(data.get("captures", [])),
        "elements": len(data.get("elements", [])),
        "scale_refs": len(data.get("scale_refs", [])),
    }


# --------------------------------------------------------------------------- #
# overall stage
# --------------------------------------------------------------------------- #
def _overall_stage(captures: list[Capture], warnings: list[str]) -> tuple[Stage, Provenance]:
    if not captures:
        warnings.append("No captures were produced — nothing to observe.")
        return Stage.UNKNOWN, Provenance(source="default", confidence=0.0)

    latest = _latest_capture(captures)
    known: list[str] = []
    for cap in captures:
        if cap.stage != Stage.UNKNOWN and cap.stage.value not in known:
            known.append(cap.stage.value)

    if len(known) > 1:
        warnings.append(
            "Captures show different construction stages ("
            + ", ".join(known)
            + ") — photos were probably taken on different dates; the latest capture ("
            + Path(latest.file).name
            + ") determines the overall stage."
        )
    if latest.stage == Stage.UNKNOWN and known:
        warnings.append(
            f"The latest capture ({Path(latest.file).name}) carries no stage information; "
            f"earlier captures suggest: {', '.join(known)}."
        )

    provenance = Provenance(
        source=latest.provenance.source,
        confidence=latest.stage_confidence,
        evidence=f"latest capture: {Path(latest.file).name}",
    )
    return latest.stage, provenance


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def to_observed_state(
    photos: Sequence[str | Path],
    *,
    known_dimension: float | None = None,
    ai: Any = None,
    stage_hint: str | None = None,
    sidecars: Mapping[str, str | Path] | None = None,
) -> ObservedState:
    """Build the observed (as-built) state from site photos.

    Always returns a valid ``ObservedState``. AI and sidecars are strictly
    additive: with neither, the result is captures + warnings + no elements.
    """
    warnings: list[str] = []
    captures: list[Capture] = []
    elements: list[ObservedElement] = []
    scale_refs: list[ScaleRef] = []
    meta_notes: list[dict[str, str]] = []
    sidecars_used: list[str] = []
    photos_missing: list[str] = []

    for raw in photos:
        p = Path(raw)
        if not p.is_file():
            photos_missing.append(p.name)
        try:
            cap = _build_capture(raw, stage_hint, warnings)
        except Exception as exc:  # noqa: BLE001 — one odd file never kills the run
            warnings.append(f"{p.name}: could not read this photo ({exc}) — recorded as a bare capture.")
            cap = Capture(file=str(raw), provenance=Provenance(source="default", confidence=0.0))
        captures.append(cap)

        sidecar_path = _find_sidecar(p, sidecars)
        if sidecar_path is not None:
            if sidecar_path.is_file():
                try:
                    data = json.loads(sidecar_path.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"{p.name}: sidecar {sidecar_path.name} could not be read ({exc}) — ignored.")
                else:
                    if isinstance(data, dict):
                        sidecars_used.append(sidecar_path.name)
                        _apply_sidecar(cap, data, p.name, elements, scale_refs, warnings, meta_notes)
                    else:
                        warnings.append(f"{p.name}: sidecar {sidecar_path.name} must contain a JSON object — ignored.")
            elif sidecars is not None and any(str(sidecars.get(k, "")) == str(sidecar_path) for k in sidecars):
                warnings.append(f"{p.name}: sidecar {sidecar_path} not found — ignored.")

    if known_dimension is not None:
        value = _f(known_dimension)
        if value is not None and value > 0:
            scale_refs.append(
                ScaleRef(
                    kind="user_dimension",
                    value=value,
                    unit="m",
                    provenance=Provenance(
                        source="user_supplied",
                        confidence=1.0,
                        evidence="user-supplied known dimension",
                    ),
                )
            )
        else:
            warnings.append(f"known_dimension {known_dimension!r} is not a positive number (metres) — ignored.")

    ai_meta: dict[str, Any] | None = None
    if ai is not None:
        ai_meta = _merge_ai(captures, ai, stage_hint, elements, scale_refs, warnings)

    # ---- scaling honesty: absolute sizes need a scale reference ----------- #
    has_user_scale = any(ref.provenance.source == "user_supplied" for ref in scale_refs)
    if not scale_refs:
        warnings.append(
            "No scale reference available — absolute sizes cannot be estimated from these "
            f"photos; element confidences were capped at {NO_SCALE_CONFIDENCE_CAP:.2f} and every "
            "size must be treated as unmeasured."
        )
    elif not has_user_scale:
        warnings.append(
            "Scale references come only from AI vision — absolute sizes are approximate; "
            "verify with a tape measure or a known dimension."
        )
    if not scale_refs:
        for el in elements:
            el.provenance.confidence = min(el.provenance.confidence, NO_SCALE_CONFIDENCE_CAP)

    # ---- echo every low-confidence element for human verification --------- #
    for el in elements:
        if el.provenance.confidence < LOW_CONFIDENCE:
            location = el.location_hint or "location unspecified"
            warnings.append(
                f"Low-confidence observation ({el.provenance.confidence:.2f}) from "
                f"{el.provenance.evidence or 'unknown source'}: {el.kind.value} at {location} — "
                "treat as an item to verify, not a fact."
            )

    stage, stage_provenance = _overall_stage(captures, warnings)

    meta: dict[str, Any] = {
        "photo_count": len(captures),
        "sidecars_used": sidecars_used,
        "photos_missing": photos_missing,
    }
    if ai_meta is not None:
        meta["ai"] = ai_meta
    if meta_notes:
        meta["notes"] = meta_notes

    return ObservedState(
        stage=stage,
        stage_provenance=stage_provenance,
        captures=captures,
        elements=elements,
        scale_refs=scale_refs,
        warnings=list(dict.fromkeys(warnings)),
        meta=meta,
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _expand_paths(paths: Sequence[str]) -> list[str]:
    found: list[str] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for child in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                if child.suffix.lower() in _IMAGE_SUFFIXES and child.is_file():
                    found.append(str(child))
        elif p.is_file():
            found.append(str(p))
        else:
            print(f"warning: {raw} is not a file or directory — skipped", file=sys.stderr)
    return found


def _render_summary(state: ObservedState) -> str:
    lines: list[str] = []
    lines.append(
        f"Karmi observe — {len(state.captures)} capture(s), {len(state.elements)} element(s), "
        f"{len(state.scale_refs)} scale ref(s)"
    )
    lines.append(
        f"  stage: {state.stage.value}  "
        f"(confidence {state.stage_provenance.confidence:.2f}, source {state.stage_provenance.source})"
    )
    if state.captures:
        lines.append("  captures:")
        for cap in state.captures:
            lines.append(
                f"    - {Path(cap.file).name:<32} view={cap.view:<9} stage={cap.stage.value:<11} "
                f"conf={cap.stage_confidence:.2f}  {cap.taken_at or 'no timestamp'}"
            )
    if state.elements:
        lines.append("  elements:")
        for el in state.elements:
            size = ", ".join(f"{k}={v:g}" for k, v in el.approx_size.items()) or "no size"
            lines.append(
                f"    - [{el.id}] {el.kind.value:<8} {size:<30} @ {el.location_hint or 'location unspecified'}"
                f"  ({el.provenance.source}, conf {el.provenance.confidence:.2f})"
            )
    else:
        lines.append(
            "  elements: none — no AI and no sidecar measurements were available "
            "(a valid, honest result)"
        )
    if state.scale_refs:
        lines.append("  scale refs:")
        for ref in state.scale_refs:
            lines.append(
                f"    - {ref.kind:<13} {ref.value:g} {ref.unit}  "
                f"({ref.provenance.source}, conf {ref.provenance.confidence:.2f})"
            )
    if state.warnings:
        lines.append("  warnings (limits and items to verify):")
        for w in state.warnings:
            lines.append(f"    - {w}")
    return "\n".join(lines)


def _cli(argv: Sequence[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m core.observe",
        description="Build the observed (as-built) state from site photos. Offline by default.",
    )
    ap.add_argument("paths", nargs="+", help="photo files and/or directories to scan for images")
    ap.add_argument("--known-dimension", type=float, default=None, metavar="METRES",
                    help="a user-supplied known dimension in metres (becomes a scale reference)")
    ap.add_argument("--stage-hint", default=None,
                    help="construction stage for all photos (foundation|columns|walls|slab|roof|finishing|...)")
    ap.add_argument("--json", action="store_true", help="print the ObservedState as JSON")
    ap.add_argument("--ai", action="store_true",
                    help="use the configured open-weight AI provider (KARMI_AI_* env vars)")
    args = ap.parse_args(argv)

    photos = _expand_paths(args.paths)
    if not photos:
        print("error: no photos found in the given paths", file=sys.stderr)
        return 2

    ai = None
    if args.ai:
        from core.ai import get_provider

        ai = get_provider()

    state = to_observed_state(
        photos,
        known_dimension=args.known_dimension,
        ai=ai,
        stage_hint=args.stage_hint,
    )
    if args.json:
        print(state.model_dump_json(indent=2))
    else:
        print(_render_summary(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())


__all__ = ["to_observed_state", "AI_CONFIDENCE_CAP", "LOW_CONFIDENCE", "NO_SCALE_CONFIDENCE_CAP"]