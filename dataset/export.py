"""Karmi dataset — export: JSONL, Hugging Face folder, and the split.

Three things live here, in increasing order of subtlety:

``to_jsonl(records, path)``
    One record per line. Withdrawn records are **excluded by default** — the
    release pipeline cannot accidentally re-publish a record whose consent was
    withdrawn (dataset-plan §3).

``to_hf_dataset(records, out_dir)``
    A plain folder Hugging Face ``datasets`` can load — ``data/<split>.jsonl``
    plus a ``README.md`` dataset card with YAML front-matter (licence,
    language, tags, configs) and a body documenting consent, provenance,
    de-identification and limitations (dataset-plan §7). No dependency beyond
    the standard library; the card says "mixed licences — check per-record
    ``licence``" whenever they are not uniform.

``split(records, seed, ratios)``
    The documented, reproducible split rule. The unit of splitting is the
    **record** — one house, one consent, one naksa approval — so a drawing and
    all of its photos can never end up in different splits (dataset-plan §1,
    §6). Rule, precisely:

    1. Records are ordered by ``sha256("<seed>:<record_id>")`` (hex). This is
       deterministic, independent of input order, and reproducible by anyone
       from the published manifest.
    2. Counts are ``floor(n * ratio)`` per split; the remaining seats go to the
       largest fractional parts (ties resolved in split order
       ``train, validation, test``).
    3. Small-N guarantee: the first ``min(n, number of active splits)`` splits
       each get at least one record; seats are taken from the currently largest
       split. So n=3 with (0.8, 0.1, 0.1) → 1/1/1, and n=2 → 1/1/0 (train,
       validation). (The plan is explicit that v0.x publishes folds instead of
       one big split — dataset-plan §6.)
    4. The split is published as ``splits/v0.1.json`` with per-record content
       hashes.

    Example: n=3 with (0.8, 0.1, 0.1) → 1/1/1, not 3/0/0 — at tiny N the
    guarantee beats the ratio, and the manifest records both.

CLI
---
::

    python -m dataset.export --example
    python -m dataset.export --records dataset/example --out dataset/example/export
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from dataset.schema import DATASET_VERSION, DatasetRecord, ReleaseTier

__all__ = [
    "DEFAULT_SEED",
    "SPLIT_NAMES",
    "is_releasable",
    "split",
    "split_manifest",
    "to_jsonl",
    "to_hf_dataset",
]

DEFAULT_SEED = 20261004  # the date the dataset plan was compiled; any int works, it must be published
SPLIT_NAMES = ("train", "validation", "test")
DEFAULT_RATIOS = (0.8, 0.1, 0.1)


# --------------------------------------------------------------------------- #
# releasability
# --------------------------------------------------------------------------- #
def is_releasable(record: DatasetRecord) -> tuple[bool, str]:
    """Can this record appear in a release *today*?

    Returns ``(ok, reason)``. Reasons are stable strings, safe for logs.
    """
    if record.consent.withdrawn:
        return False, "consent withdrawn"
    if not record.consent.grants_release():
        return False, "not every signatory granted dataset release"
    if record.release_tier == ReleaseTier.PUBLIC:
        covered = record.consent.licence_intersection()
        if record.licence.id.value not in covered:
            return False, "record licence not covered by every signatory's licence scope"
    return True, "ok"


# --------------------------------------------------------------------------- #
# JSONL
# --------------------------------------------------------------------------- #
def to_jsonl(
    records: Iterable[DatasetRecord],
    path: str | Path,
    *,
    include_withdrawn: bool = False,
) -> dict[str, Any]:
    """Write records as JSON Lines, skipping withdrawn records by default.

    ``include_withdrawn=True`` is for archival exports (e.g. a withdrawal
    ledger) — never for a release. Returns a summary dict.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    skipped: list[dict[str, str]] = []
    with open(p, "w", encoding="utf-8") as fh:
        for rec in records:
            ok, reason = is_releasable(rec)
            if not ok and not include_withdrawn:
                skipped.append({"record_id": rec.record_id, "reason": reason})
                continue
            fh.write(rec.model_dump_json() + "\n")
            written.append(rec.record_id)
    return {
        "path": p.name,
        "written": len(written),
        "record_ids": written,
        "skipped": skipped,
    }


