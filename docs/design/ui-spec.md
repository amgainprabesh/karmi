# Karmi — UI specification

**Version** 0.1 · Frogtoberfest 2026 · Applies to `web/` (FastAPI app), `render/viewer.html`, and the `core/report.py` output.

**Companion files in this directory:** `wireframes.html` (the three core screens at wireframe fidelity, real Nepali labels) and `language-guide.md` (tone rules, banned words, sentence templates).

> **Rule for implementers.** Every value shown in the UI comes from `core/schema.py` (schema version 0.1.0) or from the run's `run.json`. This spec names those fields in `backticks`. If a screen seems to need data that is not in the schema, the screen is wrong — not the schema.

---

## 1. The two users

- **Homeowner (primary).** A Nepali homeowner who cannot read a drawing and wants to know, in plain Nepali, which parts of the built house to look at before they sign anything — without being scared or made to feel someone cheated.
- **Engineer / municipality (secondary).** The NEC-registered professional or local-body reviewer who receives the printed report and wants an element-by-element list where every value shows its source and confidence, so it can be verified on site in minutes.

The interface is **Nepali-first** (Nepali is the primary line, English a smaller second line) because the homeowner is the one holding the phone; the engineer can read both.

---

## 2. The honesty rules, as UI requirements

These are requirements, not suggestions. They are testable.

- **HR-1 — No bare numbers.** Every numeric value that came from extraction or comparison is rendered together with its confidence, in the same visual block (chip). The value comes from `Provenance.confidence` (extracted values) or `Delta.confidence` (comparison values). If confidence is unknown (`0.0` with `Provenance.source == "default"`), render the chip `भरोसा: थाहा भएन` — never leave it blank.
- **HR-2 — Never the word "violation".** The words *violation / violates / non-compliant* and *उल्लंघन / उल्लङ्घन* never appear in any user-visible string, English or Nepali. Copy is checked against the banned list in `language-guide.md` before merge.
- **HR-3 — Every difference is something to verify.** The noun for the collection is `जाँच्नुपर्ने बुँदाहरू` ("items to verify"). Row verbs are `फरक देखिन्छ` / `कृपया जाँच गर्नुहोस्` / `यकिन गर्न सकिएन`. Never `गलत` ("wrong"), never a verdict.
- **HR-4 — The limits panel is always visible.** `DiffReport.limits` renders as its own panel on Results and in the printed report. It is never collapsed, never behind a toggle, never hidden on mobile, never truncated. If `limits` is empty, render the standing scope line (language-guide template T8) instead of showing nothing.
- **HR-5 — Status is never colour-only.** Every status/severity/confidence chip is icon + Nepali word (+ colour). Colour is the third signal, never the only one.
- **HR-6 — No accusation.** Findings name elements, never people or trades. No builder, contractor, mason or owner is named anywhere in the UI or report. Wording per `language-guide.md` §4.
- **HR-7 — Sources are shown.** Every extracted value exposes its `Provenance.source` in human words (`नक्साबाट — सटीक` vs `फोटोबाट — अनुमान`) on the chip tooltip or in the row detail.
- **HR-8 — No silent omissions.** `SceneGraph.warnings` and `ObservedState.warnings` always render (warnings strip). `unverifiable` deltas are always listed — an item Karmi could not determine is itself information.
- **HR-9 — It is not a verdict.** A standing line ("यो निर्णय वा प्रमाणपत्र होइन — जाँच्नुपर्ने बुँदाहरूको सूची हो।") appears in the report footer and inside the limits panel.

---

## 3. Screens

Screens ↔ artifacts:

| Screen | Served by | Notes |
|---|---|---|
| Upload | `web/` `/` | plain HTML form, POST; works with JS off |
| Processing | `web/` `/run/{id}` (running state) | same URL as Results |
| Results | `web/` `/run/{id}` (done state) | server-rendered, Nepali-first |
| Verify-list detail | section of Results, anchors `#verify-{id}` | also a section of the printed report |
| 3D dual view | `render/viewer.html`, embedded on Results | consumes the run's `view.json`; enhancement only |
| Printable / PDF | `core/report.py` → `report.html` | self-contained, inline CSS, no JS |

