"""``core.diff`` — the geometric matcher is GLOBAL BEST-FIRST.

Pins the fixed regression: with a 1.2 m and a 1.5 m drawn window and one
observed 1.5 m window, the observed element must pair with the 1.5 m drawn
window. A scene-order-greedy matcher walks the scene element by element and
gives the 1.5 m observation to whichever drawn window it reaches first (the
1.2 m one is within the 50% width tolerance), leaving the true match unmatched
and turning a perfect match into a false finding. These tests fail if that
strategy comes back.

Also pins: explicit ``matches_scene_id`` wins over geometry; an unknown
explicit id warns instead of crashing; and when two observations compete for
one drawn element the better fit wins while the loser is still reported.

Hand-made models only; no extractor, no AI, no network.
"""

from __future__ import annotations

import pytest

from core import schema as S
from conftest import make_wall, require

diff_mod = require(
    "core.diff",
    reason="core.diff is not importable yet (being written in parallel) — skipping the matcher tests",
)


def _diff(scene: S.SceneGraph, observed: S.ObservedState) -> S.DiffReport:
    fn = getattr(diff_mod, "diff_scene", None)
    assert callable(fn), "core.diff.diff_scene is missing"
    report = fn(scene, observed)
    assert isinstance(report, S.DiffReport), f"diff_scene returned {type(report)!r}, expected DiffReport"
    return report


def _opening(oid: str, width: float, *, center: tuple[float, float]) -> S.Opening:
    return S.Opening(
        id=oid,
        kind=S.OpeningKind.WINDOW,
        wall_id="w_n",
        center=center,
        width=width,
        height=1.2,
        sill_height=0.9,
        provenance=S.Provenance(source="vector_geometry", confidence=0.9, evidence="handmade"),
    )


def _obs_opening(
    oid: str,
    width: float,
    *,
    matches: str | None = None,
    hint: str = "window on the north wall",
) -> S.ObservedElement:
    return S.ObservedElement(
        id=oid,
        kind=S.ElementKind.OPENING,
        approx_size={"width": float(width)},
        location_hint=hint,
        matches_scene_id=matches,
        provenance=S.Provenance(source="ai_vision", confidence=0.85, evidence="handmade"),
    )


def _obs_wall(oid: str, length: float) -> S.ObservedElement:
    return S.ObservedElement(
        id=oid,
        kind=S.ElementKind.WALL,
        approx_size={"length": float(length)},
        location_hint="front",
        provenance=S.Provenance(source="ai_vision", confidence=0.85, evidence="handmade"),
    )


# --------------------------------------------------------------------------- #
# the fixed regression: best relative difference wins, regardless of scene order
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("scene_order", ["narrow_first", "wide_first"])
def test_observed_window_pairs_with_the_best_geometric_match(scene_order):
    win_12 = _opening("win_12", 1.2, center=(2.0, 4.0))
    win_15 = _opening("win_15", 1.5, center=(4.0, 4.0))
    openings = [win_12, win_15] if scene_order == "narrow_first" else [win_15, win_12]

    scene = S.SceneGraph(source_file="handmade://two-windows", openings=openings)
    observed = S.ObservedState(elements=[_obs_opening("obs_window", 1.5)])
    report = _diff(scene, observed)

    pair_deltas = [d for d in report.deltas if d.observed_ref == "obs_window"]
    assert len(pair_deltas) == 1, (
        f"the observed window should appear in exactly one delta, got "
        f"{[(d.scene_ref, d.observed_ref, d.status) for d in report.deltas]}"
    )
    delta = pair_deltas[0]
    assert delta.scene_ref == "win_15", (
        f"a 1.5 m observation must pair with the 1.5 m drawn window (best relative "
        f"difference), not {delta.scene_ref!r} — scene-order-greedy matching is back"
    )
    assert delta.status == S.DeltaStatus.MATCHED, (
        f"the pair is a near-exact match; got status {delta.status} ({delta.reason!r})"
    )
    assert delta.severity == S.Severity.INFO, (
        f"a 0% difference must stay within DIFF_INFO_MAX, got severity {delta.severity}"
    )
    assert delta.expected is not None and delta.expected == delta.observed, (
        f"expected/observed should be the same 1.50 m value, got "
        f"{delta.expected!r} vs {delta.observed!r}"
    )

    assert not any(
        d.scene_ref == "win_12" and d.observed_ref == "obs_window" for d in report.deltas
    ), "the 1.2 m drawn window must NOT claim the 1.5 m observation"

    # the 1.2 m window gets its own (unmatched) delta instead
    win_12_deltas = [d for d in report.deltas if d.scene_ref == "win_12"]
    assert len(win_12_deltas) == 1, f"win_12 should still be reported: {win_12_deltas}"
    assert win_12_deltas[0].observed_ref is None


