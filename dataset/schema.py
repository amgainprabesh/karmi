"""Karmi dataset — the annotation record contract.

One record = one building project (one house, one naksa approval) — not one
page and not one photo. A house is the unit of consent, the unit of
de-identification, and the unit of the train/test split, so pages and photos
of the same house can never straddle splits (dataset-plan §1, §6).

This module deliberately **reuses** the frozen types from ``core/schema.py``:

* ``SceneGraph``  — the drawing side of the record (approved building);
* ``ObservedState`` — the photo side, one per annotated photo (this matches the
  sidecar format that ``core/observe.py`` already reads: a ``photo.jpg.json``
  next to a photo);
* ``Provenance`` — every annotated element carries its source; ground truth
  written by a human uses the ``human_annotation`` literal, so "was this drawn
  by a model or a human?" is answerable per element (dataset-plan §2.2);
* ``SourceKind`` — vector_pdf / raster_pdf / scan / image.

The record cannot be constructed without a consent block and a licence; a
public-tier record additionally requires that *every* signatory granted dataset
release and that the record's licence is inside every signatory's licence
scope (Copyright Act 2059: a CC licence can only be granted by the rights
holder — dataset-plan §4). See ``dataset/consent.py`` for the legal reasoning.

Honesty fields are first-class: ``synthetic`` marks example records generated
from the repo's fixtures (never real data), ``quality`` carries review flags,
and the free-text ``notes`` field is scanned by ``dataset.deidentify``.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from core.schema import (
    SCHEMA_VERSION,
    ObservedState,
    Provenance,
    SceneGraph,
    SourceKind,
)
from dataset.consent import (
    Consent,
    ConsentRole,
    Licence,
    LicenceId,
)

__all__ = [
    "DATASET_VERSION",
    "ReleaseTier",
    "Jurisdiction",
    "DrawingAnnotation",
    "PhotoAnnotation",
    "Annotator",
    "AnnotationQuality",
    "DatasetRecord",
    # re-exports so `from dataset.schema import ...` is enough for consumers
    "Consent",
    "ConsentRole",
    "Licence",
    "LicenceId",
    "SceneGraph",
    "ObservedState",
    "Provenance",
    "SourceKind",
]

#: Version of the dataset record schema. Tracks ``core.schema.SCHEMA_VERSION``:
#: "a schema bump is a dataset version bump" (dataset-plan §1).
DATASET_VERSION = SCHEMA_VERSION

_ABS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/|~[\\/])")
_RECORD_ID_RE = re.compile(r"^karmi-[a-z0-9][a-z0-9-]*$")
_OPAQUE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _check_opaque_relpath(value: str, what: str) -> str:
    """File names in a record must be relative, opaque and path-safe.

    SECURITY.md T6: absolute paths leak the contributor's username and folder
    structure, and dataset exports rename files to opaque IDs before release.
    """
    v = value.strip()
    if _ABS_PATH_RE.match(v):
        raise ValueError(f"{what} must be a relative, opaque file name, not {value!r}")
    if ".." in v.split("/") or "\\" in v:
        raise ValueError(f"{what} must use forward slashes and no '..' segments: {value!r}")
    if not _OPAQUE_FILE_RE.match(v):
        raise ValueError(
            f"{what} must be an opaque relative path (letters/digits/._-), got {value!r}"
        )
    return v


class ReleaseTier(str, Enum):
    """Where a record is allowed to appear (dataset-plan §7)."""

    PUBLIC = "public"   # redacted tier, open on the Hub
    GATED = "gated"     # access-request tier with manual approval


class Jurisdiction(BaseModel):
    """Coarse location. Municipality/district are optional; ward is only kept
    when the contributor agreed (dataset-plan §5: "generalize rather than
    redact where useful" — GPS is always dropped, ward-level may stay)."""

    municipality: str | None = Field(None, description='e.g. "Kathmandu Metropolitan City" or "withheld"')
    district: str | None = None
    ward: str | None = Field(None, description="coarse location, only with contributor agreement")

    def display(self) -> str:
        parts = [p for p in (self.municipality, self.district) if p]
        if self.ward:
            parts.append(f"Ward {self.ward}")
        return ", ".join(parts) if parts else "withheld"


class DrawingAnnotation(BaseModel):
    """The drawing side of a record: the ground-truth SceneGraph plus release
    bookkeeping. ``page_files`` names the *public, redacted* page renders
    (opaque names); the original PDF itself is never part of a public release
    (dataset-plan §5: render at 300 dpi, never publish the original text layer)."""

    scene: SceneGraph
    page_files: list[str] = Field(default_factory=list)
    original_sha256: str | None = Field(
        None, description="hash of the original drawing file (provenance without shipping it)"
    )
    provenance: Provenance = Provenance()
    notes: str | None = None

    @field_validator("page_files")
    @classmethod
    def _page_files_relative(cls, v: list[str]) -> list[str]:
        return [_check_opaque_relpath(x, "drawing.page_files entry") for x in v]

    @model_validator(mode="after")
    def _scene_source_file_must_be_relative(self) -> "DrawingAnnotation":
        sf = self.scene.source_file
        if sf and _ABS_PATH_RE.match(sf.strip()):
            raise ValueError(
                "drawing.scene.source_file must be a relative reference (or null), "
                f"not an absolute path — absolute paths leak the contributor's "
                f"machine layout (SECURITY.md T6): {sf!r}"
            )
        return self


class PhotoAnnotation(BaseModel):
    """One annotated photo: an ``ObservedState`` scoped to that photo.

    The ``observed`` object follows the same shape ``core/observe.py`` builds
    from a sidecar (``photo.jpg.json``): captures + elements + scale_refs, so
    annotations made in ``dataset/annotate.html`` can be dropped next to a
    photo and read by the existing pipeline.
    """

    file: str = Field(description="opaque release file name, e.g. 'photos/p01-front.jpg'")
    observed: ObservedState
    original_sha256: str | None = None
    redacted: bool = Field(
        False,
        description="True once this photo's release copy has been through "
        "dataset.deidentify (EXIF stripped, people excluded per consent)",
    )
    provenance: Provenance = Provenance()
    notes: str | None = None

    @field_validator("file")
    @classmethod
    def _file_relative(cls, v: str) -> str:
        return _check_opaque_relpath(v, "photo.file")


class Annotator(BaseModel):
    """Pseudonymous annotator identity — never a name or contact (plan §8:
    annotation labour is paid and credited, but a released record carries an id,
    not a person)."""

    annotator_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    role: Literal["core_team", "volunteer", "contributor"] = "core_team"
    tool: str | None = Field(None, description="e.g. 'dataset/annotate.html'")


class AnnotationQuality(BaseModel):
    """Machine-readable quality flags (dataset-plan §8: double-annotate ≥10%)."""

    reviewed: bool = False
    double_annotated: bool = False
    n_annotators: int = Field(1, ge=1)
    completeness: float = Field(
        0.0, ge=0.0, le=1.0, description="fraction of the annotation checklist completed"
    )
    issues: list[str] = Field(
        default_factory=list, description="known problems a consumer must know about"
    )

    @model_validator(mode="after")
    def _double_implies_two(self) -> "AnnotationQuality":
        if self.double_annotated and self.n_annotators < 2:
            raise ValueError("double_annotated=True requires n_annotators >= 2")
        return self


class DatasetRecord(BaseModel):
    """One annotated building project — the dataset's atomic unit.

    Required by construction: ``record_id``, ``source_kind``, ``consent``,
    ``licence``, ``drawing``, ``annotator``. There is no code path that makes a
    record without consent, and a public-tier record must additionally satisfy
    the consent/licence coverage rules below.
    """

    schema_version: str = DATASET_VERSION
    record_id: str = Field(
        pattern=_RECORD_ID_RE.pattern,
        description="opaque id, e.g. 'karmi-0001' — filenames are never used as ids "
        "(SECURITY.md T6.5: original filenames can contain a name)",
    )
    synthetic: bool = Field(
        False,
        description="True for fixture-derived example records. Such records must "
        "never be presented as collected data.",
    )
    source_kind: SourceKind
    jurisdiction: Jurisdiction | None = None
    consent: Consent
    licence: Licence
    release_tier: ReleaseTier = ReleaseTier.PUBLIC
    drawing: DrawingAnnotation
    photos: list[PhotoAnnotation] = Field(default_factory=list)
    annotator: Annotator
    quality: AnnotationQuality = Field(default_factory=AnnotationQuality)
    notes: str | None = None
    created_at: datetime | None = None

    # -- structural checks --------------------------------------------------- #
    @field_validator("photos")
    @classmethod
    def _photo_files_unique(cls, v: list[PhotoAnnotation]) -> list[PhotoAnnotation]:
        seen = [p.file for p in v]
        if len(set(seen)) != len(seen):
            dupes = sorted({x for x in seen if seen.count(x) > 1})
            raise ValueError(f"photo file names must be unique within a record: {dupes}")
        return v

    # -- consent / licence coverage ----------------------------------------- #
    @model_validator(mode="after")
    def _release_requirements(self) -> "DatasetRecord":
        # 1. The record must be able to name its rights: a public release needs
        #    dataset_release=True from every signatory (Privacy Act purpose
        #    limitation; Copyright Act: licence from the rights holder(s)).
        if self.release_tier == ReleaseTier.PUBLIC and not self.consent.withdrawn:
            not_releasing = [
                g for g in self.consent.grants if not g.scope.dataset_release
            ]
            if not_releasing:
                roles = sorted(
                    {r.value for g in not_releasing for r in g.roles}
                )
                raise ValueError(
                    "public-tier record requires dataset_release=True in every "
                    f"consent grant; these signatories did not grant release: {roles}"
                )
            # 2. Every signatory's licence scope must cover the record licence.
            covered = self.consent.licence_intersection()
            if self.licence.id.value not in covered:
                raise ValueError(
                    f"record licence {self.licence.id.value!r} is not covered by every "
                    f"signatory's licence scope (intersection: {sorted(covered) or 'empty'}) "
                    "— get the missing grant or lower the licence (dataset-plan §4)"
                )
        # 3. Withdrawn records cannot sit in the public tier.
        if self.consent.withdrawn and self.release_tier == ReleaseTier.PUBLIC:
            raise ValueError(
                "a withdrawn record cannot remain in the public tier; set "
                "release_tier='gated' (it will be excluded from exports regardless)"
            )
        return self

    # -- helpers ------------------------------------------------------------- #
    def summary(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "synthetic": self.synthetic,
            "tier": self.release_tier.value,
            "source_kind": self.source_kind.value,
            "licence": self.licence.id.value,
            "withdrawn": self.consent.withdrawn,
            "walls": len(self.drawing.scene.walls),
            "openings": len(self.drawing.scene.openings),
            "rooms": len(self.drawing.scene.rooms),
            "photos": len(self.photos),
            "photo_elements": sum(len(p.observed.elements) for p in self.photos),
        }

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            self.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        return p