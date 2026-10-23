"""AI narration guard — ``core.diff.narrate`` must never let a model invent a figure.

The AI may only *rewrite* the deterministic Nepali narration for fluency. The
rewrite is kept only if it has the same line count, stays in Devanagari, and
every number in it was computed by the diff engine. These tests drive the
guard with fake providers that behave well, invent a number, drift in shape,
or fail outright.

The fakes ECHO the template lines they are actually sent (parsed out of the
prompt), so the tests do not depend on the exact template wording.
"""

from __future__ import annotations

import re

import pytest

from conftest import require

diff = require("core.diff")
S = require("core.schema")


def _lines_from_prompt(prompt: str) -> list[str]:
    """The template lines are everything after the final blank-line-delimited header."""
    body = prompt.rsplit("\n\n", 1)[-1]
    return [ln for ln in body.splitlines()[1:] if ln.strip()]


class EchoLLM:
    """A well-behaved open-weight provider: rewrites wording, keeps every number."""

    name = "fake-open-weight-echo"

    def __init__(self, transform=None):
        self.transform = transform or (lambda lines: [f"{ln} (सरल)" for ln in lines])
        self.calls = 0

    def complete(self, prompt, system=None):
        self.calls += 1
        return "\n".join(self.transform(_lines_from_prompt(prompt)))


class RaisingLLM:
    name = "fake-broken"

    def complete(self, prompt, system=None):
        raise RuntimeError("model crashed")


class UnavailableLLM:
    name = "fake-offline"

    def available(self):
        return False

    def complete(self, prompt, system=None):  # pragma: no cover — must not be reached
        raise AssertionError("complete() called although available() is False")


@pytest.fixture
def report():
    return diff.diff_scene(*_models())


def _models():
    from conftest import make_observed, make_scene

    return make_scene(), make_observed()


def _template(report_obj):
    return list(diff.narrate(report_obj.model_copy(deep=True), ai=None).narration_np)


# --------------------------------------------------------------------------- #
def test_no_ai_uses_the_deterministic_template(report):
    out = diff.narrate(report, ai=None)
    assert 3 <= len(out.narration_np) <= 6
    assert all(re.search(r"[\u0900-\u097F]", ln) for ln in out.narration_np)
    assert out.meta["ai"]["used"] is False


def test_faithful_rewrite_is_accepted(report):
    template = _template(report)
    llm = EchoLLM()
    out = diff.narrate(report, ai=llm)
    assert llm.calls == 1
    assert out.meta["ai"]["used"] is True, out.meta["ai"]
    assert out.narration_np != template
    assert len(out.narration_np) == len(template)


def test_rewrite_that_invents_a_number_is_rejected(report):
    template = _template(report)

    def invent(lines):
        return [lines[0] + " झ्याल ९९.७ मिटर चौडा छ", *lines[1:]]

    out = diff.narrate(report, ai=EchoLLM(invent))
    assert out.meta["ai"]["used"] is False
    assert "unverified number" in out.meta["ai"]["reason"]
    assert out.narration_np == template, "the template must be kept when the rewrite is rejected"
    assert any("rejected" in w for w in out.meta.get("warnings", []))


def test_invented_number_in_ascii_digits_is_also_rejected(report):
    out = diff.narrate(report, ai=EchoLLM(lambda ls: [ls[0] + " 42.5", *ls[1:]]))
    assert out.meta["ai"]["used"] is False


@pytest.mark.parametrize(
    "transform, reason",
    [
        (lambda ls: ls[:-1], "expected"),                         # dropped a line
        (lambda ls: ls + ["अतिरिक्त हरफ"], "expected"),            # added a line
        (lambda ls: ["This is English only."] * len(ls), "Devanagari"),
        (lambda ls: [ls[0] + " " + "क" * 300, *ls[1:]], "too long"),
    ],
    ids=["dropped-line", "extra-line", "not-nepali", "too-long"],
)
def test_shape_violations_are_rejected(report, transform, reason):
    template = _template(report)
    out = diff.narrate(report, ai=EchoLLM(transform))
    assert out.meta["ai"]["used"] is False
    assert reason in out.meta["ai"]["reason"], out.meta["ai"]["reason"]
    assert out.narration_np == template


def test_provider_that_raises_falls_back_without_raising(report):
    template = _template(report)
    out = diff.narrate(report, ai=RaisingLLM())
    assert out.meta["ai"]["used"] is False
    assert "failed" in out.meta["ai"]["reason"]
    assert out.narration_np == template


def test_unavailable_provider_is_not_called(report):
    out = diff.narrate(report, ai=UnavailableLLM())
    assert out.meta["ai"]["used"] is False
    assert "unavailable" in out.meta["ai"]["reason"]


def test_numbered_list_markers_are_stripped_before_validation(report):
    """Models love '1.' prefixes; those are formatting, not invented figures."""
    out = diff.narrate(report, ai=EchoLLM(lambda ls: [f"{i}. {ln}" for i, ln in enumerate(ls, 1)]))
    assert out.meta["ai"]["used"] is True, out.meta["ai"]
    assert not any(re.match(r"^\d+\.", ln) for ln in out.narration_np)