### 3.1 Upload — `/`

**Purpose.** Take in the approved drawing and the site photos with zero jargon; set expectations about what happens next and how accurate it can be.

**Layout (words).** One column, max 640 px, calm and large. App name and one-line explanation at top. Three stacked cards: (1) drawing upload, (2) site photos, (3) optional known dimension. One primary button at the bottom. One fine-print privacy line. Everything is a plain form — no drag-and-drop requirement (drag is an enhancement).

**Exact fields shown.**

- Drawing card: file input accepting PDF/scan/photo; after selection: `source_file` filename (from the eventual `SceneGraph.source_file`) and a type note derived from `SceneGraph.source_kind` (`vector_pdf` → "भेक्टर PDF — सबैभन्दा सटीक"; `raster_pdf` → "रास्टर PDF"; `scan` → "स्क्यान"; `image` → "फोटो").
- Photos card: multi-file input; thumbnails with filename. These become `ObservedState.captures[]` (`Capture.file`, `Capture.view`).
- Optional known dimension: number + unit input. This feeds the pipeline parameter `known_dimension` and later appears as `ScaleRef(kind="user_dimension")`; echo it in the report's "कसरी नापियो" panel.
- Optional orientation: north direction in degrees (advanced, collapsed). Feeds `north_deg` and later `SceneGraph.north_deg` / `north_provenance` (`user_supplied`).
- Privacy line: "डिफल्टमा सबै प्रशोधन यही कम्प्युटरमा हुन्छ — फाइलहरू बाहिर पठाइँदैन।" (matches `docs/architecture.md` — default pipeline runs locally).

**States.**

- *Empty:* primary button disabled with helper `नक्सा छान्नुहोस्` (choose a drawing first).
- *Loading (uploading):* button becomes `पठाइँदै छ…` with spinner; inputs disabled.
- *Error — unreadable drawing:* inline banner `यो PDF पढ्न सकिएन। अर्को फाइल प्रयास गर्नुहोस् वा स्क्यानको स्पष्ट फोटो पठाउनुहोस्।` (per architecture.md failure modes: refuse and ask for a better copy; never guess).
- *Error — no photos:* banner `कम्तीमा एउटा फोटो चाहिन्छ। फोटो नभए नक्सा मात्र पनि चलाउन सकिन्छ — नतिजा आंशिक हुनेछ।` (pipeline is optional-tolerant).

**Next actions.** `जाँच सुरु गर्नुहोस्` (start). On submit → run created → Processing.

### 3.2 Processing — `/run/{id}` (running)

**Purpose.** Show honest progress; never fake a percentage; make partial failure understandable.

**Layout (words).** Centered column. Title `तपाईंको जाँच भइरहेको छ`. A vertical stage list of five stages, each with status word + glyph + elapsed time when done. Below: a live warnings/errors area (empty until something happens). A note that the page can stay open and will refresh into the result.

**Exact fields shown.**

- Stage list mirrors the pipeline stages recorded in `run.json → result.timings_ms` and `result.files`: `scene` (नक्सा पढ्दै), `observe` (फोटो हेरिँदै), `diff` (तुलना गरिँदै), `report_html` / `report_md` (रिपोर्ट बनाउँदै), `view` (3D दृश्य तयार पार्दै).
- Per-stage status: प्रतीक्षामा / भइरहेको / भयो / समस्या — derived from stage completion, never invented progress percentages.
- `run.json → result.errors[]`, `result.warnings[]` as they appear (plain Nepali rendering of the failure per §3.6 rules; raw text may be shown in a "प्राविधिक विवरण" expander).

**States.**

- *Loading:* spinner on the active stage only; elapsed seconds for finished stages.
- *Partial failure:* banner `केही चरण पूरा भएन — नतिजा आंशिक हुन सक्छ।` plus the failing stage name and the plain-Nepali reason. Next: `फेरि प्रयास गर्नुहोस्` or `फाइल परिवर्तन गर्नुहोस्`.
- *Not found:* `यो जाँच भेटिएन — लिंक जाँच्नुहोस् वा नयाँ जाँच सुरु गर्नुहोस्।`
- *Empty:* not applicable (a run always has input); do not render the screen without a run id.

