# Naksa drawing conventions — how Nepali building-permit drawings look and how to read them

> Research notes for Karmi's extraction stage (drawing → scene graph). Compiled 2026-10-04 (NPT).
> Every claim carries a source URL and a confidence tag.
> **[HIGH]** = read directly in a primary/regulatory or municipal document; **[MED]** = single secondary source, or a search-index copy of a document that could not be re-fetched; **[LOW]** = practice claim that still needs a municipal bylaw check.
> `UNVERIFIED` items are flagged in place and collected in §10.

Karmi's scope: **single-floor residential** sets, both CAD-exported vector PDFs and scans. Everything below is about reading *approved* (naksa-pass) drawings, not construction working drawings.

---

## 1. The drawing set submitted to a municipality

The national baseline is **Building Rules, 2066 (2009)** (framed under the Building Act, 2055). Schedule 1 lists what a permit application attaches:[BR]

| Group | Sheets (Schedule 1) |
|---|---|
| Architectural | Floor plans · Elevations · **Two sections — longitudinal and cross, one through the staircase** · Site plan · Elevation of doors and windows showing openings and sizes · Staircase details · Ramp details |
| Structural (frame buildings) | Column reinforcement (critical column, position indicated) · critical beam reinforcement · slab reinforcement · staircase reinforcement · trench plan & toe wall · critical foundation details · ductile detailing of beam–column joints |
| Structural (load-bearing) | Floor plan with vertical steel at critical sections · trench plan & foundation details · slab reinforcement · wall cross section |
| Sanitary / Electrical | Category "A"/"B" buildings only (toilet plans, roof plan, septic/soak pit, wiring layout, etc.) |

- Source: Building Rules 2066, English translation (iibh.org) — https://www.iibh.org/kijun/pdf/Nepal_02_Building_Rule_2009.pdf — **[HIGH]** (full text read). The same lists appear in the PLGSP Resource Book — https://plgsp.gov.np/sites/default/files/2023-09/Resource_Book_on_Building_Bylaws%20and%20Building%20Permit%20System%20in_Nepal.pdf — **[HIGH]**.
- A **single-floor residential house is typically Class "C"**: under Rule 3(2) only *drawings* (no structural design) are required — but municipalities routinely ask for more, and eBPS portals push a 4-set bundle (Architectural, Structural, Sanitary, Electrical). Source: nepalengineeringtoolbox naksa-pass guide — https://nepalengineeringtoolbox.com/resources/naksa-pass-guide/ — **[MED]**.
- One municipality's concrete sheet naming (Birtamod, Jhapa): `A_1` location map + site plan; `A_2` floor plans (max 2 per sheet); `A_3` elevations; `A_4` sectional elevations; structural `S_1`–`S_10`. Source: Birtamod Municipality, *A3 Sheet details* (PDF) — https://birtamodmun.gov.np/sites/birtamodmun.gov.np/files/documents/A3_Sheet%20details%20birtamode%20municipality.pdf — **[HIGH]** (full text read).

**Reading implication for Karmi:** a full set is multi-sheet and multi-scale. Extraction should treat *ground floor plan* as the primary geometry source, *site plan* for setbacks/orientation, and *schedules + sections* for opening heights; expect only the ground-floor plan in v0 scope.

---

## 2. Sheet layout and title block ("name plate")

- **Paper size:** A3 = 297 × 420 mm is the standard submission sheet (Birtamod, Lalitpur EBPS). Some municipalities accept A2/A4 as well; A4 is used for cover pages and corrections. Sources: Birtamod PDF (above) — **[HIGH]**; Lalitpur Metropolitan City EBPS, *नक्शा पेश गर्दा ख्याल गर्नुपर्ने कुराहरू* (PDF) — https://www.lsmcebps.gov.np/UploadFiles/naksha_pesh_garda%20_khyal_garnu_parne_kuraaharu.pdf — **[HIGH]** (full text read); Thaha Municipality Naksa Pass Book — https://www.thahamun.gov.np/sites/thahamun.gov.np/files/documents/Naksa%20Pass%20Book_0.pdf — **[MED]** (retrieved via search index; direct fetch returned 404 on 2026-10-04).
- **Borders:** left margin 1.5 in, other sides 0.5 in (Thaha) — **[MED]**. Birtamod notes IS 962:1989 for layout/folding/symbols — **[HIGH]**.
- **Name plate / title block at the bottom of the sheet**, with (Lalitpur EBPS list):[LMC]
  - Name of landowner and house owner
  - Name of engineer + Nepal Engineering Council (NEC) registration
  - Land details: kitta (plot) number, land area, plot area, ward no.
  - GPS coordinates of the land
  - Scale of drawing
  - Name of consultant (if any)
  - **Sheet number and description of the drawing**, date of submission
