"""``core.diff`` (and ``core.report`` rendering) on hand-made pairs.

These tests never touch the extractor: the scene/observed pairs are built by
hand via the helpers in ``conftest.py``, so they exercise the comparison
contract itself — matched / differs / missing / unexpected, monotone severity,
and the low-confidence severity cap.
"""

from __future__ import annotations

import pytest

from core import schema as S
from conftest import (
    call_adaptive,
    make_observed_for,
    make_wall,
    make_wall_element,
    require,
    require_attr,
)

diff_mod = require(
    "core.diff",
    reason="core.diff is not importable yet (being written in parallel) — skipping the diff tests",
)

_RANK = {S.Severity.INFO: 0, S.Severity.LOW: 1, S.Severity.MEDIUM: 2, S.Severity.HIGH: 3}


def _diff(scene: S.SceneGraph, observed: S.ObservedState) -> S.DiffReport:
    diff_scene = require_attr(diff_mod, "diff_scene")
    report = call_adaptive(diff_scene, scene, observed, ai=None)
    assert isinstance(report, S.DiffReport), f"diff_scene returned {type(report)!r}, expected DiffReport"
    return report


def _one_wall_scene(length: float = 6.0, wall_id: str = "w1") -> S.SceneGraph:
    return S.SceneGraph(
        source_file="handmade://one-wall",
        walls=[make_wall(wall_id, (0.0, 0.0), (length, 0.0))],
    )


def _one_wall_observed(
    length: float, confidence: float = 0.8, matches: str | None = "w1", element_id: str = "o1"
) -> S.ObservedState:
    return make_observed_for(
        [make_wall_element(element_id, length=length, matches=matches, confidence=confidence)]
    )


def _linked(report: S.DiffReport, *ids: str):
    """Deltas that reference any of ``ids`` via scene_ref / observed_ref."""
    return [d for d in report.deltas if any(i in (d.scene_ref, d.observed_ref) for i in ids)]


def _statuses(report: S.DiffReport):
    return {d.status for d in report.deltas}


def _severity_of(report: S.DiffReport) -> S.Severity:
    return max((d.severity for d in report.deltas), key=_RANK.__getitem__, default=S.Severity.INFO)


def test_identical_pair_reports_matched():
    report = _diff(_one_wall_scene(6.0), _one_wall_observed(6.0))
    statuses = _statuses(report)
    assert S.DeltaStatus.MATCHED in statuses, (
        f"an identical hand-made pair should produce a MATCHED delta, "
        f"got {[(d.element, d.status) for d in report.deltas]}"
    )
    assert statuses <= {S.DeltaStatus.MATCHED, S.DeltaStatus.UNVERIFIABLE}, (
        f"nothing else should be flagged for an identical pair: {[(d.element, d.status) for d in report.deltas]}"
    )
    linked = _linked(report, "w1", "o1")
    if linked:
        assert any(d.status == S.DeltaStatus.MATCHED for d in linked)


def test_changed_size_reports_differs():
    report = _diff(_one_wall_scene(6.0), _one_wall_observed(5.0))
    assert S.DeltaStatus.DIFFERS in _statuses(report), (
        f"a 1.0 m deviation on a 6.0 m wall should produce DIFFERS, "
        f"got {[(d.element, d.status) for d in report.deltas]}"
    )
    linked = _linked(report, "w1", "o1")
    if linked:
        assert any(d.status == S.DeltaStatus.DIFFERS for d in linked)


def test_unobserved_scene_element_reports_missing():
    scene = S.SceneGraph(
        source_file="handmade://two-walls",
        walls=[
            make_wall("w1", (0.0, 0.0), (6.0, 0.0)),
            make_wall("w2", (0.0, 2.0), (6.0, 2.0)),
        ],
    )
    observed = _one_wall_observed(6.0, matches="w1")
    report = _diff(scene, observed)
    assert S.DeltaStatus.MISSING in _statuses(report), (
        f"w2 was never observed but no MISSING delta appeared: "
        f"{[(d.element, d.status) for d in report.deltas]}"
    )
    linked = _linked(report, "w2")
    if linked:
        assert any(d.status == S.DeltaStatus.MISSING for d in linked)


