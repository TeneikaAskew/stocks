"""The stage-one sites, and the baseline entries that stay beside them, written out.

FEAT-DATA-001, stage 1 of the market-time sweep: 71 places in 39 files where
deployed code took "today" from the container's clock (64 ``host-today``) or
from ``CURRENT_DATE`` (7 ``sql-utc-date``) now take it from
``lib.eastern_time`` (``market_today()``, ``market_today_sql()``).

The ratchet (``tests/meta/test_timezone_boundaries.py``) only knows that its
baseline may shrink. This file pins WHICH entries this stage removed and which
31 entries of the same 39 files it deliberately left for later stages
(instants, conversions, the bar readers), so a later edit cannot quietly widen
or narrow the stage:

* an entry added to one of the 39 files fails here even if the ratchet's
  baseline is regenerated to admit it;
* one of the 31 "fixed" in passing fails here until this list says so.

``STAGE_ONE`` and ``STAYS`` are the spec's Appendix A and Appendix B
(``docs/superpowers/specs/2026-11-14-feat-data-001-deployed-dates-exchange-clock.md``).
An identity is what the ratchet's scanner gives a site: ``<scope>::<call
text>``, or ``<scope>::fstr#<hash>`` / ``str#<hash>`` for a SQL statement. A
file can hold the same identity more than once (``main::date.today()`` three
times), so the lists are compared as multisets.
"""
from __future__ import annotations

import json
from collections import Counter

import pytest

from tests.meta import test_timezone_boundaries as ratchet