# --------------------------------------------------------------------------- #
# the split rule
# --------------------------------------------------------------------------- #
def _stable_key(record_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{record_id}".encode("utf-8")).hexdigest()


def _allocate(n: int, ratios: Sequence[float]) -> list[int]:
    """floor + largest-remainder + small-N minimum-one guarantee (see module doc)."""
    base = [int(n * r) for r in ratios]
    frac = [n * r - b for r, b in zip(ratios, base)]
    remaining = n - sum(base)
    order = sorted(range(len(ratios)), key=lambda i: (-frac[i], i))
    for k in range(remaining):
        base[order[k % len(order)]] += 1

    active = [i for i, r in enumerate(ratios) if r > 0]
    guarantee = active[: min(n, len(active))]
    for idx in guarantee:
        if base[idx] == 0:
            donors = [i for i in active if base[i] > 1]
            if not donors:
                break
            donor = max(donors, key=lambda i: (base[i], -i))
            base[donor] -= 1
            base[idx] += 1
    return base


def split(
    records: Iterable[DatasetRecord],
    seed: int = DEFAULT_SEED,
    ratios: Sequence[float] = DEFAULT_RATIOS,
    *,
    names: Sequence[str] = SPLIT_NAMES,
) -> dict[str, list[DatasetRecord]]:
    """Split records into train/validation/test — record-level, reproducible.

    See the module docstring for the exact rule. The guarantee that matters:
    every photo (and every page) of a record travels with that record, so a
    house never straddles two splits.
    """
    if len(ratios) != len(names):
        raise ValueError(f"{len(names)} split names need {len(names)} ratios, got {len(ratios)}")
    if any(r < 0 for r in ratios):
        raise ValueError("ratios must be non-negative")
    total = sum(ratios)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"ratios must sum to 1.0 (got {total})")

    ordered = sorted(records, key=lambda r: _stable_key(r.record_id, seed))
    counts = _allocate(len(ordered), ratios)
    out: dict[str, list[DatasetRecord]] = {}
    cursor = 0
    for name, count in zip(names, counts):
        out[name] = ordered[cursor : cursor + count]
        cursor += count
    return out


def split_manifest(
    records: Iterable[DatasetRecord],
    seed: int = DEFAULT_SEED,
    ratios: Sequence[float] = DEFAULT_RATIOS,
    *,
    names: Sequence[str] = SPLIT_NAMES,
) -> dict[str, Any]:
    """The published split: rule, seed, counts and per-record content hashes."""
    recs = list(records)
    splits = split(recs, seed, ratios, names=names)
    return {
        "schema": "karmi-split-manifest/0.1.0",
        "dataset_version": DATASET_VERSION,
        "rule": (
            "record-level (one house = one record = one consent unit); ordered by "
            "sha256('<seed>:<record_id>'); counts floor(n*ratio) + largest-remainder, "
            "with the first min(n, active splits) splits each getting >=1 record when "
            "possible (seats taken from the largest split); ties in split order "
            "train, validation, test"
        ),
        "seed": seed,
        "ratios": list(ratios),
        "n_records": len(recs),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "splits": {
            name: {
                "count": len(recs_),
                "record_ids": [r.record_id for r in recs_],
                "content_sha256": {
                    r.record_id: hashlib.sha256(r.model_dump_json().encode("utf-8")).hexdigest()
                    for r in recs_
                },
            }
            for name, recs_ in splits.items()
        },
    }


def verify_no_leakage(splits: dict[str, list[DatasetRecord]]) -> list[str]:
    """Defensive check: a record — and every photo file it owns — in one split only.

    Returns a list of violations (empty means clean). Used by the test-suite and
    by anyone auditing a split before publication.
    """
    violations: list[str] = []
    record_split: dict[str, str] = {}
    photo_split: dict[str, str] = {}
    for name, recs in splits.items():
        for rec in recs:
            if rec.record_id in record_split:
                violations.append(
                    f"record {rec.record_id} appears in both {record_split[rec.record_id]} and {name}"
                )
            record_split[rec.record_id] = name
            for photo in rec.photos:
                if photo.file in photo_split and photo_split[photo.file] != name:
                    violations.append(
                        f"photo {photo.file} (record {rec.record_id}) appears in both "
                        f"{photo_split[photo.file]} and {name}"
                    )
                photo_split[photo.file] = name
    return violations