**Next actions.** Wait (auto-refresh), or on failure: retry / change files / start over.

### 3.3 Results — `/run/{id}` (done)

**Purpose.** The one screen that must work for both users: Nepali summary and verify list first; a precise delta table underneath; limits always in view.

**Layout (words), top to bottom.**

1. Header: `जाँच नतिजा`, run id, run meta line, stage badge.
2. Lead narration (Nepali, from the pipeline) — the human explanation.
3. Summary cards row (six cards, horizontally scrollable on narrow screens).
4. Warnings strip (only if `SceneGraph.warnings` or `ObservedState.warnings` non-empty).
5. Delta table: columns `तत्व` (element) · `नक्सामा` (expected) · `साइटमा` (observed) · `अवस्था` (status chip) · `भरोसा` (confidence chip). Rows expand on tap to show `Delta.reason_np` / `Delta.reason`, `Provenance.source`, `Provenance.evidence`, `ObservedElement.location_hint`, and the deep links.
6. Limits panel: `कर्मीले के भन्न सक्दैन` — always visible (HR-4).
7. 3D dual view: embedded viewer (§3.5) below the table; on slow devices it loads on demand but its toggle button is always visible.
8. Verify list preview: first two `VerifyItem` cards + `सबै जाँच्नुपर्ने बुँदा हेर्नुहोस्` link (→ §3.4).
9. Actions row: `प्रिन्ट / PDF` · `नयाँ जाँच सुरु गर्नुहोस्`.

**Exact fields shown.**

- Run meta (`run.json`): `generated_at`, `drawing`, `photos` (count), `known_dimension_m` (if set), `ai_provider`.
- Stage badge: `ObservedState.stage` + `stage_provenance` → `साइटको अवस्था: भित्ता · भरोसा: उच्च (87%)`.
- Lead: `DiffReport.narration_np` (Nepali, primary), `DiffReport.narration_en` (small, secondary).
- Summary cards: exactly the keys produced by `DiffReport.recount()` — `high`, `medium`, `low`, `info`, `matched`, `verify_items` (plus `total` labelled `जम्मा`). Counts of the four severities include all deltas regardless of status — label the cards `गम्भीरता अनुसार` so this is not misread.
- Delta rows: `Delta.element`, `Delta.expected`, `Delta.observed`, `Delta.status`, `Delta.severity`, `Delta.confidence`, `Delta.reason_np`, `Delta.reason`, `Delta.scene_ref`, `Delta.observed_ref`, `Delta.id` (anchor).
- Warnings strip: `SceneGraph.warnings[]`, `ObservedState.warnings[]` verbatim.
- Limits panel: `DiffReport.limits[]` verbatim; if empty → template T8.
- Footer: `DiffReport.schema_version` / `SCHEMA_VERSION`, `scene_file`, `observed_files`.

**States.**

- *Empty (no deltas):* `कुनै फरक भेटिएन।` + standing line: `यसको अर्थ घर पूर्ण रूपमा जाँचिएको होइन — तल "कर्मीले के भन्न सक्दैन" हेर्नुहोस्।` The limits panel is still shown (HR-4).
- *Degraded run (`run.json → result.errors` non-empty):* top banner `केही चरण पूरा भएन — नतिजा आंशिक हो।` + link to technical detail.
- *Loading:* sections render skeleton blocks; the page never shows a spinner where data will be replaced without a visible text alternative.
- *Error (bad id):* same as Processing "not found".

**Next actions.** Expand a row; open the 3D view; jump to verify items; print; start a new check.

### 3.4 Verify-list detail — `#verify-{id}` (section of Results)

**Purpose.** This is the product. A numbered list of things a human should check, each with why and exactly what to do — the artifact the homeowner takes to the engineer or municipality.

