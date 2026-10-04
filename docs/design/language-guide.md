# Karmi — language guide

**The words Karmi is allowed to use.** Every user-visible string — web UI, report, error messages, emails, demo video captions — is checked against this file. When in doubt, use a template from §5 rather than composing new copy.

Two columns everywhere: **SAY THIS** / **NEVER SAY THIS**, in English and Nepali.

---

## 1. The three core phrases

These carry the product's whole posture. Use them exactly:

| Phrase | Meaning | Use it when |
|---|---|---|
| **कृपया जाँच गर्नुहोस्** | please verify / have this checked | addressing the homeowner about a specific finding |
| **फरक देखिन्छ** | a difference appears (is visible) | describing what the comparison shows — without asserting why |
| **यकिन गर्न सकिएन** | could not be determined | whenever Karmi lacks the evidence to say anything stronger |

Rule: a finding never graduates from "फरक देखिन्छ" to anything stronger without a human verifying it on site. Karmi reports; people decide.

---

## 2. SAY THIS / NEVER SAY THIS

| # | Situation | ✅ SAY THIS (EN) | ❌ NEVER SAY THIS (EN) | ✅ SAY THIS (NE) | ❌ NEVER SAY THIS (NE) |
|---|---|---|---|---|---|
| 1 | Describing a difference | "This may differ from the approved drawing." / "The drawing shows X; the photo suggests Y — please verify." | "This violates the approved drawing." / "Violation." | "यो अनुमोदित नक्साभन्दा फरक देखिन्छ।" / "नक्सामा X छ; फोटोमा Y देखिन्छ — कृपया जाँच गर्नुहोस्।" | "यसले नक्साको उल्लंघन गरेको छ।" / "उल्लंघन।" |
| 2 | Asking for verification | "Please verify." / "Have this checked." | "This is wrong." / "It was built incorrectly." | "कृपया जाँच गर्नुहोस्।" / "यो एक पटक जाँच्नुहोस्।" | "यो गलत छ।" / "यो बनाइएको गलत छ।" |
| 3 | Cannot determine | "We could not determine this from the available photos." / "This needs a closer photo or a tape measure." | *(silence — dropping the item)* / "Probably fine." | "उपलब्ध फोटोबाट यो यकिन गर्न सकिएन।" / "यसका लागि नजिकको फोटो वा टेपले नाप्नु आवश्यक छ।" | *(बुँदा नै नलेख्ने)* / "ठीकै छ होला।" |
| 4 | Confidence in plain words | "This measurement comes from a photo — treat it as approximate (about ±10–20 cm)." / "This one comes from the drawing, so it is exact." | "The window is 1.02 m." *(bare number)* / "99% accurate." | "यो नाप फोटोबाट अनुमान गरिएको हो — लगभग मान्नुहोस् (करिब 10–20 सेन्टिमिटर तलमाथि हुन सक्छ)।" / "यो नाप नक्साबाट आएको — सटीक हो।" | "झ्याल 1.02 मिटर छ।" *(भरोसा नभनी)* / "100% सही।" |
| 5 | Not accusing anyone | "The photo suggests the window is narrower than drawn. It may be a measurement difference — verify before drawing any conclusion." | "The contractor cheated." / "The mason built it wrong." | "फोटोमा झ्याल नक्साभन्दा साँघुरो जस्तो देखिन्छ। नापको तलमाथि पनि हुन सक्छ — निष्कर्ष निकाल्नुअघि जाँच्नुहोस्।" | "ठेकेदारले ठग्यो।" / "डकर्मीले गलत बनायो।" |
| 6 | When something matches | "As far as visible, this part matches the drawing." | "This is fully compliant." / "This part is safe." | "यो भाग देखिएसम्म नक्सासँग मिल्दो छ।" | "यो पूर्ण रूपमा नियमसम्मत छ।" / "यो भाग सुरक्षित छ।" |
| 7 | Scope and limits | "This check compares the drawing with the photos only. Structure, plumbing, electrical work and build quality are not checked." | *(no limits stated)* / "This is a complete inspection." | "यो जाँचले नक्सा र फोटो मात्र तुलना गर्छ — संरचना, प्लम्बिङ, विद्युत् र निर्माणको गुणस्तर जाँचिएको छैन।" | *(सीमा नलेख्ने)* / "यो पूरा निरीक्षण हो।" |
| 8 | Numbers and units | "about 1.0 m (photo estimate)" / "1.50 m (from the drawing — exact)" | bare "1.0 m" / false precision "0.9987 m" | "लगभग 1.0 मिटर (फोटोबाट अनुमान)" / "1.50 मिटर (नक्साबाट — सटीक)" | "1.0 मिटर" *(स्रोत नभनी)* / "0.9987 मिटर" |
| 9 | Stage of construction | "Site stage: walls (could not fully confirm)." | "Construction completed." *(when unsure)* | "साइटको अवस्था: भित्ता (पूर्ण यकिन भएन)।" | "निर्माण सम्पन्न भयो।" *(यकिन नभएको बेला)* |

