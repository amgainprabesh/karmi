# Competition fit — Karmi vs Frogtoberfest 2026 judging

> Honest self-assessment against the published rules. Sources read in full on 2026-10-04:
> - Frogtoberfest homepage — https://frogtoberfest.lftechnology.com/
> - Frogtoberfest Guidelines — https://frogtoberfest.lftechnology.com/guidelines
> Where the repo's actual state falls short, this document says so.

## 0. What the event actually asks for

- One month to build an **open-source, AI-powered product**; Demo Day **October 30, 2026** in Kathmandu Valley; top 5 teams present live; grand prize = "Best AI Project" — "the project that stands out for **innovation, technical excellence, open-source contribution, and real-world impact**."[H]
- The AI bar: *"AI does real work inside the solution: processing, transforming, or reasoning over data as part of the system's core logic—not just generating a response that gets shown to a user."* The baseline check: *"if you deleted the AI call from your codebase, would the product still do its job? If yes, it doesn't qualify."*[G]
- **Open-weight only, end to end:** *"only open-source or open-weight AI qualifies (e.g. Llama, Mistral, Qwen, DeepSeek, self-hosted or via a hosted provider)… Proprietary APIs like OpenAI, Claude, or Gemini are discouraged, even for small auxiliary calls."*[H][G]
- Minimum submission requirements: public GitHub repo · documentation (README, architecture, tech, limitations) · working demo · demo video/presentation · qualifies as "Build with AI" · **AI Usage Disclosure** "naming the exact file/function where AI output is consumed programmatically".[G]

## 1. Eligibility checklist (honest status)

| Requirement[G] | Karmi status (2026-10-04) | Action |
|---|---|---|
| Public GitHub repo | Remote exists (`github.com/amgainprabesh/karmi`); public visibility to verify before submission | confirm public + LICENSE present |
| Documentation | `README.md`, `docs/architecture.md`, `AI_USAGE.md`, and this `docs/research/` set exist | add a "limitations / future work" section explicitly (partly in README) |
| Working demo | **Weakest link today.** README: "what works today is the 2D→3D transition engine"; `AI_USAGE.md` says "Nothing yet" under *Implemented* | must ship one end-to-end path before Demo Day |
| Demo video | Not yet | record after the end-to-end path works |
| Qualifies as "Build with AI" | Architecture is mapped to their qualifying patterns (§2) but **the AI calls are not implemented yet** — the current prototype contains no AI | implement extraction A or B (even a small, real one) and show it being consumed |
| AI Usage Disclosure | `AI_USAGE.md` exists and matches their required format (file/function where output is consumed) | keep it current; move rows from *Planned* to *Implemented* as they land |

## 2. (a) "AI does real work inside the solution"

Mapping Karmi's design onto the guidelines' own list of qualifying patterns (the guidelines call these out explicitly):[G]

| Guidelines pattern | Karmi stage | Where AI output is consumed programmatically |
|---|---|---|
| Structured extraction | Drawing → geometry; photos → observed state | `core/model.py` → `build_scene_graph()`; `core/observe.py` → `to_observed_state()` — output is JSON (`SceneGraph` / `ObservedState`), not prose |
| Multi-step pipeline | Extraction A + B → diff → report | `core/diff.py` consumes both models; `core/report` consumes the diff |
| Decision / routing | Comparison engine sets severity; low-confidence observations route to the human verify-list | `Delta.severity`, `VerifyItem` construction in `core/diff.py` |
| Data transformation at scale | The dataset build (drawing/photo pairs → published dataset) | dataset pipeline (§ `dataset-plan.md`) |

**The deletion test:** remove the AI calls and Karmi has no scene graph and no observed state — the diff has nothing to compare. The renderer is deliberately dumb (it consumes a semantic model and infers nothing), so the AI is load-bearing by construction. That is the right shape for this competition.

**Honest caveat:** the guidelines demand the AI work be *visible* and *implemented*. Today the repo has architecture and a hand-authored 2D→3D prototype. The single most important job before Demo Day is to make **one real AI call feed one real downstream artifact** (e.g. a real VLM extracting openings from a real naksa page, with the JSON then driving the diff), and to record that in `AI_USAGE.md`.

## 3. (b) What is genuinely open-source contribution

