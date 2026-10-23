# Karmi Testing Guide & Pre-Demo Checklist

This document describes Karmi's testing strategy, verification commands, and the manual checklist required before demoing or releasing.

---

## 1. Testing Architecture & Layers

Karmi's testing strategy spans unit tests, integration pipelines, regulatory and honesty contracts, quality gates, and automated mutation testing:

```
+-------------------------------------------------------------------------+
|                              Manual Checklist                            |
|             (Visual 3D inspection, Devanagari font, A4 printouts)        |
+-------------------------------------------------------------------------+
                                    |
+-------------------------------------------------------------------------+
|                  Definition-of-Done (DoD) & Regression                  |
|    (scripts/check_dod.py, test_demo_regression.py, control run zero-diff)|
+-------------------------------------------------------------------------+
                                    |
+-------------------------------------------------------------------------+
|                         Repo Quality Gate                                |
|    (scripts/check_all.py: Pytest, Pipelines, Imports, Web, Privacy)     |
+-------------------------------------------------------------------------+
                                    |
+-------------------------------------------------------------------------+
|                       End-to-End & Web Smoke                             |
|               (scripts/smoke_web.py: Real uvicorn HTTP test)             |
+-------------------------------------------------------------------------+
                                    |
+-------------------------------------------------------------------------+
|                    Unit Tests & Safety Guards                            |
|    (Schema, Diff, Nepali, Narration guard, Raster, Ingest, Dataset)      |
+-------------------------------------------------------------------------+
```

---

## 2. Test Commands Reference

### Fast test suite (sub-5s feedback)
Runs all unit and integration tests, skipping slow PDF raster rendering and complete multipart web uploads:
```bash
python -m pytest -q -m "not slow"
```

### Full test suite
Runs all 155 tests (including `dataset/tests/`):
```bash
python -m pytest -q
```

### Coverage baseline check
Computes line coverage across `core`, `render`, `web`, and `dataset`:
```bash
python -m pytest --cov --cov-report=term-missing -q
```

### Quality gate (7 checks)
Validates pytest, pipelines across base/drift/sparse, 21 package imports, web app routes, and local filesystem privacy:
```bash
python scripts/check_all.py
```
Or with coverage check enabled:
```bash
python scripts/check_all.py --coverage
```

### Definition-of-Done verification (PLAN.md §2, D1–D8)
Verifies all 7 automated DoD checks and lists the manual check:
```bash
python scripts/check_dod.py
```

### Web smoke test
Spawns a real background web server, exercises multipart upload with sidecars, confirms Nepali HTML rendering and JSON consistency, and terminates cleanly:
```bash
python scripts/smoke_web.py
```

### Mutation spot-check
Applies 6 intentional regressions to verify that tests immediately catch defects in severity thresholds, confidence caps, coverage guards, narration sanitization, Nepali digit translation, and traversal prevention:
```bash
python scripts/mutation_spotcheck.py
```

---

## 3. Pre-Demo Manual Checklist (Frogtoberfest Demo Day)

Complete these visual and physical checks on the actual demo laptop:

- [ ] **3D Viewer WebGL Rendering**:
  - Open `runs/demo/view.json` in `render/viewer.html` via `python scripts/demo.py --open` or `http://localhost:8000/viewer/<run_id>`.
  - Confirm the 3D building geometry renders without WebGL warnings or console errors.
  - Test the view mode buttons: **Approved**, **As-Built**, and **Diff**.
  - In **Diff** mode, confirm that the differing elements (e.g. front window `O8`, side door `O4`, bedroom `R1`) are distinctly highlighted in red.
  - Click on elements to ensure the inspection panel slides out and shows measurements in both English and Nepali.

- [ ] **Devanagari Font & System Rendering**:
  - Inspect the run page (`/run/<id>`) and report page (`report.html`).
  - Verify there are no missing glyphs, tofu boxes (``), or overlapping Devanagari conjuncts.

- [ ] **A4 Print Layout**:
  - Open `report.html` in the browser, press `Ctrl+P` (Print to PDF / Print).
  - Select A4 portrait.
  - Verify that page breaks occur cleanly between the header, summary statistics, items to verify, and notes.
  - Ensure margins and tables survive municipal office printing.

- [ ] **Offline Execution Guarantee**:
  - Disconnect Wi-Fi and ethernet.
  - Run:
    ```bash
    python scripts/demo.py --out runs/offline_demo
    ```
  - Verify that the run finishes in under 2 seconds with `OK — no errors`, and all artifacts are produced with zero network dependencies.

- [ ] **Demo Video Duration**:
  - Rehearse the presentation following `docs/DEMO_SCRIPT.md`.
  - Time the walkthrough: must be strictly under 3 minutes (180 seconds).