---

## 3. Describing confidence to a non-technical reader

Never show a bare percentage or decimal. Use band word first, number in brackets, and one plain sentence explaining what it means:

| Band | Range (`Provenance.confidence` / `Delta.confidence`) | Chip text | Plain sentence to pair with it |
|---|---|---|---|
| उच्च (high) | 0.80 – 1.00 | `भरोसा: उच्च (87%)` | "यो मान स्रोतबाट सीधै आएको हो।" (This value came straight from the source.) |
| मध्यम (medium) | 0.50 – 0.79 | `भरोसा: मध्यम (62%)` | "यो अनुमान हो — तलमाथि हुन सक्छ, जाँच गर्नु राम्रो।" (This is an estimate — it may be off; a check is worthwhile.) |
| कम (low) | 0.01 – 0.49 | `भरोसा: कम (35%)` | "कम भरोसा — प्रत्यक्ष नाप वा स्पष्ट फोटो चाहिन्छ।" (Low confidence — needs a direct measurement or a clearer photo.) |
| थाहा भएन (unknown) | 0.0 with `source == "default"` | `भरोसा: थाहा भएन` | "यसको स्रोत खुलेको छैन — यसलाई प्रमाण नमान्नुहोस्।" (The source is not known — do not treat this as evidence.) |

And always name the source of the number in human words:

- **नक्साबाट — सटीक** (from the drawing — exact): `vector_geometry`, `raster_geometry` when it parses cleanly.
- **फोटोबाट — अनुमान** (from a photo — estimate): `ai_vision`.
- **तपाईंले दिनुभएको** (you supplied it): `user_supplied`.

The standard sentence for photo-derived numbers, use it verbatim: **"यो नाप फोटोबाट अनुमान गरिएको हो — लगभग मान्नुहोस्।"**

---

## 4. Phrasing a finding so it does not accuse a builder or contractor

Rules, in order of importance:

1. **The subject is the element, never a person.** "झ्याल नक्साभन्दा सानो जस्तो देखिन्छ" — not "whoever built the window made it small".
2. **Use appearance verbs** — देखिन्छ / जस्तो देखिन्छ / देखियो (appears / looks like / was seen). Never "छ" (is) for a photo-derived fact.
3. **Always leave room for innocent explanations** — measurement error, photo angle, work not yet finished: "नापको तलमाथि पनि हुन सक्छ" / "अझै नबनेको हुन सक्छ".
4. **Never name trades, companies or people** — no ठेकेदार, डकर्मी, कामदार in findings. (Only in the generic instruction "आफ्नो डिजाइनर वा पालिकामा लगेर जाँच्नुहोस्", where it is advice, not blame.)
5. **End on the next action**, not on the problem: "कृपया जाँच गर्नुहोस्" / "मेजर टेपले नाप्नुहोस्" / "डिजाइनरसँग कुरा गर्नुहोस्".
6. **"Verify before concluding" is the closing sentence** whenever a difference is described: "निष्कर्ष निकाल्नुअघि जाँच्नुहोस्।"

---

## 5. Sentence templates (ready to use)

Fill `{...}` from the schema; keep the sentence shape. These eight cover the common findings.

