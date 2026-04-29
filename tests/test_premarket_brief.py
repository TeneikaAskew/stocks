"""Unit tests for `gcp/premarket_brief.py::load_earnings_for_brief`.

The brief drives the morning Discord post. Its correctness invariants:
    - Tier ranking 1-6 by source-set (AV+UW+EW=1, AV-only=6)
    - Top-N cap applied AFTER tier+market-cap sort (not alphabetical)
    - top_n=0 disables the cap (legacy unbounded mode)
    - Multi-source rows collapse to one entry per (ticker, date)
    - SP500 truthy sorts ahead of False/None
    - market_cap NULL from one source doesn't outrank a real value
      from another source for the same (ticker, date)
    - Weekly mode: Sunday → next Mon-Fri date math
    - No Cloud SQL → empty result, no crash

All tests monkeypatch `gcp.database.query_to_dataframe` so no live DB.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


@pytest.fixture
def mock_cloud_sql(monkeypatch):
    """Force Cloud SQL "configured" and capture the SQL/params handed to
    `query_to_dataframe`. Returns a setter that lets each test feed in
    a different DataFrame."""
    from gcp import database
    from gcp import premarket_brief as pb

    captured = {"sql": None, "params": None}

    def install(df: pd.DataFrame):
        def fake_query(sql, params=None):
            captured["sql"] = sql
            captured["params"] = dict(params or {})
            return df.copy() if df is not None else pd.DataFrame()

        monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
        monkeypatch.setattr(database, "query_to_dataframe", fake_query)
        # Re-bind the import inside premarket_brief too — the fn does
        # `from gcp.database import ...` at call time, so module-level
        # patches on `gcp.database` are sufficient. (No second patch
        # needed.)

    return install, captured


# ──────────────────────────────────────────────────────────────────────
# Empty / no Cloud SQL paths
# ──────────────────────────────────────────────────────────────────────


def test_returns_empty_when_cloud_sql_not_configured(monkeypatch):
    """Brief degrades gracefully — empty earnings, no crash."""
    from gcp import database
    from gcp.premarket_brief import load_earnings_for_brief

    monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: False)
    result = load_earnings_for_brief(date(2026, 4, 27))
    assert result == {"mode": "daily", "earnings": []}


def test_returns_empty_envelope_when_query_returns_no_rows(mock_cloud_sql):
    """Empty result still returns the envelope (mode/start/end/earnings)
    so callers can render an "no earnings today" embed."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame())
    from gcp.premarket_brief import load_earnings_for_brief

    today = date(2026, 4, 27)
    result = load_earnings_for_brief(today)
    assert result["mode"] == "daily"
    assert result["earnings"] == []
    assert result["start"] == today
    assert result["end"] == today


# ──────────────────────────────────────────────────────────────────────
# Tier ranking — the load-bearing logic
# ──────────────────────────────────────────────────────────────────────


def _row(ticker, source, **kw):
    """Build a one-row earnings_calendar dict matching the SELECT shape."""
    base = {
        "ticker": ticker,
        "earnings_date": date(2026, 4, 27),
        "company_name": ticker + " Inc",
        "earnings_time": "BMO",
        "eps_estimate": 1.0,
        "expected_move": 5.0,
        "sector": "Tech",
        "market_cap": 1_000_000_000,
        "is_s_p_500": False,
        "stock_volume": 1_000_000,
        "options_volume": 50_000,
        "open_interest": 100_000,
        "rv_1d_last_12q": None,
        "strategy": None,
        "strike": None,
        "premium": None,
        "score": None,
        "data_source": source,
    }
    base.update(kw)
    return base


def test_tier_1_when_all_three_sources_agree(mock_cloud_sql):
    """AV + UW + EW → tier 1 (top confirmed)."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([
        _row("AAPL", "alphavantage"),
        _row("AAPL", "unusual_whales"),
        _row("AAPL", "earnings_whispers", strategy="straddle", strike=180.0,
             premium=2.5, score=8),
    ]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    assert len(result["earnings"]) == 1
    e = result["earnings"][0]
    assert e["tier"] == 1
    assert sorted(e["sources"]) == [
        "alphavantage", "earnings_whispers", "unusual_whales"
    ]
    # EW row wins for display (carries strategy)
    assert e["strategy"] == "straddle"
    assert e["strike"] == 180.0


def test_tier_6_av_only_long_tail(mock_cloud_sql):
    """AlphaVantage-only rows are tier 6 — long-tail small caps."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([
        _row("XYZ", "alphavantage"),
    ]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    assert result["earnings"][0]["tier"] == 6


