"""``core.diff`` — the coverage guard: absence of evidence is not evidence of absence.

Pins the rule introduced with ``COVERAGE_SPARSE_RATIO``:

* when the site evidence could only be compared against fewer than that share
  of the drawn elements, every unmatched drawn element is UNVERIFIABLE at LOW
  severity (reason keyed ``not_covered``) — never MISSING/HIGH;
* when coverage is at or above the ratio, unmatched drawn elements keep their
  normal MISSING severity (the guard must not swallow real findings);
* ``report.meta`` carries ``coverage`` and ``coverage_sparse``, and
  ``report.limits`` states the coverage numbers;
* an empty scene neither crashes nor emits a spurious coverage warning.

All models are hand-made; no extractor, no AI, no network. The threshold is
always read from the module — never hardcoded.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from core import schema as S
from conftest import make_wall, require

diff_mod = require(
    "core.diff",
    reason="core.diff is not importable yet (being written in parallel) — skipping the coverage-guard tests",
)

#: The guard's own threshold; None means the behaviour was removed (a failure
#: inside each test, not a skip — this file exists to pin that behaviour).
COVERAGE_SPARSE_RATIO = getattr(diff_mod, "COVERAGE_SPARSE_RATIO", None)
_MISSING_SEVERITY = getattr(diff_mod, "MISSING_SEVERITY", {})


def _ratio() -> float:
    assert COVERAGE_SPARSE_RATIO is not None, (
        "core.diff no longer exposes COVERAGE_SPARSE_RATIO — the coverage guard was removed"
    )
    return float(COVERAGE_SPARSE_RATIO)


def _diff(scene: S.SceneGraph, observed: S.ObservedState) -> S.DiffReport:
    fn = getattr(diff_mod, "diff_scene", None)
    assert callable(fn), "core.diff.diff_scene is missing"
    report = fn(scene, observed)
    assert isinstance(report, S.DiffReport), f"diff_scene returned {type(report)!r}, expected DiffReport"
    return report


def _wall(i: int, length: float) -> S.Wall:
    return make_wall(f"w{i}", (0.0, float(i)), (float(length), float(i)), confidence=0.95)


def _obs_wall(i: int, length: float, *, matches: str | None = None) -> S.ObservedElement:
    return S.ObservedElement(
        id=f"o{i}",
        kind=S.ElementKind.WALL,
        approx_size={"length": float(length)},
        location_hint="front",
        matches_scene_id=matches,
        provenance=S.Provenance(source="ai_vision", confidence=0.8, evidence="handmade"),
    )


def _mentions_coverage(line: str) -> bool:
    """True when a limits line is the coverage statement (either language)."""
    low = str(line).lower()
    return "cover" in low or "समेटे" in str(line)


# --------------------------------------------------------------------------- #
# sparse coverage — unmatched drawn elements are "not checked", not "missing"
# --------------------------------------------------------------------------- #
def test_sparse_coverage_reports_unmatched_as_unverifiable_low():
    ratio = _ratio()
    lengths = [6.0, 5.0, 4.0, 3.0, 2.0]
    scene = S.SceneGraph(
        source_file="handmade://coverage-sparse",
        walls=[_wall(i, L) for i, L in enumerate(lengths)],
    )
    observed = S.ObservedState(elements=[_obs_wall(1, 6.0)])
    report = _diff(scene, observed)

    total = len(scene.walls)
    matched = 1
    coverage = report.meta.get("coverage")

    assert report.meta.get("coverage_sparse") is True, (
        f"coverage {coverage!r} of {total} drawn elements should be flagged sparse: {report.meta}"
    )
    assert coverage == pytest.approx(matched / total), (
        f"meta['coverage'] should equal matched/total ({matched}/{total}), got {coverage!r}"
    )
    assert coverage < ratio
    assert report.meta.get("matched_pairs") == matched

    unmatched_refs = {f"w{i}" for i in range(1, total)}
    unmatched = [d for d in report.deltas if d.scene_ref in unmatched_refs]
    assert len(unmatched) == total - matched, (
        f"expected {total - matched} unmatched drawn elements, got "
        f"{[(d.scene_ref, d.status) for d in report.deltas]}"
    )
    for d in unmatched:
        assert d.status == S.DeltaStatus.UNVERIFIABLE, (
            f"unmatched drawn element {d.scene_ref} should be UNVERIFIABLE under sparse "
            f"coverage, got {d.status}"
        )
        assert d.severity == S.Severity.LOW, (
            f"unmatched drawn element {d.scene_ref} should be LOW severity under sparse "
            f"coverage (not {d.severity})"
        )
        assert d.reason and "cover" in d.reason.lower(), (
            f"the reason should say the photos do not cover this part, got {d.reason!r}"
        )

    assert all(d.status != S.DeltaStatus.MISSING for d in report.deltas), (
        f"sparse coverage must not produce MISSING findings: "
        f"{[(d.scene_ref, d.status) for d in report.deltas]}"
    )
    assert report.meta.get("missing") == 0
    assert report.meta.get("unverifiable") == total - matched
    assert report.summary.get("high", 0) == 0, (
        f"sparse coverage must not report HIGH-severity findings: {report.summary}"
    )

    coverage_lines = [line for line in report.limits if _mentions_coverage(line)]
    assert coverage_lines, f"limits do not state the coverage numbers: {report.limits}"
    assert any(
        str(matched) in line and str(total) in line and str(total - matched) in line
        for line in coverage_lines
    ), f"the coverage limit should mention {matched}/{total} (uncovered {total - matched}): {coverage_lines}"

    warnings = report.meta.get("warnings") or []
    assert any("cover" in str(w).lower() for w in warnings), (
        f"a warning should explain the sparse coverage substitution: {warnings}"
    )

    # the one matched pair is unaffected by the guard
    matched_deltas = [d for d in report.deltas if d.scene_ref == "w0"]
    assert len(matched_deltas) == 1
    assert matched_deltas[0].status == S.DeltaStatus.MATCHED


# --------------------------------------------------------------------------- #
# dense coverage — the guard must not swallow real findings
# --------------------------------------------------------------------------- #
def test_dense_coverage_keeps_normal_missing_findings():
    ratio = _ratio()
    lengths = [6.0, 5.0, 4.0, 3.0, 2.0]
    scene = S.SceneGraph(
        source_file="handmade://coverage-dense",
        walls=[_wall(i, L) for i, L in enumerate(lengths)],
    )
    observed = S.ObservedState(elements=[_obs_wall(i, L) for i, L in enumerate(lengths[:4])])
    report = _diff(scene, observed)

    assert report.meta.get("coverage") == pytest.approx(4 / 5)
    assert report.meta.get("coverage") >= ratio
    assert report.meta.get("coverage_sparse") is False, (
        f"4/5 coverage is above the sparse ratio — the guard must not trigger: {report.meta}"
    )

    unmatched = [d for d in report.deltas if d.scene_ref == "w4"]
    assert len(unmatched) == 1, f"expected exactly one delta for w4, got {unmatched}"
    delta = unmatched[0]
    assert delta.status == S.DeltaStatus.MISSING, (
        f"with dense coverage an unobserved wall is a real MISSING finding, got {delta.status}"
    )
    assert delta.severity == _MISSING_SEVERITY.get("wall", S.Severity.HIGH), (
        f"MISSING wall severity should come from MISSING_SEVERITY, got {delta.severity}"
    )
    assert delta.severity != S.Severity.LOW, "the coverage guard swallowed a real finding"
    assert report.summary.get("matched") == 4


# --------------------------------------------------------------------------- #
# boundary — coverage exactly at the threshold is NOT sparse
# --------------------------------------------------------------------------- #
def test_coverage_exactly_at_the_threshold_is_not_sparse():
    ratio = _ratio()
    frac = Fraction(ratio).limit_denominator(64)
    if frac.denominator > 40 or not (0 < frac.numerator < frac.denominator):
        pytest.skip(f"COVERAGE_SPARSE_RATIO={ratio!r} does not admit a small exact fraction")
    total = frac.denominator * 2
    matched = frac.numerator * 2

    scene = S.SceneGraph(
        source_file="handmade://coverage-boundary",
        walls=[_wall(i, 2.0 + i * 0.5) for i in range(total)],
    )
    # explicit ids keep the pairing (and therefore the coverage) deterministic
    observed = S.ObservedState(
        elements=[_obs_wall(i, 2.0 + i * 0.5, matches=f"w{i}") for i in range(matched)]
    )
    report = _diff(scene, observed)

    assert report.meta.get("coverage") == pytest.approx(ratio, abs=1e-6), (
        f"expected coverage to land exactly on the threshold, got {report.meta.get('coverage')!r}"
    )
    assert report.meta.get("coverage_sparse") is False, (
        "sparse is a strict 'below the ratio' condition — at the threshold the guard stays off"
    )

    unmatched_refs = {f"w{i}" for i in range(matched, total)}
    unmatched = [d for d in report.deltas if d.scene_ref in unmatched_refs]
    assert len(unmatched) == total - matched
    assert all(d.status == S.DeltaStatus.MISSING for d in unmatched), (
        f"at the threshold, unmatched drawn elements keep normal statuses: "
        f"{[(d.scene_ref, d.status) for d in unmatched]}"
    )


# --------------------------------------------------------------------------- #
# empty scene — no crash, no spurious coverage warning
# --------------------------------------------------------------------------- #
def test_empty_scene_does_not_crash_or_warn_about_coverage():
    report = _diff(S.SceneGraph(), S.ObservedState())

    assert report.deltas == []
    assert report.meta.get("coverage") == 1.0, (
        f"an empty scene has nothing uncovered — coverage should be 1.0: {report.meta}"
    )
    assert report.meta.get("coverage_sparse") is False
    assert not [line for line in report.limits if _mentions_coverage(line)], (
        f"an empty scene must not emit a coverage limit line: {report.limits}"
    )

    # an empty scene with observed elements: still no coverage warning, and the
    # observed element is still reported (as UNEXPECTED)
    report2 = _diff(S.SceneGraph(), S.ObservedState(elements=[_obs_wall(1, 6.0)]))
    assert report2.meta.get("coverage_sparse") is False
    assert not [line for line in report2.limits if _mentions_coverage(line)], (
        f"no drawn elements means no coverage statement: {report2.limits}"
    )
    assert any(d.status == S.DeltaStatus.UNEXPECTED for d in report2.deltas), (
        f"the observed element should still be reported: "
        f"{[(d.scene_ref, d.observed_ref, d.status) for d in report2.deltas]}"
    )