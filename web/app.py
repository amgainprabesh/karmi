"""Karmi web UI — a local FastAPI app that runs the whole pipeline end to end.

Start it from the repository root::

    python -m web.app
    # or
    uvicorn web.app:app --port 8000

Everything runs locally: no network calls, no CDNs, no external fonts.
Runs are written under ``web/runs/<run_id>/`` (override with ``KARMI_RUNS_DIR``).

Product rule, stated everywhere in the UI, in both languages: Karmi reports
**items to verify** — it never declares a violation.
"""

from __future__ import annotations

import json
import math
import os
import re
import secrets
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

# Deep input validation (magic bytes, PDF JavaScript/Launch/encrypt, page limits,
# decompression-bomb shape). The cheap extension/`%PDF` checks below are only a
# first gate — see docs/SECURITY.md. Imported defensively so the UI still runs
# if the module is unavailable, but the app refuses to silently skip it.
try:
    from core.validate import UnsafeInput, validate_upload
except Exception:  # pragma: no cover - hardening is required in a normal checkout
    UnsafeInput = None  # type: ignore[assignment]
    validate_upload = None  # type: ignore[assignment]

# --------------------------------------------------------------------------- #
# paths & constants
# --------------------------------------------------------------------------- #
WEB_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RUNS_DIR = Path(os.environ.get("KARMI_RUNS_DIR", str(WEB_DIR / "runs"))).resolve()
RUNS_DIR.mkdir(parents=True, exist_ok=True)

STATIC_DIR = WEB_DIR / "static"
VIEWER_FILE = REPO_ROOT / "render" / "viewer.html"
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))

RUN_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_PHOTO_BYTES = 32 * 1024 * 1024
MAX_SIDECAR_BYTES = 1024 * 1024
MAX_PHOTOS = 20

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff"}
STAGES = ["foundation", "columns", "walls", "slab", "roof", "finishing"]
STAGE_LABELS = {
    "foundation": "Foundation / जग",
    "columns": "Columns / पिलर",
    "walls": "Walls / भित्ता",
    "slab": "Slab / स्ल्याब",
    "roof": "Roof / छाना",
    "finishing": "Finishing / फिनिशिङ",
}
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2, "info": 3}
SEVERITY_LABELS = {
    "high": "High / उच्च",
    "medium": "Medium / मध्यम",
    "low": "Low / न्यून",
    "info": "Info / जानकारी",
}
STATUS_ORDER = {"differs": 0, "missing": 1, "unexpected": 2, "unverifiable": 3, "matched": 4}
STATUS_LABELS = {
    "matched": "Matched / मिल्यो",
    "differs": "Differs / फरक देखियो",
    "missing": "Not seen in photos / फोटोमा देखिएन",
    "unexpected": "Not in the drawing / नक्सामा छैन",
    "unverifiable": "Could not verify / जाँच हुन सकेन",
}

# Standing, product-level honesty. Shown on both pages, both languages.
STANDING_LIMITS: list[tuple[str, str]] = [
    (
        "Karmi compares only what the photos show. Parts of the building can be hidden by "
        "scaffolding, by finishing work, or simply never photographed.",
        "कर्मीले फोटोमा देखिने कुराको मात्र तुलना गर्छ। भवनका केही भाग इस्क्याफोल्डिङ, फिनिशिङ वा "
        "फोटो नखिचिएका कारण देखिन सक्दैनन्।",
    ),
    (
        "Sizes read from photos are estimates with a confidence value — they are not measured facts.",
        "फोटोबाट निकालिएका नाप अनुमानित हुन् र तिनमा विश्वास स्तर (confidence) जोडिएको हुन्छ — "
        "तिनलाई नापी गरिएको तथ्य मान्नु हुँदैन।",
    ),
    (
        "Karmi does not check structure, steel, soil or engineering safety — only layout and "
        "visible size.",
        "कर्मीले संरचना, फलाम, माटो वा इन्जिनियरिङ सुरक्षा जाँच्दैन — यसले लेआउट र देखिने नाप मात्र "
        "तुलना गर्छ।",
    ),
    (
        "This is not a legal document and not a municipal inspection.",
        "यो कानुनी दस्तावेज होइन र पालिकाको निरीक्षण पनि होइन।",
    ),
    (
        "Only your architect or your municipality can decide whether a change is acceptable.",
        "कुनै परिवर्तन स्वीकार्य छ कि छैन भन्ने निर्णय आफ्नो आर्किटेक्ट वा पालिकाले मात्र गर्न सक्छ।",
    ),
]

