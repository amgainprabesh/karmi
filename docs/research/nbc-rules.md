# NBC rules & municipal numbers for a single-floor residential building

> Research notes for Karmi's diff thresholds. Compiled 2026-10-04 (NPT).
> **This file feeds the diff thresholds — a wrong number is a real bug.** Every number below states the value, the source name, the URL, and a confidence note. Where a number could not be confirmed, it is marked **UNVERIFIED — needs a municipal bylaw check** (see §8).
>
> Confidence tags: **[HIGH]** = read directly in the regulatory/municipal document; **[MED]** = one secondary source or search-index copy; **[LOW]** = practice claim needing municipal confirmation.
>
> Structural context: the two governing texts are the **National Building Code NBC 206 "Architectural Design Requirements"** (2015, second revision 2024) and municipal **building bylaws** (setbacks, FAR, coverage, height are bylaw territory, not NBC). NBC 206 itself says: *"This publication represents a standard of good practice … Compliance with it does not confer immunity from relevant legal requirements, including bylaws."* — so the bylaw check is not optional. NBC 206:2024 full text: https://ebps.itaharimun.gov.np/UploadFiles/NBC206Amended.pdf ; NBC 206:2015 full text: https://ebps.kathmandu.gov.np/UploadImage/Asset/ReferenceDoc/3/NBC_206_2015_ARCHITECTURAL_DESIGN_REQUIREMENTS.pdf — **[HIGH]** (both documents retrieved; every cited section read directly).

---

## 1. Setbacks (municipal bylaws — the national baseline)

The most widely reproduced baseline is the **Basic By-laws 2072 (2015)** / sectoral by-laws, as reproduced in the Government's PLGSP Resource Book (MoFAGA, 2023), Chapter 1.2.5 "Setback":

| # | Parameter | Value | Source | URL | Confidence |
|---|---|---|---|---|---|
| 1.1 | Side/rear setback, residential **up to 10 m height**, toward neighbour (for door/window openings) | **1.5 m** | PLGSP Resource Book, quoting Basic By-laws 2072, rules 5.2 + table | https://plgsp.gov.np/sites/default/files/2023-09/Resource_Book_on_Building_Bylaws%20and%20Building%20Permit%20System%20in_Nepal.pdf | **[HIGH]** (full text read) |
| 1.2 | Same, for a **blank wall** (no openings) | side setback **not mandatory** | same, rule 5.2 | same | **[HIGH]** |
| 1.3 | Front setback, **local road**, residential | **1.5 m from the Right-of-Way (ROW) boundary** | same, rule 5.5 + table | same | **[HIGH]** |
| 1.4 | Front setback, **national highway / feeder / district road** | **6 m** | same, rule 5.8 + table | same | **[HIGH]** |
| 1.5 | Residential **>10–17 m height** | **3 m** (table); §5.10 narrative says "at least 2 m … all sides" — internal inconsistency in the source; irrelevant to single-floor | same, rule 5.10 + table | same | **[MED]** (conflict noted) |
| 1.6 | Practice interpretation of 1.5 m | < 1.5 m to the neighbour means a "**dead wall**" — no windows may open; windows on a boundary wall are refused | nepalengineeringtoolbox naksa-pass guide | https://nepalengineeringtoolbox.com/resources/naksa-pass-guide/ | **[MED]** |
| 1.7 | Kathmandu Valley summary (secondary) | building up to 10 m high: ≥1.5 m from plot boundary; 70% ground coverage ≤250 m² plot, 60% above; ROW ≥3 m from road centre | kharchapatra blog | https://kharchapatra.com/blog/naksha-pass-cost-kathmandu | **[MED]** |
| 1.8 | Concrete municipal example (Kirtipur, 2008 bylaws, still instructive) | **detached**: 1.5 m open on all three sides + ≥1 m front from road; **semi-detached**: 1.5 m back + one side; **row**: 1 m front (ROW) + 1.5 m back | Kirtipur Municipality Building & Planning By-laws | https://www.kirtipurmun.gov.np/storage/01K56DSTRMWM9WHMTXDTYYQJ8M.pdf | **[HIGH]** (full text read) |

