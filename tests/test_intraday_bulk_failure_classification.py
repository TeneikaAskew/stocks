"""Tests for the typed-failure handling in
gcp/fetchers/fetch_alphavantage_intraday.py.

These pin three contracts that together prevent the regression seen on
2026-05-22 → 2026-05-23, when intraday-bulk-backfill execution `s2fpq`
crashed all 8 tasks because a handful of delisted tickers (YSS et al.)
were treated as task-fatal `sys.exit(1)` failures, producing 8 spurious
gcp-job-failure issues over 6 days.

  1. ``fetch_month`` now returns ``(df, reason)`` — every code path
     produces a reason string distinct from the dataframe, so the
     caller can categorise WHY the fetch returned None.

  2. ``process_symbol`` returns one of the ``OUTCOME_*`` constants.
     A symbol whose entire month-range returns only permanently-broken
     reasons (Invalid API call / no timeseries / generic info)
     classifies as ``OUTCOME_DEAD`` and is NOT a systemic failure.
     A symbol with at least one transient (rate_limit / request_error)
     month doesn't get the dead-ticker badge — re-runs get another shot.

  3. ``main()`` only ``sys.exit(1)``s on SYSTEMIC failures (process_symbol
     raised). Dead tickers log at WARNING and the task exits 0 — that's
     the load-bearing change that stops the 8-issue cascade.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gcp.fetchers.fetch_alphavantage_intraday as fai


# ── 1. fetch_month returns (df, reason) ──────────────────────────────


def _mock_resp(json_payload: dict):
    """Build a requests.Response-shaped mock."""
    r = MagicMock()
    r.json.return_value = json_payload
    r.raise_for_status.return_value = None
    return r


def test_fetch_month_returns_invalid_api_call_reason():
    """The dead-ticker case: AV "Error Message" payload returns
    (None, FETCH_INVALID_API). Without this distinct reason, the
    outer loop can't tell "delisted ticker" from "rate limit hit"."""
    with patch.object(fai.requests, 'get',
                      return_value=_mock_resp({'Error Message': 'Invalid API call'})):
        df, reason = fai.fetch_month('XXXX', 2025, 1, 'fake_key')
    assert df is None
    assert reason == fai.FETCH_INVALID_API


def test_fetch_month_returns_rate_limit_reason():
    """AV "Note" → FETCH_RATE_LIMIT. This is a TRANSIENT reason so a
    ticker with only this reason must NOT be classified as dead."""
    with patch.object(fai.requests, 'get',
                      return_value=_mock_resp({'Note': 'Thank you for using AlphaVantage'})):
        df, reason = fai.fetch_month('SPY', 2025, 1, 'fake_key')
    assert df is None
    assert reason == fai.FETCH_RATE_LIMIT


def test_fetch_month_returns_request_error_on_network_failure():
    """Network exception → FETCH_REQUEST_ERROR (transient)."""
    with patch.object(fai.requests, 'get', side_effect=ConnectionError('boom')):
        df, reason = fai.fetch_month('SPY', 2025, 1, 'fake_key')
    assert df is None
    assert reason == fai.FETCH_REQUEST_ERROR


def test_fetch_month_returns_success_with_valid_payload():
    """Happy path: real time-series payload → (df, FETCH_OK)."""
    payload = {
        'Time Series (1min)': {
            '2025-01-02 09:30:00': {
                '1. open': '100.0', '2. high': '101.0',
                '3. low': '99.5', '4. close': '100.5', '5. volume': '5000',
            }
        }
    }
    with patch.object(fai.requests, 'get', return_value=_mock_resp(payload)):
        df, reason = fai.fetch_month('SPY', 2025, 1, 'fake_key')
    assert reason == fai.FETCH_OK
    assert df is not None and not df.empty
    assert df.iloc[0]['ticker'] == 'SPY'


# ── 2. process_symbol classifies dead vs transient ────────────────────


def _patch_process_symbol_internals(monkeypatch, fetch_returns):
    """Stub out everything heavy in process_symbol so we can drive the
    outcome from the fetch_month return values. ``fetch_returns`` is
    an iterable of (df, reason) tuples — one per (year, month)."""
    iterator = iter(fetch_returns)
    monkeypatch.setattr(fai, 'fetch_month',
                        lambda *a, **kw: next(iterator))
    # Always-False skip check so we exercise the fetch loop.
    monkeypatch.setattr(fai, '_ticker_already_backfilled',
                        lambda symbol: False)
    # Single (year, month) gives us one fetch_month call per element
    # in fetch_returns — caller controls range by passing N tuples.
    monkeypatch.setattr(fai, 'get_trading_months',
                        lambda s, e: [(2025, m + 1) for m in range(len(fetch_returns))])
    # Skip the DB write — irrelevant for outcome classification.
    monkeypatch.setattr(fai, 'is_cloud_sql_configured', lambda: False)
    # Avoid real sleeps in the rate limiter.
    monkeypatch.setattr(fai.time, 'sleep', lambda x: None)


def test_process_symbol_returns_dead_when_all_months_invalid_api(monkeypatch):
    """All 3 months returned "Invalid API call" → OUTCOME_DEAD. This is
    the YSS-style delisted-ticker case that crashed `s2fpq` 8 times."""
    _patch_process_symbol_internals(monkeypatch, [
        (None, fai.FETCH_INVALID_API),
        (None, fai.FETCH_INVALID_API),
        (None, fai.FETCH_INVALID_API),
    ])
    outcome = fai.process_symbol('YSS', '2025-01-01', '2025-03-01',
                                 ['fake_key'], force=False)
    assert outcome == fai.OUTCOME_DEAD


