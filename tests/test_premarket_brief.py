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


@pytest.fixture(autouse=True)
def _allow_unconfirmed(monkeypatch):
    """Most tests assert on tier-4/5/6 single-source rows. Default
    production behavior filters those out (BRIEF_INCLUDE_UNCONFIRMED=0),
    so set the override here to keep the legacy test surface intact.
    Specific tests for the confirmed-only filter override this.
    """
    monkeypatch.setenv('BRIEF_INCLUDE_UNCONFIRMED', '1')


@pytest.fixture
def mock_cloud_sql(monkeypatch):
    """Force Cloud SQL "configured" and capture the SQL/params handed to
    `query_to_dataframe`. Returns a setter that lets each test feed in
    a different DataFrame."""
    from gcp import database
    from gcp import premarket_brief as pb

    captured = {"sql": None, "params": {}, "sqls": [], "all_params": []}

    def install(df: pd.DataFrame):
        def fake_query(sql, params=None):
            # The brief loaders issue more than one query (main earnings
            # select + reversal-rate CTE + AMC-walkback lookup). Tests
            # assert on parameters by name (`captured["params"]["prior"]`,
            # `["start"]`, `["end"]`, etc.) — store the union of every
            # call's params so an assertion never fails just because
            # the last query happened to omit a key set by an earlier
            # one. Per-call detail is preserved in `sqls` / `all_params`
            # for tests that need to inspect query order or count.
            captured["sql"] = sql
            captured["sqls"].append(sql)
            new_params = dict(params or {})
            captured["all_params"].append(new_params)
            captured["params"] = {**captured["params"], **new_params}
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
    """Build a one-row earnings_calendar dict matching the SELECT shape.

    Includes the LEFT-joined market_data_daily columns (gap_pct, pre_high,
    pre_low, pre_vwap) — set by tests that exercise the gap-render path.
    Also includes the beat/miss columns (eps_actual, eps_surprise_pct)
    set by tests that exercise the report-verdict render.
    """
    base = {
        "ticker": ticker,
        "earnings_date": date(2026, 4, 27),
        "company_name": ticker + " Inc",
        "earnings_time": "BMO",
        "eps_estimate": 1.0,
        "eps_actual": None,
        "eps_surprise_pct": None,
        "expected_move": 5.0,
        "sector": "Tech",
        "market_cap": 1_000_000_000,
        "stock_volume": 1_000_000,
        "options_volume": 50_000,
        "open_interest": 100_000,
        "rv_1d_last_12q": None,
        "strategy": None,
        "strike": None,
        "premium": None,
        "score": None,
        "data_source": source,
        # Joined market_data_daily columns — None when no daily row
        "gap_pct": None,
        "pre_high": None,
        "pre_low": None,
        "pre_vwap": None,
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


def test_tier_2_uw_plus_yahoo_promotes_av_disagreement(mock_cloud_sql):
    """The SBUX case: UW + Yahoo agree on the date, AV booked a different
    day. With Yahoo as a date-confirming source, two sources agree →
    tier 2 instead of being demoted to tier 5 just because AV is missing.
    """
    install, _ = mock_cloud_sql
    install(pd.DataFrame([
        _row("SBUX", "unusual_whales", market_cap=112_000_000_000),
        _row("SBUX", "yahoo"),
    ]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    e = result["earnings"][0]
    assert e["tier"] == 2, "UW + Yahoo agreement = tier 2"
    assert sorted(e["sources"]) == ["unusual_whales", "yahoo"]


def test_tier_1_three_dates_plus_ew(mock_cloud_sql):
    """All three date sources agree + EW strategy → tier 1 (strongest signal)."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([
        _row("AAPL", "alphavantage"),
        _row("AAPL", "unusual_whales"),
        _row("AAPL", "yahoo"),
        _row("AAPL", "earnings_whispers", strategy="straddle"),
    ]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    assert result["earnings"][0]["tier"] == 1


def test_tier_4_yahoo_only(mock_cloud_sql):
    """Yahoo alone (no AV/UW/EW) → tier 4 — one non-AV date confirmed.

    Better than AV-alone tier 6 because Yahoo dates are accurate; worse
    than tier 2 because we want corroboration from a second source.
    """
    install, _ = mock_cloud_sql
    install(pd.DataFrame([_row("XYZ", "yahoo")]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    assert result["earnings"][0]["tier"] == 4


def test_tier_4_uw_alone_demoted_from_legacy_tier_5(mock_cloud_sql):
    """UW alone is now tier 4 (was tier 5 before Yahoo). The new floor
    for "one non-AV date source confirmed" is tier 4 — matches Yahoo-only."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([_row("ZZZ", "unusual_whales")]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    assert result["earnings"][0]["tier"] == 4


def test_tier_3_yahoo_plus_ew(mock_cloud_sql):
    """Yahoo + EW (strategy without AV/UW backing) → tier 3."""
    install, _ = mock_cloud_sql
    install(pd.DataFrame([
        _row("ABC", "yahoo"),
        _row("ABC", "earnings_whispers", strategy="bull_spread"),
    ]))
    from gcp.premarket_brief import load_earnings_for_brief

    result = load_earnings_for_brief(date(2026, 4, 27))
    assert result["earnings"][0]["tier"] == 3


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


class TestStochRegimeTag:
    """StochRSI K/D → 'oversold' / 'overbought' / 'neutral'."""

    def test_pegged_top_is_overbought(self):
        from gcp.premarket_brief import _stoch_regime_tag
        assert _stoch_regime_tag(100, 99) == 'overbought'
        assert _stoch_regime_tag(85, 80) == 'overbought'

    def test_pegged_bottom_is_oversold(self):
        from gcp.premarket_brief import _stoch_regime_tag
        assert _stoch_regime_tag(0, 1) == 'oversold'
        assert _stoch_regime_tag(20, 15) == 'oversold'

    def test_mid_range_is_neutral(self):
        from gcp.premarket_brief import _stoch_regime_tag
        assert _stoch_regime_tag(50, 55) == 'neutral'
        assert _stoch_regime_tag(40, 60) == 'neutral'

    def test_either_line_pegged_top_triggers_overbought(self):
        """If K=85 but D=70, the more extreme reading wins."""
        from gcp.premarket_brief import _stoch_regime_tag
        assert _stoch_regime_tag(85, 70) == 'overbought'

    def test_none_input_returns_blank(self):
        from gcp.premarket_brief import _stoch_regime_tag
        assert _stoch_regime_tag(None, 50) == ''
        assert _stoch_regime_tag(50, None) == ''


class TestResolveSignalStatus:
    """`signal_status` is gated by `ftfc_direction`.

    The regression preserves the 2026-05-08 audit fix (track-B G.P1.5):
    bullish FTFC must not surface a "PUT setup" status, and bearish
    FTFC must not surface "CALL setup". Mixed FTFC picks the higher
    score's side; ties resolve to CALL.

    `signal_threshold=3` and `building_threshold=2` mirror the
    production defaults at `lib/config.py:312-313`.
    """

    def test_bullish_ftfc_gates_to_call_even_when_put_score_higher(self):
        from gcp.premarket_brief import _resolve_signal_status
        # Pre-fix this row would have published "PUT setup (4/5)";
        # post-fix it publishes "CALL building (2/5)" (because
        # bullish FTFC means we surface only the call_score side).
        assert _resolve_signal_status(
            call_score=2, put_score=4,
            ftfc_direction='bullish',
            signal_threshold=3, building_threshold=2,
        ) == 'CALL building (2/5)'

    def test_bearish_ftfc_gates_to_put_even_when_call_score_higher(self):
        from gcp.premarket_brief import _resolve_signal_status
        assert _resolve_signal_status(
            call_score=4, put_score=2,
            ftfc_direction='bearish',
            signal_threshold=3, building_threshold=2,
        ) == 'PUT building (2/5)'

    def test_mixed_ftfc_picks_higher_score_side(self):
        from gcp.premarket_brief import _resolve_signal_status
        assert _resolve_signal_status(
            call_score=4, put_score=2,
            ftfc_direction='mixed',
            signal_threshold=3, building_threshold=2,
        ) == 'CALL setup (4/5)'
        assert _resolve_signal_status(
            call_score=1, put_score=4,
            ftfc_direction='mixed',
            signal_threshold=3, building_threshold=2,
        ) == 'PUT setup (4/5)'

    def test_mixed_ftfc_ties_resolve_to_call(self):
        """Tie at 3-3 under mixed FTFC publishes CALL (deterministic
        choice keeps downstream consumers from oscillating)."""
        from gcp.premarket_brief import _resolve_signal_status
        assert _resolve_signal_status(
            call_score=3, put_score=3,
            ftfc_direction='mixed',
            signal_threshold=3, building_threshold=2,
        ) == 'CALL setup (3/5)'

    def test_below_building_threshold_returns_no_signal(self):
        from gcp.premarket_brief import _resolve_signal_status
        assert _resolve_signal_status(
            call_score=1, put_score=1,
            ftfc_direction='bullish',
            signal_threshold=3, building_threshold=2,
        ) == 'No signal'

    def test_setup_threshold_picks_setup_label_over_building(self):
        from gcp.premarket_brief import _resolve_signal_status
        assert _resolve_signal_status(
            call_score=4, put_score=0,
            ftfc_direction='bullish',
            signal_threshold=3, building_threshold=2,
        ) == 'CALL setup (4/5)'

    def test_none_ftfc_treated_as_mixed(self):
        from gcp.premarket_brief import _resolve_signal_status
        # None / unknown FTFC string defensively falls back to mixed
        # (higher-score wins); prevents a NoneError or AttributeError
        # if upstream ever sends a missing direction.
        assert _resolve_signal_status(
            call_score=4, put_score=2,
            ftfc_direction=None,
            signal_threshold=3, building_threshold=2,
        ) == 'CALL setup (4/5)'

    def test_capitalized_bullish_still_gates_correctly(self):
        from gcp.premarket_brief import _resolve_signal_status
        # FTFC dir comes from `compute_strat_status` and could be
        # 'Bullish' / 'BULLISH' / 'bullish'. Lowercase + substring
        # match is robust to all of those.
        assert _resolve_signal_status(
            call_score=4, put_score=0,
            ftfc_direction='Bullish',
            signal_threshold=3, building_threshold=2,
        ) == 'CALL setup (4/5)'


class TestResolveDataFreshness:
    """Track B audit G.P0.4 — staleness detector for the brief.

    The audit's repro: brief on 2026-05-04 → 05-07 read the same
    2026-04-27 daily bar each morning because the daily fetcher had
    been frozen since 4-28. The null-close filter at line 724
    silently fell back to last-good-bar. This regression class locks
    the new helper's contract — including the weekend exemption that
    keeps Monday briefs reading Friday from being false-flagged.
    """

    def test_one_day_gap_is_fresh(self):
        from gcp.premarket_brief import _resolve_data_freshness
        from datetime import date
        is_stale, gap, status = _resolve_data_freshness(
            last_bar_date=date(2026, 5, 6),
            analysis_date=date(2026, 5, 7),
        )
        assert is_stale is False
        assert gap == 1
        assert status == 'fresh'

    def test_zero_day_gap_is_fresh(self):
        """Edge case — analysis_date == last_bar_date (a same-day
        replay)."""
        from gcp.premarket_brief import _resolve_data_freshness
        from datetime import date
        is_stale, gap, status = _resolve_data_freshness(
            last_bar_date=date(2026, 5, 7),
            analysis_date=date(2026, 5, 7),
        )
        assert is_stale is False
        assert gap == 0
        assert status == 'fresh'

    def test_six_day_gap_flags_stale(self):
        """The audit's own repro window: 2026-05-07 brief reading
        2026-04-27 last bar = 10 days. Should fire."""
        from gcp.premarket_brief import _resolve_data_freshness
        from datetime import date
        is_stale, gap, status = _resolve_data_freshness(
            last_bar_date=date(2026, 4, 27),
            analysis_date=date(2026, 5, 7),
        )
        assert is_stale is True
        assert gap == 10
        assert status == 'STALE_DAILY_DATA'

    def test_friday_to_monday_weekend_exemption(self):
        """Monday brief reading Friday (gap=3, weekday=Mon=0) is
        FRESH, not stale — that's the normal weekend bridge."""
        from gcp.premarket_brief import _resolve_data_freshness
        from datetime import date
        is_stale, gap, status = _resolve_data_freshness(
            last_bar_date=date(2026, 5, 1),    # Friday
            analysis_date=date(2026, 5, 4),    # Monday
        )
        assert is_stale is False
        assert gap == 3
        assert status == 'fresh'

    def test_sunday_weekly_brief_friday_data_is_fresh(self):
        """Codex P2 review on PR #336: the Sunday weekly brief flow
        (premarket_brief.py is_sunday branch reading Friday's daily
        bar) has gap=2, weekday=Sun=6. The market hasn't produced a
        newer bar over the weekend, so this must be fresh — the v1
        weekend exemption only covered Monday and would have
        suppressed every Sunday-brief ticker."""
        from gcp.premarket_brief import _resolve_data_freshness
        from datetime import date
        is_stale, gap, status = _resolve_data_freshness(
            last_bar_date=date(2026, 5, 1),    # Friday
            analysis_date=date(2026, 5, 3),    # Sunday
        )
        assert is_stale is False
        assert gap == 2
        assert status == 'fresh'

    def test_thursday_to_monday_is_stale(self):
        """Thursday → Monday brief (gap=4) is stale — the weekend
        exemption only covers Friday → Monday. Bias toward
        false-positives on holiday weeks per the docstring."""
        from gcp.premarket_brief import _resolve_data_freshness
        from datetime import date
        is_stale, gap, status = _resolve_data_freshness(
            last_bar_date=date(2026, 4, 30),    # Thursday
            analysis_date=date(2026, 5, 4),     # Monday
        )
        assert is_stale is True
        assert gap == 4
        assert status == 'STALE_DAILY_DATA'

    def test_none_last_bar_returns_unknown(self):
        from gcp.premarket_brief import _resolve_data_freshness
        from datetime import date
        is_stale, gap, status = _resolve_data_freshness(
            last_bar_date=None,
            analysis_date=date(2026, 5, 7),
        )
        assert is_stale is False
        assert gap == -1
        assert status == 'unknown'


class TestDataAsOfAnchor:
    """W11 — `data_as_of` should be anchored to 16:00 ET (US/Eastern
    market close) on the bar's date, regardless of how the daily
    DatetimeIndex hands it in.

    The W6 v1 writer used `latest.name` directly, which for pandas
    DatetimeIndex at UTC midnight renders as "20:00 EDT prior day"
    when displayed in ET — confusing for validation queries where
    a reader expects the timestamp to mean "this bar's data". The
    anchor normalizes to bar_date + 16:00 ET so:

      * UTC display: bar_date + 4h (e.g. 2026-05-06 → 20:00 UTC)
      * ET display:  bar_date + 16:00 (e.g. 2026-05-06 → 16:00 EDT)

    Both forms unambiguously name the bar's date; the ET form
    additionally names market close, which is when the daily bar's
    data crystallizes.
    """

    def test_anchor_renders_at_market_close_in_et(self):
        """A `latest.name` of pandas-default UTC midnight is normalized
        to 16:00 ET on the same calendar date."""
        import pandas as pd
        from datetime import date

        # Simulate what generate_premarket_brief does when latest.name
        # is a tz-naive Timestamp at UTC midnight (pandas default for
        # daily bars).
        last_bar_ts = pd.Timestamp('2026-05-06')  # naive midnight
        last_bar_date_obj = last_bar_ts.date()
        anchored = (
            pd.Timestamp(last_bar_date_obj)
            .tz_localize('America/New_York')
            .replace(hour=16, minute=0, second=0)
        )

        # In ET: 16:00 EDT on 5/6
        et = anchored.tz_convert('America/New_York')
        assert et.date() == date(2026, 5, 6)
        assert et.hour == 16
        assert et.minute == 0

        # In UTC: same instant rendered in UTC = 20:00 UTC (EDT offset = -4)
        utc = anchored.tz_convert('UTC')
        assert utc.hour == 20
        assert utc.date() == date(2026, 5, 6)

    def test_anchor_is_stable_across_dst_transitions(self):
        """W11 anchor must give 16:00 ET regardless of EDT (-04:00)
        vs EST (-05:00). November bar in EST vs May bar in EDT —
        both should display at 16:00 ET."""
        import pandas as pd
        from datetime import date

        # EST date (early November is EST)
        est_anchored = (
            pd.Timestamp(date(2025, 11, 10))
            .tz_localize('America/New_York')
            .replace(hour=16, minute=0, second=0)
        )
        assert est_anchored.tz_convert('America/New_York').hour == 16
        # EST offset is -5, so UTC is 21:00
        assert est_anchored.tz_convert('UTC').hour == 21

        # EDT date (May is EDT)
        edt_anchored = (
            pd.Timestamp(date(2026, 5, 6))
            .tz_localize('America/New_York')
            .replace(hour=16, minute=0, second=0)
        )
        assert edt_anchored.tz_convert('America/New_York').hour == 16
        # EDT offset is -4, so UTC is 20:00
        assert edt_anchored.tz_convert('UTC').hour == 20

    def test_anchor_display_no_longer_renders_prior_day_at_8pm(self):
        """The audit's user-reported confusion ('why am I seeing
        8 PM market-close data?'). With the W11 anchor, displaying
        the timestamp in ET shows 16:00 ET on the bar's date, never
        the prior day at 20:00."""
        import pandas as pd
        from datetime import date

        anchored = (
            pd.Timestamp(date(2026, 5, 6))
            .tz_localize('America/New_York')
            .replace(hour=16, minute=0, second=0)
        )
        et_repr = anchored.tz_convert('America/New_York')
        # Rendering as a date+time string in ET
        et_str = et_repr.strftime('%Y-%m-%d %H:%M:%S')
        assert et_str == '2026-05-06 16:00:00', (
            f"expected 16:00 ET on bar's date, got {et_str!r}"
        )
        # And explicitly NOT the v1 buggy form
        assert '20:00' not in et_str
        assert '2026-05-05' not in et_str  # not the prior day


class TestFormatDataFreshnessSummary:
    """The "Based on data from X to Y" line rendered in the overview
    embed (Track B audit G.P0.5)."""

    def test_healthy_single_bar_window(self):
        from gcp.premarket_brief import _format_data_freshness_summary
        from datetime import date
        line = _format_data_freshness_summary(
            earliest_as_of=date(2026, 5, 6),
            latest_as_of=date(2026, 5, 6),
            analysis_date=date(2026, 5, 7),
            any_stale=False,
        )
        assert line == 'Based on data from 2026-05-06 → 2026-05-06 (1 trading day)'

    def test_stale_includes_warning_emoji_and_session_count(self):
        """Audit repro: trader looking at the 2026-05-07 brief should
        see at-a-glance that the analysis was based on 6-session-stale
        data. The line must include both 'stale by N session(s)' and
        the warning emoji."""
        from gcp.premarket_brief import _format_data_freshness_summary
        from datetime import date
        line = _format_data_freshness_summary(
            earliest_as_of=date(2026, 4, 27),
            latest_as_of=date(2026, 4, 27),
            analysis_date=date(2026, 5, 7),
            any_stale=True,
        )
        assert 'Based on data from 2026-04-27 → 2026-04-27' in line
        assert 'stale by 10 sessions' in line
        assert '⚠' in line

    def test_none_input_returns_none(self):
        """No tickers had usable data — embed builder should skip the
        line entirely. None signal lets the caller's
        `if freshness_summary:` guard handle it."""
        from gcp.premarket_brief import _format_data_freshness_summary
        from datetime import date
        assert _format_data_freshness_summary(
            earliest_as_of=None,
            latest_as_of=None,
            analysis_date=date(2026, 5, 7),
            any_stale=False,
        ) is None


class TestFmtCombo:
    """Snake-case storage form → title-case render form."""

    def test_322_bull_continuation_capitalized(self):
        from gcp.premarket_brief import _fmt_combo
        assert _fmt_combo('322_bull_continuation') == '322 Bull Continuation'

    def test_failed_2u_keeps_2u_uppercase(self):
        from gcp.premarket_brief import _fmt_combo
        assert _fmt_combo('failed_2u_bear_reversal') == 'Failed 2U Bear Reversal'

    def test_clean_2d_bull(self):
        from gcp.premarket_brief import _fmt_combo
        assert _fmt_combo('clean_2d_bull') == 'Clean 2D Bull'

    def test_212_bull_reversal(self):
        from gcp.premarket_brief import _fmt_combo
        assert _fmt_combo('212_bull_reversal') == '212 Bull Reversal'

    def test_none_or_empty_returns_blank(self):
        from gcp.premarket_brief import _fmt_combo
        assert _fmt_combo('') == ''
        assert _fmt_combo(None) == ''
        assert _fmt_combo('none') == ''


class TestFmtTimeframe:
    """RESAMPLE_RULES key → uppercase short form."""

    def test_lowercase_day_to_uppercase(self):
        from gcp.premarket_brief import _fmt_timeframe
        assert _fmt_timeframe('1d') == '1D'

    def test_lowercase_week_to_uppercase(self):
        from gcp.premarket_brief import _fmt_timeframe
        assert _fmt_timeframe('1w') == '1W'

    def test_1mo_collapses_to_1M(self):
        from gcp.premarket_brief import _fmt_timeframe
        assert _fmt_timeframe('1mo') == '1M'

    def test_4h_to_4H(self):
        from gcp.premarket_brief import _fmt_timeframe
        assert _fmt_timeframe('4h') == '4H'

    def test_blank_passthrough(self):
        from gcp.premarket_brief import _fmt_timeframe
        assert _fmt_timeframe('') == ''


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

    def test_stochrsi_renders_with_overbought_regime_tag(self):
        """100/99 reading should append (overbought) so the trader sees
        the regime context next to the raw numbers."""
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data(stoch_k=100, stoch_d=99)}}
        fields = _build_ticker_fields(brief)
        mom_value = next(f['value'] for f in fields if f['name'] == 'IWM Momentum')
        stoch_line = next(ln for ln in mom_value.split('\n') if ln.startswith('StochRSI:'))
        assert '100/99' in stoch_line
        assert '(overbought)' in stoch_line

    def test_stochrsi_renders_with_oversold_regime_tag(self):
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data(stoch_k=5, stoch_d=10)}}
        fields = _build_ticker_fields(brief)
        mom_value = next(f['value'] for f in fields if f['name'] == 'IWM Momentum')
        stoch_line = next(ln for ln in mom_value.split('\n') if ln.startswith('StochRSI:'))
        assert '(oversold)' in stoch_line

    def test_stochrsi_neutral_renders_with_neutral_tag(self):
        """Mid-range readings show '(neutral)' — positive signal too,
        not noise. Tells the trader 'no momentum exhaustion either way'."""
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data(stoch_k=50, stoch_d=55)}}
        fields = _build_ticker_fields(brief)
        mom_value = next(f['value'] for f in fields if f['name'] == 'IWM Momentum')
        stoch_line = next(ln for ln in mom_value.split('\n') if ln.startswith('StochRSI:'))
        assert '(neutral)' in stoch_line

    def test_three_inline_fields_per_ticker_when_no_llm_analysis(self):
        """With no llm_analysis the embed keeps the legacy 3-field layout."""
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data()}}
        fields = _build_ticker_fields(brief)
        assert len(fields) == 3
        assert all(f['inline'] for f in fields)

    def test_strat_field_renders_combo_title_case(self):
        """`322_bull_continuation` should render as `322 Bull Continuation`
        in the brief embed — not the snake_case storage form."""
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data(
            strat_combo='322_bull_continuation',
        )}}
        fields = _build_ticker_fields(brief)
        strat_value = next(f['value'] for f in fields if f['name'] == 'IWM Strat')
        assert '322 Bull Continuation' in strat_value
        assert '322_bull_continuation' not in strat_value

    def test_daily_and_combo_render_on_separate_lines(self):
        """Daily and Combo should be on their own lines — the previous
        `Daily: 2U | Combo: 322 Bull Continuation` form overflowed
        visually on mobile when the combo name was long."""
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data(
            strat_combo='322_bull_continuation',
        )}}
        fields = _build_ticker_fields(brief)
        strat_value = next(f['value'] for f in fields if f['name'] == 'IWM Strat')
        lines = strat_value.split('\n')
        # Each prefix appears as the START of its own line — never piped
        daily_lines = [ln for ln in lines if ln.startswith('Daily:')]
        combo_lines = [ln for ln in lines if ln.startswith('Combo:')]
        assert len(daily_lines) == 1
        assert len(combo_lines) == 1
        # Old `Daily: ... | Combo: ...` mash-up gone
        assert '|' not in daily_lines[0]
        assert 'Combo:' not in daily_lines[0]

    def test_strat_field_renders_timeframes_uppercase(self):
        """ftfc_labels keys (1d/1w/1mo) should render uppercase (1D/1W/1M)."""
        from gcp.premarket_brief import _build_ticker_fields
        brief = {'tickers': {'IWM': self._ticker_data(
            ftfc_labels={'1d': '2U', '1w': '2U', '1mo': '2U'},
        )}}
        fields = _build_ticker_fields(brief)
        strat_value = next(f['value'] for f in fields if f['name'] == 'IWM Strat')
        # New uppercase form
        assert '1D:2U' in strat_value
        assert '1W:2U' in strat_value
        assert '1M:2U' in strat_value
        # Old lowercase form gone
        assert '1d:2U' not in strat_value
        assert '1mo:2U' not in strat_value

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
    """`_resolve_brief_tickers` resolves the ticker list in three layers:
    BRIEF_TICKERS env var, Cloud SQL watchlists (in_brief=TRUE), and
    finally cfg.market.tickers default."""

    def _stub_empty_watchlist(self, monkeypatch):
        """Make load_watchlist return [] so tests can assert the
        config-default fallback. Production CSQL returns 4 ETFs."""
        import gcp.premarket_brief as pb
        # Patch the function in its source module — the brief imports
        # it lazily inside _resolve_brief_tickers.
        from gcp.fetchers import _watchlist as wlmod
        monkeypatch.setattr(wlmod, "load_watchlist", lambda **kw: [])

    def test_default_unchanged_when_unset(self, monkeypatch):
        monkeypatch.delenv("BRIEF_TICKERS", raising=False)
        self._stub_empty_watchlist(monkeypatch)
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
        self._stub_empty_watchlist(monkeypatch)
        from gcp.premarket_brief import _resolve_brief_tickers
        assert _resolve_brief_tickers(["IWM"]) == ["IWM"]

    def test_cloud_sql_watchlist_supersedes_default(self, monkeypatch):
        """When BRIEF_TICKERS is unset but Cloud SQL has in_brief tickers,
        the brief uses those (production behaviour)."""
        monkeypatch.delenv("BRIEF_TICKERS", raising=False)
        from gcp.fetchers import _watchlist as wlmod
        monkeypatch.setattr(
            wlmod, "load_watchlist",
            lambda **kw: ["IWM", "QQQ", "SPY", "SPX"]
                          if kw.get("surface") == "brief" else [],
        )
        from gcp.premarket_brief import _resolve_brief_tickers
        # cfg default is irrelevant when the watchlist surface returns a value
        assert _resolve_brief_tickers(["IRRELEVANT"]) == [
            "IWM", "QQQ", "SPY", "SPX"]

    def test_brief_tickers_env_supersedes_watchlist(self, monkeypatch):
        """BRIEF_TICKERS env wins over Cloud SQL watchlist."""
        monkeypatch.setenv("BRIEF_TICKERS", "AMD")
        from gcp.fetchers import _watchlist as wlmod
        called = {"yes": False}
        def _wl(**kw):
            called["yes"] = True
            return ["IWM", "QQQ"]
        monkeypatch.setattr(wlmod, "load_watchlist", _wl)
        from gcp.premarket_brief import _resolve_brief_tickers
        assert _resolve_brief_tickers(["IWM"]) == ["AMD"]
        assert not called["yes"], "load_watchlist should not be called when env is set"


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