**Karmi reading:** for a single-floor house the operative default is **1.5 m side/rear (only where openings exist) and 1.5 m front from a local road ROW** — but this is exactly the layer that varies by municipality and by year (see §8.1). Setback thresholds must be **configuration, not constants** in `core/diff.py`.

---

## 2. Minimum room dimensions (NBC 206)

| # | Parameter | Value | Source | URL | Confidence |
|---|---|---|---|---|---|
| 2.1 | Habitable room — min dimension | **2.0 m** | NBC 206:2015 §3.2.2 (identical in 2024) | see §intro URLs | **[HIGH]** |
| 2.2 | Habitable room — min area | **6 m²** | same | same | **[HIGH]** |
| 2.3 | Kitchen — min dimension / area | **1.8 m / 5 m²** | same | same | **[HIGH]** |
| 2.4 | Toilet cubicle / WC — min dimension / area | **0.9 m / 1.2 m²** | same | same | **[HIGH]** |
| 2.5 | Bathroom — min dimension / area | **1.2 m / 1.8 m²** | same | same | **[HIGH]** |
| 2.6 | Combined WC + bath — min dimension / area | **1.2 m / 2.8 m²** | same | same | **[HIGH]** |
| 2.7 | Habitable room height (floor → lowest ceiling point) | **≥ 2.4 m** | NBC 206 §3.2.1 | same | **[HIGH]** |
| 2.8 | Bathroom / WC height | **≥ 2.0 m** | same | same | **[HIGH]** |
| 2.9 | Clear headroom under a beam / false ceiling | **≥ 2.1 m** | same | same | **[HIGH]** |
| 2.10 | Plinth height above existing road level | **≥ 450 mm** | NBC 206 §3.1 | same | **[HIGH]** |
| 2.11 | Kitchen "25% more than minimum permitted" opening (see §5) | — | NBC 206 §3.3 | same | **[HIGH]** |

Note: the 2024 revision kept all §3.2 values unchanged (only exit-route clauses were materially revised in 2024). Verify against the revision a given municipality cites.

---

## 3. Stairs (NBC 206, "Residences – General")

| # | Parameter | Value | Source | URL | Confidence |
|---|---|---|---|---|---|
| 3.1 | Minimum clear width of staircase / corridor (residential) | **0.9 m** | NBC 206 Table 3 (2015 & 2024) | §intro URLs | **[HIGH]** |
| 3.2 | Reduced-use staircase (loft/attic/terrace access only) | **600 mm** | NBC 206 §2.4 | same | **[HIGH]** |
| 3.3 | Minimum tread (residential) | **250 mm** | NBC 206 Table 4 | same | **[HIGH]** |
| 3.4 | Maximum riser (residential) | **190 mm** | NBC 206 Table 4 | same | **[HIGH]** |
| 3.5 | Maximum risers per single flight | **15** | same | same | **[HIGH]** |
| 3.6 | Minimum headroom under staircase | **2.0 m** | same | same | **[HIGH]** |
| 3.7 | Handrail height from centre of tread | **900 mm** | same | same | **[HIGH]** |

For a single-storey house, 3.1–3.4 are the checkable numbers (width, tread, riser). Karmi's "drift" fixture (stair 0.85 m vs 1.00 m) is aligned with the 0.9 m threshold.

---

## 4. Doors (NBC 206)

