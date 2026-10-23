"""Tests for Karmi Open-Weight AI Resiliency, Diagnostics, and Fallback Chaining.

Following Extreme Programming (XP) TDD: Tests are written first before
implementing features in core/ai/provider.py.
"""

from __future__ import annotations

import httpx
import pytest

from core.ai.provider import (
    AIProvider,
    AIProviderError,
    AIUnavailable,
    ClosedModelError,
    NullProvider,
    OllamaProvider,
    OpenAICompatProvider,
    assert_open_weight,
    is_open_weight,
)


class MockHealthyProvider:
    """A mock provider simulating a healthy open-weight endpoint."""

    name = "mock_healthy"
    model = "llama3.2:3b"

    def __init__(self, response: str = "mocked response"):
        self.response = response
        self.calls = 0

    def available(self) -> bool:
        return True

    def complete(self, prompt: str, **kwargs) -> str:
        self.calls += 1
        return self.response

    def diagnose(self) -> dict:
        return {"status": "healthy", "available": True, "provider": self.name, "model": self.model}


class MockFailingProvider:
    """A mock provider simulating an unavailable or failing endpoint."""

    name = "mock_failing"
    model = "qwen2.5:7b"

    def __init__(self, error: Exception | None = None):
        self.error = error or AIUnavailable("Simulated endpoint downtime")
        self.calls = 0

    def available(self) -> bool:
        return False

    def complete(self, prompt: str, **kwargs) -> str:
        self.calls += 1
        raise self.error

    def diagnose(self) -> dict:
        return {"status": "unreachable", "available": False, "provider": self.name, "error": str(self.error)}


def test_null_provider_diagnose():
    """NullProvider must diagnose honestly as disabled/unavailable without network calls."""
    null_p = NullProvider()
    diag = null_p.diagnose()
    assert isinstance(diag, dict)
    assert diag["available"] is False
    assert diag["provider"] == "none"
    assert "disabled" in diag.get("status", "") or "none" in diag.get("status", "")


def test_ollama_provider_diagnose_offline():
    """OllamaProvider diagnose against an unused port must report unreachable cleanly without raising."""
    # Use unused port on localhost
    ollama = OllamaProvider(model="llama3.2:1b", base_url="http://127.0.0.1:59999", timeout=0.1)
    diag = ollama.diagnose()
    assert isinstance(diag, dict)
    assert diag["available"] is False
    assert diag["provider"] == "ollama"
    assert diag["status"] == "unreachable"
    assert "error" in diag


def test_openai_compat_provider_diagnose_offline():
    """OpenAICompatProvider diagnose against an unused port must report unreachable cleanly."""
    compat = OpenAICompatProvider(model="mistral:7b", base_url="http://127.0.0.1:59998", timeout=0.1)
    diag = compat.diagnose()
    assert isinstance(diag, dict)
    assert diag["available"] is False
    assert diag["provider"] == "openai_compat"
    assert diag["status"] == "unreachable"


def test_fallback_provider_primary_healthy():
    """FallbackProvider uses primary when it is available."""
    from core.ai.provider import FallbackProvider

    primary = MockHealthyProvider(response="primary response")
    secondary = MockHealthyProvider(response="secondary response")

    chained = FallbackProvider([primary, secondary])
    assert chained.available() is True
    assert chained.name == "fallback"

    res = chained.complete("Hello")
    assert res == "primary response"
    assert primary.calls == 1
    assert secondary.calls == 0


def test_fallback_provider_primary_fails_secondary_succeeds():
    """FallbackProvider transparently falls back to secondary when primary fails."""
    from core.ai.provider import FallbackProvider

    primary = MockFailingProvider(AIUnavailable("Ollama is down"))
    secondary = MockHealthyProvider(response="secondary fallback response")

    chained = FallbackProvider([primary, secondary])
    assert chained.available() is True

    res = chained.complete("Analyze photo")
    assert res == "secondary fallback response"
    assert primary.calls == 1
    assert secondary.calls == 1
    assert len(chained.fallback_events) >= 1
    assert "Ollama is down" in chained.fallback_events[0]["reason"]


def test_fallback_provider_all_fail():
    """FallbackProvider raises AIUnavailable when all providers in the chain fail."""
    from core.ai.provider import FallbackProvider

    primary = MockFailingProvider(AIUnavailable("Endpoint 1 down"))
    secondary = MockFailingProvider(AIUnavailable("Endpoint 2 down"))

    chained = FallbackProvider([primary, secondary])
    assert chained.available() is False

    with pytest.raises(AIUnavailable) as exc:
        chained.complete("Analyze photo")
    assert "All providers in fallback chain failed" in str(exc.value)


def test_fallback_provider_diagnose():
    """FallbackProvider diagnose aggregates diagnostics from all chained providers."""
    from core.ai.provider import FallbackProvider

    primary = MockFailingProvider(AIUnavailable("Primary down"))
    secondary = MockHealthyProvider(response="OK")

    chained = FallbackProvider([primary, secondary])
    diag = chained.diagnose()
    assert isinstance(diag, dict)
    assert diag["available"] is True
    assert len(diag["providers"]) == 2
    assert diag["providers"][0]["status"] == "unreachable"
    assert diag["providers"][1]["status"] == "healthy"


def test_retry_on_transient_http_error(monkeypatch):
    """Provider retry logic retries on transient connection error before failing."""
    from core.ai.provider import with_retry

    attempts = 0

    def unreliable_call():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("Connection reset by peer")
        return "success after retries"

    result = with_retry(unreliable_call, max_retries=3, initial_delay=0.01)
    assert result == "success after retries"
    assert attempts == 3
