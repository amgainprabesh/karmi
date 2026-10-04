# Dataset plan — "the first annotated dataset of Nepali naksa drawings paired with construction photos"

> Karmi's open-source data contribution. Compiled 2026-10-04 (NPT).
> This document maps the dataset onto `core/schema.py` (v0.1.0) field names and is deliberately conservative about consent, copyright and release mechanics.
> Status: **plan** — nothing here is released yet; the repo's `README.md` currently lists the dataset as roadmap ("annotated dataset release", unchecked).

---

## 1. What one record contains

One record = **one building project** (one house, one naksa approval), not one page. A house is the unit of consent, the unit of de-identification, and the unit of the train/test split (pages of the same house must never straddle splits).

```
karmi-0001/
  meta.json                 # record metadata, consent, license, split (see §2.6)
  drawing/
    original.pdf            # RESTRICTED tier only — never published
    public/page-01.png      # redacted raster render (300 dpi), published
    public/page-01.pdf      # redacted single-page PDF (where rights allow)
  photos/
    2026-03-14_front.jpg    # EXIF-stripped, de-identified
    2026-03-14_interior.jpg
  annotations/
    scene_gt.json           # SceneGraph-shaped ground truth (drawing side)
    observed_gt.json        # ObservedState-shaped ground truth (photo side, where annotated)
    exports/coco.json       # optional derived instance-segmentation export
  derived/
    scene_model.json        # the model's raw output (baseline comparison)
    report.json             # optional DiffReport for the pair
```

Every JSON in `annotations/` carries `schema_version` (`"0.1.0"` today). A schema bump is a dataset version bump.

---

## 2. Annotation schema — mapped onto `core/schema.py`

### 2.1 Drawing side → `SceneGraph`

| Dataset annotation | `core/schema.py` type / field | Notes |
|---|---|---|
| Page manifest | `SceneGraph.source_kind` (`vector_pdf`/`raster_pdf`/`scan`/`image`), `source_file` | drives the raster-vs-vector evaluation slices |
| Walls | `Wall`: `id`, `start`, `end` (metres, drawing space), `thickness` (m), `is_external` | polylines split at corners/junctions; `thickness` from 230/115 mm priors + dimension text |
| Openings | `Opening`: `id`, `kind` (`door`/`window`/`vent`/`unknown`), `wall_id`, `center`, `width`, `height`, `sill_height` | width/height from the opening schedule & dimension text first, drawn geometry second |
| Rooms | `Room`: `id`, `name` (English), `name_np` (Devanagari), `polygon`, `area_m2` | bilingual labels are the Nepali-specific contribution; label lexicon in `naksa-conventions.md` §8 |
| Dimensions | `Dimension`: `id`, `value`, `unit` (`m`/`ft`/`ft_in`/`unknown`), `label`, `start`, `end` | store both metric and feet-inch sets |
| Orientation | `SceneGraph.north_deg`, `north_provenance` | degrees from the sheet's north arrow |
| Scale | `SceneGraph.scale_m_per_unit`, `scale_provenance` | read from title block; used for cross-checks only |
| Extent | `SceneGraph.bbox` (minx, miny, maxx, maxy, metres) | |
| Sheet-level caveats | `SceneGraph.warnings`, `meta` | e.g. "no schedule", "north missing" |

### 2.2 Provenance — one schema gap to resolve

`Provenance.source` (schema v0.1.0) enumerates `vector_geometry`, `raster_geometry`, `ai_vision`, `ai_text`, `user_supplied`, `default`. Ground truth written by a human annotator has no exact literal today. Two options, decide before v0.1 release:

