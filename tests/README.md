# Karmi test suite

Run everything (from the repository root, with the project venv):

    .venv/Scripts/python.exe -m pytest -q

Run a single file, or a single test:

    .venv/Scripts/python.exe -m pytest tests/test_schema.py -q
    .venv/Scripts/python.exe -m pytest tests/test_pipeline.py::test_run_pipeline_writes_a_parseable_run_manifest -q

Skip reasons are shown with `-ra` (already the default via `pytest.ini`):

    .venv/Scripts/python.exe -m pytest -ra

## Tolerant-skip design

Other agents write `core.model`, `core.observe`, `core.diff`, `core.report`,
`core.validate`, `render.adapter` and `web.app` in parallel with this suite.
The suite is built so that:

* **module missing -> SKIP.** Each test file starts with
  `pytest.importorskip(...)` (via the `require()` helper in `conftest.py`).
  A file whose module is not written yet reports *skipped*, never failed.
* **module present but broken -> FAIL.** That is the signal we want: a module
  that imports but cannot do its job turns the suite red.
* **assertions target behaviour, not internals.** Tests assert what the frozen
  contract in `core/schema.py` and the pipeline docstring guarantee
  (a zero-length wall raises, confidence is bounded, run.json is written, the
  report carries a verify section, ...), never exact extractor numbers.
* no test requires network, an AI model, or a module another agent has not
  finished yet.

## Helpers (`tests/conftest.py`)

| helper | purpose |
|---|---|
| `require(name)` | import a module or skip with a clear reason |
| `require_attr(mod, name)` | fetch an entry point or skip if it does not exist yet |
| `call_adaptive(fn, ...)` | call a function with only the kwargs its signature accepts (tolerates signature drift) |
| `no_network(monkeypatch)` | makes any real network attempt explode — proves the offline path is offline |
| `make_scene()` / `make_observed()` / `make_report()` (+ `make_wall`, `make_wall_element`, `make_observed_for`) | hand-made model pair so schema/diff/report tests never depend on the extractor |

Fixtures: `naksa_base`, `naksa_drift`, `naksa_sparse` (paths to
`fixtures/*.pdf`), `tmp_run_dir`, `sample_scene`, `sample_observed`,
`sample_report`, `sample_models`, `require_module`.

## Files

| file | needs | covers |
|---|---|---|
| `test_schema.py` | `core.schema` (always present) | JSON round-trips, wall/confidence invariants, `recount()`, enum serialisation |
| `test_geometry_and_model.py` | `core.model` | base/sparse/drift drawings vs structural sanity |
| `test_observe.py` | `core.observe` | empty/unreadable photos warn, sidecar provenance, offline proof |
| `test_diff_and_report.py` | `core.diff`, `core.report` | matched/differs/missing/unexpected, monotone severity, confidence cap, verify section |
| `test_validate.py` | `core.validate` | accept real PDF, reject fake/oversized, `safe_filename`/`safe_join` |
| `test_pipeline.py` | `core.pipeline` (always present) | run.json end-to-end, manifest re-run, no-network default path |
| `test_render_adapter.py` | `render.adapter` | view payload shape, empty-input warnings |
| `test_nepali.py` | `core.nepali` | digit round-trips, unit formatting, enum translations, weak evidence safeguards |
| `test_narration_guard.py` | `core.diff` | AI narration validation: numbers check, line count and language safety |
| `test_ingest.py` | `core.ingest` | input classification for vector PDF, raster scan, photos, and invalid formats |
| `test_raster.py` | `core.raster` | deterministic line/segment extraction, deskew recovery, scan-only pipeline |
| `test_web_app.py` | `web.app` | FastAPI endpoints, healthz, upload flows with sidecars, 400/404 handling |
| `test_demo_regression.py` | multiple | pins 8-finding demo scenario, control run zero-diff, and DoD invariants D1-D7 |
| `test_render_selfcheck.py` | `render._selfcheck` | adapter self-check and viewer.html DOM integrity markers |
| `dataset/tests/` | `dataset` | dataset schema, consent records, de-identification, and export manifests |

## Fast run & coverage

Run fast tests (excluding slow raster/full upload runs):

    .venv/Scripts/python.exe -m pytest -q -m "not slow"

Run with test coverage report:

    .venv/Scripts/python.exe -m pytest --cov --cov-report=term-missing -q

`pytest.ini` sets `testpaths = tests dataset/tests`, `pythonpath = .` and
`-p no:cacheprovider` (so runs never leave a `.pytest_cache/` in the repo).