def test_tier_2_av_plus_uw_no_strategy(mock_cloud_sql):
    """AV + UW (no EW) → tier 2."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([
        _row("MSFT", "alphavantage"),
        _row("MSFT", "unusual_whales"),
    ]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    assert result["earnings"][0]["tier"] == 2


# ──────────────────────────────────────────────────────────────────────
# top_n cap — applied AFTER tier+market-cap sort
# ──────────────────────────────────────────────────────────────────────


def test_top_n_keeps_highest_tier_first(mock_cloud_sql):
    """Cap of 2 + 5 input tickers across tiers 1-6 → keep the two
    top-tier names. Verifies the cap is post-sort, not alphabetical."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([
        # Alphabetical order would put A first; tier order should beat it.
        _row("ZULU", "alphavantage"),
        _row("ZULU", "unusual_whales"),
        _row("ZULU", "earnings_whispers"),  # tier 1
        _row("ALPHA", "alphavantage"),       # tier 6
        _row("BRAVO", "alphavantage"),
        _row("BRAVO", "unusual_whales"),     # tier 2
    ]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27), top_n=2)
    tickers = [e["ticker"] for e in result["earnings"]]
    assert tickers == ["ZULU", "BRAVO"], (
        "top_n must keep tier-1/tier-2 names ahead of alphabetical tier-6"
    )


def test_top_n_zero_returns_all_rows(mock_cloud_sql):
    """top_n=0 disables the cap (legacy unbounded behaviour for the
    weekly digest where we want everything)."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([_row(f"T{i}", "alphavantage") for i in range(50)]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27), top_n=0)
    assert len(result["earnings"]) == 50


def test_default_top_n_is_25(mock_cloud_sql):
    """Default top_n=25 mirrors `fetch_market_data --max-earnings-tickers`
    so the brief and the daily fetcher prioritise the same names."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([_row(f"T{i:03d}", "alphavantage") for i in range(40)]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    assert len(result["earnings"]) == 25


# ──────────────────────────────────────────────────────────────────────
# _max_non_null — multi-row coalescing
# ──────────────────────────────────────────────────────────────────────


def test_market_cap_coalesces_across_sources(mock_cloud_sql):
    """UW row has market_cap=NULL; AV row has the real value. The merged
    entry must use the real value, not the NULL."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([
        _row("NVDA", "unusual_whales", market_cap=None),
        _row("NVDA", "alphavantage", market_cap=2_500_000_000_000),
    ]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    assert result["earnings"][0]["market_cap"] == 2_500_000_000_000


def test_sp500_truthy_in_any_row_wins(mock_cloud_sql):
    """is_s_p_500 may be False on UW but True on AV. The merged entry
    sorts as if SP500 — so an AV-confirmed SP500 doesn't lose to a
    UW row that omitted the flag."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([
        _row("AAPL", "unusual_whales", is_s_p_500=False),
        _row("AAPL", "alphavantage", is_s_p_500=True),
    ]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    assert result["earnings"][0]["is_s_p_500"] is True


# ──────────────────────────────────────────────────────────────────────
# Weekly mode — Sunday → next Mon-Fri
# ──────────────────────────────────────────────────────────────────────


def test_weekly_mode_starts_next_monday(mock_cloud_sql):
    """Sunday 2026-04-26 → start Mon 2026-04-27, end Fri 2026-05-01."""
    install, captured = mock_cloud_sql
    install(pd.DataFrame())
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 26), weekly=True)
    assert result["mode"] == "weekly"
    # Sunday weekday=6 → days_until_monday = (7-6)%7 || 7 = 1
    assert captured["params"]["start"] == date(2026, 4, 27)
    assert captured["params"]["end"] == date(2026, 5, 1)