**Layout (words).** Section title `कृपया जाँच गर्नुहोस् — {n} बुँदा` and one line of instruction (`यी बुँदा आफ्नो डिजाइनर वा पालिकामा लगेर जाँच्नुहोस्।`). Cards sorted by `VerifyItem.severity` (उच्च → जानकारी). Each card: severity chip row; the item in Nepali (`item_np`) with the English (`item`) beneath in small text; two labelled blocks — `किन?` (from `VerifyItem.why`) and `के गर्ने?` (from `VerifyItem.how`); a link `सम्बन्धित फरक हेर्नुहोस्` when `VerifyItem.delta_ref` resolves; a `प्रिन्ट गर्नुहोस्` action.

**Exact fields shown.** `VerifyItem.id`, `item_np`, `item`, `why`, `how`, `severity`, `delta_ref`; plus the linked `Delta`'s `element`, `expected`, `observed`, `status`, `severity`, `confidence`, `reason_np` in the card's collapsed detail.

**States.**

- *Empty (`verify_list` empty):* `यस रनमा जाँच्नुपर्ने बुँदा भेटिएन।` + `कर्मीले के भन्न सक्दैन` panel stays visible above. Never render a bare "all good".
- *Loading:* cards as skeletons.
- *Error:* if `delta_ref` does not resolve, hide the link (never show a dead link).

**Next actions.** Open the related delta; print the list; go back to the table; take it to the engineer/municipality.

### 3.5 3D dual view — `render/viewer.html` (embedded + standalone)

**Purpose.** Let a person *see* approved vs as-built — the emotional proof that this is about their actual house — then click a highlighted element and land on the same facts as the table.

**Layout (words).** A canvas area with a top toolbar: play button `2D नक्सा → 3D घर` (the extrude transition), view toggles `नक्सा (अनुमोदित)` / `बनेको (साइट)` / `दुवै तुलना`, and a persistent legend. Under the canvas: one line telling the user what the colours mean in words, plus the stage badge. Clicking a highlighted element opens a small panel (or scrolls the page) with that element's facts. The viewer is an enhancement: everything it shows also exists in the delta table.

**Exact fields shown.**

- Element popover: `Delta.element`, `Delta.status`, `Delta.severity`, `Delta.confidence`, `Delta.expected`, `Delta.observed`, `Delta.reason_np`; `Provenance.source` of the observed value.
- Room labels: `Room.name_np`, fallback `Room.name`, fallback `कोठा {Room.id}`.
- Stage badge: `ObservedState.stage` + `stage_provenance`.
- Approved geometry: `SceneGraph.walls`, `openings`, `rooms` (the renderer is deliberately dumb — it draws the model, it infers nothing).
- Elements with no delta at all: neutral grey, tooltip `यसको जाँच नतिजा उपलब्ध छैन` (never guess a colour).

**States.**

- *Loading:* `3D दृश्य तयार हुँदै छ…` + the table below stays fully usable.
- *Error (view.json missing / WebGL unavailable):* `3D दृश्य देखाउन सकिएन — सबै जानकारी तलको तालिका र जाँच सूचीमा उपलब्ध छ।`
- *Empty (no observed elements):* approved model shown alone with the note `अहिलेसम्म फोटोबाट कुनै संरचना चिनिएको छैन — नक्साको मोडेल मात्र देखाइएको छ।`
- *Reduced motion:* `prefers-reduced-motion` → the transition plays as a jump cut, not an animation.

**Next actions.** Toggle views; click an element → jump to its delta row / verify item; open full-screen; back to the table.

### 3.6 Printable / PDF report — `core/report.py` output

**Purpose.** The portable artifact: a self-contained HTML file the homeowner prints or saves as PDF and carries to the engineer or municipality. No JS, no external assets — it must open from a phone, a print shop PC, anything.

**Layout (words).** A4 portrait, single column. Header block (title, run id, date, drawing filename). One-paragraph Nepali summary. Severity summary as a simple list. Full delta table. Full verify checklist with a pen-tickable checkbox per item. Warnings. `कसरी नापियो` panel (scale references). Limits panel (never omitted — HR-4). Footer: generated_at, schema version, the standing line that this is not a verdict. Section order puts Nepali first everywhere.

