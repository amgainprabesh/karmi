# Karmi (कर्मी)

**A compiler between approved architectural design and built reality — for Nepal's housing.**

> Status: Frogtoberfest 2026 build. The repository is young: what works today is the 2D→3D
> transition engine (`proto/plan-to-3d.html`), plus the architecture and AI-usage plan below.

---

## The problem

In Nepal you cannot legally build without a **Naksa Pass** (Building Act 2055). Drawings are
prepared and signed by a Nepal Engineering Council–registered professional, reviewed against the
**National Building Code** and municipal bylaws, and approved by the local body.

Then construction drifts. The window comes out 3' instead of 5'. The stair is narrower. The side
setback shrinks. Nobody re-measures; the homeowner cannot read the drawings they paid for, and the
completion certificate (*Sampurna Praman Patra*) is supposed to require conformance but has no
practical way to verify it.

Deviations from approved design are how unsafe buildings get built — in one of the most
seismically exposed countries on earth.

## What Karmi does

1. **Approved set in.** Upload the naksa drawing set (vector PDF or scan). AI extracts walls,
   door/window openings, room polygons, dimensions and orientation → a machine-readable model of
   the *approved* building.
2. **Reality in.** Upload construction photos taken over time. AI identifies the construction
   stage (foundation → columns → walls → roof) and detects visible elements with approximate
   dimensions, using scale references (brick courses, standard door height) — each with a
   confidence value.
3. **Compile the difference.** A comparison engine diffs the two models element by element:
   expected vs observed, with severity.
4. **Explain it.** A Nepali report plus a **2D→3D transition**: the approved house, then the
   as-built house, differences highlighted — ending in *items to verify with your architect or
   municipality*.

## Where the AI is load-bearing

Their core test: *delete the AI call and does the product still work?* Here it does not — the
renderer is deliberately dumb, it consumes a semantic model and infers nothing.

| Stage | AI does | Consumed by |
|---|---|---|
| Extraction A — drawing → geometry | segmentation / vector classification of walls, openings, rooms | `core/model.py` → scene graph builder |
| Extraction B — photos → observed state | stage classification + element detection + approximate dimensions + confidence | `core/observe.py` → diff engine |
| Comparison & explanation | structured diff reasoning, severity, Nepali explanation text | `core/diff.py` → report renderer |

## Model policy

**Open-weight only, end to end** — vision, text and embeddings. No OpenAI / Claude / Gemini /
Azure anywhere, including auxiliary calls. Locally hosted inference (Ollama / llama.cpp / vLLM) is
the default; a hosted provider serving open weights is an optional fallback. See `AI_USAGE.md`.

## Open-source contribution

* The first annotated dataset of **Nepali Naksa Pass drawings paired with construction photos**.
* The **conformance engine** and the **2D→3D transition renderer**.

## Deliberate scope limits

Single floor, residential. Walls / rooms / doors / windows / stage. No structural calculations. No
absolute-precision claims: outputs are flagged estimates with confidence, framed as *items to
verify* — never as accusations of violation.

## Known limitations

* Absolute dimensions from a photograph alone are not reliably recoverable. We use scale
  references, an optional user-supplied known dimension, and confidence labels.
* Vector-PDF drawings parse far more accurately than scans; raster accuracy on Nepali drawing
  conventions is an open task until our dataset is released.

## Roadmap

- [x] 2D→3D transition prototype (hand-authored plan) — `proto/plan-to-3d.html`
- [ ] plan → semantic model from vector PDFs
- [ ] raster fallback, fine-tuned on Nepali naksa drawings
- [ ] construction stage classifier + element detection from photos
- [ ] diff engine + Nepali report
- [ ] approved-vs-built dual render
- [ ] annotated dataset release

## Team

**Team Amgain** — Frogtoberfest 2026
Prabesh Amgain · Prabhat Amgain

## Licence

MIT — see `LICENSE`.