def test_weekly_mode_on_thursday_jumps_to_next_week(mock_cloud_sql):
    """Thursday weekday=3 → days_until_monday = (7-3)%7 = 4 → Mon next week."""
    install, captured = mock_cloud_sql
    install(pd.DataFrame())
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 23), weekly=True)
    assert captured["params"]["start"] == date(2026, 4, 27)
    assert captured["params"]["end"] == date(2026, 5, 1)


# ──────────────────────────────────────────────────────────────────────
# Daily mode — start == end
# ──────────────────────────────────────────────────────────────────────


def test_daily_mode_query_uses_today(mock_cloud_sql):
    install, captured = mock_cloud_sql
    install(pd.DataFrame())
    from gcp.premarket_brief import load_earnings_for_brief

    today = date(2026, 4, 27)
    result = load_earnings_for_brief(today)
    assert result["mode"] == "daily"
    assert captured["params"]["start"] == today
    assert captured["params"]["end"] == today


# ── Catalyst-aware ORB selection (v2 strat refactor) ─────────────────────────


class TestSelectOrbWindow:
    def test_no_high_impact_returns_5m(self):
        from gcp.premarket_brief import select_orb_window
        result = select_orb_window([
            {'time': '08:30', 'name': 'PMI', 'importance': 'medium'},
        ])
        assert result['window'] == '5m'

    def test_830_high_impact_returns_15m(self):
        from gcp.premarket_brief import select_orb_window
        result = select_orb_window([
            {'time': '08:30', 'name': 'NFP', 'importance': 'high'},
        ])
        assert result['window'] == '15m'
        assert 'NFP' in result['reason']

    def test_1000_high_impact_returns_30m(self):
        from gcp.premarket_brief import select_orb_window
        result = select_orb_window([
            {'time': '10:00', 'name': 'ISM', 'importance': 'high'},
        ])
        assert result['window'] == '30m'
        assert 'ISM' in result['reason']

    def test_empty_events_returns_5m(self):
        from gcp.premarket_brief import select_orb_window
        result = select_orb_window([])
        assert result['window'] == '5m'

    def test_high_impact_at_other_time_returns_5m(self):
        from gcp.premarket_brief import select_orb_window
        result = select_orb_window([
            {'time': '14:00', 'name': 'FOMC', 'importance': 'high'},
        ])
        assert result['window'] == '5m'


class TestPlaybookEmbed:
    def test_skips_when_no_playbook(self):
        from gcp.premarket_brief import _build_playbook_embed
        brief = {
            'tickers': {
                'IWM': {'price': 215.42},
            },
            'recommended_orb_window': '5m',
            'recommended_orb_reason': 'No catalyst',
        }
        embed = _build_playbook_embed(brief)
        assert embed['fields'] == []

    def test_renders_when_playbook_present(self):
        from gcp.premarket_brief import _build_playbook_embed
        brief = {
            'tickers': {
                'IWM': {
                    'price': 215.42,
                    'playbook': 'IWM 215.42 — Daily 2U\nCALLS above 215.85 (PDH)',
                },
            },
            'recommended_orb_window': '15m',
            'recommended_orb_reason': '15-min ORB recommended (08:30 NFP)',
        }
        embed = _build_playbook_embed(brief)
        assert 'Strat Playbook' in embed['title']
        assert '15m' in embed['title']
        assert len(embed['fields']) == 1
        assert 'CALLS above' in embed['fields'][0]['value']

    def test_orb_explanation_appears_in_description(self):
        """LLM-generated ORB explanation appended to embed description."""
        from gcp.premarket_brief import _build_playbook_embed
        brief = {
            'tickers': {
                'IWM': {'playbook': 'IWM\nCALLS above 215.85 (PDH)'},
            },
            'recommended_orb_window': '5m',
            'recommended_orb_reason': '5-min ORB selected',
            'llm_orb_explanation': '5m is the baseline scalp window when '
                                   'no high-impact event before 10:00 AM. '
                                   '15m/30m alternatives still valid for swing.',
        }
        embed = _build_playbook_embed(brief)
        assert '5-min ORB selected' in embed['description']
        assert 'baseline scalp window' in embed['description']
        # Brain emoji marker so the explanation is visually distinct
        assert '\U0001F9E0' in embed['description']

    def test_per_ticker_playbook_explanation_field(self):
        """LLM 'Why this trigger' field rendered after each ticker's playbook."""
        from gcp.premarket_brief import _build_playbook_embed
        brief = {
            'tickers': {
                'IWM': {
                    'playbook': 'IWM\nCALLS above 215.85 (PDH)',
                    'llm_playbook': 'CDO chosen because pre-market sits at open.',
                },
            },
            'recommended_orb_window': '5m',
        }
        embed = _build_playbook_embed(brief)
        # Two fields: the playbook code-block + the explanation
        assert len(embed['fields']) == 2
        explain_field = next(f for f in embed['fields'] if 'Why this trigger' in f['name'])
        assert 'CDO chosen' in explain_field['value']
        assert explain_field['inline'] is False

    def test_playbook_explanation_omitted_when_blank(self):
        """No explanation field when llm_playbook missing."""
        from gcp.premarket_brief import _build_playbook_embed
        brief = {
            'tickers': {'IWM': {'playbook': 'IWM\nCALLS above 215.85 (PDH)'}},
            'recommended_orb_window': '5m',
        }
        embed = _build_playbook_embed(brief)
        assert len(embed['fields']) == 1
        assert all('Why this trigger' not in f['name'] for f in embed['fields'])


