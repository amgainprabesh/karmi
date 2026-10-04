"""Privacy & uploads — user paths stay out of run manifests, hostile uploads are
rejected, PII is detectable, and model-derived text cannot inject raw HTML into
the report renderer.

Covers the recently-changed behaviours:

* ``core.pipeline`` stores RELATIVE paths in run.json (``_display_path``) — a
  shared run folder must not leak the user's home directory, username, or a
  drive letter;
* ``core.validate.validate_upload`` rejects a text file renamed ``.pdf`` and an
  oversized file, and accepts the real fixtures (PDF and photo);
* ``safe_filename`` neutralises ``../``, Windows reserved device names and
  bidi-override characters, and composes with ``safe_join`` as documented;
* ``find_pii_candidates`` finds a Nepali mobile number, an email and an
  NEC-style registration number, and ``redact`` removes them;
* ``sanitize_model_text`` strips control characters and escapes HTML, and the
  HTML report renderer's output contains no raw ``<script>`` when a reason
  field carries one.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import unicodedata
from pathlib import Path

import pytest

from conftest import make_observed, make_report, make_scene, require, require_attr

pipeline_mod = require(
    "core.pipeline",
    reason="core.pipeline is not importable yet — skipping the privacy/upload tests",
)
validate_mod = require(
    "core.validate",
    reason="core.validate is not importable yet (being written in parallel) — skipping the upload tests",
)
observe_mod = require(
    "core.observe",
    reason="core.observe is not importable yet — skipping the sidecar-discovery test",
)

_RESERVED_STEMS = {
    "CON", "PRN", "AUX", "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 10)},
}

_HOSTILE_NAMES = [
    "../evil.pdf",
    "..\\evil.pdf",
    "a/b/c.pdf",
    "../../etc/passwd",
    "CON.pdf",
    "con",
    "COM1.txt",
    "LPT9",
    "na\u202emes.pdf",          # RTL override
    "ph\u2066oto\u2069.jpg",    # LRI / PDI isolates
    "\u202e\u202e.pdf",
    "..",
]

_BIDI_OVERRIDES = ("\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
                   "\u2066", "\u2067", "\u2068", "\u2069")


def _photo(tmp_path: Path, fixtures_dir: Path) -> Path:
    """A real JPEG copied out of the repo fixtures (or a generated fallback)."""
    dest = tmp_path / "front_walls_stage.jpg"
    source = fixtures_dir / "photos" / "front_walls_stage.jpg"
    if source.is_file():
        shutil.copyfile(source, dest)
        return dest
    PIL_Image = pytest.importorskip("PIL.Image", reason="no photo fixture and Pillow is missing")
    PIL_Image.new("RGB", (16, 16), (120, 120, 120)).save(dest, "JPEG")
    return dest


# --------------------------------------------------------------------------- #
# run.json must not leak the user's filesystem layout
# --------------------------------------------------------------------------- #
def test_run_manifest_paths_are_relative_and_private(naksa_base, fixtures_dir, tmp_run_dir, tmp_path):
    if not Path(naksa_base).is_file():
        pytest.skip("naksa_base.pdf fixture is missing")
    run_pipeline = require_attr(pipeline_mod, "run_pipeline")
    photo = _photo(tmp_path, fixtures_dir)

    run_pipeline(naksa_base, [photo], out_dir=tmp_run_dir)

    manifest_path = tmp_run_dir / "run.json"
    assert manifest_path.is_file(), "run_pipeline did not write run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest.get("drawing"), f"run.json has no drawing field: {sorted(manifest)}"
    photos = manifest.get("photos")
    assert isinstance(photos, list) and len(photos) == 1, f"run.json photos: {photos!r}"

    home = Path.home()
    forbidden = {str(home), home.name, os.environ.get("USERNAME", ""), os.environ.get("USER", "")}
    forbidden = {token for token in forbidden if token}

    for value in [manifest["drawing"], *photos]:
        assert isinstance(value, str) and value.strip(), f"run.json path is not a string: {value!r}"
        assert not os.path.isabs(value), f"run.json leaked an absolute path: {value!r}"
        assert not Path(value).is_absolute(), f"run.json leaked an absolute path: {value!r}"
        assert ":" not in value, f"run.json leaked a drive letter / stream separator: {value!r}"
        for token in forbidden:
            assert token.lower() not in value.lower(), (
                f"run.json leaked {token!r} (home dir / username) in {value!r}"
            )


# --------------------------------------------------------------------------- #
# validate_upload — content over name, size limits, real fixtures accepted
# --------------------------------------------------------------------------- #
def test_validate_upload_rejects_text_renamed_pdf(tmp_path):
    validate_upload = require_attr(validate_mod, "validate_upload")
    UnsafeInput = require_attr(validate_mod, "UnsafeInput")
    fake = tmp_path / "drawing.pdf"
    fake.write_text("Plain text wearing a .pdf extension — not a drawing.", encoding="utf-8")
    with pytest.raises(UnsafeInput) as excinfo:
        validate_upload(fake)
    assert excinfo.value.code == "magic_mismatch", (
        f"a renamed text file should fail the magic-byte check: {excinfo.value.code!r}"
    )


def test_validate_upload_rejects_an_oversized_file(tmp_path):
    validate_upload = require_attr(validate_mod, "validate_upload")
    UnsafeInput = require_attr(validate_mod, "UnsafeInput")
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * 4096)
    with pytest.raises(UnsafeInput) as excinfo:
        validate_upload(big, max_bytes=1024)
    assert excinfo.value.code == "too_large"


def test_validate_upload_accepts_the_real_pdf_fixture(naksa_base):
    if not Path(naksa_base).is_file():
        pytest.skip("naksa_base.pdf fixture is missing")
    validate_upload = require_attr(validate_mod, "validate_upload")
    info = validate_upload(naksa_base)
    assert info["ok"] is True
    assert info["kind"] == "pdf"
    assert info["pages"] >= 1
    assert re.fullmatch(r"[0-9a-f]{64}", info["sha256"]), f"bad sha256: {info['sha256']!r}"


def test_validate_upload_accepts_the_real_photo_fixture(fixtures_dir):
    photo = fixtures_dir / "photos" / "front_walls_stage.jpg"
    if not photo.is_file():
        pytest.skip("front_walls_stage.jpg fixture is missing")
    validate_upload = require_attr(validate_mod, "validate_upload")
    # the same allow-list the web upload path uses for photos
    info = validate_upload(photo, allowed={"jpg", "jpeg", "png", "webp"})
    assert info["ok"] is True
    assert info["kind"] == "image"
    assert info["image"]["format"] == "JPEG"


# --------------------------------------------------------------------------- #
# safe_filename + safe_join (the documented compose pattern)
# --------------------------------------------------------------------------- #
def test_safe_filename_neutralises_hostile_names_and_composes_with_safe_join(tmp_path):
    safe_filename = require_attr(validate_mod, "safe_filename")
    safe_join = require_attr(validate_mod, "safe_join")
    base = tmp_path / "uploads"
    base.mkdir()
    base_resolved = base.resolve()

    for raw in _HOSTILE_NAMES:
        name = safe_filename(raw)
        assert isinstance(name, str) and name.strip(), f"safe_filename({raw!r}) -> {name!r}"
        assert "/" not in name and "\\" not in name, (
            f"safe_filename({raw!r}) = {name!r} still contains a path separator"
        )
        assert ".." not in name, f"safe_filename({raw!r}) = {name!r} still contains '..'"
        assert not any(ch in name for ch in _BIDI_OVERRIDES), (
            f"safe_filename({raw!r}) = {name!r} still contains a bidi override"
        )
        assert not any(unicodedata.category(ch).startswith("C") for ch in name), (
            f"safe_filename({raw!r}) = {name!r} still contains control/format characters"
        )
        stem = name.partition(".")[0].upper()
        assert stem not in _RESERVED_STEMS, (
            f"safe_filename({raw!r}) = {name!r} is still a Windows reserved name"
        )

        joined = safe_join(base, name)
        resolved = Path(joined).resolve()
        assert resolved == base_resolved or base_resolved in resolved.parents, (
            f"safe_join(base, safe_filename({raw!r})) escaped the base dir: {resolved}"
        )

    # a normal name still works
    assert "naksa_plan_v2" in safe_filename("naksa_plan_v2.pdf")


# --------------------------------------------------------------------------- #
# PII detection + redaction
# --------------------------------------------------------------------------- #
def test_find_pii_candidates_finds_and_redact_removes():
    find_pii_candidates = require_attr(validate_mod, "find_pii_candidates")
    redact = require_attr(validate_mod, "redact")

    sample = (
        "Drawer: Sita Sharma. Mobile: +977 9812345678. "
        "Email: sita.sharma@example.com. NEC No. 45678. Ward No. 5."
    )
    found = find_pii_candidates(sample)
    assert any("9812345678" in f for f in found), (
        f"the Nepali mobile number was not found: {found}"
    )
    assert any("@" in f and "example.com" in f for f in found), (
        f"the email was not found: {found}"
    )
    assert any("NEC" in f.upper() and "45678" in f for f in found), (
        f"the NEC-style registration number was not found: {found}"
    )

    redacted = redact(sample, found)
    assert "9812345678" not in redacted, f"phone survived redaction: {redacted!r}"
    assert "sita.sharma@example.com" not in redacted, f"email survived redaction: {redacted!r}"
    assert "45678" not in redacted, f"NEC number survived redaction: {redacted!r}"
    assert "[REDACTED]" in redacted


# --------------------------------------------------------------------------- #
# sanitize_model_text + the renderer's output
# --------------------------------------------------------------------------- #
def test_sanitize_model_text_strips_controls_and_escapes_html():
    sanitize_model_text = require_attr(validate_mod, "sanitize_model_text")
    payload = "ok\x00\x1b\x07 <script>alert('x')</script>\u202e tail"
    out = sanitize_model_text(payload)

    assert "<script>" not in out, f"raw HTML survived sanitisation: {out!r}"
    assert "&lt;script&gt;" in out, f"HTML was not escaped: {out!r}"
    assert "\u202e" not in out, "a bidi override survived sanitisation"
    assert not any(unicodedata.category(ch).startswith("C") for ch in out), (
        f"control/format characters survived sanitisation: {out!r}"
    )

    assert sanitize_model_text("a\n\n   b") == "a b", "whitespace was not collapsed"
    truncated = sanitize_model_text("x" * 100, max_len=10)
    assert len(truncated) <= 10 and truncated.endswith("…"), (
        f"truncation marker missing: {truncated!r}"
    )


def test_report_html_has_no_raw_script_from_model_text():
    report_mod = require("core.report", reason="core.report is not importable yet")
    render_html = require_attr(report_mod, "render_html")
    sanitize_model_text = require_attr(validate_mod, "sanitize_model_text")

    report = make_report()
    payload = "<script>alert('pwn')</script>"
    report.deltas[0].reason = payload
    report.deltas[0].reason_np = payload

    html = render_html(report, make_scene(), make_observed())
    assert "<script>" not in html, (
        "the HTML report rendered a raw <script> from model-derived text — XSS-shaped output"
    )
    assert "&lt;script&gt;" in html, "the payload was dropped instead of rendered inertly"

    # defence in depth: the documented flow is to sanitise model-derived text
    # before it reaches the renderer, so the escaped form is what gets rendered.
    report.deltas[0].reason = sanitize_model_text(payload)
    report.deltas[0].reason_np = sanitize_model_text(payload)
    html2 = render_html(report, make_scene(), make_observed())
    assert "<script>" not in html2


# --------------------------------------------------------------------------- #
# the sidecar convention the web upload path relies on
# --------------------------------------------------------------------------- #
def test_photo_sidecar_next_to_the_photo_is_discovered(tmp_path, fixtures_dir):
    """The web upload saves ``<photo>.json`` next to the photo; observe must find it."""
    to_observed_state = require_attr(observe_mod, "to_observed_state")
    photo = _photo(tmp_path, fixtures_dir)
    sidecar = photo.parent / (photo.name + ".json")  # photo.jpg.json
    sidecar.write_text(
        json.dumps(
            {
                "stage": "walls",
                "view": "front",
                "elements": [
                    {
                        "kind": "wall",
                        "approx_size": {"length": 6.0},
                        "location_hint": "front",
                        "confidence": 0.8,
                    }
                ],
                "scale_refs": [
                    {"kind": "user_dimension", "value": 6.0, "unit": "m", "confidence": 0.9}
                ],
            }
        ),
        encoding="utf-8",
    )

    state = to_observed_state([str(photo)])
    assert state.elements, (
        "a photo.jpg.json sidecar saved next to the photo was not discovered by core.observe"
    )
    assert all(e.provenance.source == "user_supplied" for e in state.elements), (
        f"sidecar elements should carry user_supplied provenance: "
        f"{[(e.id, e.provenance.source) for e in state.elements]}"
    )
    assert any(
        "front_walls_stage.jpg.json" in str(name)
        for name in (state.meta.get("sidecars_used") or [])
    ), f"the sidecar was not recorded in meta: {state.meta.get('sidecars_used')}"
    assert any(r.provenance.source == "user_supplied" for r in state.scale_refs)