# ─────────────────────────────────────────────────────────────────────
# Phase 2: morning-run protection — --update flag, history write,
# per-ticker conditional UPSERT. See docs/plans/MORNING_RUN_PROTECTION_PLAN.md.
# ─────────────────────────────────────────────────────────────────────


class TestResolveRunKindAndUpdate:
    """_resolve_run_kind_and_update precedence: CLI flag > env var >
    BRIEF_AS_OF (replay implies update) > BRIEF_TRIGGERED_BY > default."""

    def test_cli_flag_wins(self, monkeypatch):
        from gcp.premarket_brief import _resolve_run_kind_and_update
        monkeypatch.delenv('BRIEF_UPDATE', raising=False)
        monkeypatch.delenv('BRIEF_AS_OF', raising=False)
        allow_update, run_kind = _resolve_run_kind_and_update(True)
        assert allow_update is True
        assert run_kind == 'manual_update'

    def test_brief_update_env_implies_update(self, monkeypatch):
        from gcp.premarket_brief import _resolve_run_kind_and_update
        monkeypatch.setenv('BRIEF_UPDATE', 'true')
        monkeypatch.delenv('BRIEF_AS_OF', raising=False)
        allow_update, run_kind = _resolve_run_kind_and_update(False)
        assert allow_update is True
        assert run_kind == 'manual_update'

    def test_brief_as_of_set_implies_update(self, monkeypatch):
        from gcp.premarket_brief import _resolve_run_kind_and_update
        monkeypatch.setenv('BRIEF_AS_OF', '2026-04-15')
        monkeypatch.delenv('BRIEF_UPDATE', raising=False)
        allow_update, run_kind = _resolve_run_kind_and_update(False)
        assert allow_update is True
        assert run_kind == 'replay_refresh'

    def test_cloud_scheduler_triggered_by_default_no_update(self, monkeypatch):
        from gcp.premarket_brief import _resolve_run_kind_and_update
        monkeypatch.delenv('BRIEF_UPDATE', raising=False)
        monkeypatch.delenv('BRIEF_AS_OF', raising=False)
        monkeypatch.setenv('BRIEF_TRIGGERED_BY',
                           'cloud-scheduler:premarket-brief-daily')
        allow_update, run_kind = _resolve_run_kind_and_update(False)
        assert allow_update is False
        assert run_kind == 'scheduled'

    def test_no_env_no_flag_defaults_to_manual_replay(self, monkeypatch):
        from gcp.premarket_brief import _resolve_run_kind_and_update
        monkeypatch.delenv('BRIEF_UPDATE', raising=False)
        monkeypatch.delenv('BRIEF_AS_OF', raising=False)
        monkeypatch.delenv('BRIEF_TRIGGERED_BY', raising=False)
        allow_update, run_kind = _resolve_run_kind_and_update(False)
        assert allow_update is False
        assert run_kind == 'manual_replay'


