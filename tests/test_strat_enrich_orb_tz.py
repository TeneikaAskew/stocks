"""Regression: ORB enrichment must match the opening range in EASTERN time.

`strat_features.ts` is stored UTC, but `calculate_orb`'s `market_open` is
09:30 ET. If `_compute_enrichments` passes the raw UTC wall-clock, every bar
falls outside the 09:30-09:35 window and ORB High/Low/Mid/Range come back
all-NaN — the `orb_5m_high` "always NULL" bug that left the magnitude models
trained on a dead ORB feature set (issue #628).
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("numpy")

from lib.indicators import calculate_orb  # noqa: E402
from gcp.research.strat_engine.strat_enrich_levels import _compute_enrichments  # noqa: E402


def _utc_session():
    """One RTH session of 5-min bars, UTC timestamps (09:30->11:00 ET)."""
    idx = pd.date_range("2026-06-18 13:30", "2026-06-18 15:00", freq="5min", tz="UTC")
    n = len(idx)
    high = pd.Series([100 + i * 0.1 + 0.2 for i in range(n)])
    low = pd.Series([100 + i * 0.1 - 0.2 for i in range(n)])
    close = pd.Series([100 + i * 0.1 for i in range(n)])
    return idx, high, low, close


def test_calculate_orb_requires_eastern_session_window():
    """Documents the contract: calculate_orb's window is ET, so UTC wall-clock
    misses it entirely while ET-localized times populate the ORB high."""
    idx, high, low, close = _utc_session()
    utc = calculate_orb(pd.Series(idx), high, low, close, minutes=5, label="5m")
    assert utc["ORB_5m_High"].isna().all(), "UTC wall-clock must miss the ET window"
    et = calculate_orb(
        pd.Series(idx.tz_convert("America/New_York")), high, low, close,
        minutes=5, label="5m",
    )
    assert et["ORB_5m_High"].notna().any(), "ET-localized times must populate ORB high"


def test_enrichments_populate_orb_high_from_utc_ts():
    """The fix: _compute_enrichments converts ts to ET before the ORB call, so
    orb_5m_high is populated from UTC-stored bars."""
    idx, high, low, close = _utc_session()
    df = pd.DataFrame({
        "ts": idx, "open": close.values, "high": high.values,
        "low": low.values, "close": close.values, "volume": [1000] * len(idx),
    })
    out = _compute_enrichments(df)
    assert "orb_5m_high" in out.columns
    assert out["orb_5m_high"].notna().any(), \
        "orb_5m_high all-NaN — ORB window not matched in ET (timezone regression)"
