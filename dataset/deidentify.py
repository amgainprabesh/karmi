"""Karmi dataset — real de-identification (runs, not a description).

What actually happens here
--------------------------
``deidentify_photo(path, out_path)``
    Container-level EXIF/GPS removal via :func:`core.validate.strip_exif`
    (JPEG APP1/APP12/APP13/COM, PNG eXIf/tEXt, WebP EXIF/XMP chunks). The
    decoded pixels are verified bit-for-bit unchanged by hashing them before
    and after — both hashes go in the report.
``deidentify_drawing(path, out_path)``
    * PDF: text is extracted with PyMuPDF, ``core.validate.find_pii_candidates``
      finds names / phones / emails / NEC numbers / ward-kitta (English and
      Devanagari) per page; the module writes (a) a machine-readable report
      saying what was found and where, (b) a redacted **text copy**, and
      (c) a **cleaned PDF copy** with the matched text physically redacted and
      the document metadata blanked. A verification pass re-extracts text from
      the cleaned copy and reports any residual matches honestly.
    * image (a scanned drawing): same path as photos — EXIF strip + report.
``scan_record(record)``
    Walks every string field of a :class:`dataset.schema.DatasetRecord`
    (including nested ``meta`` dicts and lists) through
    ``find_pii_candidates`` and returns :class:`Finding` objects with the
    field path, category and a **masked** preview.

Privacy choices
---------------
* Findings carry a *masked* preview (``98…00``), never the raw match: a
  de-identification report that repeats the PII it removed would itself be a
  leak. ``include_matches=True`` is available for local review only and is
  never used for release artefacts.
* Reports store file *names* and SHA-256 hashes, not absolute paths
  (SECURITY.md T6: absolute paths leak the contributor's machine layout).
* Honest limits (SECURITY.md T7, dataset-plan §5): the heuristics are
  best-effort; a name written without a title is not caught; a floor plan is
  itself quasi-identifying. Human review of 100% of released pages is required
  for v0.x — this module narrows the problem, it does not eliminate it.

CLI
---
::

    python -m dataset.deidentify fixtures/photos/front_walls_stage.jpg
    python -m dataset.deidentify drawing.pdf --out dataset/deid_out/drawing.redacted.txt
    python -m dataset.deidentify --scan-record dataset/example/karmi-example-0001.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, Field

from core.validate import (
    UnsafeInput,
    find_pii_candidates,
    redact,
    strip_exif,
    validate_upload,
)

__all__ = [
    "Finding",
    "DeidReport",
    "deidentify_photo",
    "deidentify_drawing",
    "scan_record",
    "scan_text",
    "redact_spans",
]

#: Categories are the labels of core.validate's own pattern table; we read it
#: (rather than forking the regexes) so detection and labelling cannot drift.
_PII_PATTERNS_ATTR = "_PII_PATTERNS"


# --------------------------------------------------------------------------- #
# models
# --------------------------------------------------------------------------- #
class Finding(BaseModel):
    """One likely-PII hit. The raw match is deliberately not stored."""

    location: str = Field(description="page / field path where the match sits")
    category: str = Field(description="pattern label from core.validate, e.g. 'phone_mobile'")
    masked: str = Field(description="masked preview, e.g. '98…00' — never the raw match")
    length: int
    offset: int | None = Field(None, description="character offset within the location, when known")
    context: str | None = Field(
        None, description="masked surrounding text (only with include_matches=True, for local review)"
    )


class DeidReport(BaseModel):
    """Machine-readable de-identification report (safe to store/share)."""

    schema_id: str = Field("karmi-deid-report/0.1.0", alias="schema")
    kind: str = Field(description="photo | drawing_image | drawing_pdf | record_scan")
    source_name: str = Field(description="file NAME only — never an absolute path")
    source_sha256: str | None = None
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    findings: list[Finding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    pixel_sha256_before: str | None = None
    pixel_sha256_after: str | None = None
    pixels_unchanged: bool | None = Field(
        None, description="decoded pixels identical before/after (container-level strip)"
    )
    outputs: list[str] = Field(default_factory=list, description="file names written")
    notes: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    def to_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2
        )

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json() + "\n", encoding="utf-8")
        return p


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pixel_sha256(path: Path) -> str:
    """SHA-256 of the decoded pixel bytes (mode-aware)."""
    from PIL import Image

    with Image.open(path) as im:
        im.load()
        return hashlib.sha256(im.tobytes()).hexdigest()


def _mask(token: str, keep: int = 2) -> str:
    t = token.strip()
    if len(t) <= 4:
        return "*" * len(t)
    return t[:keep] + "…" + t[-keep:]


def _pii_category(token: str) -> str:
    """Label a match with the core.validate pattern that produced it."""
    try:
        from core import validate as _v

        patterns = getattr(_v, _PII_PATTERNS_ATTR, None)
    except Exception:  # noqa: BLE001 — labelling is best-effort
        patterns = None
    if patterns:
        for label, pat in patterns:
            try:
                if pat.search(token):
                    return label
            except Exception:  # noqa: BLE001
                continue
    return "unknown_pii"


def scan_text(
    text: str | None,
    location: str,
    *,
    include_matches: bool = False,
    context_chars: int = 40,
) -> list[Finding]:
    """Run the core.validate PII heuristics over one piece of text."""
    if not text:
        return []
    out: list[Finding] = []
    for cand in find_pii_candidates(text):
        start = 0
        while True:
            idx = text.find(cand, start)
            if idx < 0:
                break
            context = None
            if include_matches and context_chars > 0:
                lo = max(0, idx - context_chars)
                hi = min(len(text), idx + len(cand) + context_chars)
                context = _mask(text[lo:hi], keep=6)
            out.append(
                Finding(
                    location=location,
                    category=_pii_category(cand),
                    masked=_mask(cand),
                    length=len(cand),
                    offset=idx,
                    context=context,
                )
            )
            start = idx + len(cand)
            if len(out) >= 500:  # safety valve on pathological text
                return out
    return out


def redact_spans(
    text: str,
    candidates: Sequence[str],
    placeholder: str = "[REDACTED]",
) -> str:
    """Replace every candidate occurrence, merging overlapping match spans.

    Detection is entirely ``core.validate.find_pii_candidates`` — nothing is
    re-implemented. Replacement delegates to ``core.validate.redact`` when the
    matches do not overlap. When they DO overlap it merges the spans first,
    because token-level replacement can leave a fragment behind: a real case
    found in testing is ``"Er. Example Only\\nNEC No. 99999"`` where the
    engineer-name pattern swallows the following ``NEC No.`` — replacing the
    long token first leaves ``99999`` in the text. Merging spans removes the
    whole region. (Reported as a limitation for whoever next touches
    ``core/validate.py``.)
    """
    spans: list[tuple[int, int]] = []
    for cand in {str(c) for c in candidates if c}:
        start = 0
        while True:
            i = text.find(cand, start)
            if i < 0:
                break
            spans.append((i, i + len(cand)))
            start = i + len(cand)
    if not spans:
        return text
    spans.sort()
    overlaps = any(spans[i][0] < spans[i - 1][1] for i in range(1, len(spans)))
    if not overlaps:
        return redact(text, candidates, placeholder)  # the core primitive

    merged: list[list[int]] = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out: list[str] = []
    prev = 0
    for s, e in merged:
        out.append(text[prev:s])
        out.append(placeholder)
        prev = e
    out.append(text[prev:])
    return "".join(out)


def _exif_summary(path: Path) -> dict[str, Any]:
    from PIL import Image, ExifTags

    fields: list[str] = []
    gps_fields: list[str] = []
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            fields = sorted(str(ExifTags.TAGS.get(k, k)) for k in exif.keys())
            try:
                gps = exif.get_ifd(0x8825)
            except Exception:  # noqa: BLE001
                gps = {}
            gps_fields = sorted(str(ExifTags.GPSTAGS.get(k, k)) for k in (gps or {}))
    except Exception:  # noqa: BLE001 — metadata inspection must not fail the run
        pass
    return {
        "exif_present": bool(fields),
        "gps_present": bool(gps_fields),
        "fields": fields,
        "gps_fields": gps_fields,
    }


# --------------------------------------------------------------------------- #
# images (photos and scanned drawings)
# --------------------------------------------------------------------------- #
def _deidentify_image(path: Path, out_path: Path, kind: str) -> DeidReport:
    before = _exif_summary(path)
    px_before = _pixel_sha256(path)
    cleaned = strip_exif(path, out_path)  # raises UnsafeInput if anything is off
    after = _exif_summary(cleaned)
    px_after = _pixel_sha256(cleaned)

    removed = sorted(set(before["fields"]) - set(after["fields"]))
    notes = [
        "Container-level metadata strip (core.validate.strip_exif): decoded pixel "
        "data is bit-for-bit identical; the two pixel hashes below prove it.",
        "Metadata is only half of photo privacy: people and number plates must be "
        "excluded or blurred by human review before release (dataset-plan §5).",
    ]
    if before["gps_present"]:
        notes.append(
            f"GPS was present before stripping ({', '.join(before['gps_fields'])}) "
            "and is absent from the cleaned copy."
        )
    elif not before["exif_present"]:
        notes.append("No EXIF metadata was present on the source file; strip is a no-op.")

    return DeidReport(
        kind=kind,
        source_name=path.name,
        source_sha256=_sha256_file(path),
        findings=[],
        metadata={
            "exif_present_before": before["exif_present"],
            "gps_present_before": before["gps_present"],
            "exif_present_after": after["exif_present"],
            "gps_present_after": after["gps_present"],
            "exif_fields_before": before["fields"],
            "exif_fields_removed": removed,
            "gps_fields_removed": before["gps_fields"],
        },
        pixel_sha256_before=px_before,
        pixel_sha256_after=px_after,
        pixels_unchanged=(px_before == px_after),
        outputs=[cleaned.name],
        notes=notes,
    )


def deidentify_photo(path: str | Path, out_path: str | Path | None = None) -> DeidReport:
    """Strip EXIF/GPS from one site photo; verify pixels unchanged. Returns a report."""
    p = Path(path)
    if not p.is_file():
        raise UnsafeInput(f"file does not exist: {p}", code="not_found")
    out = Path(out_path) if out_path is not None else p.with_name(p.stem + ".clean" + p.suffix.lower())
    return _deidentify_image(p, out, kind="photo")


# --------------------------------------------------------------------------- #
# PDFs (drawing sets)
# --------------------------------------------------------------------------- #
def _deidentify_pdf(path: Path, out_path: Path) -> DeidReport:
    import pymupdf

    info = validate_upload(path)  # fail closed on untrusted input
    if info["kind"] != "pdf":
        raise UnsafeInput(f"not a PDF: {path.name}", code="magic_mismatch")

    doc = pymupdf.open(str(path))
    if doc.is_encrypted or getattr(doc, "needs_pass", 0):
        doc.close()
        raise UnsafeInput("PDF is encrypted; cannot de-identify", code="pdf_encrypted")

    text_out = out_path
    clean_pdf = text_out.with_name(text_out.stem + ".clean.pdf")

    findings: list[Finding] = []
    page_texts: list[str] = []
    n_boxes = 0
    unlocated: list[str] = []
    n_candidates = 0

    for i, page in enumerate(doc):
        text = page.get_text("text")
        page_texts.append(text)
        cands = find_pii_candidates(text)
        n_candidates += len(cands)
        for cand in cands:
            findings.append(
                Finding(
                    location=f"page {i + 1}",
                    category=_pii_category(cand),
                    masked=_mask(cand),
                    length=len(cand),
                    offset=text.find(cand),
                )
            )
            rects = page.search_for(cand)
            if not rects:
                unlocated.append(f"page {i + 1}: {_mask(cand)} ({_pii_category(cand)})")
            for r in rects:
                page.add_redact_annot(r, fill=(0, 0, 0))
                n_boxes += 1
        if cands:
            page.apply_redactions()

    # -- document metadata: scan it, then blank it --------------------------- #
    meta = dict(doc.metadata or {})
    scrubbed_keys: list[str] = []
    for key, value in meta.items():
        if value and str(value).strip():
            scrubbed_keys.append(key)
            for cand in find_pii_candidates(str(value)):
                findings.append(
                    Finding(
                        location=f"metadata.{key}",
                        category=_pii_category(cand),
                        masked=_mask(cand),
                        length=len(cand),
                    )
                )
    doc.set_metadata(
        {
            "title": "", "author": "", "subject": "", "keywords": "",
            "creator": "", "producer": "", "creationDate": "", "modDate": "",
        }
    )

    # -- write outputs -------------------------------------------------------- #
    text_out.parent.mkdir(parents=True, exist_ok=True)
    redacted_text = "\n\f\n".join(redact_spans(t, find_pii_candidates(t)) for t in page_texts)
    text_out.write_text(redacted_text, encoding="utf-8")
    try:
        doc.save(str(clean_pdf), garbage=3, deflate=True)
    except Exception:  # noqa: BLE001 — fall back to a plain save
        doc.save(str(clean_pdf))
    doc.close()

    # -- verification pass: re-extract text from the cleaned PDF ------------- #
    with pymupdf.open(str(clean_pdf)) as v:
        residual_text = "".join(p.get_text("text") for p in v)
    residual = find_pii_candidates(residual_text)
    for cand in residual:
        findings.append(
            Finding(
                location="cleaned-pdf verification",
                category=_pii_category(cand),
                masked=_mask(cand),
                length=len(cand),
            )
        )

    notes = [
        "The original PDF is never published (dataset-plan §5): the release uses the "
        "redacted text copy and the cleaned PDF copy produced here.",
        "Automated redaction is best-effort; a human reviews 100% of released pages "
        "while the dataset is small (dataset-plan §5).",
    ]
    if not "".join(page_texts).strip():
        notes.append("The PDF has no text layer (raster/scan); no text PII was found by this pass.")
    if unlocated:
        notes.append(
            "Some candidates could not be located for in-PDF redaction (search_for "
            "returned no rectangle) — the redacted text copy still removes them: "
            + "; ".join(unlocated)
        )
    if residual:
        notes.append(
            "VERIFY: the cleaned PDF still matches some patterns after redaction — "
            "review before release."
        )
    if scrubbed_keys:
        notes.append(f"PDF metadata fields scrubbed: {', '.join(scrubbed_keys)}.")

    return DeidReport(
        kind="drawing_pdf",
        source_name=path.name,
        source_sha256=info["sha256"],
        findings=findings,
        metadata={
            "pages": len(page_texts),
            "text_chars": sum(len(t) for t in page_texts),
            "pii_candidates_found": n_candidates,
            "redaction_boxes_applied": n_boxes,
            "pdf_metadata_fields_scrubbed": scrubbed_keys,
            "residual_matches_after_redaction": len(residual),
        },
        outputs=[text_out.name, clean_pdf.name],
        notes=notes,
    )


def deidentify_drawing(path: str | Path, out_path: str | Path | None = None) -> DeidReport:
    """De-identify a naksa drawing (PDF) or a scanned drawing image.

    For PDFs, ``out_path`` is the **redacted text copy** to write; a cleaned
    PDF copy is written alongside it (``<stem>.clean.pdf``). For images,
    ``out_path`` is the EXIF-stripped copy. Returns the report.
    """
    p = Path(path)
    if not p.is_file():
        raise UnsafeInput(f"file does not exist: {p}", code="not_found")
    info = validate_upload(p)
    if info["kind"] == "pdf":
        out = Path(out_path) if out_path is not None else p.with_name(p.stem + ".redacted.txt")
        return _deidentify_pdf(p, out)
    out = Path(out_path) if out_path is not None else p.with_name(p.stem + ".clean" + p.suffix.lower())
    return _deidentify_image(p, out, kind="drawing_image")


# --------------------------------------------------------------------------- #
# whole-record scan
# --------------------------------------------------------------------------- #
def _walk_strings(obj: Any, path: str, findings: list[Finding], include_matches: bool) -> None:
    if isinstance(obj, str):
        findings.extend(scan_text(obj, path, include_matches=include_matches))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk_strings(v, f"{path}.{k}", findings, include_matches)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _walk_strings(v, f"{path}[{i}]", findings, include_matches)


def scan_record(record: Any, *, include_matches: bool = False) -> list[Finding]:
    """Scan **every free-text field** of a dataset record for PII candidates.

    Walks the serialized record recursively (nested ``meta`` dicts included) and
    runs ``core.validate.find_pii_candidates`` on every string. Returns
    de-duplicated findings with a field path such as
    ``karmi-0001.drawing.scene.rooms[2].name_np``.
    """
    data = record.model_dump(mode="json")
    raw: list[Finding] = []
    _walk_strings(data, record.record_id, raw, include_matches)
    seen: set[tuple[str, str, str]] = set()
    out: list[Finding] = []
    for f in raw:
        key = (f.location, f.category, f.masked)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _default_out_dir() -> Path:
    """All CLI output lands under dataset/ — never next to the user's originals."""
    return Path(__file__).resolve().parent / "deid_out"