| # | Parameter | Value | Source | URL | Confidence |
|---|---|---|---|---|---|
| 4.1 | Residential exit door (incl. frame) | **≥ 0.9 m wide × 2.0 m high** | NBC 206 §2.2.1 (2015 & 2024) | §intro URLs | **[HIGH]** |
| 4.2 | Non-residential exit door (context) | ≥ 1.0 m × 2.1 m | same | same | **[HIGH]** |
| 4.3 | Doors of toilets / verandah (rooms not part of exit route) | permitted down to **0.75 m** wide | same | same | **[HIGH]** |
| 4.4 | Practice standard house door | **900 × 2100 mm** | enormousbuildings BOQ guide (Nepal) | https://enormousbuildings.com/bill-of-quantities/nepal/joinery | **[MED]** |
| 4.5 | Practice standard door (flood-resilient compendium) | 900 × 2200 mm | HRRP Nepal Design Compendium | https://hrrpnepal.org/uploads/media/DesignCompendiumforFloodResilientHousing-2025_compressed_20250221103110.pdf | **[MED]** |

Municipal practice requires an **opening schedule** ("Elevation of Doors and Windows showing their openings and sizes", Building Rules 2066) — door widths in Karmi should come from the schedule/dimension text, not from measured arcs.

---

## 5. Windows, lighting & ventilation (NBC 206 §3.3)

NBC 206 regulates **opening area**, not window width. For a habitable room opening to the exterior (or open verandah), excluding internal doors:

| # | Parameter | Value | Source | URL | Confidence |
|---|---|---|---|---|---|
| 5.1 | Natural light opening area | **1/10 of room area** (Hill & Mountain region); **1/8** (other regions, incl. Terai) | NBC 206 §3.3 (2015 & 2024) | §intro URLs | **[HIGH]** |
| 5.2 | Kitchen | **25% more than the minimum** (1/8 hilly / 1/6 normally) | same | same | **[HIGH]** |
| 5.3 | Natural ventilation opening area (general) | **1/16 of room area** | same | same | **[HIGH]** |
| 5.4 | Ventilation, hospitals/schools (context) | 1/8 of room area | same | same | **[HIGH]** |
| 5.5 | Recommended reference opening for a 4 × 4 m room | **1.0 × 1.5 m** (light) | same | same | **[HIGH]** |
| 5.6 | Internal courtyard minimum | **3 × 3 m** (normal-rise) | same | same | **[HIGH]** |
| 5.7 | Daylight reach | no point further than **7.5 m** from the lighting opening | NBC 206:2024 §3.3 | §intro URLs | **[HIGH]** (2024 text; 2015 has a "7.5mm" typo) |
| 5.8 | Practice window sizes | 3×3 ft (bedroom), 3×4 ft, 4×4 ft (master/living), 4×5/5×5 ft (halls); bathroom ~600×600 mm | sanam.info.np window guide; enormousbuildings | https://sanam.info.np/blog/aluminum-window-sizes-pricing-guide-nepal ; https://enormousbuildings.com/bill-of-quantities/nepal/joinery | **[MED]** |
| 5.9 | Common mm modules seen on drawings | 900×1200, 1200×1200, 1500×1200 mm | housedesigninnepal door/window guide | https://tools.housedesigninnepal.com/blog/door-window-cost-size-standards-nepal | **[MED]** |

**Karmi reading:** to check a window, compute **opening area ÷ room area** against 1/10 (hills) or 1/8 (Terai/other) — a width-only check can pass while the code check fails. Karmi's `Room.area_m2` and `Opening.width/height` support this directly.

---

## 6. Other numbers likely to be touched

