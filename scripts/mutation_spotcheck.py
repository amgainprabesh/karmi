#!/usr/bin/env python3
"""Karmi mutation spot-check — proves that tests fail when code breaks.

Applies targeted mutations one at a time to a temporary copy of the codebase,
runs the fast test suite (pytest -q -m "not slow" -x), and verifies that at
least one test catches each defect (i.e. pytest fails).
If any mutation survives, the check reports FAIL.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# List of (file_rel_path, target_string, mutated_string, description, expected_test_hint)
MUTATIONS = [
    (
        "core/diff.py",
        "DIFF_MEDIUM_MAX = 0.25",
        "DIFF_MEDIUM_MAX = 0.40",
        "Widen medium severity limit: 33% window difference becomes medium instead of high",
        "test_demo_regression or test_diff_and_report",
    ),
    (
        "core/diff.py",
        "CONFIDENCE_CAP = 0.50",
        "CONFIDENCE_CAP = 0.0",
        "Disable low confidence cap: weak evidence no longer capped at low severity",
        "test_low_confidence_caps_severity or test_demo_regression",
    ),
    (
        "core/diff.py",
        "COVERAGE_SPARSE_RATIO = 0.50",
        "COVERAGE_SPARSE_RATIO = 0.0",
        "Disable coverage guard: partial photo coverage reports missing elements as MISSING instead of UNVERIFIABLE",
        "test_coverage_guard or test_demo_regression",
    ),
    (
        "core/diff.py",
        "return problems",
        "return []",
        "Bypass narration guard: _validate_narration always accepts candidate rewrites",
        "test_narration_guard",
    ),
    (
        "core/nepali.py",
        "return str(s).translate(_ASCII_TO_DEVANAGARI)",
        "return str(s)",
        "Break digit translation: to_devanagari_digits returns ASCII digits unmodified",
        "test_nepali",
    ),
    (
        "core/validate.py",
        "candidate.relative_to(base_p)",
        "pass",
        "Break safe_join traversal protection: stops validating path containment",
        "test_validate or test_web_app",
    ),
]


def test_mutation(tmp_repo: Path, rel_file: str, target: str, replacement: str) -> bool:
    target_path = tmp_repo / rel_file
    content = target_path.read_text(encoding="utf-8")
    if target not in content:
        print(f"  [ERROR] Target string not found in {rel_file}: {target!r}")
        return False

    # Apply mutation
    mutated = content.replace(target, replacement, 1)
    target_path.write_text(mutated, encoding="utf-8")

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-m", "not slow", "-x"],
            cwd=str(tmp_repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # If returncode is non-zero, pytest failed -> mutation was KILLED (good!)
        killed = proc.returncode != 0
        return killed
    finally:
        # Revert mutation
        target_path.write_text(content, encoding="utf-8")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("Karmi mutation spot-check")
    print("=" * 66)
    t0 = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="karmi-mut-") as tmp:
        tmp_repo = Path(tmp) / "karmi"
        # Copy repository ignoring unnecessary caches and runs
        shutil.copytree(
            REPO_ROOT,
            tmp_repo,
            ignore=shutil.ignore_patterns(
                ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "runs", "web/runs", ".coverage*", "htmlcov"
            ),
        )

        all_killed = True
        for i, (rel_file, target, replacement, desc, hint) in enumerate(MUTATIONS, 1):
            print(f"[{i}/{len(MUTATIONS)}] {desc}")
            killed = test_mutation(tmp_repo, rel_file, target, replacement)
            if killed:
                print(f"      -> KILLED (tests caught the change: {hint})")
            else:
                print(f"      -> SURVIVED (DEFECT: tests failed to catch the change!)")
                all_killed = False

    elapsed = time.perf_counter() - t0
    print()
    if all_killed:
        print(f"MUTATION SPOT-CHECK: PASS — All {len(MUTATIONS)} mutations killed in {elapsed:.1f}s.")
        return 0
    else:
        print(f"MUTATION SPOT-CHECK: FAIL — At least one mutation survived.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