**T1 — Element differs in size** (`Delta.status = differs`, e.g. window, stair)
> **NE:** {element} नक्सामा {expected} छ, तर साइटको फोटोमा लगभग {observed} जस्तो देखिन्छ। फरक देखिन्छ — कृपया जाँच गर्नुहोस्। (भरोसा: {band})
> **EN:** The drawing shows {element} at {expected}; the site photo suggests about {observed}. This may differ from the approved drawing — please verify. (Confidence: {band})

**T2 — In the drawing, not seen in the photos** (`status = missing`)
> **NE:** {element} नक्सामा छ, तर अपलोड गरिएका फोटोमा भेटिएन। यो अझै नबनेको वा फोटोको कोणले नदेखिएको हुन सक्छ — कृपया साइटमा जाँच गर्नुहोस्।
> **EN:** {element} is in the drawing but was not found in the photos you uploaded. It may not be built yet, or it may simply not be visible — please verify on site.

**T3 — Seen on site, not in the drawing** (`status = unexpected`)
> **NE:** फोटोमा {element} देखियो, जुन नक्सामा देखिँदैन। यो नक्सामा नभएको भाग हो — इन्जिनियर वा पालिकासँग जाँच्नुहोस्।
> **EN:** The photo shows {element}, which does not appear in the drawing. Please check this with your engineer or municipality.

**T4 — Could not be determined** (`status = unverifiable`, or low confidence)
> **NE:** यो भाग फोटोबाट यकिन गर्न सकिएन (भरोसा: {band})। नजिकबाट स्पष्ट फोटो खिचेर फेरि जाँच गर्नुहोस्।
> **EN:** We could not determine this from the photos (confidence: {band}). Try a closer, clearer photo and run the check again.

**T5 — Photo-derived number, anytime it is shown**
> **NE:** यो नाप फोटोबाट अनुमान गरिएको हो — लगभग मान्नुहोस्। नक्साबाट आएका नाप सटीक हुन्छन्।
> **EN:** This measurement comes from a photo — treat it as approximate. Measurements taken from the drawing are exact.

**T6 — Matched element (reassurance, without overclaiming)**
> **NE:** यो भाग देखिएसम्म नक्सासँग मिल्दो छ — यहाँ थप जाँच आवश्यक देखिँदैन।
> **EN:** As far as visible, this part matches the drawing — no further check seems needed here.

**T7 — Photos cover only one stage**
> **NE:** हालसम्मका फोटो {stage} अवस्थाका हुन्। यसअघिका चरण (जस्तै जग) फोटोमा नभएकाले जाँचिएका छैनन्।
> **EN:** The photos so far show the {stage} stage. Earlier stages (for example the foundation) were not checked because no photos show them.

**T8 — Standing scope line** (also used when `DiffReport.limits` is empty; never omit)
> **NE:** यो रिपोर्टले नक्सा र फोटोबीचको फरक मात्र देखाउँछ। यो निर्णय वा प्रमाणपत्र होइन — जाँच्नुपर्ने बुँदाहरूको सूची हो।
> **EN:** This report only shows differences between the drawing and the photos. It is not a verdict or a certificate — it is a list of items to verify.

---

## 6. Banned-word list (lint these strings before merge)

Never appears in any user-visible string, any language:

- **English:** violation, violates, non-compliant, non-compliance, breach, illegal, wrong, incorrect, cheated, cheater, defect, failed (as in "failed inspection").
- **Nepali:** उल्लंघन, उल्लङ्घन, नियमविरुद्ध, अवैध, गलत, बेठिक, ठगी, ठग्यो, दोषी, त्रुटिपूर्ण (as a verdict word).

Notes:

- Severity labels (उच्च / मध्यम / कम / जानकारी) and status labels (मिल्यो / फरक देखिन्छ / भेटिएन / नक्सामा थिएन / यकिन गर्न सकिएन) are the only approved vocabulary for findings — see `ui-spec.md` §4.
- "जाँच" (check) is the product verb; "निरीक्षण" (inspection) is avoided — Karmi checks, people inspect.
- The word for the output collection is always **जाँच्नुपर्ने बुँदाहरू** ("items to verify"), never "समस्या" (problems) or "दोष" (faults).
- Numerals: Latin digits (0–9) for measurements, counts and dates, everywhere.