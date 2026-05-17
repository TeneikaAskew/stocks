"""Hermetic unit tests for ``gcp/earnings_reactions_brief.py``.

The brief drives a daily Discord post ranking upcoming earnings reporters by
their historical post-earnings reaction pattern. Correctness invariants:

  - 12-quarter window aggregation: rates are honest fractions over
    non-NULL rows only; pre-earnings drift comes from the most recent row.
  - No look-ahead: history queries filter on fiscal_date_ending < report.
  - I/O shape: a brief over N reporters issues a FIXED number of queries
    (not O(N)) — the batched-by-ticker contract from CLAUDE.md Rule 0.4.
  - Classification rule: SELL / BUY / FAILED-GAP / INSUFFICIENT thresholds.
  - No silent fallbacks (CLAUDE.md 3.7): a ticker with < 4 quarters of
    history is classified INSUFFICIENT-HISTORY and rendered explicitly,
    never imputed to 0.
  - Embed structure: 4 (or 5) sections, valid Discord embed shape.

All DB access is monkeypatched — no live Cloud SQL.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from gcp import earnings_reactions_brief as erb
from gcp.earnings_reactions_brief import (
    CLASS_BUY,
    CLASS_FAILED_GAP,
    CLASS_INSUFFICIENT,
    CLASS_SELL,
    LOOKBACK_QUARTERS,
    MIN_QUARTERS_FOR_CLASSIFICATION,
    TickerReactionContext,
    aggregate_history,
    build_discord_message,
    classify_context,
    generate_brief,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────


def _reaction_row(
    ticker="AAPL",
    fiscal="2026-03-31",
    gap=3.0,
    consistent=True,
    reversal=False,
    drift=1.0,
    sustain=2.0,
    basis="AMC",
):
    """One synthetic earnings_reactions row (dict, as query_to_dataframe
    would yield via DataFrame.to_dict)."""
    return {
        "ticker": ticker,
        "fiscal_date_ending": fiscal,
        "reaction_basis": basis,
        "reaction_gap_pct": gap,
        "direction_consistent_5d": consistent,
        "is_reversal_5d": reversal,
        "pre_earnings_drift_10d_pct": drift,
        "sustain_5d_pct": sustain,
    }


@pytest.fixture
def mock_db(monkeypatch):
    """Install fake DB query functions and capture every SQL call.

    Returns ``(install, captured)``. ``install`` takes keyword DataFrames
    keyed by the table being queried; ``captured`` records each SQL string
    and params so tests can assert on query COUNT and shape.
    """
    from gcp import database

    captured = {"sqls": [], "params": []}

    def install(calendar=None, reactions=None, insider=None):
        cal_df = calendar if calendar is not None else pd.DataFrame()
        rx_df = reactions if reactions is not None else pd.DataFrame()
        ins_df = insider if insider is not None else pd.DataFrame()

        def fake_query(sql, params=None):
            captured["sqls"].append(sql)
            captured["params"].append(dict(params or {}))
            low = sql.lower()
            if "from earnings_calendar" in low:
                return cal_df.copy()
            if "from earnings_reactions" in low:
                return rx_df.copy()
            if "from insider_transactions" in low:
                return ins_df.copy()
            return pd.DataFrame()

        monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
        monkeypatch.setattr(database, "query_to_dataframe", fake_query)

    return install, captured


# ──────────────────────────────────────────────────────────────────────
# 12-quarter window aggregation
# ──────────────────────────────────────────────────────────────────────


def test_aggregate_history_basic_rates():
    """Rates are fractions over the rows; pre-drift is the newest row."""
    rows = [
        _reaction_row(fiscal="2026-03-31", gap=4.0, consistent=True,
                      reversal=False, drift=3.5, sustain=2.0),
        _reaction_row(fiscal="2025-12-31", gap=-2.0, consistent=True,
                      reversal=False, drift=1.0, sustain=-1.0),
        _reaction_row(fiscal="2025-09-30", gap=1.0, consistent=False,
                      reversal=True, drift=0.0, sustain=0.5),
        _reaction_row(fiscal="2025-06-30", gap=-3.0, consistent=False,
                      reversal=True, drift=-1.0, sustain=-2.0),
    ]
    agg = aggregate_history(rows)

    assert agg["n_quarters"] == 4
    # 2 of 4 consistent.
    assert agg["hist12q_consistent_rate"] == pytest.approx(0.5)
    # 2 of 4 reversed.
    assert agg["hist12q_reversal_rate"] == pytest.approx(0.5)
    # |gap|: (4+2+1+3)/4 = 2.5
    assert agg["hist12q_avg_abs_gap_pct"] == pytest.approx(2.5)
    # gap up: 2 of 4 positive.
    assert agg["hist12q_gap_up_rate"] == pytest.approx(0.5)
    # sustain mean: (2 - 1 + 0.5 - 2)/4 = -0.125
    assert agg["hist12q_avg_sustain_5d_pct"] == pytest.approx(-0.125)
    # pre-drift = most recent row's drift (rows are newest-first).
    assert agg["pre_earnings_drift_10d_pct"] == pytest.approx(3.5)


def test_aggregate_history_ignores_null_flags():
    """A NULL flag is excluded from BOTH numerator and denominator —
    the rate stays an honest fraction, no NULL→0 imputation."""
    rows = [
        _reaction_row(consistent=True, reversal=None),
        _reaction_row(consistent=None, reversal=True),
        _reaction_row(consistent=True, reversal=False),
    ]
    agg = aggregate_history(rows)
    # consistent: 2 of 2 non-NULL → 1.0 (the None row is dropped).
    assert agg["hist12q_consistent_rate"] == pytest.approx(1.0)
    # reversal: 1 of 2 non-NULL → 0.5.
    assert agg["hist12q_reversal_rate"] == pytest.approx(0.5)


def test_aggregate_history_empty_returns_none_not_zero():
    """No rows → every aggregate is None (not 0) — CLAUDE.md 3.7."""
    agg = aggregate_history([])
    assert agg["n_quarters"] == 0
    assert agg["hist12q_consistent_rate"] is None
    assert agg["hist12q_avg_abs_gap_pct"] is None
    assert agg["hist12q_reversal_rate"] is None
    assert agg["pre_earnings_drift_10d_pct"] is None
    assert agg["hist12q_avg_sustain_5d_pct"] is None
    assert agg["hist12q_gap_up_rate"] is None


def test_aggregate_history_drift_falls_through_to_first_non_null():
    """When the newest row's drift is NULL, the next non-NULL row wins."""
    rows = [
        _reaction_row(fiscal="2026-03-31", drift=None),
        _reaction_row(fiscal="2025-12-31", drift=2.7),
    ]
    agg = aggregate_history(rows)
    assert agg["pre_earnings_drift_10d_pct"] == pytest.approx(2.7)


