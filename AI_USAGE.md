# AI Usage Disclosure

Required by Frogtoberfest 2026: *"a short written statement naming the exact file/function where
AI output is consumed programmatically."*

This file is kept honest and current. Sections marked **planned** are not implemented yet; when a
model lands in the codebase, its row moves to **implemented** with the file/function it feeds.

## Rule we hold ourselves to

Every AI call in Karmi is **open-weight**, start to finish — vision, text and embeddings. No
OpenAI, Anthropic/Claude, Google Gemini, Azure OpenAI or any other closed paid model API is used,
not even for auxiliary classification or embeddings. Default execution is local
(Ollama / llama.cpp / vLLM); a hosted provider serving open weights is an optional, configurable
fallback, never a dependency of the core pipeline.

## Implemented

| Component | Model | Where the output is consumed |
|---|---|---|
| — | — | Nothing yet. `proto/plan-to-3d.html` is a hand-authored plan and contains **no AI calls**; it consumes a semantic model written by hand. |

## Planned

| Stage | Model family (open-weight) | Output (structured) | Consumed by (file → function) |
|---|---|---|---|
| Drawing → geometry | Qwen2.5-VL / segmentation model fine-tuned on Nepali naksa drawings | `{walls[], openings[{kind,width}], rooms[{name,polygon}], scale, orientation}` | `core/model.py` → `build_scene_graph()` |
| Photo → observed state | Qwen2.5-VL (open weights) | `{stage, elements[{kind,approx_size,confidence}], scale_refs[]}` | `core/observe.py` → `to_observed_state()` |
| Comparison | open-weight LLM + deterministic geometry code | `{deltas[{element,expected,observed,severity,confidence}], verify_list[]}` | `core/diff.py` → `render_report()` |
| Report narration (Nepali) | open-weight LLM, Nepali tokens | plain-Nepali explanation text per delta | `core/diff.py` → `narrate()` |
| Embeddings (retrieval over drawing notes) | open embedding model (e.g. bge-m3) | vectors | `core/retrieval.py` → `index_drawings()` |

## How the AI is used, in their words

Their qualifying patterns, mapped to Karmi:

* **Structured extraction** — a drawing and a photograph both become structured JSON consumed by
  code, not text shown to a user.
* **Multi-step pipeline** — extraction A and extraction B feed a comparison step, whose output
  feeds the report renderer.
* **Decision / routing** — the comparison decides severity and what enters the "verify" list;
  low-confidence observations are routed to *human check* instead of being asserted.
* **Data transformation at scale** — the dataset build processes many drawing/photo pairs into a
  published, versioned dataset.

## What is deliberately *not* AI

Geometry, projection, camera motion, dimension arithmetic, severity thresholds and the renderer are
ordinary deterministic code. The AI supplies the semantic model; the code does the rest.
