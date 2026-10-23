#!/usr/bin/env python3
"""Karmi web smoke test — start the real server, use it, shut it down.

Prints every step with its real HTTP status:

  1. picks a free port and starts ``python -m web.app`` as a subprocess
     (runs go to a throwaway temp dir — the repository is left untouched),
  2. polls ``GET /healthz`` until the server is ready (bounded timeout —
     no blind sleeps),
  3. POSTs a real fixture drawing + the three sample photos + their measurement
     sidecars to ``/api/analyze`` as multipart/form-data (http.client),
  4. follows the run page ``GET /run/<id>`` and asserts the items-to-verify
     list is present in the rendered HTML,
  5. checks ``GET /api/report/<id>`` returns the same verify list as JSON,
  6. shuts the server down — graceful CTRL_BREAK on Windows (uvicorn handles
     SIGBREAK), SIGTERM elsewhere, force only as a last resort — and reports
     the exit code. The subprocess is ALWAYS cleaned up.

Exit code: 0 only if every step succeeded; non-zero otherwise.
No network required (loopback only).

Usage (from the repository root, with the project venv)::

    python scripts/smoke_web.py
"""

from __future__ import annotations

import http.client
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PHOTO_NAMES = (
    "front_walls_stage.jpg",
    "rear_foundation_stage.jpg",
    "side_columns_stage.jpg",
)
SIDECAR_NAMES = tuple(f"{n}.json" for n in PHOTO_NAMES)
KNOWN_DIMENSION = "10.0"
TOTAL_STEPS = 7


class SmokeFailure(Exception):
    """A step of the smoke test failed. Carries the human-readable reason."""


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def free_port() -> int:
    """Ask the OS for a free TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def build_multipart(fields, files) -> tuple[str, bytes]:
    """(boundary, body) for multipart/form-data. fields=[(name, value)],
    files=[(name, filename, content_type, bytes)] — repeated names allowed."""
    boundary = "----karmi-smoke-" + secrets.token_hex(12)
    chunks: list[bytes] = []
    for name, value in fields:
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    for name, filename, ctype, data in files:
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode("utf-8")
        )
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return boundary, b"".join(chunks)


def request(port: int, method: str, path: str, body: bytes | None = None,
            headers: dict | None = None, timeout: float = 300.0):
    """(status, headers, body) via http.client against 127.0.0.1:<port>."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()
    finally:
        conn.close()


def start_server(port: int, runs_dir: Path, log_path: Path):
    """Start `python -m web.app` in its own process group; logs to log_path."""
    env = os.environ.copy()
    env["KARMI_HOST"] = "127.0.0.1"
    env["KARMI_PORT"] = str(port)
    env["KARMI_RUNS_DIR"] = str(runs_dir)
    env["PYTHONUNBUFFERED"] = "1"
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    log_fh = open(log_path, "wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "web.app"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    return proc, log_fh


def wait_for_healthz(port: int, proc: subprocess.Popen, timeout_s: float = 60.0):
    """Poll GET /healthz until it answers 200 (bounded), or fail with the reason."""
    deadline = time.monotonic() + timeout_s
    attempts = 0
    last_error = "no attempt made"
    while time.monotonic() < deadline:
        attempts += 1
        if proc.poll() is not None:
            raise SmokeFailure(
                f"the server exited early (code {proc.returncode}) before /healthz answered"
            )
        try:
            status, _headers, body = request(port, "GET", "/healthz", timeout=3.0)
            if status == 200:
                return attempts, json.loads(body.decode("utf-8"))
            last_error = f"HTTP {status}"
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.25)
    raise SmokeFailure(f"/healthz did not answer within {timeout_s:.0f}s (last: {last_error})")


def shutdown(proc: subprocess.Popen, timeout_s: float = 15.0) -> tuple[str, int | None]:
    """Stop the server: graceful signal first, force only if it will not go."""
    if proc.poll() is not None:
        return "already exited", proc.returncode

    graceful_sent = False
    method = "terminate (forced)"
    if os.name == "nt":
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # uvicorn handles SIGBREAK → clean exit
            graceful_sent, method = True, "CTRL_BREAK (graceful)"
        except (OSError, ValueError):
            graceful_sent = False
    else:
        proc.terminate()  # SIGTERM — uvicorn shuts down cleanly
        graceful_sent, method = True, "SIGTERM (graceful)"

    if graceful_sent:
        try:
            proc.wait(timeout=timeout_s)
            return method, proc.returncode
        except subprocess.TimeoutExpired:
            pass

    proc.terminate()
    try:
        proc.wait(timeout=10.0)
        return "terminate (forced)", proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10.0)
        return "kill (forced)", proc.returncode


