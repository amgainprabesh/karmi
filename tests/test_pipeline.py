"""End-to-end pipeline test.

``run_pipeline`` is designed never to raise: every stage degrades to a warning
and a valid (if empty) artifact. This file must pass even while core.model,
core.observe, core.diff, core.report and render.adapter are missing or broken,
so it asserts only the pipeline's own guarantees: the run manifest is written,
parses, and carries a ``result`` key.
"""

from __future__ import annotations

import json

from conftest import no_network
from core.pipeline import PipelineResult, run_from_manifest, run_pipeline


def test_run_pipeline_writes_a_parseable_run_manifest(naksa_base, tmp_run_dir):
    result = run_pipeline(naksa_base, [], out_dir=tmp_run_dir)

    assert isinstance(result, PipelineResult)
    assert result.files.get("run") == "run.json"

    run_json = tmp_run_dir / "run.json"
    assert run_json.is_file(), "run_pipeline did not write run.json"

    data = json.loads(run_json.read_text(encoding="utf-8"))
    assert "result" in data, f"run.json is missing the 'result' key: {sorted(data)}"
    assert isinstance(data["result"], dict)
    assert isinstance(data["result"].get("files"), dict)
    assert isinstance(data["result"].get("errors"), list)
    assert data.get("drawing", "").replace("\\", "/").endswith("naksa_base.pdf")


def test_run_from_manifest_roundtrips(naksa_base, tmp_run_dir):
    first = run_pipeline(naksa_base, [], out_dir=tmp_run_dir)
    manifest = tmp_run_dir / first.files["run"]

    second = run_from_manifest(manifest, out_dir=tmp_run_dir / "rerun")

    assert isinstance(second, PipelineResult)
    assert (tmp_run_dir / "rerun" / "run.json").is_file()


def test_default_pipeline_touches_no_network(naksa_base, tmp_run_dir, monkeypatch):
    with no_network(monkeypatch) as sentinel:
        result = run_pipeline(naksa_base, [], out_dir=tmp_run_dir)

    assert result.files.get("run") == "run.json"
    blob = json.dumps(result.to_dict(), ensure_ascii=False)
    assert sentinel not in blob, (
        "a pipeline stage attempted network access on the default (ai=None) path: "
        f"errors={result.errors} warnings={result.warnings}"
    )