RUN_FILE_WHITELIST = {
    "view.json",
    "report.json",
    "scene.json",
    "observed.json",
    "run.json",
    "uploads.json",
    "report.html",
    "report.md",
}
RUN_FILE_MEDIA = {
    ".json": "application/json",
    ".html": "text/html; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}

app = FastAPI(title="Karmi (कर्मी) — web UI", version="0.1.0")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
class FriendlyError(Exception):
    """An error a homeowner can read. Never a traceback."""

    def __init__(self, message_en: str, message_np: str = "", status_code: int = 400):
        super().__init__(message_en)
        self.message_en = message_en
        self.message_np = message_np
        self.status_code = status_code


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_dir(run_id: str) -> Path | None:
    """Resolve a run directory; returns None for anything that is not a valid id."""
    if not RUN_ID_RE.match(run_id or ""):
        return None
    d = (RUNS_DIR / run_id).resolve()
    if d.parent != RUNS_DIR:
        return None
    return d


def _safe_filename(name: str, fallback: str) -> str:
    base = Path(str(name or "")).name
    stem = Path(base).stem or ""
    ext = Path(base).suffix.lower()
    if ext and not re.fullmatch(r"\.[A-Za-z0-9]{1,8}", ext):
        ext = ""
    stem_clean = SAFE_NAME_RE.sub("_", stem).strip("._")
    if not stem_clean:
        stem_clean = fallback
    return (stem_clean[:80] + ext)[:120]


def _unique_path(directory: Path, filename: str) -> Path:
    p = directory / filename
    if not p.exists():
        return p
    stem, ext = p.stem, p.suffix
    for i in range(2, 1000):
        q = directory / f"{stem}_{i}{ext}"
        if not q.exists():
            return q
    return directory / f"{stem}_{secrets.token_hex(2)}{ext}"


async def _save_upload(upload: UploadFile, dest: Path, max_bytes: int, label: str,
                       first_chunk: bytes = b"") -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with dest.open("wb") as fh:
        if first_chunk:
            size += len(first_chunk)
            fh.write(first_chunk)
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                fh.close()
                dest.unlink(missing_ok=True)
                mb = max_bytes // (1024 * 1024)
                raise FriendlyError(
                    f"That {label} is larger than {mb} MB. Please upload a smaller file.",
                    f"त्यो फाइल {mb} MB भन्दा ठूलो छ — कृपया सानो फाइल राख्नुहोस्।",
                )
            fh.write(chunk)
    return size


def _links(run_id: str) -> dict[str, str]:
    return {
        "results": f"/run/{run_id}",
        "report_json": f"/api/report/{run_id}",
        "run_json": f"/runs/{run_id}/run.json",
        "view_json": f"/runs/{run_id}/view.json",
        "viewer": f"/viewer/{run_id}/",
        "report_html": f"/runs/{run_id}/report.html",
        "report_md": f"/runs/{run_id}/report.md",
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
        if not math.isfinite(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list_runs(limit: int = 50) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not RUNS_DIR.is_dir():
        return items
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir() or not RUN_ID_RE.match(d.name):
            continue
        manifest = _read_json(d / "run.json")
        if not isinstance(manifest, dict):
            continue  # partial/aborted run — not listed
        result = manifest.get("result") or {}
        items.append(
            {
                "run_id": d.name,
                "generated_at": manifest.get("generated_at"),
                "ok": bool(result.get("ok")),
                "summary": result.get("summary") or {},
                "drawing": Path(str(manifest.get("drawing") or "")).name,
                "photos": len(manifest.get("photos") or []),
                "links": _links(d.name),
            }
        )
        if len(items) >= limit:
            break
    return items


def _viewer_state(rdir: Path) -> str:
    """ready | no_view_data | missing"""
    has_viewer = VIEWER_FILE.is_file()
    has_view = (rdir / "view.json").is_file()
    if has_viewer and has_view:
        return "ready"
    if has_viewer:
        return "no_view_data"
    return "missing"


def _error_page(request: Request, status_code: int, title: str,
                message_en: str, message_np: str = "") -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "status_code": status_code,
            "title": title,
            "message_en": message_en,
            "message_np": message_np,
        },
        status_code=status_code,
    )


# --------------------------------------------------------------------------- #
# upload processing (shared by /api/analyze and the no-JS /analyze form)
# --------------------------------------------------------------------------- #
async def _process_upload(
    drawing: UploadFile | None,
    photos: list[UploadFile] | None,
    known_dimension_raw: str | None,
    stage_raw: str | None,
) -> tuple[int, dict[str, Any]]:
    """Save uploads, run the pipeline, return (status_code, payload).

    Raises FriendlyError for input problems a homeowner can fix.
    """
    if drawing is None or not str(drawing.filename or "").strip():
        raise FriendlyError(
            "Please attach the approved naksa drawing (PDF).",
            "कृपया स्वीकृत नक्सा (PDF) संलग्न गर्नुहोस्।",
        )

    # -- optional known dimension -------------------------------------------
    kd: float | None = None
    if known_dimension_raw is not None and str(known_dimension_raw).strip() != "":
        try:
            kd = float(str(known_dimension_raw).strip())
        except ValueError:
            raise FriendlyError(
                "The known dimension must be a number in metres (for example 10.0).",
                "थाहा भएको नाप मिटरमा संख्या हुनुपर्छ (जस्तै १०.०)।",
            )
        if not math.isfinite(kd) or kd <= 0 or kd > 10000:
            raise FriendlyError(
                "The known dimension must be a positive number of metres (0–10000).",
                "थाहा भएको नाप शून्यभन्दा ठूलो, मिटरमा हुनुपर्छ (०–१००००)।",
            )

    # -- optional stage ------------------------------------------------------
    stage = (stage_raw or "").strip() or None
    if stage is not None and stage not in STAGES:
        raise FriendlyError(
            "Unknown construction stage. Choose one of: " + ", ".join(STAGES) + ".",
            "निर्माण चरण मिलेन। यीमध्ये एउटा छान्नुहोस्: " + ", ".join(STAGES) + "।",
        )

    # -- drawing: must really be a PDF (check content, not just the name) ---
    head = await drawing.read(1024)
    if b"%PDF" not in head[:1024]:
        raise FriendlyError(
            "That file is not a PDF. Karmi needs the approved drawing as a PDF file.",
            "त्यो फाइल PDF होइन। कर्मीलाई स्वीकृत नक्सा PDF रूपमा चाहिन्छ।",
        )

    run_id = _new_run_id()
    rdir = RUNS_DIR / run_id
    inputs = rdir / "inputs"

    try:
        inputs.mkdir(parents=True, exist_ok=True)

        dname = _safe_filename(drawing.filename, "drawing")
        drawing_path = _unique_path(inputs, (Path(dname).stem or "drawing") + ".pdf")
        drawing_size = await _save_upload(drawing, drawing_path, MAX_PDF_BYTES, "drawing",
                                          first_chunk=head)

        # -- deep validation of the saved PDF (see docs/SECURITY.md) ---------
        if validate_upload is not None and UnsafeInput is not None:
            try:
                validate_upload(drawing_path, max_bytes=MAX_PDF_BYTES)
            except UnsafeInput as ue:
                raise FriendlyError(
                    f"That PDF was rejected by Karmi's safety checks ({ue.reason}). "
                    "If it came from a scanner or another tool, re-export it and try again.",
                    "त्यो PDF कर्मीको सुरक्षा जाँचमा अस्वीकृत भयो। पुनः निर्यात गरेर "
                    "प्रयास गर्नुहोस्।",
                ) from ue

        # -- photos: tolerant. Bad photos are skipped with a note, never fatal.
        saved_photos: list[dict[str, Any]] = []
        saved_sidecars: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for idx, ph in enumerate(photos or []):
            name = str(ph.filename or "").strip()
            if not name:
                skipped.append({"file": f"(unnamed photo #{idx + 1})",
                                "reason": "the file had no name"})
                continue
            ext = Path(name).suffix.lower()

            # A sidecar measurement file travels with its photo: `photo.jpg.json`.
            # It carries hand-entered measurements (see core/observe.py) and is the
            # honest offline fallback when no AI model is configured — so it must
            # reach the pipeline, not be silently dropped with the upload.
            if ext == ".json":
                dest = _unique_path(inputs, _safe_filename(name, f"measurements_{idx + 1:02d}.json"))
                try:
                    ssize = await _save_upload(ph, dest, MAX_SIDECAR_BYTES, "measurements file")
                except FriendlyError as fe:
                    skipped.append({"file": name, "reason": fe.message_en})
                    continue
                saved_sidecars.append({"file": name, "saved_as": dest.name, "bytes": ssize})
                continue

            if ext not in PHOTO_EXTS:
                skipped.append({"file": name,
                                "reason": "not an image file (JPG/PNG/WebP/HEIC) or a "
                                          "measurements .json file"})
                continue
            if len(saved_photos) >= MAX_PHOTOS:
                skipped.append({"file": name, "reason": f"more than {MAX_PHOTOS} photos"})
                continue
            dest = _unique_path(inputs, _safe_filename(name, f"photo_{idx + 1:02d}"))
            try:
                psize = await _save_upload(ph, dest, MAX_PHOTO_BYTES, "photo")
            except FriendlyError as fe:
                skipped.append({"file": name, "reason": fe.message_en})
                continue
            # deep validation where the format is one we can check by magic bytes
            if validate_upload is not None and UnsafeInput is not None and ext in {
                ".jpg", ".jpeg", ".png", ".webp",
            }:
                try:
                    validate_upload(dest, max_bytes=MAX_PHOTO_BYTES,
                                    allowed={"jpg", "jpeg", "png", "webp"})
                except UnsafeInput as ue:
                    dest.unlink(missing_ok=True)
                    skipped.append({"file": name,
                                    "reason": f"failed Karmi's safety check: {ue.reason}"})
                    continue
            saved_photos.append({"file": name, "saved_as": dest.name, "bytes": psize})

        _write_json_file(
            rdir / "uploads.json",
            {
                "run_id": run_id,
                "created_at": _now_iso(),
                "drawing": {"file": drawing.filename, "saved_as": drawing_path.name,
                            "bytes": drawing_size},
                "photos": saved_photos,
                "measurements": saved_sidecars,
                "photos_skipped": skipped,
                "known_dimension_m": kd,
                "stage_hint": stage,
            },
        )
    except FriendlyError:
        if not (rdir / "run.json").is_file():
            shutil.rmtree(rdir, ignore_errors=True)
        raise
    except Exception:
        if not (rdir / "run.json").is_file():
            shutil.rmtree(rdir, ignore_errors=True)
        raise

    # -- run the pipeline ----------------------------------------------------
    photo_paths = [str(inputs / p["saved_as"]) for p in saved_photos]
    try:
        from core.pipeline import run_pipeline

        res = await run_in_threadpool(
            run_pipeline,
            str(drawing_path),
            photo_paths,
            str(rdir),
            known_dimension=kd,
            stage_hint=stage,
        )
    except Exception as exc:  # noqa: BLE001 — a hard failure still gets a friendly page
        traceback.print_exc()
        _ensure_fallback_manifest(rdir, run_id, drawing_path, photo_paths, exc, kd, stage)
        return 500, {
            "ok": False,
            "run_id": run_id,
            "error": ("Karmi could not finish the analysis. The run was saved and the "
                      "details are on the run page."),
            "error_np": ("कर्मीले विश्लेषण पूरा गर्न सकेन। रन सुरक्षित गरिएको छ — विवरण रन "
                         "पृष्ठमा हेर्नुहोस्।"),
            "detail": f"{type(exc).__name__}: {exc}"[:400],
            "links": _links(run_id),
        }

    summary = res.report.summary if res.report else {}
    payload: dict[str, Any] = {
        "ok": bool(res.ok),
        "degraded": not bool(res.ok),
        "run_id": run_id,
        "summary": summary,
        "counts": {
            "high": _safe_int(summary.get("high")),
            "medium": _safe_int(summary.get("medium")),
            "low": _safe_int(summary.get("low")),
            "info": _safe_int(summary.get("info")),
            "total": _safe_int(summary.get("total")),
            "matched": _safe_int(summary.get("matched")),
            "verify_items": _safe_int(summary.get("verify_items")),
        },
        "errors": res.errors,
        "warnings": res.warnings,
        "timings_ms": res.timings_ms,
        "photos_saved": len(saved_photos),
        "photos_skipped": skipped,
        "stage_hint": stage,
        "known_dimension_m": kd,
        "links": _links(run_id),
    }
    return 200, payload


def _ensure_fallback_manifest(rdir: Path, run_id: str, drawing_path: Path,
                              photo_paths: list[str], exc: Exception,
                              kd: float | None, stage: str | None) -> None:
    """Make sure /run/<id> can explain itself even if the pipeline raised."""
    if (rdir / "run.json").is_file():
        return
    _write_json_file(
        rdir / "run.json",
        {
            "schema": "0.1.0",
            "generated_at": _now_iso(),
            "drawing": str(drawing_path),
            "photos": list(photo_paths),
            "known_dimension_m": kd,
            "ai_provider": "none",
            "result": {
                "ok": False,
                "out_dir": str(rdir),
                "files": {},
                "errors": [f"pipeline: {type(exc).__name__}: {exc}"[:500]],
                "warnings": ["The analysis did not finish."],
                "timings_ms": {},
                "summary": {},
            },
        },
    )


# --------------------------------------------------------------------------- #
# routes — pages
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "runs": _list_runs(limit=5),
            "stages": [(s, STAGE_LABELS[s]) for s in STAGES],
            "standing_limits": STANDING_LIMITS,
            "error": None,
            "error_np": None,
        },
    )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze_form(
    request: Request,
    drawing: UploadFile | None = File(default=None),
    photos: list[UploadFile] = File(default=[]),
    known_dimension: str | None = Form(default=None),
    stage: str | None = Form(default=None),
) -> Response:
    """No-JavaScript path: classic form POST, then redirect to the run page."""
    try:
        status, payload = await _process_upload(drawing, photos, known_dimension, stage)
    except FriendlyError as fe:
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "request": request,
                "runs": _list_runs(limit=5),
                "stages": [(s, STAGE_LABELS[s]) for s in STAGES],
                "standing_limits": STANDING_LIMITS,
                "error": fe.message_en,
                "error_np": fe.message_np,
            },
            status_code=fe.status_code,
        )
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "request": request,
                "runs": _list_runs(limit=5),
                "stages": [(s, STAGE_LABELS[s]) for s in STAGES],
                "standing_limits": STANDING_LIMITS,
                "error": "Something went wrong while reading the upload. Please try again.",
                "error_np": "अपलोड पढ्दा समस्या आयो — कृपया फेरि प्रयास गर्नुहोस्।",
            },
            status_code=500,
        )
    if payload.get("run_id"):
        return RedirectResponse(url=f"/run/{payload['run_id']}", status_code=303)
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "runs": _list_runs(limit=5),
            "stages": [(s, STAGE_LABELS[s]) for s in STAGES],
            "standing_limits": STANDING_LIMITS,
            "error": payload.get("error", "The upload could not be processed."),
            "error_np": payload.get("error_np", ""),
        },
        status_code=status,
    )


