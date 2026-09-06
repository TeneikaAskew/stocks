"""Trading dates are Eastern, and a Cloud SQL failure is not a GCS fallback.

`market_data_intraday.ts` is TIMESTAMPTZ and the Cloud SQL session runs in
UTC, so a bare `DATE(ts)` yields UTC calendar dates. Market data is Eastern.
Measured on prod 2026-09-06 for IWM:

    DISTINCT DATE(ts)                              -> 3,278 dates
    DISTINCT (ts AT TIME ZONE 'America/New_York')  -> 2,927 dates

351 of those (11%) were phantoms — artifacts of after-hours bars at or after
20:00 ET rolling past midnight UTC and being attributed to the next trading
day. The Charts picker offered every one of them.

These assert on the SQL itself rather than round-tripping a database, because
the bug is in how the query frames time, and the hermetic suite has no
timezone-carrying fixture that would reproduce it.
"""
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "platform"))

pytest.importorskip("fastapi")

MAIN_PY = (REPO_ROOT / "platform" / "api" / "main.py").read_text()

# The two queries that derive a trading date from a market-data timestamp.
_ET_CAST = r"ts AT TIME ZONE 'America/New_York'"


def _strip_sql_comments(sql: str) -> str:
    """Drop `-- ...` lines.

    The queries explain the timezone trap in their own comments, quoting the
    wrong form (`DATE(ts)`) to say do-not-do-this. Scanning raw text would
    flag that prose as a violation.
    """
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.split("\n"))


def _market_data_queries() -> list[str]:
    """SQL string literals in main.py that read market_data_intraday."""
    return [_strip_sql_comments(m.group(0)) for m in re.finditer(
        r'"""[^"]*market_data_intraday[^"]*"""', MAIN_PY, re.S)]


def test_every_market_data_date_derivation_uses_eastern():
    """No bare DATE(ts) / ts::date on market_data_intraday anywhere."""
    offenders = []
    for q in _market_data_queries():
        for m in re.finditer(r'DATE\(\s*ts\s*\)|(?<!\))\bts::date\b', q):
            # allowed only if it is the ET-converted form
            window = q[max(0, m.start() - 60):m.end() + 10]
            if _ET_CAST not in window:
                offenders.append(q[max(0, m.start() - 90):m.end() + 30].strip())
    assert not offenders, (
        "bare UTC date derivation on market data — every bar at or after "
        "20:00 ET lands on the next trading day:\n\n" + "\n---\n".join(offenders)
    )


def test_dates_list_and_data_fetch_agree():
    """Both queries must frame time identically.

    If the picker lists ET dates and the data fetch filters UTC dates, the
    user selects a date the loader then cannot find. Neither query is wrong
    on its own; they are wrong relative to each other.
    """
    qs = _market_data_queries()
    listing = [q for q in qs if "DISTINCT" in q and "trade_date" in q]
    fetching = [q for q in qs if "open, high, low, close" in q and "= :dt" in q]
    assert listing, "could not find the dates-listing query"
    assert fetching, "could not find the single-date fetch query"
    for q in listing + fetching:
        assert _ET_CAST in q, f"query does not convert to Eastern:\n{q}"


def test_named_zone_not_a_fixed_offset():
    """EDT is UTC-4 and EST is UTC-5; a hardcoded offset is wrong half the year."""
    for bad in ("'EDT'", "'EST'", "'UTC-4'", "'UTC-5'", "INTERVAL '-4 hours'",
                "INTERVAL '-5 hours'"):
        assert bad not in MAIN_PY, (
            f"{bad} is a fixed offset — use the named zone "
            f"'America/New_York' so DST is handled")


def test_cloud_sql_failure_does_not_silently_serve_gcs():
    """A database error raises rather than downgrading to staging parquets.

    The response does carry source="gcs", but no frontend reads it, so the
    downgrade was invisible in practice (Rule 3.7). The GCS path remains for
    the genuinely different case of Cloud SQL being UNCONFIGURED.
    """
    fn_start = MAIN_PY.index("def get_available_dates")
    fn_end = MAIN_PY.index("@app.get", fn_start + 10)
    body = MAIN_PY[fn_start:fn_end]

    assert "falling back to local" not in body, (
        "the swallowing warning is back — a Cloud SQL failure must not be "
        "downgraded to the GCS staging parquets")
    assert "status_code=503" in body, (
        "a Cloud SQL failure must surface as 503, not an empty/stale 200")
