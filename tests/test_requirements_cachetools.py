"""Regression test for the missing-cachetools CI failure.

`platform/api/main.py` and several routers (`backtest.py`, `playbook.py`,
`grid.py`, `signals.py`, `health.py`, `options.py`) import
`cachetools.TTLCache` at module level, but `cachetools` was never added to
`requirements.txt` or `platform/api/requirements.txt`. CI installs
`requirements.txt` (see `.github/workflows/backtest-pipeline.yml`), so any
test that collects one of those modules fails with
`ModuleNotFoundError: No module named 'cachetools'` — this sank PR #745's
CI (runs 30235045716, 30235335101, 2026-07-27) even though that PR's own
diff was unrelated. Pin the dependency declaration so it can't silently
drop out again.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _requirements_text(rel_path: str) -> str:
    path = REPO / rel_path
    assert path.exists(), f"{rel_path} not found"
    return path.read_text()


def _declares_cachetools(text: str) -> bool:
    return re.search(r"^cachetools\b", text, re.MULTILINE) is not None


def test_root_requirements_declares_cachetools():
    """requirements.txt is what CI's `pip install -r requirements.txt`
    installs (backtest-pipeline.yml) — it must declare cachetools since
    platform/api/main.py imports it at module level."""
    text = _requirements_text("requirements.txt")
    assert _declares_cachetools(text), (
        "requirements.txt is missing cachetools — platform/api/main.py "
        "and its routers import cachetools.TTLCache at module level, so "
        "any test that collects those modules fails with "
        "ModuleNotFoundError (see PR #745 CI failure, 2026-07-27)"
    )


def test_platform_api_requirements_declares_cachetools():
    """platform/api/requirements.txt is what the deployed platform-api
    Cloud Run service installs — must also declare cachetools or the
    live service fails at import time."""
    text = _requirements_text("platform/api/requirements.txt")
    assert _declares_cachetools(text), (
        "platform/api/requirements.txt is missing cachetools — the "
        "deployed platform-api image would fail at import time"
    )


def test_every_cachetools_importer_is_covered_by_a_declared_requirement():
    """Sanity check the other direction: every .py file under platform/api
    that imports cachetools is exactly the set this test's rationale
    describes. Guards against silently missing a new importer in the
    docstring/rationale above without also re-verifying the requirements
    files (belt-and-suspenders, not a substitute for the two tests above)."""
    platform_api = REPO / "platform" / "api"
    importers = sorted(
        str(p.relative_to(REPO))
        for p in platform_api.rglob("*.py")
        if re.search(r"^\s*(from cachetools|import cachetools)", p.read_text(), re.MULTILINE)
    )
    assert importers, (
        "expected at least one platform/api module to import cachetools — "
        "if this now fails, either the import was removed (safe to relax "
        "the two tests above) or something renamed the package"
    )