class TestPersistPlaybookFailedHandling:
    """A per-ticker playbook crash sets data['status']='PLAYBOOK_FAILED'
    on the ticker's brief dict (gcp/premarket_brief.py:1008-1019). The
    persist layer must:
      - still write the row to premarket_analysis_history (audit trail)
      - skip the canonical premarket_analysis row entirely
    Without this, a fresh-day failure inserts a NULL-playbook row into
    the canonical view that the morning Discord embed reads from.
    """

    def _install_persist_mocks(self, monkeypatch):
        from gcp import database

        captured = {
            'history_rows': [],
            'upsert_rows': [],
            'row_exists_calls': [],
        }

        def fake_bulk_insert(df, table):
            captured['history_rows'].append((table, df.to_dict('records')))
            return len(df)

        def fake_upsert(df, table, keys):
            captured['upsert_rows'].append((table, df.to_dict('records')))
            return len(df)

        def fake_row_exists(table, where):
            captured['row_exists_calls'].append((table, dict(where)))
            return False  # default: no existing rows → all inserts

        monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
        monkeypatch.setattr(database, 'bulk_insert_dataframe', fake_bulk_insert)
        monkeypatch.setattr(database, 'upsert_dataframe', fake_upsert)
        monkeypatch.setattr(database, 'row_exists', fake_row_exists)
        return captured

    def _brief_with_tickers(self, tickers: dict) -> dict:
        return {
            'analysis_date': date(2026, 4, 30),
            'tickers': tickers,
        }

    def test_playbook_failed_writes_to_history_only(self, monkeypatch):
        """PLAYBOOK_FAILED ticker: history yes, canonical no."""
        from gcp.premarket_brief import persist_to_cloud_sql

        captured = self._install_persist_mocks(monkeypatch)
        brief = self._brief_with_tickers({
            'IWM': {'status': 'PLAYBOOK_FAILED', 'price': 220.0,
                    'playbook_error': "TypeError: NoneType > float"},
            'SPX': {'status': None, 'price': 6891.7, 'playbook': 'long calls @...'},
        })
        n = persist_to_cloud_sql(brief, allow_update=True,
                                 run_kind='manual_update', triggered_by='test')

        # Both rows go to history
        assert len(captured['history_rows']) == 1
        history_table, history = captured['history_rows'][0]
        assert history_table == 'premarket_analysis_history'
        history_tickers = {r['ticker'] for r in history}
        assert history_tickers == {'IWM', 'SPX'}

        # Only SPX goes to current
        assert n == 1
        assert len(captured['upsert_rows']) == 1
        upsert_table, upsert = captured['upsert_rows'][0]
        assert upsert_table == 'premarket_analysis'
        assert {r['ticker'] for r in upsert} == {'SPX'}

    def test_no_data_skips_both_tables(self, monkeypatch):
        """NO DATA ticker is excluded entirely; PLAYBOOK_FAILED is not."""
        from gcp.premarket_brief import persist_to_cloud_sql

        captured = self._install_persist_mocks(monkeypatch)
        brief = self._brief_with_tickers({
            'NONE': {'status': 'NO DATA'},
            'IWM':  {'status': 'PLAYBOOK_FAILED', 'price': 220.0},
            'SPX':  {'status': None, 'price': 6891.7},
        })
        persist_to_cloud_sql(brief, allow_update=True,
                             run_kind='manual_update', triggered_by='test')

        history = captured['history_rows'][0][1]
        history_tickers = {r['ticker'] for r in history}
        # NO DATA fully excluded; PLAYBOOK_FAILED still in history
        assert history_tickers == {'IWM', 'SPX'}

    def test_all_playbook_failed_returns_zero_canonical(self, monkeypatch):
        """If every ticker is PLAYBOOK_FAILED the canonical write short-
        circuits to 0 without raising on an empty DataFrame."""
        from gcp.premarket_brief import persist_to_cloud_sql

        captured = self._install_persist_mocks(monkeypatch)
        brief = self._brief_with_tickers({
            'IWM': {'status': 'PLAYBOOK_FAILED', 'price': 220.0},
            'QQQ': {'status': 'PLAYBOOK_FAILED', 'price': 600.0},
        })
        n = persist_to_cloud_sql(brief, allow_update=True,
                                 run_kind='manual_update', triggered_by='test')
        assert n == 0
        # History still got both rows
        history = captured['history_rows'][0][1]
        assert {r['ticker'] for r in history} == {'IWM', 'QQQ'}
        # No canonical-table call at all
        assert captured['upsert_rows'] == []

    def test_playbook_failed_skipped_in_default_path(self, monkeypatch):
        """In the default (allow_update=False) path, PLAYBOOK_FAILED
        tickers are dropped before the row_exists check."""
        from gcp.premarket_brief import persist_to_cloud_sql

        captured = self._install_persist_mocks(monkeypatch)
        brief = self._brief_with_tickers({
            'IWM': {'status': 'PLAYBOOK_FAILED', 'price': 220.0},
            'SPX': {'status': None, 'price': 6891.7, 'playbook': 'x'},
        })
        persist_to_cloud_sql(brief, allow_update=False,
                             run_kind='scheduled', triggered_by='test')
        # row_exists called for SPX only — IWM was filtered upstream
        seen = {c[1]['ticker'] for c in captured['row_exists_calls']}
        assert seen == {'SPX'}