**Exact fields shown.** Everything in §3.3 and §3.4, plus: `ScaleRef.kind`, `ScaleRef.value`, `ScaleRef.unit` (`brick_course` → इँटाको तह; `door_height` → ढोकाको उचाइ; `user_dimension` → तपाईंले दिनुभएको नाप; `known_object` → थाहा भएको वस्तु); `SceneGraph.north_deg` + `north_provenance` (if `None`: `उत्तर दिशा थाहा भएन — दिशा जाँचिएको छैन`); `SceneGraph.scale_m_per_unit` + `scale_provenance`; `SceneGraph.source_kind`; technical appendix with `SceneGraph.dimensions` (`Dimension.value`, `Dimension.unit`, `Dimension.label`) and room list (`Room.name_np`, `Room.area_m2`).

**States.** Static document — no loading states. If `limits` empty → T8 line. If warnings exist → amber strip. If a section has no data, print the section heading with the honest line (`यो रनमा यो खण्ड उपलब्ध छैन`) — never drop a section silently.

**Next actions.** Print; save as PDF; staple to the completion-certificate paperwork for the engineer/municipality conversation.

---

## 4. Data-to-UI mapping

Every field below exists in `core/schema.py` (v0.1.0) or `run.json` (`core/pipeline.py`). Verified against the source before merge.

