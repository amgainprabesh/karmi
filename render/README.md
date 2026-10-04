# Karmi render — approved ↔ as-built viewer

Two pieces, one contract:

| file | role |
|---|---|
| `adapter.py` | `build_view(scene, observed, report) -> dict` — turns the pipeline's three objects into **one deterministic payload** (`view.json`) |
| `viewer.html` | a single self-contained page that draws that payload: a guaranteed-offline **2D SVG plan** and a **3D path** (three.js) that enhances when three.js is reachable |
| `_selfcheck.py` | verification: adapter tests + viewer parse/id checks + optional jsdom/browser smoke tests |
| `__init__.py` | re-exports `build_view` |

The viewer is **deterministic drawing code**: it never calls an AI and never touches the network to decide anything. It draws exactly what `view.json` says. Everything the payload had to *assume* is listed in `meta.assumptions` and shown on screen.

---

## Quick start

The pipeline writes `view.json` into its output directory (e.g. `runs/latest/`):

```bash
# from the repo root, with the venv python:
.venv/Scripts/python.exe -c "from core.pipeline import run_pipeline; run_pipeline('fixtures/naksa_base.pdf', out_dir='runs/latest')"

# serve viewer.html next to view.json (browsers cannot fetch local files from file://)
cp render/viewer.html runs/latest/
cd runs/latest && python -m http.server 8123
# open http://localhost:8123/viewer.html
```

Other ways to load the payload (checked in this order by the viewer):

1. `window.KARMI_VIEW = {...}` — injected before the viewer script runs;
2. an embedded `<script id="karmi-view-data" type="application/json">…</script>` block;
3. `fetch("view.json")` relative to the page (then `../runs/latest/view.json` as a convenience fallback).

**Fully offline / single-file demo** (payload embedded, opens even from `file://` for the 2D plan):

```bash
.venv/Scripts/python.exe render/_selfcheck.py --demo out/viewer_demo.html
```

**3D offline**: drop a copy of three.js into `render/vendor/` and the viewer loads it *without any CDN*:

```bash
mkdir -p render/vendor && curl -L -o render/vendor/three.module.js \
  https://unpkg.com/three@0.160.0/build/three.module.js
```

Without that file the viewer tries the CDN (`unpkg`, then `jsdelivr`) and shows a visible banner — *“Offline 3D view unavailable — three.js was not found in render/vendor/ …”*. If the CDN is unreachable too, it stays on the 2D plan and says so. **The 2D SVG path never needs a network.**

---

## Payload schema (`VIEW_SCHEMA = "0.1.0"`)

```jsonc
{
  "schema": "0.1.0",
  "meta": {
    "generated_at": "…", "generator": "karmi render adapter",
    "scene_source": "naksa_base.pdf", "observed_sources": ["photo1.jpg"],
    "stage": "walls",                    // observed stage
    "counts": { "approved": {…}, "observed": {…}, "deltas": {…} },
    "assumptions": ["…"],                // everything that was defaulted/approximated
    "warnings": ["…"],                   // adapter-level honesty notes
    "limits": ["…"], "narration_en": ["…"], "narration_np": ["…"],
    "diff_summary": {…}, "empty": false
  },
  "approved": {
    "walls":    [{ "id", "start": [x, y], "end": [x, y], "thickness", "height",
                   "confidence", "status", "is_external", "label", "delta_ids" }],
    "openings": [{ "id", "kind", "center": [x, y], "width", "height", "sill",
                   "confidence", "status", "wall_id", "label", "delta_ids" }],
    "rooms":    [{ "id", "name", "name_np", "polygon": [[x, y], …], "area_m2",
                   "confidence", "status", "label", "delta_ids" }],
    "bbox": [minx, miny, maxx, maxy],    // null if no geometry
    "warnings": ["…"]
  },
  "observed": {                          // same shape, plus:
    "stage": "walls",
    "other":    [{ "id", "kind", "label", "status", "confidence", "note" }],   // e.g. columns, slabs
    "unplaced": [{ "id", "kind", "label", "status", "confidence", "note" }]    // no position evidence
  },
  "deltas": [ { "id", "element", "status", "severity", "confidence",
                "expected", "observed", "reason", "reason_np",
                "scene_ref", "observed_ref" } ],
  "camera": { "target": [x, y, 0], "yaw_deg": -35, "pitch_deg": 32,
              "distance": 17.0, "fov": 45, "fit": true }
}
```

Coordinates are metres in drawing space. `status` on every element is one of
**`matched | differs | missing | unexpected | unverifiable`**, derived from the DiffReport by
following `scene_ref` / `observed_ref`. **An element no delta refers to is `unverifiable` — never silently
`matched`.** When several deltas touch one element the most informative status wins
(`differs > missing > unexpected > unverifiable > matched`).

### Honesty rules in the adapter

* **Defaults are assumptions.** If the drawing has no wall height, both sides use **2.7 m**
  (external and internal) and say so in `meta.assumptions`. Missing thickness → **0.23 m**
  external / **0.115 m** internal. Doors: sill 0, height default 2.1 m. Windows: sill 0.9 m,
  height 1.2 m. Each default is counted and reported.
* **No invention of position.** An observed element with no coordinates is anchored to its
  matched approved element (recorded as an approximation); if there is nothing to anchor to it
  goes to `observed.unplaced` with a warning — it is not drawn at a made-up spot.
* **Nothing is dropped silently.** Observed elements of kinds that cannot be drawn (columns,
  slabs…) are listed in `observed.other`; openings with no width are flagged and the viewer
  shows them as markers, not holes; delta references that point at unknown ids are warned about.
* **Empty/None inputs never raise.** `build_view(None, None, None)` returns a valid payload
  whose warnings say there is nothing to show.

---

## Viewer behaviour

* **Views**: `Approved` / `As-built` / `Diff` (diff = both, differences in red, everything else dimmed).
* **Renderers**: `2D plan` (SVG — always available, pan/drag, wheel zoom, double-click reset) and
  `3D` (three.js — drag orbit, wheel zoom, double-click reset, click an element to select it).
* **Money shot**: `▶ 2D नक्सा → 3D घर` switches to 3D and extrudes the floor plan upward —
  the camera swings from top-down plan view to a perspective orbit while walls grow from the floor.
* **Click any element** (in 2D or 3D) for a side panel: status badge, confidence bar, geometry,
  and every delta's expected vs observed, severity, reason (EN + Nepali).
* **Colours**: green = matched, red = differs / missing (dashed) / unexpected (dotted),
  grey = unverifiable. Elements with confidence < 0.5 are hatched and labelled **approx**.
  The legend (bottom-left) explains all of it.
* **Missing data is said on screen**: no payload → an empty state explaining how to produce
  `view.json`; empty run → "Empty run"; no observations → "No as-built observations in this run".

---

## Verification

```bash
.venv/Scripts/python.exe render/_selfcheck.py            # adapter + viewer static checks
.venv/Scripts/python.exe render/_selfcheck.py --demo     # + write a self-contained demo page
```

Optional DOM smoke test: install `jsdom` somewhere and point the check at it
(`KARMI_JSDOM_DIR=/path/to/dir npm install jsdom`), or set `KARMI_JSDOM_DIR`.

What it checks: payload counts vs inputs, status derivation, empty/dict/garbage inputs,
`node --check` on the extracted inline script, every `$('id')` in the JS exists in the HTML,
required ids + offline-fallback markers, and (with jsdom) that the SVG renders, selection opens
the panel, mode toggles re-render, and 3D degrades honestly when three.js is unreachable.