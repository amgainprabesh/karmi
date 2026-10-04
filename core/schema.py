"""Karmi — shared data contract.

Every module in the pipeline speaks these types. Do not change field names or
semantics without updating `docs/architecture.md`; parallel work depends on this
file being stable.

Vocabulary
----------
scene graph   : machine-readable model of the APPROVED building (from the naksa drawing)
observed state: machine-readable model of the AS-BUILT building (from site photos)
delta         : one element-wise difference between the two, with severity
verify list   : things a human should check — Karmi never asserts a "violation"

Coordinates are in metres, in drawing space, origin at the drawing's own origin.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# enums
# --------------------------------------------------------------------------- #
class SourceKind(str, Enum):
    VECTOR_PDF = "vector_pdf"
    RASTER_PDF = "raster_pdf"
    SCAN = "scan"
    IMAGE = "image"


class OpeningKind(str, Enum):
    DOOR = "door"
    WINDOW = "window"
    VENT = "vent"
    UNKNOWN = "unknown"


class Stage(str, Enum):
    UNKNOWN = "unknown"
    SITE = "site"
    FOUNDATION = "foundation"
    COLUMNS = "columns"
    WALLS = "walls"
    SLAB = "slab"
    ROOF = "roof"
    FINISHING = "finishing"
    COMPLETE = "complete"


class ElementKind(str, Enum):
    WALL = "wall"
    OPENING = "opening"
    COLUMN = "column"
    SLAB = "slab"
    ROOF = "roof"
    SETBACK = "setback"
    OTHER = "other"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DeltaStatus(str, Enum):
    MATCHED = "matched"
    DIFFERS = "differs"
    MISSING = "missing"          # expected in drawing, not observed on site
    UNEXPECTED = "unexpected"    # observed on site, not in drawing
    UNVERIFIABLE = "unverifiable"  # not enough evidence either way


# --------------------------------------------------------------------------- #
# provenance helpers
# --------------------------------------------------------------------------- #
class Provenance(BaseModel):
    """Where a value came from. Honesty is a feature: `confidence` and `source`
    travel with every extracted number."""

    source: Literal[
        "vector_geometry",   # deterministic, parsed from PDF paths
        "raster_geometry",   # deterministic, from image contours
        "ai_vision",         # open-weight VLM
        "ai_text",           # open-weight LLM
        "human_annotation",  # a person measured or labelled it (dataset / sidecar)
        "user_supplied",
        "default",
    ] = "default"
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence: str | None = None  # filename, page, or note


# --------------------------------------------------------------------------- #
# extraction A — approved drawing -> scene graph
# --------------------------------------------------------------------------- #
class Wall(BaseModel):
    id: str
    start: tuple[float, float]
    end: tuple[float, float]
    thickness: float | None = Field(None, description="metres")
    is_external: bool | None = None
    provenance: Provenance = Provenance()

    @field_validator("end")
    @classmethod
    def _non_degenerate(cls, v: tuple[float, float], info: Any) -> tuple[float, float]:
        start = info.data.get("start")
        if start is not None and abs(v[0] - start[0]) < 1e-9 and abs(v[1] - start[1]) < 1e-9:
            raise ValueError("wall has zero length")
        return v

    @property
    def length(self) -> float:
        return ((self.end[0] - self.start[0]) ** 2 + (self.end[1] - self.start[1]) ** 2) ** 0.5


class Opening(BaseModel):
    id: str
    kind: OpeningKind = OpeningKind.UNKNOWN
    wall_id: str | None = None
    center: tuple[float, float]
    width: float | None = Field(None, description="metres")
    height: float | None = Field(None, description="metres")
    sill_height: float | None = None
    provenance: Provenance = Provenance()


class Room(BaseModel):
    id: str
    name: str | None = None
    name_np: str | None = None
    polygon: list[tuple[float, float]]
    area_m2: float | None = None
    provenance: Provenance = Provenance()


class Dimension(BaseModel):
    id: str
    value: float
    unit: Literal["m", "ft", "ft_in", "unknown"] = "m"
    label: str | None = None
    start: tuple[float, float] | None = None
    end: tuple[float, float] | None = None
    provenance: Provenance = Provenance()

    def to_metres(self) -> float | None:
        if self.unit == "m":
            return self.value
        if self.unit == "ft":
            return self.value * 0.3048
        return None


class SceneGraph(BaseModel):
    """The APPROVED building."""

    schema_version: str = SCHEMA_VERSION
    source_kind: SourceKind = SourceKind.VECTOR_PDF
    source_file: str | None = None
    units: Literal["m"] = "m"

    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)
    dimensions: list[Dimension] = Field(default_factory=list)

    north_deg: float | None = None
    north_provenance: Provenance = Provenance()
    scale_m_per_unit: float | None = None
    scale_provenance: Provenance = Provenance()

    bbox: tuple[float, float, float, float] | None = Field(
        None, description="(minx, miny, maxx, maxy) in metres"
    )
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    def summary(self) -> dict[str, int]:
        return {
            "walls": len(self.walls),
            "openings": len(self.openings),
            "rooms": len(self.rooms),
            "dimensions": len(self.dimensions),
            "warnings": len(self.warnings),
        }


# --------------------------------------------------------------------------- #
# extraction B — site photos -> observed state
# --------------------------------------------------------------------------- #
class ScaleRef(BaseModel):
    kind: Literal["brick_course", "door_height", "user_dimension", "known_object", "unknown"] = (
        "unknown"
    )
    value: float
    unit: Literal["m", "mm", "ft"] = "m"
    provenance: Provenance = Provenance()


class Capture(BaseModel):
    file: str
    taken_at: str | None = None
    stage: Stage = Stage.UNKNOWN
    stage_confidence: float = Field(0.0, ge=0.0, le=1.0)
    view: Literal["front", "side", "rear", "interior", "aerial", "unknown"] = "unknown"
    provenance: Provenance = Provenance()


class ObservedElement(BaseModel):
    id: str
    kind: ElementKind
    approx_size: dict[str, float] = Field(
        default_factory=dict, description="e.g. {'length': 3.2, 'height': 2.7} in metres"
    )
    location_hint: str | None = Field(
        None, description="human-readable, e.g. 'front-left corner'"
    )
    matches_scene_id: str | None = Field(
        None, description="id of the scene-graph element this is believed to be"
    )
    provenance: Provenance = Provenance()


class ObservedState(BaseModel):
    """The AS-BUILT building."""

    schema_version: str = SCHEMA_VERSION
    stage: Stage = Stage.UNKNOWN
    stage_provenance: Provenance = Provenance()
    captures: list[Capture] = Field(default_factory=list)
    elements: list[ObservedElement] = Field(default_factory=list)
    scale_refs: list[ScaleRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    def summary(self) -> dict[str, int]:
        return {
            "captures": len(self.captures),
            "elements": len(self.elements),
            "scale_refs": len(self.scale_refs),
            "warnings": len(self.warnings),
        }


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #
class Delta(BaseModel):
    id: str
    element: str = Field(description="human label, e.g. 'window on north wall'")
    scene_ref: str | None = None
    observed_ref: str | None = None
    status: DeltaStatus = DeltaStatus.UNVERIFIABLE
    expected: str | None = None
    observed: str | None = None
    severity: Severity = Severity.INFO
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reason: str | None = Field(None, description="English, one line")
    reason_np: str | None = Field(None, description="Nepali, one line")


class VerifyItem(BaseModel):
    id: str
    item: str = Field(description="what to check, plain language")
    item_np: str | None = None
    why: str | None = None
    how: str | None = Field(None, description="concrete next step for the homeowner")
    severity: Severity = Severity.INFO
    delta_ref: str | None = None


class DiffReport(BaseModel):
    schema_version: str = SCHEMA_VERSION
    scene_file: str | None = None
    observed_files: list[str] = Field(default_factory=list)

    deltas: list[Delta] = Field(default_factory=list)
    verify_list: list[VerifyItem] = Field(default_factory=list)

    summary: dict[str, int] = Field(default_factory=dict)
    narration_np: list[str] = Field(default_factory=list)
    narration_en: list[str] = Field(default_factory=list)

    limits: list[str] = Field(
        default_factory=list,
        description="honest statements about what this run could not determine",
    )
    meta: dict[str, Any] = Field(default_factory=dict)

    def recount(self) -> "DiffReport":
        counts = {s.value: 0 for s in Severity}
        for d in self.deltas:
            counts[d.severity.value] += 1
        counts["total"] = len(self.deltas)
        counts["matched"] = sum(1 for d in self.deltas if d.status == DeltaStatus.MATCHED)
        counts["verify_items"] = len(self.verify_list)
        self.summary = counts
        return self


__all__ = [
    "SCHEMA_VERSION",
    "SourceKind",
    "OpeningKind",
    "Stage",
    "ElementKind",
    "Severity",
    "DeltaStatus",
    "Provenance",
    "Wall",
    "Opening",
    "Room",
    "Dimension",
    "SceneGraph",
    "ScaleRef",
    "Capture",
    "ObservedElement",
    "ObservedState",
    "Delta",
    "VerifyItem",
    "DiffReport",
]