| # | Parameter | Value | Source | URL | Confidence |
|---|---|---|---|---|---|
| 6.1 | Maximum travel distance to exit (single floor) | 30 m (40 m with external corridor) — never binds on a small house | NBC 206 §2.2 | §intro URLs | **[HIGH]** |
| 6.2 | Second staircase required above | 500 m² plinth — never binds for single-floor residential | NBC 206 §2.4.1 | same | **[HIGH]** |
| 6.3 | Compound/boundary wall (practice) | max ~4 ft solid + 3 ft grill (≈7 ft total) | nepalengineeringtoolbox naksa guide; meroproperty | https://nepalengineeringtoolbox.com/resources/naksa-pass-guide/ ; https://www.meroproperty.com/building-construction-law-in-nepal | **[MED]** |
| 6.4 | Ground coverage (practice) | 70% for plots ≤250 m², 60% above (Kathmandu Valley baseline) | kharchapatra; meroproperty | (above) | **[MED]** |
| 6.5 | Building classes (context) | A/B/C by height, area, span; single-floor small house = Class C, no structural design required | Building Act 2055 §8; ghardurbar summary | https://ghardurbar.com/blogs/%E0%A4%A8%E0%A4%BF%E0%A4%B0%E0%A5%8D%E0%A4%AE%E0%A4%BE%E0%A4%A3-%E0%A4%B8%E0%A4%AE%E0%A5%8D%E0%A4%AC%E0%A4%A8%E0%A5%8D%E0%A4%A7%E0%A5%80-%E0%A4%AE%E0%A4%BE%E0%A4%AA%E0%A4%A6%E0%A4%A3%E0%A5%8D%E0%A4%A1 | **[MED]** |

---

## 7. Tolerance for deviation that municipalities actually apply in practice

**Finding: no published numeric tolerance exists — in either the NBC or any municipal bylaw found.** What exists instead is a *process*:

