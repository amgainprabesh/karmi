# Karmi — Status Board

> **Live board.** Snapshot: 2026-10-04 17:35 NST · **Owner:** PM · **Integration snapshot by:** orchestrator · Companion documents: [`PLAN.md`](PLAN.md) (scope contract), [`CHANGELOG.md`](../CHANGELOG.md) (what landed).
>
> **Verification rule:** `verified` requires a named check that was actually run — recorded in the "Verified by" column (who + what command/observation + date). Anything less is `written-unverified`.
>
> **This snapshot is post-integration.** The orchestrator ran the pipeline, the test suite, the web app and the 3D viewer, and fixed four real defects it found. Rows the orchestrator personally ran are `verified`; everything else stays honest at `written-unverified`. A second build round (dataset tooling, raster path, scripts, extra tests) is in flight and is marked `in progress`.

## Legend

| Status | Meaning |
|---|---|
| planned | Scoped or assigned; no work visible yet |
| in progress | Owner is actively writing it; not on disk yet (or partial) |
| written-unverified | File(s) exist on disk; no one has run or checked them |
| verified | A named check was run and passed; recorded in "Verified by" |
| blocked | Cannot proceed; reason noted below the table |

## Board

| Component | Owner | File(s) | Contract | Status | Verified by |
|---|---|---|---|---|---|
| Data contract | Orchestrator | `core/schema.py` | Pydantic models: `SceneGraph`, `ObservedState`, `DiffReport`, `Provenance`; SCHEMA_VERSION 0.1.0 | verified | orchestrator — schema round-trip in the test suite; `Provenance.source` extended with `human_annotation` (2026-10-04) |
| Orchestration | Orchestrator | `core/pipeline.py` | `run_pipeline()`, `run_from_manifest()`; artifact set: scene/observed/report JSON, HTML + MD reports, `view.json`, `run.json` | verified | orchestrator — full runs on fixtures; `run.json` confirmed free of absolute paths (2026-10-04) |
| Fixtures | Orchestrator | `fixtures/make_naksa.py`, `fixtures/naksa_{base,drift,sparse}.pdf` | Synthetic vector drawings; base / drift / sparse variants | verified | orchestrator — plan geometry corrected (the divider was drawn in the wrong column); now 5 rooms at 24/21/16/6.4/7.6 m² with **0 warnings** (2026-10-04) |
| Repo skeleton | Orchestrator | `requirements.txt`, `.python-version`, `LICENSE`, `.gitignore`, `core/__init__.py` | Pinned dependencies; Python 3.12; MIT licence; run dirs gitignored | verified | orchestrator — clean venv build; `git add -A` stages no run output (2026-10-04) |
| Ingest | BACKEND-CORE | `core/ingest.py` | Input normalisation; `SourceKind` detection; photo intake | verified | orchestrator — exercised through scene extraction on all three fixtures (2026-10-04) |
| Geometry | BACKEND-CORE | `core/geometry.py` | Vector segment ops: snapping, merging, polygon closure | verified | orchestrator — exercised via extraction (7 walls, 9 openings, 5 rooms) (2026-10-04) |
| Scene model | BACKEND-CORE | `core/model.py` | `build_scene_graph(drawing, *, scale_m_per_unit, north_deg, ai) -> SceneGraph` | verified | orchestrator — `python -m core.model fixtures/naksa_base.pdf` → 7 walls / 9 openings / 5 rooms / 2 dims / scale 0.025 m/pt conf 0.90 / north 0° (2026-10-04) |
| AI provider layer | BACKEND-AI | `core/ai/` (provider, prompts, vision) | Injectable `ai` object; `NullProvider` default; open-weight only | written-unverified | owner: mock-provider run, 69/69 checks. **No live model has been run** — stated in `AI_USAGE.md`; round 2 adds a real HTTP round-trip test |
| Observe | BACKEND-AI | `core/observe.py` | `to_observed_state(photos, *, known_dimension, ai, stage_hint, sidecars) -> ObservedState` | verified | orchestrator — `python -m core.observe fixtures/photos` → stage `walls`, 4 captures, sidecar elements carrying provenance (2026-10-04) |
| Diff engine | BACKEND-DIFF | `core/diff.py` | `diff_scene(scene, observed, *, ai) -> DiffReport` | verified | orchestrator — **two real defects found and fixed**: an order-dependent matcher (now global best-first); absence of evidence reported as `MISSING`/HIGH (now a coverage guard). Headline run: window drawn 1.50 m vs measured 1.00 m → HIGH, 33.3% (2026-10-04) |
| Report renderer | BACKEND-DIFF | `core/report.py` | `render_html(report, scene, observed) -> str`, `render_markdown(...) -> str` | verified | orchestrator — HTML + MD written in every run; results page rendered in headless Edge (2026-10-04) |
| Nepali narration | BACKEND-DIFF | `core/nepali.py` | Nepali strings for deltas and verify items | verified | orchestrator — rendered in headless Edge; Devanagari confirmed correct (2026-10-04) |
| Web UI | FRONTEND-WEB | `web/app.py`, `web/templates/` (base, index, run, error), `web/static/` | HTTP upload → `run_pipeline` → report + viewer pages | verified | orchestrator — `/healthz` 200; real upload → 79 KB run page containing the verify list; malicious PDF → friendly bilingual 400. **Fixed**: `.json` measurement sidecars were silently dropped; `/viewer/ID/vendor/three.module.js` 404'd (2026-10-04) |
| Renderer | RENDER-3D | `render/adapter.py`, `render/viewer.html`, `render/vendor/three.module.js` | `build_view(scene, observed, report) -> dict`; viewer consumes `view.json` | verified | orchestrator — headless Edge + WebGL: 3D model renders with rooms labelled NP+EN; Diff mode highlights the differing element in red; **0 console errors, 0 HTTP ≥ 400** (2026-10-04) |
| Tests | TESTING | `tests/` | pytest: schema round-trip, fixture parse, diff determinism, degraded paths | verified | orchestrator — `python -m pytest -q` → **53 passed** (2026-10-04); round 2 adds coverage-guard, matching, AI-over-HTTP and privacy tests |
| Security + privacy | SECURITY | `core/validate.py`, `docs/SECURITY.md`, `docs/PRIVACY.md` | Upload validation; local-first privacy stance | verified | orchestrator — JS-bearing PDF rejected by both the CLI and the web upload; traversal paths 404; `run.json` path leak fixed (2026-10-04) |
| Research | RESEARCH | `docs/research/` | Citable regulatory references (NBC, Building Act 2055, bylaws) | written-unverified | owner cited primary sources with URLs; anything unconfirmed is explicitly flagged in the documents |
| UI design spec | DESIGN | `docs/design/ui-spec.md`, `docs/design/language-guide.md`, `docs/design/wireframes.html` | UI layout and flow spec, data-to-UI mapping, allowed language | written-unverified | owner: 123 schema-field references checked against `core/schema.py`, 0 problems; wireframes rendered in headless Chrome |
| Dataset tooling | R2-DATASET | `dataset/` | Annotation record, consent, de-identification, export, splits | in progress | second build round |
| Raster / scan path | R2-RASTER | `core/raster.py`, `docs/RASTER.md` | Deterministic raster → line segments with honest confidence | in progress | second build round |
| Scripts / quality gate | R2-SCRIPTS | `scripts/` | One-command demo, check-all gate, web smoke test | in progress | second build round |
| 2D→3D prototype (pre-existing) | Orchestrator | `proto/plan-to-3d.html` | Hand-authored 2D→3D animation demo; no AI; superseded by `render/` | written-unverified | not wired to the pipeline; kept as the design ancestor |
| Judge-facing docs | Orchestrator | `README.md`, `docs/architecture.md`, `AI_USAGE.md` | Problem statement, architecture, AI disclosure, run instructions | verified | orchestrator — updated to match reality after integration (2026-10-04) |
| Project docs (this package) | PM | `docs/PLAN.md`, `docs/DEMO_SCRIPT.md`, `docs/status.md`, `CHANGELOG.md` | Scope contract, video script, live board, changelog | written-unverified | PM — markdown structure check only; this board re-snapshotted by the orchestrator |

