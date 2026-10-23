#!/usr/bin/env python3
"""Karmi quality gate — one command that answers "is this repo healthy?".

Checks (one PASS/FAIL row each):

  1. pytest    — runs ``sys.executable -m pytest -q`` and reports the real
                 summary line.
  2. pipeline  — runs the full pipeline end-to-end on all three fixture
                 drawings (base / drift / sparse) with the sample photos and
                 asserts each produced a report with the expected shape:
                 no errors, a report object, ``summary.total`` consistent with
                 the delta list, a verify list — and ``summary.total > 0`` for
                 base and drift.
  3. imports   — imports every module in ``core/``, ``render/`` and ``web/``;
                 a broken module fails the gate.
  4. web app   — constructs the FastAPI app object and asserts its route table
                 contains ``/``, ``/healthz``, ``/api/analyze`` and the viewer
                 run route — WITHOUT starting a server.
  5. privacy   — scans every non-gitignored file for this machine's absolute
                 paths (a Windows user-profile path, or the username as a path
                 segment). A leak fails the gate.

Exit code: 0 when every check passes, 1 when any check fails.
No network required.

Usage (from the repository root, with the project venv)::

    python scripts/check_all.py
"""

from __future__ import annotations

import getpass
import importlib
import re
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

PIPELINE_FIXTURES = ("base", "drift", "sparse")
PHOTO_NAMES = (
    "front_walls_stage.jpg",
    "rear_foundation_stage.jpg",
    "side_columns_stage.jpg",
)
SIDECAR_NAMES = tuple(f"{n}.json" for n in PHOTO_NAMES)
IMPORT_PACKAGES = ("core", "render", "web")

# dirs excluded from the privacy scan — every one of these is gitignored
# (runtime output, caches, virtualenv, git internals)
PRIVACY_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "runs", "models",
}
# file patterns that are gitignored as well (run manifests may hold user paths)
PRIVACY_SKIP_GLOBS = ("*.scene.json", "run.json", "uploads.json", ".env", "*.key", "credentials.json", ".coverage*", ".coverage")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    output: str = field(default="")  # extra text printed when the check fails


# --------------------------------------------------------------------------- #
# 1. pytest
# --------------------------------------------------------------------------- #
def check_pytest(with_cov: bool = False) -> Check:
    name = "pytest" if not with_cov else "pytest (+ cov)"
    try:
        cmd = [sys.executable, "-m", "pytest", "-q"]
        if with_cov:
            cmd.extend(["--cov", "--cov-report=term"])
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=900,
        )
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"could not run pytest: {type(exc).__name__}: {exc}")

    combined = (proc.stdout or "")
    if proc.stderr:
        combined += "\n" + proc.stderr
    lines = [ln.strip() for ln in combined.splitlines() if ln.strip()]
    summary_line = lines[-1] if lines else "(no output)"
    if proc.returncode == 0:
        return Check(name, True, summary_line)
    tail = "\n".join(lines[-30:])
    return Check(name, False, f"exit code {proc.returncode} — {summary_line}", output=tail)


# --------------------------------------------------------------------------- #
# 2. pipeline end-to-end on the three fixture drawings
# --------------------------------------------------------------------------- #
def check_pipeline(variant: str, tmp: Path) -> Check:
    name = f"pipeline: naksa_{variant}.pdf"
    try:
        from core.pipeline import run_pipeline  # lazy — a broken core must fail this check, not the gate
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"could not import core.pipeline: {type(exc).__name__}: {exc}",
                     output=traceback.format_exc())

    drawing = REPO_ROOT / "fixtures" / f"naksa_{variant}.pdf"
    photos = [str(REPO_ROOT / "fixtures" / "photos" / n) for n in PHOTO_NAMES]
    sidecars = {p: str(REPO_ROOT / "fixtures" / "photos" / s) for p, s in zip(photos, SIDECAR_NAMES)}
    if not drawing.is_file():
        return Check(name, False, f"fixture missing: {drawing}")

    try:
        res = run_pipeline(
            str(drawing), photos, out_dir=str(tmp / f"pipeline_{variant}"),
            known_dimension=10.0, sidecars=sidecars,
        )
    except Exception as exc:  # noqa: BLE001 — run_pipeline promises not to raise; if it does, that is a finding
        return Check(name, False, f"run_pipeline raised {type(exc).__name__}: {exc}",
                     output=traceback.format_exc())

    problems: list[str] = []
    if res.errors:
        problems.append("errors: " + "; ".join(res.errors))
    if res.report is None:
        problems.append("no report was produced")
        return Check(name, False, "; ".join(problems))

    rep = res.report
    total = rep.summary.get("total") if isinstance(rep.summary, dict) else None
    if not isinstance(total, int):
        problems.append(f"summary.total is not an int ({total!r})")
    elif len(rep.deltas) != total:
        problems.append(f"summary.total ({total}) != len(deltas) ({len(rep.deltas)})")
    if not isinstance(rep.verify_list, list):
        problems.append("verify_list is not a list")
    if not isinstance(rep.limits, list) or not rep.limits:
        problems.append("limits list is empty — the run must state its limits")
    if variant in ("base", "drift") and isinstance(total, int) and total <= 0:
        problems.append(f"summary.total = {total} (expected > 0)")

    detail = (
        f"total={total} (high={rep.summary.get('high')} medium={rep.summary.get('medium')} "
        f"low={rep.summary.get('low')} info={rep.summary.get('info')}), "
        f"verify={len(rep.verify_list)}"
    )
    if problems:
        detail += " — " + "; ".join(problems)
    return Check(name, not problems, detail)


