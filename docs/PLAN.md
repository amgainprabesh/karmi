# Karmi — v0 Build Plan & Scope Contract

> **Owner:** PM · **Status:** living document · **Last updated:** 2026-10-04 · **Live state:** [`docs/status.md`](status.md)
>
> Karmi (कर्मी) — "a compiler between approved architectural design and built reality" — is Team Amgain's entry to **Frogtoberfest 2026** (Leapfrog Technology). Challenge window: Oct 1–30, 2026; top 5 teams present live in Kathmandu on Demo Day, Oct 30.
>
> This document is the **scope contract** for the v0 build: what "done" means (as checks, not aspirations), who owns what, what is deliberately not built, and what could go wrong. Companion documents: [`architecture.md`](architecture.md) (design), [`AI_USAGE.md`](../AI_USAGE.md) (AI disclosure), [`status.md`](status.md) (live state), [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) (video script).

## 1. What v0 is

Karmi compiles the difference between an **approved** building and the **as-built** building:

```
approved naksa (vector PDF) ──► scene graph ──┐
                                              ├──► diff engine ──► Nepali report (items to verify)
site photos ──► observed state ───────────────┘                └──► 2D→3D approved-vs-built view
```

Constraints that are part of the definition, not preferences:

- **Open-weight AI only, end to end** (challenge rule; no closed paid APIs, including auxiliary calls).
- **Local-first**: the pipeline runs on the demo machine; `NullProvider` keeps it alive with no network.
- **Degrade, never crash**: every stage is optional-tolerant and produces warnings, not exceptions.
- **Honest by construction**: confidence travels with every extracted value; the output says *items to verify*, never *violation*. Single-floor residential, geometry only — no structural claims.

## 2. Definition of done — v0

v0 is done when **a stranger can clone the repo, run it on the sample set, and get an honest, reproducible approved-vs-built difference report — offline, with open-weight AI — and the demo video shows exactly that.** Each outcome below is checkable by someone who has never met the team.

| # | Outcome (what must be true) | How a stranger checks it |
|---|---|---|
| D1 | **End-to-end run on the fixture set.** The pipeline processes `fixtures/naksa_base.pdf` plus the fixture photo set end to end and writes `scene.json`, `observed.json`, `report.json`, `report.html`, `report.md`, `view.json`, `run.json`. Every JSON file parses; `report.json` round-trips through `core.schema.DiffReport`. | Clean checkout → install pinned deps (`requirements.txt`) → run the documented entry point (pinned in README at integration) → inspect the output directory; reload `report.json` with `DiffReport.model_validate`. |
| D2 | **The difference is real, not decorative.** On the drift scenario, `report.json` contains at least one delta with status `differs`/`missing` and severity at least `low`, plus at least one `verify_list` item; the `summary` counts equal the actual arrays (`recount()` invariant). | Open `report.json`; count deltas by status; run the recount test. |
| D3 | **The 2D→3D view is data-driven.** `render/viewer.html` draws geometry from `view.json` — no hardcoded house. The number of highlighted elements equals `differs + missing + unexpected` deltas in `report.json`; deleting a delta from a scratch copy of `view.json` removes its highlight. | Load the viewer; compare counts against `report.json`; test with a scratch copy. |
| D4 | **The web workflow works without instructions.** `uvicorn web.app:app` serves an upload page; uploading the approved drawing + photos produces the report page (Nepali renders) and the 3D view; uploading without photos degrades to a visible warning, not an HTTP 500. | Follow the two upload paths in a browser; observe the warning banner on the degraded path. |
| D5 | **AI is load-bearing and disclosed.** Photo → `observed.json` happens only through the open-weight model path; running with `ai=None` (NullProvider) produces explicit warnings and zero fabricated observations. `AI_USAGE.md`'s "consumed by (file → function)" column matches the actual call sites. | Run once with `ai=None`, diff the observed output (expect warnings, no invented elements); grep the named functions in the code. |
| D6 | **Tests are green and meaningful.** `pytest -q` passes on a clean checkout, covering at minimum: schema round-trip, fixture-drawing parse, diff determinism (same inputs → identical deltas), report rendering non-empty, and the degraded/no-AI path. | Run `pytest -q`; read the test names; spot-check that one test fails when its target code is broken. |
| D7 | **Honesty invariants hold.** Every delta carries `confidence` and `reason`; low-confidence items are routed to `verify_list` rather than asserted; the rendered report never contains "violation"/"violates" wording. | Scripted scan of `report.json` plus a grep over the rendered report artifacts. |
| D8 | **Docs and video are judge-complete.** README, `docs/architecture.md`, `AI_USAGE.md`, this plan, `docs/status.md`, `CHANGELOG.md`, `docs/SECURITY.md`, `docs/PRIVACY.md` exist and agree with the code; the demo video is under 3:00 and shows problem, solution, workflow and value (challenge guidelines). | File checklist; watch the video; re-run the demo path and compare with what the video shows. |

