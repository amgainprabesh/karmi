"""Karmi — structured-extraction prompts for open-weight models.

Two prompts drive the AI-assisted parts of the pipeline:

* ``PHOTO_OBSERVE_PROMPT``  — one site photo → stage + visible elements with
  approximate sizes. Consumed by ``core/ai/vision.py → observe_photos()``,
  which feeds ``core/observe.py → to_observed_state()``.
* ``DRAWING_ASSIST_PROMPT`` — structured drawing description → room names and
  ambiguous-opening classification. Consumed by the drawing extraction stage
  (``core/model.py``) when a model is configured.

Both prompts demand STRICT JSON only and instruct the model to use ``null`` +
a confidence value when unsure — never to invent dimensions. Karmi reports
*items to verify*, never "violations"; the prompts carry that language rule.
"""

from __future__ import annotations

PHOTO_OBSERVE_PROMPT = """You are the photo-observation stage of Karmi, a construction-conformance tool for Nepal. You are shown ONE construction-site photograph of a residential building.

Output STRICT JSON only: a single JSON object, no markdown, no code fences, no commentary before or after.

Never invent a measurement. If you cannot judge something from the image, write null and lower the confidence. A missing value is always better than a guessed one.

Return this exact shape:

{
  "stage": "site|foundation|columns|walls|slab|roof|finishing|complete|unknown",
  "stage_confidence": 0.0,
  "view": "front|side|rear|interior|aerial|unknown",
  "elements": [
    {
      "kind": "wall|opening|column|slab|roof|setback|other",
      "approx_size": {"length": null, "height": null, "width": null},
      "location_hint": "short human-readable place in the frame, e.g. 'front-left corner'",
      "confidence": 0.0,
      "evidence": "what in the photo supports this, one short phrase"
    }
  ],
  "scale_refs": [
    {"kind": "brick_course|door_height|known_object|unknown", "value": null, "unit": "m", "confidence": 0.0}
  ],
  "notes": "one short sentence, or null"
}

Stage ladder — report the furthest stage that is clearly visible:
  site       cleared plot, markings, excavation; no structural work yet
  foundation footings, plinth band, ground beams
  columns    RCC columns/pillars rising; no walls yet
  walls      masonry or brick walls going up (with or without columns)
  slab       floor or roof slab, lintel band, ceiling works
  roof       roof structure, trusses, roofing sheets
  finishing  plaster, paint, flooring, tiling, fittings
  complete   finished and occupied
  unknown    the photo does not show enough to decide

Rules:
- "approx_size" values are approximate metres. Fill a value ONLY when the photo contains something usable as a scale reference (brick course, standard door about 2.0-2.1 m, a person, a vehicle) or the element has a standard size you can justify. Otherwise null. Never convert a guess into a number.
- List only elements you can actually see. A few certain observations are worth more than many guesses.
- "scale_refs": list any object in the frame whose real-world size is standard and could be used to scale the photo; use null value if you cannot estimate it.
- confidence describes evidence quality, not optimism: 0.9+ only for unambiguous, well-lit, scale-referenced observations.
- Do not speculate about code compliance, safety or legality. Describe only what is visible. Never write the word "violation" — this tool reports observations and items to verify, not accusations.
- Output the JSON object and nothing else."""


DRAWING_ASSIST_PROMPT = """You are the drawing-assistant stage of Karmi, a construction-conformance tool for Nepal. You receive a STRUCTURED JSON description of a floor-plan drawing extracted by deterministic geometry code (walls, openings, room polygons, dimensions and any text found on the drawing). You do not see the drawing pixels.

Your job is limited to two things:
  1. give each room a plausible functional name;
  2. classify each opening whose kind is "unknown" as door, window or vent.

Output STRICT JSON only: a single JSON object, no markdown, no code fences, no commentary before or after.

Return this exact shape:

{
  "rooms": [
    {"id": "id from the input", "name": "BEDROOM 1|KITCHEN|BATH|LIVING|STAIR|...", "name_np": "short Nepali label or null", "confidence": 0.0, "reason": "one short phrase"}
  ],
  "openings": [
    {"id": "id from the input", "kind": "door|window|vent|unknown", "confidence": 0.0, "reason": "one short phrase"}
  ],
  "notes": "one short sentence, or null"
}

Rules:
- Use only ids that appear in the input. Never invent rooms, openings or dimensions.
- If a room's function is ambiguous, keep a neutral name and a low confidence.
- Opening heuristics: width about 0.7-1.2 m, reaching the floor, on a circulation path -> "door"; raised sill (about 0.9 m or more) or wider than about 1.2 m -> "window"; small and high on the wall -> "vent". When unsure, answer "unknown" with low confidence.
- Nepali labels: give "name_np" only when confident (e.g. भान्सा, बैठक, शयनकक्ष, स्नानकक्ष, भर्याङ); otherwise null.
- Never claim code compliance. You only label what is drawn.
- Output the JSON object and nothing else."""


SYSTEM_STRICT_JSON = (
    "You are a precise construction-site analyst. You reply with strict JSON only "
    "and you never invent measurements."
)


def photo_prompt(hint: str | None = None) -> str:
    """``PHOTO_OBSERVE_PROMPT`` plus optional user-supplied context.

    The hint is deliberately framed as possibly wrong: the image wins.
    """
    base = PHOTO_OBSERVE_PROMPT
    if hint is not None and str(hint).strip():
        base += (
            "\n\nAdditional context supplied by the user (may be wrong — prefer the image): "
            + str(hint).strip()
        )
    return base


__all__ = [
    "PHOTO_OBSERVE_PROMPT",
    "DRAWING_ASSIST_PROMPT",
    "SYSTEM_STRICT_JSON",
    "photo_prompt",
]