| # | Schema field | Where it appears | How it is rendered |
|---|---|---|---|
| 1 | `Provenance.confidence` | Next to every extracted numeric value (table rows, verify cards, viewer popover, report) | Confidence chip: band word + `(NN%)` — `भरोसा: उच्च (87%)`. Bands: ≥0.80 उच्च · 0.50–0.79 मध्यम · 0.01–0.49 कम · `0.0` with `source == "default"` → `भरोसा: थाहा भएन` (HR-1) |
| 2 | `Provenance.source` | Chip tooltip + row detail + report appendix | Human words: `vector_geometry` → नक्साको रेखाचित्रबाट — सटीक · `raster_geometry` → नक्साको इमेजबाट — अनुमान · `ai_vision` → फोटो विश्लेषणबाट — अनुमान · `ai_text` → AI व्याख्याबाट · `user_supplied` → तपाईंले दिनुभएको · `default` → स्रोत थाहा भएन (HR-7) |
| 3 | `Provenance.evidence` | Row detail / tooltip / report appendix | Verbatim (filename, page, note) |
| 4 | `DiffReport.summary` | Results — summary cards | Six cards from `recount()` keys: `high` `medium` `low` `info` `matched` `verify_items`, plus `total` as `जम्मा`; severity cards labelled `गम्भीरता अनुसार` (counts span all statuses) |
| 5 | `DiffReport.narration_np` | Results lead paragraph; report | Nepali-first, `lang="ne"`, paragraphs joined |
| 6 | `DiffReport.narration_en` | Results, under the Nepali lead | Small English text, `lang="en"` |
| 7 | `DiffReport.deltas[]` | Results — delta table; report | One row per delta; sorted by `severity` (high→info) then `status`; matched rows visually calm; never truncated |
| 8 | `Delta.id` | Row anchor `#delta-{id}` | Deep-link target from verify items |
| 9 | `Delta.element` | Table column `तत्व`; viewer popover | Verbatim plain-language label |
| 10 | `Delta.status` | Status chip in table + viewer legend | Icon + word: `matched` → ✓ मिल्यो (green) · `differs` → ≠ फरक देखिन्छ (amber) · `missing` → ◌ भेटिएन (slate) · `unexpected` → + नक्सामा थिएन (slate) · `unverifiable` → ? यकिन गर्न सकिएन (grey). Never colour-only (HR-5) |
| 11 | `Delta.severity` | Row left accent; sort key; summary cards; verify cards | Icon + word: `high` → ▲ उच्च · `medium` → ◆ मध्यम · `low` → ▽ कम · `info` → ● जानकारी |
| 12 | `Delta.expected` | Table column `नक्सामा` | String as-is; any number inside gets its confidence chip |
| 13 | `Delta.observed` | Table column `साइटमा` | String as-is; carries the `Delta.confidence` chip (HR-1) |
| 14 | `Delta.confidence` | Confidence chip on the observed value | Same band rendering as #1 |
| 15 | `Delta.reason_np` / `Delta.reason` | Row expand + verify card detail | Nepali first, English second |
| 16 | `Delta.scene_ref` / `Delta.observed_ref` | Row detail links | `सम्बन्धित फरक हेर्नुहोस्`-style link only when the id resolves; otherwise hidden |
| 17 | `VerifyItem.item_np` / `VerifyItem.item` | Verify list card title | Nepali first (large), English below (small) |
| 18 | `VerifyItem.why` | Verify card — `किन?` | Plain text |
| 19 | `VerifyItem.how` | Verify card — `के गर्ने?` | Plain text; imperative, non-accusatory (HR-6) |
| 20 | `VerifyItem.severity` | Verify card accent + order | Same severity scale as #11 |
| 21 | `VerifyItem.delta_ref` | Verify card link | `सम्बन्धित फरक हेर्नुहोस्` → `#delta-{ref}` |
| 22 | `DiffReport.limits[]` | Results + report — `कर्मीले के भन्न सक्दैन` panel | Always visible, never collapsed (HR-4); empty → template T8 |
| 23 | `DiffReport.scene_file` / `observed_files` | Report footer / run meta | Filenames only |
| 24 | `DiffReport.schema_version` | Report footer | `Karmi schema 0.1.0` |
| 25 | `DiffReport.verify_list[]` | Results preview + report checklist | Ordered by severity; report adds a pen-tickable checkbox |
| 26 | `SceneGraph.source_kind` | Upload review + report header | `vector_pdf` → भेक्टर PDF — सबैभन्दा सटीक · `raster_pdf` → रास्टर PDF (स्क्यान) · `scan` → स्क्यान · `image` → नक्साको फोटो |
| 27 | `SceneGraph.source_file` | Upload review; report header | Filename |
| 28 | `SceneGraph.warnings[]` | Results + report — warnings strip | Amber strip above the table; verbatim; never hidden (HR-8) |
| 29 | `SceneGraph.north_deg` + `north_provenance` | Report `कसरी नापियो` panel | Degrees + source; `None` → `उत्तर दिशा थाहा भएन — दिशा जाँचिएको छैन` |
| 30 | `SceneGraph.scale_m_per_unit` + `scale_provenance` | Report appendix | Value + source |
| 31 | `SceneGraph.summary()` | Upload review; report header | Counts `walls`, `openings`, `rooms`, `dimensions`, `warnings` |
| 32 | `SceneGraph.walls[]` — `Wall.thickness`, `Wall.is_external` | 3D viewer geometry; report appendix | Not homeowner-facing; no chips needed in main flow |
| 33 | `Opening.kind` | Delta labels; viewer | `door` → ढोका · `window` → झ्याल · `vent` → भेन्ट · `unknown` → खुला भाग (प्रकार थाहा भएन) |
| 34 | `Opening.width` / `height` / `sill_height` | Delta expected/observed detail; appendix | Metres, 2 decimals + confidence chip |
| 35 | `Room.name_np` / `Room.name` | Viewer labels; report room list | Nepali first; fallback English; fallback `कोठा {Room.id}` |
| 36 | `Room.area_m2` | Report room list | m², 1 decimal + chip |
| 37 | `Dimension.value` + `Dimension.unit` + `Dimension.label` | Report technical appendix | Original unit shown; `to_metres()` conversion where available; `ft_in` → note `रूपान्तरण उपलब्ध छैन` |
| 38 | `ObservedState.stage` + `stage_provenance` | Stage badge (Results, viewer, report) | `foundation` → जग · `columns` → खम्बा · `walls` → भित्ता · `slab` → स्ल्याब · `roof` → छाना · `finishing` → फिनिशिङ · `complete` → निर्माण सम्पन्न · `site` → साइट तयारी · `unknown` → थाहा भएन; + confidence |
| 39 | `ObservedState.captures[]` | Results photo strip; report | Per photo: `Capture.file`, `view`, `taken_at`, `stage` + `stage_confidence` |
| 40 | `Capture.view` | Photo caption | `front` → अगाडिबाट · `side` → छेउबाट · `rear` → पछाडिबाट · `interior` → भित्रबाट · `aerial` → माथिबाट · `unknown` → कोण थाहा भएन |
| 41 | `ObservedElement.location_hint` | Row detail; verify card | Verbatim (e.g. `front-left corner`) |
| 42 | `ObservedElement.approx_size` | Observed column; detail | Each number + chip |
| 43 | `ObservedElement.matches_scene_id` | Linkage (not shown raw) | Resolves the row's `scene_ref` link |
| 44 | `ScaleRef.kind` / `value` / `unit` | Report `कसरी नापियो` panel | `brick_course` → इँटाको तह · `door_height` → ढोकाको उचाइ · `user_dimension` → तपाईंले दिनुभएको नाप · `known_object` → थाहा भएको वस्तु · `unknown` → थाहा भएन |
| 45 | `ObservedState.warnings[]` | Warnings strip | Same as #28 |
| 46 | `PipelineResult.errors` / `warnings` (in `run.json → result`) | Processing + degraded-run banner | Plain Nepali + next step; raw text only in a `प्राविधिक विवरण` expander |
| 47 | `run.json` — `generated_at`, `drawing`, `photos`, `known_dimension_m`, `ai_provider` | Report footer `यो रनको जानकारी`; Results meta | Date, filenames, optional dimension, provider name |
| 48 | `SCHEMA_VERSION` | Report footer | String, verbatim |
| 49 | `SceneGraph.bbox` | 3D viewer framing only | Not displayed as text |
| 50 | `SceneGraph.meta` / `DiffReport.meta` / `ObservedState.meta` | Debug only | Never displayed to users |