| Contribution | Genuinely new? | Notes |
|---|---|---|
| **Annotated Nepali naksa dataset (drawings + construction photos + comparison labels)** | Yes — no such dataset was found in this research pass | The claim must be re-verified at release; consent/licensing per `dataset-plan.md`; start with a small real v0.1, not a promise |
| **Conformance / diff engine** (element-wise expected-vs-observed, severity, verify-list) | Yes as a concept in this domain | Deterministic geometry + open-weight reasoning; MIT code |
| **2D→3D transition renderer** (approved vs as-built dual view) | Yes as presented (dumb renderer consuming a semantic model) | Prototype exists; must be driven by real extracted models by Demo Day |
| Open-weight-only pipeline + disclosure | Not novel per se, but exactly what this event rewards | Must stay true end-to-end, including embeddings/aux calls |

What is *not* a contribution: the base models (Qwen/Llama etc.), PyMuPDF, the general idea of floor-plan vectorisation (CubiCasa5K et al. exist). The honest pitch is **domain data + the comparison layer**, not model novelty.

## 4. (c) The weakest part — and how to strengthen it

**Weakest part: the gap between the story and the shipped artifact.** The repo currently demonstrates a hand-authored 2D→3D transition; every AI row in `AI_USAGE.md` is "planned". Judges run an eligibility gate and a quick screen; a project whose core claim is unimplemented is the classic way to lose. Secondary weaknesses:

1. **Photo-based absolute dimensions are scientifically shaky** (the README admits it). If the demo leans on them without confidence framing, it invites the one question that kills the entry: "how do you know it's 3 feet?"
2. **Raster accuracy on Nepali conventions** is unsolved until the dataset exists — and the dataset won't exist at scale in four weeks.
3. **Risk of being perceived as a chatbot/report generator** if the demo shows text output instead of consumed JSON.
4. **Dataset claim ("first")** is a promise, not yet a fact.

**How to strengthen (priority order):**

1. **Ship one narrow end-to-end path with real data:** one real (consented, redacted) vector-PDF naksa → scene graph → 3–5 real site photos → observed state → diff → Nepali verify-list. Narrow beats broad here.
2. **Make the verify-list the hero.** Karmi's safety positioning ("items to verify", never "violations") is genuinely different from every "AI inspector" pitch; say it loudly.
3. **Show the plumbing.** A 5-second shot of the JSON entering `core/diff.py` answers the competition's core test more convincingly than any narration.
4. **Ship a tiny real dataset** (even 5–10 consented projects, redacted) rather than promising a big one; link it from the README.
5. **Quantify limits in the README** (dimension error ranges, confidence labels, failure modes) — the guidelines explicitly value documented limitations, and it protects against judge probing.
6. Keep `AI_USAGE.md` truthful and current; it is already shaped exactly like the requirement.

## 5. (d) The demo video — what it must show

**What the guidelines require:** "a short demo showing the **problem, solution, workflow, and value**" and evidence that "AI output is processed, consumed, or acted on by another part of the system".[G] No duration is specified on the pages read on 2026-10-04 (the "3-minute" target is our own constraint for Demo Day pacing; the FAQ separately requires a "working demo", and the final presentation is live on Oct 30).[H]

**3-minute storyboard (suggested):**

| Time | Beat | Must show |
|---|---|---|
| 0:00–0:25 | **Problem** | A real approved naksa on screen, then a photo of a window/stair that drifted; the line "nobody re-measures; the completion certificate has no practical check" |
| 0:25–1:10 | **Workflow 1 — drawing in** | Upload the vector PDF → extraction runs → walls/openings/rooms appear overlaid on the sheet; cut to the JSON being written and immediately read by `core/diff.py` (the "consumed programmatically" proof) |
| 1:10–1:55 | **Workflow 2 — reality in** | Site photos → stage classification + detected elements with **confidence values**; show a low-confidence item being routed to the verify list instead of asserted |
| 1:55–2:35 | **The compile** | Element-wise diff: matched / differs / missing, severity; the **Nepali report**; the 2D→3D transition (approved green → as-built red, differences highlighted) |
| 2:35–3:00 | **Value + honesty** | "Items to verify with your architect or municipality"; open dataset + open weights; repo URL; one sentence on limits |

Do **not** end on a chat window or a wall of text — end on the transition render and the verify list. Record it only after the end-to-end path runs for real; a fake-data demo is both a rules risk and a credibility risk.

## 6. Deadlines & logistics to keep in view

- Registration window was September 16–29; the build is one month; **Demo Day October 30, 2026**, in person — "at least one (1) member from the team should be physically present in Kathmandu valley".[H]
- Top 5 shortlisted teams present live; "Best AI Project" takes the grand prize.[H]

## Sources

- [H] Frogtoberfest homepage — https://frogtoberfest.lftechnology.com/
- [G] Frogtoberfest Guidelines — https://frogtoberfest.lftechnology.com/guidelines