# ──────────────────────────────────────────────────────────────────────
# Classification rule
# ──────────────────────────────────────────────────────────────────────


def _ctx(n_q=12, consistent=None, reversal=None, drift=None):
    c = TickerReactionContext(ticker="TST")
    c.n_quarters = n_q
    c.hist12q_consistent_rate = consistent
    c.hist12q_reversal_rate = reversal
    c.pre_earnings_drift_10d_pct = drift
    return c


def test_classify_insufficient_history():
    """< 4 quarters → INSUFFICIENT, surfaced explicitly (not imputed)."""
    c = _ctx(n_q=MIN_QUARTERS_FOR_CLASSIFICATION - 1,
             consistent=0.9, reversal=0.0, drift=0.0)
    label, reason = classify_context(c)
    assert label == CLASS_INSUFFICIENT
    assert "quarter" in reason
    assert not c.has_sufficient_history


def test_classify_failed_gap_high_reversal_dominates():
    """High reversal rate wins even when consistency is also high."""
    c = _ctx(consistent=0.90, reversal=0.50, drift=5.0)
    label, _ = classify_context(c)
    assert label == CLASS_FAILED_GAP


def test_classify_sell_the_news():
    """Hot upside pre-drift + high consistency → sell-the-news."""
    c = _ctx(consistent=0.75, reversal=0.10, drift=4.0)
    label, reason = classify_context(c)
    assert label == CLASS_SELL
    assert "priced in" in reason


