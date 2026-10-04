"""Schema contract tests.

``core/schema.py`` is the frozen contract every other module speaks, so these
tests must run (and pass) no matter which parallel modules exist. They assert
the invariants the contract guarantees:

* every model round-trips through JSON unchanged;
* a zero-length wall is rejected;
* confidence is bounded to 0..1;
* ``recount()`` produces a coherent summary;
* enums serialise as their plain string values.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from core import schema as S


def _instances():
    prov = S.Provenance(source="vector_geometry", confidence=0.9, evidence="plan.pdf page 1")
    wall = S.Wall(
        id="w1", start=(0.0, 0.0), end=(4.0, 0.0), thickness=0.23, is_external=True, provenance=prov
    )
    opening = S.Opening(
        id="o1", kind=S.OpeningKind.DOOR, wall_id="w1", center=(1.0, 0.0), width=0.9,
        height=2.1, sill_height=0.0, provenance=prov,
    )
    room = S.Room(
        id="r1", name="LIVING", name_np="बैठक",
        polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)], area_m2=12.0, provenance=prov,
    )
    dim = S.Dimension(
        id="d1", value=4.0, unit="m", label="4.0 m", start=(0.0, 0.0), end=(4.0, 0.0),
        provenance=prov,
    )
    scene = S.SceneGraph(
        source_kind=S.SourceKind.VECTOR_PDF,
        source_file="plan.pdf",
        walls=[wall],
        openings=[opening],
        rooms=[room],
        dimensions=[dim],
        north_deg=0.0,
        scale_m_per_unit=0.025,
        bbox=(0.0, 0.0, 4.0, 3.0),
        warnings=["north arrow missing"],
        meta={"pages": 1},
    )
    scale_ref = S.ScaleRef(kind="door_height", value=2.1, unit="m", provenance=prov)
    capture = S.Capture(
        file="front.jpg", taken_at="2026-10-01T09:00:00", stage=S.Stage.WALLS,
        stage_confidence=0.8, view="front", provenance=prov,
    )
    element = S.ObservedElement(
        id="e1", kind=S.ElementKind.WALL, approx_size={"length": 4.0, "height": 2.7},
        location_hint="front-left", matches_scene_id="w1", provenance=prov,
    )
    observed = S.ObservedState(
        stage=S.Stage.WALLS, stage_provenance=prov, captures=[capture], elements=[element],
        scale_refs=[scale_ref], warnings=["one photo was blurry"], meta={"n_photos": 1},
    )
    delta = S.Delta(
        id="x1", element="door o1", scene_ref="o1", observed_ref="e1",
        status=S.DeltaStatus.DIFFERS, expected="width 0.9 m", observed="width 0.8 m",
        severity=S.Severity.MEDIUM, confidence=0.6, reason="Narrower.",
        reason_np="साँघुरो।",
    )
    verify = S.VerifyItem(
        id="v1", item="Measure the front door width.",
        item_np="अगाडिको ढोकाको चौडाइ नाप्नुहोस्।", why="Photos suggest it is narrower.",
        how="Use a tape measure.", severity=S.Severity.MEDIUM, delta_ref="x1",
    )
    report = S.DiffReport(
        scene_file="plan.pdf",
        observed_files=["front.jpg"],
        deltas=[delta],
        verify_list=[verify],
        narration_en=["Door may be narrow."],
        narration_np=["ढोका साँघुरो हुन सक्छ।"],
        limits=["Wall thickness unverifiable."],
        meta={"run": 1},
    ).recount()
    return [prov, wall, opening, room, dim, scene, scale_ref, capture, element, observed, delta, verify, report]


@pytest.mark.parametrize("model", _instances(), ids=lambda m: type(m).__name__)
def test_every_model_roundtrips_through_json(model):
    as_json = model.model_dump_json()
    restored = type(model).model_validate_json(as_json)
    assert restored == model, f"{type(model).__name__} changed after a JSON round-trip"

    # the same via a plain dict round-trip
    payload = model.model_dump(mode="json")
    assert type(model).model_validate(json.loads(json.dumps(payload))) == model

    # json-mode dumps must be strictly JSON-serialisable (no enum/tuple leaks)
    assert json.loads(json.dumps(payload)) == payload


def test_zero_length_wall_is_rejected():
    with pytest.raises(ValidationError):
        S.Wall(id="w0", start=(1.0, 1.0), end=(1.0, 1.0))
    with pytest.raises(ValidationError):
        S.Wall(id="w0", start=(1.0, 1.0), end=(1.0 + 1e-12, 1.0))
    # a short but real wall is accepted
    assert S.Wall(id="w1", start=(0.0, 0.0), end=(0.001, 0.0)).length == pytest.approx(0.001)


@pytest.mark.parametrize("bad", [-0.01, -1.0, 1.01, 2.0, 1e9])
def test_confidence_outside_0_1_is_rejected(bad):
    with pytest.raises(ValidationError):
        S.Provenance(confidence=bad)
    with pytest.raises(ValidationError):
        S.Delta(id="d", element="e", confidence=bad)
    with pytest.raises(ValidationError):
        S.Capture(file="f.jpg", stage_confidence=bad)


def test_confidence_bounds_are_inclusive():
    assert S.Provenance(confidence=0.0).confidence == 0.0
    assert S.Provenance(confidence=1.0).confidence == 1.0
    assert S.Delta(id="d", element="e", confidence=1.0).confidence == 1.0
    assert S.Capture(file="f.jpg", stage_confidence=0.0).stage_confidence == 0.0


def test_recount_produces_a_coherent_summary():
    severities = [
        S.Severity.INFO, S.Severity.INFO, S.Severity.LOW,
        S.Severity.MEDIUM, S.Severity.HIGH, S.Severity.HIGH,
    ]
    statuses = [
        S.DeltaStatus.MATCHED, S.DeltaStatus.DIFFERS, S.DeltaStatus.MISSING,
        S.DeltaStatus.UNEXPECTED, S.DeltaStatus.UNVERIFIABLE, S.DeltaStatus.DIFFERS,
    ]
    deltas = [
        S.Delta(id=f"d{i}", element=f"e{i}", status=status, severity=severity)
        for i, (status, severity) in enumerate(zip(statuses, severities))
    ]
    verify = [S.VerifyItem(id="v1", item="check one"), S.VerifyItem(id="v2", item="check two")]
    report = S.DiffReport(deltas=deltas, verify_list=verify)

    out = report.recount()
    assert out is report
    assert report.summary == {
        "info": 2, "low": 1, "medium": 1, "high": 2,
        "total": 6, "matched": 1, "verify_items": 2,
    }
    report.recount()  # idempotent
    assert report.summary["total"] == 6

    empty = S.DiffReport().recount()
    assert empty.summary == {
        "info": 0, "low": 0, "medium": 0, "high": 0,
        "total": 0, "matched": 0, "verify_items": 0,
    }


def test_enums_serialise_as_their_values():
    for enum_cls in (S.SourceKind, S.OpeningKind, S.Stage, S.ElementKind, S.Severity, S.DeltaStatus):
        for member in enum_cls:
            assert member.value and member.value == member.value.lower()
            assert json.dumps(member) == f'"{member.value}"'

    delta = S.Delta(id="d", element="e", status=S.DeltaStatus.DIFFERS, severity=S.Severity.HIGH)
    dumped = delta.model_dump(mode="json")
    assert dumped["status"] == "differs"
    assert dumped["severity"] == "high"
    assert type(dumped["status"]) is str

    scene = S.SceneGraph(source_kind=S.SourceKind.RASTER_PDF)
    assert json.loads(scene.model_dump_json())["source_kind"] == "raster_pdf"

    opening = S.Opening(id="o", center=(0.0, 0.0), kind=S.OpeningKind.WINDOW)
    assert json.loads(opening.model_dump_json())["kind"] == "window"


def test_dimension_to_metres():
    assert S.Dimension(id="d", value=3.0, unit="m").to_metres() == 3.0
    assert S.Dimension(id="d", value=10.0, unit="ft").to_metres() == pytest.approx(3.048)
    assert S.Dimension(id="d", value=1.0, unit="ft_in").to_metres() is None
    assert S.Dimension(id="d", value=1.0, unit="unknown").to_metres() is None


def test_summary_counts_track_the_lists(sample_scene, sample_observed):
    assert sample_scene.summary() == {
        "walls": 5, "openings": 2, "rooms": 1, "dimensions": 1, "warnings": 0,
    }
    assert sample_observed.summary() == {
        "captures": 1, "elements": 2, "scale_refs": 0, "warnings": 0,
    }


def test_schema_version_is_coherent():
    assert isinstance(S.SCHEMA_VERSION, str) and S.SCHEMA_VERSION
    assert S.SceneGraph().schema_version == S.SCHEMA_VERSION
    assert S.ObservedState().schema_version == S.SCHEMA_VERSION
    assert S.DiffReport().schema_version == S.SCHEMA_VERSION