"""Karmi — AI provider layer. OPEN-WEIGHT MODELS ONLY.

Karmi never calls a closed model API (OpenAI, Anthropic/Claude, Google Gemini,
Azure, ...). That rule is enforced in code: every provider that accepts a model
name must pass ``assert_open_weight(model)`` before it can be constructed, and
``get_provider()`` (see ``core/ai/__init__.py``) is the only factory the rest of
the pipeline uses.

Providers
---------
* ``NullProvider``         — the default. ``available()`` is False and
  ``complete()`` raises ``AIUnavailable``. The whole product runs with zero
  configuration and zero network calls.
* ``OllamaProvider``       — a local Ollama server (default
  http://localhost:11434), ``/api/chat``, images as base64 (Ollama's vision
  format). Short timeouts, clean errors.
* ``OpenAICompatProvider`` — any OpenAI-compatible endpoint that serves OPEN
  WEIGHTS (vLLM, LM Studio, llama.cpp server, Fireworks, Together).

Importing this module never touches the network; nothing here opens a socket
unless ``available()`` / ``complete()`` is called on a provider the user
explicitly configured.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable

import httpx

DEFAULT_OLLAMA_MODEL = "qwen2.5-vl:7b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_COMPAT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_TIMEOUT_S = 60.0


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #
class AIUnavailable(RuntimeError):
    """The AI provider cannot be used (not configured, or not reachable)."""


class AIProviderError(RuntimeError):
    """The AI provider was reachable but the call failed."""


class ClosedModelError(ValueError):
    """A model outside Karmi's open-weight allowlist was requested."""


# --------------------------------------------------------------------------- #
# open-weight allowlist (enforced, not advisory)
# --------------------------------------------------------------------------- #
OPEN_WEIGHT_FAMILIES: tuple[str, ...] = (
    "qwen",
    "llama",
    "mistral",
    "mixtral",
    "gemma",
    "deepseek",
    "phi",
    "nomic",
    "bge",
    "granite",
    "olmo",
    "smol",
    "internvl",
    "llava",
    "yi",
    "falcon",
)

# Families short enough to appear inside unrelated words ("sapphire" contains
# "phi"); these must sit on a token boundary.
_BOUNDARY_FAMILIES = frozenset({"yi", "phi", "bge"})


def _has_boundary_match(model: str, family: str) -> bool:
    start = 0
    while True:
        i = model.find(family, start)
        if i == -1:
            return False
        before = model[i - 1] if i > 0 else ""
        after = model[i + len(family)] if i + len(family) < len(model) else ""
        if (before == "" or not before.isalnum()) and (after == "" or not after.isalnum()):
            return True
        start = i + 1


def is_open_weight(model: str) -> bool:
    """True when ``model`` belongs to an open-weight family Karmi may call."""
    m = str(model or "").strip().lower()
    if not m:
        return False
    for family in OPEN_WEIGHT_FAMILIES:
        if family in _BOUNDARY_FAMILIES:
            if _has_boundary_match(m, family):
                return True
        elif family in m:
            return True
    return False


def assert_open_weight(model: str) -> str:
    """Return ``model`` when it is open-weight; otherwise raise ``ClosedModelError``."""
    if not is_open_weight(model):
        raise ClosedModelError(
            f"Refusing model {model!r}: it is not on Karmi's open-weight allowlist "
            f"({', '.join(OPEN_WEIGHT_FAMILIES)}). Karmi only runs open-weight models."
        )
    return model


# --------------------------------------------------------------------------- #
# image handling (paths / bytes / data URLs / raw base64 -> (mime, base64))
# --------------------------------------------------------------------------- #
_IMAGE_SUFFIX_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}
_B64_RE = re.compile(r"^[A-Za-z0-9+/=\s]+$")


def _image_payload(item: Any) -> tuple[str, str]:
    """Return ``(mime, base64)`` for a file path, bytes, data URL or base64 string."""
    if isinstance(item, (bytes, bytearray)):
        return "image/jpeg", base64.b64encode(bytes(item)).decode("ascii")
    if isinstance(item, Path):
        try:
            data = item.read_bytes()
        except OSError as exc:
            raise AIProviderError(f"could not read image {str(item)!r}: {exc}") from exc
        return _IMAGE_SUFFIX_MIME.get(item.suffix.lower(), "image/jpeg"), base64.b64encode(data).decode("ascii")
    if isinstance(item, str):
        s = item.strip()
        m = re.match(r"^data:([^;,]+);base64,(.*)$", s, re.DOTALL)
        if m:
            return m.group(1), "".join(m.group(2).split())
        try:
            p = Path(s)
            if p.is_file():
                data = p.read_bytes()
                return _IMAGE_SUFFIX_MIME.get(p.suffix.lower(), "image/jpeg"), base64.b64encode(data).decode("ascii")
        except OSError:
            pass
        if len(s) >= 32 and _B64_RE.match(s):
            return "image/jpeg", "".join(s.split())
        raise AIProviderError(f"image not found and not valid base64: {s[:120]!r}")
    raise AIProviderError(f"unsupported image argument of type {type(item).__name__}")