def log_tail(log_path: Path, lines: int = 40) -> str:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(server log unavailable)"
    tail = [ln for ln in text.splitlines() if ln.strip()][-lines:]
    return "\n".join(tail) if tail else "(server log is empty)"


def log_contains(log_path: Path, *needles: str) -> bool:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return all(n in text for n in needles)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

    print("Karmi web smoke test")
    print("=" * 66)

    port = free_port()
    tmp = Path(tempfile.mkdtemp(prefix="karmi-smoke-"))
    runs_dir = tmp / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    log_path = tmp / "server.log"

    proc: subprocess.Popen | None = None
    log_fh = None
    rc = 1
    shutdown_note = ""

    try:
        # -- inputs ---------------------------------------------------------- #
        drawing = REPO_ROOT / "fixtures" / "naksa_base.pdf"
        photos = [REPO_ROOT / "fixtures" / "photos" / n for n in PHOTO_NAMES]
        sidecars = [REPO_ROOT / "fixtures" / "photos" / n for n in SIDECAR_NAMES]
        missing = [p for p in [drawing, *photos, *sidecars] if not p.is_file()]
        if missing:
            raise SmokeFailure("fixture(s) missing: " + ", ".join(str(p) for p in missing))

        # -- 1. start -------------------------------------------------------- #
        print(f"[1/{TOTAL_STEPS}] start server      : {sys.executable} -m web.app  "
              f"(127.0.0.1:{port}, runs in {tmp})")
        proc, log_fh = start_server(port, runs_dir, log_path)

        # -- 2. health ------------------------------------------------------- #
        attempts, health = wait_for_healthz(port, proc, timeout_s=60.0)
        if health.get("ok") is not True:
            raise SmokeFailure(f"/healthz reported ok={health.get('ok')!r}")
        if health.get("core_available") is not True:
            raise SmokeFailure(
                f"/healthz says the core pipeline is not available: {health.get('core_error')!r}"
            )
        print(f"[2/{TOTAL_STEPS}] GET  /healthz        -> 200  (ready after {attempts} poll(s); "
              f"service={health.get('service')} v{health.get('version')}; "
              f"viewer_available={health.get('viewer_available')}; core_available=True)")

        # -- 3. POST the real fixture drawing -------------------------------- #
        fields = [("known_dimension", KNOWN_DIMENSION)]
        files = [("drawing", drawing.name, "application/pdf", drawing.read_bytes())]
        files += [("photos", p.name, "image/jpeg", p.read_bytes()) for p in photos]
        files += [("photos", s.name, "application/json", s.read_bytes()) for s in sidecars]
        boundary, body = build_multipart(fields, files)
        status, _headers, raw = request(
            port, "POST", "/api/analyze", body=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
        )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SmokeFailure(f"POST /api/analyze returned non-JSON ({exc}): {raw[:200]!r}")
        if status != 200:
            raise SmokeFailure(f"POST /api/analyze -> HTTP {status}: {json.dumps(payload)[:300]}")
        if payload.get("ok") is not True:
            raise SmokeFailure(f"POST /api/analyze -> ok={payload.get('ok')!r}: "
                               f"{json.dumps(payload.get('errors') or payload)[:300]}")
        counts = payload.get("counts") or {}
        run_id = payload.get("run_id")
        if not run_id:
            raise SmokeFailure("POST /api/analyze returned no run_id")
        if int(counts.get("total") or 0) <= 0:
            raise SmokeFailure(f"POST /api/analyze compared 0 elements: {counts}")
        # every sidecar must survive the upload path: the demo set measures one
        # high, one medium and one low difference (window, side door, bedroom)
        n_flagged = sum(int(counts.get(k) or 0) for k in ("high", "medium"))
        if n_flagged < 2:
            raise SmokeFailure(
                f"expected the sidecar measurements to flag >= 2 high/medium differences "
                f"through the web path, got {counts} — were the sidecars dropped?"
            )
        print(f"[3/{TOTAL_STEPS}] POST /api/analyze    -> {status}  (run_id={run_id}; "
              f"total={counts.get('total')}; high={counts.get('high')}; medium={counts.get('medium')}; "
              f"verify_items={counts.get('verify_items')}; photos={payload.get('photos_saved')})")

        # -- 4. follow the run page ------------------------------------------ #
        status, _headers, page_raw = request(port, "GET", f"/run/{run_id}")
        if status != 200:
            raise SmokeFailure(f"GET /run/{run_id} -> HTTP {status}")
        html = page_raw.decode("utf-8", "replace")
        if 'id="verify-list"' not in html:
            raise SmokeFailure("the run page has no verify-list section")
        if "Items to verify" not in html:
            raise SmokeFailure("the run page has no 'Items to verify' heading")
        rendered_items = html.count('class="verify-item')
        if rendered_items < 1:
            raise SmokeFailure("the verify list section is present but empty")
        print(f"[4/{TOTAL_STEPS}] GET  /run/<id>       -> {status}  (html {len(page_raw)} bytes)")

        # -- 5. verify list present ------------------------------------------ #
        verify_items = int(counts.get("verify_items") or 0)
        if rendered_items != verify_items:
            raise SmokeFailure(
                f"run page renders {rendered_items} verify item(s) but the API reported {verify_items}"
            )
        print(f"[5/{TOTAL_STEPS}] verify list        : present — {rendered_items} item(s) rendered "
              f"('Items to verify' + id=\"verify-list\")")

        # -- 6. the same list as JSON ---------------------------------------- #
        status, _headers, raw = request(port, "GET", f"/api/report/{run_id}")
        if status != 200:
            raise SmokeFailure(f"GET /api/report/{run_id} -> HTTP {status}")
        report = json.loads(raw.decode("utf-8"))
        n_json = len(report.get("verify_list") or [])
        if n_json != verify_items:
            raise SmokeFailure(
                f"report JSON has {n_json} verify item(s), API said {verify_items}"
            )
        print(f"[6/{TOTAL_STEPS}] GET  /api/report/<id> -> {status}  (verify_list in JSON: {n_json} item(s))")

        rc = 0

    except SmokeFailure as exc:
        print(f"SMOKE TEST: FAIL — {exc}")
        rc = 1
    except Exception as exc:  # noqa: BLE001
        print(f"SMOKE TEST: FAIL — unexpected {type(exc).__name__}: {exc}")
        traceback.print_exc()
        rc = 1
    finally:
        # -- 7. shutdown (ALWAYS runs) --------------------------------------- #
        if proc is not None:
            try:
                method, code = shutdown(proc)
                # uvicorn re-raises the captured signal after a graceful stop, so the
                # exit status is signal-style (CTRL_BREAK on Windows -> 3, SIGTERM on
                # Unix -> -15). The log is the real evidence of a clean shutdown.
                clean = "graceful" in method and log_contains(
                    log_path, "Shutting down", "Finished server process"
                )
                marker = "  (log: clean shutdown confirmed)" if clean else ""
                print(f"[{TOTAL_STEPS}/{TOTAL_STEPS}] shutdown           : {method} — "
                      f"server exited with code {code}{marker}")
                if rc == 0:
                    if clean:
                        shutdown_note = (
                            "note: after a graceful stop uvicorn re-raises the shutdown signal, so the "
                            f"exit status is signal-style ({code}) — the server log confirms the clean "
                            "shutdown sequence."
                        )
                    else:
                        shutdown_note = (
                            "warning: the server stopped, but uvicorn's clean-shutdown sequence was not "
                            "seen in the log — a forced stop is reported above."
                        )
            except Exception as exc:  # noqa: BLE001
                print(f"[{TOTAL_STEPS}/{TOTAL_STEPS}] shutdown           : FAILED to stop the server "
                      f"({type(exc).__name__}: {exc})")
                rc = 1
        if log_fh is not None:
            try:
                log_fh.close()
            except Exception:
                pass
        if rc != 0:
            print()
            print("--- server log (tail) ---")
            print(log_tail(log_path))
        shutil.rmtree(tmp, ignore_errors=True)

    if rc == 0:
        if shutdown_note:
            print(shutdown_note)
        print("SMOKE TEST: PASS — every step completed against a real running server.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())