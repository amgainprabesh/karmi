# Karmi — Status Board

> **Live board.** Snapshot: 2026-10-04 16:29 NST · **Owner:** PM · Companion documents: [`PLAN.md`](PLAN.md) (scope contract), `CHANGELOG.md` (what landed).
>
> **Verification rule:** `verified` requires a named check that was actually run — recorded in the "Verified by" column (who + what command/observation + date). Anything less is `written-unverified`.
>
> **Honesty note (read first):** the PM has not executed any component code. Parallel workstreams are being written right now and files are landing continuously — this is a point-in-time snapshot. In it, **no component is verified**; partial workstreams show the files seen on disk and are marked `in progress`. Re-check before relying on any row.

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
| Data contract (frozen) | Orchestrator | `core/schema.py` | Pydantic models: `SceneGraph`, `ObservedState`, `DiffReport`, `Provenance`; SCHEMA_VERSION 0.1.0 | written-unverified | — |
| Orchestration (frozen) | Orchestrator | `core/pipeline.py` | `run_pipeline()`, `run_from_manifest()`; artifact set: scene/observed/report JSON, HTML + MD reports, `view.json`, `run.json` | written-unverified | — |
| Fixtures (frozen) | Orchestrator | `fixtures/make_naksa.py`, `fixtures/naksa_{base,drift,sparse}.pdf` | Synthetic vector drawings; base / drift / sparse variants | written-unverified | — |
| Repo skeleton | Orchestrator | `requirements.txt`, `.python-version`, `LICENSE`, `.gitignore`, `core/__init__.py` | Pinned dependencies; Python 3.12; MIT licence | written-unverified | — |
| Ingest | BACKEND-CORE | `core/ingest.py` | Input normalisation; `SourceKind` detection; photo intake | in progress | — |
| Geometry | BACKEND-CORE | `core/geometry.py` | Vector segment ops: snapping, merging, polygon closure | in progress | — |
| Scene model | BACKEND-CORE | `core/model.py` | `build_scene_graph(drawing, *, scale_m_per_unit, north_deg, ai) -> SceneGraph` | in progress | — |
| AI provider layer | BACKEND-AI | `core/ai/` (provider, prompts, vision) | Injectable `ai` object; `NullProvider` default; open-weight only | in progress | — |
| Observe | BACKEND-AI | `core/observe.py` | `to_observed_state(photos, *, known_dimension, ai, stage_hint, sidecars) -> ObservedState` | in progress | — |
| Diff engine | BACKEND-DIFF | `core/diff.py` | `diff_scene(scene, observed, *, ai) -> DiffReport` | in progress | — |
| Report renderer | BACKEND-DIFF | `core/report.py` | `render_html(report, scene, observed) -> str`, `render_markdown(...) -> str` | in progress | — |
| Nepali narration | BACKEND-DIFF | `core/nepali.py` | Nepali strings for deltas and verify items | in progress | — |
| Web UI | FRONTEND-WEB | `web/app.py`, `web/templates/` (base, index, run, error), `web/static/` | HTTP upload → `run_pipeline` → report + viewer pages | in progress (partial — files on disk, not run) | — |
| Renderer | RENDER-3D | `render/adapter.py`, `render/viewer.html` | `build_view(scene, observed, report) -> dict`; viewer consumes `view.json` | in progress (partial — `adapter.py` on disk, `viewer.html` pending) | — |
| Tests | TESTING | `tests/` | pytest: schema round-trip, fixture parse, diff determinism, degraded paths | in progress | — |
| Security + privacy | SECURITY | `core/validate.py`, `docs/SECURITY.md`, `docs/PRIVACY.md` | Upload validation; local-first privacy stance | in progress | — |
| Research | RESEARCH | `docs/research/` | Citable regulatory references (NBC, Building Act 2055, bylaws) | in progress | — |
| UI design spec | Unconfirmed (not on PM roster) | `docs/design/ui-spec.md` | UI layout and flow spec for the web app | written-unverified | — |
| Language guide | Unconfirmed (not on PM roster) | `docs/design/language-guide.md` | Nepali/English wording conventions | written-unverified | — |
| Dataset tooling (stretch) | Unassigned (stretch) | `dataset/` (planned) | Annotation format + seed pairs; public release is post-v0 | planned | — |
| 2D→3D prototype (pre-existing) | Orchestrator | `proto/plan-to-3d.html` | Hand-authored 2D→3D animation demo; no AI; not yet wired to the pipeline | written-unverified | — |
| Judge-facing docs | Orchestrator | `README.md`, `docs/architecture.md`, `AI_USAGE.md` | Problem statement, architecture, AI disclosure | written-unverified | — |
| Project docs (this package) | PM | `docs/PLAN.md`, `docs/DEMO_SCRIPT.md`, `docs/status.md`, `CHANGELOG.md` | Scope contract, video script, live board, changelog | written-unverified | PM — markdown structure check only (2026-10-04) |

## Blocked

None as of this snapshot.

## Checkpoints

| Checkpoint | Date | What must be true |
|---|---|---|
| M2 | Oct 14 | Vertical slice runs offline on the fixtures |
| M3 | Oct 21 | Money shot renders from real diff data; core tests green |
| M4 | Oct 26 | Feature freeze; all DoD checks pass; demo video recorded |

## How to update this board

- An owner moves their row from `in progress` to `written-unverified` when files land, and to `verified` only after running a named check — put the command, the date, and who ran it in "Verified by".
- The PM re-snapshots at M2 / M3 / M4; the orchestrator re-snapshots at integration.
- Keep it pessimistic: if it has not been checked, it is not verified.