1. Use `"user_supplied"` for all human-verified ground truth (no schema change), or
2. Bump `SCHEMA_VERSION` to `0.2.0` and add `"human_annotation"` (a one-literal enum extension; update `docs/architecture.md` per the schema file's own instruction).

Recommendation: **option 2**, because "was this drawn by a model or a human?" is the single most important provenance bit in a training dataset.

### 2.3 Photo side → `ObservedState`

| Dataset annotation | `core/schema.py` type / field | Notes |
|---|---|---|
| Photo file | `Capture.file`, `taken_at` | timestamp coarsened to month in the public tier |
| Construction stage | `Capture.stage` (`site`→`complete`), `stage_confidence` | ground truth stage is a human label |
| View | `Capture.view` (`front`/`side`/`rear`/`interior`/`aerial`/`unknown`) | |
| Elements | `ObservedElement`: `id`, `kind` (`wall`/`opening`/`column`/`slab`/`roof`/`setback`/`other`), `approx_size` (dict, metres), `location_hint`, `matches_scene_id` | `matches_scene_id` is the pairing gold label — the hardest and most valuable annotation |
| Scale references | `ScaleRef`: `kind` (`brick_course`/`door_height`/`user_dimension`/`known_object`/`unknown`), `value`, `unit` | brick course height and standard door height are the two workhorse references |
| State-level | `ObservedState.stage`, `stage_provenance`, `warnings`, `meta` | |

### 2.4 Diff layer (optional per record)

Where both sides are annotated for the same house, a human-verified `DiffReport` ( `Delta`, `VerifyItem`) can be included as a *derived* label: `Delta.status` ∈ `matched`/`differs`/`missing`/`unexpected`/`unverifiable`, `severity` ∈ `info`/`low`/`medium`/`high`. This layer is what makes the dataset useful beyond segmentation — it teaches the *comparison*, which is Karmi's actual product.

### 2.5 Export formats

- **Primary:** the schema JSON above (one file per project; JSON Lines index across projects).
- **Derived:** COCO-style instance segmentation export (walls, openings, rooms as polygons) for standard training pipelines — precedent: CubiCasa5K ships SVG polygons and community COCO conversions.[CC5K]
- **Tabular:** a `metadata.parquet` with one row per project (splits, licenses, counts) for the Hub viewer.

### 2.6 `meta.json` (public tier)

`record_id`, `schema_version`, `municipality` (name or `"withheld"`), `source_kind`, `drawing_date` (month-level), `capture_months`, `building_class` (A/B/C), `storeys`, `plot_area_m2` (optional, coarse), `consent: {homeowner, designer, license_grant, restrictions[]}`, `license`, `split`, `annotation: {n_annotators, double_annotated}`. No names, no kitta numbers, no GPS (see §5).

---

## 3. How data is collected (with informed consent)

**Channels (in order of preference):**

1. **Designer/consultancy partnerships** — NEC-registered engineers/architects who prepared the drawings can provide their own sets *and* broker homeowner contact. Their consent is required anyway (they authored the drawings — §4).
2. **Homeowner volunteers** — through community outreach, ward-level notices, and the team's network. A homeowner typically holds a stamped copy of the approved set.
3. **Municipal cooperation (formal only)** — some municipalities run eBPS and hold approved sets. Any use requires a written institutional agreement; **do not scrape eBPS portals or municipal websites** for drawings — the files contain personal data and no such permission exists.
4. **Construction photos** — from the same homeowners/builders, ideally a time series per house (foundation → columns → walls → roof → finishing), or supplied by the partner engineer who supervised the site.

**Informed consent — per project, three signatories where applicable:**

- **Homeowner(s):** consent to publish the (redacted) drawing and photos of their property; acknowledge the Privacy Act 2075 purpose-limitation rule ("used only for the purpose for which such data have been collected" — §12(3)).[PA]
- **Drawing author (designer/consultancy):** license to reproduce, redact, and redistribute the drawing as part of an open dataset (§4).
- **Photographer:** if photos were not taken by the homeowner/team, their license too.

**Consent form mechanics:** bilingual (Nepali + English), plain language, separate checkboxes for (a) public dataset inclusion, (b) gated tier only, (c) training-only, (d) withdrawal contact; recorded with date + signature; a copy given to the signatory. Guardian consent for under-18 owners (Privacy Act §33).[PA] No data enters any public tier without a signed form; the original form is retained (encrypted) as the legal record.

**Withdrawal:** contributors may withdraw; the record is removed from the next dataset revision and a changelog entry records it. Be explicit in the form: copies already downloaded cannot be recalled — this is a real limitation, not a promise we can keep.

---

## 4. Copyright and licensing — the legal caution

**The drawings are authored works.** Nepal's Copyright Act 2059 (2002) protects "architectural design" and "other work relating to architecture" as copyrightable works (§2(a)(5)–(6)); the **author is the first owner of economic rights** (§6(1)); works prepared for remuneration can vest in the paying party (§6(2)(c)); moral rights — attribution and no distortion/mutilation — are **not transferable** and survive (§8).[CA] Practical consequences:

- **A CC license can only be granted by the rights holder.** Obtain the license grant *in the consent form text* from whoever holds the economic rights — in practice the designer/consultancy (commissioned work), and/or the homeowner depending on their contract. **When in doubt, get both signatures.** 
- **Redaction is a modification.** It is fine with explicit consent; moral rights mean we (a) credit contributing designers/consultancies at an aggregate level (dataset card acknowledgment list, with permission) and (b) never present a modified drawing as the author's unaltered work.
- **The municipal approval stamp does not transfer copyright** — approval is an administrative act; it gives no publication right.
- **Educational fair-use-like exceptions exist in the Act (Chapter 4), but we do not rely on them** for redistribution; datasets need explicit licenses.
- **Photos** are photographic works; the photographer owns them. Same rule: license from the photographer.
- **Recommended dataset license:** **CC BY 4.0** for the public redacted tier (maximum utility; matches modern data-sharing norms). Where a contributor grants less, record a per-record license (`cc-by-nc-4.0`, `cc-by-sa-4.0`, or `license: other` + terms file). The dataset card must state "mixed licenses — check per-record `license`". Precedent note: CubiCasa5K is CC BY-NC 4.0,[CC5K-LIC] which limits commercial reuse; we prefer BY where consent allows. Code stays MIT (repo `LICENSE`).

---

## 5. De-identification

**The name plate is the problem** — it contains owner names, engineer name + NEC registration, kitta number, GPS coordinates, signatures, phone numbers, dates (`naksa-conventions.md` §2).

Pipeline per sheet:

1. Render at 300 dpi (never publish the original PDF's text layer).
2. **Detect and redact:** owner/landowner names · engineer name + NEC number · signatures · citizenship numbers · phone numbers · addresses · **kitta number** · **GPS coordinates** · any bank/loan references.
3. **Generalize rather than redact where useful:** keep ward-level location ("Ward 12, Kathmandu") if the contributor agrees; drop GPS entirely (GPS + kitta = trivially re-identifying).
4. Scrub PDF/document metadata (title, author fields) and EXIF from photos; blur people, vehicles, number plates in photos.
5. Automated PII pass (OCR + regex for phone/NEC/kitta patterns + a name list from the consent form) **followed by human review of 100% of released pages** for v0.x while N is small.
6. Keep originals in encrypted, access-controlled storage (separate from the public repo); log access; publish only redacted derivatives.

**Honest limit:** house layouts are themselves quasi-identifiers (a unique floor plan + a photo can re-identify a home). De-identification reduces risk; it does not eliminate it. That is why the consent form covers *publication of the layout itself* and why a contributor can choose the gated tier instead.

---

## 6. Train / val / test split

- **Split by project** (house), never by page/photo — page-level splits leak near-identical geometry.
- Target **80 / 10 / 10** by project count; with tiny N (v0.x), publish **folds** instead of one split and report cross-validation.
- **Stratify** by `source_kind` (vector vs raster vs scan), municipality, and drawing source (which consultancy — some offices reuse a standard plan, which is a leakage risk; near-duplicate detection by plan similarity, not file hash).
- **Generalization slice:** when N allows, hold out one municipality entirely as a test slice and label it as such in `meta.json`.
- Publish the split as a file (`splits/v0.1.json`) with content hashes; splits are versioned with the dataset.

---

## 7. Release mechanics (Hugging Face)

1. **Repository:** create a dataset repo (e.g. `karmi-naksa` under a team org) — public for the redacted tier. Hub dataset repos are Git repositories with revision history, so multiple dataset versions live in one repo.[HF-ADD]
2. **Dataset card:** `README.md` with YAML metadata (`license`, `language: [ne, en]`, `pretty_name`, tags such as `image`, `tabular`, `floor-plan`, `construction`); the card must document use cases, limitations, provenance and ethical considerations.[HF-CARD] Link the schema doc and paper (if any) so the Hub cross-links them.
3. **Gated tier:** for records whose consent excludes public release, enable **access requests** with **manual approval** and extra fields (affiliation, intended use) — the Hub supports exactly this workflow.[HF-GATE]
4. **File layout on the Hub:** `metadata.parquet` (one row per project) + `annotations/*.jsonl` + images under `images/`; Parquet is the recommended format for tabular metadata, raw files for images.[HF-ADD] Upload with `huggingface_hub.upload_folder` (resumable for large folders).[HF-ADD]
5. **Versioning:** Git tags on the dataset repo (`v0.1.0`, `v0.2.0` …) + a changelog section in the card; every record carries `schema_version`. Optionally mint a DOI (Zenodo mirror) once v1.0 ships so the release is citable.
6. **Baselines:** ship the model checkpoints (fine-tuned segmentation/VLM) as separate model repos with their own cards; report the model metrics *on the released test split* so numbers are reproducible.

---

## 8. Ethics — the realistic version

- **Consent is the bottleneck.** Expect weeks per project; expect refusals; expect some municipalities to say no entirely. Plan for a small, high-quality v0.1 (target: **25–50 projects**, ≥150 annotated rooms, ≥300 openings, ≥250 photos across stages) rather than a big scrape.
- **No scraping, ever** — municipal portals, Facebook groups, and designer portfolios are not data sources without permission.
- **Withdrawal is honoured in future revisions only** — say so in the form.
- **Nepal has no general data protection authority** and the Privacy Act's reach over foreign entities is unclear,[DG] but the Act's consent and purpose-limitation duties apply to us as collectors; treat them as binding regardless.
- **Annotation labour:** paid, credited, and described in the card; double-annotate ≥10% and report agreement (room polygon IoU, wall endpoint distance, opening width error, label accuracy).
- **Do not overclaim:** "first annotated dataset of Nepali naksa drawings paired with construction photos" is a claim to re-verify at release time (a fresh search found no such dataset; state the search scope in the card).

---

## 9. Prior art to position against

- **CubiCasa5K** — 5,000 Finnish floor plans, 80+ categories, polygon annotations, splits 4,200/400/400; the standard floor-plan dataset; licensed CC BY-NC 4.0 (community conversions mirror this).[CC5K][CC5K-LIC] Karmi's dataset differs in *domain* (Nepali naksa conventions, Devanagari labels) and in *pairing* (drawings + as-built photos + comparison labels).
- **Active-learning floor-plan annotation** — a published pipeline that manually annotated 500 plans and used active learning for the rest; a template for Karmi's own pre-annotate-then-correct workflow.[AL]

## Sources

- [CC5K] CubiCasa5K paper — https://arxiv.org/html/1904.01920v1 ; repo — https://github.com/cubicasa/cubicasa5k
- [CC5K-LIC] CubiCasa5K license note (CC BY-NC 4.0) — https://github.com/Shaunting/floorplan-segmentation-benchmark
- [AL] Progressive active learning floor-plan annotation — https://pmc.ncbi.nlm.nih.gov/articles/PMC10533859/
- [PA] Privacy Act, 2075 (2018), English — https://hmis.gov.np/media/22/03_The-Privacy-Act-2075-2018.pdf
- [CA] Copyright Act, 2059 (2002), English — http://www.nepalcopyright.gov.np/downloadfile/The%20Copyright%20Act_1315912777_1573122046.pdf
- [DG] Nepal jurisdiction summary (no general DPA) — https://www.dataguidance.com/jurisdictions/nepal
- [HF-ADD] HF Hub — Uploading datasets — https://huggingface.co/docs/hub/en/datasets-adding
- [HF-CARD] HF Hub — Dataset cards — https://huggingface.co/docs/hub/en/datasets-cards
- [HF-GATE] HF Hub — Gated datasets — https://huggingface.co/docs/hub/en/datasets-gated