"""Import-coverage tripwire for every production module.

Why this exists (2026-08-24): main's CI only runs on push / PR. Nothing
was pushed to main between 2026-07-14 and 2026-08-24, and during that
blind window the unpinned *transitive* dependency ``cachetools`` fell
out of fresh pip resolutions — every PR opened in the window then died
at test collection with ModuleNotFoundError, and three duplicate fix
PRs (#746 / #749 / #755) were opened against the same one-line problem.

This test imports every module under ``gcp/``, ``lib/``, and
``platform/api/`` directly, so:

  - a missing (or newly-unpinned) dependency fails ONE parametrized
    case named after the exact module that needs it, instead of
    killing collection of whichever test file happens to import it
    first; and
  - modules that no other test imports (several fetchers and job
    entrypoints) still get at least import-time coverage — an
    import-time crash there would otherwise first surface as a
    production Cloud Run failure.

Import-time side effects: repo convention is that modules do real work
only inside ``main()`` / on first call (DB engines are lazy). If this
test flushes out a module that hits the network or requires env vars
at import time, that is itself a bug worth fixing — do not silently
add it to the skip list without a justifying comment.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLATFORM_DIR = REPO / "platform"

# Modules whose import legitimately requires other justified
# runtime-only context. Keep this list SMALL: every entry is a module
# with no lean-CI import coverage, and an unjustified entry recreates
# the blind spot this test exists to close.
SKIP: dict[str, str] = {}

# The research ML stack (requirements-research.txt, ~250MB) is only
# installed in backtest-pipeline.yml's research-test job — which also
# runs THIS file, so these modules do get import coverage there. In the
# lean job they skip with an explicit reason instead of failing.
_HAS_RESEARCH = importlib.util.find_spec("lightgbm") is not None


def _needs_research_stack(name: str) -> bool:
    return name.startswith("gcp.research") or name.startswith("lib.exec_backtest")


def _discover() -> list[str]:
    mods: list[str] = []
    for pkg in ("gcp", "lib"):
        mods.append(pkg)
        for m in pkgutil.walk_packages([str(REPO / pkg)], prefix=f"{pkg}."):
            mods.append(m.name)
    # platform/api is imported as `api.*` with platform/ on sys.path —
    # same convention as tests/test_backtest_router_units.py.
    api_dir = PLATFORM_DIR / "api"
    if api_dir.exists():
        mods.append("api")
        for m in pkgutil.walk_packages([str(api_dir)], prefix="api."):
            mods.append(m.name)
    return sorted(set(mods))


MODULES = _discover()


def test_discovery_found_a_realistic_module_count():
    """If discovery breaks (path changes, packaging change), the
    parametrized test below would silently shrink to nothing and pass.
    Pin a floor so that failure mode is loud."""
    assert len(MODULES) >= 60, MODULES


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str):
    if name in SKIP:
        pytest.skip(SKIP[name])
    if _needs_research_stack(name) and not _HAS_RESEARCH:
        pytest.skip("research stack absent — import-covered by the "
                    "research-test CI job, which runs this file with "
                    "requirements-research.txt installed")
    if str(PLATFORM_DIR) not in sys.path:
        sys.path.insert(0, str(PLATFORM_DIR))
    importlib.import_module(name)
