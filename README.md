# Karmi (कर्मी)

**A compiler between approved architectural design and built reality — for Nepal's housing.**

> Status: Frogtoberfest 2026 build — **v0.1.0**. The full pipeline runs end to end,
> offline, with no model and no network: a vector naksa PDF becomes a scene graph,
> site photos (plus hand-entered measurements) become an observed state, the two are
> compared, and the result is a Nepali report and a 2D→3D dual view. `pytest` is green.
> See `docs/status.md` for the honest component-by-component state.

---

## Run it

```bash
# 1. environment (Python 3.12)
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt   # or .venv/bin/python

# 2. the pipeline on the sample drawing
python -m core.model fixtures/naksa_base.pdf          # drawing  -> scene graph
python -m core.observe fixtures/photos                # photos   -> observed state
python -c "from core.pipeline import run_pipeline; \
  print(run_pipeline('fixtures/naksa_base.pdf', ['fixtures/photos/front_walls_stage.jpg'], \
  out_dir='runs/demo', known_dimension=10.0).to_dict())"

# 3. the web UI
python -m web.app            # then open http://localhost:8000

# 4. the tests
python -m pytest -q
```

Nothing above needs a model, a GPU, an API key or a network connection. The AI layer is
optional and injected — see `AI_USAGE.md`.

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
- [x] plan → semantic model from vector PDFs (`core/model.py`, `core/geometry.py`)
- [x] construction-stage + element observation from photos, with a hand-measured sidecar
      fallback (`core/observe.py`) — the AI vision path is implemented and mock-tested;
      it has not yet been run against a live open-weight model
- [x] diff engine + Nepali report (`core/diff.py`, `core/report.py`, `core/nepali.py`)
- [x] approved-vs-built dual render (`render/adapter.py`, `render/viewer.html`)
- [x] local web UI (`web/`)
- [x] test suite (`tests/`, 53 passing)
- [x] security & privacy layer (`core/validate.py`, `docs/SECURITY.md`, `docs/PRIVACY.md`)
- [ ] raster fallback, fine-tuned on Nepali naksa drawings
- [ ] live-model validation of the photo → observed-state extraction
- [ ] annotated dataset release (`docs/research/dataset-plan.md`)

## Repository layout

```
core/       schema.py (the data contract) · pipeline.py (entry point)
            model.py · geometry.py · ingest.py      drawing -> scene graph
            observe.py · ai/                        photos -> observed state
            diff.py · report.py · nepali.py         compare + Nepali report
            validate.py                             input validation & privacy
render/     adapter.py · viewer.html                approved-vs-built dual view
web/        app.py · templates/ · static/           local FastAPI UI
fixtures/   make_naksa.py + 3 sample drawings + sample photos (all synthetic)
tests/      pytest suite
docs/       architecture · PLAN · status · SECURITY · PRIVACY · research/ · design/
```

Every drawing and photo in `fixtures/` is **synthetic** — generated by
`fixtures/make_naksa.py` and Pillow. No real person's plan or house is in this repo.

## Team

**Team Amgain** — Frogtoberfest 2026
Prabesh Amgain · Prabhat Amgain

## Licence

MIT — see `LICENSE`.