@app.get("/run/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str) -> HTMLResponse:
    rdir = _run_dir(run_id)
    if rdir is None or not rdir.is_dir():
        return _error_page(
            request, 404, "Run not found",
            "This run does not exist (or the id is mistyped).",
            "यो रन भेटिएन (वा आईडी मिलेन)।",
        )
    return TEMPLATES.TemplateResponse(request, "run.html", _run_context(request, run_id, rdir))


# --------------------------------------------------------------------------- #
# routes — JSON API
# --------------------------------------------------------------------------- #
@app.post("/api/analyze")
async def api_analyze(
    drawing: UploadFile | None = File(default=None),
    photos: list[UploadFile] = File(default=[]),
    known_dimension: str | None = Form(default=None),
    stage: str | None = Form(default=None),
) -> JSONResponse:
    try:
        status, payload = await _process_upload(drawing, photos, known_dimension, stage)
        return JSONResponse(status_code=status, content=payload)
    except FriendlyError as fe:
        return JSONResponse(
            status_code=fe.status_code,
            content={"ok": False, "error": fe.message_en, "error_np": fe.message_np},
        )
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "Something went wrong while reading the upload. Please try again.",
                "error_np": "अपलोड पढ्दा समस्या आयो — कृपया फेरि प्रयास गर्नुहोस्।",
                "detail": f"{type(exc).__name__}: {exc}"[:300],
            },
        )