- A sample A3 layout in the same document shows fields: OWNER · BUILDING TYPE · PLOT NO · GPS COORDINATE (Lat/Long) · LAND AREA · LOCATION · SCALE · SHEET NO · DRAWN BY · CHECKED BY · REC NO · DATE.[LMC] — **[HIGH]**.
- Birtamod's required cover page carries: applicant name/address, citizenship no., contact no., plot no., plot area, building category, no. of storeys, floor areas, ground coverage %, FAR, registration number, permit-stage dates. Source: Birtamod cover page format — https://birtamodmun.gov.np/sites/birtamodmun.gov.np/files/documents/Cover%20Page%20format%20v2.0.pdf — **[MED]** (search-index read).
- University course notes for NEC registration describe the same name-plate contents ("name plate at the bottom of the drawing sheet … kitta number, land area, plot area, ward no., Google coordinate, scale, consultant, sheet number, description, date"). Source: Pokhara University course notes (NEC NUM), via Studocu — https://www.studocu.com/row/document/pokhara-university/civil-engineering/architectural-drawing-guidelines-floor-plans-site-plan-nec-num/136812480 — **[MED]**.

**De-identification note for the dataset:** the name plate is exactly where all the PII lives (names, NEC number, kitta, GPS, signatures, dates). See `dataset-plan.md` §5.

---

## 3. Scale conventions

| Drawing | Scale | Source |
|---|---|---|
| All drawings (default) | **1:100 or 1″ = 8′** | Building Rules 2066 Schedule 1 note[BR] — **[HIGH]** |
| Details (minimum allowed) | **not smaller than 1:50 or 1″ = 4′** | same — **[HIGH]** |
| Site plan | 1:100 up to 1 ropani; 1:200 (or 1″ = 16′) for more | same; Lalitpur EBPS: 1:100 ≤1 ropani, 1:200 ≤3 ropani, 1:400 above — **[HIGH]** |
| Structural details (practice) | foundation 1:25 · column/beam sections 1:20 · frame sections 1:50 · enlarged details 1:10/1:5 | Birtamod PDF — **[HIGH]** |