def test_unmatched_observed_element_reports_unexpected():
    observed = make_observed_for(
        [
            make_wall_element("o1", length=6.0, matches="w1"),
            make_wall_element("o_extra_dangling", length=3.0, matches="ghost_wall"),
            make_wall_element("o_extra_unlocated", length=2.5, matches=None),
        ]
    )
    report = _diff(_one_wall_scene(6.0), observed)
    assert S.DeltaStatus.UNEXPECTED in _statuses(report), (
        f"elements that are not in the drawing should be UNEXPECTED: "
        f"{[(d.element, d.status) for d in report.deltas]}"
    )
    dangling = _linked(report, "o_extra_dangling")
    if dangling:
        assert any(d.status == S.DeltaStatus.UNEXPECTED for d in dangling)
    unlocated = _linked(report, "o_extra_unlocated")
    if unlocated:
        assert all(
            d.status in (S.DeltaStatus.UNEXPECTED, S.DeltaStatus.UNVERIFIABLE) for d in unlocated
        )


def test_severity_is_monotonic_in_deviation():
    none = _severity_of(_diff(_one_wall_scene(6.0), _one_wall_observed(6.0)))
    mid = _severity_of(_diff(_one_wall_scene(6.0), _one_wall_observed(6.8)))
    big = _severity_of(_diff(_one_wall_scene(6.0), _one_wall_observed(3.0)))

    assert _RANK[big] > _RANK[none], (
        f"a 50% deviation ({big}) must rank above a perfect match ({none})"
    )
    assert _RANK[mid] <= _RANK[big], (
        f"severity must not fall as the deviation grows: mid={mid} big={big}"
    )
    assert _RANK[none] <= _RANK[mid]


def test_low_confidence_caps_severity():
    confident = _severity_of(_diff(_one_wall_scene(6.0), _one_wall_observed(3.0, confidence=0.95)))
    shaky = _severity_of(_diff(_one_wall_scene(6.0), _one_wall_observed(3.0, confidence=0.05)))

    assert _RANK[confident] >= _RANK[S.Severity.LOW], (
        f"a 50% deviation at 95% confidence should register, got {confident}"
    )
    assert _RANK[shaky] <= _RANK[S.Severity.MEDIUM], (
        f"low-confidence evidence should be capped at MEDIUM, got {shaky}"
    )
    assert _RANK[shaky] <= _RANK[confident], (
        f"low confidence ({shaky}) must not outrank high confidence ({confident})"
    )


def test_report_summary_is_coherent_after_diff():
    report = _diff(_one_wall_scene(6.0), _one_wall_observed(5.0))
    report.recount()
    assert report.summary.get("total") == len(report.deltas)
    assert sum(report.summary.get(s.value, 0) for s in S.Severity) == len(report.deltas)


# --------------------------------------------------------------------------- #
# rendering (core.report) — skipped separately if that module is missing
# --------------------------------------------------------------------------- #
def _report_module():
    return require(
        "core.report",
        reason="core.report is not importable yet (renderer being written in parallel)",
    )


def test_render_html_contains_the_verify_section(sample_report, sample_scene, sample_observed):
    report_mod = _report_module()
    render_html = require_attr(report_mod, "render_html")
    html = call_adaptive(render_html, sample_report, sample_scene, sample_observed)

    assert isinstance(html, str) and html.strip(), "render_html returned an empty document"
    assert "<" in html, "render_html does not look like HTML"
    assert "verify" in html.lower() or "जाँच" in html, (
        "the HTML report must contain the items-to-verify section"
    )
    item = sample_report.verify_list[0]
    assert (item.item in html) or (item.item_np and item.item_np in html), (
        "the verify item text is missing from the HTML report"
    )


def test_render_markdown_contains_the_verify_section(sample_report, sample_scene, sample_observed):
    report_mod = _report_module()
    render_markdown = require_attr(report_mod, "render_markdown")
    md = call_adaptive(render_markdown, sample_report, sample_scene, sample_observed)

    assert isinstance(md, str) and md.strip(), "render_markdown returned an empty document"
    assert "verify" in md.lower() or "जाँच" in md, (
        "the markdown report must contain the items-to-verify section"
    )
    item = sample_report.verify_list[0]
    assert (item.item in md) or (item.item_np and item.item_np in md), (
        "the verify item text is missing from the markdown report"
    )