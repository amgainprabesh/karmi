# Karmi web UI

A local FastAPI app that runs the whole Karmi pipeline end to end in a browser:
upload the approved naksa (PDF) + site photos, get a report page with the
comparison table and a numbered **items-to-verify** list (Nepali first).

**Product rule, stated in the UI in both languages:** Karmi reports *items to
verify* — it never declares a violation.

Everything runs locally. No network calls, no CDNs, no external fonts.

## Run it

From the repository root:

```bash
# option 1
.venv/Scripts/python.exe -m web.app          # Windows venv path
python -m web.app                            # plain python

# option 2
uvicorn web.app:app --port 8000
```

Then open <http://127.0.0.1:8000>.

Environment variables (all optional):

| Variable          | Default        | Meaning                          |
|-------------------|----------------|----------------------------------|
| `KARMI_HOST`      | `127.0.0.1`    | bind address (`python -m web.app`) |
| `KARMI_PORT`      | `8000`         | port (`python -m web.app`)       |
| `KARMI_RUNS_DIR`  | `web/runs`     | where run folders are written    |

## Routes

| Route | What it does |
|---|---|
| `GET /` | upload page (drawing PDF, photos, optional known dimension + stage) |
| `POST /api/analyze` | multipart upload → saves under `web/runs/<id>/inputs/`, runs `core.pipeline.run_pipeline`, returns JSON: run id, summary counts, links, errors/warnings |
| `POST /analyze` | same but a classic form POST → 303 redirect to the run page (works with JavaScript disabled) |
| `GET /run/{id}` | results page: severity cards, delta table (with confidence + provenance), numbered verify list (Nepali first), limits callout, 3D dual view |
| `GET /api/report/{id}` | raw `report.json` |
| `GET /api/runs` | JSON list of all runs |
| `GET /runs/{id}/{file}` | whitelisted run artifacts: `view.json`, `report.json`, `scene.json`, `observed.json`, `run.json`, `uploads.json`, `report.html`, `report.md` |
| `GET /viewer/{id}` | serves `render/viewer.html` if it exists (read at request time), else a clear placeholder page |
| `GET /viewer/{id}/view.json` | the run's `view.json` in the viewer's own URL space (the viewer fetches `view.json` relative to itself) |
| `GET /healthz` | health + `viewer_available` / `core_available` flags |
| `GET /static/*` | CSS/JS |

## Run folder layout

```
web/runs/<YYYYMMDD-HHMMSS-hex>/
  inputs/        # saved uploads (drawing.pdf, photos)
  uploads.json   # original filenames, sizes, skipped files
  scene.json / observed.json / report.json / report.html / report.md / view.json / run.json
                 # written by core.pipeline.run_pipeline
```

`web/runs/` is runtime output — it is safe to delete.

## Honesty & robustness rules baked in

* Errors are never tracebacks in the UI: validation problems return a friendly
  bilingual message (400), unexpected ones a structured JSON/HTML error (500).
  Photos that are not images are skipped with a note, not fatal.
* A degraded pipeline (a stage failed) still produces a run page that says so.
* The 3D section checks at request time whether `render/viewer.html` exists; if
  not, it shows a placeholder explaining the viewer is not built yet — the rest
  of the page is unaffected. When the viewer lands it is embedded via
  `/viewer/{id}/` and receives the run's view data three ways: inline as
  `window.KARMI_VIEW` (the viewer's first preference), as
  `window.KARMI_VIEW_URL`, and as a relative `view.json` served from the same
  URL space.
* The delta table always shows confidence and the provenance source of both the
  drawing element and the observed element.
* `static/app.js` is progressive enhancement only (upload progress bar,
  severity filter). The site fully works with JavaScript disabled.

## Tests / manual verification

```bash
curl -s localhost:8000/healthz
curl -s -F drawing=@fixtures/naksa_base.pdf -F known_dimension=10.0 localhost:8000/api/analyze
curl -s localhost:8000/run/<ID> | head
```