def test_classify_buy_the_news():
    """High consistency with no upside pre-run → buy-the-news."""
    c = _ctx(consistent=0.75, reversal=0.10, drift=-1.0)
    label, _ = classify_context(c)
    assert label == CLASS_BUY


def test_classify_buy_the_news_when_drift_missing():
    """Missing drift counts as 'not hot' → still buy-the-news, not a crash."""
    c = _ctx(consistent=0.70, reversal=0.10, drift=None)
    label, _ = classify_context(c)
    assert label == CLASS_BUY


def test_classify_failed_gap_fallback_no_dominant_pattern():
    """Low consistency + low reversal → failed-gap fallback, reason names
    the missed thresholds (not a silent fallback)."""
    c = _ctx(consistent=0.30, reversal=0.10, drift=0.5)
    label, reason = classify_context(c)
    assert label == CLASS_FAILED_GAP
    assert "unreliable" in reason


# ──────────────────────────────────────────────────────────────────────
# No-history "explicit unavailable" path
# ──────────────────────────────────────────────────────────────────────


def test_no_history_ticker_is_explicit_not_fabricated():
    """A reporter with zero reaction history is classified INSUFFICIENT,
    its predictors stay None, and the embed line says so explicitly."""
    ctx = erb.build_ticker_context(
        reporter={"ticker": "NEWCO", "company_name": "New Co",
                  "earnings_time": "postmarket"},
        history_rows=[],
        insider=None,
        upcoming_report_date=date(2026, 5, 18),
    )
    assert ctx.classification == CLASS_INSUFFICIENT
    assert ctx.n_quarters == 0
    assert ctx.hist12q_consistent_rate is None
    assert ctx.insider_net_value_60d is None
    assert ctx.latest_reaction is None
    line = erb._predictor_line(ctx)
    assert "insufficient history" in line
    assert "NEWCO" in line


# ──────────────────────────────────────────────────────────────────────
# I/O shape — fixed query count regardless of reporter count
# ──────────────────────────────────────────────────────────────────────


def test_query_count_is_fixed_not_per_ticker(mock_db, monkeypatch):
    """A brief over many reporters issues a FIXED number of queries
    (2 calendar + 2 history + 2 insider = 6), proving the batched-by-
    ticker contract (CLAUDE.md Rule 0.4) — not O(N)."""
    monkeypatch.delenv("EARNINGS_BRIEF_AS_OF", raising=False)
    install, captured = mock_db

    # 20 reporters on the next session.
    cal = pd.DataFrame([
        {"ticker": f"TK{i:02d}", "company_name": f"Co {i}",
         "earnings_time": "postmarket"}
        for i in range(20)
    ])
    install(calendar=cal, reactions=pd.DataFrame(), insider=pd.DataFrame())

    generate_brief(analysis_date=date(2026, 5, 14))  # a Thursday

    # 2 calendar reads (next + last session) + 2 history + 2 insider.
    assert len(captured["sqls"]) == 6


def test_history_query_has_no_lookahead(mock_db):
    """The earnings_reactions query filters fiscal_date_ending < report."""
    install, captured = mock_db
    cal = pd.DataFrame([{"ticker": "AAPL", "company_name": "Apple",
                         "earnings_time": "postmarket"}])
    install(calendar=cal)

    generate_brief(analysis_date=date(2026, 5, 14))

    rx_sqls = [s for s in captured["sqls"]
               if "from earnings_reactions" in s.lower()]
    assert rx_sqls, "expected an earnings_reactions query"
    for s in rx_sqls:
        assert "fiscal_date_ending <" in s.lower()
    # The lookback window is the 12-quarter constant.
    rx_params = [p for s, p in zip(captured["sqls"], captured["params"])
                 if "from earnings_reactions" in s.lower()]
    assert all(p.get("lookback") == LOOKBACK_QUARTERS for p in rx_params)


# ──────────────────────────────────────────────────────────────────────
# End-to-end brief + embed structure
# ──────────────────────────────────────────────────────────────────────


