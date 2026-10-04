"""Karmi pipeline — the one entry point everything else calls.

    approved drawing ─┐
                      ├─► diff ─► report (+ view.json for the 3D renderer)
    site photos ──────┘

Design notes
------------
* Every stage is optional-tolerant: a missing stage produces a warning and a
  degraded — but valid — result, never an exception. A hackathon demo must not
  die because one photo was blurry.
* AI is injected (`ai=`) so the whole pipeline runs with `NullProvider` and no
  network at all. That is the default.
* Outputs land in `out_dir/`: scene.json, observed.json, report.json,
  report.html, report.md, view.json, run.json
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from core import schema
from core.schema import DiffReport, ObservedState, SceneGraph

RUN_SCHEMA = "0.1.0"


@dataclass
class PipelineResult:
    out_dir: Path
    scene: SceneGraph | None = None
    observed: ObservedState | None = None
    report: DiffReport | None = None
    files: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timings_ms: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.report is not None and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "out_dir": self.out_dir.name,
            "files": self.files,
            "errors": self.errors,
            "warnings": self.warnings,
            "timings_ms": self.timings_ms,
            "summary": (self.report.summary if self.report else {}),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _display_path(p: str | Path, base: Path) -> str:
    """Path for the run manifest.

    Stored *relative to the run directory* whenever possible so that a run manifest
    never leaks the user's home directory, username or folder layout — these files
    are shown to other people (engineer, municipality) and may be shared.
    """
    try:
        return str(Path(p).resolve().relative_to(base.resolve()))
    except (ValueError, OSError):
        return Path(p).name


def run_pipeline(
    drawing: str | Path,
    photos: Sequence[str | Path] = (),
    out_dir: str | Path = "runs/latest",
    *,
    known_dimension: float | None = None,
    north_deg: float | None = None,
    ai: Any = None,
    stage_hint: str | None = None,
    sidecars: dict[str, Path] | None = None,
) -> PipelineResult:
    """Run the whole Karmi pipeline once and write every artifact to `out_dir`."""
    import time

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    res = PipelineResult(out_dir=out)

    def timed(name: str, fn, *a, **kw):
        t0 = time.perf_counter()
        try:
            return fn(*a, **kw)
        finally:
            res.timings_ms[name] = int((time.perf_counter() - t0) * 1000)

    # ---- 1. scene graph (approved) ------------------------------------- #
    try:
        from core.model import build_scene_graph

        res.scene = timed(
            "scene",
            build_scene_graph,
            drawing,
            scale_m_per_unit=None,
            north_deg=north_deg,
            ai=ai,
        )
        _write_json(out / "scene.json", res.scene)
        res.files["scene"] = "scene.json"
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the demo
        res.errors.append(f"scene: {exc}")
        res.warnings.append("Could not build the approved model from this drawing.")
        res.scene = SceneGraph(source_file=str(drawing), warnings=["extraction failed"])

    # ---- 2. observed state (as built) ---------------------------------- #
    try:
        from core.observe import to_observed_state

        res.observed = timed(
            "observe",
            to_observed_state,
            [str(p) for p in photos],
            known_dimension=known_dimension,
            ai=ai,
            stage_hint=stage_hint,
            sidecars={str(k): str(v) for k, v in (sidecars or {}).items()},
        )
        _write_json(out / "observed.json", res.observed)
        res.files["observed"] = "observed.json"
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"observe: {exc}")
        res.warnings.append("Could not read the site photos.")
        res.observed = ObservedState(warnings=["observation failed"])

    # ---- 3. diff -------------------------------------------------------- #
    try:
        from core.diff import diff_scene

        res.report = timed("diff", diff_scene, res.scene, res.observed, ai=ai)
        res.report.recount()
        _write_json(out / "report.json", res.report)
        res.files["report"] = "report.json"
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"diff: {exc}")
        res.report = DiffReport(
            limits=["The comparison step did not complete for this run."],
            meta={"traceback": traceback.format_exc()},
        ).recount()

    # ---- 4. report renders ---------------------------------------------- #
    try:
        from core.report import render_html, render_markdown

        html = timed("report_html", render_html, res.report, res.scene, res.observed)
        (out / "report.html").write_text(html, encoding="utf-8")
        res.files["report_html"] = "report.html"

        md = render_markdown(res.report, res.scene, res.observed)
        (out / "report.md").write_text(md, encoding="utf-8")
        res.files["report_md"] = "report.md"
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"report: {exc}")

    # ---- 5. view payload for the 3D renderer ---------------------------- #
    try:
        from render.adapter import build_view

        view = build_view(res.scene, res.observed, res.report)
        _write_json(out / "view.json", view)
        res.files["view"] = "view.json"
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"view: {exc}")

    # ---- 6. run manifest ------------------------------------------------- #
    _write_json(
        out / "run.json",
        {
            "schema": RUN_SCHEMA,
            "generated_at": _now(),
            # paths are stored relative to this run directory — never absolute, so a
            # shared run folder cannot reveal the user's filesystem layout
            "drawing": _display_path(drawing, out),
            "photos": [_display_path(p, out) for p in photos],
            "known_dimension_m": known_dimension,
            "ai_provider": getattr(ai, "name", "none") if ai is not None else "none",
            "result": res.to_dict(),
        },
    )
    res.files["run"] = "run.json"
    return res


def run_from_manifest(manifest_path: str | Path, out_dir: str | Path | None = None) -> PipelineResult:
    """Re-run a pipeline from a saved run manifest (used by the web UI and tests)."""
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    return run_pipeline(
        m["drawing"],
        m.get("photos", []),
        out_dir or Path(manifest_path).parent,
        known_dimension=m.get("known_dimension_m"),
    )


__all__ = ["PipelineResult", "run_pipeline", "run_from_manifest", "RUN_SCHEMA"]