- **Both metric and feet-inch notations are live**: the regulation itself writes "1:100 **or** 1″ = 8′"; Thaha writes "1:100 (1/8″ = 1′-0″), 1:200 (1″ = 16′)" — **[MED]**.
- Lalitpur EBPS instructs submissions to use the **metric system**, but building area in **both metric and sq ft** — **[HIGH]**. So expect dimension text in mm/m *and* in feet/inches on the same set; the `Dimension.unit` enum (`m` / `ft` / `ft_in` / `unknown`) exists for exactly this.
- **Discrepancy flagged:** the English translation of Building Rules 2066 says site plan "1:1200 or 1″ = 16′" for plots over 1 ropani; the Nepali original on moljpa.gov.np writes 1:200, and Lalitpur EBPS says 1:200/1:400. Treat "1:1200" as a typo; **UNVERIFIED — needs a municipal bylaw check** if it ever matters (it doesn't for single-floor extraction; scale is read from the sheet anyway).

---

## 4. Dimensioning conventions

- Required dimension types (Lalitpur EBPS): **element-to-element, center-to-center, overall (easy to compute area), and internal room size + room name**.[LMC] — **[HIGH]**. Thaha adds the classic drafting rule "**dimension shall be read out and not measured**" (i.e. trust the printed number, not the scaled distance) — **[MED]**.
- Dimension lines sit outside the wall lines with tick/slash terminators; the number is the **real-world** size regardless of scale (generic convention; see §6 sources) — **[HIGH]** as a convention.
- Units seen in practice: feet-inches (`12'-6"`, older sets, hand drafting) and millimetres/metres (CAD-era, eBPS). Ropani/Aana/Dam are used for *land* areas, not building dims. The PLGSP measurement table lists both systems side by side (1 ft = 30.48 cm; 1 ropani = 5476 sq ft) — **[HIGH]** (PLGSP full text).
- **Karmi rule of thumb:** never scale geometry from the sheet for *reported* dimensions — prefer parsed dimension text (`Dimension` objects) plus `scale_m_per_unit` only for cross-checking. Nepali sets frequently disagree slightly between drawn geometry and dimension text.

---

## 5. North arrow

- **All three municipal sources say the same thing: north points to the top (header) of the sheet** — site plan specifically. Birtamod ("North direction should always point towards the upper (header) side"), Lalitpur EBPS ("उत्तर दिशा माथि तर्फ नै हुनु पर्ने"), Thaha ("North directions should always point towards the upper (header) side").[LMC] — **[HIGH]** (Birtamod, LMC), **[MED]** (Thaha).
- Lalitpur also asks for a **location plan with the nearest junction in the north direction**, and a survey-direction north on the site plan — **[HIGH]**.
- Karmi's failure mode is already designed for: if no north arrow → ask the user, flag uncertainty (`SceneGraph.north_deg`, `north_provenance`). Note that **project north vs true/survey north can differ** on the same set — record what the arrow says, don't infer.

---

## 6. Common symbols (what extraction must recognize)

No Nepali municipal document defines symbols itself — Birtamod explicitly defers: "For Building drawing layouts, scales, folding of drawing sheets and drawing symbols **refer IS 962 : 1989**" (the Indian Standard code of practice for architectural drawing).[BIR] — **[HIGH]**. IS 962 is also what NEC exams teach — the NEC license-exam prep PDF asks title-block questions — https://panafile.b-cdn.net/crash%20course/QAD%20(3)%20(1).pdf — **[LOW]**.

Standard conventions (per IS 962 / international drafting practice; general sources):

| Symbol | Appearance | Meaning |
|---|---|---|
| Wall | thick parallel lines (double line); thickness = spacing | solid wall; external vs internal by thickness |
| Single door | break in wall + straight leaf line + quarter-circle **swing arc** | hinge side and swing direction from the arc |
| Double/sliding door | two arcs meeting / two overlapping panels, no arc | type distinction |
| Window | thin break in wall with 2–3 parallel lines (glass/frame lines) | opening; width read at the break |
| Stair | run of parallel tread lines + **arrow with UP/DN** | direction of travel; arrow points up from the current floor |
| Section cut | heavy line with arrows + letters (A–A, B–B) | where the building is sliced and which way it is viewed |
| North arrow | arrow in a circle, letter N | orientation (top of sheet, see §5) |
| Level mark | small triangle/circle with a number (e.g. +0.600) | reduced level of floor/sill/landing |

Sources for the symbol conventions: StudioMatrx guide — https://www.studiomatrx.org/guides/construction-drawing-symbols-homeowners-should-know — **[MED]**; ArchitectureCourses symbols guide — https://www.architecturecourses.org/design/architectural-drawing-symbols — **[MED]**; illustrarch floor-plan guide — https://illustrarch.com/articles/75463-architecture-floor-plan.html — **[MED]**; SmartDraw symbol list — https://www.smartdraw.com/floor-plan/floor-plan-symbols.htm — **[MED]**; SFP architectural conventions (north arrow placement, section call-outs) — https://www.sfponline.org/uploads/14/architecturalsymbolsandconventions.pdf — **[MED]**.

**Karmi extraction implication:** door-swing arcs are the strongest signal that a gap is a *door* (vs a window or a plain gap); stair arrows are how the stair run gets an orientation; section marks can be ignored for v0. Municipalities require the **door/window opening schedule** on the sheet ("Elevation of Doors and Windows showing their openings and sizes" — Building Rules 2066), so widths/heights should preferentially come from the schedule text, not from measured arcs.

---

## 7. Wall thicknesses used in practice

| Element | Thickness | Source | Confidence |
|---|---|---|---|
| Exterior brick wall ("एक इट्टा गारो", full-brick) | **9″ ≈ 230 mm** (nominal brick 240 × 115 × 57 mm w/ mortar) | nepalengineeringtoolbox masonry guide — https://nepalengineeringtoolbox.com/resources/house-construction/brick-masonry-construction-guide/ | **[HIGH]** as practice |
| Interior partition ("आधा इट्टा गारो", half-brick) | **4.5″ ≈ 110–115 mm** | same source; buildupnepal CSEB cost report (230 mm external / 115 mm internal fired brick) — https://www.buildupnepal.com/wp-content/uploads/2022/07/report-on-cseb-cost-comparison-structural-performance.pdf | **[HIGH]** as practice |
| Non-load-bearing walls, code limits | min ½ brick (110 mm), max 1 brick (230 mm) | NBC 202:2015 — https://giwmscdnone.gov.np/media/app/public/54/posts/1679824354_21.pdf (search-index copy; direct fetch failed) and load-bearing-masonry guideline — https://giwmscdnone.gov.np/media/pdf_upload/NBC%20202%202015%20Guidline%20on%20Load%20Bearing%20Masonry_zwnw0l0.pdf | **[MED]** |
| Partition walls (min) | **115 mm**, with horizontal reinforcement | NBC 109:1994 (Unreinforced masonry) — https://giwmscdnone.gov.np/media/pdf_upload/NBC%20109-1994%20Masonry%20Unreinforced_liuddba.PDF | **[MED]** |
| Infill wall in Category I/II buildings | not less than **230 mm** | NBC 109:1994 (same) | **[MED]** |

- Practice detail worth knowing: 9″ walls are laid in English bond with 1:6 mortar; 4.5″ partitions in stretcher bond with 1:4 mortar and horizontal rebar every 3–4 courses; exterior 4.5″ walls are "not recommended in Nepal". Source: nepalengineeringtoolbox (above) — **[MED]**.
- Market reality: Nepali bricks are commonly ~230 × 110 × 55 mm, nominal ~240 × 115 × 57 mm with mortar. Sources: satwahomes brick-price article — https://satwahomes.com/blog/brick-price-in-nepal/ — **[LOW]**; nepalengineeringtoolbox — **[MED]**.
- Karmi's own fixtures already encode this: `fixtures/make_naksa.py` draws external walls at **0.23 m** and internal at **0.115 m** (local file), which matches the sources above.

**Reading tip:** on scanned drawings the wall thickness is the gap between the wall line pair; on many Nepali plans *both* wall faces are drawn but only some dimension chains give the thickness — cross-check with 9″/4.5″ priors before trusting a raw pixel measurement.

---

## 8. Room label vocabulary (Devanagari ↔ English)

Drawings in practice mix English and Nepali labels (English all-caps is common on CAD sets; Nepali appears on scanned/hand-drafted sets and in municipal forms). Karmi stores both: `Room.name` (English) and `Room.name_np` (Devanagari).

| Devanagari | Romanized | English | Source |
|---|---|---|---|
| कोठा | koṭhā | room (generic) | talkpal / learnentry[TP][LE] |
| बैठक कोठा (बैठक) | baiṭhak koṭhā | living / sitting room | ling-app / talkpal / learnentry[LA][TP][LE] |
| बस्ने कोठा | basne koṭhā | living room (variant) | talkpal[TP] |
| सुत्ने कोठा | sutne koṭhā | bedroom | ling-app / talkpal / learnentry[LA][TP][LE] |
| शयन कक्ष | śayan kakṣa | bedroom (formal) | talkpal / lingualabs[TP] |
| भान्सा कोठा · भान्छा कोठा | bhānsā / bhānchhā koṭhā | kitchen | MLIT Nepali doc (भान्सा कोठा)[MLIT]; learnentry (भान्छा)[LE] |
| खाना खाने कोठा | khānā khāne koṭhā | dining room | MLIT doc[MLIT] |
| भोजन कक्ष | bhojan kakṣa | dining room (formal) | ling-app[LA] |
| शौचालय | śaucālaya | toilet / latrine | talkpal / ling-app / learnentry[TP][LA][LE] |
| बाथरुम | bātharuma | bathroom (loanword, very common) | talkpal / ling-app[TP][LA] |
| स्नानघर | snānaghar | bath room (native) | talkpal[TP] |
| पूजा कोठा | pūjā koṭhā | prayer room (northeast corner per Vastu) | nepalnaksa / expertsewa / nepaljyotish[NN][ES][NJ] |
| सिँढी (सीढी) | sĩḍhī (sīḍhī) | stairs | ling-app[LA] |
| छत / छाना | chhat / chhānā | roof / roof-covering | talkpal / ling-app[TP][LA] |
| आँगन | ā̃gan | courtyard | talkpal[TP] |
| भुइँ तला | bhuĩ talā | ground floor | ling-app[LA] |
| दोस्रो तला | dosro talā | second floor | ling-app[LA] |

- **[MED]** for the language-learning sources (they occasionally mis-align rows — e.g. one ling-app table swaps toilet/utility entries; only use terms that agree across ≥2 sources, as above).
- Labels commonly seen in practice that still lack a citable Nepali source in this pass: **बरन्डा** (verandah), **ग्यारेज** (garage), **भण्डार कोठा** (store). Marked **UNVERIFIED — needs a native-speaker check** before shipping in the label lexicon.
- Drawing abbreviations also appear in English (BED, KIT, WC, LIV, TOILET, PUJA, STAIR) — treat label language as a per-sheet property, not a per-municipality one.

---

## 9. Reading recipe for Karmi (order of operations)

1. **Find the sheet type** (title/name plate, sheet number `A_2…`).
2. **Read scale** from the title block/scale note (1:100 typical); record `scale_m_per_unit` + provenance.
3. **Find north** (top-of-sheet arrow) → `north_deg`.
4. **Trace walls** as double-line pairs → `Wall.start/end/thickness`; classify external (≈230 mm) vs internal (≈115 mm).
5. **Find openings**: gaps + arcs = doors; gaps + thin parallel lines = windows; consult the opening schedule for sizes → `Opening.kind/width/height`.
6. **Close room polygons** between walls; OCR the label → `Room.name/name_np/polygon`.
7. **Parse dimension chains** (element / centre-to-centre / overall / internal) → `Dimension` objects; use them as ground truth over pixel measurements.
8. **Site plan** → setback distances (building face ↔ plot boundary) as dimension objects; note that `core/schema.py` models setbacks as observed elements (`ElementKind.SETBACK`) — keep the site-plan setbacks as `Dimension` + `meta` until the diff stage needs them.
9. Emit warnings for anything missing (no north, no scale, no schedule) — the schema's `warnings` list exists for this.

---

## 10. UNVERIFIED / flagged items

- **Site-plan scale "1:1200"** in the English Building Rules 2066 translation vs "1:200" in the Nepali original and Lalitpur EBPS — treat as translation typo; **UNVERIFIED — needs a municipal bylaw check** if used programmatically.
- **Thaha Municipality details** (borders 1.5″/0.5″, A2/A3/A4, "site plan + ground floor + section on the same sheet") — search-index copy only; direct PDF fetch returned 404. **UNVERIFIED — needs a municipal bylaw check** (corroborated in substance by Birtamod/LMC, so low risk).
- **Exact name-plate field set varies per municipality** (Lalitpur's list is the most complete one found; Birtamod uses a cover page). Do not assume one fixed template when redacting — detect the title block region per sheet.
- **Devanagari labels for verandah/garage/store** — no citable source yet; needs a native-speaker check.
- **Whether a majority of single-floor sets are vector PDFs** — this is Karmi's ingestion assumption (README: "the Naksa Pass set is usually CAD-exported"); no statistic found either way. Treat as assumption until the dataset exists.

## Sources

- [BR] Building Rules, 2066 (2009), English translation — https://www.iibh.org/kijun/pdf/Nepal_02_Building_Rule_2009.pdf ; Nepali original (moljpa.gov.np) — https://www.moljpa.gov.np/wp-content/uploads/2024/08/%E0%A4%AD%E0%A4%B5%E0%A4%A8-%E0%A4%A8%E0%A4%BF%E0%A4%AF%E0%A4%AE%E0%A4%BE%E0%A4%B5%E0%A4%B2%E0%A5%80%E0%A5%A8%E0%A5%A6%E0%A5%AC%E0%A5%AC.pdf
- [BIR] Birtamod Municipality A3 sheet format — https://birtamodmun.gov.np/sites/birtamodmun.gov.np/files/documents/A3_Sheet%20details%20birtamode%20municipality.pdf
- [LMC] Lalitpur Metropolitan City EBPS, naksa submission guidelines — https://www.lsmcebps.gov.np/UploadFiles/naksha_pesh_garda%20_khyal_garnu_parne_kuraaharu.pdf
- [THA] Thaha Municipality Naksa Pass Book — https://www.thahamun.gov.np/sites/thahamun.gov.np/files/documents/Naksa%20Pass%20Book_0.pdf (fetch 404; search-index only)
- [PLGSP] Resource Book on Building By-laws and Building Permit System in Nepal (MoFAGA/PLGSP, 2023) — https://plgsp.gov.np/sites/default/files/2023-09/Resource_Book_on_Building_Bylaws%20and%20Building%20Permit%20System%20in_Nepal.pdf
- [LA] ling-app rooms vocabulary — https://ling-app.com/blog/vocabulary-for-rooms-in-nepali/
- [TP] talkpal household items — https://talkpal.ai/culture/what-are-the-words-for-household-items-in-nepali/
- [LE] learnentry building vocabulary — https://www.learnentry.com/english-nepali/vocabulary/building-in-nepali/
- [MLIT] Japan MLIT Nepali-language housing PDF — https://www.mlit.go.jp/common/001316937.pdf
- [NN] nepalnaksa.com (पूजा कोठा) — https://www.nepalnaksa.com/home-design-architecture-construction-cement-steel-pipe-fitting-colours-nepal/
- [ES] expertsewa Nepal home design — https://expertsewa.com/blog/nepal-home-design-2026-transform-space-sanctuary
- [NJ] nepaljyotish Vastu page — https://nepaljyotish.org/en/vastu-shastra/