STAGE_ONE: dict[str, dict[str, list[str]]] = {
    "gcp/audit_job_runner.py": {
        "host-today": [
            'main::date.today()',
        ],
    },
    "gcp/backtest_job.py": {
        "host-today": [
            '_resolve_window::date.today()',
        ],
    },
    "gcp/build_options_daily_greeks.py": {
        "host-today": [
            'main::date.today()',
            'main::date.today()',
        ],
    },
    "gcp/build_realtime_gex.py": {
        "host-today": [
            'main::date.today()',
            'main::date.today()',
        ],
    },
    "gcp/discord_interactions/main.py": {
        "host-today": [
            'parse_date_arg::date.today()',
        ],
    },
    "gcp/earnings_long_watchlist.py": {
        "host-today": [
            'main::date.today()',
        ],
        "sql-utc-date": [
            '_query_watchlist::fstr#3c17358f2881',
        ],
    },
    "gcp/fetchers/backfill_daily_indicators.py": {
        "host-today": [
            '_filter_recent_rows::_date.today()',
        ],
        "sql-utc-date": [
            '_tickers_with_gaps::fstr#b950f2df4227',
        ],
    },
    "gcp/fetchers/build_options_daily_features.py": {
        "host-today": [
            'main::date.today()',
            'main::date.today()',
        ],
    },
    "gcp/fetchers/compute_earnings_reactions.py": {
        "host-today": [
            '_resolve_scope::_dt.now()',
        ],
    },
    "gcp/fetchers/fetch_av_historical_options.py": {
        "host-today": [
            '_resolve_start_from_latest::date.today()',
            '_resolve_start_from_latest::date.today()',
            'main::date.today()',
            'main::date.today()',
            'main::date.today()',
        ],
    },
    "gcp/fetchers/fetch_earnings_history.py": {
        "host-today": [
            '_resolve_scope::_dt.now()',
        ],
        "sql-utc-date": [
            '_earnings_calendar_tickers::fstr#266f9c5482ea',
        ],
    },
    "gcp/fetchers/fetch_economic_events.py": {
        "host-today": [
            'fetch_fred_releases::date.today()',
        ],
    },
    "gcp/fetchers/fetch_fred_rates.py": {
        "host-today": [
            'main::date.today()',
        ],
    },
    "gcp/fetchers/fetch_insider_transactions.py": {
        "host-today": [
            'fetch_for_ticker::pd.Timestamp.utcnow()',
        ],
        "sql-utc-date": [
            '_earnings_calendar_tickers::fstr#591204bc497c',
        ],
    },
    "gcp/fetchers/fetch_premarket_refresh.py": {
        "host-today": [
            'main::date.today()',
        ],
    },
    "gcp/fetchers/fetch_sec_filings.py": {
        "host-today": [
            'main::date.today()',
        ],
        "sql-utc-date": [
            '_earnings_calendar_tickers::fstr#591204bc497c',
        ],
    },
    "gcp/fetchers/fetch_top_movers.py": {
        "host-today": [
            'fetch_top_movers::date.today()',
        ],
    },
    "gcp/indicator_correlation_job.py": {
        "host-today": [
            'main::date.today()',
        ],
    },
    "gcp/refresh_earnings_views.py": {
        "host-today": [
            'refresh_daily::date.today()',
        ],
        "sql-utc-date": [
            'refresh_daily::fstr#e2ebe6247dcf',
        ],
    },
    "gcp/regime_combo_job.py": {
        "host-today": [
            'main::date.today()',
        ],
    },
    "gcp/research/strat_engine/strat_pred_serve.py": {
        "host-today": [
            'predict_one::pd.Timestamp.utcnow()',
        ],
    },
    "gcp/signal_monitor.py": {
        "host-today": [
            'SignalMonitor.fetch_latest_bar::datetime.now()',
        ],
    },
    "gcp/trade_logger.py": {
        "host-today": [
            'TradeLogger._daily_file::datetime.now()',
            'TradeLogger.get_daily_trades::datetime.now()',
            'TradeLogger.get_weekly_trades::datetime.now()',
            'TradeLogger.get_weekly_trades::datetime.now()',
            'TradeLogger.log_trade::datetime.now()',
        ],
    },
    "gcp/weekend_review.py": {
        "host-today": [
            'generate_weekly_review::datetime.now()',
        ],
    },
    "lib/agents/summarizers.py": {
        "host-today": [
            '_check_chain_freshness::date_type.today()',
            'summarize_gamma_levels::date_type.today()',
        ],
    },
    "lib/data_loader.py": {
        "host-today": [
            '_check_staleness::date.today()',
        ],
    },
    "lib/indicators.py": {
        "host-today": [
            'calculate_orb::datetime.today()',
        ],
    },
    "lib/strategies/calibration.py": {
        "host-today": [
            '_latest_calibration::date.today()',
        ],
    },
    "lib/strategies/exit_config_overrides.py": {
        "host-today": [
            '_latest_overrides::date.today()',
        ],
    },
    "lib/trading_analysis.py": {
        "host-today": [
            'MarketAnalyzer._calculate_orb::datetime.today()',
        ],
    },
    "platform/api/main.py": {
        "host-today": [
            'get_reference_levels::datetime.now()',
        ],
    },
    "platform/api/routers/catalysts.py": {
        "host-today": [
            'get_catalyst_events::datetime.now()',
            'get_catalyst_snapshot::_date.today()',
            'get_catalysts_for_ticker::datetime.now()',
        ],
    },
    "platform/api/routers/dashboard.py": {
        "host-today": [
            '_apply_live_overlay::datetime.now()',
        ],
    },
    "platform/api/routers/grid.py": {
        "host-today": [
            '_load_chain_for_live::date_type.today()',
            'get_grid_timeseries::date_type.today()',
        ],
    },
    "scripts/backtest_playability.py": {
        "host-today": [
            'compute_options_insights::datetime.now()',
        ],
    },
    "scripts/calibrate_thresholds.py": {
        "host-today": [
            '_parse_as_of::date.today()',
            'calibrate_ticker::date.today()',
            'fetch_bars::date.today()',
        ],
    },
    "scripts/fetch_catalyst_calendar.py": {
        "host-today": [
            'main::datetime.now()',
        ],
    },
    "scripts/fetch_earnings_calendar.py": {
        "host-today": [
            'EarningsCalendarFetcher.fetch_unusual_whales_earnings::datetime.now()',
            'EarningsCalendarFetcher.print_summary::datetime.now()',
            '_resolve_scope::datetime.now()',
            '_resolve_target_dates_for_av_options::datetime.now()',
            'main::datetime.now()',
            'main::datetime.now()',
            'main::datetime.now()',
            'main::datetime.now()',
            'main::datetime.now()',
        ],
    },
    "scripts/run_param_sweep.py": {
        "host-today": [
            'main::date.today()',
        ],
        "sql-utc-date": [
            'apply_winner::str#f9f26d5f0493',
        ],
    },
}