Non-goals are listed in §5; the frozen interfaces that make D1–D8 possible are in §3 and §8.

## 3. Workstreams

Owner roles match the build roster; every file has exactly one writer. Status snapshot: 2026-10-04; live detail in `docs/status.md`.

| Component | Owner role | File(s) | Interface (contract) | Status |
|---|---|---|---|---|
| Data contract + orchestration — **frozen** | Orchestrator | `core/schema.py`, `core/pipeline.py` | Pydantic models `SceneGraph` / `ObservedState` / `DiffReport` (+ `Provenance`, confidence); `run_pipeline()`, `run_from_manifest()`; artifact set | frozen — do not edit without orchestrator review |
| Fixtures — **frozen** | Orchestrator | `fixtures/make_naksa.py`, `fixtures/naksa_{base,drift,sparse}.pdf` | Synthetic vector naksa drawings; `base` reference, `drift` for diff tests, `sparse` for warning paths | frozen |
| Ingest + geometry | BACKEND-CORE | `core/ingest.py`, `core/geometry.py` | Input normalisation; `SourceKind` detection; vector segment and room helpers | in progress |
| Scene model (drawing → approved) | BACKEND-CORE | `core/model.py` | `build_scene_graph(drawing, *, scale_m_per_unit, north_deg, ai) -> SceneGraph` | in progress |
| AI provider layer | BACKEND-AI | `core/ai/` (provider, prompts, vision) | Injectable `ai` object (`.name`); `NullProvider` default; open-weight only | in progress |
| Observe (photos → as-built) | BACKEND-AI | `core/observe.py` | `to_observed_state(photos, *, known_dimension, ai, stage_hint, sidecars) -> ObservedState` | in progress |
| Diff + severity | BACKEND-DIFF | `core/diff.py` | `diff_scene(scene, observed, *, ai) -> DiffReport` | in progress |
| Report + Nepali | BACKEND-DIFF | `core/report.py`, `core/nepali.py` | `render_html(report, scene, observed) -> str`, `render_markdown(report, scene, observed) -> str`; Nepali narration | in progress |
| Web UI | FRONTEND-WEB | `web/app.py`, `web/templates/`, `web/static/` | HTTP: upload approved + photos → run → report page + view route | in progress |
| 2D→3D renderer | RENDER-3D | `render/adapter.py`, `render/viewer.html` | `build_view(scene, observed, report) -> dict`; viewer consumes `view.json` | in progress |
| Tests | TESTING | `tests/` | `pytest`; determinism + degraded-path coverage | in progress |
| Security + privacy | SECURITY | `core/validate.py`, `docs/SECURITY.md`, `docs/PRIVACY.md` | Upload validation; privacy stance (local-first, opt-in data) | in progress |
| Domain research | RESEARCH | `docs/research/` | Citable references for every regulatory claim (NBC, Building Act 2055, municipal bylaws) | in progress |
| Dataset tooling (stretch) | Unassigned (stretch) | `dataset/` (planned) | Annotation format + seed pairs; full public release is post-v0 | planned |
| Plan, demo script, status, changelog | PM | `docs/PLAN.md`, `docs/DEMO_SCRIPT.md`, `docs/status.md`, `CHANGELOG.md` | This document is the scope contract | written-unverified (author format check only) |

> Statuses for parallel workstreams are the PM's snapshot of assignment and on-disk state — **not verification**. No workstream is verified in this snapshot; see `docs/status.md` for the honest board.

## 4. Critical path

The critical path runs through whatever the demo video needs on screen:

