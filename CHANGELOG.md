# Changelog

All notable changes to Karmi are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses `MAJOR.MINOR.PATCH` versioning; the v0 line is pre-release until Demo Day (2026-10-30).

> **Remote status: nothing in this repository has been pushed to a remote yet.** This entry describes the local build as of 2026-10-04. Components being written in parallel are marked *(in progress)* and are **not verified** — the live state is in `docs/status.md`; the scope contract is `docs/PLAN.md`.

## [v0.1.0] — unreleased

### Added

**Frozen foundations (on disk; not yet run end-to-end as a suite):**

- `core/schema.py` — the v0 data contract: `SceneGraph` (approved), `ObservedState` (as-built), `DiffReport` (deltas + verify list), with `Provenance` and a confidence value travelling on every extracted number.
- `core/pipeline.py` — degrade-never-crash orchestration. `run_pipeline()` writes the full artifact set (`scene.json`, `observed.json`, `report.json`, `report.html`, `report.md`, `view.json`, `run.json`); the AI provider is injected and `NullProvider` is the default, so the pipeline runs with no network at all.
- `fixtures/make_naksa.py` and `fixtures/naksa_{base,drift,sparse}.pdf` — synthetic, structurally realistic naksa-style drawings containing no real household data: a reference plan, a drifted variant for diff tests, and a walls-only variant for warning paths.
- `proto/plan-to-3d.html` — the 2D→3D transition prototype: a hand-authored plan that proves the animation approach (no AI; not yet wired to the pipeline).

**In progress (parallel workstreams; unverified — files may not be on disk yet):**

- `core/ingest.py`, `core/geometry.py`, `core/model.py` — vector-PDF → scene graph. *(in progress)*
- `core/ai/*`, `core/observe.py` — open-weight provider layer; photos → observed state. *(in progress)*
- `core/diff.py`, `core/report.py`, `core/nepali.py` — comparison, severity, Nepali report. *(in progress)*
- `web/` — FastAPI upload UI. *(in progress)*
- `render/adapter.py`, `render/viewer.html` — data-driven 2D↔3D approved-vs-built viewer. *(in progress)*
- `tests/` — pytest suite. *(in progress)*
- `core/validate.py`, `docs/SECURITY.md`, `docs/PRIVACY.md` — security and privacy. *(in progress)*
- `docs/research/` — domain research for citable regulatory claims. *(in progress)*

**Documentation:**

- `docs/PLAN.md` — v0 definition of done (testable), workstreams, critical path, out-of-scope list, risk register, milestones.
- `docs/DEMO_SCRIPT.md` — shot-by-shot script for the required demo video (under 3:00; problem / solution / workflow / value).
- `docs/status.md` — live status board; everything unverified is marked as such.
- `README.md`, `docs/architecture.md`, `AI_USAGE.md` — problem statement, architecture, and the open-weight model policy with where AI output is consumed programmatically.

### Changed

- Repository reshaped from a single prototype (`proto/plan-to-3d.html`) into a staged pipeline architecture: a frozen data contract (`core/schema.py`), one orchestration entry point (`core/pipeline.py`), synthetic fixtures, and one writer per module — so parallel workstreams integrate through a stable interface.
- Model policy fixed for the whole pipeline: open-weight only, start to finish; no closed paid APIs, including auxiliary calls.

### Fixed

- Nothing yet — the first fixes will land as the parallel workstreams are exercised. No component has been end-to-end verified as of this entry.