@app.get("/api/report/{run_id}")
def api_report(run_id: str) -> Response:
    rdir = _run_dir(run_id)
    if rdir is None or not rdir.is_dir():
        return JSONResponse(status_code=404, content={"ok": False,
                                                      "error": "No such run."})
    p = rdir / "report.json"
    if not p.is_file():
        return JSONResponse(status_code=404,
                            content={"ok": False,
                                     "error": "This run has no report yet."})
    data = _read_json(p)
    if data is None:
        return JSONResponse(status_code=500,
                            content={"ok": False,
                                     "error": "The report file for this run is unreadable."})
    return JSONResponse(content=data)


@app.get("/api/runs")
def api_runs() -> JSONResponse:
    return JSONResponse(content={"ok": True, "runs": _list_runs(limit=200)})


@app.get("/run/{run_id}/export/json")
def export_json(run_id: str) -> Response:
    rdir = _run_dir(run_id)
    if rdir is None or not rdir.is_dir():
        return JSONResponse(status_code=404, content={"ok": False, "error": "Run not found."})
    p = rdir / "report.json"
    if not p.is_file():
        return JSONResponse(
            status_code=404, content={"ok": False, "error": "Report JSON not available for this run."}
        )
    return FileResponse(
        p,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="karmi-report-{run_id}.json"'},
    )


