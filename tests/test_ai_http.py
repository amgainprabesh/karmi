"""``core.ai`` — the open-weight provider path proven over real HTTP.

Everything here talks to a LOCAL ``http.server`` bound to 127.0.0.1 (started by
a fixture in this file) — a loopback socket, not the network. The provider
layer had only ever been mock-tested in-process; this file exercises the real
httpx request/response path, the real defensive JSON parsing, and the real
honesty clamps:

* an OpenAI-compatible ``/v1/chat/completions`` response is parsed into
  observed elements; merged provenance is ``ai_vision`` and confidence is
  clamped at ``AI_CONFIDENCE_CAP`` (<= 0.7) even when the model claims 0.99;
* the Ollama ``/api/chat`` shape (images as base64 in the message) works too;
* closed models (``gpt-4o``) are refused before any request is built;
* markdown-fenced + trailing-prose output is still parsed, and truncated JSON
  raises a clear ``AIExtractionError`` — never silent garbage;
* with no configuration the default is ``NullProvider`` and ``available()``
  is False.
"""

from __future__ import annotations

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from core import schema as S
from conftest import require, require_attr

pytest.importorskip("httpx", reason="httpx is required by the AI provider layer")

ai = require(
    "core.ai",
    reason="core.ai is not importable yet (being written in parallel) — skipping the provider tests",
)
vision_mod = require(
    "core.ai.vision",
    reason="core.ai.vision is not importable yet — skipping the provider tests",
)
observe_mod = require(
    "core.observe",
    reason="core.observe is not importable yet — skipping the provider tests",
)

_MODEL = "qwen2.5-vl-7b-instruct"

#: A valid structured-extraction payload, as an open-weight VLM would emit it.
_GOOD_OBSERVATION = {
    "stage": "walls",
    "stage_confidence": 0.9,
    "view": "front",
    "elements": [
        {
            "kind": "wall",
            "approx_size": {"length": 6.2, "height": 2.7},
            "location_hint": "front facade",
            "confidence": 0.99,  # above the cap — the merge must clamp it
            "evidence": "brick courses visible",
        },
        {
            "kind": "window",
            "approx_size": {"width": 1.5},
            "location_hint": "window on the north wall",
            "confidence": 0.4,
        },
    ],
    "scale_refs": [{"kind": "door_height", "value": 2.05, "unit": "m", "confidence": 0.8}],
    "notes": "test observation",
}

#: Markdown fences + trailing prose — the parser must still find the JSON block.
_FENCED = (
    "Here is my analysis of the photo:\n"
    "```json\n" + json.dumps(_GOOD_OBSERVATION) + "\n```\n"
    "Hope this helps!"
)

#: Truncated mid-object — nothing parseable, so the caller must raise clearly.
_TRUNCATED = '{"stage": "walls", "elements": [{"kind": "wall", "approx_size": {"length": 6.0'


class _AIHandler(BaseHTTPRequestHandler):
    """Canned OpenAI-compatible + Ollama responses; records every request."""

    protocol_version = "HTTP/1.1"
    server_version = "KarmiTestAI/0.1"

    def log_message(self, *args):  # noqa: D102 — silence stdlib stderr chatter
        pass

    # -- helpers ----------------------------------------------------------- #
    def _read_json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    def _send_json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _completion(self, content: str):
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": _MODEL,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content},
                 "finish_reason": "stop"}
            ],
        }

    # -- routes ------------------------------------------------------------ #
    def do_GET(self):
        self.server.requests.append({"method": "GET", "path": self.path})  # type: ignore[attr-defined]
        if self.path.endswith("/models") or self.path == "/api/tags":
            self._send_json(200, {"data": [{"id": _MODEL}]})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        body = self._read_json_body()
        self.server.requests.append({"method": "POST", "path": self.path, "body": body})  # type: ignore[attr-defined]
        if self.path == "/v1/chat/completions":
            self._send_json(200, self._completion(json.dumps(_GOOD_OBSERVATION)))
        elif self.path == "/malformed/v1/chat/completions":
            self._send_json(200, self._completion(_FENCED))
        elif self.path == "/truncated/v1/chat/completions":
            self._send_json(200, self._completion(_TRUNCATED))
        elif self.path == "/api/chat":
            self._send_json(
                200,
                {
                    "model": "qwen2.5-vl:7b",
                    "message": {"role": "assistant", "content": json.dumps(_GOOD_OBSERVATION)},
                    "done": True,
                },
            )
        else:
            self._send_json(404, {"error": "not found"})