STAYS: dict[str, dict[str, list[str]]] = {
    "gcp/audit_job_runner.py": {
        "host-today": [
            'main::datetime.now()',
        ],
    },
    "gcp/build_realtime_gex.py": {
        "host-today": [
            'compute_realtime_frame::pd.Timestamp.utcnow()',
            'compute_realtime_frame::pd.Timestamp.utcnow()',
        ],
        "utc-parse": [
            "_load_intraday_spots::pd.to_datetime(df['ts'], utc=True)",
            "_load_realtime_chain::pd.to_datetime(df['ts'], utc=True)",
        ],
    },
    "gcp/fetchers/backfill_daily_indicators.py": {
        "sql-utc-date": [
            '<module>::str#60fba3841c30',
        ],
    },
    "gcp/research/strat_engine/strat_pred_serve.py": {
        "utc-parse": [
            'predict_one::pd.to_datetime(as_of, utc=True)',
            "predict_one::pd.to_datetime(df['ts'], utc=True)",
            "predict_one::pd.to_datetime(latest['ts'].iloc[0], utc=True)",
        ],
    },
    "gcp/signal_monitor.py": {
        "host-today": [
            'SignalMonitor._check_exits::datetime.now()',
            'SignalMonitor._evaluate_strategies_for_bar::datetime.now()',
            'SignalMonitor.fire_alert::datetime.utcnow()',
        ],
        "tz-localize-none": [
            'SignalMonitor._bound_daily_frame::df.index.tz_localize(None)',
            'SignalMonitor._bound_daily_frame::idx.dt.tz_localize(None)',
            'SignalMonitor._corrected_rvol::self._now(_ET).replace(second=0, microsecond=0, tzinfo=None)',
            'SignalMonitor._corrected_rvol::times.dt.tz_convert(_ET).dt.tz_localize(None)',
            "SignalMonitor._corrected_rvol::times.dt.tz_localize('UTC').dt.tz_convert(_ET).dt.tz_localize(None)",
            'SignalMonitor._now::ts.replace(tzinfo=None)',
        ],
    },
    "lib/data_loader.py": {
        "tz-localize-none": [
            'DataLoader._strip_timezone::df.index.tz_localize(None)',
            "DataLoader._strip_timezone::df['Time'].dt.tz_localize(None)",
        ],
    },
    "lib/trading_analysis.py": {
        "host-today": [
            'MarketAnalyzer._archive_file::datetime.now()',
        ],
    },
    "platform/api/main.py": {
        "tz-localize-none": [
            '_reference_from_gcs_local_dev::df.index.tz_localize(None)',
            'get_market_data::df.index.tz_localize(None)',
        ],
    },
    "platform/api/routers/catalysts.py": {
        "sql-utc-date": [
            '_news_sql::str#b68870b10be5',
        ],
    },
    "platform/api/routers/dashboard.py": {
        "tz-localize-none": [
            '_build_movement_level_map::ts_col.dt.tz_localize(None)',
        ],
    },
    "scripts/fetch_catalyst_calendar.py": {
        "host-today": [
            '_save_catalysts_locked::datetime.now()',
        ],
    },
    "scripts/fetch_earnings_calendar.py": {
        "host-today": [
            'EarningsCalendarFetcher.fetch_unusual_whales_earnings::datetime.now()',
            '_fetch_yahoo_bulk::datetime.now()',
            '_fetch_yahoo_one::datetime.now()',
            '_fetch_yahoo_one::datetime.now()',
            'fetch_alphavantage_earnings::datetime.now()',
        ],
    },
}