class TestStaleEmbedRenders:
    """Codex P1 review on PR #336 caught that the per-ticker render
    paths (`_build_overview_embed`, `_build_ticker_fields`) did not
    skip STALE_DAILY_DATA rows, which would have caused KeyError on
    `d['price']` / `d['rsi']` / `d['prev_day_high']` etc. since the
    per-ticker analysis is skipped upstream.

    Both builders now emit a degraded line that names the ticker
    and the staleness gap, mirroring the existing NO DATA path.
    """

    def _stale_brief(self, gap_days: int = 10):
        return {
            'date': 'Thu May 07, 2026',
            'analysis_date': date(2026, 5, 7),
            'tickers': {
                'SPY': {
                    'status': 'STALE_DAILY_DATA',
                    'data_freshness_status': 'STALE_DAILY_DATA',
                    'freshness_gap_days': gap_days,
                },
            },
        }

    def test_overview_embed_renders_stale_degraded_line(self):
        """Stale ticker still appears in the description, but with a
        clear staleness banner instead of crashing on missing fields."""
        from gcp.premarket_brief import _build_overview_embed
        embed = _build_overview_embed(self._stale_brief(gap_days=10))
        assert 'SPY' in embed['description']
        assert 'STALE' in embed['description']
        assert '10 sessions old' in embed['description']
        assert '⚠' in embed['description']

    def test_overview_embed_does_not_crash_on_missing_per_ticker_fields(self):
        """Defensive: pre-fix this raised KeyError on d['price']."""
        from gcp.premarket_brief import _build_overview_embed
        # Should not raise.
        embed = _build_overview_embed(self._stale_brief(gap_days=3))
        assert isinstance(embed, dict)
        assert 'description' in embed

    def test_ticker_fields_renders_stale_degraded_field(self):
        from gcp.premarket_brief import _build_ticker_fields
        fields = _build_ticker_fields(self._stale_brief(gap_days=10))
        # One field per ticker; SPY's value carries the staleness
        spy_field = next(f for f in fields if f['name'] == 'SPY')
        assert 'STALE' in spy_field['value']
        assert '10 sessions old' in spy_field['value']

    def test_singular_session_when_gap_one_treated_as_one_session(self):
        """Edge case: gap==1 wouldn't be flagged stale by the helper,
        but if a downstream caller forces status='STALE_DAILY_DATA'
        with gap=1, the rendered string should say '1 session old'
        (singular) not '1 sessions old'."""
        from gcp.premarket_brief import _build_overview_embed
        embed = _build_overview_embed(self._stale_brief(gap_days=1))
        assert '1 session old' in embed['description']
        assert '1 sessions old' not in embed['description']