@app.get("/run/{run_id}/export/report")
def export_report(run_id: str) -> Response:
    rdir = _run_dir(run_id)
    if rdir is None or not rdir.is_dir():
        return JSONResponse(status_code=404, content={"ok": False, "error": "Run not found."})
    p = rdir / "report.html"
    if not p.is_file():
        return JSONResponse(
            status_code=404, content={"ok": False, "error": "Report HTML not available for this run."}
        )
    return FileResponse(
        p,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="karmi-report-{run_id}.html"'},
    )


@app.get("/run/{run_id}/export/print")
def export_print(run_id: str) -> Response:
    rdir = _run_dir(run_id)
    if rdir is None or not rdir.is_dir():
        return JSONResponse(status_code=404, content={"ok": False, "error": "Run not found."})
    p = rdir / "report.json"
    if not p.is_file():
        return JSONResponse(
            status_code=404, content={"ok": False, "error": "Report JSON not available for this run."}
        )
    rep_data = _read_json(p) or {}
    from core.pdf_export import render_printable_report
    html_content = render_printable_report(
        rep_data,
        metadata={
            "run_id": run_id,
            "created_at": rep_data.get("generated_at", _now_iso()),
        },
    )
    return HTMLResponse(content=html_content, media_type="text/html; charset=utf-8")