#: The existing test files this stage edited because they stubbed a module's
#: clock, or took their expectation from the host's date, for a changed site.
#: CI runs in UTC: from 00:00 to 05:00 UTC the host's date is a day ahead of
#: the exchange's, so a test here that still read the host clock would fail by
#: the hour it ran at.
TESTS_THAT_READ_THE_EXCHANGE_DATE: tuple[str, ...] = (
    "tests/agents/test_agent_summarizers.py",
    "tests/api/test_grid_router.py",
    "tests/gcp/test_backfill_daily_indicators.py",
    "tests/gcp/test_earnings_long_watchlist_freshness.py",
    "tests/gcp/test_earnings_long_watchlist_sources.py",
    "tests/gcp/test_ew_fetcher_reader_retirement.py",
    "tests/gcp/test_fetch_av_historical_options.py",
    "tests/gcp/test_refresh_earnings_views_sources.py",
    "tests/gcp/test_trade_logger_reads.py",
    "tests/integration/test_earnings_daily_path_persistence.py",
    "tests/integration/test_param_sweep_persistence.py",
    "tests/lib/test_signals_per_ticker_overrides.py",
    "tests/lib/test_strategies_calibration.py",
    "tests/scripts/test_calibrate_thresholds.py",
)


def _flat(data: dict[str, dict[str, list[str]]]) -> Counter:
    return Counter(
        (path, rule, identity)
        for path, rules in data.items()
        for rule, identities in rules.items()
        for identity in identities
    )


def _count(data: dict[str, dict[str, list[str]]], rule: str) -> int:
    return sum(len(rules.get(rule, [])) for rules in data.values())


def test_the_lists_are_the_spec_s():
    assert sum(_flat(STAGE_ONE).values()) == 71
    assert len(STAGE_ONE) == 39
    assert _count(STAGE_ONE, "host-today") == 64
    assert _count(STAGE_ONE, "sql-utc-date") == 7
    assert {rule for rules in STAGE_ONE.values() for rule in rules} == {"host-today", "sql-utc-date"}

    assert sum(_flat(STAYS).values()) == 31
    assert len(STAYS) == 12
    assert set(STAYS) <= set(STAGE_ONE)

    # One identity is on both lists, once each: the function holds a date read
    # (stage 1) and a fetched_at stamp (an instant, a later stage) with the same call text.
    assert dict(_flat(STAGE_ONE) & _flat(STAYS)) == {(
        "scripts/fetch_earnings_calendar.py", "host-today",
        "EarningsCalendarFetcher.fetch_unusual_whales_earnings::datetime.now()",
    ): 1}


def test_the_baseline_of_the_39_files_is_exactly_the_31():
    """None of the 71 is in the baseline, and each of the 31 still is."""
    baseline = json.loads(ratchet.BASELINE.read_text(encoding="utf-8"))
    held = Counter(
        (path, rule, identity)
        for path in STAGE_ONE
        for rule, identities in baseline.get(path, {}).items()
        for identity in identities
    )
    want = _flat(STAYS)
    left_over = sorted((held - want).elements())
    missing = sorted((want - held).elements())
    assert not left_over and not missing, (
        "The ratchet baseline of the 39 stage-one files is not the 31 entries that stay.\n"
        f"In the baseline and not on the list ({len(left_over)}):\n  "
        + "\n  ".join(map(str, left_over))
        + f"\nOn the list and not in the baseline ({len(missing)}):\n  "
        + "\n  ".join(map(str, missing))
    )


def test_the_code_of_the_39_files_holds_exactly_the_31():
    """The same statement about the code itself, so it does not rest on the baseline file."""
    held = Counter(
        (path, rule, identity)
        for path in STAGE_ONE
        for rule, _line, identity in ratchet._scan(ratchet.REPO / path)
    )
    assert held == _flat(STAYS)


@pytest.mark.parametrize("path", TESTS_THAT_READ_THE_EXCHANGE_DATE)
def test_the_edited_tests_do_not_read_the_host_clock(path):
    hits = [(line, identity) for rule, line, identity in ratchet._scan(ratchet.REPO / path)
            if rule == "host-today"]
    assert hits == [], f"{path} reads the host clock: use lib.eastern_time (market_today, utc_now)"


def test_the_host_clock_check_sees_a_read_in_a_test_file(tmp_path, monkeypatch):
    """The check above cannot pass because the scanner is blind to test code."""
    monkeypatch.setattr(ratchet, "REPO", tmp_path)  # the scanner names a site by its path under REPO
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "from datetime import date\n\n\ndef test_x():\n    assert date.today()\n", encoding="utf-8")
    assert [rule for rule, _line, _identity in ratchet._scan(probe)] == ["host-today"]
