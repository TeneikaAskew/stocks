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