@app.get("/api/export/{run_id}")
def api_export(run_id: str) -> JSONResponse:
    rdir = _run_dir(run_id)
    if rdir is None or not rdir.is_dir():
        return JSONResponse(status_code=404, content={"ok": False, "error": "Run not found."})
    rep_data = _read_json(rdir / "report.json") or {}
    reg_data = rep_data.get("meta", {}).get("regulatory", {})
    summary = rep_data.get("summary", {})
    return JSONResponse(
        content={
            "ok": True,
            "run_id": run_id,
            "summary": summary,
            "regulatory": reg_data,
            "deltas_count": len(rep_data.get("deltas", [])),
            "verify_items_count": len(rep_data.get("verify_list", [])),
            "links": {
                "report_html": f"/run/{run_id}/export/report",
                "report_json": f"/run/{run_id}/export/json",
                "report_print": f"/run/{run_id}/export/print",
                "viewer": f"/viewer/{run_id}/",
                "run_page": f"/run/{run_id}",
            },
        }
    )


@app.get("/runs/{run_id}/{name}")
def run_file(run_id: str, name: str) -> Response:
    rdir = _run_dir(run_id)
    if rdir is None or name not in RUN_FILE_WHITELIST:
        return JSONResponse(status_code=404, content={"ok": False, "error": "File not found."})
    p = rdir / name
    if not p.is_file():
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": f"{name} is not available for this run."},
        )
    media = RUN_FILE_MEDIA.get(p.suffix.lower(), "application/octet-stream")
    return FileResponse(p, media_type=media)


# --------------------------------------------------------------------------- #
# 3D viewer — serve render/viewer.html if it exists, otherwise a placeholder
# --------------------------------------------------------------------------- #
def _viewer_placeholder_html(run_id: str | None, message_en: str, message_np: str) -> str:
    run_line = f'<p class="muted">Run: <code>{run_id}</code></p>' if run_id else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Karmi — 3D view not available</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<main class="wrap" style="padding-top:48px">
  <div class="card placeholder-card">
    <h2>3D dual view — not available here yet</h2>
    {run_line}
    <p class="np" lang="ne">{message_np}</p>
    <p>{message_en}</p>
    <p><a href="/run/{run_id or ''}">&larr; Back to the run page</a></p>
  </div>
</main>
</body>
</html>"""


@app.get("/viewer/{run_id}/view.json")
def viewer_data(run_id: str) -> Response:
    """view.json in the viewer's own URL space (it fetches 'view.json' relative)."""
    rdir = _run_dir(run_id)
    if rdir is None or not rdir.is_dir():
        return JSONResponse(status_code=404, content={"ok": False, "error": "No such run."})
    p = rdir / "view.json"
    if not p.is_file():
        return JSONResponse(status_code=404,
                            content={"ok": False, "error": "No view data for this run."})
    return FileResponse(p, media_type="application/json")


@app.get("/viewer/{run_id}/vendor/{name}")
def viewer_vendor(run_id: str, name: str) -> Response:
    """Serve render/vendor/* inside the viewer's URL space.

    The viewer loads three.js as `./vendor/three.module.js`, which resolves to
    /viewer/<run_id>/vendor/... — without this route that request 404s and the page
    silently falls back to a CDN, so "offline 3D" would only work with a network.
    """
    safe = _safe_filename(name, "")
    if not safe or not safe.endswith(".js"):
        return JSONResponse(status_code=404, content={"ok": False, "error": "Not found."})
    base = (VIEWER_FILE.parent / "vendor").resolve()
    target = (base / safe).resolve()
    try:
        target.relative_to(base)  # refuse anything escaping render/vendor/
    except ValueError:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Not found."})
    if not target.is_file():
        return JSONResponse(status_code=404, content={"ok": False, "error": "Not found."})
    return FileResponse(target, media_type="text/javascript")


@app.get("/viewer/{run_id}", response_class=HTMLResponse)
@app.get("/viewer/{run_id}/", response_class=HTMLResponse)
def viewer(run_id: str) -> HTMLResponse:
    rdir = _run_dir(run_id)
    if rdir is None or not rdir.is_dir():
        return HTMLResponse(
            _viewer_placeholder_html(
                None,
                "This run does not exist, so there is nothing to render.",
                "यो रन भेटिएन, त्यसैले देखाउन केही छैन।",
            ),
            status_code=404,
        )
    if not VIEWER_FILE.is_file():
        return HTMLResponse(
            _viewer_placeholder_html(
                run_id,
                "The 3D viewer is not built yet in this checkout (render/viewer.html is "
                "missing). The data it will render is already saved for this run at "
                f'/runs/{run_id}/view.json.',
                "यो संस्करणमा 3D भ्युअर अझै बनेको छैन (render/viewer.html छैन)। यस रनको "
                "तथ्याङ्क भने तयार छ।",
            )
        )
    html = VIEWER_FILE.read_text(encoding="utf-8")
    # Shim: the viewer prefers `window.KARMI_VIEW` (an object); if absent it
    # fetches "view.json" relative to itself (served above). We provide both.
    shim = (
        "<script>"
        f"window.KARMI_RUN_ID={json.dumps(run_id)};"
        f"window.KARMI_VIEW_URL={json.dumps(f'/runs/{run_id}/view.json')};"
    )
    view_path = rdir / "view.json"
    if view_path.is_file() and view_path.stat().st_size < 8 * 1024 * 1024:
        view_data = _read_json(view_path)
        if view_data is not None:
            payload = json.dumps(view_data, ensure_ascii=False)
            payload = (payload.replace("<", "\\u003c")
                              .replace("\u2028", "\\u2028")
                              .replace("\u2029", "\\u2029"))
            shim += f"window.KARMI_VIEW={payload};"
    shim += "</script>"
    if re.search(r"<head[^>]*>", html, re.IGNORECASE):
        # NB: lambda replacement — a plain replacement string would eat the
        # backslashes inside the JSON shim (re.sub escape processing).
        html = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + "\n" + shim,
                      html, count=1, flags=re.IGNORECASE)
    else:
        html = shim + "\n" + html
    return HTMLResponse(html)


