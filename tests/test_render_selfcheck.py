"""Test integration of render self-checks into pytest."""

from __future__ import annotations

import shutil
import pytest

from conftest import require

render_selfcheck = require("render._selfcheck")


def test_render_selfcheck_part_a_adapter():
    """Run part A (build_view on handmade inputs and degenerate cases)."""
    render_selfcheck.FAILURES.clear()
    render_selfcheck.PASSES.clear()
    view = render_selfcheck.check_adapter()
    assert isinstance(view, dict)
    assert len(render_selfcheck.FAILURES) == 0, f"check_adapter failed: {render_selfcheck.FAILURES}"
    assert len(render_selfcheck.PASSES) >= 20


def test_render_selfcheck_part_b_viewer():
    """Run part B (viewer.html structure, IDs, and fallback markers)."""
    render_selfcheck.FAILURES.clear()
    render_selfcheck.PASSES.clear()
    render_selfcheck.check_viewer()
    assert len(render_selfcheck.FAILURES) == 0, f"check_viewer failed: {render_selfcheck.FAILURES}"
    assert len(render_selfcheck.PASSES) >= 10
