"""The API image installs the same pandas-market-calendars as the locks.

Why (FEAT-DATA-001): lib/eastern_time.py imports pandas_market_calendars
lazily, and the FastAPI app calls those functions. The platform-api image
installs ONLY platform/api/requirements.txt plus the Dockerfile's inline
list (not the lock files), so a library that "works in requirements.lock"
is absent from the image and every call fails at request time. The
holiday table is data inside the library, so a version that drifts between
the API image and the research/GCP jobs means the two disagree about which
days the market is open. This pins all three to one version.

Repo-level invariant, so it lives in tests/meta/ (two levels below root).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPECTED = "5.3.0"
PIN_FILES = (
    "platform/api/requirements.txt",
    "requirements.lock",
    "requirements-gcp.lock",
)


def _pinned_version(rel_path: str) -> str | None:
    """Exact ``==`` pin of pandas-market-calendars in a requirements file."""
    for raw in (REPO / rel_path).read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*==\s*([^\s;]+)", line)
        if m and re.sub(r"[-_.]+", "-", m.group(1)).lower() == "pandas-market-calendars":
            return m.group(2)
    return None


def test_api_pin_matches_locks():
    pins = {path: _pinned_version(path) for path in PIN_FILES}
    assert pins == {path: EXPECTED for path in PIN_FILES}, pins
