#!/usr/bin/env python3
"""Karmi render self-check — verification for `render/adapter.py` + `render/viewer.html`.

Checks (all must pass for exit code 0):
  A. adapter   — build_view on a hand-made scene+observed+report: counts match
                 the inputs, statuses derive from the diff refs, elements with
                 no delta stay `unverifiable`. Empty/None inputs return a valid
                 payload with warnings and never raise. Partial and dict inputs.
  B. viewer    — extract the inline <script> from viewer.html and:
                   * `node --check` it (the JS must parse),
                   * every `$('id')` the JS references exists as `id="…"` in
                     the HTML,
                   * the required element ids are present,
                   * the guaranteed-offline SVG fallback + three.js loader
                     markers are present.
  C. demo      — `--demo OUT` writes a self-contained copy of viewer.html
                 with the fixture payload embedded, for offline use.

Optional (auto-skipped if missing):
  D. jsdom     — if `jsdom` is installed in $KARMI_JSDOM_DIR (or alongside the
                 script), load the demo HTML in a DOM and assert the 2D SVG
                 plan actually renders, selection opens the panel, and the
                 APPROVED/AS-BUILT/DIFF toggles re-render.

Run from the repo root (or anywhere):  .venv/Scripts/python.exe render/_selfcheck.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDER = ROOT / "render"
VIEWER = RENDER / "viewer.html"

REQUIRED_IDS = [
    "karmi-view-data", "banner", "meta-line", "svg-plan", "stage2d", "stage3d",
    "canvas3d", "labels3d", "empty-state", "panel", "panel-head", "panel-body",
    "panel-close", "legend", "btn-play", "btn-2d", "btn-3d",
    "view-approved", "view-observed", "view-diff",
]

FAILURES: list[str] = []
PASSES: list[str] = []


def ok(msg: str) -> None:
    PASSES.append(msg)
    print("  PASS  " + msg)


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print("  FAIL  " + msg)


def scratch_dir() -> Path:
    d = Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "karmi_selfcheck"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# A. adapter
# --------------------------------------------------------------------------- #
def make_fixture():
    """A small hand-made Nepali house: 5 walls, 3 openings, 2 rooms, 6 observed
    elements, 6 deltas covering matched / differs / missing / unexpected /
    unverifiable and one element with no delta at all."""
    sys.path.insert(0, str(ROOT))
    from core.schema import (
        Delta, DeltaStatus, DiffReport, ElementKind, ObservedElement, ObservedState,
        Opening, OpeningKind, Provenance, Room, SceneGraph, Severity, Stage, Wall,
    )

    conf = lambda c, src="ai_vision": Provenance(source=src, confidence=c)  # noqa: E731

    scene = SceneGraph(
        source_file="naksa_base.pdf",
        walls=[
            Wall(id="W1", start=(0, 0), end=(8, 0), thickness=0.23, is_external=True, provenance=conf(0.9, "vector_geometry")),
            Wall(id="W2", start=(8, 0), end=(8, 6), thickness=0.23, is_external=True, provenance=conf(0.9, "vector_geometry")),
            Wall(id="W3", start=(8, 6), end=(0, 6), thickness=0.23, is_external=True, provenance=conf(0.9, "vector_geometry")),
            Wall(id="W4", start=(0, 6), end=(0, 0), thickness=0.23, is_external=True, provenance=conf(0.9, "vector_geometry")),
            Wall(id="W5", start=(4, 0), end=(4, 6), thickness=0.115, is_external=False, provenance=conf(0.7)),
        ],
        openings=[
            Opening(id="O1", kind=OpeningKind.DOOR, wall_id="W1", center=(2, 0), width=0.9, height=2.1, sill_height=0.0, provenance=conf(0.8)),
            Opening(id="O2", kind=OpeningKind.WINDOW, wall_id="W2", center=(8, 3), width=1.2, height=None, sill_height=None, provenance=conf(0.4)),
            Opening(id="O3", kind=OpeningKind.WINDOW, wall_id="W3", center=(6, 6), width=1.0, height=1.2, sill_height=0.9, provenance=conf(0.6)),
        ],
        rooms=[
            Room(id="R1", name="living", name_np="बैठक", polygon=[(0, 0), (4, 0), (4, 6), (0, 6)], provenance=conf(0.8)),
            Room(id="R2", name="kitchen", name_np="भान्सा", polygon=[(4, 0), (8, 0), (8, 6), (4, 6)], provenance=conf(0.8)),
        ],
        bbox=(0, 0, 8, 6),
        warnings=["dimension text on sheet was too small to read"],
    )
    observed = ObservedState(
        stage=Stage.WALLS,
        elements=[
            ObservedElement(id="E1", kind=ElementKind.WALL, matches_scene_id="W1",
                            approx_size={"length": 8.0, "height": 2.7}, location_hint="front wall", provenance=conf(0.75)),
            ObservedElement(id="E2", kind=ElementKind.WALL, matches_scene_id="W2",
                            approx_size={"length": 6.4}, location_hint="east wall", provenance=conf(0.6)),
            ObservedElement(id="E3", kind=ElementKind.WALL,
                            approx_size={"x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 6.0, "thickness": 0.24},
                            location_hint="west wall", provenance=conf(0.55)),
            ObservedElement(id="E4", kind=ElementKind.OPENING, matches_scene_id="O1",
                            approx_size={"width": 1.4, "height": 2.1, "sill": 0.0}, location_hint="front door", provenance=conf(0.6)),
            ObservedElement(id="E5", kind=ElementKind.COLUMN, approx_size={"height": 2.7},
                            location_hint="front-left corner", provenance=conf(0.4)),
            ObservedElement(id="E6", kind=ElementKind.WALL, approx_size={"length": 3.0},
                            location_hint="somewhere near the back", provenance=conf(0.3)),
        ],
    )
    report = DiffReport(
        deltas=[
            Delta(id="D1", element="front wall (W1)", scene_ref="W1", observed_ref="E1",
                  status=DeltaStatus.MATCHED, expected="8.0 m", observed="8.0 m",
                  severity=Severity.INFO, confidence=0.75, reason="front wall matches"),
            Delta(id="D2", element="east wall", scene_ref="W2", observed_ref="E2",
                  status=DeltaStatus.DIFFERS, expected="6.0 m", observed="6.4 m",
                  severity=Severity.MEDIUM, confidence=0.6, reason="east wall looks ~0.4 m longer"),
            Delta(id="D3", element="north wall", scene_ref="W3", observed_ref=None,
                  status=DeltaStatus.MISSING, expected="wall on north side", observed="not visible",
                  severity=Severity.HIGH, confidence=0.5, reason="north wall not seen in any photo"),
            Delta(id="D4", element="front door", scene_ref="O1", observed_ref="E4",
                  status=DeltaStatus.DIFFERS, expected="0.9 m", observed="1.4 m",
                  severity=Severity.MEDIUM, confidence=0.6, reason="door opening is wider than drawn"),
            Delta(id="D5", element="new column", scene_ref=None, observed_ref="E5",
                  status=DeltaStatus.UNEXPECTED, expected="—", observed="column", severity=Severity.LOW,
                  confidence=0.4, reason="a column that is not in the drawing"),
            Delta(id="D6", element="living room", scene_ref="R1", observed_ref=None,
                  status=DeltaStatus.UNVERIFIABLE, severity=Severity.INFO, confidence=0.2,
                  reason="no interior photo of the living room"),
        ],
        limits=["No interior photos were available."],
        narration_en=["The east wall is longer than drawn."],
    ).recount()
    return scene, observed, report


def check_adapter() -> dict:
    print("\n[A] adapter — build_view(scene, observed, report)")
    sys.path.insert(0, str(ROOT))
    from render.adapter import build_view

    scene, observed, report = make_fixture()
    view = build_view(scene, observed, report)

    # 1. shape
    if set(view.keys()) == {"schema", "meta", "approved", "observed", "deltas", "camera"}:
        ok("top-level keys are exactly {schema, meta, approved, observed, deltas, camera}")
    else:
        fail(f"top-level keys wrong: {sorted(view.keys())}")
    if view["schema"] == "0.1.0":
        ok('schema == "0.1.0"')
    else:
        fail(f"schema is {view['schema']!r}")

    for side in ("approved", "observed"):
        need = {"walls", "openings", "rooms", "bbox", "warnings"}
        if side == "observed":
            need.add("stage")
        missing = need - set(view[side].keys())
        if missing:
            fail(f"{side} missing keys: {missing}")
        else:
            ok(f"{side} has walls/openings/rooms/bbox/warnings" + (" + stage" if side == "observed" else ""))

    # 2. counts match the inputs
    ca, co = view["meta"]["counts"]["approved"], view["meta"]["counts"]["observed"]
    expect_a = {"walls": len(scene.walls), "openings": len(scene.openings), "rooms": len(scene.rooms)}
    expect_o = {"elements": len(observed.elements), "walls": 3, "openings": 1, "rooms": 0, "other": 1, "unplaced": 1}
    print(f"       approved counts: {ca}   (inputs: {expect_a})")
    print(f"       observed counts: {co}   (expected: {expect_o})")
    if {k: ca[k] for k in expect_a} == expect_a:
        ok("approved counts match the scene graph input")
    else:
        fail(f"approved counts mismatch: {ca} vs {expect_a}")
    if co == expect_o:
        ok("observed counts match the observed-state input (3 placed walls, 1 opening, 1 other, 1 unplaced)")
    else:
        fail(f"observed counts mismatch: {co} vs {expect_o}")
    if view["meta"]["counts"]["deltas"]["total"] == len(report.deltas):
        ok(f"delta count matches the report ({len(report.deltas)})")
    else:
        fail("delta count mismatch")

    # 3. status derivation via scene_ref / observed_ref
    ws = {w["id"]: w["status"] for w in view["approved"]["walls"]}
    print(f"       approved wall statuses: {ws}")
    if ws == {"W1": "matched", "W2": "differs", "W3": "missing", "W4": "unverifiable", "W5": "unverifiable"}:
        ok("approved statuses follow scene_ref; W4/W5 (no delta) stay unverifiable — never silently matched")
    else:
        fail(f"approved statuses wrong: {ws}")
    os_ = {w["id"]: w["status"] for w in view["observed"]["walls"]}
    print(f"       observed wall statuses: {os_}")
    if os_ == {"E1": "matched", "E2": "differs", "E3": "unverifiable"}:
        ok("observed statuses follow observed_ref")
    else:
        fail(f"observed statuses wrong: {os_}")
    op = {o["id"]: o["status"] for o in view["approved"]["openings"]}
    if op == {"O1": "differs", "O2": "unverifiable", "O3": "unverifiable"}:
        ok("opening statuses follow scene_ref")
    else:
        fail(f"opening statuses wrong: {op}")
    rooms = {r["id"]: (r["status"], r["delta_ids"]) for r in view["approved"]["rooms"]}
    print(f"       rooms (status, delta_ids): {rooms}")
    if rooms == {"R1": ("unverifiable", ["D6"]), "R2": ("unverifiable", [])}:
        ok("rooms carry a derived status and their delta links (R1 <- D6, R2 no delta)")
    else:
        fail(f"room status/link derivation wrong: {rooms}")

    # 4. required element keys
    w = view["approved"]["walls"][0]
    if {"id", "start", "end", "thickness", "height", "confidence", "status"} <= set(w.keys()):
        ok("wall elements carry id/start/end/thickness/height/confidence/status")
    else:
        fail(f"wall element keys: {sorted(w.keys())}")
    o = view["approved"]["openings"][0]
    if {"id", "kind", "center", "width", "height", "sill", "confidence", "status"} <= set(o.keys()):
        ok("opening elements carry id/kind/center/width/height/sill/confidence/status")
    else:
        fail(f"opening element keys: {sorted(o.keys())}")
    r = view["approved"]["rooms"][0]
    if {"id", "name", "name_np", "polygon", "area_m2", "confidence"} <= set(r.keys()):
        ok("room elements carry id/name/name_np/polygon/area_m2/confidence")
    else:
        fail(f"room element keys: {sorted(r.keys())}")

    # 5. honesty: defaults recorded as assumptions; sizes defaulted
    if view["meta"]["assumptions"] and any("2.7" in a for a in view["meta"]["assumptions"]):
        ok("wall height default (2.7 m) recorded in meta.assumptions")
    else:
        fail("wall-height assumption missing")
    o2 = [x for x in view["approved"]["openings"] if x["id"] == "O2"][0]
    if o2["height"] == 1.2 and o2["sill"] == 0.9:
        ok("window with no height/sill got 1.2 m / 0.9 m defaults (recorded in assumptions)")
    else:
        fail(f"O2 defaults wrong: height={o2['height']} sill={o2['sill']}")
    e2 = [x for x in view["observed"]["walls"] if x["id"] == "E2"][0]
    if abs((e2["end"][1] - e2["start"][1]) - 6.4) < 1e-6:
        ok("observed wall E2 anchored to W2 and rescaled to its observed 6.4 m length")
    else:
        fail(f"E2 geometry: {e2['start']} -> {e2['end']}")

    json.dumps(view, ensure_ascii=False)
    ok("payload is JSON-serialisable")

    # 6. empty / None inputs — never raise
    v2 = build_view(None, None, None)
    if v2["schema"] == "0.1.0" and v2["meta"]["empty"] is True and v2["meta"]["warnings"]:
        ok(f"build_view(None, None, None) -> valid payload, warnings={v2['meta']['warnings']}")
    else:
        fail("empty-input payload is not valid")
    v3 = build_view(scene, None, None)
    if v3["meta"]["counts"]["approved"]["walls"] == 5 and all(
        x["status"] == "unverifiable" for x in v3["approved"]["walls"]
    ):
        ok("build_view(scene, None, None) -> approved drawn, everything unverifiable, no raise")
    else:
        fail("partial (scene-only) payload wrong")
    v4 = build_view(json.loads(scene.model_dump_json()), json.loads(observed.model_dump_json()), None)
    if v4["meta"]["counts"]["observed"]["walls"] == 3:
        ok("plain-dict inputs accepted")
    else:
        fail("dict inputs not handled")
    v5 = build_view(object(), 42, "nope")
    if v5["schema"] == "0.1.0" and v5["meta"]["warnings"]:
        ok("garbage inputs degrade to a warning payload, no exception")
    else:
        fail("garbage inputs raised or produced an invalid payload")

    print(f"       camera: {view['camera']}")
    print(f"       assumptions ({len(view['meta']['assumptions'])}):")
    for a in view["meta"]["assumptions"]:
        print("         - " + a)
    print(f"       warnings ({len(view['meta']['warnings'])}):")
    for x in view["meta"]["warnings"]:
        print("         - " + x)
    return view


# --------------------------------------------------------------------------- #
# B. viewer.html static checks
# --------------------------------------------------------------------------- #
def extract_script(html: str) -> str:
    blocks = re.findall(r"<script([^>]*)>(.*?)</script>", html, re.S)
    js = [body for attrs, body in blocks if "application/json" not in attrs]
    if len(js) != 1:
        raise SystemExit(f"expected exactly 1 inline JS block, found {len(js)}")
    return js[0]


def check_viewer() -> None:
    print("\n[B] viewer.html — parse + id integrity + fallback markers")
    if not VIEWER.exists():
        fail("render/viewer.html does not exist")
        return
    html = VIEWER.read_text(encoding="utf-8")
    script = extract_script(html)

    # 1. node --check
    node = shutil.which("node")
    if not node:
        fail("node not found on PATH — cannot verify the JS parses")
    else:
        js_path = scratch_dir() / "viewer_script.js"
        js_path.write_text(script, encoding="utf-8")
        proc = subprocess.run([node, "--check", str(js_path)], capture_output=True, text=True)
        if proc.returncode == 0:
            ok(f"`node --check` passes on the extracted inline script ({len(script)} chars)")
        else:
            fail("node --check failed:\n" + (proc.stderr or proc.stdout))

    # 2. every id the JS references exists in the HTML
    refs = set(re.findall(r"\$\('([^']+)'\)", script)) | set(re.findall(r'\$\("([^"]+)"\)', script))
    html_ids = set(re.findall(r'id="([^"]+)"', html.split("</script>")[0]))
    missing = sorted(refs - html_ids)
    print(f"       JS references {len(refs)} static ids: {', '.join(sorted(refs))}")
    if missing:
        fail(f"ids referenced by JS but absent from HTML: {missing}")
    else:
        ok("every id referenced by the JS exists in the HTML")

    # 3. required ids
    req_missing = [i for i in REQUIRED_IDS if i not in html_ids]
    if req_missing:
        fail(f"required ids missing: {req_missing}")
    else:
        ok(f"all {len(REQUIRED_IDS)} required element ids present")

    # 4. offline 2D SVG fallback + three.js loader markers
    checks = [
        ("createElementNS", "SVG plan is built with createElementNS (guaranteed-offline 2D path)"),
        ("khatch", "hatch pattern for low-confidence 'approx' elements present"),
        ("vendor/three.module.js", "checks for the local three.js vendor file first"),
        ("unpkg.com/three", "CDN fallback for three.js present"),
        ("Offline 3D view unavailable", "banner text warns when offline 3D is unavailable"),
        ("window.KARMI_VIEW", "reads an injected window.KARMI_VIEW payload"),
        ("view.json", "fetches view.json relative to the page"),
        ("extrude", "2D->3D transition (extrude) documented in the file"),
    ]
    for marker, label in checks:
        if marker in html:
            ok(label)
        else:
            fail(f"marker missing from viewer.html: {marker!r} ({label})")

    # 5. no external resource references in the static markup (offline 2D path)
    head = html.split("<script")[0]
    ext = re.findall(r'(?:src|href)="(https?://[^"]+)"', head)
    if ext:
        fail(f"static markup references external resources: {ext}")
    else:
        ok("no external <link>/<script src> in the static markup — 2D path needs zero network")


def embed_view(view: dict, out_path: Path) -> Path:
    html = VIEWER.read_text(encoding="utf-8")
    payload = json.dumps(view, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    marker = '<script id="karmi-view-data" type="application/json">{}</script>'
    if html.count(marker) != 1:
        raise SystemExit("embedded-data script marker not found exactly once in viewer.html")
    out = html.replace(marker, '<script id="karmi-view-data" type="application/json">' + payload + "</script>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out, encoding="utf-8")
    return out_path


# --------------------------------------------------------------------------- #
# D. optional jsdom DOM test
# --------------------------------------------------------------------------- #
JSDOM_TEST = r"""
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const html = fs.readFileSync(process.argv[2], 'utf8');
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost/viewer.html' });
const w = dom.window, d = w.document;
function later(ms){ return new Promise(r => setTimeout(r, ms)); }
(async () => {
  await later(400);
  const out = { steps: [] };
  const svg = d.getElementById('svg-plan');
  out.svgChildren = svg.childNodes.length;
  out.walls = svg.querySelectorAll('[data-etype="wall"]').length;
  out.openings = svg.querySelectorAll('[data-etype="opening"]').length;
  out.rooms = svg.querySelectorAll('[data-etype="room"]').length;
  out.labels = svg.querySelectorAll('text').length;
  out.meta = d.getElementById('meta-line').textContent;
  out.chips = d.querySelectorAll('#legend .chip').length;
  out.state = w.KARMI_VIEWER || {};
  // click a wall polygon -> panel opens with expected/observed
  const wall = svg.querySelector('[data-etype="wall"]');
  const poly = wall.querySelector('polygon');
  poly.dispatchEvent(new w.MouseEvent('pointerdown', { bubbles: true, clientX: 100, clientY: 100 }));
  poly.dispatchEvent(new w.MouseEvent('pointerup', { bubbles: true, clientX: 100, clientY: 100 }));
  await later(50);
  const panel = d.getElementById('panel');
  out.panelOpen = panel.classList.contains('on');
  out.panelText = d.getElementById('panel-body').textContent.slice(0, 300);
  out.selected = (w.KARMI_VIEWER || {}).selected;
  // switch to diff view
  d.getElementById('view-diff').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await later(50);
  out.diffMode = (w.KARMI_VIEWER || {}).mode;
  out.diffWalls = d.getElementById('svg-plan').querySelectorAll('[data-etype="wall"]').length;
  // switch to as-built
  d.getElementById('view-observed').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await later(50);
  out.observedMode = (w.KARMI_VIEWER || {}).mode;
  out.observedWalls = d.getElementById('svg-plan').querySelectorAll('[data-etype="wall"]').length;
  // attempt 3D -> must degrade gracefully (no dynamic import in jsdom)
  d.getElementById('btn-3d').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await later(600);
  out.dimAfter3D = (w.KARMI_VIEWER || {}).dim;
  out.threeStatus = (w.KARMI_VIEWER || {}).threeStatus;
  out.banner = d.getElementById('banner').textContent;
  console.log('JSDOM-RESULT ' + JSON.stringify(out));
  process.exit(0);
})().catch(e => { console.error('JSDOM-ERROR ' + (e && e.stack || e)); process.exit(2); });
"""


def check_jsdom(demo: Path) -> None:
    print("\n[D] jsdom DOM smoke test (optional)")
    node = shutil.which("node")
    if not node:
        print("  SKIP  node not found")
        return
    candidates = [
        scratch_dir() / "karmi_jsdom",
        scratch_dir().parent / "karmi_jsdom",
        Path(os.environ["KARMI_JSDOM_DIR"]) if os.environ.get("KARMI_JSDOM_DIR") else None,
    ]
    base = None
    for c in candidates:
        if c and (c / "node_modules" / "jsdom").exists():
            base = c
            break
    if base is None:
        print("  SKIP  jsdom not installed (npm install jsdom in the scratch dir to enable)")
        return
    test_js = base / "jsdom_test.js"
    test_js.write_text(JSDOM_TEST, encoding="utf-8")
    proc = subprocess.run([node, str(test_js), str(demo)], capture_output=True, text=True, cwd=str(base))
    line = next((l for l in proc.stdout.splitlines() if l.startswith("JSDOM-RESULT ")), None)
    if not line:
        fail("jsdom test produced no result:\n" + (proc.stdout + proc.stderr)[-1500:])
        return
    res = json.loads(line[len("JSDOM-RESULT "):])
    print("       " + json.dumps({k: v for k, v in res.items() if k != "panelText"}, indent=None))
    if res["walls"] >= 5 and res["openings"] >= 3 and res["rooms"] >= 2:
        ok(f"2D SVG rendered from embedded payload: {res['walls']} walls, {res['openings']} openings, {res['rooms']} rooms")
    else:
        fail(f"2D SVG render incomplete: {res}")
    if res["panelOpen"] and "expected" in res["panelText"] and "observed" in res["panelText"]:
        ok("clicking a wall opens the side panel with expected/observed delta detail")
    else:
        fail(f"panel did not open with delta detail: {res.get('panelOpen')}")
    if res["diffMode"] == "diff" and res["observedMode"] == "observed":
        ok("APPROVED / AS-BUILT / DIFF toggles re-render the plan")
    else:
        fail(f"mode toggles failed: {res.get('diffMode')} / {res.get('observedMode')}")
    if res["dimAfter3D"] == "2d" and res["threeStatus"] == "failed" and "unavailable" in res["banner"]:
        ok("3D degrades honestly when three.js is unreachable (stays 2D + banner)")
    else:
        fail(f"3D degradation unexpected: dim={res.get('dimAfter3D')} three={res.get('threeStatus')}")


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Karmi render self-check")
    ap.add_argument("--demo", nargs="?", const=str(scratch_dir() / "viewer_demo.html"),
                    help="write a self-contained viewer.html with the fixture payload embedded")
    ap.add_argument("--skip-jsdom", action="store_true")
    args = ap.parse_args()

    print(f"Karmi render self-check — repo {ROOT}")
    view = check_adapter()
    check_viewer()

    if args.demo:
        p = embed_view(view, Path(args.demo))
        print(f"\n[C] demo written: {p}  ({p.stat().st_size} bytes)")
        if not args.skip_jsdom:
            check_jsdom(p)

    print("\n" + "=" * 66)
    print(f"RESULT: {len(PASSES)} passed, {len(FAILURES)} failed")
    for f in FAILURES:
        print("  FAILED: " + f)
    print("=" * 66)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())