class TestTickerFieldsLayout:
    """Field-pair splits + LLM analysis slot for the ticker analysis embed."""

    def _ticker_data(self, **overrides):
        base = {
            'price': 215.42, 'change_pct': 1.2,
            'rsi': 72, 'rsi_direction': 'up',
            'stoch_k': 99, 'stoch_d': 99,
            'macd_cross': 'Bullish',
            'consecutive_up': 2, 'consecutive_down': 0,
            'signal_status': 'PUT setup (4/5)',
            'prev_day_high': 278.13, 'prev_day_low': 274.23,
            'sma200': 244.59,
            'bb_upper': 269.49, 'bb_lower': 234.88,
            'ema9': 261.14, 'ema20': 256.36,
            'atr14': 6.06,
            'strat_candle': '2U', 'strat_combo': '132_bull_continuation',
            'strat_setup': False,
            'ftfc_score': 1.0, 'ftfc_direction': 'bullish',
            'ftfc_labels': {'1d': '2U', '1w': '2U', '1mo': '2U'},
        }
        base.update(overrides)
        return base

    def test_prev_h_and_prev_l_on_separate_lines(self):
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data()}}
        fields = _build_ticker_fields(brief)
        levels_value = next(f['value'] for f in fields if f['name'] == 'IWM Levels')
        # Each on its own line — the old combined "Prev H/L" form is gone
        assert 'Prev H: $278.13' in levels_value
        assert 'Prev L: $274.23' in levels_value
        assert 'Prev H/L:' not in levels_value

    def test_ema9_and_ema20_on_separate_lines(self):
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data()}}
        fields = _build_ticker_fields(brief)
        levels_value = next(f['value'] for f in fields if f['name'] == 'IWM Levels')
        assert 'EMA9: $261.14' in levels_value
        assert 'EMA20: $256.36' in levels_value
        assert 'EMA 9/20:' not in levels_value

    def test_rsi_and_stoch_on_separate_lines(self):
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data()}}
        fields = _build_ticker_fields(brief)
        mom_value = next(f['value'] for f in fields if f['name'] == 'IWM Momentum')
        # Two distinct lines now, not the old "RSI: X | StochRSI: Y" mash-up
        rsi_lines = [ln for ln in mom_value.split('\n') if ln.startswith('RSI:')]
        stoch_lines = [ln for ln in mom_value.split('\n') if ln.startswith('StochRSI:')]
        assert len(rsi_lines) == 1
        assert len(stoch_lines) == 1
        assert '|' not in rsi_lines[0]  # no inline pipe-separated value any more

    def test_three_inline_fields_per_ticker_when_no_llm_analysis(self):
        """With no llm_analysis the embed keeps the legacy 3-field layout."""
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data()}}
        fields = _build_ticker_fields(brief)
        assert len(fields) == 3
        assert all(f['inline'] for f in fields)

    def test_llm_analysis_appends_full_width_field(self):
        """When llm_analysis is set, a 4th non-inline field renders below."""
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data(
            llm_analysis='IWM sits 13% above SMA200; longs favored on pullback.',
        )}}
        fields = _build_ticker_fields(brief)
        assert len(fields) == 4
        explain = fields[3]
        assert 'IWM Analysis' in explain['name']
        assert explain['inline'] is False
        assert 'longs favored' in explain['value']

    def test_two_tickers_each_get_their_own_explanation_block(self):
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {
            'IWM': self._ticker_data(llm_analysis='IWM analysis text.'),
            'SPY': self._ticker_data(llm_analysis='SPY analysis text.'),
        }}
        fields = _build_ticker_fields(brief)
        # 4 fields per ticker × 2 = 8 total
        assert len(fields) == 8
        # Each analysis field follows its ticker's 3 inline columns
        assert fields[0]['name'] == 'IWM Levels'
        assert fields[3]['name'].endswith('IWM Analysis')
        assert fields[4]['name'] == 'SPY Levels'
        assert fields[7]['name'].endswith('SPY Analysis')


