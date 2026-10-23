"""Karmi — open-weight-only AI layer.

Public surface
--------------
* ``get_provider(config=None)`` — the only factory the pipeline uses. Reads
  ``KARMI_AI_PROVIDER`` (``none`` | ``ollama`` | ``openai_compat``),
  ``KARMI_AI_BASE_URL``, ``KARMI_AI_MODEL``, ``KARMI_AI_API_KEY`` and
  ``KARMI_AI_TIMEOUT``. With no configuration it returns ``NullProvider``:
  the product runs with zero configuration and zero network calls.
* ``assert_open_weight`` / ``is_open_weight`` — the enforced allowlist of
  open-weight model families. Closed models (GPT, Claude, Gemini, ...) are
  refused with ``ClosedModelError`` before any request is built.
* ``AIUnavailable`` — raised when a provider cannot be used; callers degrade.
* ``observe_photos`` — photos -> structured observation via ``core.ai.vision``.

Importing this package performs no network calls.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

from . import prompts  # noqa: F401 — re-exported for convenience
from .provider import (
    DEFAULT_COMPAT_BASE_URL,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_TIMEOUT_S,
    OPEN_WEIGHT_FAMILIES,
    AIProvider,
    AIProviderError,
    AIUnavailable,
    ClosedModelError,
    FallbackProvider,
    NullProvider,
    OllamaProvider,
    OpenAICompatProvider,
    assert_open_weight,
    is_open_weight,
    with_retry,
)
from .vision import AIExtractionError, observe_photos

__all__ = [
    "AIProvider",
    "AIProviderError",
    "AIUnavailable",
    "AIExtractionError",
    "ClosedModelError",
    "NullProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "FallbackProvider",
    "with_retry",
    "OPEN_WEIGHT_FAMILIES",
    "DEFAULT_OLLAMA_MODEL",
    "DEFAULT_OLLAMA_BASE_URL",
    "DEFAULT_COMPAT_BASE_URL",
    "DEFAULT_TIMEOUT_S",
    "assert_open_weight",
    "is_open_weight",
    "get_provider",
    "observe_photos",
    "prompts",
]


def _cfg_get(config: Any, key: str) -> str | None:
    """Read ``key`` from a mapping or an attribute-style config object."""
    if config is None:
        return None
    if isinstance(config, Mapping):
        value = config.get(key)
    else:
        value = getattr(config, key, None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _timeout(config: Any, *, default: float = DEFAULT_TIMEOUT_S) -> float:
    raw = _cfg_get(config, "timeout") or os.environ.get("KARMI_AI_TIMEOUT")
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"KARMI_AI_TIMEOUT must be a number of seconds, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"KARMI_AI_TIMEOUT must be positive, got {raw!r}")
    return value


def get_provider(config: Any = None) -> AIProvider:
    """Build the configured provider. Default: ``NullProvider`` (no AI, no network).

    ``config`` may be a mapping (or any object with matching attributes) with
    keys ``provider``, ``base_url``, ``model``, ``api_key``, ``timeout``.
    Values from ``config`` win over environment variables.
    """
    kind = (_cfg_get(config, "provider") or os.environ.get("KARMI_AI_PROVIDER") or "none")
    kind = kind.strip().lower()

    if kind in ("", "none", "null", "off", "false"):
        return NullProvider()

    if kind == "ollama":
        model = _cfg_get(config, "model") or os.environ.get("KARMI_AI_MODEL") or DEFAULT_OLLAMA_MODEL
        base_url = (
            _cfg_get(config, "base_url")
            or os.environ.get("KARMI_AI_BASE_URL")
            or DEFAULT_OLLAMA_BASE_URL
        )
        return OllamaProvider(model=model, base_url=base_url, timeout=_timeout(config))

    if kind in ("openai_compat", "openai-compat", "compat"):
        model = _cfg_get(config, "model") or os.environ.get("KARMI_AI_MODEL")
        if not model:
            raise ValueError(
                "KARMI_AI_MODEL (or config['model']) is required for the openai_compat provider"
            )
        base_url = (
            _cfg_get(config, "base_url")
            or os.environ.get("KARMI_AI_BASE_URL")
            or DEFAULT_COMPAT_BASE_URL
        )
        api_key = _cfg_get(config, "api_key") or os.environ.get("KARMI_AI_API_KEY")
        return OpenAICompatProvider(
            model=model, base_url=base_url, api_key=api_key, timeout=_timeout(config)
        )

    if kind in ("fallback", "resilient"):
        primary = OllamaProvider(
            model=_cfg_get(config, "model") or os.environ.get("KARMI_AI_MODEL") or DEFAULT_OLLAMA_MODEL,
            base_url=_cfg_get(config, "base_url") or os.environ.get("KARMI_AI_BASE_URL") or DEFAULT_OLLAMA_BASE_URL,
            timeout=_timeout(config),
        )
        return FallbackProvider([primary, NullProvider()])

    raise ValueError(
        f"Unknown AI provider {kind!r}: expected one of none | ollama | openai_compat | fallback"
    )