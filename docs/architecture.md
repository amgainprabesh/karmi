# Architecture — Karmi

## One picture

```
        APPROVED DRAWING (naksa PDF / scan)              SITE PHOTOS (over time)
                    │                                            │
        ┌───────────▼───────────┐                    ┌───────────▼───────────┐
        │  Extraction A (AI)     │                    │  Extraction B (AI)     │
        │  drawing → geometry    │                    │  photos → observed     │
        └───────────┬───────────┘                    └───────────┬───────────┘
                    │ structured JSON                             │ structured JSON
                    ▼                                             ▼
            ┌──────────────────┐                        ┌──────────────────┐
            │  scene graph     │  walls, openings,      │  observed state  │  stage, elements,
            │  (approved)      │  rooms, dims, N-arrow  │  (as built)      │  approx dims + confidence
            └────────┬─────────┘                        └────────┬─────────┘
                     └──────────────┬──────────────────────────────┘
                                    ▼
                        ┌───────────────────────┐
                        │  Diff engine          │  element-wise expected vs observed,
                        │  (AI reasoning + code)│  severity, confidence, verify-list
                        └───────────┬───────────┘
                                    ▼
                 ┌──────────────────┴───────────────────┐
                 ▼                                      ▼
      Nepali report (items to verify)        2D→3D transition render:
                                             approved in green, as-built in red
```

## Components

| # | Component | Role | AI? |
|---|---|---|---|
| 1 | `core/ingest` | accept PDF/scan + photos, normalise, store with metadata | no |
| 2 | `core/model` | drawing → scene graph (walls with thickness, openings classified door/window, room polygons, dimensions, orientation) | **yes** |
| 3 | `core/observe` | photos → observed state (construction stage, detected elements, approximate dimensions with confidence) | **yes** |
| 4 | `core/diff` | element-wise comparison, severity scoring, Nepali narration | **yes** (reasoning) + no (geometry) |
| 5 | `core/report` | Nepali report + verify-list, machine-readable export | no |
| 6 | `render/transition` | 2D→3D animated transition; dual approved-vs-built view | no |
| 7 | `dataset/` | annotation tooling + released dataset | no |

## Ingestion strategy, in priority order

1. **Vector PDF** — the Naksa Pass set is usually CAD-exported, so wall lines are real paths.
   Parse with `pymupdf`, snap near-axis segments, merge collinear runs, close room polygons.
   Cheap, accurate, no model needed for the topology.
2. **Raster fallback** — segmentation model (fine-tuned on our Nepali naksa dataset) → masks →
   contour vectorisation → polygons. This is the part the dataset exists to make good.
3. **Scan/photo of a drawing** — same as 2, with a scale calibration step (user supplies one known
   dimension).

## Metric recovery (the honest part)

A photograph alone cannot give absolute dimensions. Karmi therefore:

* uses **scale references** present in the frame (brick course height, standard door height, a
  supplied object of known size),
* accepts an optional **user-supplied known dimension**,
* reports **approximate dimensions with a confidence value**, and
* routes low-confidence items to **human verification** rather than asserting them.

Everything Karmi outputs is phrased as *items to verify with your architect or municipality*.

## Failure modes we design for

| Failure | Handling |
|---|---|
| Remarked-up / low-quality scan | refuse and ask for a better copy; never guess |
| Drawing without a north arrow | request orientation from the user; flag the resulting uncertainty |
| Photo taken at an angle | estimate and report confidence; degrade to qualitative comparison |
| Ambiguous opening (window vs vent) | classify with confidence, list in verify-items |
| User expectation of a "violation report" | language is deliberately "verify", never "violates" |

## Privacy

Site photos and drawings often contain identifiable homes and names. The default pipeline runs
locally; any public dataset release is **opt-in per contributor** and stripped of personal
identifiers.
