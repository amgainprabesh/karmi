# Karmi — Demo Video Script (v0)

> **Target runtime: 2:50** (hard cap: under 3:00). Frogtoberfest requires the video to show **problem, solution, workflow, value** — the coverage table below is the audit.
> Format: screen recording of the real product with minimal motion graphics. Voiceover in English; **one homeowner-facing beat in Nepali** (subtitled). Tone: calm, factual, no hype. Every number spoken or shown must come from the actual run — see the checklist at the end.

## Coverage check

| Requirement | Beats |
|---|---|
| Problem | B1 |
| Solution | B2 |
| Workflow | B3–B5 |
| Value | B6–B7 |

## Timeline at a glance

| Beat | Time | Length | Content |
|---|---|---|---|
| B1 | 0:00–0:18 | 0:18 | The problem: approved design vs built reality |
| B2 | 0:18–0:32 | 0:14 | What Karmi is |
| B3 | 0:32–1:00 | 0:28 | Workflow: approved drawing in → `scene.json` (AI beat) |
| B4 | 1:00–1:24 | 0:24 | Workflow: site photos in → `observed.json` + confidence (AI beat) |
| B5 | 1:24–2:02 | 0:38 | **Money shot**: 2D→3D approved house builds itself, as-built appears, differences highlighted |
| B6 | 2:02–2:26 | 0:24 | Honest limits + Nepali "items to verify" |
| B7 | 2:26–2:50 | 0:24 | Value + close |

---

## B1 — The problem (0:00–0:18)

**On screen:** Split screen. Left: the fixture naksa drawing, zoomed into the front wall with its window dimension. Right: a construction photo (foundation or columns stage). Slow push-in. Lower third: "Approved design → Built reality".

**Voiceover:** "In Nepal, you can't legally build without an approved naksa — drawings signed by a registered engineer, checked against the National Building Code, approved by the local body. Then construction drifts. A window comes out narrower than approved. A stair, tighter. Nobody re-measures — and the homeowner can't read the drawings they paid for. Karmi closes that gap."

**Notes:** No statistics unless a citable source exists in `docs/research/` (RESEARCH owns this). If any real photo is used, it must be consented and free of names, addresses and faces — prefer fixture/synthetic imagery.

## B2 — What Karmi is (0:18–0:32)

**On screen:** Title card — "Karmi (कर्मी): a compiler between approved design and built reality." Then the four-step pipeline animates in: approved set in → reality in → compile the difference → explain it (in Nepali). Reuse the diagram from `docs/architecture.md`.

**Voiceover:** "Karmi is a compiler between approved architectural design and built reality. Approved drawing in. Site photos in. It compiles the difference, element by element — and explains it in plain Nepali."

**Notes:** Keep this to one breath. The next three beats are the substance.

## B3 — Workflow: the approved set in (0:32–1:00)

**On screen:** The web UI. Drag `naksa_base.pdf` in, start the run. Cut to split screen: the drawing on the left, `scene.json` on the right — walls, openings, rooms, dimensions. Highlight one wall run and its matching JSON line. Optional 5-second insert: the `AI_USAGE.md` "consumed by" row for drawing → geometry next to the corresponding function (`core/model.py → build_scene_graph()`) in an editor.

**Voiceover:** "Step one: the approved set. Karmi reads the vector drawing and compiles a machine-readable model — walls, doors, windows, rooms — as structured JSON. That JSON is the actual artifact the renderer consumes. No chatbot, no screenshot-and-guess. Delete the model call, and the drawing never becomes a building. That is the AI, doing the work."

**Notes:** Show the real file path of the JSON on screen. The JSON shown must come from the recorded run — never hand-edit it for the camera. Zoom 120–150% so it is readable at 1080p.

## B4 — Workflow: reality in (1:00–1:24)

**On screen:** Upload 3–5 site photos. Then `observed.json`: stage classification ("walls"), elements with `approx_size`, and visible confidence values. Zoom on one confidence chip (e.g. 0.72). Briefly show the optional known-dimension input ("door height 2.1 m — supplied by the user").

**Voiceover:** "Step two: reality. Site photos are classified by construction stage, and visible elements are estimated against scale references — a brick course, a standard door — each with a confidence value. A photo alone can't give millimetres, so the user can supply one known dimension to anchor the scale. Where the evidence is thin, Karmi says so."

**Notes:** If the fallback as-built path is used (re-drawn as-built plan instead of photos), the on-screen label must say so — never dress the drawing path up as photo extraction.

## B5 — Money shot: the 2D→3D transition (1:24–2:02)