def _render(report: DeidReport) -> str:
    lines = [
        f"Karmi de-identify — {report.kind}  ({report.source_name})",
        f"  findings: {len(report.findings)}",
    ]
    for f in report.findings[:20]:
        loc = f" @ {f.offset}" if f.offset is not None else ""
        lines.append(f"    - [{f.category}] {f.masked}  ({f.location}{loc})")
    if len(report.findings) > 20:
        lines.append(f"    … and {len(report.findings) - 20} more")
    if report.pixel_sha256_before is not None:
        lines.append(f"  pixels unchanged: {report.pixels_unchanged}")
        lines.append(f"    before: {report.pixel_sha256_before}")
        lines.append(f"    after:  {report.pixel_sha256_after}")
    md = report.metadata
    if "gps_present_before" in md:
        lines.append(
            f"  GPS: before={md['gps_present_before']} after={md['gps_present_after']} "
            f"(exif removed: {', '.join(md['exif_fields_removed']) or 'none'})"
        )
    if "pages" in md:
        lines.append(
            f"  pages: {md['pages']}, PII candidates: {md['pii_candidates_found']}, "
            f"redaction boxes: {md['redaction_boxes_applied']}, "
            f"residual after redaction: {md['residual_matches_after_redaction']}"
        )
    if report.outputs:
        lines.append(f"  outputs: {', '.join(report.outputs)}")
    for n in report.notes:
        lines.append(f"  note: {n}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m dataset.deidentify",
        description="De-identify a drawing/photo before it enters the dataset, or "
        "scan a whole record for PII candidates.",
    )
    ap.add_argument("path", nargs="?", help="PDF or image to de-identify")
    ap.add_argument("--out", default=None, help="output path (default: dataset/deid_out/)")
    ap.add_argument(
        "--kind",
        choices=["photo", "drawing"],
        default="photo",
        help="how to label an IMAGE input (PDFs are always 'drawing')",
    )
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument(
        "--scan-record", metavar="RECORD.json",
        help="scan a dataset record JSON for PII candidates instead of a file",
    )
    ap.add_argument("--include-matches", action="store_true",
                    help="local review only: add masked context around each match")
    ap.add_argument("--strict", action="store_true",
                    help="with --scan-record: exit 1 when findings exist")
    args = ap.parse_args(argv)

    # -- record scan mode ---------------------------------------------------- #
    if args.scan_record:
        from dataset.schema import DatasetRecord

        rp = Path(args.scan_record)
        if not rp.is_file():
            print(f"error: record not found: {rp}", file=sys.stderr)
            return 2
        record = DatasetRecord.model_validate_json(rp.read_text(encoding="utf-8"))
        findings = scan_record(record, include_matches=args.include_matches)
        if args.json:
            print(json.dumps([f.model_dump() for f in findings], ensure_ascii=False, indent=2))
        else:
            print(f"Karmi de-identify — record scan  ({rp.name}, id={record.record_id})")
            print(f"  findings: {len(findings)}")
            for f in findings:
                loc = f" @ {f.offset}" if f.offset is not None else ""
                print(f"    - [{f.category}] {f.masked}  ({f.location}{loc})")
        return 1 if (args.strict and findings) else 0

    if not args.path:
        ap.print_help()
        return 2
    src = Path(args.path)
    if not src.is_file():
        print(f"error: file not found: {src}", file=sys.stderr)
        return 2

    out_dir = _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        info = validate_upload(src)
        if info["kind"] == "pdf":
            out = Path(args.out) if args.out else out_dir / (src.stem + ".redacted.txt")
            report = deidentify_drawing(src, out)
        else:
            out = Path(args.out) if args.out else out_dir / (src.stem + ".clean" + src.suffix.lower())
            if args.kind == "drawing":
                report = deidentify_drawing(src, out)
            else:
                report = deidentify_photo(src, out)
    except UnsafeInput as exc:
        print(f"REJECTED  {src.name}: {exc.reason}", file=sys.stderr)
        return 2

    report_path = out_dir / (Path(report.outputs[0]).stem + ".deid-report.json") \
        if report.outputs else out_dir / (src.stem + ".deid-report.json")
    report.save(report_path)

    if args.json:
        print(report.to_json())
    else:
        print(_render(report))
        print(f"  report written: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())