# --------------------------------------------------------------------------- #
# Hugging Face folder
# --------------------------------------------------------------------------- #
def _licence_summary(records: Sequence[DatasetRecord]) -> Counter:
    return Counter(r.licence.id.value for r in records)


def _yaml_scalar(v: str) -> str:
    return '"' + v.replace('"', '\\"') + '"'


def _render_card(
    all_records: Sequence[DatasetRecord],
    splits: dict[str, list[DatasetRecord]],
    *,
    name: str,
    seed: int,
    ratios: Sequence[float],
    data_files: dict[str, str],
) -> str:
    licences = _licence_summary(all_records)
    mixed = len(licences) > 1
    any_synthetic = any(r.synthetic for r in all_records)
    n_photos = sum(len(r.photos) for r in all_records)
    n_withdrawn = sum(1 for r in all_records if r.consent.withdrawn)

    # ---- YAML front-matter -------------------------------------------------- #
    fm: list[str] = ["---"]
    if mixed:
        fm.append("license:")
        for lic in sorted(licences):
            fm.append(f"- {lic}")
        fm.append("# mixed licences — check per-record `licence`")
    else:
        fm.append(f"license: {next(iter(licences)) if licences else 'other'}")
    fm += [
        "language:",
        "- ne",
        "- en",
        f"pretty_name: {_yaml_scalar(name)}",
        "task_categories:",
        "- image-segmentation",
        "- object-detection",
        "tags:",
        "- floor-plan",
        "- construction",
        "- nepal",
        "- naksa",
        "- architecture",
        "size_categories:",
        "- n<1K",
        "configs:",
        "- config_name: default",
        "  data_files:",
    ]
    for split_name, rel in data_files.items():
        fm += [f"  - split: {split_name}", f"    path: {rel}"]
    fm.append("---")

    # ---- body ---------------------------------------------------------------- #
    role_counts: Counter = Counter()
    method_counts: Counter = Counter()
    for r in all_records:
        for g in r.consent.grants:
            for role in g.roles:
                role_counts[role.value] += 1
            method_counts[g.method.value] += 1

    lines: list[str] = []
    lines.append("")
    lines.append(f"# {name}")
    lines.append("")
    if any_synthetic:
        lines.append(
            "> **⚠ This export contains SYNTHETIC example records.** They are generated "
            "from the Karmi repository's own fixtures to demonstrate the format. They "
            "are not collected data, they describe no real building, and they must not "
            "be used as if they were."
        )
        lines.append("")
    lines.append(
        "The Karmi dataset pairs **approved Nepali naksa drawings** (building permit "
        "plans) with **construction site photos** of the same house, annotated as "
        "machine-readable ground truth in the shared schema of the Karmi project "
        "(`core/schema.py`). One record = one building project; drawings and photos of "
        "a house never straddle the train/validation/test splits."
    )
    lines.append("")
    lines.append("## Records")
    lines.append("")
    lines.append("| record_id | split | tier | source_kind | licence | photos | synthetic | withdrawn |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for split_name, recs in splits.items():
        for r in recs:
            lines.append(
                f"| {r.record_id} | {split_name} | {r.release_tier.value} | "
                f"{r.source_kind.value} | {r.licence.id.value} | {len(r.photos)} | "
                f"{'yes' if r.synthetic else 'no'} | {'yes' if r.consent.withdrawn else 'no'} |"
            )
    lines.append("")
    lines.append("## Consent")
    lines.append("")
    lines.append(
        f"{len(all_records)} record(s), {n_photos} annotated photo(s). "
        f"Withdrawn records are excluded from every export ({n_withdrawn} excluded here). "
        "Every record carries one consent grant per signatory — homeowner, drawing "
        "author and (where applicable) photographer — recording what was consented to "
        "(licence scope, dataset release, model training), when, and how. "
        "Consent follows Nepal's Privacy Act 2075: consent-based, purpose-limited "
        "(§12(3)), guardian consent where the owner is under 18 (§33), and revocable. "
        "Drawings are authored works under the Copyright Act 2059: licences come from "
        "the rights holders (§6), moral rights are respected (§8) — see "
        "`dataset/consent.py`."
    )
    lines.append("")
    lines.append(
        f"Grants by role: {dict(role_counts) or '—'}. Methods: {dict(method_counts) or '—'}."
    )
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(
        f"- Generated by `dataset.export.to_hf_dataset()` on {datetime.now(timezone.utc):%Y-%m-%d} (UTC)."
    )
    lines.append(f"- Record schema version: `{DATASET_VERSION}` (tracks `core/schema.py`).")
    lines.append(f"- Split rule: record-level, seed `{seed}`, ratios `{list(ratios)}`; "
                 "see `splits/v0.1.json` for per-record content hashes.")
    lines.append(
        "- Ground-truth annotation provenance is `human_annotation` per element, so "
        "'drawn by a human or a model?' is answerable per field."
    )
    if any_synthetic:
        lines.append(
            "- Source: repository fixtures (`fixtures/naksa_base.pdf`, "
            "`fixtures/photos/`) — synthetic, generated by `dataset/example/build_examples.py`."
        )
    lines.append("")
    lines.append("## De-identification")
    lines.append("")
    lines.append(
        "Before release, photos pass `dataset.deidentify` (container-level EXIF/GPS "
        "strip, decoded pixels verified bit-for-bit unchanged) and drawing text is "
        "scanned with `core.validate.find_pii_candidates` (names, phones, emails, NEC "
        "numbers, ward/kitta — English and Devanagari). Records in this export carry "
        "`redacted` flags per photo. Honest limits: the heuristics are best-effort, a "
        "name without a title is not caught, and a floor plan is itself "
        "quasi-identifying — human review of 100% of released pages is required while "
        "the dataset is small (dataset-plan §5)."
    )
    lines.append("")
    lines.append("## How to load")
    lines.append("")
    lines.append("```python")
    lines.append('from datasets import load_dataset')
    lines.append(f'ds = load_dataset("{name}")   # or a local path to this folder')
    lines.append("ds[\"train\"][0].keys()")
    lines.append("```")
    lines.append("")
    lines.append("## Licence")
    lines.append("")
    if mixed:
        lines.append(
            "**Mixed licences — check each record's `licence` field.** "
            f"This export contains: {', '.join(sorted(licences))}. "
            "Recommended default is CC BY 4.0; contributors who granted less are "
            "recorded individually (dataset-plan §4)."
        )
    else:
        lic = next(iter(licences)) if licences else "other"
        lines.append(f"Records in this export are under **{lic}** (per-record `licence` field).")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- The dataset currently contains **no real records**: Karmi's collection "
        "campaign (consent-first, no scraping — dataset-plan §3/§8) has not started. "
        "This export exists so the format, tooling and review process can be used and "
        "criticised before any real data is involved."
    )
    lines.append(
        "- PII heuristics are best-effort; a drawing's layout and a photo of a home can "
        "still be identifying even after de-identification."
    )
    lines.append(
        "- Karmi reports items *to verify*; annotations here are ground truth for "
        "tooling, not regulatory findings."
    )
    lines.append("")
    lines.append("## Changelog")
    lines.append("")
    lines.append("- v0.1.0 — tooling release with synthetic examples only.")
    lines.append("")
    return "\n".join(fm + lines)


