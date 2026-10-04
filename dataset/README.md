# Karmi dataset — tooling for the open naksa-annotation dataset

This folder is the tooling for **Karmi's open-source data contribution**: the
first annotated dataset of Nepali *naksa* (building-permit) drawings paired with
construction photos of the same house. The full plan — schema mapping, consent,
copyright, de-identification, splits, release mechanics — is
[`docs/research/dataset-plan.md`](../docs/research/dataset-plan.md); this
folder implements it.

> **Honest status: there are no real records yet.** Karmi's data collection is
> consent-first and has not started (no scraping, ever — dataset-plan §3/§8).
> Everything in `dataset/example/` is **synthetic**, generated from the
> repository's own fixtures (`fixtures/naksa_base.pdf`, `fixtures/photos/`).
> The tooling exists now so the format, de-identification and review process can
> be used, tested and criticised before any real data is involved.

---

## What one record contains

One record = **one building project** (one house, one naksa approval) — the unit
of consent, de-identification and splitting. A house's drawing and all its
photos always travel together (no leakage across splits).

| File | Purpose |
|---|---|
| `schema.py` | the annotation record (pydantic). Reuses `core/schema.py`: `SceneGraph` (drawing), `ObservedState` (photos), `Provenance` (`human_annotation` for ground truth). |
| `consent.py` | consent grants (who/what/when/how), licence vocabulary, `withdraw()` → redaction instruction. Legal reasoning in its docstring. |
| `deidentify.py` | runs real de-identification: EXIF/GPS strip, drawing-text PII scan + redaction, `scan_record()`. |
| `export.py` | `to_jsonl()`, `to_hf_dataset()`, `split()` (record-level, reproducible). |
| `annotate.html` | offline, single-file annotation tool (no CDN, no build step). |
| `example/` | synthetic example records + the builder that generates them. |
| `tests/test_dataset.py` | pytest checks for the invariants (consent validation, split reproducibility, de-identification). |

## The record schema

Validated by `dataset/schema.py` (`DatasetRecord`); JSON example in
`dataset/example/karmi-example-0001.json`.

| Field | Type | Notes |
|---|---|---|
| `schema_version` | str | tracks `core.schema.SCHEMA_VERSION` ("0.1.0"); a schema bump is a dataset version bump |
| `record_id` | str | opaque, `karmi-…`; never a filename (filenames can contain a name) |
| `synthetic` | bool | true for fixture-derived examples; such records are never presented as collected data |
| `source_kind` | enum | `vector_pdf` / `raster_pdf` / `scan` / `image` |
| `jurisdiction` | object? | municipality / district (optional); ward only with contributor agreement |
| `consent` | object | **required.** Grants: roles, method, date, scope (licence scope, dataset release, model training, restrictions); withdrawal state |
| `licence` | object | **required.** `cc-by-4.0` (recommended), `cc-by-sa-4.0`, `cc-by-nc-4.0`, or `other` + terms note |
| `release_tier` | enum | `public` / `gated` |
| `drawing.scene` | `SceneGraph` | walls, openings, rooms (bilingual labels), dimensions, scale, north — metres |
| `photos[]` | list | per photo: `file` (opaque), `observed` (`ObservedState`, sidecar-compatible), `redacted` flag |
| `annotator` | object | pseudonymous id + role (never a name) |
| `quality` | object | reviewed / double-annotated / n_annotators / completeness / issues |
| `notes` | str? | free text — scanned by `scan_record()` |
| `created_at` | datetime? | |

**Validation rules that are enforced in code:**

1. A record cannot be constructed without a `consent` block and a `licence`.
2. A `public` record requires `dataset_release=true` from **every** signatory.
3. A `public` record's licence must be inside **every** signatory's licence scope
   (a CC licence can only be granted by the rights holder — Copyright Act 2059;
   dataset-plan §4).
4. A withdrawn record cannot remain in the public tier, and is excluded from
   every export.