class TestOverviewEmbedSetupExplanation:
    """LLM 'Today's setup' line lands under the FTFC summary."""

    def test_setup_explanation_renders_under_ftfc(self):
        from gcp.premarket_brief import _build_overview_embed
        brief = {
            'date': 'Tue Apr 28, 2026',
            'tickers': {
                'IWM': {'price': 215, 'change_pct': 1.0, 'rsi': 72,
                        'ftfc_direction': 'bullish', 'ftfc_score': 1.0,
                        'vol_regime': 'Normal'},
            },
            'llm_overview': "All names print +1.0 FTFC bullish — every "
                            "timeframe agrees. Trend-continuation favored.",
        }
        embed = _build_overview_embed(brief)
        assert "Today's setup" in embed['description']
        assert 'Trend-continuation favored' in embed['description']
        # Brain emoji prefix so the line is visually distinct
        assert '\U0001F9E0' in embed['description']

    def test_overview_unchanged_when_no_explanation(self):
        from gcp.premarket_brief import _build_overview_embed
        brief = {
            'date': 'Tue Apr 28, 2026',
            'tickers': {
                'IWM': {'price': 215, 'change_pct': 1.0, 'rsi': 72,
                        'ftfc_direction': 'bullish', 'ftfc_score': 1.0,
                        'vol_regime': 'Normal'},
            },
        }
        embed = _build_overview_embed(brief)
        # Setup explanation absent → header line absent
        assert "Today's setup" not in embed['description']


# ── BRIEF_AS_OF / BRIEF_TICKERS env overrides (Slice 0 of Discord plan) ──


class TestResolveAnalysisDate:
    """`_resolve_analysis_date` reads BRIEF_AS_OF for historical replay."""

    def test_default_returns_today(self, monkeypatch):
        monkeypatch.delenv("BRIEF_AS_OF", raising=False)
        from gcp.premarket_brief import _resolve_analysis_date
        assert _resolve_analysis_date() == date.today()

    def test_explicit_past_date_honoured(self, monkeypatch):
        monkeypatch.setenv("BRIEF_AS_OF", "2026-04-23")
        from gcp.premarket_brief import _resolve_analysis_date
        assert _resolve_analysis_date() == date(2026, 4, 23)

    def test_blank_falls_back_to_today(self, monkeypatch):
        monkeypatch.setenv("BRIEF_AS_OF", "   ")
        from gcp.premarket_brief import _resolve_analysis_date
        assert _resolve_analysis_date() == date.today()

    def test_future_date_rejected(self, monkeypatch):
        from datetime import timedelta
        future = (date.today() + timedelta(days=30)).isoformat()
        monkeypatch.setenv("BRIEF_AS_OF", future)
        from gcp.premarket_brief import _resolve_analysis_date
        with pytest.raises(ValueError, match="future"):
            _resolve_analysis_date()


