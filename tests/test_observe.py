"""``core.observe`` — site photos -> observed state. Offline, never raises.

The whole module skips while ``core.observe`` is not importable. The tests
assert the degradation contract (empty / unreadable inputs warn instead of
crashing), sidecar-driven observations carry provenance, and the offline path
genuinely touches no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import schema as S
from conftest import NETWORK_SENTINEL, call_adaptive, no_network, require, require_attr

observe_mod = require(
    "core.observe",
    reason="core.observe is not importable yet (being written in parallel) — skipping the photo tests",
)


def _observe(photos, **kwargs):
    to_observed_state = require_attr(observe_mod, "to_observed_state")
    return call_adaptive(
        to_observed_state,
        [str(p) for p in photos],
        known_dimension=None,
        ai=None,
        stage_hint=None,
        **kwargs,
    )


def _write_photo(path: Path) -> Path:
    try:
        from PIL import Image

        Image.new("RGB", (96, 96), (140, 140, 140)).save(path)
    except Exception:  # pragma: no cover - Pillow is a declared dependency
        path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    return path


_SIDECAR_ELEMENT = {
    "id": "obs_front_wall",
    "kind": "wall",
    "approx_size": {"length": 6.0, "height": 2.7},
    "location_hint": "front",
    "matches_scene_id": "w_south",
    "confidence": 0.8,
}
_SIDECAR_OBJECT = {
    "stage": "walls",
    "stage_confidence": 0.8,
    "view": "front",
    "elements": [_SIDECAR_ELEMENT],
    "scale_refs": [{"kind": "brick_course", "value": 0.075, "unit": "m"}],
}
_SIDECAR_LIST = [_SIDECAR_ELEMENT]


def test_empty_photo_list_is_valid_and_warns():
    state = _observe([])
    assert isinstance(state, S.ObservedState)
    assert state.warnings, "an empty photo list should produce at least one warning"


def test_unreadable_photo_degrades_to_warning(tmp_path):
    state = _observe([tmp_path / "does_not_exist.jpg"])
    assert isinstance(state, S.ObservedState)
    assert state.warnings, "a missing photo file should degrade to a warning, not a crash"


def test_sidecar_observation_produces_elements_with_provenance(tmp_path):
    photo = _write_photo(tmp_path / "front.jpg")
    sidecar = tmp_path / "front.sidecar.json"

    attempts = []
    state = None
    for payload in (_SIDECAR_OBJECT, _SIDECAR_LIST):
        sidecar.write_text(json.dumps(payload), encoding="utf-8")
        try:
            candidate = _observe([photo], sidecars={str(photo): str(sidecar)})
        except Exception as exc:  # a bad sidecar must not crash observation either
            attempts.append(f"{type(payload).__name__} sidecar raised {type(exc).__name__}: {exc}")
            continue
        if candidate.elements:
            state = candidate
            break
        attempts.append(f"{type(payload).__name__} sidecar produced no elements")

    assert state is not None, (
        "core.observe did not consume a sidecar in either of two plausible shapes "
        f"({'; '.join(attempts)}); check the sidecar format it expects"
    )
    for element in state.elements:
        assert isinstance(element.provenance, S.Provenance), f"element {element.id} has no provenance"
    assert any(
        e.provenance.confidence > 0.0 or e.provenance.source != "default" for e in state.elements
    ), "sidecar-driven elements should carry a provenance signal (confidence / source)"


def test_offline_path_touches_no_network(tmp_path, monkeypatch):
    photo = _write_photo(tmp_path / "front.jpg")
    sidecar = tmp_path / "front.sidecar.json"
    sidecar.write_text(json.dumps(_SIDECAR_OBJECT), encoding="utf-8")

    with no_network(monkeypatch) as sentinel:
        assert sentinel == NETWORK_SENTINEL
        empty_state = _observe([])
        state = _observe([photo], sidecars={str(photo): str(sidecar)})

    assert isinstance(empty_state, S.ObservedState)
    assert isinstance(state, S.ObservedState)
    blob = state.model_dump_json()
    assert sentinel not in blob, f"observation attempted real network access: {blob[:400]}"