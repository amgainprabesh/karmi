# Karmi — Kanban & Sprint Board

> **Frameworks:** Agile Scrum + Kanban (WIP limits) + Extreme Programming (XP: TDD, continuous testing, mutation spotcheck, simple design)  
> **Final Sprint:** Sprint 4 — Interactive 3D Measurement & Bilingual Overlay Inspector  
> **Definition of Done:** All acceptance criteria satisfied; unit tests written first (TDD) and green; zero "violation" wording; 100% offline fallback preserved; quality gate (`scripts/check_all.py`), DoD check (`scripts/check_dod.py`), web smoke (`scripts/smoke_web.py`), and mutation tests (`scripts/mutation_spotcheck.py`) passing.

---

## Kanban Workflow Policies & WIP Limits

| Stage | Policy / Entry Criteria | WIP Limit |
|---|---|:---:|
| **Backlog** | Stories prioritized, acceptance criteria defined with honesty invariants. | ∞ |
| **In Progress** | TDD test written first (Red state confirmed); active minimal code implementation. | **1** |
| **Review & Test** | All unit tests green; quality gate, DoD checks, mutation spotcheck passing. | **1** |
| **Done** | Merged into main codebase; full regression passing; docs updated. | ∞ |

---

## Live Board

```
+-----------------------------------------------------------------------------------------+
| BACKLOG                                                                                 |
+-----------------------------------------------------------------------------------------+
| (empty — all 5 iteration cycles completed)                                              |
+-----------------------------------------------------------------------------------------+
| IN PROGRESS [WIP: 0/1]                                                                  |
+-----------------------------------------------------------------------------------------+
| (empty)                                                                                 |
+-----------------------------------------------------------------------------------------+
| REVIEW & TEST [WIP: 0/1]                                                                |
+-----------------------------------------------------------------------------------------+
| (empty)                                                                                 |
+-----------------------------------------------------------------------------------------+
| DONE                                                                                    |
+-----------------------------------------------------------------------------------------+
| [STORY-8] Interactive 3D Measurement & Bilingual Overlay Inspector (TDD green, 3/3)     |
| [STORY-7] AI Vision Structured Schema & Multi-Photo Consensus (TDD green, 5/5 passed)   |
| [STORY-6] Raster & Blueprint Extractor Calibration & Tolerance Tuning (TDD green, 5/5)  |
| [STORY-5] Printable Bilingual Report Document & PDF Exporter (TDD green, Gate 7/7, DoD) |
| [STORY-4] Municipal Bylaws, Setbacks, Ground Coverage & FAR Engine (TDD green, 7/7)     |
| [STORY-3] Web UI Interactive Export & 3D Inspector Deep-Linking (TDD green, 5/5 passed) |
| [STORY-2] Open-Weight AI Resiliency, Health Diagnostics & Fallback Chaining (TDD green) |
| [STORY-1] NBC 206 Regulatory Conformance Verification Engine (TDD green, Gate 7/7, DoD) |
| [BASELINE] Quality gate verified 7/7, DoD verified 7/7 automated, test suite baseline    |
+-----------------------------------------------------------------------------------------+
```

---

## User Stories & Acceptance Criteria

### [STORY-1] NBC 206 Regulatory Conformance Verification Engine
- **ID:** KARMI-S1-REGULATORY
- **Sprint:** Sprint 1 | **Status:** `DONE`
- **Verification:** `tests/test_regulatory.py` (6/6 passed); `check_all.py` (7/7 passed); zero "violation" phrasing; NBC 206 §2.2.1/§3.2.2/§3.3 citations active.

---

### [STORY-2] Open-Weight AI Resiliency, Health Diagnostics & Fallback Chaining
- **ID:** KARMI-S2-AI-RESILIENCE
- **Sprint:** Sprint 1 | **Status:** `DONE`
- **Verification:** `tests/test_ai_provider_resilience.py` (8/8 passed); `diagnose()` across Null/Ollama/OpenAICompat/Fallback providers; `FallbackProvider` transparent degradation; `with_retry` backoff; open-weight allowlist preserved.

---

### [STORY-3] Web UI Interactive Export & 3D Inspector Deep-Linking
- **ID:** KARMI-S3-WEB-3D-POLISH
- **Sprint:** Sprint 1 | **Status:** `DONE`
- **Verification:** `tests/test_web_export.py` (5/5 passed); direct download HTML and JSON endpoints active; `viewer.html` parses `?focus=` search params to zoom and highlight diff elements; web smoke test (7/7 passed).

