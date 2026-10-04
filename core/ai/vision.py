"""Karmi — AI vision: site photos → structured observation.

``observe_photos(photos, *, provider, hint=None)`` sends each photo to an
open-weight vision model (one call per photo, so stage/view/elements stay
attributable to a specific capture), parses the response defensively and
returns a dict shaped like ``core.schema.ObservedState`` fields:

    {
      "provider": "ollama",
      "model": "qwen2.5-vl:7b",
      "captures":   [{"file", "stage", "stage_confidence", "view", "notes"}],
      "elements":   [{"file", "kind", "approx_size", "location_hint",
                      "confidence", "evidence"}],
      "scale_refs": [{"file", "kind", "value", "unit", "confidence"}],
      "warnings":   ["<photo>: AI call failed (...)", ...],
    }

Honesty rules (enforced by ``core/observe.py`` when merging):
* confidences are the model's own; the merge step clamps them (<= 0.7).
* a photo whose call/parse fails becomes a warning, not a fabrication; if
  EVERY photo fails, ``AIExtractionError`` is raised and the caller degrades
  to the deterministic path.
* ``null`` values are preserved as absence, never filled in.

Nothing here runs at import time and nothing here touches the network unless
``provider.complete()`` does (the provider is injected by the caller).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.schema import ElementKind, Stage

from .prompts import SYSTEM_STRICT_JSON, photo_prompt


class AIExtractionError(RuntimeError):
    """The AI observation could not be produced (call failed, bad JSON, ...)."""


# --------------------------------------------------------------------------- #
# defensive value coercion — models drift; we never trust their types
# --------------------------------------------------------------------------- #
def _to_float(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        for key in ("value", "metres", "meters", "m", "amount", "estimate"):
            if key in raw:
                return _to_float(raw[key])
        return None
    if isinstance(raw, str):
        m = re.search(r"-?\d+(?:[.,]\d+)?", raw.replace(" ", ""))
        if not m:
            return None
        try:
            return float(m.group().replace(",", "."))
        except ValueError:
            return None
    return None


def _clamp(value: float | None, lo: float, hi: float) -> float:
    if value is None:
        return lo
    return max(lo, min(hi, value))


_ALLOWED_SIZE_KEYS = ("length", "width", "height", "thickness", "depth", "diameter", "span", "area")


def _coerce_size(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        name = str(key).strip().lower().replace(" ", "_")
        if name not in _ALLOWED_SIZE_KEYS:
            continue
        f = _to_float(value)
        if f is not None:
            out[name] = f
    return out


_STAGE_ALIASES = {
    "not_started": Stage.SITE,
    "cleared": Stage.SITE,
    "excavation": Stage.SITE,
    "ground": Stage.SITE,
    "plinth": Stage.FOUNDATION,
    "footing": Stage.FOUNDATION,
    "footings": Stage.FOUNDATION,
    "structure": Stage.COLUMNS,
    "frame": Stage.COLUMNS,
    "framing": Stage.COLUMNS,
    "pillars": Stage.COLUMNS,
    "brickwork": Stage.WALLS,
    "masonry": Stage.WALLS,
    "brick_walls": Stage.WALLS,
    "ceiling": Stage.SLAB,
    "floor_slab": Stage.SLAB,
    "lintel": Stage.SLAB,
    "roofing": Stage.ROOF,
    "truss": Stage.ROOF,
    "plaster": Stage.FINISHING,
    "paint": Stage.FINISHING,
    "flooring": Stage.FINISHING,
    "tiling": Stage.FINISHING,
    "finished": Stage.COMPLETE,
    "done": Stage.COMPLETE,
    "completed": Stage.COMPLETE,
}

_KIND_ALIASES = {
    "door": ElementKind.OPENING,
    "window": ElementKind.OPENING,
    "vent": ElementKind.OPENING,
    "window_opening": ElementKind.OPENING,
    "pillar": ElementKind.COLUMN,
    "beam": ElementKind.SLAB,
    "fence": ElementKind.OTHER,
    "compound_wall": ElementKind.WALL,
    "boundary_wall": ElementKind.WALL,
    "foundation": ElementKind.OTHER,
    "stair": ElementKind.OTHER,
}

_VIEW_ALIASES = {
    "back": "rear",
    "backside": "rear",
    "inside": "interior",
    "indoor": "interior",
    "top": "aerial",
    "drone": "aerial",
    "overhead": "aerial",
    "exterior": "front",
}


def _parse_stage(raw: Any) -> Stage:
    if raw is None:
        return Stage.UNKNOWN
    if isinstance(raw, Stage):
        return raw
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return Stage(s)
    except ValueError:
        pass
    return _STAGE_ALIASES.get(s, Stage.UNKNOWN)


def _parse_kind(raw: Any) -> ElementKind:
    if raw is None:
        return ElementKind.OTHER
    if isinstance(raw, ElementKind):
        return raw
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return ElementKind(s)
    except ValueError:
        pass
    return _KIND_ALIASES.get(s, ElementKind.OTHER)


def _parse_view(raw: Any) -> str:
    if raw is None:
        return "unknown"
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if s.endswith("_view"):
        s = s[:-5]
    if s in ("front", "side", "rear", "interior", "aerial"):
        return s
    return _VIEW_ALIASES.get(s, "unknown")


# --------------------------------------------------------------------------- #
# pydantic models validated against core.schema types
# --------------------------------------------------------------------------- #
class PhotoElement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: ElementKind = ElementKind.OTHER
    approx_size: dict[str, float] = Field(default_factory=dict)
    location_hint: str | None = None
    confidence: float = 0.0
    evidence: str | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def _v_kind(cls, v: Any) -> ElementKind:
        return _parse_kind(v)

    @field_validator("approx_size", mode="before")
    @classmethod
    def _v_size(cls, v: Any) -> dict[str, float]:
        return _coerce_size(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _v_conf(cls, v: Any) -> float:
        return _clamp(_to_float(v), 0.0, 1.0)

    @field_validator("location_hint", "evidence", mode="before")
    @classmethod
    def _v_text(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class PhotoScaleRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["brick_course", "door_height", "known_object", "user_dimension", "unknown"] = "unknown"
    value: float | None = None
    unit: Literal["m", "mm", "ft"] = "m"
    confidence: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def _normalise_unit(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        unit = str(data.get("unit") or "m").strip().lower()
        value = data.get("value")
        if unit in ("cm", "centimetre", "centimeter", "centimetres", "centimeters"):
            f = _to_float(value)
            data = dict(data)
            data["value"] = (f / 100.0) if f is not None else None
            data["unit"] = "m"
        elif unit in ("metre", "metres", "meter", "meters"):
            data = dict(data)
            data["unit"] = "m"
        elif unit in ("millimetre", "millimetres", "millimeter", "millimeters"):
            data = dict(data)
            data["unit"] = "mm"
        return data

    @field_validator("kind", mode="before")
    @classmethod
    def _v_kind(cls, v: Any) -> str:
        s = str(v or "").strip().lower().replace(" ", "_").replace("-", "_")
        return s if s in ("brick_course", "door_height", "known_object", "user_dimension") else "unknown"

    @field_validator("value", mode="before")
    @classmethod
    def _v_value(cls, v: Any) -> float | None:
        return _to_float(v)

    @field_validator("unit", mode="before")
    @classmethod
    def _v_unit(cls, v: Any) -> str:
        s = str(v or "m").strip().lower()
        return s if s in ("m", "mm", "ft") else "m"

    @field_validator("confidence", mode="before")
    @classmethod
    def _v_conf(cls, v: Any) -> float:
        return _clamp(_to_float(v), 0.0, 1.0)


class PhotoObservation(BaseModel):
    """One photo's structured observation, validated against schema enums."""

    model_config = ConfigDict(extra="ignore")

    stage: Stage = Stage.UNKNOWN
    stage_confidence: float = 0.0
    view: Literal["front", "side", "rear", "interior", "aerial", "unknown"] = "unknown"
    elements: list[PhotoElement] = Field(default_factory=list)
    scale_refs: list[PhotoScaleRef] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("stage", mode="before")
    @classmethod
    def _v_stage(cls, v: Any) -> Stage:
        return _parse_stage(v)

    @field_validator("stage_confidence", mode="before")
    @classmethod
    def _v_conf(cls, v: Any) -> float:
        return _clamp(_to_float(v), 0.0, 1.0)

    @field_validator("view", mode="before")
    @classmethod
    def _v_view(cls, v: Any) -> str:
        return _parse_view(v)

    @field_validator("elements", "scale_refs", mode="before")
    @classmethod
    def _v_list(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, dict):
            return [v]
        return v

    @field_validator("notes", mode="before")
    @classmethod
    def _v_notes(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None


# --------------------------------------------------------------------------- #
# defensive JSON parsing
# --------------------------------------------------------------------------- #
_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def _extract_json_object(text: Any) -> Any:
    """Parse model output into a JSON value, defensively.

    Strips markdown fences, tries a direct parse, then scans for the first
    balanced ``{...}`` block. Raises ``AIExtractionError`` when nothing works.
    """
    if isinstance(text, (dict, list)):
        return text
    if not isinstance(text, str) or not text.strip():
        raise AIExtractionError("the model returned an empty response")
    t = text.strip()
    m = _FENCE_RE.search(t)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except (ValueError, TypeError):
        pass
    for start in (i for i, ch in enumerate(t) if ch == "{"):
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(t[start : i + 1])
                        except ValueError:
                            break
    snippet = text.strip().replace("\n", " ")[:200]
    raise AIExtractionError(f"no valid JSON object found in the model output: {snippet!r}")


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def observe_photos(
    photos: Sequence[str | Path],
    *,
    provider: Any,
    hint: str | None = None,
) -> dict[str, Any]:
    """Observe construction photos with an open-weight vision model.

    Returns a dict shaped like ``ObservedState`` fields (see module docstring).
    Raises ``AIExtractionError`` when no photo could be observed at all.
    """
    if provider is None:
        raise AIExtractionError("No AI provider was supplied.")
    if not photos:
        raise AIExtractionError("No photos to observe.")

    try:
        usable = bool(provider.available())
    except Exception as exc:  # noqa: BLE001 — availability must never crash the caller
        raise AIExtractionError(f"provider availability check failed: {exc}") from exc
    if not usable:
        raise AIExtractionError(
            f"AI provider {getattr(provider, 'name', '?')!r} is not available."
        )

    prompt = photo_prompt(hint)
    captures: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    scale_refs: list[dict[str, Any]] = []
    warnings: list[str] = []

    for raw_path in photos:
        path = Path(raw_path)
        if not path.is_file():
            warnings.append(f"{path.name}: photo file not found — skipped by AI observation.")
            continue
        try:
            text = provider.complete(
                prompt,
                system=SYSTEM_STRICT_JSON,
                images=[str(path)],
                max_tokens=1024,
                temperature=0.1,
            )
        except Exception as exc:  # noqa: BLE001 — one bad call degrades, never crashes
            warnings.append(f"{path.name}: AI call failed ({exc}).")
            continue
        try:
            data = _extract_json_object(text)
            if not isinstance(data, dict):
                raise AIExtractionError(f"expected a JSON object, got {type(data).__name__}")
            obs = PhotoObservation.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{path.name}: could not parse the AI response ({exc}).")
            continue

        captures.append(
            {
                "file": str(path),
                "stage": obs.stage.value,
                "stage_confidence": obs.stage_confidence,
                "view": obs.view,
                "notes": obs.notes,
            }
        )
        for el in obs.elements:
            elements.append(
                {
                    "file": str(path),
                    "kind": el.kind.value,
                    "approx_size": dict(el.approx_size),
                    "location_hint": el.location_hint,
                    "confidence": el.confidence,
                    "evidence": el.evidence,
                }
            )
        for ref in obs.scale_refs:
            if ref.value is None or ref.value <= 0:
                continue
            scale_refs.append(
                {
                    "file": str(path),
                    "kind": ref.kind,
                    "value": ref.value,
                    "unit": ref.unit,
                    "confidence": ref.confidence,
                }
            )

    if not captures:
        detail = "; ".join(warnings) if warnings else "no usable result"
        raise AIExtractionError(f"AI vision failed for every photo: {detail}")

    return {
        "provider": getattr(provider, "name", "?"),
        "model": getattr(provider, "model", "?"),
        "captures": captures,
        "elements": elements,
        "scale_refs": scale_refs,
        "warnings": warnings,
    }


__all__ = ["AIExtractionError", "observe_photos", "PhotoObservation", "PhotoElement", "PhotoScaleRef"]