# --------------------------------------------------------------------------- #
# explicit matches_scene_id beats geometry
# --------------------------------------------------------------------------- #
def test_explicit_matches_scene_id_beats_geometry():
    # win_a (1.5 m) is a perfect geometric match for the observation; win_b
    # (0.8 m) is far outside the width tolerance. The explicit id still wins.
    scene = S.SceneGraph(
        source_file="handmade://explicit-vs-geometry",
        openings=[
            _opening("win_a", 1.5, center=(1.0, 0.0)),
            _opening("win_b", 0.8, center=(3.0, 0.0)),
        ],
    )
    observed = S.ObservedState(elements=[_obs_opening("obs_e", 1.5, matches="win_b")])
    report = _diff(scene, observed)

    pair_deltas = [d for d in report.deltas if d.observed_ref == "obs_e"]
    assert len(pair_deltas) == 1, f"obs_e should appear in exactly one delta: {report.deltas}"
    assert pair_deltas[0].scene_ref == "win_b", (
        f"an explicit matches_scene_id must beat geometry; got {pair_deltas[0].scene_ref!r}"
    )
    assert not any(d.scene_ref == "win_a" and d.observed_ref == "obs_e" for d in report.deltas), (
        "the geometrically-closer element must not steal an explicitly-assigned observation"
    )


# --------------------------------------------------------------------------- #
# unknown explicit id — warning, not a crash
# --------------------------------------------------------------------------- #
def test_unknown_matches_scene_id_warns_and_does_not_crash():
    scene = S.SceneGraph(
        source_file="handmade://ghost-id",
        walls=[make_wall("w1", (0.0, 0.0), (6.0, 0.0), confidence=0.95)],
    )
    observed = S.ObservedState(
        elements=[
            S.ObservedElement(
                id="obs_x",
                kind=S.ElementKind.WALL,
                approx_size={"length": 20.0},  # far outside any tolerance
                location_hint="front",
                matches_scene_id="ghost",
                provenance=S.Provenance(source="ai_vision", confidence=0.9, evidence="handmade"),
            )
        ]
    )
    report = _diff(scene, observed)  # must not raise

    warnings = report.meta.get("warnings") or []
    assert any(
        "ghost" in str(w) and ("does not exist" in str(w) or "not exist" in str(w))
        for w in warnings
    ), f"a dangling matches_scene_id should warn about it: {warnings}"

    # the observed element is still reported (never silently dropped)
    assert any(d.observed_ref == "obs_x" for d in report.deltas), (
        f"obs_x vanished from the report: {[(d.scene_ref, d.observed_ref) for d in report.deltas]}"
    )


# --------------------------------------------------------------------------- #
# two observations competing for one drawn element
# --------------------------------------------------------------------------- #
def test_competing_observations_keep_the_better_fit_and_dont_lose_the_other():
    scene = S.SceneGraph(
        source_file="handmade://competing",
        walls=[make_wall("w1", (0.0, 0.0), (6.0, 0.0), confidence=0.95)],
    )
    # o_other (6.5 m, 8.3% off) comes first; o_best (6.0 m, 0% off) second.
    observed = S.ObservedState(elements=[_obs_wall("o_other", 6.5), _obs_wall("o_best", 6.0)])
    report = _diff(scene, observed)

    w1_deltas = [d for d in report.deltas if d.scene_ref == "w1"]
    assert len(w1_deltas) == 1, f"the drawn wall should have exactly one delta: {w1_deltas}"
    assert w1_deltas[0].observed_ref == "o_best", (
        f"the better-fitting observation (0% vs 8.3%) must win the pair, got "
        f"{w1_deltas[0].observed_ref!r}"
    )

    others = [d for d in report.deltas if d.observed_ref == "o_other"]
    assert others, "the losing observation silently vanished from the report"
    assert others[0].status in (S.DeltaStatus.UNEXPECTED, S.DeltaStatus.UNVERIFIABLE), (
        f"the losing observation must be reported as UNEXPECTED or UNVERIFIABLE, "
        f"got {others[0].status}"
    )

    reported_observed = {d.observed_ref for d in report.deltas if d.observed_ref}
    assert reported_observed == {"o_best", "o_other"}, (
        f"both observations must appear in the report: {reported_observed}"
    )