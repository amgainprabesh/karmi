# `scripts/` — one-command paths for Karmi

Four small scripts that make the project easy to run, demo and check without
reading any source. Everything here is offline: no network, no GPU, no API key,
no AI model.

**Requirements: nothing but the project venv.** From the repository root:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt   # .venv/bin/python on macOS/Linux
```

Then run any script with that interpreter — e.g.
`.venv/Scripts/python.exe scripts/demo.py` on Windows, `.venv/bin/python scripts/demo.py`
on macOS/Linux, or plain `python scripts/demo.py` with the venv activated.
The scripts resolve the repository root themselves, so the working directory
does not matter; fixture paths are always found relative to the repo root.

---

## `scripts/demo.py` — the whole product, one command

Runs the full pipeline on the sample naksa drawing (`fixtures/naksa_base.pdf`)
with the three sample site photos plus the hand-measurement sidecar
(`fixtures/photos/front_walls_stage.jpg.json`) and `known_dimension=10.0`.
Writes every artifact to `runs/demo/` (gitignored) and prints a presentable
summary: severity counts, the headline finding in English **and** Nepali, the
coverage/limits lines, and the path of every file it wrote. It also writes
`runs/demo/DEMO.md`, a short walkthrough of what the run shows and what the
honest limits are.

```bash
python scripts/demo.py                 # full run + printed summary + runs/demo/DEMO.md
python scripts/demo.py --out runs/x    # write somewhere else
python scripts/demo.py --open          # ... and open report.html in the default browser
python scripts/demo.py --json          # machine-readable summary on stdout only
```

Expected output shape (human mode):

```
Karmi demo — approved naksa vs site evidence, fully offline
==============================================================
drawing   : fixtures/naksa_base.pdf
photos    : 3  (front_walls_stage.jpg, rear_foundation_stage.jpg, side_columns_stage.jpg)
sidecar   : fixtures/photos/front_walls_stage.jpg.json  (hand measurements)
known dim : 10.0 m
out dir   : runs/demo
engine    : no AI · no network · deterministic

Run       : OK — no errors  (scene 17 ms, observe 70 ms, ...)
Severity  : high 1 · medium 0 · low 19 · info 1
Compared  : 21 elements, 1 matched the drawing, 20 items to verify

Headline finding
--------------------------------------------------------------
  element  : window on wall W7  [d002]
  severity : high  (confidence 0.75)
  drawing  : 1.50 m
  site     : 1.00 m
  EN : According to the drawing the width of window on wall W7 is 1.50 m; ...
  NE : नक्साअनुसार झ्याल (भित्ता W7)को चौडाइ १.५ मिटर छ; ...

These are items to verify — Karmi never declares a violation.

Coverage & limits (what this run could NOT determine)
--------------------------------------------------------------
  - <one bilingual line per limit>

Artifacts written
--------------------------------------------------------------
  runs/demo/report.html
  runs/demo/report.md
  runs/demo/report.json
  runs/demo/view.json
  runs/demo/scene.json
  runs/demo/observed.json
  runs/demo/run.json
  runs/demo/DEMO.md

Read the full report: runs/demo/report.html  (re-run with --open to launch it)
```

`--json` prints a single JSON object with `ok`, `summary`, `headline`
(English + Nepali reasons), `limits`, `files`, `errors`, `warnings` and
`timings_ms`.

Exit codes: `0` clean run, `1` the pipeline reported errors or an expected
artifact is missing, `2` the fixtures are missing (wrong checkout).

---

## `scripts/check_all.py` — the single quality gate

One command that answers "is this repo healthy?". It prints a PASS/FAIL table
and exits non-zero on any failure:

1. **pytest** — runs `sys.executable -m pytest -q` and reports the real
   summary line (e.g. `53 passed in 7.4s`).
2. **pipeline** — runs the full pipeline end-to-end on all three fixture
   drawings (`naksa_base.pdf`, `naksa_drift.pdf`, `naksa_sparse.pdf`) and
   asserts each produced a report with the expected shape: no errors, a report
   object whose `summary.total` matches its delta list, a verify list and a
   non-empty limits list. `summary.total > 0` is required for base and drift.
3. **imports** — imports every module in `core/`, `render/` and `web/`;
   a broken module fails the gate with its real error text.
4. **web app** — constructs the FastAPI `app` object and asserts its route
   table contains `/`, `/healthz`, `/api/analyze` and the viewer run route —
   **without starting a server**.
5. **privacy** — scans every non-gitignored file for this machine's absolute
   paths (a Windows user-profile path such as a drive letter followed by
   `\Users\`, or the username as a path segment). A leak fails the gate.

```bash
python scripts/check_all.py
```

Expected output shape:

```
Karmi quality gate
==================================================================
repo : karmi