Notes for implementers:

- `Severity` enum has exactly four values (`info`, `low`, `medium`, `high`) and `DeltaStatus` exactly five (`matched`, `differs`, `missing`, `unexpected`, `unverifiable`) — no other words exist; do not add.
- `DiffReport.summary` is produced by `recount()`; use its keys, don't invent new counts in the UI layer.
- The report and web UI must both degrade gracefully when `scene`/`observed` stages failed (see `core/pipeline.py` — every stage is optional-tolerant).
- All `*_np` fields are optional in the schema. If a Nepali string is missing, fall back to the English field marked `lang="en"` — never render an empty line, and never machine-translate in the UI layer.
- `VerifyItem` carries no confidence of its own; when a verify item quotes a number, the number comes from its linked delta and keeps that delta's confidence chip (HR-1).

---

## 5. Typography and colour

### 5.1 Font stack (Devanagari-safe, no CDNs)

```css
--font-ui: "Noto Sans Devanagari", "Nirmala UI", "Mangal", "Kalimati",
           system-ui, "Segoe UI", Roboto, sans-serif;
```

- The stack ships with the OS on target machines (Windows: Nirmala UI; macOS: system Devanagari; Linux: Noto). **Never load fonts from a CDN** — the app must work offline (privacy default is local processing).
- Sizes: body **16 px minimum**, Nepali body text **17 px**, secondary/meta **14 px minimum**, nothing below 14 px in product UI. Headings: 20 / 24 / 30 px, weight 600.
- Line height **1.7** for Devanagari (matras clip below 1.5); never apply `letter-spacing` to Nepali text (it visually breaks conjuncts); numbers use `font-variant-numeric: tabular-nums`.
- Numerals: use Latin digits (0–9) for all measurements, counts, percentages and dates — common in Nepali engineering documents and safer to read aloud. Devanagari numerals (१, २, ३…) are acceptable only for section/step numbering in headings.

### 5.2 Palette — paper, ink, one accent, status colours