def test_process_symbol_does_not_classify_dead_when_any_transient(monkeypatch):
    """If even ONE month returned a transient reason (rate_limit), the
    ticker is NOT dead — we don't know the live answer for that month.
    A re-run should get another shot. Critical so we don't auto-prune
    legit tickers that hit a temporary AV outage."""
    _patch_process_symbol_internals(monkeypatch, [
        (None, fai.FETCH_INVALID_API),
        (None, fai.FETCH_RATE_LIMIT),   # one transient
        (None, fai.FETCH_INVALID_API),
    ])
    outcome = fai.process_symbol('AMBIG', '2025-01-01', '2025-03-01',
                                 ['fake_key'], force=False)
    assert outcome == fai.OUTCOME_OK, (
        'transient mid-stream should not mark a ticker as dead; '
        'a re-run gets another shot at the transient month'
    )


def test_process_symbol_returns_ok_on_any_success(monkeypatch):
    """One real month of data → OUTCOME_OK regardless of other failures."""
    df = pd.DataFrame({
        'ts': [pd.Timestamp('2025-01-02 09:30', tz='UTC')],
        'open': [100.0], 'high': [101.0], 'low': [99.5],
        'close': [100.5], 'volume': [5000],
        'ticker': ['SPY'], 'interval': ['1min'], 'data_source': ['alphavantage'],
    })
    _patch_process_symbol_internals(monkeypatch, [
        (None, fai.FETCH_INVALID_API),  # one bad month
        (df, fai.FETCH_OK),             # one good month
    ])
    outcome = fai.process_symbol('SPY', '2025-01-01', '2025-02-01',
                                 ['fake_key'], force=False)
    assert outcome == fai.OUTCOME_OK


def test_process_symbol_skipped_returns_skipped(monkeypatch):
    """Already-backfilled ticker returns OUTCOME_SKIPPED (not OK, not
    a failure — the outer loop counts it as succeeded)."""
    monkeypatch.setattr(fai, '_ticker_already_backfilled',
                        lambda symbol: True)
    outcome = fai.process_symbol('SPY', '2025-01-01', '2025-02-01',
                                 ['fake_key'], force=False)
    assert outcome == fai.OUTCOME_SKIPPED


# ── 3. main() exit semantics — the load-bearing change ───────────────


def _patch_main(monkeypatch, process_returns):
    """Stub out enough of main() to drive it with predetermined
    process_symbol outcomes. process_returns is a dict
    {symbol: outcome_string OR Exception_instance}."""
    monkeypatch.setattr(fai, 'get_api_keys', lambda: ['fake'])
    monkeypatch.setattr(fai, 'is_cloud_sql_configured', lambda: False)
    monkeypatch.setattr(fai.os, 'environ', {})

    def fake_process(symbol, *a, **kw):
        r = process_returns[symbol]
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(fai, 'process_symbol', fake_process)

    # Use a symbol set covering each outcome family.
    monkeypatch.setattr(sys, 'argv',
                        ['fai', '--symbol', ','.join(process_returns.keys()),
                         '--start-date', '2025-01-01',
                         '--end-date', '2025-02-01'])


def test_main_exits_0_when_only_dead_tickers(monkeypatch):
    """REGRESSION: the bug that produced 8 spurious gcp-job-failure
    issues in 6 days. A task with ONLY dead-ticker failures must NOT
    sys.exit(1). It logs WARNING + exits 0 so the auto-issue creator
    doesn't fire."""
    _patch_main(monkeypatch, {
        'SPY': fai.OUTCOME_OK,
        'YSS': fai.OUTCOME_DEAD,
        'XXX': fai.OUTCOME_DEAD,
    })
    # main() returns None (no exit) on success; sys.exit(1) raises SystemExit
    fai.main()  # should NOT raise


def test_main_exits_1_on_any_systemic(monkeypatch):
    """A task with a SYSTEMIC failure (process_symbol raised) MUST
    sys.exit(1) so the operator is paged. Dead tickers and OK tickers
    in the same run don't change this."""
    _patch_main(monkeypatch, {
        'SPY': fai.OUTCOME_OK,
        'YSS': fai.OUTCOME_DEAD,
        'BUG': RuntimeError('upsert_dataframe failed'),
    })
    with pytest.raises(SystemExit) as exc:
        fai.main()
    assert exc.value.code == 1


def test_main_exits_0_when_all_succeed(monkeypatch):
    """Sanity: clean run exits cleanly."""
    _patch_main(monkeypatch, {
        'SPY': fai.OUTCOME_OK,
        'IWM': fai.OUTCOME_OK,
        'QQQ': fai.OUTCOME_SKIPPED,
    })
    fai.main()  # should NOT raise


def test_dead_ticker_reasons_set_includes_invalid_api():
    """AST/value guard: the _DEAD_TICKER_REASONS set must contain the
    permanently-broken reasons. A future refactor that removes
    FETCH_INVALID_API from this set would re-introduce the original
    bug where dead tickers crash the task."""
    assert fai.FETCH_INVALID_API in fai._DEAD_TICKER_REASONS
    assert fai.FETCH_INFO_MSG in fai._DEAD_TICKER_REASONS
    assert fai.FETCH_NO_TIMESERIES in fai._DEAD_TICKER_REASONS
    # And TRANSIENT reasons must NOT be in the dead set
    assert fai.FETCH_RATE_LIMIT not in fai._DEAD_TICKER_REASONS
    assert fai.FETCH_REQUEST_ERROR not in fai._DEAD_TICKER_REASONS
