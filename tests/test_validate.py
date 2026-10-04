"""``core.validate`` — upload validation and filename safety.

The exact call shape of the validator is not pinned by the schema, so these
tests probe a short list of plausible entry points and call shapes, and
normalise the verdict (returned bool/tuple/dict, or a raised error) to
accepted / rejected. If no entry point exists yet, the tests skip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import require

validate_mod = require(
    "core.validate",
    reason="core.validate is not importable yet (being written in parallel) — skipping the validation tests",
)

_VALIDATOR_NAMES = (
    "validate_pdf",
    "validate_drawing",
    "validate_upload",
    "validate_file",
    "check_pdf",
    "validate",
)
_SIZE_NAMES = (
    "MAX_UPLOAD_BYTES",
    "MAX_PDF_BYTES",
    "MAX_FILE_BYTES",
    "MAX_SIZE_BYTES",
    "MAX_UPLOAD_SIZE_BYTES",
    "MAX_BYTES",
    "MAX_UPLOAD_MB",
    "MAX_PDF_MB",
    "MAX_SIZE_MB",
    "MAX_UPLOAD_SIZE_MB",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_UPLOAD_BYTES",
)
_RESERVED_STEMS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_BAD_NAMES = [
    "../evil.pdf",
    "..\\evil.pdf",
    "a/b.pdf",
    "a\\b.pdf",
    "../../etc/passwd",
    "CON",
    "con.pdf",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "LPT1",
    "COM1.pdf",
    "LPT1.txt",
]
_JOIN_ESCAPES = [
    "../evil.pdf",
    "..\\evil.pdf",
    "../../evil.pdf",
    "a/../../evil.pdf",
    "C:/Windows/evil.pdf",
    "C:\\Windows\\evil.pdf",
    "/etc/passwd",
    "..",
    "a/..",
]


def _validator():
    for name in _VALIDATOR_NAMES:
        fn = getattr(validate_mod, name, None)
        if callable(fn):
            return fn, name
    pytest.skip(f"core.validate exposes none of {', '.join(_VALIDATOR_NAMES)} yet")


def _verdict(fn, path: Path):
    """Call the validator tolerantly; return (accepted: bool, detail: str)."""
    path = Path(path)
    last_type_error = None
    for how in ("path", "name_bytes"):
        try:
            result = fn(path) if how == "path" else fn(path.name, path.read_bytes())
        except TypeError as exc:
            last_type_error = exc
            continue
        except (ValueError, AssertionError, OSError) as exc:
            return False, f"rejected with {type(exc).__name__}: {exc}"
        except Exception as exc:
            if type(exc).__module__ != "builtins":  # a domain error = a rejection
                return False, f"rejected with {type(exc).__name__}: {exc}"
            raise
        if isinstance(result, bool):
            return result, f"returned {result!r}"
        if isinstance(result, tuple) and result and isinstance(result[0], bool):
            return result[0], f"returned {result!r}"
        if isinstance(result, dict):
            for key in ("ok", "valid", "accepted"):
                if key in result:
                    return bool(result[key]), f"returned {result!r}"
        return True, f"returned {result!r} (no error raised)"
    raise last_type_error if last_type_error is not None else AssertionError("no call shape matched")


def _verdict_or_skip(fn, name, path):
    try:
        return _verdict(fn, path)
    except TypeError as exc:
        pytest.skip(f"could not call core.validate.{name} with (path) or (name, bytes): {exc}")


def test_accepts_a_real_pdf_fixture(naksa_base):
    fn, name = _validator()
    accepted, detail = _verdict_or_skip(fn, name, naksa_base)
    assert accepted, f"core.validate.{name} rejected a real PDF fixture ({detail})"


def test_rejects_text_renamed_to_pdf(tmp_path):
    fn, name = _validator()
    fake = tmp_path / "drawing.pdf"
    fake.write_text("This is plainly not a PDF — it is text wearing a .pdf extension.", encoding="utf-8")
    accepted, detail = _verdict_or_skip(fn, name, fake)
    assert not accepted, f"core.validate.{name} accepted a text file renamed to .pdf ({detail})"


def _size_limit():
    for name in _SIZE_NAMES:
        value = getattr(validate_mod, name, None)
        if isinstance(value, int) and value > 0:
            return value * 1024 * 1024 if name.endswith("_MB") else value
    return None


def test_rejects_an_oversized_file(tmp_path, naksa_base):
    fn, name = _validator()
    limit = _size_limit()
    if limit is None or limit > 64 * 1024 * 1024:
        pytest.skip(
            "core.validate exposes no usable size-limit constant — cannot build an oversized input"
        )

    # a real (parseable) PDF padded past the limit, so rejection can only be size-based
    data = naksa_base.read_bytes()
    big = tmp_path / "huge.pdf"
    with big.open("wb") as fh:
        fh.write(data)
        pad = limit + 1024 - len(data)
        if pad > 0:
            fh.write(b"\x00" * pad)
    assert big.stat().st_size > limit

    accepted, detail = _verdict_or_skip(fn, name, big)
    assert not accepted, (
        f"core.validate.{name} accepted a {big.stat().st_size}-byte file over the {limit}-byte limit ({detail})"
    )


def _safe(name):
    fn = getattr(validate_mod, name, None)
    if not callable(fn):
        pytest.skip(f"core.validate.{name} does not exist yet")
    return fn


def test_safe_filename_rejects_traversal_and_reserved_names():
    safe_filename = _safe("safe_filename")
    for raw in _BAD_NAMES:
        try:
            out = safe_filename(raw)
        except (ValueError, AssertionError, OSError):
            continue  # raising = rejected
        except Exception as exc:
            if type(exc).__module__ != "builtins":
                continue  # a domain error = rejected
            raise
        assert isinstance(out, str), f"safe_filename({raw!r}) returned {out!r}"
        assert "/" not in out and "\\" not in out, (
            f"safe_filename({raw!r}) = {out!r} still contains a path separator"
        )
        assert ".." not in out, f"safe_filename({raw!r}) = {out!r} still contains '..'"
        assert out.split(".")[0].upper() not in _RESERVED_STEMS, (
            f"safe_filename({raw!r}) = {out!r} is still a Windows reserved name"
        )


def test_safe_filename_accepts_a_normal_name():
    safe_filename = _safe("safe_filename")
    out = safe_filename("naksa_plan_v2.pdf")
    assert isinstance(out, str) and out, "safe_filename rejected a normal filename"
    assert "naksa_plan_v2" in out and out.endswith(".pdf")


def test_safe_join_keeps_paths_inside_the_base_dir(tmp_path):
    safe_join = _safe("safe_join")
    base = tmp_path / "uploads"
    base.mkdir()
    base_resolved = base.resolve()

    for raw in _JOIN_ESCAPES + _BAD_NAMES:
        try:
            out = safe_join(base, raw)
        except (ValueError, AssertionError, OSError):
            continue
        except Exception as exc:
            if type(exc).__module__ != "builtins":
                continue
            raise
        resolved = Path(out).resolve()
        inside = resolved == base_resolved or base_resolved in resolved.parents
        assert inside, f"safe_join({raw!r}) escaped the base directory: {resolved}"

    out = safe_join(base, "sub/plan.pdf")
    resolved = Path(out).resolve()
    assert resolved == base_resolved or base_resolved in resolved.parents, (
        f"safe_join moved a safe path outside the base dir: {resolved}"
    )
    assert resolved.name == "plan.pdf"


def test_safe_filename_and_safe_join_together_neutralise_reserved_names(tmp_path):
    """The documented compose pattern: ``safe_join(base, safe_filename(name))``.

    The division of labour is: ``safe_join`` guards the storage root
    (traversal/escape/absolute paths), ``safe_filename`` neutralises Windows
    reserved device names. The *pair* must make any hostile name safe to store
    under ``base`` — that is the upload contract this test asserts.
    """
    safe_filename = _safe("safe_filename")
    safe_join = _safe("safe_join")
    base = tmp_path / "uploads"
    base.mkdir()
    base_resolved = base.resolve()

    for raw in _BAD_NAMES:
        try:
            name = safe_filename(raw)
        except (ValueError, AssertionError, OSError):
            continue  # rejected outright — fine
        except Exception as exc:
            if type(exc).__module__ != "builtins":
                continue
            raise
        try:
            out = safe_join(base, name)
        except (ValueError, AssertionError, OSError):
            continue  # rejected by the joiner — fine
        except Exception as exc:
            if type(exc).__module__ != "builtins":
                continue
            raise
        resolved = Path(out).resolve()
        assert resolved == base_resolved or base_resolved in resolved.parents, (
            f"safe_join(base, safe_filename({raw!r})) escaped the base dir: {resolved}"
        )
        if resolved != base_resolved:
            assert resolved.name.split(".")[0].upper() not in _RESERVED_STEMS, (
                f"safe_join(base, safe_filename({raw!r})) = {resolved.name!r} "
                "is still a Windows reserved name"
            )