1. **Fixture drawing parses to a valid `SceneGraph`** (BACKEND-CORE) — everything downstream is dead without it.
2. **Photos → `ObservedState`** (BACKEND-AI) — the as-built half of the money shot.
3. **`diff_scene()` produces deltas with sane severities** (BACKEND-DIFF) — the highlights.
4. **`build_view()` + viewer renders the transition** (RENDER-3D) — the money shot itself.
5. **Web flow wraps it** (FRONTEND-WEB) — so the video can show the real workflow, not a terminal.

Parallelisation rules that keep this short:

- `core/diff.py` can be built against hand-written `SceneGraph` / `ObservedState` objects (the schema is frozen) before `observe.py` lands — mock-first keeps two workstreams parallel.
- The viewer can be built against a static `view.json` produced from fixtures; it must not wait for the web UI.
- Report polish, tests, security docs and dataset tooling are off the critical path — but **not** the honesty invariants (D7), which apply from day one.
- Integration checkpoints: **M2 (Oct 14)**, **M3 (Oct 21)**, **M4 freeze (Oct 26)**. Anything not working at M4 is cut from the demo — visibly, in `docs/status.md` — never faked.

## 5. Explicitly out of scope for v0

Each of these is a deliberate cut, with the reason:

| Out of scope | Why |
|---|---|
| Raster/scan fine-tuning | Vector PDFs are the accurate path; raster is best-effort with warnings and zero accuracy claims. The dataset that would make raster good is a post-v0 release. |
| Structural calculations | Karmi compares geometry; it does not engineer. No load, seismic or safety computations, ever — that stays with a licensed engineer. |
| Multi-floor | Single-floor residential only in v0; a second storey multiplies the extraction problem. |
| Mobile app | Web only. |
| Accounts / auth / multi-user | Single-user local tool; no login, no stored profiles. |
| Cloud hosting / SaaS | Runs on the demo machine; no deployment pipeline, no external storage. |
| Absolute-dimension claims from photos | Approximate + confidence, always; a photo alone cannot give millimetres and we never pretend otherwise. |
| Legal determinations | No "violation" verdicts, no municipality integration, no compliance certification. Outputs are *items to verify*. |
| Closed AI APIs | Hard rule, not just for v0: open-weight only, including auxiliary calls (challenge eligibility). |
| Full annotated dataset release | v0 ships fixtures + the annotation plan; the public release is post-v0 (needs consent flows and careful anonymisation). |

## 6. Risk register

Likelihood/impact are for the v0 window. "Trigger" = the signal that the mitigation must activate.

| Risk | Likelihood | Impact | Mitigation | Trigger |
|---|---|---|---|---|
| Raster drawings parse badly | High | Medium | Vector-first; refuse-and-request-better-copy; raster behind explicit warnings + confidence downgrade; never guess | Parse warnings on a raster input exceed threshold in testing, or any user uploads a scan |
| Photos cannot give absolute dimensions | Certain (physics) | Medium | Scale references + optional user-supplied known dimension; confidence on every number; degrade to qualitative comparison when scale is missing; verify-list routing | No scale reference detected in a photo set, or scale confidence below 0.5 |
| A wrong regulatory number could mislead a homeowner | Medium | High | Every regulatory claim cites a source (RESEARCH); no number ships without a citation; "verify" language, never "violates"; when in doubt, cut the number | Any uncited number found in report copy, viewer text or demo script |
| The demo depends on synthetic data | High (privacy forbids real naksa) | Medium | Say it out loud in the video; fixtures are structurally realistic; pursue a consented real-photo set; never present synthetic as real | No consented real photo set by Oct 20 → lock the synthetic-only narrative |
| Scope creep | Medium | High | This document is the contract; §5 out-of-scope list; new work needs an owner and a trade (something is dropped); status board shows every addition | Any new file or feature not in the §3 table |
| Diff engine produces a false "difference" that worries a homeowner | Medium | High | Confidence thresholds gate severity; low-confidence → verify list; `matched`/`unverifiable` statuses; base-vs-base control run as a regression test; "items to verify" framing | Any high-severity delta with confidence below 0.6, or a false positive on the control run |
| Frozen schema drifts (parallel work diverges) | Medium | High | `core/schema.py` is frozen; changes only via orchestrator review; modules import, never redefine; contract tests | Any file redefining schema types or changing field names |
| Integration time (many parallel streams, one repo) | Medium | High | Small frozen interfaces; mock-first for diff/report/viewer; M2/M3/M4 checkpoints; degrade-never-crash pipeline | Any workstream silent at a checkpoint |
| Local model not runnable on the demo machine | Medium | Medium | `NullProvider` keeps the pipeline alive; pin the exact model + quant; record AI beats on a working machine; optional hosted open-weight fallback | Model run over 60 s per image or OOM during rehearsal |
| Privacy/PII leaks into repo or video | Medium | High | Local-first processing; synthetic fixtures; consent + anonymisation for any real photo; SECURITY/PRIVACY docs; pre-upload scan of video frames | Any real name, address, face or signature visible in a frame or file |