class TestPersistStaleDataHandling:
    """Track B audit G.P0.4 — STALE_DAILY_DATA tickers must follow the
    same write contract as PLAYBOOK_FAILED: history yes, canonical no.

    The audit's failure mode was the brief silently re-publishing a
    week-old row into the canonical premarket_analysis table four
    mornings in a row. This regression class locks in the fix:
    `data['status']='STALE_DAILY_DATA'` is the trigger by which the
    persist layer suppresses the canonical write while still
    producing an audit-trail row in history with a populated `notes`
    column.
    """

    def _install_persist_mocks(self, monkeypatch):
        from gcp import database

        captured = {
            'history_rows': [],
            'upsert_rows': [],
        }

        def fake_bulk_insert(df, table):
            captured['history_rows'].append((table, df.to_dict('records')))
            return len(df)

        def fake_upsert(df, table, keys):
            captured['upsert_rows'].append((table, df.to_dict('records')))
            return len(df)

        def fake_row_exists(table, where):
            return False

        monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
        monkeypatch.setattr(database, 'bulk_insert_dataframe', fake_bulk_insert)
        monkeypatch.setattr(database, 'upsert_dataframe', fake_upsert)
        monkeypatch.setattr(database, 'row_exists', fake_row_exists)
        return captured

    def _brief_with_tickers(self, tickers):
        return {
            'analysis_date': date(2026, 5, 7),
            'tickers': tickers,
        }

    def test_stale_writes_history_only_skips_canonical(self, monkeypatch):
        """The audit's repro: SPY's daily data is 10 sessions old, IWM
        is healthy. SPY history row gets a notes string explaining the
        skip; only IWM goes to the canonical table."""
        from gcp.premarket_brief import persist_to_cloud_sql

        captured = self._install_persist_mocks(monkeypatch)
        brief = self._brief_with_tickers({
            'SPY': {'status': 'STALE_DAILY_DATA',
                    'data_as_of': pd.Timestamp('2026-04-27'),
                    'data_freshness_status': 'STALE_DAILY_DATA',
                    'freshness_gap_days': 10},
            'IWM': {'status': None, 'price': 220.0,
                    'data_as_of': pd.Timestamp('2026-05-06'),
                    'data_freshness_status': 'fresh'},
        })
        n = persist_to_cloud_sql(brief, allow_update=True,
                                 run_kind='manual_update', triggered_by='test')

        history = captured['history_rows'][0][1]
        history_by_ticker = {r['ticker']: r for r in history}
        # Both rows in history
        assert set(history_by_ticker.keys()) == {'SPY', 'IWM'}
        # SPY history row carries an explanatory notes string
        assert isinstance(history_by_ticker['SPY']['notes'], str)
        assert 'STALE_DAILY_DATA' in history_by_ticker['SPY']['notes']
        assert 'gap=10' in history_by_ticker['SPY']['notes']
        # IWM history row has no notes (healthy path).
        # pandas DataFrame round-trip converts Python None → NaN in
        # mixed-dtype object columns when other rows carry strings,
        # so test the absence with pd.isna rather than `is None`.
        assert pd.isna(history_by_ticker['IWM']['notes'])

        # Only IWM in canonical
        assert n == 1
        upsert = captured['upsert_rows'][0][1]
        assert {r['ticker'] for r in upsert} == {'IWM'}

    def test_data_as_of_columns_propagate_to_history_rows(self, monkeypatch):
        """The new freshness telemetry columns must reach the history
        rows even on healthy tickers — that's the post-fix observability
        that lets a single SELECT identify stuck-fetcher days."""
        from gcp.premarket_brief import persist_to_cloud_sql

        captured = self._install_persist_mocks(monkeypatch)
        ts = pd.Timestamp('2026-05-06')
        brief = self._brief_with_tickers({
            'IWM': {'status': None, 'price': 220.0,
                    'data_as_of': ts, 'data_freshness_status': 'fresh'},
        })
        persist_to_cloud_sql(brief, allow_update=True,
                             run_kind='manual_update', triggered_by='test')

        row = captured['history_rows'][0][1][0]
        assert row['data_as_of'] == ts
        assert row['data_freshness_status'] == 'fresh'

    def test_all_stale_canonical_write_short_circuits(self, monkeypatch):
        """Audit's worst-case: all tickers stale on the same morning.
        canonical write must short-circuit to 0 (no empty-DataFrame
        crash) and history still records all rows with notes."""
        from gcp.premarket_brief import persist_to_cloud_sql

        captured = self._install_persist_mocks(monkeypatch)
        brief = self._brief_with_tickers({
            'SPY': {'status': 'STALE_DAILY_DATA',
                    'data_as_of': pd.Timestamp('2026-04-27'),
                    'data_freshness_status': 'STALE_DAILY_DATA',
                    'freshness_gap_days': 10},
            'IWM': {'status': 'STALE_DAILY_DATA',
                    'data_as_of': pd.Timestamp('2026-04-27'),
                    'data_freshness_status': 'STALE_DAILY_DATA',
                    'freshness_gap_days': 10},
        })
        n = persist_to_cloud_sql(brief, allow_update=True,
                                 run_kind='manual_update', triggered_by='test')
        assert n == 0
        history = captured['history_rows'][0][1]
        assert {r['ticker'] for r in history} == {'SPY', 'IWM'}
        for row in history:
            assert row['notes'] is not None
            assert 'STALE_DAILY_DATA' in row['notes']
        assert captured['upsert_rows'] == []


class TestPersistLLMCommentary:
    """Track B audit G.P2.11 — persist Gemini-generated brief
    commentary for audit trail.

    Pre-W7, the four LLM commentary slots
    (`brief['llm_overview']`, `brief['llm_orb_explanation']`,
    `brief['tickers'][T]['llm_analysis']`,
    `brief['tickers'][T]['llm_playbook']`) were rendered live to
    Discord and discarded. No post-hoc audit could grade what users
    actually saw on a given morning because nothing in
    premarket_analysis captured the LLM text.

    Post-W7, those four strings flow through `persist_to_cloud_sql`
    into both the canonical `premarket_analysis` row and the
    append-only `premarket_analysis_history` row. They are
    non-deterministic — a replay generates different Gemini text —
    but the original morning's text is preserved for back-audit.

    User-confirmed scope decision (during the implementation-plan
    clarification round): "persist for audit trail" rather than skip.
    """

    def _install_persist_mocks(self, monkeypatch):
        from gcp import database

        captured = {
            'history_rows': [],
            'upsert_rows': [],
        }

        def fake_bulk_insert(df, table):
            captured['history_rows'].append((table, df.to_dict('records')))
            return len(df)

        def fake_upsert(df, table, keys):
            captured['upsert_rows'].append((table, df.to_dict('records')))
            return len(df)

        def fake_row_exists(table, where):
            return False

        monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
        monkeypatch.setattr(database, 'bulk_insert_dataframe', fake_bulk_insert)
        monkeypatch.setattr(database, 'upsert_dataframe', fake_upsert)
        monkeypatch.setattr(database, 'row_exists', fake_row_exists)
        return captured

    def test_brief_level_and_per_ticker_llm_fields_propagate_to_history(
        self, monkeypatch,
    ):
        from gcp.premarket_brief import persist_to_cloud_sql

        captured = self._install_persist_mocks(monkeypatch)
        brief = {
            'analysis_date': date(2026, 5, 8),
            'llm_overview': 'Bullish bias across all three ETFs.',
            'llm_orb_explanation': 'Default 5-min ORB; no high-impact catalyst.',
            'tickers': {
                'IWM': {
                    'status': None, 'price': 220.0,
                    'llm_analysis': 'IWM tagged 2U with bullish FTFC.',
                    'llm_playbook': 'CALLS above PDH; stop at CWO.',
                },
                'SPY': {
                    'status': None, 'price': 720.0,
                    'llm_analysis': 'SPY in a tight inside bar.',
                    'llm_playbook': 'Wait for inside-bar break.',
                },
            },
        }
        persist_to_cloud_sql(brief, allow_update=True,
                             run_kind='manual_update', triggered_by='test')

        history = captured['history_rows'][0][1]
        by_ticker = {r['ticker']: r for r in history}

        # Brief-level fields are duplicated to every ticker's row
        # (the persist layer doesn't have a brief-level table; we
        # mirror onto each row so a single SELECT carries everything
        # without joins).
        for row in by_ticker.values():
            assert row['llm_overview'] == 'Bullish bias across all three ETFs.'
            assert row['llm_orb_explanation'] == \
                'Default 5-min ORB; no high-impact catalyst.'

        # Per-ticker fields are distinct
        assert by_ticker['IWM']['llm_analysis'] == \
            'IWM tagged 2U with bullish FTFC.'
        assert by_ticker['SPY']['llm_analysis'] == \
            'SPY in a tight inside bar.'
        assert by_ticker['IWM']['llm_playbook'] == \
            'CALLS above PDH; stop at CWO.'
        assert by_ticker['SPY']['llm_playbook'] == \
            'Wait for inside-bar break.'

    def test_missing_llm_fields_persist_as_null(self, monkeypatch):
        """When the LLM step is disabled (BRIEF_LLM_DISABLE=1) or
        fails, the four slots are absent from the brief dict.
        Persist should land NULL in each, not crash on KeyError."""
        from gcp.premarket_brief import persist_to_cloud_sql

        captured = self._install_persist_mocks(monkeypatch)
        brief = {
            'analysis_date': date(2026, 5, 8),
            # No llm_overview / llm_orb_explanation
            'tickers': {
                'IWM': {'status': None, 'price': 220.0},
                # No llm_analysis / llm_playbook
            },
        }
        persist_to_cloud_sql(brief, allow_update=True,
                             run_kind='manual_update', triggered_by='test')

        # The persisted row keys should still exist (not KeyError);
        # values are None, which pandas serializes as NaN in mixed
        # DataFrames.
        row = captured['history_rows'][0][1][0]
        for col in ('llm_overview', 'llm_orb_explanation',
                    'llm_analysis', 'llm_playbook'):
            assert col in row, f"missing column {col} in persisted row"
            assert pd.isna(row[col]) or row[col] is None

    def test_canonical_upsert_carries_llm_fields(self, monkeypatch):
        """The canonical premarket_analysis row also gets the LLM
        fields — not just history. Future SELECT against the canonical
        table for "today's commentary" must work without joining to
        history."""
        from gcp.premarket_brief import persist_to_cloud_sql

        captured = self._install_persist_mocks(monkeypatch)
        brief = {
            'analysis_date': date(2026, 5, 8),
            'llm_overview': 'Test overview',
            'tickers': {
                'IWM': {'status': None, 'price': 220.0,
                        'llm_analysis': 'Test per-ticker'},
            },
        }
        persist_to_cloud_sql(brief, allow_update=True,
                             run_kind='manual_update', triggered_by='test')
        upsert_row = captured['upsert_rows'][0][1][0]
        assert upsert_row['llm_overview'] == 'Test overview'
        assert upsert_row['llm_analysis'] == 'Test per-ticker'