| Mechanism | What it is | Source | URL | Confidence |
|---|---|---|---|---|
| Stage inspections | Temporary permit (up to plinth) → permanent permit after plinth verification → completion certificate after final inspection. Municipal engineers measure the site at plinth stage to verify setbacks, and the final inspection "verif[ies] that the actual construction has been done as per the approved designs and drawings". | PLGSP Resource Book §3.1.1; JICA Building Code Working Paper | https://plgsp.gov.np/... (above); https://www.jica.go.jp/oda/project/1900306/news/__icsFiles/afieldfile/2025/06/04/bcwp_en.pdf | **[HIGH]** (PLGSP), **[MED]** (JICA) |
| "Justification for variations" | The municipal field-inspection checklist has columns "According to Municipal Approval Drawing / According to Actual Construction in Site / **Justification for variations**" — i.e. deviations are judged and justified, not compared to a numeric tolerance. | PLGSP Resource Book, Annex IV checklist | (above) | **[HIGH]** (full text read) |
| Regularization | Deviating buildings are typically brought back in line via a revised **as-built drawing + penalty fee** ("map amendment"), rather than a fixed tolerance. | amarnepal guide | https://amarnepal.com/guides/building-permit-process-nepal-guide | **[MED]** |
| Enforcement discretion | Penalties for contravening the permit (e.g. up to Rs 100,000 and/or 1 year imprisonment under Kirtipur's bylaw) are discretionary; the inspector decides. | Kirtipur bylaw §6 | (above) | **[HIGH]** |
| Reality check — how much drifts | In a Birendranagar study, only **5 of 22 completed buildings fully complied** with approved designs; common deviations: staircase dimensions, plinth area, room layout. Inspections focus on the plinth stage. A JICA review likewise notes "constructions have been different from building design drawings in many cases". | Rijal et al. 2025, OCEM Journal; JICA BCWP | https://www.nepjol.info/index.php/ocemjmtss/article/download/74756/57272/216375 ; JICA URL above | **[HIGH]** (study read) |

**Design consequence for Karmi (engineering choice, NOT a legal number):** since no legal tolerance exists, `core/diff.py` should not pretend to apply one. Recommended: a **configurable `noise_floor`** per municipality (default suggestion: ±50 mm on linear dims / ±2% on areas, labeled "measurement noise"), and everything above it becomes a `VerifyItem` with severity — never a "violation". This default is our engineering choice and must be documented as such in the config, not presented as a legal tolerance.

---

## 8. UNVERIFIED — needs a municipal bylaw check

Everything in this section must be checked against the actual municipal bylaw before being encoded anywhere in the diff engine.

1. **Current Kathmandu Valley / KMC / Lalitpur setback values for single-floor residential after the 2078 B.S. (2022) bylaw amendments.** Secondary sources indicate the 2078 amendments changed setback and height provisions (IOE conference paper: "latest building bylaws 2078 concerned with major modification on setback, building height, FAR" — https://conference.ioe.edu.np/publications/ioegc12/IOEGC-12-113-12163.pdf), and one news piece reports new front setbacks (6 m Kathmandu Valley / 8 m Terai) and a 1.5 m rule for buildings up to 10 m — but that article is a machine-translated news report and its numbers are internally garbled (https://www.janaaastha.com/story/127336). **UNVERIFIED — needs a municipal bylaw check.**
2. **Whether the 1.5 m side/rear rule is universal or municipality-specific.** Kirtipur (2008) uses 1.5 m for detached homes on three sides and 1 m front for some building types; the PLGSP table gives 1.5 m front for local roads. Both can be true in different municipalities. **UNVERIFIED — needs a municipal bylaw check.**
3. **The basis from which the front setback is measured** — ROW boundary vs plot boundary vs road centre. PLGSP says "from the boundary of rights way"; some sources describe distance from road centre (e.g. "at least 3 m from the centre of the connecting road"). **UNVERIFIED — needs a municipal bylaw check.**
4. **Any numeric construction tolerance** (e.g. ±X mm on room dimensions or openings at inspection). None found in NBC 206, the PLGSP book, or any municipal document retrieved. **UNVERIFIED — needs a municipal bylaw check** (and likely does not exist in written form anywhere; ask the Building Permit section directly).
5. **Minimum window width as such.** NBC 206 regulates opening *area* (§5); no minimum window width was found. Do not invent one. **UNVERIFIED — needs a municipal bylaw check** if a width threshold is ever required.
6. **Thaha Municipality drawing rules** (borders, sheet sizes) — search-index only (PDF fetch 404). **[MED]** confidence, flag for later.
7. **Whether "NBC 206:2015" or "NBC 206:2024" is the revision your municipality enforces** — the 2024 revision is gazetted and in force nationally (Nepal Gazette 2081/02/28 per the 2024 document's preface), but municipalities with older eBPS templates may still reference 2015. Check the municipal checklist. **UNVERIFIED — needs a municipal bylaw check.**

---

## 9. Sources (primary list)

- NBC 206:2024 (DUDBC) — https://ebps.itaharimun.gov.np/UploadFiles/NBC206Amended.pdf
- NBC 206:2015 (DUDBC) — https://ebps.kathmandu.gov.np/UploadImage/Asset/ReferenceDoc/3/NBC_206_2015_ARCHITECTURAL_DESIGN_REQUIREMENTS.pdf
- Building Rules, 2066 (2009) — https://www.iibh.org/kijun/pdf/Nepal_02_Building_Rule_2009.pdf
- PLGSP / MoFAGA Resource Book on Building By-laws and Building Permit System (2023) — https://plgsp.gov.np/sites/default/files/2023-09/Resource_Book_on_Building_Bylaws%20and%20Building%20Permit%20System%20in_Nepal.pdf
- Kirtipur Municipality Building & Planning By-laws — https://www.kirtipurmun.gov.np/storage/01K56DSTRMWM9WHMTXDTYYQJ8M.pdf
- Rijal, Bhattarai, Baduwal & Khatri (2025), "Assessing Code Compliance and Mason Proficiency in Residential Construction in Birendranagar Municipality" — https://www.nepjol.info/index.php/ocemjmtss/article/download/74756/57272/216375
- JICA, Building Construction Working Paper (Nepal) — https://www.jica.go.jp/oda/project/1900306/news/__icsFiles/afieldfile/2025/06/04/bcwp_en.pdf
- nepalengineeringtoolbox — naksa-pass guide: https://nepalengineeringtoolbox.com/resources/naksa-pass-guide/ ; masonry guide: https://nepalengineeringtoolbox.com/resources/house-construction/brick-masonry-construction-guide/
- amarnepal building-permit guide — https://amarnepal.com/guides/building-permit-process-nepal-guide