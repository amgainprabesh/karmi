"""``render.adapter.build_view`` — the payload the 3D renderer consumes.

The whole module skips while ``render.adapter`` is not importable. Once it
exists: a hand-made pair must yield a serialisable, non-empty payload that
references the scene it was built from, and empty inputs must still yield a
valid payload carrying warnings.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping

from core import schema as S
from conftest import call_adaptive, require, require_attr

adapter_mod = require(
    "render.adapter",
    reason="render.adapter is not importable yet (renderer being written in parallel) — skipping",
)


def _as_dict(payload):
    if isinstance(payload, str):
        payload = json.loads(payload)
    if dataclasses.is_dataclass(payload) and not isinstance(payload, type):
        payload = dataclasses.asdict(payload)
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    assert isinstance(payload, Mapping), f"build_view should return a mapping, got {type(payload)!r}"
    return dict(payload)


def test_build_view_on_handmade_inputs(sample_scene, sample_observed, sample_report):
    build_view = require_attr(adapter_mod, "build_view")
    view = _as_dict(call_adaptive(build_view, sample_scene, sample_observed, sample_report))

    assert view, "build_view returned an empty payload"
    blob = json.dumps(view, ensure_ascii=False)
    known_ids = {"w_south", "w_east", "w_north", "w_west", "o_window", "o_door", "r_living"}
    referenced = sum(1 for ident in known_ids if ident in blob)
    assert referenced >= 2, (
        "the view payload does not appear to reference the scene graph it was built from "
        f"(found {referenced} of {sorted(known_ids)}); keys={sorted(view)}"
    )


def test_build_view_on_empty_inputs_is_valid_with_warnings():
    build_view = require_attr(adapter_mod, "build_view")
    view = _as_dict(call_adaptive(build_view, S.SceneGraph(), S.ObservedState(), S.DiffReport()))

    blob = json.dumps(view, ensure_ascii=False).lower()
    assert "warning" in blob, (
        f"empty inputs should yield a valid payload carrying warnings; keys={sorted(view)}"
    )