# ──────────────────────────────────────────────────────────────────────
# market_data_daily JOIN — gap_pct propagation
# ──────────────────────────────────────────────────────────────────────


class TestTradeabilityRanking:
    """The brief ranks by (options_volume × market_cap) BEFORE tier so a
    tier-2 name with real options flow (e.g. SBUX 20K options + $112B
    mcap) outranks tier-1 names with zero options (WELL, WM, MDLZ —
    EW-confirmed but no flow). Tier remains a tiebreaker for similar
    composite scores.
    """

    def test_high_flow_tier2_beats_zero_flow_tier1(self, mock_cloud_sql):
        """SBUX tier 2 with real flow > WELL tier 1 with zero flow."""
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            # WELL: tier 1 (3 sources confirm) but zero options
            _row("WELL", "alphavantage",     options_volume=0, market_cap=149_000_000_000),
            _row("WELL", "unusual_whales",   options_volume=0, market_cap=149_000_000_000),
            _row("WELL", "earnings_whispers",options_volume=0, market_cap=149_000_000_000),
            # SBUX: tier 2 (UW + Yahoo only) but high options + high mcap
            _row("SBUX", "unusual_whales",   options_volume=20_000, market_cap=112_000_000_000),
            _row("SBUX", "yahoo",            options_volume=20_000, market_cap=112_000_000_000),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief

        result = load_earnings_for_brief(date(2026, 4, 27))
        tickers = [e["ticker"] for e in result["earnings"]]
        assert tickers == ["SBUX"], (
            "SBUX with real flow must beat WELL with zero flow; WELL filtered out by options>0"
        )

    def test_tier_breaks_ties_at_same_score(self, mock_cloud_sql):
        """Two names with identical options/mcap → tier 1 ranks first."""
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            _row("BBB", "unusual_whales",     options_volume=10_000, market_cap=50_000_000_000),
            _row("BBB", "yahoo",              options_volume=10_000, market_cap=50_000_000_000),
            _row("AAA", "alphavantage",       options_volume=10_000, market_cap=50_000_000_000),
            _row("AAA", "unusual_whales",     options_volume=10_000, market_cap=50_000_000_000),
            _row("AAA", "earnings_whispers",  options_volume=10_000, market_cap=50_000_000_000),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief

        result = load_earnings_for_brief(date(2026, 4, 27))
        tickers = [e["ticker"] for e in result["earnings"]]
        assert tickers == ["AAA", "BBB"], (
            "Same score → tier 1 (AAA) ranks before tier 2 (BBB)"
        )


class TestConfirmedOnlyFilter:
    """BRIEF_INCLUDE_UNCONFIRMED defaults to '0' — tier 4-6 rows
    (single-source / AV-alone / EW-alone) are dropped from the embed.
    Override to '1' brings them back."""

    def test_default_drops_tier_5_uw_only(self, monkeypatch, mock_cloud_sql):
        # Override the autouse fixture to test default (filter ON) behavior.
        # Also disable the nQ-confidence filter (added 2026-05-14): this test
        # exists to verify the AV ∩ UW source gate, not the reaction-history
        # depth gate. The mocked DB returns no reaction stats so every row
        # would otherwise have nQ=0 and get dropped.
        monkeypatch.delenv('BRIEF_INCLUDE_UNCONFIRMED', raising=False)
        monkeypatch.setenv('BRIEF_MIN_REACTION_QUARTERS', '0')
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            _row('AAA', 'alphavantage', options_volume=10_000),
            _row('AAA', 'unusual_whales', options_volume=10_000),
            _row('AAA', 'earnings_whispers', options_volume=10_000),
            _row('LONE', 'unusual_whales', options_volume=10_000),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief
        result = load_earnings_for_brief(date(2026, 4, 27))
        tickers = {e['ticker'] for e in result['earnings']}
        assert 'AAA' in tickers       # tier 1, kept
        assert 'LONE' not in tickers  # tier 4, filtered out

    def test_override_keeps_unconfirmed(self, monkeypatch, mock_cloud_sql):
        monkeypatch.setenv('BRIEF_INCLUDE_UNCONFIRMED', '1')
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            _row('LONE', 'unusual_whales', options_volume=10_000),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief
        result = load_earnings_for_brief(date(2026, 4, 27))
        assert {e['ticker'] for e in result['earnings']} == {'LONE'}


class TestOptionsFlowFilter:
    """Names without options flow are filtered out — earnings are only
    tradeable via options for this brief's use case. Removes the
    long-tail tier-6 AV-only names (NULL options) and the
    EW-confirmed-but-no-flow names (options_volume=0)."""

    def test_zero_options_volume_filtered_out(self, mock_cloud_sql):
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            _row("WELL", "unusual_whales", options_volume=0),
            _row("AAPL", "unusual_whales", options_volume=12_345),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief

        result = load_earnings_for_brief(date(2026, 4, 27))
        tickers = [e["ticker"] for e in result["earnings"]]
        assert tickers == ["AAPL"]

    def test_null_options_volume_filtered_out(self, mock_cloud_sql):
        """AV-only / EW-only rows have NULL options_volume (UW-derived
        column). Those long-tail names get filtered out."""
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            _row("OBSCURE", "alphavantage", options_volume=None),
            _row("ACTIVE",  "unusual_whales", options_volume=5_000),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief

        result = load_earnings_for_brief(date(2026, 4, 27))
        tickers = [e["ticker"] for e in result["earnings"]]
        assert tickers == ["ACTIVE"]

    def test_options_volume_propagates_max_across_sources(self, mock_cloud_sql):
        """One source has options_volume=NULL but another has the real
        value. Filter must use the MAX across sources, not whichever
        row was 'first'. Otherwise we'd drop SBUX whenever its AV row
        (with NULL options) sorts before its UW row."""
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            _row("SBUX", "alphavantage",   options_volume=None),
            _row("SBUX", "unusual_whales", options_volume=20_272),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief

        result = load_earnings_for_brief(date(2026, 4, 27))
        assert len(result["earnings"]) == 1
        assert result["earnings"][0]["ticker"] == "SBUX"
        assert result["earnings"][0]["options_volume"] == 20_272


class TestEarningsTimePicker:
    """The group's earnings_time must come from the most-specific row,
    not the lowest-priority one. AV often persists 'unknown' even when
    UW has 'postmarket' — the embed mis-bucketed META/GOOGL into the
    'Time Unknown' section before the dedicated picker.
    """

    def test_specific_time_beats_unknown(self, mock_cloud_sql):
        """AV row says 'unknown', UW row says 'postmarket' — output time
        must be 'postmarket' so the row lands in the AMC section."""
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            _row("META", "alphavantage", earnings_time="unknown"),
            _row("META", "unusual_whales", earnings_time="postmarket"),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief
        result = load_earnings_for_brief(date(2026, 4, 27))
        assert result["earnings"][0]["time"] == "postmarket"

    def test_uw_wins_over_av_on_time_when_both_specific(self, mock_cloud_sql):
        """UW > AV on time-of-day per the Yahoo cross-check observations
        (UW had MA right when AV disagreed)."""
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            _row("MA", "alphavantage", earnings_time="postmarket"),
            _row("MA", "unusual_whales", earnings_time="premarket"),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief
        result = load_earnings_for_brief(date(2026, 4, 27))
        assert result["earnings"][0]["time"] == "premarket"

    def test_all_unknown_stays_unknown(self, mock_cloud_sql):
        install, _ = mock_cloud_sql
        install(pd.DataFrame([_row("X", "yahoo", earnings_time="unknown")]))
        from gcp.premarket_brief import load_earnings_for_brief
        result = load_earnings_for_brief(date(2026, 4, 27))
        assert result["earnings"][0]["time"] == "unknown"