---

### [STORY-4] Municipal Building Bylaws, Setbacks, Ground Coverage & FAR Engine
- **ID:** KARMI-S2-MUNICIPAL
- **Sprint:** Sprint 2 (Cycle 1) | **Status:** `DONE`
- **Verification:** `tests/test_municipal.py` (7/7 passed); profiles for National Baseline (Basic By-laws 2072), Kathmandu Valley (KVDA), Kirtipur, Pokhara; front/side/rear setbacks with blank wall exemptions; ground coverage & FAR advisory checks; zero "violation" phrasing.

---

### [STORY-5] Printable Bilingual Report Document & PDF Exporter
- **ID:** KARMI-S2-PDF-EXPORT
- **Sprint:** Sprint 2 (Cycle 2) | **Status:** `DONE`
- **Verification:** `tests/test_pdf_export.py` (3/3 passed); `core/pdf_export.py` generating print-optimized HTML documents with `@media print`, physical checkboxes `[ ]`, tripartite sign-off blocks (mason, homeowner, engineer), and `/run/{run_id}/export/print` web route.

---

### [STORY-6] Raster & Blueprint Extractor Calibration & Tolerance Tuning
- **ID:** KARMI-S3-RASTER-CALIBRATION
- **Sprint:** Sprint 3 (Cycle 3) | **Status:** `DONE`
- **Verification:** `tests/test_raster_calibration.py` (5/5 passed); `detect_blueprint_polarity` auto-recovers inverted ammonia blueprints; `calibrate_tolerances` scales pixel extraction thresholds with rendering DPI; `blueprint_quality_score` provides structured quality grading ('A'-'D') and homeowner advice.

---

### [STORY-7] AI Vision Structured Schema & Multi-Photo Consensus
- **ID:** KARMI-S3-AI-CONSENSUS
- **Sprint:** Sprint 3 (Cycle 4) | **Status:** `DONE`
- **Verification:** `tests/test_ai_vision_schema.py` (5/5 passed); `PhotoElement` perspective & occlusion dampening; `multi_photo_consensus` stage voting, discrepancy detection, and element clustering with corroboration bonuses capped at 0.70.

---

### [STORY-8] Interactive 3D Measurement & Bilingual Overlay Inspector
- **ID:** KARMI-S4-VIEWER-MEASURE
- **Sprint:** Sprint 4 (Cycle 5) | **Status:** `DONE`
- **Verification:** `tests/test_viewer_enhancements.py` (3/3 passed); interactive distance ruler (`#btn-measure`) computing real-world distances in meters and feet; bilingual HUD toggle (`#btn-lang`); regulatory & municipal metadata forwarded via `render/adapter.py`.

---

## Iteration Retrospectives (Inspect & Adapt)

### Retrospective — Sprint 1 to Sprint 4 (5 Consecutive Iterations)
1. **Extreme Programming (XP) Discipline:**
   - **100% Test-Driven Development (TDD):** Every single story began by creating the test file (`test_municipal.py`, `test_pdf_export.py`, `test_raster_calibration.py`, `test_ai_vision_schema.py`, `test_viewer_enhancements.py`), verifying the Red state, and implementing minimal code to achieve Green.
   - **Continuous Regression Testing:** Automated test suite expanded from **155 to 197 passing tests** (192 fast tests running in ~5.1s).
   - **Mutation Testing:** 6/6 mutations killed on every release gate (`scripts/mutation_spotcheck.py`).
   - **Quality Gate:** 7/7 checks consistently passing (`scripts/check_all.py`).
   - **Definition of Done:** 7/7 automated checks passing (`scripts/check_dod.py`).
2. **Kanban Flow & Zero Inventory Waste:**
   - Strict WIP Limit of 1 was maintained during development; stories moved cleanly from Backlog -> In Progress -> Review & Test -> Done.
3. **Product Honesty & Localization:**
   - Preserved zero "violation" phrasing across all new engines (municipal bylaw checks, printable field reports, AI vision consensus, and 3D viewer ruler).
   - Preserved 100% offline functionality across both CAD vector and blueprint scan paths.