# --------------------------------------------------------------------------- #
# 3. import every module in core/, render/, web/
# --------------------------------------------------------------------------- #
def check_imports() -> Check:
    name = "imports: core/ render/ web/"
    modules: list[str] = []
    failures: list[str] = []
    for pkg in IMPORT_PACKAGES:
        pkg_dir = REPO_ROOT / pkg
        if not pkg_dir.is_dir():
            failures.append(f"{pkg}/: package directory is missing")
            continue
        for f in sorted(pkg_dir.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            mod = ".".join(f.relative_to(REPO_ROOT).with_suffix("").parts)
            modules.append(mod)
            try:
                importlib.import_module(mod)
            except Exception as exc:  # noqa: BLE001 — that is exactly what we are hunting
                failures.append(f"{mod}: {type(exc).__name__}: {exc}")
    if failures:
        return Check(name, False,
                     f"{len(failures)} of {len(modules)} module(s) failed to import",
                     output="\n".join(failures))
    return Check(name, True, f"{len(modules)} modules imported cleanly")


# --------------------------------------------------------------------------- #
# 4. web app constructed, route table correct — no server started
# --------------------------------------------------------------------------- #
def check_web_app() -> Check:
    name = "web app: construct + routes"
    try:
        from web.app import app
    except Exception as exc:  # noqa: BLE001
        return Check(name, False, f"could not import web.app: {type(exc).__name__}: {exc}",
                     output=traceback.format_exc())
    paths = sorted({getattr(r, "path", "") for r in app.routes})
    required = ("/", "/healthz", "/api/analyze", "/viewer/{run_id}", "/viewer/{run_id}/")
    missing = [p for p in required if p not in paths]
    if missing:
        return Check(name, False, "missing route(s): " + ", ".join(missing),
                     output="route table:\n" + "\n".join(paths))
    return Check(name, True,
                 f"{len(paths)} routes; /, /healthz, /api/analyze and the viewer run route are present")


# --------------------------------------------------------------------------- #
# 5. privacy — no machine absolute paths outside gitignored dirs
# --------------------------------------------------------------------------- #
def check_privacy() -> Check:
    name = "privacy: no machine paths in repo"
    username = (getpass.getuser() or "").strip()
    patterns: list[tuple[str, re.Pattern[bytes]]] = [
        # any Windows user-profile prefix (a drive letter followed by the Users directory)
        ("a Windows user-profile path", re.compile(rb"(?i)[A-Za-z]:[\\/]{1,2}Users\b")),
    ]
    if username:
        # the username as a path segment, e.g. /home/<user> or ...\<user>\
        patterns.append(
            (f"the username {username!r} in a path",
             re.compile(rb"(?i)[\\/]" + re.escape(username.encode("utf-8", "ignore")) + rb"\b"))
        )

    hits: list[str] = []
    scanned = 0
    for f in sorted(REPO_ROOT.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(REPO_ROOT)
        if any(part in PRIVACY_SKIP_DIRS for part in rel.parts):
            continue
        if any(f.match(g) for g in PRIVACY_SKIP_GLOBS):
            continue
        scanned += 1
        try:
            data = f.read_bytes()
        except OSError:
            continue
        for description, pat in patterns:
            m = pat.search(data)
            if m:
                snippet = data[max(0, m.start() - 30):m.end() + 40].decode("utf-8", "replace")
                snippet = snippet.replace("\r", " ").replace("\n", " ")
                hits.append(f"{rel}  [{description}]  …{snippet}…")
                break

    if hits:
        return Check(name, False, f"{len(hits)} file(s) contain a machine absolute path",
                     output="\n".join(hits[:20]))
    return Check(name, True, f"{scanned} files scanned, 0 machine paths found")


# --------------------------------------------------------------------------- #
# table + main
# --------------------------------------------------------------------------- #
def print_table(checks: list[Check]) -> None:
    w1 = max(len("CHECK"), max(len(c.name) for c in checks))
    w2 = 6  # len("RESULT")
    print()
    print(f"{'CHECK'.ljust(w1)}  {'RESULT'.ljust(w2)}  DETAIL")
    print(f"{'-' * w1}  {'-' * w2}  {'-' * 70}")
    for c in checks:
        print(f"{c.name.ljust(w1)}  {('PASS' if c.ok else 'FAIL').ljust(w2)}  {c.detail}")


def main(argv=None) -> int:
    try:  # keep Nepali / box text intact on any console encoding
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

    import argparse
    parser = argparse.ArgumentParser(description="Karmi quality gate")
    parser.add_argument("--coverage", action="store_true", help="run pytest with coverage measurement")
    args = parser.parse_args(argv)

    t0 = time.perf_counter()
    print("Karmi quality gate")
    print("=" * 66)
    print(f"repo : {REPO_ROOT.name}")

    checks: list[Check] = []
    with tempfile.TemporaryDirectory(prefix="karmi-checkall-") as tmp:
        tmp_dir = Path(tmp)
        checks.append(check_pytest(with_cov=args.coverage))
        for variant in PIPELINE_FIXTURES:
            checks.append(check_pipeline(variant, tmp_dir))
        checks.append(check_imports())
        checks.append(check_web_app())
        checks.append(check_privacy())

    print_table(checks)

    for c in checks:
        if not c.ok and c.output:
            print()
            print(f"--- output for failed check: {c.name} ---")
            print(c.output)

    failed = [c for c in checks if not c.ok]
    elapsed = time.perf_counter() - t0
    print()
    if failed:
        print(f"GATE: FAIL — {len(failed)} of {len(checks)} checks failed ({elapsed:.1f}s)")
        return 1
    print(f"GATE: PASS — {len(checks)}/{len(checks)} checks passed ({elapsed:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())