## 7. Milestones

Aligned to the Frogtoberfest timeline (week boundaries per organisers; internal checkpoints chosen by us).

| Milestone | Window | Exit criteria | Status |
|---|---|---|---|
| M0 — Registration + kickoff | Sep 16–29 (registration) · Oct 1 (kickoff) | Team registered; public repo exists; kickoff webinar attended | done |
| M1 — Contract + fixtures (Week 1, Explore) | Oct 1–7 | `core/schema.py` + `core/pipeline.py` frozen; fixtures generated; this plan, demo script, status board and changelog written; workstreams staffed | done for frozen items; docs written 2026-10-04 (unverified) |
| M2 — Vertical slice (Week 2, Build) | by Oct 14 | Fixture drawing → `scene.json` → diff → `report.json` runs end to end offline (NullProvider); web upload shell serves; test skeleton running | in progress |
| M3 — Reality + money shot (Week 3, Build) | by Oct 21 | Photos → `observed.json` with confidences; viewer plays approved→as-built transition from `view.json`; at least 3 visible differences on the drift scenario; core tests green | in progress |
| M4 — Feature freeze + video (Week 4, Showcase) | by Oct 26 | All D1–D8 checks pass on the demo machine; demo video recorded; docs + AI_USAGE + SECURITY/PRIVACY complete; CHANGELOG updated | not started |
| M5 — Submit + shortlist (Week 4) | by Oct 29 | Submission submitted; repo clean; pitch rehearsed; buffer held for fixes | not started |
| M6 — Demo Day | Oct 30, Kathmandu | Top-5 live demo; at least one team member present in Kathmandu valley | not started |

## 8. Ground rules (binding)

1. **`core/schema.py` is the contract.** Field names and semantics do not change without orchestrator review and an update to `docs/architecture.md`.
2. **One writer per file.** Do not edit another workstream's files; integration edits belong to the orchestrator.
3. **Degrade, never crash.** A missing stage produces a warning and a valid degraded result.
4. **Honesty invariants:** confidence travels with every extracted value; low-confidence routes to the verify list; the words "violation"/"violates" never ship; synthetic data is labelled.
5. **Open-weight only** — vision, text, embeddings, auxiliary calls. Nothing closed, nothing paid.
6. **Nothing enters the demo path unverified.** The owner runs their own check and records it in `docs/status.md` before a component is called done.

### Open decisions

| Decision | Owner | Deadline | Default if undecided |
|---|---|---|---|
| Demo as-built data story: photo set vs drift-drawing stand-in | Orchestrator + PM | Oct 22 | Drift-drawing stand-in, labelled on screen |
| Local model + quant for extraction A/B | BACKEND-AI | Oct 18 | Smallest Qwen2.5-VL that fits the demo laptop; NullProvider for pipeline tests |
| Regulatory citations for any number shown in the demo | RESEARCH | Oct 22 | Cut the number from the script |

## 9. For a future contributor — start here

1. Read `core/schema.py` (10 minutes). It is the vocabulary: scene graph, observed state, delta, verify list, provenance.
2. Read `core/pipeline.py` — how the five stages wire together and the exact artifact set each run produces.
3. Generate a fixture: `python fixtures/make_naksa.py --variant base` (also `drift`, `sparse`).
4. `docs/status.md` says what exists and what is verified; this file says what v0 promises; `docs/architecture.md` says how it is designed.
5. Run `pytest -q`, then run the pipeline on the fixtures. If something is broken, fix it and update the status board — that is the culture of this repo.