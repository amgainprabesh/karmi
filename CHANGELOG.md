# Changelog

All notable changes to Karmi are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses `MAJOR.MINOR.PATCH` versioning; the v0 line is pre-release until Demo Day (2026-10-30).

> **Remote status: nothing in this repository has been pushed to a remote yet.** This entry describes the local build as of 2026-10-04. Components being written in parallel are marked *(in progress)* and are **not verified** — the live state is in `docs/status.md`; the scope contract is `docs/PLAN.md`.

## [v0.1.0] — unreleased

### Added

**Sprint 1 — Agile Scrum & Extreme Programming delivery:**

- `core/regulatory.py` — Nepal National Building Code (NBC 206 Architectural Design Requirements 2015/2024) conformance verification engine: checks habitable room area (≥ 6.0 m²), minimum room dimension (≥ 2.0 m), kitchen area (≥ 5.0 m²) and width (≥ 1.8 m), toilet/bath minimum dimensions, exit door clear width (≥ 0.9 m), and natural daylight/ventilation opening ratio (1/10 in Hills/Mountains). Wired into `core/diff.py` to enrich `verify_list` items and `report.meta["regulatory"]`. Strictly preserves the honesty invariant with 0 "violation" phrasing.
- `core/ai/provider.py` & `core/ai/__init__.py` — Resilient Open-Weight AI Layer: added active `diagnose()` health check probes for Ollama (`/api/tags`), OpenAI-compatible (`/models`), and Null providers; implemented `with_retry()` with exponential backoff on transient HTTP/connection errors; added `FallbackProvider` allowing transparent multi-backend chaining from primary open-weight providers down to mock/null offline fallbacks without uncaught crashes.
- `web/app.py` & `web/templates/run.html` — Web UI Direct Export & Inspection: added `/run/{run_id}/export/json` and `/run/{run_id}/export/report` download routes with proper `Content-Disposition: attachment` headers; added `/api/export/{run_id}` structured summary endpoint; added direct download action buttons in `run.html`.
- `render/viewer.html` — 3D Viewer Deep-Linking: added URL search query param inspection (`?focus=<id>` or `?highlight=<id>`) to automatically isolate, switch to diff mode, and open the element inspection card on load.

**Sprints 2, 3, 4 — Five Iteration Cycles Delivery (Agile Scrum + Kanban + XP):**

- **Cycle 1 (Story 4): Municipal Building Bylaws & Setbacks Engine (`core/municipal.py`, `core/diff.py`):**
  - Implemented municipal building bylaw profiles (National Basic 2072, Kathmandu Valley KVDA, Kirtipur, Pokhara).
  - Evaluated front road setback (1.5m to 6.0m), side/rear setbacks with openings (1.5m), blank wall exemptions, ground coverage ($\le 70\%$ for $\le 250\text{ m}^2$, $\le 60\%$ above), and Floor Area Ratio (FAR) advisory checks.
  - TDD verified via `tests/test_municipal.py` (7/7 passed).
- **Cycle 2 (Story 5): Printable Bilingual Report Document & PDF Exporter (`core/pdf_export.py`, `web/app.py`):**
  - Created print-optimized HTML report with `@media print`, physical `[ ]` checkboxes for site masons, and tripartite sign-off blocks (डकर्मी, घरधनी, इन्जिनियर).
  - Added `/run/{run_id}/export/print` web route and clickable action button in `web/templates/run.html`.
  - TDD verified via `tests/test_pdf_export.py` (3/3 passed).
- **Cycle 3 (Story 6): Raster & Blueprint Extractor Calibration & Tolerance Tuning (`core/raster.py`):**
  - Auto-detected ammonia blueprint ("नीलो ब्लूप्रिन्ट") and photo negative polarity (`detect_blueprint_polarity`), automatically inverting tones before line extraction.
  - Calibrated run-length extraction tolerances (`calibrate_tolerances`) proportionally to rendering DPI.
  - Added structured blueprint quality grading (`blueprint_quality_score`) with letter grades ('A'-'D') and homeowner advice in Nepali.
  - TDD verified via `tests/test_raster_calibration.py` (5/5 passed).
- **Cycle 4 (Story 7): AI Vision Structured Schema & Multi-Photo Consensus (`core/ai/vision.py`):**
  - Enhanced `PhotoElement` with perspective and occlusion detection (`effective_confidence` damping).
  - Implemented `multi_photo_consensus`: confidence-weighted stage voting, cross-photo stage discrepancy alerts, and element clustering with corroboration bonuses capped at 0.70.
  - TDD verified via `tests/test_ai_vision_schema.py` (5/5 passed).
- **Cycle 5 (Story 8): Interactive 3D Measurement & Bilingual Overlay Inspector (`render/viewer.html`, `render/adapter.py`):**
  - Added interactive point-to-point measurement ruler (`#btn-measure`) in 2D plan and 3D views, computing real-world distances in meters and feet with Devanagari annotations.
  - Implemented instant bilingual HUD language toggle (`#btn-lang`: नेपाली ↔ EN) across all buttons, status badges, and panels.
  - Forwarded municipal and regulatory metadata to view payload in `render/adapter.py`.
  - TDD verified via `tests/test_viewer_enhancements.py` (3/3 passed). Total passing test suite reached **197 tests**.

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

- Comprehensive test suite expansion: added direct unit tests for `core/nepali.py` (Devanagari numerals, units, enum labels), `core/diff.py` AI narration safety guard, `core/ingest.py`, `core/raster.py` (line extraction, deskew recovery, scan-only pipeline), `web/app.py` (FastAPI routes and upload flows), `test_demo_regression.py` (pins the 8-finding demo scenario and automated DoD checks D1–D7), and `test_render_selfcheck.py`.
- Mutation testing spot-check script (`scripts/mutation_spotcheck.py`) that validates test sensitivity against 6 intentional regressions.
- Pre-demo manual testing guide and checklist in `docs/TESTING.md`.

### Changed

- `pytest.ini` now automatically collects `dataset/tests/`, silences starlette deprecation warnings, and configures the `@pytest.mark.slow` marker. Total passing tests increased from 77 to 155.
- `scripts/check_all.py` updated with optional `--coverage` flag and privacy filters for coverage cache files.
- `requirements.txt` updated to include `pytest-cov>=5.0` in dev dependencies. Line coverage baseline measured at 74% across codebase.

### Fixed

- Fixed false claim bug in `core/nepali.py` (`weak_evidence_np` / `weak_evidence_en`): when confidence exceeded the threshold, the function previously asserted "confidence X, below Y"; it now cleanly returns `""`.
- Multi-photo sidecar handling in `scripts/demo.py`, `scripts/smoke_web.py`, and `scripts/check_all.py` expanded across all 3 construction stages.