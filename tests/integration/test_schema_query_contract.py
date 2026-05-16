"""Real-SQL contract tests — production queries against the real schema.

Why this file exists
--------------------
The hermetic tests in `tests/test_platform_api.py` mock the data layer:
they hand the endpoint a DataFrame, so they cannot see a bug *in the SQL
string itself*. If a query says `SELECT alert_time` but the column is
`alert_ts`, or references a column a schema migration renamed, the mock
still returns clean data and the test passes green — while production
500s.

This session alone hit three such drift bugs via `db-query.yml`:
`alert_time` (real column: `alert_ts`), and `run_kind` / `written_at`
(columns that do not exist). Every one would pass the mocked tests.

These tests apply the real `gcp/schema.sql` to an ephemeral Postgres,
seed a few synthetic rows, and run the production query functions
end-to-end. A drifted column makes the query return nothing → the
summarizer reports `available=False` → the test fails. The CI log shows
the underlying `query_to_dataframe` warning with the real SQLSTATE.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pytest

# Skip the whole file unless a test Postgres is wired up. The main CI
# `Run Tests` job passes --ignore=tests/integration, so this guard only
# matters for a local `pytest tests/` run with no DB.
pytestmark = pytest.mark.skipif(
    not os.environ.get("DB_HOST"),
    reason="integration tests need a Postgres (DB_HOST) — see the "
    "integration-tests CI job in backtest-pipeline.yml",
)


def test_schema_core_tables_exist(run_sql):
    """`gcp/schema.sql` applied cleanly and created the core tables.

    A blunt smoke test: if the schema file is broken (bad DDL, a failed
    DO-block), the `psql -f` step fails before pytest even runs — but
    this also catches a table being silently dropped from the file."""
    df = run_sql(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public'"
    )
    present = set(df["table_name"])
    for expected in (
        "market_data_daily",
        "market_data_intraday",
        "signal_alerts",
        "etf_options_snapshots",
        "premarket_analysis",
        "insight_reports",
        "daily_rates",
        "earnings_calendar",
    ):
        assert expected in present, f"{expected} missing from applied schema"


def test_summarize_market_context_real_schema(clean_db, seed):
    """`summarize_market_context` SELECTs ~26 columns from
    `market_data_daily`. Run it against the real table — a renamed
    indicator column would make the query return empty."""
    from lib.agents import summarizers

    seed("market_data_daily", [{
        "ticker": "SPY",
        "date": date(2026, 5, 12),
        "open": 500.0, "high": 506.0, "low": 499.0, "close": 505.0,
        "volume": 70_000_000,
        "sma_200": 480.0, "ema_20": 500.0, "ema_50": 495.0,
        "rsi_14": 61.0, "volatility_20d": 0.15, "price_vs_ema20": 0.010,
    }])

    out = summarizers.summarize_market_context("SPY")
    assert out["available"] is True, (
        "query returned nothing — likely a market_data_daily column "
        "renamed out from under summarize_market_context's SELECT"
    )
    assert out["close"] == 505.0
    assert out["regime"] == "trending_up"      # close>sma_200 & price_vs_ema20>0
    assert out["vol_tag"] == "normal"          # 0.12 <= 0.15 < 0.22
    assert out["above_sma_200"] is True


def test_summarize_signals_history_real_schema(clean_db, seed):
    """`summarize_signals_history` SELECTs from `signal_alerts` filtering
    on `alert_ts`. This is the exact table whose `alert_ts` column was
    mistyped `alert_time` in an ad-hoc query this session — a real
    contract test on it is the highest-value case in this file."""
    from lib.agents import summarizers

    recent = datetime.now(timezone.utc) - timedelta(days=1)
    seed("signal_alerts", [
        {"ticker": "IWM", "alert_ts": recent, "alert_date": recent.date(),
         "direction": "CALL", "strength_label": "strong",
         "base_score": 4.0, "total_score": 4.5},
        {"ticker": "IWM", "alert_ts": recent - timedelta(hours=2),
         "alert_date": recent.date(), "direction": "PUT",
         "strength_label": "weak", "base_score": 2.0, "total_score": 2.0},
    ])

    out = summarizers.summarize_signals_history("IWM")
    assert out["available"] is True
    assert out["total_alerts"] == 2
    assert out["call_count"] == 1
    assert out["put_count"] == 1


def test_summarize_options_flow_real_schema(clean_db, seed):
    """`summarize_options_flow` SELECTs from `etf_options_snapshots` with
    a `MAX(snapshot_date)` correlated subquery — a JOIN-shaped query
    worth running for real."""
    from lib.agents import summarizers

    snap = date(2026, 5, 12)
    snap_ts = datetime(2026, 5, 12, 20, 0, 0, tzinfo=timezone.utc)  # NOT NULL
    rows = [
        {"ticker": "SPY", "snapshot_date": snap, "snapshot_ts": snap_ts,
         "expiration": date(2026, 5, 30),
         "strike": 500.0, "option_type": "calls", "volume": 10_000,
         "open_interest": 50_000, "implied_volatility": 0.18, "delta": 0.55,
         "data_source": "alphavantage"},
        {"ticker": "SPY", "snapshot_date": snap, "snapshot_ts": snap_ts,
         "expiration": date(2026, 5, 30),
         "strike": 500.0, "option_type": "puts", "volume": 8_000,
         "open_interest": 40_000, "implied_volatility": 0.22, "delta": -0.45,
         "data_source": "alphavantage"},
    ]
    seed("etf_options_snapshots", rows)

    # as_of one trading day after the snapshot → fresh (staleness guard OK)
    out = summarizers.summarize_options_flow("SPY", as_of=date(2026, 5, 13))
    assert out["available"] is not False, (
        f"summarize_options_flow returned unavailable: {out.get('reason')}"
    )
    assert out["call_volume"] == 10_000
    assert out["put_volume"] == 8_000


def test_summarize_gamma_levels_real_schema(clean_db, seed):
    """`summarize_gamma_levels` reads the option chain and runs
    `lib.gamma.build_summary`. Exercises the chain SELECT against the
    real `etf_options_snapshots` columns (gamma/vega/bid/ask/mark/…)."""
    from lib.agents import summarizers

    snap = date(2026, 5, 12)
    snap_ts = datetime(2026, 5, 12, 20, 0, 0, tzinfo=timezone.utc)  # NOT NULL
    exp = date(2026, 5, 30)
    rows = []
    for strike, opt, oi, dlt in [
        (495.0, "puts", 5000, -0.30), (500.0, "calls", 1500, 0.50),
        (500.0, "puts", 1500, -0.50), (505.0, "calls", 5000, 0.30),
    ]:
        rows.append({
            "ticker": "SPY", "snapshot_date": snap, "snapshot_ts": snap_ts,
            "expiration": exp,
            "strike": strike, "option_type": opt, "open_interest": oi,
            "gamma": 0.05, "vega": 0.10, "delta": dlt,
            "bid": 1.10, "ask": 1.20, "mark": 1.15, "last_price": 1.15,
            "data_source": "alphavantage",
        })
    seed("etf_options_snapshots", rows)

    out = summarizers.summarize_gamma_levels("SPY", as_of=date(2026, 5, 13))
    assert out["available"] is not False, (
        f"summarize_gamma_levels returned unavailable: {out.get('reason')}"
    )
    assert out["chain_size"] == 4
    assert "regime" in out