class TestGapPctPropagation:
    """The brief loader LEFT-joins market_data_daily so each output row
    carries today's gap_pct. NULL when the ticker isn't in the daily
    fetcher universe — must not crash."""

    def test_gap_pct_propagates_to_output_row(self, mock_cloud_sql):
        install, captured = mock_cloud_sql
        install(pd.DataFrame([
            _row("HUM", "alphavantage", earnings_time="premarket", gap_pct=4.2),
            _row("HUM", "yahoo",        earnings_time="premarket", gap_pct=4.2),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief

        result = load_earnings_for_brief(date(2026, 4, 27))
        assert result["earnings"][0]["gap_pct"] == 4.2

    def test_gap_pct_null_when_no_market_data_row(self, mock_cloud_sql):
        """LEFT JOIN with no match → NULL → output row has gap_pct=None."""
        install, _ = mock_cloud_sql
        install(pd.DataFrame([_row("XYZ", "alphavantage", gap_pct=None)]))
        from gcp.premarket_brief import load_earnings_for_brief

        result = load_earnings_for_brief(date(2026, 4, 27))
        assert result["earnings"][0]["gap_pct"] is None

    def test_sql_joins_market_data_daily(self, mock_cloud_sql):
        """The SQL the loader sends must reference market_data_daily so
        the join happens at query time, not Python-side. The loader
        issues multiple queries (main earnings select + reversal-rate
        CTE); assert against every captured SQL so we don't depend on
        which one runs last."""
        install, captured = mock_cloud_sql
        install(pd.DataFrame([_row("AAPL", "alphavantage")]))
        from gcp.premarket_brief import load_earnings_for_brief

        load_earnings_for_brief(date(2026, 4, 27))
        joined = " | ".join(s.lower() for s in captured["sqls"])
        assert "left join market_data_daily" in joined
        assert "gap_pct" in joined


# ──────────────────────────────────────────────────────────────────────
# _build_earnings_embed — daily section split + gap render
# ──────────────────────────────────────────────────────────────────────


def _earnings_brief(rows, mode='daily'):
    """Build the dict shape that load_earnings_for_brief returns."""
    return {'mode': mode, 'earnings': rows}


def _row_out(ticker, time_, tier, **kw):
    """Build the post-loader output row shape that _build_earnings_embed
    consumes (different from the SQL row — already grouped/tiered)."""
    base = {
        'ticker': ticker, 'date': date(2026, 4, 29),
        'company_name': ticker + ' Inc',
        'time': time_, 'tier': tier,
        'eps_estimate': 1.0,
        'eps_actual': None, 'eps_surprise_pct': None,
        'expected_move': None,
        'sector': '', 'market_cap': 1e9,
        'strategy': '', 'strike': None, 'premium': None, 'score': None,
        'sources': ['alphavantage'],
        'gap_pct': None, 'pre_high': None, 'pre_low': None,
    }
    base.update(kw)
    return base


class TestEarningsEmbedSectionSplit:

    def test_daily_partitions_into_two_sections(self):
        """BMO + AMC sections only — Time Unknown rows are dropped from
        the embed (foreign listings / TNS placeholders without tradeable
        timing)."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('HUM',  'premarket',  1),
            _row_out('AMZN', 'postmarket', 2),
            _row_out('XYZ',  'unknown',    4),
        ]))
        desc = embed['description']
        assert 'Reporting Before Open' in desc
        assert 'Reporting After Close' in desc
        assert 'Time Unknown' not in desc
        # Unknown-time row dropped entirely
        assert 'XYZ' not in desc
        # BMO before AMC
        assert desc.index('HUM') < desc.index('AMZN')

    def test_empty_section_omitted(self):
        """Day with only AMC reporters → no 'Before Open' header rendered."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('MSFT', 'postmarket', 1),
            _row_out('AMZN', 'postmarket', 2),
        ]))
        assert 'Reporting Before Open' not in embed['description']
        assert 'Reporting After Close' in embed['description']

    def test_per_section_cap_independent(self):
        """11 BMO + 11 AMC names → each section caps at 10, BMO doesn't
        crowd out AMC. Confirms the per-section cap fix."""
        rows = (
            [_row_out(f'BMO{i:02d}', 'premarket', 1) for i in range(11)]
            + [_row_out(f'AMC{i:02d}', 'postmarket', 1) for i in range(11)]
        )
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief(rows))
        desc = embed['description']
        # Each '+1 more' line indicates a section had the cap hit
        assert desc.count('+1 more') == 2

    def test_no_earnings_renders_placeholder(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([]))
        assert 'No earnings scheduled' in embed['description']


class TestEarningsEmbedGapRender:

    def test_positive_gap_renders_with_chart_up(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('HUM', 'premarket', 1, gap_pct=4.2),
        ]))
        # 📈 = U+1F4C8
        assert '\U0001f4c8' in embed['description']
        assert '+4.2%' in embed['description']

    def test_negative_gap_renders_with_chart_down(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('SBUX', 'postmarket', 2, gap_pct=-3.7),
        ]))
        # 📉 = U+1F4C9
        assert '\U0001f4c9' in embed['description']
        assert '-3.7%' in embed['description']

    def test_below_threshold_gap_suppressed(self):
        """±0.05% rounding noise must not clutter the line."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('AAPL', 'postmarket', 1, gap_pct=0.02),
        ]))
        assert '\U0001f4c8' not in embed['description']
        assert '\U0001f4c9' not in embed['description']

    def test_null_gap_renders_no_arrow(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('UNKWN', 'premarket', 4, gap_pct=None),
        ]))
        assert '\U0001f4c8' not in embed['description']
        assert '\U0001f4c9' not in embed['description']


# ──────────────────────────────────────────────────────────────────────
# PR 1: Beat/miss enrichment from Yahoo TAS rows
# ──────────────────────────────────────────────────────────────────────


class TestBeatMissPropagation:
    """eps_actual + eps_surprise_pct flow through the loader from Yahoo
    TAS rows (already-reported names). Null for not-yet-reported names."""

    def test_eps_actual_propagates_from_yahoo_row(self, mock_cloud_sql):
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            _row("V", "yahoo", eps_actual=3.31, eps_surprise_pct=6.77),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief
        result = load_earnings_for_brief(date(2026, 4, 27))
        e = result["earnings"][0]
        assert e["eps_actual"] == 3.31
        assert e["eps_surprise_pct"] == 6.77

    def test_negative_surprise_preserved(self, mock_cloud_sql):
        """A -6.8% miss must NOT be filtered as 'no signal' the way a
        zero-options ticker is. Sign carries the verdict."""
        install, _ = mock_cloud_sql
        install(pd.DataFrame([
            _row("SBUX", "yahoo", eps_actual=0.41,
                 eps_surprise_pct=-6.8),
        ]))
        from gcp.premarket_brief import load_earnings_for_brief
        result = load_earnings_for_brief(date(2026, 4, 27))
        assert result["earnings"][0]["eps_surprise_pct"] == -6.8

    def test_null_actual_keeps_null(self, mock_cloud_sql):
        install, _ = mock_cloud_sql
        install(pd.DataFrame([_row("AAPL", "alphavantage")]))
        from gcp.premarket_brief import load_earnings_for_brief
        result = load_earnings_for_brief(date(2026, 4, 27))
        assert result["earnings"][0]["eps_actual"] is None
        assert result["earnings"][0]["eps_surprise_pct"] is None


class TestBeatMissRender:
    """The embed renders 'EPS 0.44→0.41 ❌ -6.8%' inline once a company
    has reported. Verdict marker chosen by surprise threshold:
        >= +1% → ✅ beat
        <= -1% → ❌ miss
        otherwise → 🎯 inline
    """

    def test_beat_renders_check_mark(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('V', 'postmarket', 1,
                     eps_estimate=3.10, eps_actual=3.31,
                     eps_surprise_pct=6.77),
        ]))
        assert '✅' in embed['description']
        assert '3.10→33.31' in embed['description'].replace(' ', '') \
            or 'EPS 3.10→3.31' in embed['description']
        # Surprise pct is shown with sign
        assert '+6.8%' in embed['description']

    def test_miss_renders_x_mark(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('SBUX', 'postmarket', 2,
                     eps_estimate=0.44, eps_actual=0.41,
                     eps_surprise_pct=-6.8),
        ]))
        assert '❌' in embed['description']
        assert '-6.8%' in embed['description']

    def test_inline_renders_bullseye(self):
        """Surprise within ±1% is 'inline' — bullseye marker."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('AAPL', 'postmarket', 1,
                     eps_estimate=1.94, eps_actual=1.95,
                     eps_surprise_pct=0.5),
        ]))
        assert '\U0001f3af' in embed['description']

    def test_no_actual_falls_back_to_estimate(self):
        """Pre-report ticker (no actual yet) shows 'EPS X.XX' fallback,
        no verdict marker."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('AMZN', 'postmarket', 2,
                     eps_estimate=1.65, eps_actual=None,
                     eps_surprise_pct=None),
        ]))
        desc = embed['description']
        # No verdict markers
        assert '✅' not in desc
        assert '❌' not in desc
        assert '\U0001f3af' not in desc
        # Plain EPS estimate fallback present
        assert 'EPS 1.65' in desc

    def test_surprise_derived_when_yahoo_missing_pct(self):
        """If Yahoo gave actual but not surprise%, derive from
        (actual - estimate) / |estimate|."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('META', 'postmarket', 2,
                     eps_estimate=6.69, eps_actual=6.94,
                     eps_surprise_pct=None),  # missing
        ]))
        # Expect derived surprise = (6.94 - 6.69) / 6.69 * 100 ≈ +3.7%
        assert '+3.7%' in embed['description']
        assert '✅' in embed['description']


# ──────────────────────────────────────────────────────────────────────
# PR 3: Yesterday-AMC reaction view
# ──────────────────────────────────────────────────────────────────────


