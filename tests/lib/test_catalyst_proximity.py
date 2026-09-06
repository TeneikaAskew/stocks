"""Phase 1.5 — tests for lib/strategies/catalyst_proximity.py.

Three test surfaces:
  1. Pure helpers (classify_event_type, classify_event_session,
     classify_proximity_bucket) — table-driven, exhaustive.
  2. Internal nearest-event helpers — mocked DB layer.
  3. End-to-end get_catalyst_context — mocked DB, full flow.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from lib.strategies import catalyst_proximity as cp

ET = ZoneInfo("America/New_York")


# ──────────────────────────────────────────────────────────────────────
# 1. classify_event_type — substring-match against HIGH_IMPACT_ECONOMIC
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("event_name,expected", [
    ("FOMC Meeting Announcement", "fomc"),
    ("Federal Open Market Committee", "fomc"),
    ("Fed Interest Rate Decision", "fomc"),
    ("Consumer Price Index (CPI) m/m", "cpi"),
    ("Core CPI y/y", "cpi"),
    ("Employment Situation", "nfp"),
    ("Nonfarm Payrolls", "nfp"),
    ("Non-Farm Payrolls", "nfp"),
    ("Personal Income and Outlays", "pce"),
    ("Core PCE Price Index", "pce"),
    ("Gross Domestic Product Q1", "gdp"),
    ("ISM Manufacturing PMI", "ism"),
    ("ISM Services PMI", "ism"),
    ("Advance Retail Sales", "retail_sales"),
    ("Initial Jobless Claims", "jobless_claims"),
    ("Beige Book", "beige_book"),
    ("Powell Speaks", "fed_speaker"),
    ("Fed Chair Powell at Jackson Hole", "fed_speaker"),
    # negatives
    ("Random Local Holiday", None),
    ("EUR/USD Trading Range", None),
    ("", None),
    (None, None),
])
def test_classify_event_type_table(event_name, expected):
    assert cp.classify_event_type(event_name) == expected


# ──────────────────────────────────────────────────────────────────────
# 2. classify_event_session — by ET clock + weekday
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("dt,expected", [
    # Wednesday 2026-04-29
    (datetime(2026, 4, 29, 8, 30, tzinfo=ET),  "pre_market"),   # CPI release
    (datetime(2026, 4, 29, 4, 0,  tzinfo=ET),  "pre_market"),
    (datetime(2026, 4, 29, 9, 29, tzinfo=ET),  "pre_market"),
    (datetime(2026, 4, 29, 9, 30, tzinfo=ET),  "intraday"),
    (datetime(2026, 4, 29, 14, 0, tzinfo=ET),  "intraday"),     # FOMC
    (datetime(2026, 4, 29, 15, 59, tzinfo=ET), "intraday"),
    (datetime(2026, 4, 29, 16, 0, tzinfo=ET),  "post_market"),
    (datetime(2026, 4, 29, 16, 30, tzinfo=ET), "post_market"),  # earnings_post
    (datetime(2026, 4, 29, 19, 59, tzinfo=ET), "post_market"),
    (datetime(2026, 4, 29, 20, 0, tzinfo=ET),  "pre_market"),   # rolls into next session
    (datetime(2026, 4, 29, 23, 30, tzinfo=ET), "pre_market"),
    # Saturday + Sunday
    (datetime(2026, 5, 2, 14, 0, tzinfo=ET),   "weekend"),       # Sat
    (datetime(2026, 5, 3, 14, 0, tzinfo=ET),   "weekend"),       # Sun
    # Monday
    (datetime(2026, 5, 4, 8, 30, tzinfo=ET),   "pre_market"),
])
def test_classify_event_session_table(dt, expected):
    assert cp.classify_event_session(dt) == expected


def test_classify_event_session_naive_input_treated_as_et():
    """Naive datetimes are treated as ET (defensive default)."""
    naive = datetime(2026, 4, 29, 14, 0)  # no tz
    assert cp.classify_event_session(naive) == "intraday"


# ──────────────────────────────────────────────────────────────────────
# 3. classify_proximity_bucket — exhaustive decision tree
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("next_min,last_min,expected", [
    # imminent: 0-30 min before event
    (0,    None, "imminent"),
    (15,   None, "imminent"),
    (30,   None, "imminent"),
    # pre: 30-120 min before
    (31,   None, "pre"),
    (90,   None, "pre"),
    (120,  None, "pre"),
    # during: 0-60 min after
    (None, 0,    "during"),
    (None, 30,   "during"),
    (None, 60,   "during"),
    # post: 61-180 min after
    (None, 61,   "post"),
    (None, 120,  "post"),
    (None, 180,  "post"),
    # next_day: 181 min - 24 h after
    (None, 181,  "next_day"),
    (None, 720,  "next_day"),
    (None, 1440, "next_day"),
    # quiet: nothing in window
    (None, None,        "quiet"),
    (None, 1441,        "quiet"),  # >24h since
    (1000, None,        "quiet"),  # >2h until
    # imminent overrides during (closest-to-future wins)
    (15,   45,   "imminent"),
    # pre overrides during
    (90,   30,   "pre"),
])
def test_classify_proximity_bucket_table(next_min, last_min, expected):
    assert cp.classify_proximity_bucket(next_min, last_min) == expected


# ──────────────────────────────────────────────────────────────────────
# 4. EMPTY_CONTEXT shape
# ──────────────────────────────────────────────────────────────────────
def test_empty_context_keys():
    expected = {
        "next_catalyst_min", "next_catalyst_type",
        "last_catalyst_min", "last_catalyst_type",
        "catalyst_session", "proximity_bucket",
    }
    assert set(cp.EMPTY_CONTEXT.keys()) == expected
    assert cp.EMPTY_CONTEXT["proximity_bucket"] == "quiet"


# ──────────────────────────────────────────────────────────────────────
# 5. _nearest_economic — mocked DB
# ──────────────────────────────────────────────────────────────────────
def _mock_econ_df(events):
    """events: list of (date, time, name) tuples."""
    return pd.DataFrame([
        {"event_date": e[0], "event_time": e[1], "event_name": e[2],
         "importance": "high"}
        for e in events
    ])


def test_nearest_economic_picks_imminent_fomc():
    cp.reset_cache()
    ts = datetime(2026, 4, 29, 13, 45, tzinfo=ET)  # 15 min before FOMC
    fake = _mock_econ_df([
        (datetime(2026, 4, 29).date(), dtime(14, 0), "FOMC Statement"),
        (datetime(2026, 4, 29).date(), dtime(8, 30), "Initial Jobless Claims"),
    ])
    with patch.object(cp, "_query_or_empty", return_value=fake):
        next_min, next_type, last_min, last_type = cp._nearest_economic(ts)
    assert next_min == 15
    assert next_type == "fomc"
    # last event was Jobless Claims at 8:30, ~315 min ago
    assert last_min == 5 * 60 + 15
    assert last_type == "jobless_claims"


def test_nearest_economic_skips_low_impact():
    cp.reset_cache()
    ts = datetime(2026, 4, 29, 10, 0, tzinfo=ET)
    fake = _mock_econ_df([
        (datetime(2026, 4, 29).date(), dtime(11, 0), "Random Local Event"),
        (datetime(2026, 4, 29).date(), dtime(14, 0), "Federal Open Market Committee"),
    ])
    with patch.object(cp, "_query_or_empty", return_value=fake):
        next_min, next_type, _, _ = cp._nearest_economic(ts)
    assert next_type == "fomc"            # local event ignored
    assert next_min == 4 * 60             # exactly 4h to FOMC


def test_nearest_economic_no_db():
    cp.reset_cache()
    ts = datetime(2026, 4, 29, 10, 0, tzinfo=ET)
    with patch.object(cp, "_query_or_empty", return_value=pd.DataFrame()):
        result = cp._nearest_economic(ts)
    assert result == (None, None, None, None)


# ──────────────────────────────────────────────────────────────────────
# 6. _nearest_earnings — mocked DB
# ──────────────────────────────────────────────────────────────────────
def test_nearest_earnings_premarket():
    cp.reset_cache()
    ts = datetime(2026, 4, 29, 7, 0, tzinfo=ET)  # 1 h before premarket earnings
    fake = pd.DataFrame([
        {"earnings_date": datetime(2026, 4, 29).date(), "earnings_time": "premarket"},
    ])
    with patch.object(cp, "_query_or_empty", return_value=fake):
        next_min, next_type, last_min, last_type = cp._nearest_earnings("MSFT", ts)
    assert next_min == 60
    assert next_type == "earnings_pre"
    assert last_min is None
    assert last_type is None


def test_nearest_earnings_postmarket_already_happened():
    cp.reset_cache()
    ts = datetime(2026, 4, 29, 17, 30, tzinfo=ET)  # 1 h after postmarket
    fake = pd.DataFrame([
        {"earnings_date": datetime(2026, 4, 29).date(), "earnings_time": "postmarket"},
    ])
    with patch.object(cp, "_query_or_empty", return_value=fake):
        next_min, next_type, last_min, last_type = cp._nearest_earnings("MSFT", ts)
    assert next_min is None
    assert last_min == 60
    assert last_type == "earnings_post"


# ──────────────────────────────────────────────────────────────────────
# 7. _nearest_8k — mocked DB, item filter
# ──────────────────────────────────────────────────────────────────────
def test_nearest_8k_material_item_returns_offset():
    cp.reset_cache()
    ts = datetime(2026, 4, 29, 9, 35, tzinfo=ET)
    fake = pd.DataFrame([
        {"filing_date": datetime(2026, 4, 28).date(), "items": ["2.01"]},
    ])
    with patch.object(cp, "_query_or_empty", return_value=fake):
        last_min, last_type = cp._nearest_8k("MSFT", ts)
    # filing assumed at 17:00 ET on 4/28 → ts is 4/29 09:35 = 16h35m later
    assert last_type == "sec_8k"
    assert last_min == 16 * 60 + 35


def test_nearest_8k_immaterial_item_skipped():
    cp.reset_cache()
    ts = datetime(2026, 4, 29, 9, 35, tzinfo=ET)
    fake = pd.DataFrame([
        {"filing_date": datetime(2026, 4, 28).date(), "items": ["3.03"]},  # not in material set
    ])
    with patch.object(cp, "_query_or_empty", return_value=fake):
        last_min, last_type = cp._nearest_8k("MSFT", ts)
    assert (last_min, last_type) == (None, None)


# ──────────────────────────────────────────────────────────────────────
# 8. End-to-end get_catalyst_context — full flow with mocks
# ──────────────────────────────────────────────────────────────────────
def test_get_catalyst_context_imminent_fomc_picks_intraday_session():
    cp.reset_cache()
    ts = pd.Timestamp("2026-04-29 13:45", tz=ET)
    econ_df = _mock_econ_df([
        (datetime(2026, 4, 29).date(), dtime(14, 0), "FOMC Statement"),
    ])

    def fake_query(sql, params):
        if "economic_events" in sql:
            return econ_df
        return pd.DataFrame()

    with patch.object(cp, "_query_or_empty", side_effect=fake_query):
        ctx = cp.get_catalyst_context("SPY", ts)

    assert ctx["next_catalyst_min"] == 15
    assert ctx["next_catalyst_type"] == "fomc"
    assert ctx["proximity_bucket"] == "imminent"
    assert ctx["catalyst_session"] == "intraday"


def test_get_catalyst_context_quiet_when_no_events():
    cp.reset_cache()
    ts = pd.Timestamp("2026-04-29 13:00", tz=ET)
    with patch.object(cp, "_query_or_empty", return_value=pd.DataFrame()):
        ctx = cp.get_catalyst_context("SPY", ts)
    assert ctx["proximity_bucket"] == "quiet"
    assert ctx["next_catalyst_min"] is None
    assert ctx["last_catalyst_min"] is None
    assert ctx["catalyst_session"] is None


def test_get_catalyst_context_caches_within_5min_window():
    cp.reset_cache()
    calls = {"n": 0}

    def fake_query(sql, params):
        calls["n"] += 1
        return pd.DataFrame()

    with patch.object(cp, "_query_or_empty", side_effect=fake_query):
        cp.get_catalyst_context("SPY", pd.Timestamp("2026-04-29 13:00:30", tz=ET))
        cp.get_catalyst_context("SPY", pd.Timestamp("2026-04-29 13:01:30", tz=ET))
        cp.get_catalyst_context("SPY", pd.Timestamp("2026-04-29 13:04:00", tz=ET))
    # 3 calls, all within the same 5-min floor (13:00) → 1 DB pass = 3 queries
    # (one per table — economic, earnings, 8-K)
    assert calls["n"] == 3


def test_get_catalyst_context_recomputes_across_5min_boundary():
    cp.reset_cache()
    calls = {"n": 0}

    def fake_query(sql, params):
        calls["n"] += 1
        return pd.DataFrame()

    with patch.object(cp, "_query_or_empty", side_effect=fake_query):
        cp.get_catalyst_context("SPY", pd.Timestamp("2026-04-29 13:04:30", tz=ET))
        cp.get_catalyst_context("SPY", pd.Timestamp("2026-04-29 13:05:30", tz=ET))
    # crossed 13:05 → second call recomputes → 6 queries total (3 per cycle)
    assert calls["n"] == 6


def test_get_catalyst_context_handles_naive_timestamp():
    cp.reset_cache()
    ts = pd.Timestamp("2026-04-29 13:45")  # tz-naive
    with patch.object(cp, "_query_or_empty", return_value=pd.DataFrame()):
        ctx = cp.get_catalyst_context("SPY", ts)
    assert ctx["proximity_bucket"] == "quiet"  # didn't crash


def test_get_catalyst_context_handles_none_ticker():
    ctx = cp.get_catalyst_context(None, pd.Timestamp("2026-04-29 13:00", tz=ET))
    assert ctx == cp.EMPTY_CONTEXT
    # mutating returned dict must NOT pollute EMPTY_CONTEXT
    ctx["proximity_bucket"] = "MUTATED"
    assert cp.EMPTY_CONTEXT["proximity_bucket"] == "quiet"


def test_get_catalyst_context_handles_nat_timestamp():
    ctx = cp.get_catalyst_context("SPY", pd.NaT)
    assert ctx == cp.EMPTY_CONTEXT


# ──────────────────────────────────────────────────────────────────────
# 9. Integration — earnings + economic combined
# ──────────────────────────────────────────────────────────────────────
def test_get_catalyst_context_imminent_earnings_beats_pre_economic():
    """Imminent earnings (10 min before) wins over a 'pre' economic
    event (90 min before). next_catalyst_type is the closer one."""
    cp.reset_cache()
    ts = pd.Timestamp("2026-04-29 07:50", tz=ET)
    econ_df = _mock_econ_df([
        (datetime(2026, 4, 29).date(), dtime(9, 20), "FOMC Statement"),  # 90 min away
    ])
    earn_df = pd.DataFrame([
        {"earnings_date": datetime(2026, 4, 29).date(), "earnings_time": "premarket"},
    ])  # earnings_pre proxy = 8:00 ET, 10 min away

    def fake_query(sql, params):
        if "economic_events" in sql:
            return econ_df
        if "earnings_calendar" in sql:
            return earn_df
        return pd.DataFrame()

    with patch.object(cp, "_query_or_empty", side_effect=fake_query):
        ctx = cp.get_catalyst_context("MSFT", ts)

    assert ctx["next_catalyst_min"] == 10
    assert ctx["next_catalyst_type"] == "earnings_pre"
    assert ctx["proximity_bucket"] == "imminent"