def to_hf_dataset(
    records: Iterable[DatasetRecord],
    out_dir: str | Path,
    *,
    name: str = "karmi-naksa-example",
    seed: int = DEFAULT_SEED,
    ratios: Sequence[float] = DEFAULT_RATIOS,
) -> dict[str, Any]:
    """Write a Hugging Face ``datasets``-loadable folder: data/*.jsonl + card.

    Withdrawn records are excluded (the manifest records how many). Returns a
    summary dict.
    """
    out = Path(out_dir)
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    all_recs = list(records)
    releasable = [r for r in all_recs if is_releasable(r)[0]]
    excluded = [
        {"record_id": r.record_id, "reason": is_releasable(r)[1]}
        for r in all_recs
        if not is_releasable(r)[0]
    ]

    splits = split(releasable, seed, ratios)
    data_files: dict[str, str] = {}
    written: dict[str, int] = {}
    for split_name, recs in splits.items():
        if not recs:
            continue  # don't ship empty files; the card lists only what exists
        rel = f"data/{split_name}.jsonl"
        to_jsonl(recs, out / rel)
        data_files[split_name] = rel
        written[split_name] = len(recs)

    manifest = split_manifest(releasable, seed, ratios)
    splits_dir = out / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    (splits_dir / "v0.1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    card = _render_card(all_recs, splits, name=name, seed=seed, ratios=ratios, data_files=data_files)
    (out / "README.md").write_text(card, encoding="utf-8")

    return {
        "out_dir": str(out),
        "records": len(all_recs),
        "releasable": len(releasable),
        "excluded": excluded,
        "splits": written,
        "data_files": data_files,
        "card": "README.md",
        "split_manifest": "splits/v0.1.json",
        "leakage_check": verify_no_leakage(splits),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_records(path: Path) -> list[DatasetRecord]:
    """Load record JSONs from a file or a directory (skipping non-records)."""
    files: list[Path]
    if path.is_dir():
        files = sorted(path.glob("*.json"))
    else:
        files = [path]
    out: list[DatasetRecord] = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or "consent" not in data or "record_id" not in data:
            continue
        try:
            out.append(DatasetRecord.model_validate(data))
        except Exception as exc:  # noqa: BLE001 — fail loudly: a skipped record is data loss
            raise ValueError(
                f"{f.name} does not validate as a DatasetRecord: {exc}"
            ) from exc
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m dataset.export",
        description="Export Karmi dataset records: JSONL + a Hugging Face folder.",
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--example", action="store_true",
                     help="use the synthetic example records (dataset/example/)")
    src.add_argument("--records", metavar="PATH",
                     help="a record JSON file or a directory of record JSONs")
    ap.add_argument("--out", default=None, help="output directory")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args(argv)

    pkg_dir = Path(__file__).resolve().parent
    if args.example:
        records_dir = pkg_dir / "example"
        out_dir = Path(args.out) if args.out else records_dir / "export"
        records = _load_records(records_dir)
        if not records:
            print("no example records found — building them first "
                  "(python -m dataset build-examples)…", file=sys.stderr)
            sys.path.insert(0, str(pkg_dir.parent))
            from dataset.example.build_examples import build_examples

            build_examples()
            records = _load_records(records_dir)
        name = "karmi-naksa-example"
    else:
        records_path = Path(args.records)
        if not records_path.exists():
            print(f"error: no such file or directory: {records_path}", file=sys.stderr)
            return 2
        out_dir = Path(args.out) if args.out else records_path if records_path.is_dir() else records_path.parent / "export"
        try:
            records = _load_records(records_path)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        name = "karmi-naksa"

    if not records:
        print("error: no dataset records found", file=sys.stderr)
        return 2

    # 1. flat JSONL of everything releasable
    jsonl_path = out_dir / f"{name}.jsonl"
    jsonl = to_jsonl(records, jsonl_path)

    # 2. HF-style folder
    hf = to_hf_dataset(records, out_dir / "hf", name=name, seed=args.seed)

    if args.json:
        print(json.dumps({"jsonl": jsonl, "hf": hf}, ensure_ascii=False, indent=2))
        return 0

    print(f"Karmi dataset export — {len(records)} record(s) loaded, "
          f"{jsonl['written']} written, {len(jsonl['skipped'])} excluded")
    for s in jsonl["skipped"]:
        print(f"  excluded: {s['record_id']} — {s['reason']}")
    print(f"  jsonl:     {jsonl_path}  ({jsonl['written']} record(s))")
    print(f"  HF folder: {out_dir / 'hf'}")
    for split_name, count in hf["splits"].items():
        print(f"    data/{split_name}.jsonl  ({count})")
    print(f"    README.md  (dataset card)")
    print(f"    splits/v0.1.json  (split manifest with content hashes)")
    print(f"  leakage check: {'CLEAN' if not hf['leakage_check'] else hf['leakage_check']}")

    # the first record's keys, so the shape is visible at a glance
    if jsonl["written"]:
        first = json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])
        print(f"  first record keys: {sorted(first.keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())