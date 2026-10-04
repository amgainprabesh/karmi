"""Karmi render package — the viewer payload bridge.

`render.adapter.build_view(scene, observed, report)` turns the three pipeline
objects into one deterministic payload (view.json) that `render/viewer.html`
draws verbatim. The viewer never infers anything; every decision and every
assumption lives in the payload.
"""

from render.adapter import VIEW_SCHEMA, build_view

__all__ = ["VIEW_SCHEMA", "build_view"]