def test_generate_brief_buckets_and_embed_structure(mock_db, monkeypatch):
    """End-to-end: reporters flow into the right buckets and the embed has
    the expected 4-section shape."""
    monkeypatch.delenv("EARNINGS_BRIEF_AS_OF", raising=False)
    install, _ = mock_db

    # Next session reporters: SELLER, BUYER, FADER, NEWBIE.
    cal = pd.DataFrame([
        {"ticker": "SELLER", "company_name": "Sell Co",
         "earnings_time": "postmarket"},
        {"ticker": "BUYER", "company_name": "Buy Co",
         "earnings_time": "premarket"},
        {"ticker": "FADER", "company_name": "Fade Co",
         "earnings_time": "postmarket"},
        {"ticker": "NEWBIE", "company_name": "New Co",
         "earnings_time": "postmarket"},
    ])

    # 12 quarters each for SELLER/BUYER/FADER; NEWBIE gets only 2.
    rows = []
    # SELLER: hot upside pre-drift + high consistency, low reversal.
    for q in range(12):
        rows.append(_reaction_row(
            ticker="SELLER", fiscal=f"20{23 + q // 4}-0{1 + 3 * (q % 4)}-28"[:10],
            gap=3.0, consistent=True, reversal=False, drift=4.5))
    # BUYER: high consistency, no upside pre-run.
    for q in range(12):
        rows.append(_reaction_row(
            ticker="BUYER", fiscal=f"20{23 + q // 4}-0{1 + 3 * (q % 4)}-28"[:10],
            gap=2.0, consistent=True, reversal=False, drift=-1.0))
    # FADER: high reversal rate.
    for q in range(12):
        rows.append(_reaction_row(
            ticker="FADER", fiscal=f"20{23 + q // 4}-0{1 + 3 * (q % 4)}-28"[:10],
            gap=2.0, consistent=False, reversal=True, drift=0.0))
    # NEWBIE: only 2 quarters → insufficient.
    for q in range(2):
        rows.append(_reaction_row(
            ticker="NEWBIE", fiscal=f"2026-0{1 + 3 * q}-28",
            gap=1.0, consistent=True, reversal=False, drift=0.0))
    rx = pd.DataFrame(rows)

    install(calendar=cal, reactions=rx, insider=pd.DataFrame())

    brief = generate_brief(analysis_date=date(2026, 5, 14))

    sell = {c.ticker for c in brief["sell_the_news"]}
    buy = {c.ticker for c in brief["buy_the_news"]}
    fail = {c.ticker for c in brief["failed_gap"]}
    insuf = {c.ticker for c in brief["insufficient"]}
    assert "SELLER" in sell
    assert "BUYER" in buy
    assert "FADER" in fail
    assert "NEWBIE" in insuf

    msg = build_discord_message(brief)
    assert "embeds" in msg
    embed = msg["embeds"][0]
    assert embed["title"].startswith("Earnings Reactions Brief")
    # 4 fixed sections + the insufficient-history section.
    assert len(embed["fields"]) == 5
    # Embed must be within Discord's per-embed char budget.
    import json as _json
    assert len(_json.dumps(embed)) <= erb.MAX_EMBED_CHARS


def test_build_discord_message_handles_empty_brief():
    """An empty session still renders a valid 4-field embed (no crash)."""
    brief = {
        "analysis_date": date(2026, 5, 17),
        "next_session": date(2026, 5, 18),
        "last_session": date(2026, 5, 15),
        "last_session_contexts": [],
        "sell_the_news": [],
        "buy_the_news": [],
        "failed_gap": [],
        "insufficient": [],
    }
    msg = build_discord_message(brief)
    embed = msg["embeds"][0]
    assert len(embed["fields"]) == 4
    assert all(f["value"] == "_none_" for f in embed["fields"])


def test_to_dict_is_json_serialisable():
    """TickerReactionContext.to_dict() yields a JSON-safe dict (dates →
    strings) so a website surface can consume it."""
    import json as _json
    ctx = erb.build_ticker_context(
        reporter={"ticker": "AAPL", "company_name": "Apple",
                  "earnings_time": "postmarket"},
        history_rows=[_reaction_row(ticker="AAPL")],
        insider={"net_value": 1_250_000.0, "txn_count": 4},
        upcoming_report_date=date(2026, 5, 18),
    )
    d = ctx.to_dict()
    _json.dumps(d)  # must not raise
    assert d["ticker"] == "AAPL"
    assert d["insider_net_value_60d"] == 1_250_000.0