class TestResolveBriefTickers:
    """`_resolve_brief_tickers` reads BRIEF_TICKERS for one-off / replay
    runs that target a specific ticker subset."""

    def test_default_unchanged_when_unset(self, monkeypatch):
        monkeypatch.delenv("BRIEF_TICKERS", raising=False)
        from gcp.premarket_brief import _resolve_brief_tickers
        assert _resolve_brief_tickers(["IWM", "SPY"]) == ["IWM", "SPY"]

    def test_comma_separated(self, monkeypatch):
        monkeypatch.setenv("BRIEF_TICKERS", "AMD,ARM,CARS")
        from gcp.premarket_brief import _resolve_brief_tickers
        assert _resolve_brief_tickers(["IWM"]) == ["AMD", "ARM", "CARS"]

    def test_space_separated(self, monkeypatch):
        monkeypatch.setenv("BRIEF_TICKERS", "amd arm")
        from gcp.premarket_brief import _resolve_brief_tickers
        assert _resolve_brief_tickers(["IWM"]) == ["AMD", "ARM"]

    def test_semicolon_separated(self, monkeypatch):
        # gcloud --update-env-vars uses comma as its own delimiter, so
        # multi-ticker BRIEF_TICKERS values must use semicolons to pass
        # through the CLI cleanly.
        monkeypatch.setenv("BRIEF_TICKERS", "AMD;ARM;CARS")
        from gcp.premarket_brief import _resolve_brief_tickers
        assert _resolve_brief_tickers(["IWM"]) == ["AMD", "ARM", "CARS"]

    def test_blank_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BRIEF_TICKERS", "  ")
        from gcp.premarket_brief import _resolve_brief_tickers
        assert _resolve_brief_tickers(["IWM"]) == ["IWM"]


# ── BRIEF_AS_OF df cutoff (regression for ARM 4/20 leak) ─────────────────


class TestBriefAsOfDfCutoff:
    """Regression test for the brief's df cutoff logic.

    Without the cutoff, `loader.load_daily()` returns the FULL daily
    history. On historical replays this leaks future bars into the
    StratClassifier, the level map (PDH/PDL/PWH/...), and the indicator
    calc — surfaced when the ARM 4/20 replay produced PDH=$237.68 (the
    actual 2026-04-24 high) instead of $168.35 (the actual 4/17 high).

    These tests confirm the strict-less-than cutoff trims future bars
    on a tz-naive DatetimeIndex.
    """

    def test_strict_less_than_excludes_analysis_date(self):
        """df rows on/after analysis_date must be filtered out."""
        import pandas as pd
        idx = pd.to_datetime([
            '2026-04-15', '2026-04-16', '2026-04-17',  # before
            '2026-04-20',                                # analysis_date itself
            '2026-04-21', '2026-04-22',                  # future leak
        ])
        df = pd.DataFrame(
            {'High': [1, 2, 3, 999, 1000, 1001]},  # 999/1000/1001 = leakage flags
            index=idx,
        )
        analysis_date = date(2026, 4, 20)
        cutoff = pd.Timestamp(analysis_date)
        idx_norm = df.index.tz_localize(None) if df.index.tz is not None else df.index
        out = df.loc[idx_norm < cutoff]
        # Only 4/15-4/17 should remain (3 rows)
        assert len(out) == 3
        assert out['High'].max() == 3  # leakage values 999/1000/1001 excluded
        # df.iloc[-1] should be 4/17 (the last bar before analysis_date)
        assert out.index[-1].date() == date(2026, 4, 17)

    def test_tz_aware_index_normalized(self):
        """Tz-aware index works the same as tz-naive."""
        import pandas as pd
        idx = pd.to_datetime([
            '2026-04-17', '2026-04-20', '2026-04-22',
        ]).tz_localize('UTC')
        df = pd.DataFrame({'High': [1, 999, 1000]}, index=idx)
        analysis_date = date(2026, 4, 20)
        cutoff = pd.Timestamp(analysis_date)
        idx_norm = df.index.tz_localize(None) if df.index.tz is not None else df.index
        out = df.loc[idx_norm < cutoff]
        assert len(out) == 1
        assert out['High'].iloc[0] == 1  # only 4/17 retained