# --------------------------------------------------------------------------- #
# health & favicon
# --------------------------------------------------------------------------- #
@app.get("/healthz")
def healthz() -> JSONResponse:
    core_ok, core_error = True, None
    try:
        import importlib

        importlib.import_module("core.pipeline")
    except Exception as exc:  # noqa: BLE001
        core_ok, core_error = False, f"{type(exc).__name__}: {exc}"
    return JSONResponse(
        content={
            "ok": True,
            "service": "karmi-web",
            "version": app.version,
            "runs_dir": str(RUNS_DIR),
            "runs": len(_list_runs(limit=1000)),
            "viewer_available": VIEWER_FILE.is_file(),
            "core_available": core_ok,
            "core_error": core_error,
        }
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# run page context builder
# --------------------------------------------------------------------------- #
def _enrich_deltas(report: Any, scene: Any, observed: Any) -> list[dict[str, Any]]:
    scene_prov: dict[str, str] = {}
    if isinstance(scene, dict):
        for bucket in ("walls", "openings", "rooms", "dimensions"):
            for el in scene.get(bucket) or []:
                if isinstance(el, dict) and el.get("id"):
                    p = el.get("provenance") or {}
                    scene_prov[str(el["id"])] = str(p.get("source") or "")
    observed_prov: dict[str, str] = {}
    if isinstance(observed, dict):
        for el in observed.get("elements") or []:
            if isinstance(el, dict) and el.get("id"):
                p = el.get("provenance") or {}
                observed_prov[str(el["id"])] = str(p.get("source") or "")

    out: list[dict[str, Any]] = []
    if not isinstance(report, dict):
        return out
    for d in report.get("deltas") or []:
        if not isinstance(d, dict):
            continue
        sev = str(d.get("severity") or "info").lower()
        if sev not in SEVERITY_RANK:
            sev = "info"
        conf = max(0.0, min(1.0, _safe_float(d.get("confidence"), 0.0)))
        row = dict(d)
        row["sev"] = sev
        row["sev_rank"] = SEVERITY_RANK[sev]
        row["status"] = str(d.get("status") or "unverifiable")
        row["status_label"] = STATUS_LABELS.get(row["status"], row["status"])
        row["conf_pct"] = round(conf * 100)
        row["scene_src"] = scene_prov.get(str(d.get("scene_ref") or ""))
        row["observed_src"] = observed_prov.get(str(d.get("observed_ref") or ""))
        row["element"] = d.get("element") or d.get("id") or "(unnamed element)"
        out.append(row)
    out.sort(key=lambda r: (r["sev_rank"], STATUS_ORDER.get(r["status"], 9), str(r.get("id"))))
    return out


def _enrich_verify(report: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(report, dict):
        return out
    for v in report.get("verify_list") or []:
        if not isinstance(v, dict):
            continue
        sev = str(v.get("severity") or "info").lower()
        if sev not in SEVERITY_RANK:
            sev = "info"
        row = dict(v)
        row["sev"] = sev
        row["sev_rank"] = SEVERITY_RANK[sev]
        out.append(row)
    out.sort(key=lambda r: r["sev_rank"])
    return out


def _run_context(request: Request, run_id: str, rdir: Path) -> dict[str, Any]:
    manifest = _read_json(rdir / "run.json") or {}
    if not isinstance(manifest, dict):
        manifest = {}
    report = _read_json(rdir / "report.json")
    scene = _read_json(rdir / "scene.json")
    observed = _read_json(rdir / "observed.json")
    uploads = _read_json(rdir / "uploads.json") or {}
    if not isinstance(uploads, dict):
        uploads = {}
    result = manifest.get("result") or {}
    if not isinstance(result, dict):
        result = {}

    deltas = _enrich_deltas(report, scene, observed)
    verify = _enrich_verify(report)

    # summary always matches what the table actually shows
    if deltas:
        counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
        for d in deltas:
            counts[d["sev"]] += 1
        counts["total"] = len(deltas)
        counts["matched"] = sum(1 for d in deltas if d.get("status") == "matched")
        counts["verify_items"] = len(verify)
        summary = counts
    else:
        raw = {}
        if isinstance(report, dict) and isinstance(report.get("summary"), dict):
            raw = report["summary"]
        elif isinstance(result.get("summary"), dict):
            raw = result["summary"]
        summary = {k: _safe_int(raw.get(k)) for k in
                   ("high", "medium", "low", "info", "total", "matched", "verify_items")}

    scene_info = None
    if isinstance(scene, dict):
        scale_prov = scene.get("scale_provenance") or {}
        scene_info = {
            "source_kind": scene.get("source_kind"),
            "walls": len(scene.get("walls") or []),
            "openings": len(scene.get("openings") or []),
            "rooms": len(scene.get("rooms") or []),
            "dimensions": len(scene.get("dimensions") or []),
            "warnings": scene.get("warnings") or [],
            "scale_m_per_unit": scene.get("scale_m_per_unit"),
            "scale_source": scale_prov.get("source"),
            "scale_confidence": scale_prov.get("confidence"),
        }
    observed_info = None
    if isinstance(observed, dict):
        stage_prov = observed.get("stage_provenance") or {}
        observed_info = {
            "stage": observed.get("stage"),
            "captures": len(observed.get("captures") or []),
            "elements": len(observed.get("elements") or []),
            "scale_refs": len(observed.get("scale_refs") or []),
            "warnings": observed.get("warnings") or [],
            "stage_source": stage_prov.get("source"),
            "stage_confidence": stage_prov.get("confidence"),
        }

    stage_hint = uploads.get("stage_hint")
    if not stage_hint and isinstance(observed, dict):
        stage_hint = observed.get("stage")

    return {
        "request": request,
        "run_id": run_id,
        "manifest": manifest,
        "result": result,
        "report": report if isinstance(report, dict) else None,
        "uploads": uploads,
        "summary": summary,
        "deltas": deltas,
        "verify": verify,
        "limits": (report or {}).get("limits") or [] if isinstance(report, dict) else [],
        "standing_limits": STANDING_LIMITS,
        "narration_np": (report or {}).get("narration_np") or [] if isinstance(report, dict) else [],
        "narration_en": (report or {}).get("narration_en") or [] if isinstance(report, dict) else [],
        "errors": result.get("errors") or [],
        "warnings": result.get("warnings") or [],
        "timings_ms": result.get("timings_ms") or {},
        "generated_at": manifest.get("generated_at"),
        "drawing_name": Path(str(manifest.get("drawing") or "")).name,
        "known_dimension": manifest.get("known_dimension_m"),
        "photos_count": len(manifest.get("photos") or []),
        "ai_provider": manifest.get("ai_provider") or "none",
        "stage_label": STAGE_LABELS.get(str(stage_hint or ""), stage_hint),
        "scene_info": scene_info,
        "observed_info": observed_info,
        "viewer_state": _viewer_state(rdir),
        "has_report_html": (rdir / "report.html").is_file(),
        "has_report_md": (rdir / "report.md").is_file(),
        "has_view_json": (rdir / "view.json").is_file(),
        "links": _links(run_id),
        "severity_labels": SEVERITY_LABELS,
        "severity_rank": SEVERITY_RANK,
    }


# --------------------------------------------------------------------------- #
# exception handlers — every error becomes something a person can read
# --------------------------------------------------------------------------- #
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    if request.url.path.startswith("/api/") or request.url.path == "/healthz":
        messages = {
            404: "Not found. Check the run id.",
            405: "That request method is not allowed here.",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "error": messages.get(exc.status_code, str(exc.detail))},
        )
    return _error_page(
        request,
        exc.status_code,
        "Page not found" if exc.status_code == 404 else "Request failed",
        "That page does not exist in Karmi." if exc.status_code == 404
        else str(exc.detail),
        "त्यो पृष्ठ कर्मीमा छैन।" if exc.status_code == 404 else "",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> Response:
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "error": "The upload was not complete. Attach the drawing and try again.",
            "error_np": "अपलोड अपूर्ण थियो। नक्सा संलग्न गरेर फेरि प्रयास गर्नुहोस्।",
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    traceback.print_exc()
    if request.url.path.startswith("/api/") or request.url.path == "/healthz":
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "Something went wrong inside Karmi. The details are in the server log.",
                "error_np": "कर्मीभित्र समस्या आयो — विवरण सर्भर लगमा छ।",
                "detail": f"{type(exc).__name__}: {exc}"[:300],
            },
        )
    return _error_page(
        request,
        500,
        "Something went wrong",
        "Karmi hit an unexpected error. Nothing was lost — try again from the home page.",
        "कर्मीमा अनपेक्षित समस्या आयो — गृहपृष्ठबाट फेरि प्रयास गर्नुहोस्।",
    )


# --------------------------------------------------------------------------- #
# static files & entry point
# --------------------------------------------------------------------------- #
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main() -> None:
    import uvicorn

    host = os.environ.get("KARMI_HOST", "127.0.0.1")
    port = int(os.environ.get("KARMI_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()