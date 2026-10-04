"""Karmi dataset — tooling for the project's open-source data contribution.

This package is the *public-good* half of Karmi: everything needed to build,
de-identify, annotate and release an open dataset of Nepali naksa (building
permit) drawings paired with construction photos — the first of its kind, as
far as the project's survey of prior art could tell (see
``docs/research/dataset-plan.md`` §9).

The dataset does **not** contain any real records yet. The only records that
exist in this repository are clearly-labelled **synthetic** examples generated
from the repo's own fixtures (``dataset/example/``). Nothing here collects data.

Modules
-------
``dataset.schema``
    The annotation record contract: pydantic models reusing the frozen types in
    ``core/schema.py`` (``SceneGraph``, ``ObservedState``, ``Provenance``). A
    record cannot exist without a consent block and a licence.
``dataset.consent``
    The consent model (who / what / when / how, per signatory), the licence
    vocabulary, and withdrawal → redaction-instruction mechanics. Legal
    reasoning (Privacy Act 2075; Copyright Act 2059) lives in its docstring.
``dataset.deidentify``
    Real, runnable de-identification: EXIF/GPS stripping (pixels verified
    unchanged), drawing-text PII detection and redaction (PDF → redacted text
    copy + redacted PDF copy), and ``scan_record()`` over every free-text field.
``dataset.export``
    ``to_jsonl()``, ``to_hf_dataset()`` (Hugging Face ``datasets``-loadable
    folder + dataset card) and ``split()`` — a documented, reproducible
    record-level split that never separates a drawing from its photos.
``dataset.example``
    Builder for the synthetic example records (run:
    ``python -m dataset.export --example``).

CLI
---
::

    python -m dataset deidentify fixtures/photos/front_walls_stage.jpg
    python -m dataset export --example
    python -m dataset consent --withdraw karmi-example-0001
    python -m dataset build-examples

(or equivalently ``python -m dataset.deidentify``, ``python -m dataset.export``,
``python -m dataset.consent`` directly).
"""

__version__ = "0.1.0"

__all__ = ["__version__"]