5. Photo/drawing file names must be relative and opaque (absolute paths leak the
   contributor's machine layout — SECURITY.md T6).

## Consent & licence rules

* **Privacy Act 2075** — consent-based processing, purpose-limited (§12(3)):
  dataset release and model training are *separate* grants. Guardian consent for
  owners under 18 (§33). Withdrawal is honoured from the next revision onward;
  already-downloaded copies cannot be recalled (said plainly in the form and in
  the redaction instruction).
* **Copyright Act 2059** — drawings are authored works (§2(a)(5)-(6)); the
  author is the first owner of economic rights (§6(1)); commissioned work can
  vest in the payer (§6(2)(c)); moral rights (attribution, integrity) survive
  and are not transferable (§8). Get the licence from the rights holder(s) —
  when in doubt, **both** the homeowner and the designer. The municipal
  approval stamp transfers no copyright.
* Per record, one grant per signatory: homeowner / drawing author / photographer
  (a signatory may hold several roles). Recorded: method (written form, digital,
  email, witnessed verbal), date, licence scope, restrictions.
* Recommended licence: **CC BY 4.0**. Mixed licences are allowed per record and
  the dataset card says so.

## De-identification — how to run it

```bash
# a photo (or a scanned drawing): EXIF/GPS strip + report, pixels verified unchanged
python -m dataset.deidentify fixtures/photos/front_walls_stage.jpg

# a PDF drawing: text PII scan → report + redacted text copy + cleaned PDF copy
python -m dataset.deidentify drawing.pdf --out dataset/deid_out/drawing.redacted.txt

# scan every free-text field of a finished record
python -m dataset.deidentify --scan-record dataset/example/karmi-example-0001.json
```

Outputs land under `dataset/deid_out/` (report JSON included). What runs is real
code: `core.validate.strip_exif` (container-level; decoded pixels bit-for-bit
identical — both pixel hashes are in the report), `core.validate.find_pii_candidates`
+ `redact` over extracted PDF text (names, phones, emails, NEC numbers,
ward/kitta — English and Devanagari), plus a verification pass over the cleaned
PDF. **Honest limits:** the heuristics are best-effort, a name without a title
is not caught, a floor plan is itself quasi-identifying, and a human must review
100% of released pages while the dataset is small (dataset-plan §5).

## Splits and export

```bash
python -m dataset export --example          # JSONL + HF folder from dataset/example/
python -m dataset export --records DIR      # from any directory of record JSONs
```

The split rule (see `export.py` docstring): **record-level**, ordered by
`sha256("<seed>:<record_id>")`, counts `floor(n*ratio)` + largest-remainder with
a minimum-one guarantee for small N; published as `splits/v0.1.json` with
per-record content hashes. A drawing and its photos can never straddle splits.

`to_hf_dataset()` writes a plain folder Hugging Face `datasets` can load:

```
hf/
  README.md          # dataset card (YAML front-matter: licence, language, tags, configs)
  data/train.jsonl   # one record per line
  data/validation.jsonl
  data/test.jsonl
  splits/v0.1.json
```

## Contributing a record

1. **Consent first.** Bilingual form, one per signatory (homeowner, drawing
   author, photographer where applicable). No form → no record. The signed form
   stays in encrypted storage; the record holds a pseudonymous reference.
2. **De-identify.** Run the drawing through `deidentify` (report + redacted text
   + cleaned copy) and every photo through the EXIF strip; blur/exclude people
   and number plates.
3. **Annotate.** Open `dataset/annotate.html` in a browser (it works offline),
   load the drawing render + photos, draw walls/openings, label rooms, enter
   measurements, fill the consent block, export the record JSON + sidecars.
4. **Review.** A second person reviews 100% of pages for v0.x; double-annotate
   ≥10% and report agreement (dataset-plan §8).
5. **Place the record** in a records directory and run
   `python -m dataset export --records <dir>`; the card and split manifest are
   generated for you.

## Current status (keep this honest)

| Thing | State |
|---|---|
| Record schema + validation | **implemented** (`schema.py`, `consent.py`) |
| De-identification (EXIF, PII scan/redact, reports) | **implemented and runnable** (`deidentify.py`) |
| Export (JSONL, HF folder, split) | **implemented** (`export.py`) |
| Annotation tool | **implemented** (`annotate.html`, offline) |
| Example records | 3 synthetic records, one demonstrating withdrawal (`example/`) |
| Real records | **none collected** — consent-first collection has not started |
| COCO export, Parquet metadata, baselines | planned (dataset-plan §2.5/§7), not yet built |
| Hugging Face release | not published; `export` produces the folder for it |