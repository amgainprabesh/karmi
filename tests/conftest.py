"""Shared fixtures and tolerant helpers for the Karmi test suite.

Why this file looks the way it does
-----------------------------------
Several modules (``core.model``, ``core.observe``, ``core.diff``,
``core.report``, ``core.validate``, ``render.adapter``, ``web.app``) are being
written by other agents *while* this suite is developed. The suite therefore
follows a tolerant pattern:

* a module that does not exist yet  -> **skip** (``require()`` /
  ``pytest.importorskip``), never fail;
* a module that exists but misbehaves -> **fail** (that is the signal);
* assertions target behaviour guaranteed by ``core/schema.py`` and the pipeline
  contract, never exact internal numbers.

Helpers exported for test modules (``from conftest import ...``):

``require``        import a module or skip with a clear reason
``require_attr``   fetch an entry point or skip if it does not exist yet
``call_adaptive``  call a function with only the kwargs its signature accepts
``no_network``     context manager that makes any real network attempt explode
``make_scene`` / ``make_observed`` / ``make_report`` and small element helpers
                   build hand-made models so schema/diff/report tests never
                   depend on the extractor
"""

from __future__ import annotations

import contextlib
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = REPO_ROOT / "fixtures"

# Make `core`/`render`/`web` importable regardless of how pytest was invoked,
# and make this helper module importable as `conftest` from test files.
for _p in (str(REPO_ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import schema as S  # noqa: E402  (sys.path prepared above)


# --------------------------------------------------------------------------- #
# tolerant import / call helpers
# --------------------------------------------------------------------------- #
def require(module_name: str, reason: str | None = None):
    """Import ``module_name``, or skip the current test/module with a reason.

    Only ImportError (module missing, or a sibling not written yet) turns into
    a skip. A module that exists but raises something else at import time is
    broken, and broken is allowed to turn the suite red.
    """
    return pytest.importorskip(
        module_name,
        reason=reason
        or f"{module_name} is not importable yet (being written in parallel) — skipping",
    )


def require_attr(module, name: str, reason: str | None = None):
    """Return ``module.name``, or skip if that entry point does not exist yet."""
    fn = getattr(module, name, None)
    if fn is None:
        pytest.skip(
            reason
            or f"{getattr(module, '__name__', module)}.{name} does not exist yet — skipping"
        )
    return fn


def call_adaptive(fn, *args, **kwargs):
    """Call ``fn`` passing only the keyword arguments its signature accepts.

    Parallel agents may still be settling exact signatures; this keeps tests
    honest about behaviour while tolerating minor signature drift.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):  # builtins / callables without a signature
        return fn(*args, **kwargs)
    params = sig.parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(*args, **kwargs)
    accepted = {k: v for k, v in kwargs.items() if k in params}
    return fn(*args, **accepted)


NETWORK_SENTINEL = "NETWORK-ACCESS-ATTEMPTED"


@contextlib.contextmanager
def no_network(monkeypatch):
    """Explode on any real network attempt; yields the sentinel string.

    Covers httpx (module helpers + Client/AsyncClient), urllib, and the
    underlying http.client / socket entry points, so even a bound
    ``from httpx import get`` import is caught via the class-level patch.
    """

    def boom(*_a, **_k):
        raise AssertionError(f"{NETWORK_SENTINEL}: this code path must run offline")

    async def aboom(*_a, **_k):
        raise AssertionError(f"{NETWORK_SENTINEL}: this code path must run offline")

    import http.client
    import socket
    import urllib.request

    for obj, attr in (
        (urllib.request, "urlopen"),
        (socket, "create_connection"),
        (http.client.HTTPConnection, "connect"),
        (http.client.HTTPConnection, "request"),
    ):
        monkeypatch.setattr(obj, attr, boom, raising=False)

    try:
        import httpx
    except ImportError:
        pass
    else:
        for attr in ("get", "post", "put", "delete", "request", "stream"):
            if hasattr(httpx, attr):
                monkeypatch.setattr(httpx, attr, boom, raising=False)
        for attr in ("request", "send"):
            monkeypatch.setattr(httpx.Client, attr, boom, raising=False)
            monkeypatch.setattr(httpx.AsyncClient, attr, aboom, raising=False)

    yield NETWORK_SENTINEL


# --------------------------------------------------------------------------- #
# hand-made models — schema/diff/report tests must not depend on the extractor
# --------------------------------------------------------------------------- #
def _prov(confidence: float = 0.9, source: str = "vector_geometry", evidence: str | None = None):
    return S.Provenance(source=source, confidence=confidence, evidence=evidence)


def make_wall(
    wall_id: str = "w1",
    start=(0.0, 0.0),
    end=(6.0, 0.0),
    thickness: float | None = 0.23,
    is_external: bool = True,
    confidence: float = 0.95,
) -> S.Wall:
    return S.Wall(
        id=wall_id,
        start=tuple(start),
        end=tuple(end),
        thickness=thickness,
        is_external=is_external,
        provenance=_prov(confidence, "vector_geometry", "handmade"),
    )


def make_wall_element(
    element_id: str = "o1",
    length: float = 6.0,
    height: float = 2.7,
    matches: str | None = "w1",
    confidence: float = 0.8,
) -> S.ObservedElement:
    return S.ObservedElement(
        id=element_id,
        kind=S.ElementKind.WALL,
        approx_size={"length": float(length), "height": float(height)},
        location_hint="front",
        matches_scene_id=matches,
        provenance=_prov(confidence, "ai_vision", "handmade"),
    )


def make_observed_for(
    elements,
    stage: S.Stage = S.Stage.WALLS,
    capture_file: str = "front.jpg",
    stage_confidence: float = 0.8,
) -> S.ObservedState:
    return S.ObservedState(
        stage=stage,
        stage_provenance=_prov(stage_confidence, "ai_vision"),
        captures=[
            S.Capture(
                file=capture_file,
                stage=stage,
                stage_confidence=stage_confidence,
                view="front",
                provenance=_prov(stage_confidence, "ai_vision"),
            )
        ],
        elements=list(elements),
    )


def make_scene() -> S.SceneGraph:
    """A small hand-made 6.0 m x 4.0 m house — canonical sample for tests."""
    return S.SceneGraph(
        source_file="handmade://sample-naksa",
        walls=[
            make_wall("w_south", (0.0, 0.0), (6.0, 0.0)),
            make_wall("w_east", (6.0, 0.0), (6.0, 4.0)),
            make_wall("w_north", (0.0, 4.0), (6.0, 4.0)),
            make_wall("w_west", (0.0, 0.0), (0.0, 4.0)),
            make_wall("w_mid", (3.0, 0.0), (3.0, 4.0), thickness=0.115, is_external=False),
        ],
        openings=[
            S.Opening(
                id="o_window",
                kind=S.OpeningKind.WINDOW,
                wall_id="w_north",
                center=(2.0, 4.0),
                width=1.5,
                height=1.2,
                sill_height=0.9,
                provenance=_prov(0.9, "vector_geometry", "handmade"),
            ),
            S.Opening(
                id="o_door",
                kind=S.OpeningKind.DOOR,
                wall_id="w_south",
                center=(3.0, 0.0),
                width=0.9,
                height=2.1,
                sill_height=0.0,
                provenance=_prov(0.9, "vector_geometry", "handmade"),
            ),
        ],
        rooms=[
            S.Room(
                id="r_living",
                name="LIVING",
                name_np="बैठक",
                polygon=[(0.0, 0.0), (3.0, 0.0), (3.0, 4.0), (0.0, 4.0)],
                area_m2=12.0,
                provenance=_prov(0.8, "vector_geometry", "handmade"),
            ),
        ],
        dimensions=[
            S.Dimension(
                id="dim_width",
                value=6.0,
                unit="m",
                label="6.0 m",
                start=(0.0, 0.0),
                end=(6.0, 0.0),
                provenance=_prov(0.9, "vector_geometry", "handmade"),
            ),
        ],
        north_deg=0.0,
        scale_m_per_unit=1.0,
        bbox=(0.0, 0.0, 6.0, 4.0),
        warnings=[],
        meta={"handmade": True},
    )


def make_observed() -> S.ObservedState:
    return make_observed_for(
        [
            make_wall_element("obs_w_south", 6.0, matches="w_south"),
            S.ObservedElement(
                id="obs_window",
                kind=S.ElementKind.OPENING,
                approx_size={"width": 1.5},
                location_hint="north wall",
                matches_scene_id="o_window",
                provenance=_prov(0.75, "ai_vision", "handmade"),
            ),
        ]
    )


def make_report() -> S.DiffReport:
    """A hand-made DiffReport covering matched / differs / missing / unexpected."""
    report = S.DiffReport(
        scene_file="handmade://sample-naksa",
        observed_files=["front.jpg"],
        deltas=[
            S.Delta(
                id="delta_1",
                element="wall w_south",
                scene_ref="w_south",
                observed_ref="obs_w_south",
                status=S.DeltaStatus.MATCHED,
                expected="length 6.0 m",
                observed="length 6.0 m",
                severity=S.Severity.INFO,
                confidence=0.8,
                reason="Matches the approved drawing.",
            ),
            S.Delta(
                id="delta_2",
                element="window o_window",
                scene_ref="o_window",
                observed_ref="obs_window",
                status=S.DeltaStatus.DIFFERS,
                expected="width 1.5 m",
                observed="width 1.2 m",
                severity=S.Severity.MEDIUM,
                confidence=0.7,
                reason="Narrower than approved.",
                reason_np="स्वीकृत भन्दा साँघुरो।",
            ),
            S.Delta(
                id="delta_3",
                element="wall w_east",
                scene_ref="w_east",
                status=S.DeltaStatus.MISSING,
                expected="length 4.0 m",
                severity=S.Severity.LOW,
                confidence=0.5,
                reason="Not visible in the photos yet.",
            ),
            S.Delta(
                id="delta_4",
                element="unexpected block wall",
                observed_ref="obs_extra",
                status=S.DeltaStatus.UNEXPECTED,
                observed="approx 3.0 m long",
                severity=S.Severity.LOW,
                confidence=0.4,
                reason="Seen on site, not in the drawing.",
            ),
        ],
        verify_list=[
            S.VerifyItem(
                id="verify_1",
                item="Measure the north window width on site.",
                item_np="उत्तरतर्फको झ्यालको चौडाइ नाप्नुहोस्।",
                why="The photos suggest it is narrower than approved.",
                how="Tape-measure the clear opening and compare with 1.5 m.",
                severity=S.Severity.MEDIUM,
                delta_ref="delta_2",
            ),
        ],
        narration_en=["The north window appears narrower than approved."],
        narration_np=["उत्तरतर्फको झ्याल स्वीकृत भन्दा साँघुरो देखिन्छ।"],
        limits=["Photos cannot confirm wall thickness."],
        meta={"handmade": True},
    )
    return report.recount()


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def naksa_base() -> Path:
    return FIXTURES_DIR / "naksa_base.pdf"


@pytest.fixture(scope="session")
def naksa_drift() -> Path:
    return FIXTURES_DIR / "naksa_drift.pdf"


@pytest.fixture(scope="session")
def naksa_sparse() -> Path:
    return FIXTURES_DIR / "naksa_sparse.pdf"


@pytest.fixture
def tmp_run_dir(tmp_path: Path) -> Path:
    """A clean directory for pipeline runs inside pytest's tmp space."""
    d = tmp_path / "karmi_run"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def sample_scene() -> S.SceneGraph:
    return make_scene()


@pytest.fixture
def sample_observed() -> S.ObservedState:
    return make_observed()


@pytest.fixture
def sample_report() -> S.DiffReport:
    return make_report()


@pytest.fixture
def sample_models():
    """The hand-made pair (scene, observed, report) as one object."""
    return SimpleNamespace(scene=make_scene(), observed=make_observed(), report=make_report())


@pytest.fixture
def require_module():
    """The ``require()`` helper as a fixture, for tests that prefer injection."""
    return require