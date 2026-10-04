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

The AI is an **injected, optional provider** (`core/ai/`). Every call site below exists in
code today, is exercised by the test suite, and has a **deterministic fallback** that runs
when no provider is configured — so the pipeline always produces a real result.

| Stage | Model family (open-weight) | Output (structured) | Consumed by (file → function) | State |
|---|---|---|---|---|
| Drawing → geometry | *none needed for vector PDFs* | `SceneGraph` — walls, openings, rooms, dimensions | `core/model.py` → `build_scene_graph()` | **working**, deterministic (`vector_geometry` provenance) |
| Photo → observed state | Qwen2.5-VL / Qwen3-VL (open weights) via `OllamaProvider` or any open-weight OpenAI-compatible endpoint | `ObservedState` — stage, elements, approx sizes, confidence | `core/observe.py` → `to_observed_state()` ← `core/ai/vision.py` → `observe_photos()` | **implemented, mock-tested**; not yet run against a live model |
| Comparison | open-weight LLM (optional rewrite only) | severity + verify list | `core/diff.py` → `diff_scene()` | **working**, fully deterministic; the AI can only *rewrite* narration, never compute |
| Report narration (Nepali) | open-weight LLM, Nepali tokens | plain-Nepali explanation text per delta | `core/diff.py` → `narrate()` | **implemented**; any AI rewrite is **number-validated** against the computed values and rejected if it invents a figure |

**Honest status:** the provider layer (`NullProvider` default, `OllamaProvider`,
`OpenAICompatProvider`) and both extraction paths are written and tested with a mock
provider. A live open-weight model has **not** been run against a real photo in this
repository yet — until it is, `fixtures/photos/*.jpg.json` sidecars carry hand-measured
values, and that path is what the demo uses. A model name outside the open-weight
allowlist is refused in code (`assert_open_weight`).

## Planned

| Stage | Model family (open-weight) | Output (structured) | Consumed by (file → function) |
|---|---|---|---|
| Raster / scan drawings → geometry | segmentation model fine-tuned on Nepali naksa drawings | masks → polygons → `SceneGraph` | `core/model.py` (raster path returns warnings today) |
| Embeddings (retrieval over drawing notes) | open embedding model (e.g. bge-m3) | vectors | `core/retrieval.py` → `index_drawings()` — **must redact PII before embedding** (`core/validate.py`) |

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
