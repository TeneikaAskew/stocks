"""Import-coverage tripwire for every production module.

Why this exists (2026-08-24): main's CI only runs on push / PR. Nothing
was pushed to main between 2026-07-14 and 2026-08-24, and during that
blind window the unpinned *transitive* dependency ``cachetools`` fell
out of fresh pip resolutions — every PR opened in the window then died
at test collection with ModuleNotFoundError, and three duplicate fix
PRs (#746 / #749 / #755) were opened against the same one-line problem.

This test imports every module under ``gcp/``, ``lib/``, and
``platform/api/``, so:

  - a missing (or newly-unpinned) dependency fails with a report naming
    the exact modules that need it, instead of killing collection of
    whichever test file happens to import it first; and
  - modules that no other test imports (several fetchers and job
    entrypoints) still get at least import-time coverage — an
    import-time crash there would otherwise first surface as a
    production Cloud Run failure.

The imports run in ONE clean subprocess, not in the pytest process:
several sibling test files install MagicMock stubs into ``sys.modules``
at module level (lightgbm, google.cloud, …), and pytest imports every
test module during collection — so by run time the parent interpreter
is unavoidably poisoned regardless of test order. A ``__spec__``-less
stub even makes ``importlib.util.find_spec`` raise (seen as a CI
collection error on 2026-08-25). A fresh interpreter sees only the
real installed environment — exactly what production jobs see.

Import-time side effects: repo convention is that modules do real work
only inside ``main()`` / on first call (DB engines are lazy). If this
test flushes out a module that hits the network or requires env vars
at import time, that is itself a bug worth fixing — do not silently
add it to the skip list without a justifying comment.
"""
from __future__ import annotations

import json
import pkgutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PLATFORM_DIR = REPO / "platform"

# platform/ must be importable during discovery: pkgutil.walk_packages
# has to import the `api` package to recurse into api.routers — without
# this, discovery silently found only 4 top-level api.* modules and
# dropped all 18 router modules (caught by Codex review on PR #757).
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

# Modules whose import legitimately requires runtime-only context.
# Keep this list SMALL and justified: every entry is a module with no
# lean-CI import coverage, and an unjustified entry recreates the blind
# spot this test exists to close.
SKIP: dict[str, str] = {}

# Modules that import the research ML stack (requirements-research.txt,
# ~250MB — only installed in backtest-pipeline.yml's research-test job,
# which also runs this file, so they DO get import coverage there).
RESEARCH_PREFIXES = ("gcp.research", "lib.exec_backtest")


def _discover() -> list[str]:
    mods: list[str] = []
    for pkg in ("gcp", "lib"):
        mods.append(pkg)
        for m in pkgutil.walk_packages([str(REPO / pkg)], prefix=f"{pkg}."):
            mods.append(m.name)
    # platform/api is imported as `api.*` with platform/ on sys.path —
    # same convention as tests/api/test_backtest_router_units.py.
    api_dir = PLATFORM_DIR / "api"
    if api_dir.exists():
        mods.append("api")
        for m in pkgutil.walk_packages([str(api_dir)], prefix="api."):
            mods.append(m.name)
    return sorted(set(mods))


MODULES = _discover()


def test_discovery_found_a_realistic_module_count():
    """If discovery breaks (path changes, packaging change), the import
    sweep below would silently shrink and pass. Pin floors so that
    failure mode is loud."""
    assert len(MODULES) >= 150, MODULES
    api_mods = [m for m in MODULES if m.startswith("api.")]
    assert len(api_mods) >= 15, api_mods  # the PR #757 regression


def test_every_module_imports_in_a_clean_interpreter():
    worker = textwrap.dedent("""
        import importlib, importlib.util, json, sys
        platform_dir, modules_json = sys.argv[1], sys.argv[2]
        sys.path.insert(0, platform_dir)
        spec = json.loads(modules_json)
        has_research = importlib.util.find_spec("lightgbm") is not None
        failures, skipped = {}, []
        for name in spec["modules"]:
            if name in spec["skip"]:
                skipped.append(name)
                continue
            if (not has_research
                    and name.startswith(tuple(spec["research_prefixes"]))):
                skipped.append(name)
                continue
            try:
                importlib.import_module(name)
            except BaseException as e:  # report SystemExit too
                failures[name] = f"{type(e).__name__}: {e}"
        print(json.dumps({"failures": failures, "skipped": len(skipped),
                          "imported": len(spec["modules"]) - len(skipped)
                          - len(failures)}))
    """)
    payload = json.dumps({
        "modules": MODULES,
        "skip": SKIP,
        "research_prefixes": list(RESEARCH_PREFIXES),
    })
    proc = subprocess.run(
        [sys.executable, "-c", worker, str(PLATFORM_DIR), payload],
        capture_output=True, text=True, cwd=str(REPO), timeout=600,
    )
    assert proc.returncode == 0, (
        f"import worker crashed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    assert not report["failures"], (
        "modules failed to import in a clean interpreter "
        "(missing dependency? import-time side effect?):\n"
        + json.dumps(report["failures"], indent=2)
    )
    # Meaningful floor: most of the tree must actually have been imported.
    assert report["imported"] >= 130, report