**On screen:** The viewer. Start flat on the 2D plan. Press play: walls rise, the approved house assembles in 3D (green). Hold for a beat. Then the as-built model appears overlaid (red/amber); the camera orbits; three differences highlight in sequence with labels — front window (approved 1.5 m → observed about 1.0 m), stair width (1.00 m → 0.85 m), plus one more taken from the actual run at record time. Brief inset: the raw delta JSON (`expected: "1.5 m", observed: "1.0 m", severity: "medium", confidence: 0.72`).

**Voiceover:** "And this is the part we built Karmi for. The approved house builds itself from the drawing." *(pause for the transition)* "Then the as-built model lands on top. Where they disagree — this front window, approved at one-point-five metres, observed at about one metre; this stair; this setback — the difference is highlighted, element by element, with severity and confidence."

**Notes:** One continuous take; rehearse the camera moves. Highlighted-element count must equal `differs + missing + unexpected` in `report.json`. Say "about one metre" — it is an estimate, never a millimetre claim.

## B6 — Honest limits + the Nepali beat (2:02–2:26)

**On screen:** The Nepali report page. Scroll the items-to-verify list (जाँच्नुपर्ने बुँदाहरू). Show confidence labels and the limits footer (raster is best-effort; photo dimensions are approximate; single floor only). Text card: "Never 'violation'. Always 'verify'."

**Voiceover (Nepali line first, then English):**

- Nepali: "यी सबै जाँच्नुपर्ने बुँदाहरू हुन्। कृपया आफ्नो इन्जिनियर वा नगरपालिकासँग पुष्टि गर्नुहोस्।"
- English: "Karmi never says 'violation'. Every uncertain item carries a confidence value and lands in a verify list — in plain Nepali — for the homeowner to check with their engineer or municipality. That honesty is the feature."

**Notes:** Have a fluent speaker deliver the Nepali line slowly; burn in English subtitles for it. Show the actual limits section from the report — not a mock.

## B7 — Value + close (2:26–2:50)

**On screen:** Three-column card — Homeowner: "clear items to check, in Nepali"; Engineer: "a practical completion check"; Municipality: "conformance evidence without re-measuring". Then the end card: repo URL, "MIT · open-weight AI end to end · runs locally", Team Amgain (Prabesh Amgain, Prabhat Amgain), Frogtoberfest 2026.

**Voiceover:** "For the homeowner: clarity instead of drawings they can't read. For the engineer and the municipality: a completion check that is practical, honest and repeatable. Karmi is open source — the conformance engine, the renderer, and the open dataset of Nepali naksa drawings we're building with the community. Approved in. Reality in. Difference out."

**Notes:** Only claim the dataset if a seed release exists by recording day; otherwise say "we're building". End card must stay readable for at least 4 seconds.

---

## Pre-recording checklist

Everything below must be true **on screen** before recording starts.

**Truth and reproducibility**

- [ ] Every screen is a real run of the actual code, recorded in this session — no mockups, no hand-edited JSON shown as output.
- [ ] The run is reproducible from the public repo using only the fixtures and documented commands.
- [ ] `run.json` from the recorded run is kept; if the video claims "runs locally", the recording was made with networking off and the provider field shown.
- [ ] Every number spoken or shown matches `report.json` exactly (window, stair, severity, confidence).
- [ ] The highlighted-element count in the viewer equals `differs + missing + unexpected` in `report.json`.

**Demo data story**

- [ ] Data story locked by Oct 22: (a) photo-based as-built, or (b) drift-drawing stand-in; if (b), the video and its description say so plainly.
- [ ] Synthetic data is labelled on screen ("synthetic sample drawing — no real household data") during B1/B3/B4.
- [ ] No real names, addresses, signatures, faces or licence plates anywhere in frame.

**Money shot quality**

- [ ] Transition rehearsed: approved = green, as-built = red/amber; at least 3 differences visible and legible at 1080p.
- [ ] 2D → 3D → overlay plays as one continuous take; captured at 60 fps if possible.
- [ ] Nepali text renders correctly (font installed) in the report and viewer — no missing-glyph boxes.

**AI-is-load-bearing beat**

- [ ] `scene.json` and `observed.json` shown are the actual artifacts from the recorded run, with their file paths visible.
- [ ] The `AI_USAGE.md` "consumed by" row matches the function shown in the editor.

**Honest-limits beat**

- [ ] Confidence values and the verify list are visible; the limits footer (raster / photo dimensions / single floor) is shown.
- [ ] The words "violation"/"violates" appear nowhere on screen.

**Production**

- [ ] Runtime at or under 2:59; export at 1080p minimum; audio levelled; English subtitles burned in (at least for the Nepali line).
- [ ] Desktop clean: notifications off, no tokens or keys on screen, terminal history and bookmarks hidden, no personal filenames.
- [ ] End card (repo URL, licence, team) readable for at least 4 seconds.
- [ ] Raw footage of the full run kept in case a re-edit is needed.
- [ ] A second person (not the editor) watches the final cut against this checklist before upload.