CHECK                              RESULT  DETAIL
----------------------------------  ------  ---------------------------------------
pytest                              PASS    53 passed in 7.4s
pipeline: naksa_base.pdf            PASS    total=21 (high=1 medium=0 low=19 info=1), verify=20
pipeline: naksa_drift.pdf           PASS    total=21 (...)
pipeline: naksa_sparse.pdf          PASS    total=21 (...)
imports: core/ render/ web/         PASS    20 modules imported cleanly
web app: construct + routes         PASS    18 routes; /, /healthz, /api/analyze and the viewer run route are present
privacy: no machine paths in repo   PASS    70 files scanned, 0 machine paths found

GATE: PASS — 7/7 checks passed (12.3s)
```

On failure the offending check's real output (pytest tail, traceback, leaked
file list) is printed under `--- output for failed check: … ---`.

Exit codes: `0` every check passed, `1` at least one failed.

---

## `scripts/smoke_web.py` — the web UI against a real server

Starts `python -m web.app` as a subprocess on a free loopback port (runs go to
a throwaway temp directory — the repository is left untouched), waits for
`/healthz` by polling with a bounded timeout (no blind sleeps), POSTs a real
fixture drawing + the three sample photos + the sidecar to `/api/analyze` as
multipart form data (via `http.client`), follows the run page, asserts the
items-to-verify list is present, cross-checks it against
`/api/report/<id>`, then shuts the server down (graceful `CTRL_BREAK` on
Windows / `SIGTERM` elsewhere; force only as a last resort). The subprocess is
always cleaned up — including when a step fails.

```bash
python scripts/smoke_web.py
```

Expected output shape:

```
Karmi web smoke test
==================================================================
[1/7] start server      : ...python.exe -m web.app  (127.0.0.1:51234, runs in ...)
[2/7] GET  /healthz        -> 200  (ready after 4 poll(s); service=karmi-web v0.1.0; ...)
[3/7] POST /api/analyze    -> 200  (run_id=20261004-..., total=21; high=1; verify_items=20; photos=3)
[4/7] GET  /run/<id>       -> 200  (html 31240 bytes)
[5/7] verify list        : present — 20 item(s) rendered ('Items to verify' + id="verify-list")
[6/7] GET  /api/report/<id> -> 200  (verify_list in JSON: 20 item(s))
[7/7] shutdown           : CTRL_BREAK (graceful) — server exited with code 3  (log: clean shutdown confirmed)
note: after a graceful stop uvicorn re-raises the shutdown signal, so the exit status is signal-style (3) — the server log confirms the clean shutdown sequence.
SMOKE TEST: PASS — every step completed against a real running server.
```

(A signal-style exit status is expected: uvicorn re-raises the shutdown signal
after a clean stop, so CTRL_BREAK reports `3` on Windows and SIGTERM reports
`-15` on Unix. The script treats the server log's clean-shutdown sequence
(`Shutting down` → `Finished server process`) as the evidence of a graceful
stop; if a forced stop was needed it says so instead.)

On any failure it prints `SMOKE TEST: FAIL` with the reason, the server log
tail, and exits non-zero after cleaning up the subprocess.

Exit codes: `0` every step succeeded, `1` otherwise.

---

## `scripts/check_dod.py` — Definition of Done checker (PLAN.md §2, D1–D8)

Verifies every outcome promised in `docs/PLAN.md` §2 as a runnable check.
Runs the base pipeline, checks schema round-trips (D1), tests that differences
are real with a zero-false-positive control run (D2), proves 3D view highlights
are data-driven by verifying delta removal clears highlights (D3), exercises
the web workflow including degraded path (D4), tests that zero AI yields zero
fabricated elements and validates `AI_USAGE.md` call sites (D5), verifies
determinism and tests (D6), enforces confidence bounds and forbidden wording
invariants (D7), and inspects judge-facing documentation presence (D8).

```bash
python scripts/check_dod.py               # run all DoD checks
python scripts/check_dod.py --skip-pytest # faster iteration
python scripts/check_dod.py --json        # JSON report
```

---

## Notes

- All scripts only need the venv from `requirements.txt`; they never
  touch the network (the smoke test talks to `127.0.0.1` only).
- `runs/demo/` and any `runs/` output are gitignored runtime artifacts.
- These scripts are read-only with respect to the source tree: they write only
  to the output directory you choose (default `runs/demo`) and to temp
  directories.