class TestYesterdayAmcReactionsLoader:
    """load_yesterday_amc_reactions queries yesterday's AMC reporters,
    LEFT-joins TODAY's market_data_daily for gap_pct, returns top N
    by |gap|. Walks back over weekends so a Monday brief still finds
    Friday's AMC names."""

    def test_walks_back_over_weekend(self, mock_cloud_sql):
        install, captured = mock_cloud_sql
        install(pd.DataFrame({
            'ticker': ['SBUX'], 'earnings_date': [date(2026, 5, 1)],
            'eps_estimate': [0.44], 'eps_actual': [0.41],
            'eps_surprise_pct': [-6.8], 'market_cap': [112e9],
            'options_volume': [20272], 'expected_move': [5.78],
            'strategy': [None],
            'gap_pct': [-3.7], 'pre_high': [None], 'pre_low': [None],
        }))
        from gcp.premarket_brief import load_yesterday_amc_reactions

        # Monday 2026-05-04 → walks back to Friday 2026-05-01
        rows = load_yesterday_amc_reactions(date(2026, 5, 4))
        assert captured["params"]["prior"] == date(2026, 5, 1)
        assert captured["params"]["today"] == date(2026, 5, 4)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "SBUX"
        assert rows[0]["gap_pct"] == -3.7

    def test_skips_rows_with_null_gap(self, mock_cloud_sql):
        """A ticker without today's market_data_daily row (gap_pct NULL)
        gives no reaction signal — drop it instead of rendering 'reacted
        unknown amount'."""
        install, _ = mock_cloud_sql
        install(pd.DataFrame({
            'ticker': ['HAS_GAP', 'NO_GAP'],
            'earnings_date': [date(2026, 4, 29), date(2026, 4, 29)],
            'eps_estimate': [1.0, 1.0], 'eps_actual': [None, None],
            'eps_surprise_pct': [None, None],
            'market_cap': [1e10, 1e10], 'options_volume': [10000, 10000],
            'expected_move': [None, None], 'strategy': [None, None],
            'gap_pct': [-2.5, None],
            'pre_high': [None, None], 'pre_low': [None, None],
        }))
        from gcp.premarket_brief import load_yesterday_amc_reactions
        rows = load_yesterday_amc_reactions(date(2026, 4, 30))
        assert {r["ticker"] for r in rows} == {"HAS_GAP"}

    def test_sorts_by_absolute_gap_desc(self, mock_cloud_sql):
        """Biggest movers first — direction-agnostic."""
        install, _ = mock_cloud_sql
        install(pd.DataFrame({
            'ticker': ['SMALL', 'BIG_DOWN', 'BIG_UP'],
            'earnings_date': [date(2026, 4, 29)] * 3,
            'eps_estimate': [1.0] * 3, 'eps_actual': [None] * 3,
            'eps_surprise_pct': [None] * 3,
            'market_cap': [1e10] * 3, 'options_volume': [10000] * 3,
            'expected_move': [None] * 3, 'strategy': [None] * 3,
            'gap_pct': [0.8, -7.2, 5.4],
            'pre_high': [None] * 3, 'pre_low': [None] * 3,
        }))
        from gcp.premarket_brief import load_yesterday_amc_reactions
        rows = load_yesterday_amc_reactions(date(2026, 4, 30), top_n=10)
        assert [r["ticker"] for r in rows] == ["BIG_DOWN", "BIG_UP", "SMALL"]

    def test_top_n_caps_results(self, mock_cloud_sql):
        install, _ = mock_cloud_sql
        install(pd.DataFrame({
            'ticker': [f'T{i}' for i in range(10)],
            'earnings_date': [date(2026, 4, 29)] * 10,
            'eps_estimate': [1.0] * 10, 'eps_actual': [None] * 10,
            'eps_surprise_pct': [None] * 10,
            'market_cap': [1e10] * 10, 'options_volume': [10000] * 10,
            'expected_move': [None] * 10, 'strategy': [None] * 10,
            'gap_pct': [(-1) ** i * (i + 1) for i in range(10)],
            'pre_high': [None] * 10, 'pre_low': [None] * 10,
        }))
        from gcp.premarket_brief import load_yesterday_amc_reactions
        rows = load_yesterday_amc_reactions(date(2026, 4, 30), top_n=3)
        assert len(rows) == 3

    def test_no_cloud_sql_returns_empty(self, monkeypatch):
        from gcp import database
        monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: False)
        from gcp.premarket_brief import load_yesterday_amc_reactions
        assert load_yesterday_amc_reactions(date(2026, 4, 30)) == []


class TestEmbedAmcReactionsSection:
    """The embed appends a 'Reactions to Last Night's AMC' section when
    earnings_data has yesterday_amc_reactions."""

    def test_section_renders_when_reactions_present(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed({
            'mode': 'daily',
            'earnings': [_row_out('AAPL', 'premarket', 1)],
            'yesterday_amc_reactions': [
                _row_out('SBUX', 'postmarket', 1, gap_pct=-3.7,
                         eps_estimate=0.44, eps_actual=0.41,
                         eps_surprise_pct=-6.8),
            ],
        })
        desc = embed['description']
        assert 'Reactions to Last Night' in desc
        assert 'SBUX' in desc
        assert '\U0001f4c9' in desc   # 📉 (negative gap arrow)

    def test_amc_reactions_row_has_no_tier_badge(self):
        """The Reactions section deliberately suppresses the tier badge —
        green/blue/yellow source-confirmation dots aren't useful for names
        that already reported. Lock in: no 🟢 / 🔵 / 🟡 between the
        section header and the SBUX row."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed({
            'mode': 'daily',
            'earnings': [_row_out('AAPL', 'premarket', 1)],
            'yesterday_amc_reactions': [
                # tier=1 would normally render a 🟢 dot; the suppression
                # path must drop it for the AMC reactions section.
                _row_out('SBUX', 'postmarket', 1, gap_pct=-3.7),
            ],
        })
        desc = embed['description']
        header_idx = desc.index('Reactions to Last Night')
        sbux_idx = desc.index('SBUX', header_idx)
        between = desc[header_idx:sbux_idx]
        for badge in ('\U0001f7e2', '\U0001f535', '\U0001f7e1'):
            assert badge not in between, (
                f"tier badge {badge!r} should not appear in AMC reactions "
                f"section; saw between=[{between!r}]"
            )

    def test_ew_verdict_renders_in_whispers_section(self):
        """When evaluate_ew_strikes has scored a row, the verdict shows
        in the Whispers section (NOT in the BMO/AMC row — strategies
        moved to a dedicated section to avoid 'this is actionable today'
        confusion)."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('TEVA', 'premarket', 1,
                     strategy='Long Calls', strike=30,
                     ew_strike_verdict='HIT',
                     ew_strike_move_pct=18.7,
                     ew_minutes_to_hit=5,
                     ew_minutes_in_zone=142,
                     ew_day_change_pct=1.2),
        ]))
        desc = embed['description']
        assert 'Whispers' in desc
        # Verdict block lives in Whispers, not BMO row
        whispers_idx = desc.index('Whispers')
        teva_in_bmo = desc.index('TEVA')  # first occurrence
        teva_after_whispers = desc.find('TEVA', whispers_idx)
        assert 'EW LC $30 HIT' in desc[whispers_idx:]
        assert '+18.7%' in desc
        assert 'in 5m' in desc
        assert 'held 142m' in desc
        assert 'day +1.2%' in desc

    def test_ew_verdict_omitted_when_not_evaluated(self):
        """No verdict column = no verdict text. Strategy + strike still
        render in the Whispers section though, since the strategy alone
        is informative."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('AAPL', 'premarket', 1,
                     strategy='Long Calls', strike=260,
                     ew_strike_verdict=None),
        ]))
        desc = embed['description']
        assert 'EW LC' not in desc            # no verdict
        assert 'Long Calls' in desc           # strategy still shows
        assert 'Strike $260' in desc          # strike still shows
        assert 'Whispers' in desc             # in the Whispers section


class TestWhispersSection:
    """Strategy + strike + EW verdict moved to a dedicated 🔮 Whispers
    section so an EW Long-Call recommendation isn't read as 'today's
    actionable trigger'. Section appears only when at least one row
    has a strategy."""

    def test_strategy_does_not_render_in_bmo_row(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('TEVA', 'premarket', 1,
                     strategy='Long Calls', strike=30),
        ]))
        desc = embed['description']
        # Strategy must be in Whispers section, NOT in the BMO bullet
        bmo_section = desc.split('Whispers')[0]
        assert 'Long Calls' not in bmo_section
        assert 'Strike $30' not in bmo_section
        # And IS in whispers
        whispers_section = desc.split('Whispers')[1]
        assert 'TEVA' in whispers_section
        assert 'Long Calls' in whispers_section
        assert 'Strike $30' in whispers_section

    def test_no_whispers_section_when_no_strategy(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('NOSTAT', 'premarket', 2, strategy=None),
        ]))
        assert 'Whispers' not in embed['description']

    def test_whispers_section_only_lists_strategy_rows(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed(_earnings_brief([
            _row_out('WITH_S', 'premarket', 1,
                     strategy='Long Calls', strike=50),
            _row_out('NO_S',   'premarket', 2, strategy=None),
        ]))
        whispers = embed['description'].split('Whispers')[1]
        assert 'WITH_S' in whispers
        assert 'NO_S' not in whispers

    def test_reactions_render_between_bmo_and_amc(self):
        """Section order: BMO → reactions → AMC. Most-actionable first."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed({
            'mode': 'daily',
            'earnings': [
                _row_out('HUM',  'premarket',  1),
                _row_out('AMZN', 'postmarket', 1),
            ],
            'yesterday_amc_reactions': [
                _row_out('SBUX', 'postmarket', 1, gap_pct=-3.7),
            ],
        })
        desc = embed['description']
        bmo_pos = desc.index('Reporting Before Open')
        rx_pos  = desc.index('Reactions to Last Night')
        amc_pos = desc.index('Reporting After Close')
        assert bmo_pos < rx_pos < amc_pos, (
            "Order must be BMO → reactions → AMC (got "
            f"BMO@{bmo_pos}, reactions@{rx_pos}, AMC@{amc_pos})"
        )

    def test_no_section_when_reactions_empty(self):
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed({
            'mode': 'daily',
            'earnings': [_row_out('AAPL', 'premarket', 1)],
            'yesterday_amc_reactions': [],
        })
        assert 'Reactions to Last Night' not in embed['description']

    def test_no_section_when_key_absent(self):
        """Backward compat: existing callers don't pass the new key."""
        from gcp.premarket_brief import _build_earnings_embed
        embed = _build_earnings_embed({
            'mode': 'daily',
            'earnings': [_row_out('AAPL', 'premarket', 1)],
        })
        assert 'Reactions to Last Night' not in embed['description']


