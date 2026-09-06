"""Regression tests for the silent fallbacks fixed on this branch.

Each case shares a shape: the old code returned a neutral value the caller
could not distinguish from a real result, so **no test could tell the two
worlds apart** and the suite passed either way. That is why these sites
survived the 2026-05-13 fallback audit by four months. Each test below fails
against the pre-fix code and passes after.

See `docs/audits/FALLBACK_AUDIT_2026-05-13.md` §12 for the full status.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "platform"))

pytest.importorskip("fastapi")


# ── C-03: a stale constant standing in for a measured risk-free rate ─────────

def test_rate_lookup_never_substitutes_a_constant_by_default(monkeypatch):
    """The constants describe the late-2024 rate regime. Greeks computed from
    them are wrong in theta and rho, and look exactly like measured ones."""
    import gcp.database
    from lib import options_greeks as og

    og.get_rate_and_yield.cache_clear()

    def boom(sql, params=None):
        raise RuntimeError("cloud sql down")

    monkeypatch.setattr(gcp.database, "query_to_dataframe_strict", boom)
    with pytest.raises(og.RateLookupError):
        og.get_rate_and_yield(date(2026, 9, 4))


def test_greeks_enrichment_omits_columns_rather_than_using_a_fake_rate(monkeypatch):
    """An unavailable rate must leave the `*_computed` sidecar columns ABSENT.

    That is a state the caller can detect. Filling them from a 2024 constant
    was not.
    """
    from lib import options_greeks as og

    og.get_rate_and_yield.cache_clear()

    def boom(_d, **_kw):
        raise og.RateLookupError("no rate")

    monkeypatch.setattr(og, "get_rate_and_yield", boom)
    chain = pd.DataFrame([{
        "ticker": "SPX", "strike": 5000.0, "expiration": "2026-09-19",
        "type": "call", "last": 12.5, "bid": 12.0, "ask": 13.0,
    }])
    out = og.enrich_av_chain_with_greeks(chain, "SPX", date(2026, 9, 4))
    assert "delta_computed" not in out.columns, (
        "Greeks were computed despite no measured risk-free rate")


# ── The staleness guard that a swallow switched off ─────────────────────────

def test_trading_day_count_raises_rather_than_reporting_zero(monkeypatch):
    """`_trading_days_between` returned 0 when the NYSE calendar failed.

    Its only caller is `if biz_days > max_age_business_days: raise
    StaleSourceDataError`. 0 is never greater than the threshold, so the
    swallow silently DISABLED the guard and allowed a level map built off
    stale market_data_daily to be written -- the incident that guard exists
    to prevent.
    """
    import lib.strat_levels as sl

    class _BustedCalendar:
        def valid_days(self, start_date, end_date):
            raise RuntimeError("calendar data unavailable")

    monkeypatch.setattr(
        "pandas_market_calendars.get_calendar", lambda _n: _BustedCalendar())

    with pytest.raises(RuntimeError, match="Refusing to report 0 trading days"):
        sl._trading_days_between(
            pd.Timestamp("2026-08-01", tz="UTC"),
            pd.Timestamp("2026-09-04", tz="UTC"))


def test_trading_day_count_still_returns_zero_when_source_is_not_behind():
    """The legitimate zero is untouched: nothing is stale if nothing elapsed."""
    import lib.strat_levels as sl
    ts = pd.Timestamp("2026-09-04", tz="UTC")
    assert sl._trading_days_between(ts, ts) == 0


# ── A corrupt journal file that erased itself ───────────────────────────────

def test_unreadable_journal_file_is_an_error_not_an_empty_journal(tmp_path, monkeypatch):
    """`_load_local` returned [] for a corrupt file, and `_save_local` writes
    the returned list straight back -- so the next logged trade replaced a
    recoverable file with a one-entry list."""
    import api.routers.journal as journal
    from fastapi import HTTPException

    corrupt = tmp_path / "IWM.json"
    corrupt.write_text('[{"ticker": "IWM", "entry_pri')   # truncated write
    monkeypatch.setattr(journal, "_local_path", lambda t: corrupt)

    with pytest.raises(HTTPException) as ei:
        journal._load_local("IWM")
    assert ei.value.status_code == 500
    assert "NOT been overwritten" in ei.value.detail
    assert corrupt.read_text().startswith('[{"ticker"'), "the file was touched"


def test_missing_journal_file_is_still_an_empty_list(tmp_path, monkeypatch):
    """The legitimate empty: no file means no trades, not a failure."""
    import api.routers.journal as journal
    monkeypatch.setattr(journal, "_local_path", lambda t: tmp_path / "nope.json")
    assert journal._load_local("IWM") == []


def test_journal_file_holding_a_non_list_is_an_error(tmp_path, monkeypatch):
    """Valid JSON of the wrong shape would have been iterated as entries."""
    import api.routers.journal as journal
    from fastapi import HTTPException

    p = tmp_path / "IWM.json"
    p.write_text(json.dumps({"unexpected": "object"}))
    monkeypatch.setattr(journal, "_local_path", lambda t: p)
    with pytest.raises(HTTPException) as ei:
        journal._load_local("IWM")
    assert ei.value.status_code == 500
