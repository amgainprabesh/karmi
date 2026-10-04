"""Tests for the Karmi dataset package (``dataset/``).

Run from the repo root::

    ./.venv/Scripts/python.exe -m pytest dataset/tests/test_dataset.py -v

Covers the invariants that matter for a public dataset: consent/licence
validation, withdrawal semantics, split integrity, de-identification, and the
Hugging Face folder structure. All fixtures are synthetic; nothing touches real
personal data.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from dataset.consent import (
    ConsentMethod,
    ConsentRole,
    ConsentScope,
    LicenceId,
    withdraw,
)
from dataset.deidentify import deidentify_drawing, deidentify_photo, scan_record
from dataset.export import is_releasable, split, to_hf_dataset, to_jsonl, verify_no_leakage
from dataset.schema import DatasetRecord

REPO = Path(__file__).resolve().parents[2]
EX = REPO / "dataset" / "example"


def load_examples() -> list[DatasetRecord]:
    out: list[DatasetRecord] = []
    for p in sorted(EX.glob("karmi-example-0*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        if "consent" not in data:
            continue  # e.g. the withdrawal instruction file
        out.append(DatasetRecord.model_validate(data))
    return out


@pytest.fixture(scope="module")
def examples() -> list[DatasetRecord]:
    recs = load_examples()
    assert len(recs) == 3, "expected the three shipped synthetic examples"
    return recs


# --------------------------------------------------------------------------- #
# schema / consent invariants
# --------------------------------------------------------------------------- #
def test_examples_validate_and_scan_clean(examples: list[DatasetRecord]) -> None:
    for rec in examples:
        assert rec.synthetic is True
        assert scan_record(rec) == [], f"{rec.record_id} trips a PII heuristic"


def test_no_consent_block_is_rejected(examples: list[DatasetRecord]) -> None:
    data = examples[0].model_dump(mode="json")
    del data["consent"]
    with pytest.raises(Exception) as exc:
        DatasetRecord.model_validate(data)
    assert "consent" in str(exc.value)


def test_no_licence_is_rejected(examples: list[DatasetRecord]) -> None:
    data = examples[0].model_dump(mode="json")
    del data["licence"]
    with pytest.raises(Exception) as exc:
        DatasetRecord.model_validate(data)
    assert "licence" in str(exc.value)


def test_public_tier_needs_release_from_every_signatory(examples: list[DatasetRecord]) -> None:
    data = examples[0].model_dump(mode="json")
    data["consent"]["grants"][0]["scope"]["dataset_release"] = False
    with pytest.raises(Exception) as exc:
        DatasetRecord.model_validate(data)
    assert "dataset_release" in str(exc.value)


def test_public_tier_needs_licence_coverage(examples: list[DatasetRecord]) -> None:
    data = examples[0].model_dump(mode="json")
    # signatory only agrees to NC, record claims BY -> reject
    data["consent"]["grants"][1]["scope"]["licence_scope"] = ["cc-by-nc-4.0"]
    with pytest.raises(Exception) as exc:
        DatasetRecord.model_validate(data)
    assert "licence" in str(exc.value)


def test_withdrawal_marks_record_and_produces_instruction(examples: list[DatasetRecord]) -> None:
    rec = examples[0].model_copy(deep=True)
    assert rec.release_tier.value == "public"  # starts public
    instruction = withdraw(
        rec,
        "unit-test withdrawal",
        when=datetime(2026, 9, 20, 11, 30, tzinfo=timezone.utc),
        requested_by=ConsentRole.HOMEOWNER,
    )
    assert rec.consent.withdrawn is True
    assert rec.consent.withdrawn_at == datetime(2026, 9, 20, 11, 30, tzinfo=timezone.utc)
    assert rec.release_tier.value == "gated"  # demoted: cannot remain public
    assert instruction.action == "remove_from_release"
    assert instruction.steps and "Exclude karmi-example-0001" in instruction.steps[0]
    ok, why = is_releasable(rec)
    assert not ok and why == "consent withdrawn"

    with pytest.raises(Exception):
        withdraw(rec, "")  # empty reason is refused


def test_withdrawal_state_must_be_complete(examples: list[DatasetRecord]) -> None:
    data = examples[0].model_dump(mode="json")
    data["consent"]["withdrawn"] = True  # no withdrawn_at / reason
    with pytest.raises(Exception) as exc:
        DatasetRecord.model_validate(data)
    assert "withdrawal" in str(exc.value).lower() or "withdrawn" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# split
# --------------------------------------------------------------------------- #
def test_split_keeps_drawing_and_photos_together(examples: list[DatasetRecord]) -> None:
    splits = split(examples, seed=20261004)
    assert verify_no_leakage(splits) == []
    # every record id and every photo file occurs in exactly one split
    rid_splits: dict[str, set[str]] = {}
    photo_splits: dict[str, set[str]] = {}
    for name, recs in splits.items():
        for r in recs:
            rid_splits.setdefault(r.record_id, set()).add(name)
            for p in r.photos:
                photo_splits.setdefault(p.file, set()).add(name)
    assert all(len(v) == 1 for v in rid_splits.values())
    assert all(len(v) == 1 for v in photo_splits.values())
    # a drawing AND all its photos are in the same split row
    for name, recs in splits.items():
        for r in recs:
            assert all(p.file for p in r.photos)  # photos travel inside the record


def test_split_is_reproducible_and_order_independent(examples: list[DatasetRecord]) -> None:
    a = {k: [r.record_id for r in v] for k, v in split(examples, seed=20261004).items()}
    b = {k: [r.record_id for r in v] for k, v in split(examples[::-1], seed=20261004).items()}
    c = {k: [r.record_id for r in v] for k, v in split(examples, seed=999).items()}
    assert a == b
    assert a != c, "a different seed should produce a different assignment for these ids"


def test_split_small_n_guarantee() -> None:
    from dataset.export import _allocate

    assert _allocate(1, (0.8, 0.1, 0.1)) == [1, 0, 0]
    assert _allocate(2, (0.8, 0.1, 0.1)) == [1, 1, 0]
    assert _allocate(3, (0.8, 0.1, 0.1)) == [1, 1, 1]
    assert _allocate(10, (0.8, 0.1, 0.1)) == [8, 1, 1]
    assert sum(_allocate(100, (0.8, 0.1, 0.1))) == 100


# --------------------------------------------------------------------------- #
# de-identification
# --------------------------------------------------------------------------- #
def test_deidentify_photo_strips_gps_and_keeps_pixels(tmp_path: Path) -> None:
    src = tmp_path / "gps.jpg"
    im = Image.new("RGB", (64, 48), (10, 20, 30))
    for x in range(64):
        im.putpixel((x, x % 48), ((x * 11) % 256, 40, 200))
    exif = Image.Exif()
    exif[271] = "TestCam"
    exif[0x8825] = {1: "N", 2: (27.0, 43.0, 0.0), 3: "E", 4: (85.0, 19.0, 0.0)}
    im.save(src, exif=exif)

    report = deidentify_photo(src, tmp_path / "gps.clean.jpg")
    assert report.metadata["gps_present_before"] is True
    assert report.metadata["gps_present_after"] is False
    assert report.pixels_unchanged is True
    assert report.pixel_sha256_before == report.pixel_sha256_after

    with Image.open(tmp_path / "gps.clean.jpg") as cleaned:
        assert dict(cleaned.getexif()) == {}


def test_deidentify_pdf_redacts_text_and_metadata(tmp_path: Path) -> None:
    import pymupdf

    src = tmp_path / "drawing.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Er. Example Only   NEC No. 99999", fontsize=10)
    page.insert_text((72, 130), "Phone: +977 9800000000   Ward No. 12", fontsize=10)
    doc.set_metadata({"title": "test", "author": "Er. Example Only"})
    doc.save(str(src))
    doc.close()

    text_out = tmp_path / "drawing.redacted.txt"
    report = deidentify_drawing(src, text_out)
    assert report.kind == "drawing_pdf"
    assert len(report.findings) >= 4
    assert report.metadata["residual_matches_after_redaction"] == 0

    red = text_out.read_text(encoding="utf-8")
    assert "[REDACTED]" in red
    assert "9800000000" not in red and "99999" not in red and "Example Only" not in red

    clean = tmp_path / "drawing.redacted.clean.pdf"
    assert clean.is_file()
    with pymupdf.open(str(clean)) as v:
        residual_text = "".join(p.get_text() for p in v)
        meta = v.metadata
    from core.validate import find_pii_candidates

    assert find_pii_candidates(residual_text) == []
    assert not (meta.get("author") or "").strip()


def test_scan_record_finds_synthetic_pii(examples: list[DatasetRecord]) -> None:
    rec = examples[0].model_copy(deep=True)
    rec.notes = "fake contact: +977 9800000000, Er. Test Person, Ward 12, Kitta 45/6"
    findings = scan_record(rec)
    categories = {f.category for f in findings}
    assert {"phone_mobile_intl", "engineer_name", "ward", "plot_kitta"} <= categories
    # masked previews never carry the raw token
    assert all("9800000000" not in f.masked for f in findings)


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def test_jsonl_skips_withdrawn(examples: list[DatasetRecord], tmp_path: Path) -> None:
    out = tmp_path / "records.jsonl"
    summary = to_jsonl(examples, out)
    assert summary["written"] == 2
    assert summary["skipped"][0]["record_id"] == "karmi-example-0003"
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        DatasetRecord.model_validate_json(line)


def test_hf_folder_is_datasets_loadable(examples: list[DatasetRecord], tmp_path: Path) -> None:
    hf = tmp_path / "hf"
    result = to_hf_dataset(examples, hf, name="karmi-naksa-test", seed=20261004)
    assert result["leakage_check"] == []

    card = (hf / "README.md").read_text(encoding="utf-8")
    assert card.startswith("---")
    assert "license:" in card and "pretty_name:" in card
    assert "## Consent" in card and "## De-identification" in card

    assert result["splits"] == {"train": 1, "validation": 1}
    for split_name, rel in result["data_files"].items():
        path = hf / rel
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == result["splits"][split_name]
        for line in lines:
            rec = DatasetRecord.model_validate_json(line)
            assert rec.record_id != "karmi-example-0003"  # withdrawn, never exported

    manifest = json.loads((hf / "splits" / "v0.1.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == 20261004
    assert "content_sha256" in manifest["splits"]["train"]