| Token | Hex | Use | Contrast (verified) |
|---|---|---|---|
| `--paper` | `#FAF7F0` | Page background (warm paper) | — |
| `--surface` | `#FFFFFF` | Cards | — |
| `--ink` | `#1C1C1E` | Primary text | 15.9:1 on paper |
| `--ink-muted` | `#57534B` | Secondary text, captions | 7.2:1 on paper |
| `--border` | `#D8D2C6` | Decorative rules, card edges | non-text |
| `--border-strong` | `#8C877B` | Input/interactive boundaries | ≥3:1 required |
| `--accent` | `#3F5D45` | THE one accent: buttons, links, focus | 7.3:1 on white; white on it 7.3:1 |
| `--sev-high` | `#A6322C` on `#F9E7E5` | Severity chip `उच्च` | 5.7:1 |
| `--sev-medium` | `#8A5A00` on `#F9F0DC` | Severity chip `मध्यम` | 5.2:1 |
| `--sev-low` | `#3F5A78` on `#EAF0F5` | Severity chip `कम` | 6.2:1 |
| `--sev-info` | `#55524B` on `#F0EEE9` | Severity chip `जानकारी` | 6.7:1 |
| `--ok` | `#2F6B45` on `#E8F2EA` | Status chip `मिल्यो` | 5.5:1 |
| `--neutral` | `#5A6472` on `#EEF0F3` | Status chips `भेटिएन` / `नक्सामा थिएन` | 5.3:1 |
| `--unknown` | `#6B675F` on `#F0EEE9` | Status chip `यकिन गर्न सकिएन` | 6.7:1 |

Rules: one accent only (deep sage — a darkened sibling of the proto's `#7d8f6b`); status colours appear only inside chips with icons and words; never tint a whole row with a status colour, use a 3 px left accent bar instead.

### 5.3 Print stylesheet note (applies to `report.html` and web print)

- `@page { size: A4 portrait; margin: 18mm 16mm; }` — the report and the web print view share it.
- Print black-on-white; assume colour may drop out — every chip keeps its icon + word, so meaning survives grayscale.
- `break-inside: avoid` on delta rows, verify cards and the limits panel; `break-before: page` before the verify checklist if the table ran long.
- No hover states, no buttons, no JS in the printed output (`core/report.py` renders self-contained HTML — keep it that way).
- Footer on the last page: `generated_at`, schema version, and the standing line from HR-9.

---

## 6. Accessibility

- **Contrast.** All text pairs in §5.2 pass WCAG AA (≥4.5:1); interactive boundaries use `--border-strong` (≥3:1). Status is never colour-only (HR-5).
- **Tap targets.** All interactive controls ≥44×44 px (buttons, chips, row toggles, links get padded hit areas). Rows are tappable across their full width.
- **768 px.** Layout is single-column from 768 px down; the delta table reflows to stacked cards (label + value pairs) instead of horizontal scroll; base font stays 16 px; nothing important is hidden on mobile — including the limits panel (HR-4).
- **JS disabled.** Upload is a plain form POST; Results, verify list, limits and warnings are server-rendered HTML. The 3D viewer is the only JS-dependent piece; when JS is off it renders a `<noscript>` note: `3D दृश्यका लागि JavaScript चाहिन्छ — सबै जानकारी तलको तालिकामा छ।` and the page remains complete.
- **Screen-reader labels for status icons.** Icons are `aria-hidden="true"`; each chip carries a visually-hidden or `aria-label` sentence, e.g. `अवस्था: फरक देखिन्छ। गम्भीरता: उच्च। भरोसा: मध्यम, 62 प्रतिशत।` Tables use real `<th scope="col">`; severity/status are announced per row, not only by colour.
- **Language.** `<html lang="ne">`; English blocks marked `lang="en"` so screen readers switch voice.
- **Keyboard.** Visible focus ring (2 px accent outline, 2 px offset); skip link to the verify list; row expanders operable with Enter/Space.
- **Motion.** The 2D→3D transition honours `prefers-reduced-motion: reduce` (jump cut instead of animation).

---

## 7. Implementation notes

- **Routes:** `/` upload → `POST` creates a run → `/run/{id}` shows Processing, then Results at the same URL. Verify items get `#verify-{id}` anchors; deltas get `#delta-{id}`.
- **`render/viewer.html`** consumes the run's `view.json` (written by `render/adapter.py → build_view()`, per `core/pipeline.py`). Architecture.md calls this component `render/transition` — the pipeline's import is `render.adapter`; reconcile the name in one place before release.
- **`core/report.py`** must keep its output self-contained: inline CSS, no JS, no external fonts (HR-4 and §5.3 depend on it).
- **Copy review:** every user-visible string passes the `language-guide.md` banned-word check before merge (HR-2). The wireframes file in this directory shows the intended composition; the language guide shows the intended words.