# --------------------------------------------------------------------------- #
# provider protocol
# --------------------------------------------------------------------------- #
@runtime_checkable
class AIProvider(Protocol):
    """The shape every Karmi AI backend implements."""

    name: str
    model: str

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: Sequence[Any] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        """Run one completion. ``images`` may be paths, bytes, data URLs or base64."""
        ...

    def available(self) -> bool:
        """Cheap check: is this provider usable right now? Must never raise."""
        ...


# --------------------------------------------------------------------------- #
# null provider (default)
# --------------------------------------------------------------------------- #
class NullProvider:
    """The default: no AI at all. The pipeline degrades honestly, never guesses."""

    name = "none"
    model = ""

    def available(self) -> bool:
        return False

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: Sequence[Any] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        raise AIUnavailable(
            "No AI provider is configured (NullProvider). "
            "Set KARMI_AI_PROVIDER=ollama or KARMI_AI_PROVIDER=openai_compat to enable AI."
        )


# --------------------------------------------------------------------------- #
# ollama (local, default deployment)
# --------------------------------------------------------------------------- #
class OllamaProvider:
    """Local Ollama server — https://github.com/ollama/ollama.

    Uses ``POST /api/chat`` with ``stream: false``; images travel as base64
    strings in the message's ``images`` field (Ollama's vision format).
    """

    name = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        *,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.model = assert_open_weight(model)
        self.base_url = (str(base_url).strip().rstrip("/")) or DEFAULT_OLLAMA_BASE_URL
        self.timeout = float(timeout)

    def available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=min(2.0, self.timeout))
        except httpx.HTTPError:
            return False
        return resp.status_code == 200

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: Sequence[Any] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": str(system)})
        user: dict[str, Any] = {"role": "user", "content": str(prompt)}
        if images:
            user["images"] = [_image_payload(img)[1] for img in images]
        messages.append(user)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": float(temperature), "num_predict": int(max_tokens)},
        }
        url = f"{self.base_url}/api/chat"
        try:
            resp = httpx.post(url, json=payload, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise AIUnavailable(
                f"Ollama at {self.base_url} is not reachable ({exc.__class__.__name__}: {exc}). "
                "Is the Ollama server running?"
            ) from exc
        if resp.status_code >= 400:
            raise AIProviderError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            content = resp.json()["message"]["content"]
        except Exception as exc:  # noqa: BLE001 — any shape surprise is a provider error
            raise AIProviderError(f"unexpected response shape from Ollama: {exc}") from exc
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("Ollama returned an empty completion")
        return content


# --------------------------------------------------------------------------- #
# any OpenAI-compatible endpoint serving open weights
# --------------------------------------------------------------------------- #
class OpenAICompatProvider:
    """OpenAI-compatible chat endpoint (vLLM, LM Studio, llama.cpp, Fireworks, Together).

    ``base_url`` is normalised: if it does not end in ``/v<n>``, ``/v1`` is
    appended (e.g. ``http://localhost:8000`` -> ``.../v1/chat/completions``).
    """

    name = "openai_compat"

    def __init__(
        self,
        model: str,
        *,
        base_url: str = DEFAULT_COMPAT_BASE_URL,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.model = assert_open_weight(model)
        base = str(base_url).strip().rstrip("/")
        if not base:
            raise ValueError("base_url is required for the openai_compat provider")
        self.base_url = base
        self.api_key = (str(api_key).strip() or None) if api_key else None
        self.timeout = float(timeout)

    def _url(self, path: str) -> str:
        base = self.base_url
        if not re.search(r"/v\d+$", base):
            base += "/v1"
        return base + path

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def available(self) -> bool:
        try:
            resp = httpx.get(self._url("/models"), headers=self._headers(), timeout=min(2.0, self.timeout))
        except httpx.HTTPError:
            return False
        if resp.status_code >= 500 or resp.status_code in (401, 403):
            return False
        return True

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        images: Sequence[Any] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": str(system)})
        content: Any = str(prompt)
        if images:
            parts: list[dict[str, Any]] = [{"type": "text", "text": str(prompt)}]
            for img in images:
                mime, b64 = _image_payload(img)
                parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
            content = parts
        messages.append({"role": "user", "content": content})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
            "stream": False,
        }
        url = self._url("/chat/completions")
        try:
            resp = httpx.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise AIUnavailable(
                f"openai-compat endpoint {self.base_url} is not reachable "
                f"({exc.__class__.__name__}: {exc})."
            ) from exc
        if resp.status_code >= 400:
            raise AIProviderError(f"openai-compat endpoint returned HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            message = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"unexpected response shape from {self.base_url}: {exc}") from exc
        if isinstance(message, list):  # some servers return content parts
            message = "".join(
                str(part.get("text", "")) for part in message if isinstance(part, dict)
            )
        if not isinstance(message, str) or not message.strip():
            raise AIProviderError("openai-compat endpoint returned an empty completion")
        return message


__all__ = [
    "DEFAULT_OLLAMA_MODEL",
    "DEFAULT_OLLAMA_BASE_URL",
    "DEFAULT_COMPAT_BASE_URL",
    "DEFAULT_TIMEOUT_S",
    "OPEN_WEIGHT_FAMILIES",
    "AIProvider",
    "AIUnavailable",
    "AIProviderError",
    "ClosedModelError",
    "NullProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "is_open_weight",
    "assert_open_weight",
]