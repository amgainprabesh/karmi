#!/usr/bin/env python3
"""Karmi Definition-of-Done checker — PLAN.md §2, D1–D8, as runnable checks.

``scripts/check_all.py`` answers "is the repo healthy?". This script answers the
stricter question in ``docs/PLAN.md``: *would a stranger who clones the repo see
every v0 promise hold?* Each row is one outcome from the plan, checked the way
the plan's "How a stranger checks it" column describes — by running the code,
never by reading it.

  D1  end-to-end run writes all seven artifacts; every JSON parses and
      round-trips through the frozen schema
  D2  the difference is real: on the demo scenario (approved base drawing vs
      drifted site evidence) at least 3 elements differ, the verify list is
      non-empty, ``summary`` equals a fresh ``recount()`` — and a base-vs-base
      CONTROL run (perfect evidence) produces zero differences
  D3  the 3D view is data-driven: highlighted elements correspond exactly to
      differs/missing/unexpected deltas, and removing a delta removes its
      highlight; the viewer loads ``view.json`` and hardcodes no house
  D4  the web workflow: upload -> report page (Nepali renders) -> 3D view;
      uploading without photos degrades to a visible warning, never a 5xx
  D5  AI is load-bearing and disclosed: with no AI and no measurements the
      observed state has zero elements plus warnings; every "file -> function"
      named in AI_USAGE.md exists in the code
  D6  tests green (pytest) + diff determinism (same inputs -> identical deltas)
  D7  honesty invariants: every delta carries confidence + reason; no
      high-severity delta below confidence 0.6; every non-matched delta is on
      the verify list; no "violation" wording in any rendered report
  D8  judge-facing docs exist; the demo video is a MANUAL item (reported, not
      faked)

Usage (from the repository root, with the project venv)::

    python scripts/check_dod.py               # all checks
    python scripts/check_dod.py --skip-pytest # when the caller already ran pytest
    python scripts/check_dod.py --json        # machine-readable result

Exit code: 0 when every automatable check passes, 1 otherwise. No network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PHOTO_DIR = REPO_ROOT / "fixtures" / "photos"
PHOTO_NAMES = ("front_walls_stage.jpg", "rear_foundation_stage.jpg", "side_columns_stage.jpg")
SIDECAR_NAMES = tuple(f"{n}.json" for n in PHOTO_NAMES)
BASE_DRAWING = REPO_ROOT / "fixtures" / "naksa_base.pdf"
KNOWN_DIMENSION_M = 10.0

ARTIFACTS = ("scene.json", "observed.json", "report.json", "report.html", "report.md", "view.json", "run.json")
HIGHLIGHT_STATUSES = {"differs", "missing", "unexpected"}
MIN_DEMO_DIFFERENCES = 3          # PLAN.md M3: "at least 3 visible differences"
HIGH_SEVERITY_MIN_CONFIDENCE = 0.6  # PLAN.md risk register trigger
FORBIDDEN_WORDING = re.compile(r"(?i)\bviolat(?:e|es|ed|ion|ions|ing)\b")
#: the only sanctioned use of the word is a negation ("never a violation",
#: "not a violation", "no violation") — the honesty disclaimer itself
NEGATED_WORDING = re.compile(r"(?i)\b(?:never|not|no|without)\b[^.;:\n]{0,40}\bviolat")

JUDGE_DOCS = (
    "README.md", "docs/architecture.md", "AI_USAGE.md", "docs/PLAN.md", "docs/status.md",
    "CHANGELOG.md", "docs/SECURITY.md", "docs/PRIVACY.md", "docs/DEMO_SCRIPT.md",
)


@dataclass
class Result:
    key: str
    title: str
    ok: bool | None          # None = manual / not automatable
    detail: str
    problems: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _val(x) -> str:
    return str(getattr(x, "value", x))


def _demo_inputs() -> tuple[list[str], dict[str, str]]:
    photos = [str(PHOTO_DIR / n) for n in PHOTO_NAMES]
    sidecars = {p: str(PHOTO_DIR / s) for p, s in zip(photos, SIDECAR_NAMES)}
    return photos, sidecars


def _run_demo(out: Path):
    from core.pipeline import run_pipeline

    photos, sidecars = _demo_inputs()
    return run_pipeline(str(BASE_DRAWING), photos, out_dir=str(out),
                        known_dimension=KNOWN_DIMENSION_M, sidecars=sidecars)


def _highlighted_delta_ids(view: dict) -> tuple[set[str], set[str]]:
    """(delta ids attached to highlighted view elements, ids of highlighted scene elements)."""
    ids: set[str] = set()
    scene_ids: set[str] = set()
    for side in ("approved", "observed"):
        block = view.get(side) or {}
        for group in ("walls", "openings", "rooms", "other", "unplaced"):
            for el in block.get(group) or []:
                if str(el.get("status")) in HIGHLIGHT_STATUSES:
                    ids.update(el.get("delta_ids") or [])
                    if side == "approved":
                        scene_ids.add(str(el.get("id")))
    return ids, scene_ids


def _perfect_observation(scene):
    """An ObservedState that measures every drawn element exactly as drawn.

    The control run: if the diff engine flags anything against perfect
    evidence, it is inventing differences — the worst failure for a tool
    whose output may worry a homeowner.
    """
    from core.diff import _room_area
    from core.schema import ElementKind, ObservedElement, ObservedState, Provenance, Stage

    prov = Provenance(source="human_annotation", confidence=0.9, evidence="control run: exact drawn size")
    elements = []
    n = 0
    for w in scene.walls:
        n += 1
        (x0, y0), (x1, y1) = w.start, w.end
        length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        elements.append(ObservedElement(id=f"ctl-{n:03d}", kind=ElementKind.WALL,
                                        approx_size={"length": round(length, 4)},
                                        matches_scene_id=w.id, provenance=prov))
    for o in scene.openings:
        if o.width is None:
            continue
        n += 1
        elements.append(ObservedElement(id=f"ctl-{n:03d}", kind=ElementKind.OPENING,
                                        approx_size={"width": o.width},
                                        location_hint=f"{_val(o.kind)} on {o.wall_id}",
                                        matches_scene_id=o.id, provenance=prov))
    for r in scene.rooms:
        area = _room_area(r)
        if area is None:
            continue
        n += 1
        elements.append(ObservedElement(id=f"ctl-{n:03d}", kind=ElementKind.OTHER,
                                        approx_size={"area": area},
                                        location_hint=f"room {r.name or r.id}",
                                        matches_scene_id=r.id, provenance=prov))
    return ObservedState(stage=Stage.COMPLETE, elements=elements)


# --------------------------------------------------------------------------- #
# D1 — end-to-end run, artifacts, schema round-trip
# --------------------------------------------------------------------------- #
def check_d1(ctx: dict) -> Result:
    from core.schema import DiffReport, ObservedState, SceneGraph

    out: Path = ctx["tmp"] / "d1"
    res = _run_demo(out)
    ctx["demo"] = res
    ctx["demo_dir"] = out
    problems: list[str] = []
    if res.errors:
        problems.append("pipeline errors: " + "; ".join(res.errors))
    missing = [a for a in ARTIFACTS if not (out / a).is_file()]
    if missing:
        problems.append("missing artifacts: " + ", ".join(missing))
    parsed = 0
    for name in ARTIFACTS:
        p = out / name
        if name.endswith(".json") and p.is_file():
            try:
                json.loads(p.read_text(encoding="utf-8"))
                parsed += 1
            except json.JSONDecodeError as exc:
                problems.append(f"{name} does not parse: {exc}")
    for name, model in (("report.json", DiffReport), ("scene.json", SceneGraph), ("observed.json", ObservedState)):
        p = out / name
        if p.is_file():
            try:
                model.model_validate_json(p.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{name} does not round-trip through {model.__name__}: {exc}"[:300])
    for name in ("report.html", "report.md"):
        p = out / name
        if p.is_file() and p.stat().st_size < 500:
            problems.append(f"{name} is suspiciously small ({p.stat().st_size} bytes)")
    detail = (f"{len(ARTIFACTS) - len(missing)}/{len(ARTIFACTS)} artifacts, {parsed} JSON parsed, "
              f"schema round-trip for report/scene/observed")
    return Result("D1", "End-to-end run on the fixture set", not problems, detail, problems)


# --------------------------------------------------------------------------- #
# D2 — the difference is real, and the control run is clean
# --------------------------------------------------------------------------- #
def check_d2(ctx: dict) -> Result:
    from core.diff import diff_scene

    res = ctx["demo"]
    rep = res.report
    problems: list[str] = []
    flagged = [d for d in rep.deltas if _val(d.status) in ("differs", "missing")]
    if len(flagged) < MIN_DEMO_DIFFERENCES:
        problems.append(f"only {len(flagged)} differs/missing delta(s) on the demo scenario "
                        f"(need >= {MIN_DEMO_DIFFERENCES})")
    if not any(_val(d.severity) in ("low", "medium", "high") for d in flagged):
        problems.append("no flagged delta has severity >= low")
    if not rep.verify_list:
        problems.append("verify_list is empty")
    before = dict(rep.summary)
    after = dict(rep.model_copy(deep=True).recount().summary)
    if before != after:
        problems.append(f"summary {before} != recount() {after}")

    # control: perfect evidence must yield zero differences
    ctl_obs = _perfect_observation(res.scene)
    ctl = diff_scene(res.scene, ctl_obs)
    ctl_flagged = [d for d in ctl.deltas if _val(d.status) in HIGHLIGHT_STATUSES]
    if ctl_flagged:
        problems.append("CONTROL run (exact drawn sizes) produced differences: "
                        + "; ".join(f"{d.element}: {d.reason}" for d in ctl_flagged[:3]))
    ctl_matched = sum(1 for d in ctl.deltas if _val(d.status) == "matched")
    sev = ", ".join(f"{_val(d.severity)}:{d.scene_ref}" for d in flagged)
    detail = (f"{len(flagged)} differences ({sev}), {len(rep.verify_list)} verify items, recount OK; "
              f"control run {ctl_matched}/{len(ctl.deltas)} matched, {len(ctl_flagged)} false positives")
    return Result("D2", "The difference is real, not decorative", not problems, detail, problems)


# --------------------------------------------------------------------------- #
# D3 — the 2D->3D view is data-driven
# --------------------------------------------------------------------------- #
def check_d3(ctx: dict) -> Result:
    from render.adapter import build_view

    res = ctx["demo"]
    out: Path = ctx["demo_dir"]
    problems: list[str] = []
    view = json.loads((out / "view.json").read_text(encoding="utf-8"))
    expected = {d.id for d in res.report.deltas if _val(d.status) in HIGHLIGHT_STATUSES}
    got, _ = _highlighted_delta_ids(view)
    if got != expected:
        problems.append(f"highlighted delta ids {sorted(got)} != differs/missing/unexpected {sorted(expected)}")

    # remove one flagged delta -> its highlight must disappear
    removed_note = "no flagged delta to remove"
    victim = next((d for d in res.report.deltas if _val(d.status) == "differs" and d.scene_ref), None)
    if victim is not None:
        scratch = res.report.model_copy(deep=True)
        scratch.deltas = [d for d in scratch.deltas if d.id != victim.id]
        scratch.verify_list = [v for v in scratch.verify_list if v.delta_ref != victim.id]
        scratch.recount()
        view2 = build_view(res.scene, res.observed, scratch)
        got2, scene_ids2 = _highlighted_delta_ids(view2)
        if victim.id in got2 or victim.scene_ref in scene_ids2:
            problems.append(f"removing delta {victim.id} did not remove the highlight on {victim.scene_ref}")
        if got2 != expected - {victim.id}:
            problems.append(f"after removal, highlights {sorted(got2)} != {sorted(expected - {victim.id})}")
        removed_note = f"removing {victim.id} ({victim.scene_ref}) removed its highlight"

    viewer = (REPO_ROOT / "render" / "viewer.html").read_text(encoding="utf-8")
    if "view.json" not in viewer:
        problems.append("render/viewer.html never loads view.json")
    scene_names = {r.name for r in res.scene.rooms if r.name}
    hardcoded = sorted(n for n in scene_names if n in viewer)
    if hardcoded:
        problems.append(f"viewer.html hardcodes fixture room names: {hardcoded}")
    detail = f"{len(got)} highlighted == {len(expected)} flagged deltas; {removed_note}; viewer reads view.json"
    return Result("D3", "The 2D->3D view is data-driven", not problems, detail, problems)


# --------------------------------------------------------------------------- #
# D4 — web workflow, including the degraded path
# --------------------------------------------------------------------------- #
def check_d4(ctx: dict) -> Result:
    runs_dir = ctx["tmp"] / "web-runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    os.environ["KARMI_RUNS_DIR"] = str(runs_dir)
    try:
        from fastapi.testclient import TestClient

        import web.app as webapp
    except Exception as exc:  # noqa: BLE001
        return Result("D4", "The web workflow works", False, f"cannot import the web app: {exc}")
    if Path(webapp.RUNS_DIR).resolve() != runs_dir.resolve():
        return Result("D4", "The web workflow works", False,
                      "web.app was imported before KARMI_RUNS_DIR was set — refusing to write runs into the repo")

    problems: list[str] = []
    client = TestClient(webapp.app)
    files = [("drawing", (BASE_DRAWING.name, BASE_DRAWING.read_bytes(), "application/pdf"))]
    files += [("photos", (n, (PHOTO_DIR / n).read_bytes(), "image/jpeg")) for n in PHOTO_NAMES]
    files += [("photos", (n, (PHOTO_DIR / n).read_bytes(), "application/json")) for n in SIDECAR_NAMES]
    r = client.post("/api/analyze", files=files, data={"known_dimension": str(KNOWN_DIMENSION_M)})
    payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    run_id = payload.get("run_id")
    if r.status_code != 200 or not payload.get("ok") or not run_id:
        problems.append(f"full upload -> HTTP {r.status_code}: {str(payload)[:200]}")
    else:
        page = client.get(f"/run/{run_id}")
        if page.status_code != 200:
            problems.append(f"GET /run/<id> -> {page.status_code}")
        elif not re.search(r"[\u0900-\u097F]", page.text):
            problems.append("run page contains no Devanagari — Nepali did not render")
        elif 'id="verify-list"' not in page.text:
            problems.append("run page has no verify list")
        viewer = client.get(f"/viewer/{run_id}")
        view = client.get(f"/viewer/{run_id}/view.json")
        if viewer.status_code != 200 or view.status_code != 200:
            problems.append(f"3D view routes -> viewer {viewer.status_code}, view.json {view.status_code}")

    # degraded path: drawing only, no photos
    r2 = client.post("/api/analyze", files=[files[0]])
    p2 = r2.json() if r2.headers.get("content-type", "").startswith("application/json") else {}
    degraded_note = f"no-photo upload -> HTTP {r2.status_code}"
    if r2.status_code >= 500:
        problems.append(f"upload without photos -> HTTP {r2.status_code} (must degrade, not crash)")
    elif p2.get("run_id"):
        page2 = client.get(f"/run/{p2['run_id']}")
        warned = bool(p2.get("warnings")) or "warning" in page2.text.lower()
        if not warned:
            problems.append("upload without photos produced no visible warning")
        degraded_note += f", {len(p2.get('warnings') or [])} warning(s) shown"
    elif not (p2.get("error") or "").strip():
        problems.append("upload without photos was rejected without a message")
    else:
        degraded_note += f", friendly message: {p2.get('error')[:60]!r}"
    detail = f"upload -> report (Nepali) -> 3D view OK; {degraded_note}"
    return Result("D4", "The web workflow works without instructions", not problems, detail, problems)


# --------------------------------------------------------------------------- #
# D5 — AI load-bearing + disclosed
# --------------------------------------------------------------------------- #
def check_d5(ctx: dict) -> Result:
    from core.observe import to_observed_state

    problems: list[str] = []
    bare = ctx["tmp"] / "bare-photos"
    bare.mkdir(parents=True, exist_ok=True)
    for n in PHOTO_NAMES:  # photos WITHOUT their sidecars
        shutil.copy2(PHOTO_DIR / n, bare / n)
    obs = to_observed_state([str(bare / n) for n in PHOTO_NAMES], ai=None)
    if obs.elements:
        problems.append(f"no AI + no measurements still produced {len(obs.elements)} element(s) — fabricated")
    if not obs.warnings:
        problems.append("no AI + no measurements produced no warning")

    usage = (REPO_ROOT / "AI_USAGE.md").read_text(encoding="utf-8")
    implemented = usage.split("## Planned")[0]
    refs = re.findall(r"`(core/[\w/]+\.py)`\s*→\s*`(\w+)\(\)`", implemented)
    if not refs:
        problems.append("AI_USAGE.md names no `file` → `function()` call sites")
    for rel, fn in refs:
        src = REPO_ROOT / rel
        if not src.is_file():
            problems.append(f"AI_USAGE.md names {rel}, which does not exist")
        elif not re.search(rf"^def {fn}\(", src.read_text(encoding="utf-8"), re.M):
            problems.append(f"AI_USAGE.md names {rel} → {fn}(), which is not defined there")
    detail = (f"no-AI observe: {len(obs.elements)} elements, {len(obs.warnings)} warning(s); "
              f"{len(refs)} AI_USAGE call sites exist in code")
    return Result("D5", "AI is load-bearing and disclosed", not problems, detail, problems)


# --------------------------------------------------------------------------- #
# D6 — tests green + determinism
# --------------------------------------------------------------------------- #
def check_d6(ctx: dict) -> Result:
    from core.diff import diff_scene

    problems: list[str] = []
    pytest_note = "pytest skipped (--skip-pytest)"
    if not ctx["skip_pytest"]:
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=str(REPO_ROOT),
                              capture_output=True, text=True, timeout=900)
        lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        pytest_note = "pytest: " + (lines[-1] if lines else "(no output)")
        if proc.returncode != 0:
            problems.append(pytest_note)

    res = ctx["demo"]
    a = diff_scene(res.scene, res.observed)
    b = diff_scene(res.scene, res.observed)
    dump = lambda r: json.dumps([d.model_dump(mode="json") for d in r.deltas], sort_keys=True)  # noqa: E731
    if dump(a) != dump(b):
        problems.append("diff_scene is not deterministic: two runs on the same inputs differ")
    res2 = _run_demo(ctx["tmp"] / "d6-rerun")
    if dump(res2.report) != dump(res.report):
        problems.append("two full pipeline runs on the same inputs produced different deltas")
    detail = f"{pytest_note}; diff + full pipeline deterministic across reruns"
    return Result("D6", "Tests are green and meaningful", not problems, detail, problems)


# --------------------------------------------------------------------------- #
# D7 — honesty invariants
# --------------------------------------------------------------------------- #
def check_d7(ctx: dict) -> Result:
    problems: list[str] = []
    reports = [("demo", ctx["demo"].report, ctx["demo_dir"])]
    from core.pipeline import run_pipeline

    for variant in ("drift", "sparse"):
        out = ctx["tmp"] / f"d7-{variant}"
        photos, sidecars = _demo_inputs()
        r = run_pipeline(str(REPO_ROOT / "fixtures" / f"naksa_{variant}.pdf"), photos, out_dir=str(out),
                         known_dimension=KNOWN_DIMENSION_M, sidecars=sidecars)
        reports.append((variant, r.report, out))

    n_deltas = 0
    for label, rep, out in reports:
        on_list = {v.delta_ref for v in rep.verify_list}
        for d in rep.deltas:
            n_deltas += 1
            if d.confidence is None or not (d.reason or "").strip():
                problems.append(f"[{label}] {d.id} lacks confidence or reason")
            if _val(d.severity) == "high" and d.confidence < HIGH_SEVERITY_MIN_CONFIDENCE:
                problems.append(f"[{label}] {d.id} is HIGH with confidence {d.confidence:.2f}")
            if _val(d.status) != "matched" and d.id not in on_list:
                problems.append(f"[{label}] {d.id} ({_val(d.status)}) is asserted but not on the verify list")
        for name in ("report.html", "report.md", "report.json"):
            p = out / name
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8")
            for m in FORBIDDEN_WORDING.finditer(text):
                window = text[max(0, m.start() - 60):m.end()]
                if not NEGATED_WORDING.search(window):
                    problems.append(f"[{label}] {name} uses accusatory wording: "
                                    f"…{text[max(0, m.start() - 40):m.end() + 20]!r}…")
                    break
    detail = (f"{n_deltas} deltas across {len(reports)} runs: confidence + reason on all, "
              f"no low-confidence HIGH, every non-match on the verify list, no 'violation' wording")
    return Result("D7", "Honesty invariants hold", not problems, detail, problems)


# --------------------------------------------------------------------------- #
# D8 — docs exist; video is manual
# --------------------------------------------------------------------------- #
def check_d8(ctx: dict) -> Result:
    missing = [d for d in JUDGE_DOCS if not (REPO_ROOT / d).is_file()]
    if missing:
        return Result("D8", "Docs and video are judge-complete", False,
                      "missing docs: " + ", ".join(missing), [f"missing {m}" for m in missing])
    return Result("D8", "Docs and video are judge-complete", None,
                  f"{len(JUDGE_DOCS)} judge-facing docs present; demo video (< 3:00) is a MANUAL check "
                  f"— record it from docs/DEMO_SCRIPT.md")


CHECKS = (check_d1, check_d2, check_d3, check_d4, check_d5, check_d6, check_d7, check_d8)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="python scripts/check_dod.py", description=__doc__.split("\n")[0])
    ap.add_argument("--skip-pytest", action="store_true", help="do not run pytest inside D6")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    results: list[Result] = []
    with tempfile.TemporaryDirectory(prefix="karmi-dod-") as tmp:
        ctx = {"tmp": Path(tmp), "skip_pytest": args.skip_pytest}
        for fn in CHECKS:
            key = fn.__name__.split("_")[-1].upper()
            try:
                results.append(fn(ctx))
            except Exception as exc:  # noqa: BLE001 — a crash in a check is a failed check
                results.append(Result(key, fn.__name__, False, f"check crashed: {type(exc).__name__}: {exc}",
                                      [traceback.format_exc()]))
                if key == "D1":  # everything else depends on the demo run
                    break
    elapsed = time.perf_counter() - t0
    failed = [r for r in results if r.ok is False]

    if args.json:
        print(json.dumps({"ok": not failed, "elapsed_s": round(elapsed, 1),
                          "results": [r.__dict__ for r in results]}, ensure_ascii=False, indent=2))
        return 0 if not failed else 1

    print("Karmi — Definition of Done (docs/PLAN.md §2)")
    print("=" * 72)
    for r in results:
        mark = "PASS" if r.ok else ("MANUAL" if r.ok is None else "FAIL")
        print(f"{r.key}  {mark:<6}  {r.title}")
        print(f"            {r.detail}")
        for p in r.problems[:8]:
            print(f"            ! {p}")
    print()
    auto = [r for r in results if r.ok is not None]
    manual = [r for r in results if r.ok is None]
    verdict = "PASS" if not failed else "FAIL"
    print(f"DoD: {verdict} — {len(auto) - len(failed)}/{len(auto)} automated checks passed, "
          f"{len(manual)} manual ({elapsed:.1f}s)")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