@pytest.fixture(scope="module")
def ai_server():
    """(base_url, request_log) for a loopback HTTP server serving canned AI responses."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AIHandler)
    server.requests = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, name="karmi-test-ai", daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://127.0.0.1:{port}", server.requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def _make_photo(tmp_path: Path, fixtures_dir: Path) -> Path:
    """A real JPEG under tmp_path (and no sidecar), so merged elements are the AI ones."""
    dest = tmp_path / "front_walls_stage.jpg"
    source = fixtures_dir / "photos" / "front_walls_stage.jpg"
    if source.is_file():
        shutil.copyfile(source, dest)
        return dest
    PIL_Image = pytest.importorskip("PIL.Image", reason="no photo fixture and Pillow is missing")
    PIL_Image.new("RGB", (16, 16), (128, 128, 128)).save(dest, "JPEG")
    return dest


# --------------------------------------------------------------------------- #
# the OpenAI-compatible path, over real HTTP
# --------------------------------------------------------------------------- #
def test_openai_compat_round_trips_a_structured_observation(ai_server, tmp_path, fixtures_dir):
    base, requests_log = ai_server
    provider_cls = require_attr(ai, "OpenAICompatProvider")
    observe_photos = require_attr(vision_mod, "observe_photos")
    to_observed_state = require_attr(observe_mod, "to_observed_state")
    cap = require_attr(observe_mod, "AI_CONFIDENCE_CAP")
    assert cap <= 0.7, f"the AI confidence cap moved above 0.7: {cap!r}"

    provider = provider_cls(_MODEL, base_url=base)
    assert provider.available() is True, "the local server is up but available() says otherwise"
    photo = _make_photo(tmp_path, fixtures_dir)

    data = observe_photos([photo], provider=provider)
    assert data["provider"] == "openai_compat"
    assert data["model"] == _MODEL
    assert len(data["elements"]) == 2, f"parsed elements: {data['elements']}"
    wall = next(e for e in data["elements"] if e["kind"] == "wall")
    assert wall["approx_size"]["length"] == pytest.approx(6.2)
    assert wall["approx_size"]["height"] == pytest.approx(2.7)
    assert wall["location_hint"] == "front facade"
    assert len(data["scale_refs"]) == 1

    # the request really travelled over HTTP, with the image attached
    posts = [
        r for r in requests_log
        if r["method"] == "POST" and r["path"] == "/v1/chat/completions"
    ]
    assert posts, "no /v1/chat/completions request reached the local server"
    body = posts[-1]["body"]
    assert body.get("model") == _MODEL
    user = body.get("messages", [{}])[-1]
    parts = user.get("content") if isinstance(user.get("content"), list) else []
    part_types = {p.get("type") for p in parts if isinstance(p, dict)}
    assert {"text", "image_url"} <= part_types, (
        f"the vision request did not carry the image as a data URL: {part_types}"
    )

    # merging into the observed state: provenance ai_vision, confidence clamped
    state = to_observed_state([str(photo)], ai=provider)
    assert state.elements, "the merged observed state lost the AI elements"
    assert {e.provenance.source for e in state.elements} == {"ai_vision"}, (
        f"AI elements must carry ai_vision provenance: "
        f"{[(e.id, e.provenance.source) for e in state.elements]}"
    )
    assert all(e.provenance.confidence <= cap for e in state.elements), (
        f"AI confidences must be clamped at <= {cap}: "
        f"{[(e.id, e.provenance.confidence) for e in state.elements]}"
    )
    assert max(e.provenance.confidence for e in state.elements) == pytest.approx(cap), (
        "the model claimed 0.99 confidence — the merge must clamp it to the cap"
    )
    assert state.stage == S.Stage.WALLS
    ai_refs = [r for r in state.scale_refs if r.provenance.source == "ai_vision"]
    assert ai_refs and any(
        r.kind == "door_height" and r.value == pytest.approx(2.05) for r in ai_refs
    ), f"the AI scale reference did not survive the merge: {state.scale_refs}"


def test_ollama_chat_shape_round_trips(ai_server, tmp_path, fixtures_dir):
    base, requests_log = ai_server
    provider_cls = require_attr(ai, "OllamaProvider")
    observe_photos = require_attr(vision_mod, "observe_photos")

    provider = provider_cls("qwen2.5-vl:7b", base_url=base)
    assert provider.available() is True
    photo = _make_photo(tmp_path, fixtures_dir)

    data = observe_photos([photo], provider=provider)
    assert data["provider"] == "ollama"
    assert len(data["elements"]) == 2

    posts = [r for r in requests_log if r["method"] == "POST" and r["path"] == "/api/chat"]
    assert posts, "no /api/chat request reached the local server"
    user = posts[-1]["body"].get("messages", [{}])[-1]
    images = user.get("images") or []
    assert images and all(isinstance(img, str) and img for img in images), (
        "Ollama's vision format carries images as base64 strings in the message"
    )


# --------------------------------------------------------------------------- #
# closed models are refused before any request is built
# --------------------------------------------------------------------------- #
def test_closed_models_are_refused_before_any_request(ai_server):
    base, requests_log = ai_server
    assert_open_weight = require_attr(ai, "assert_open_weight")
    ClosedModelError = require_attr(ai, "ClosedModelError")
    compat_cls = require_attr(ai, "OpenAICompatProvider")
    ollama_cls = require_attr(ai, "OllamaProvider")

    before = len(requests_log)
    with pytest.raises(ClosedModelError):
        assert_open_weight("gpt-4o")
    with pytest.raises(ClosedModelError):
        compat_cls("gpt-4o", base_url=base)
    with pytest.raises(ClosedModelError):
        ollama_cls("gpt-4o", base_url=base)
    assert len(requests_log) == before, (
        "a refused closed model still produced an HTTP request"
    )

    # the allowlist still admits the open-weight model used by this suite
    assert assert_open_weight(_MODEL) == _MODEL


# --------------------------------------------------------------------------- #
# malformed responses: recovered or a clear error — never silent garbage
# --------------------------------------------------------------------------- #
def test_malformed_responses_are_recovered_or_raise_clearly(ai_server, tmp_path, fixtures_dir):
    base, _ = ai_server
    provider_cls = require_attr(ai, "OpenAICompatProvider")
    observe_photos = require_attr(vision_mod, "observe_photos")
    AIExtractionError = require_attr(ai, "AIExtractionError")
    photo = _make_photo(tmp_path, fixtures_dir)

    # markdown fences + trailing prose: the JSON block must still be extracted
    fenced = provider_cls(_MODEL, base_url=f"{base}/malformed")
    data = observe_photos([photo], provider=fenced)
    assert data["captures"], "the fenced response produced no capture"
    assert len(data["elements"]) == 2, (
        f"the parser did not recover the fenced JSON block: {data['elements']}"
    )

    # truncated JSON: a clear AIExtractionError, never a partial/garbage result
    truncated = provider_cls(_MODEL, base_url=f"{base}/truncated")
    with pytest.raises(AIExtractionError) as excinfo:
        observe_photos([photo], provider=truncated)
    message = str(excinfo.value)
    assert message.strip(), "AIExtractionError carried no message"
    assert "could not parse" in message.lower() or "no valid json" in message.lower(), (
        f"the extraction error should explain the parse failure: {message!r}"
    )


# --------------------------------------------------------------------------- #
# the default: no provider configured -> NullProvider, offline
# --------------------------------------------------------------------------- #
def test_default_provider_is_null_and_unavailable(monkeypatch):
    for var in (
        "KARMI_AI_PROVIDER",
        "KARMI_AI_BASE_URL",
        "KARMI_AI_MODEL",
        "KARMI_AI_API_KEY",
        "KARMI_AI_TIMEOUT",
    ):
        monkeypatch.delenv(var, raising=False)

    get_provider = require_attr(ai, "get_provider")
    NullProvider = require_attr(ai, "NullProvider")
    AIUnavailable = require_attr(ai, "AIUnavailable")

    provider = get_provider()
    assert isinstance(provider, NullProvider), (
        f"with no configuration the default must be NullProvider, got {type(provider).__name__}"
    )
    assert provider.available() is False
    with pytest.raises(AIUnavailable):
        provider.complete("hello")

    # an explicit 'none' config is NullProvider too
    assert isinstance(get_provider({"provider": "none"}), NullProvider)