## Blocked

None.

## Known honest gaps

1. **No live open-weight model has been run.** The provider layer and both extraction paths are written and mock-tested; the demo uses hand-measured sidecars. This is stated plainly in `AI_USAGE.md` rather than glossed over.
2. **Raster/scan drawings are not extracted yet** — they return a warning and an empty model. `core/raster.py` is in flight.
3. **No real dataset exists yet.** `docs/research/dataset-plan.md` is the plan, the tooling is in flight, and no real records will be collected without explicit consent.
4. **Regulatory numbers are research, not code.** `docs/research/nbc-rules.md` feeds future threshold tuning and is explicitly marked unverified wherever a municipal bylaw check is still needed.
5. **Nothing is pushed to a remote.** All work is local commits only.

## Checkpoints

| Checkpoint | Date | What must be true |
|---|---|---|
| M2 | Oct 14 | Vertical slice runs offline on the fixtures — **already true as of 2026-10-04** |
| M3 | Oct 21 | Money shot renders from real diff data; core tests green — **already true as of 2026-10-04** |
| M4 | Oct 26 | Feature freeze; all DoD checks pass; demo video recorded |
| Demo Day | Oct 30 | Top-5 shortlist pitches in person in Kathmandu |

## How to update this board

- An owner moves their row from `in progress` to `written-unverified` when files land, and to `verified` only after running a named check — put the command, the date, and who ran it in "Verified by".
- The PM re-snapshots at M2 / M3 / M4; the orchestrator re-snapshots at integration.
- Keep it pessimistic: if it has not been checked, it is not verified.