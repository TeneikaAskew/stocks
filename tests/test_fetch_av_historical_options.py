"""Unit tests for `gcp/fetchers/fetch_av_historical_options.py`.

Production fetcher that writes to two source-of-truth stores
(Cloud SQL `etf_options_snapshots` + GCS parquet). Tests focus on:
    - `fetch_av_options` rate-limit / error response handling
    - `_normalize_av_response` schema coercion + column rename
    - `process_ticker` dedup before upsert (AV occasionally returns
      duplicate contracts — same conflict_cols would crash UPSERT)
    - `_weekday_range` skipping weekends in backfill mode

No live AV API, no live Cloud SQL/GCS — every external call is patched.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────
# fetch_av_options — error / rate-limit handling
# ──────────────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, json_data, ok=True):
        self._json = json_data
        self.ok = ok

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http error")

    def json(self):
        return self._json


def test_fetch_av_options_returns_empty_on_rate_limit_message(monkeypatch):
    """AV returns `{"Information": "...rate limit..."}` when over quota.
    Caller must NOT crash and NOT pass a malformed df downstream."""
    from gcp.fetchers import fetch_av_historical_options as mod

    fake = _FakeResponse({
        "Information": "Our standard API rate limit is 5 requests per minute"
    })
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: fake)

    df = mod.fetch_av_options("SPY", "2026-04-25", "fake-key")
    assert df.empty
    assert isinstance(df, pd.DataFrame)


def test_fetch_av_options_returns_empty_on_no_data(monkeypatch):
    """`message=success` but `data=[]` → empty df, no crash."""
    from gcp.fetchers import fetch_av_historical_options as mod

    fake = _FakeResponse({
        "message": "success",
        "endpoint": "Historical Options",
        "data": [],
    })
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: fake)

    df = mod.fetch_av_options("SPY", "2026-04-25", "fake-key")
    assert df.empty


def test_fetch_av_options_returns_empty_on_http_exception(monkeypatch):
    """Network exception → empty df, logged. The job-level loop tolerates
    per-ticker failures so one bad name doesn't take down the run."""
    from gcp.fetchers import fetch_av_historical_options as mod

    def boom(*a, **k):
        raise ConnectionError("network down")

    monkeypatch.setattr(mod.requests, "get", boom)
    df = mod.fetch_av_options("SPY", "2026-04-25", "fake-key")
    assert df.empty


def test_fetch_av_options_returns_normalized_df_on_success(monkeypatch):
    from gcp.fetchers import fetch_av_historical_options as mod

    fake_payload = {
        "message": "success",
        "endpoint": "Historical Options",
        "data": [
            {
                "contractID": "SPY260425C00500000",
                "type": "call",
                "expiration": "2026-04-30",
                "strike": "500.00",
                "last": "1.25",
                "mark": "1.30",
                "bid": "1.25",
                "ask": "1.35",
                "volume": "120",
                "open_interest": "1500",
                "implied_volatility": "0.18",
                "delta": "0.50",
                "gamma": "0.02",
                "theta": "-0.05",
                "vega": "0.10",
                "rho": "0.01",
            },
        ],
    }
    monkeypatch.setattr(
        mod.requests, "get", lambda *a, **k: _FakeResponse(fake_payload)
    )

    df = mod.fetch_av_options("spy", "2026-04-25", "fake-key")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["ticker"] == "SPY"  # uppercased
    assert row["data_source"] == "alphavantage"
    assert row["market_session"] == "EOD"
    assert row["option_type"] == "calls"  # call → calls
    assert row["strike"] == 500.0  # numeric coercion
    assert row["last_price"] == 1.25  # column renamed
    assert row["snapshot_date"] == date(2026, 4, 25)


# ──────────────────────────────────────────────────────────────────────
# _normalize_av_response — schema coercion
# ──────────────────────────────────────────────────────────────────────


def test_normalize_drops_rows_missing_required_keys():
    """A row with no expiration/strike/option_type can't satisfy the
    Cloud SQL UPSERT conflict key — drop it."""
    from gcp.fetchers.fetch_av_historical_options import _normalize_av_response

    raw = pd.DataFrame([
        # Good row
        {"type": "call", "expiration": "2026-04-30", "strike": "500.0"},
        # Missing strike — drops
        {"type": "put", "expiration": "2026-04-30"},
        # Missing expiration — drops
        {"type": "call", "strike": "510.0"},
    ])
    out = _normalize_av_response(raw, "SPY", "2026-04-25")
    assert len(out) == 1
    assert out.iloc[0]["option_type"] == "calls"


def test_normalize_coerces_numeric_strings():
    """Greeks/strikes arrive as strings from the JSON API; they must be
    numeric for SQL/parquet writers."""
    from gcp.fetchers.fetch_av_historical_options import _normalize_av_response

    raw = pd.DataFrame([{
        "type": "call", "expiration": "2026-04-30", "strike": "500.0",
        "last": "1.25", "mark": "1.30", "bid": "1.25", "ask": "1.35",
        "volume": "100", "open_interest": "1000",
        "delta": "0.50", "gamma": "0.02",
    }])
    out = _normalize_av_response(raw, "SPY", "2026-04-25")
    for col in ("strike", "last_price", "mark", "bid", "ask",
                "volume", "open_interest", "delta", "gamma"):
        # numpy/pandas numeric dtypes (int64, float64, etc.)
        assert pd.api.types.is_numeric_dtype(out[col])
    # Coerce-failure → NaN, not crash
    raw2 = pd.DataFrame([{
        "type": "put", "expiration": "2026-04-30", "strike": "500",
        "delta": "n/a",
    }])
    out2 = _normalize_av_response(raw2, "SPY", "2026-04-25")
    assert pd.isna(out2.iloc[0]["delta"])


def test_normalize_uppercases_ticker_and_lowercases_option_type():
    """Defensive — symbol normalisation must not depend on caller."""
    from gcp.fetchers.fetch_av_historical_options import _normalize_av_response

    raw = pd.DataFrame([
        {"type": "CALL", "expiration": "2026-04-30", "strike": "500.0"},
        {"type": "Put",  "expiration": "2026-04-30", "strike": "495.0"},
    ])
    out = _normalize_av_response(raw, "spy", "2026-04-25")
    assert (out["ticker"] == "SPY").all()
    assert sorted(out["option_type"].unique().tolist()) == ["calls", "puts"]


# ──────────────────────────────────────────────────────────────────────
# process_ticker — dedup + upsert + GCS upload
# ──────────────────────────────────────────────────────────────────────


def test_process_ticker_dedups_before_upsert(monkeypatch):
    """AV occasionally returns duplicate contracts within the same
    response (audit notes: 2017-09-15, 2020-06-22). The conflict-cols
    `(ticker, snapshot_ts, option_type, expiration, strike)` would
    cause Postgres ON CONFLICT to error on duplicate within batch.
    The fetcher must drop dups before upsert."""
    from gcp.fetchers import fetch_av_historical_options as mod

    # Two rows with identical conflict-key (same strike+expiration+type)
    fake_payload = {
        "message": "success",
        "endpoint": "Historical Options",
        "data": [
            {"contractID": "X1", "type": "call",
             "expiration": "2026-04-30", "strike": "500", "last": "1.0"},
            {"contractID": "X1-dup", "type": "call",
             "expiration": "2026-04-30", "strike": "500", "last": "1.5"},
        ],
    }
    monkeypatch.setattr(
        mod.requests, "get", lambda *a, **k: _FakeResponse(fake_payload)
    )

    upserts = []
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(
        mod, "upsert_dataframe",
        lambda df, table, conflict_cols: upserts.append(
            (len(df), table, list(conflict_cols))
        ),
    )

    mod.process_ticker("SPY", "2026-04-25", api_key="k")

    assert len(upserts) == 1
    n_rows, table, conflict_cols = upserts[0]
    assert n_rows == 1, "duplicate contract was deduped pre-upsert"
    assert table == "etf_options_snapshots"
    assert conflict_cols == [
        "ticker", "snapshot_ts", "option_type", "expiration", "strike",
    ]


def test_process_ticker_skip_existing_short_circuits(monkeypatch):
    """`--skip-existing` queries Cloud SQL first; if a row exists, no
    AV call is made (saves rate-limit budget on retries)."""
    from gcp.fetchers import fetch_av_historical_options as mod

    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(
        "gcp.database.query_to_dataframe",
        lambda *a, **k: pd.DataFrame([{"1": 1}]),  # row exists
    )
    # If AV is hit, this raises — proves the short-circuit works.
    monkeypatch.setattr(
        mod.requests, "get",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called"))
    )
    # Should return without touching AV
    mod.process_ticker(
        "SPY", "2026-04-25", api_key="k", skip_existing=True
    )


def test_process_ticker_skips_when_av_returns_empty(monkeypatch):
    """No data from AV → no upsert, no crash."""
    from gcp.fetchers import fetch_av_historical_options as mod

    monkeypatch.setattr(
        mod.requests, "get",
        lambda *a, **k: _FakeResponse({
            "message": "success", "endpoint": "Historical Options", "data": []
        }),
    )
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)

    upserts = []
    monkeypatch.setattr(
        mod, "upsert_dataframe", lambda df, t, c: upserts.append(df),
    )

    mod.process_ticker("SPY", "2026-04-25", api_key="k")
    assert upserts == []


# ──────────────────────────────────────────────────────────────────────
# _weekday_range — backfill mode
# ──────────────────────────────────────────────────────────────────────


def test_weekday_range_skips_weekends():
    """Mon-Sun spans should drop Sat+Sun."""
    from gcp.fetchers.fetch_av_historical_options import _weekday_range

    # Mon 2026-04-20 → Sun 2026-04-26 (7 days)
    out = _weekday_range(date(2026, 4, 20), date(2026, 4, 26))
    assert out == [
        "2026-04-20",  # Mon
        "2026-04-21",  # Tue
        "2026-04-22",  # Wed
        "2026-04-23",  # Thu
        "2026-04-24",  # Fri
        # 25-26 = Sat-Sun, dropped
    ]


def test_weekday_range_all_weekend_returns_empty():
    """Sat → Sun → 0 weekdays."""
    from gcp.fetchers.fetch_av_historical_options import _weekday_range

    out = _weekday_range(date(2026, 4, 25), date(2026, 4, 26))
    assert out == []


def test_weekday_range_single_day():
    """start == end on a weekday → 1 day."""
    from gcp.fetchers.fetch_av_historical_options import _weekday_range

    out = _weekday_range(date(2026, 4, 22), date(2026, 4, 22))  # Wed
    assert out == ["2026-04-22"]


# ──────────────────────────────────────────────────────────────────────
# _resolve_start_from_latest — self-resuming start date
# ──────────────────────────────────────────────────────────────────────


def test_resolve_start_from_latest_uniform_coverage(monkeypatch):
    """All tickers at 2026-04-13 → start = 2026-04-14."""
    from gcp.fetchers import fetch_av_historical_options as mod

    monkeypatch.setattr(
        "gcp.database.query_to_dataframe",
        lambda *a, **k: pd.DataFrame([
            {"ticker": "SPY", "d": pd.Timestamp("2026-04-13")},
            {"ticker": "IWM", "d": pd.Timestamp("2026-04-13")},
        ]),
    )
    out = mod._resolve_start_from_latest(["SPY", "IWM"])
    assert out == date(2026, 4, 14)


def test_resolve_start_from_latest_uses_min_of_per_ticker_max(monkeypatch):
    """SPY/IWM/SPX through Apr 30, QQQ behind at Apr 16 → start = Apr 17.

    The whole point of MIN-of-per-ticker-MAX (Codex P1 #390): a single
    tail-behind ticker pulls the start back so its missing days get
    re-fetched, while the others' already-present days are skipped via
    per-(ticker, date) skip-existing in process_ticker.
    """
    from gcp.fetchers import fetch_av_historical_options as mod

    monkeypatch.setattr(
        "gcp.database.query_to_dataframe",
        lambda *a, **k: pd.DataFrame([
            {"ticker": "SPY", "d": pd.Timestamp("2026-04-30")},
            {"ticker": "IWM", "d": pd.Timestamp("2026-04-30")},
            {"ticker": "SPX", "d": pd.Timestamp("2026-04-30")},
            {"ticker": "QQQ", "d": pd.Timestamp("2026-04-16")},
        ]),
    )
    out = mod._resolve_start_from_latest(["SPY", "IWM", "SPX", "QQQ"])
    assert out == date(2026, 4, 17)


def test_resolve_start_from_latest_newly_added_ticker_excluded(monkeypatch):
    """A ticker with no rows yet drops out of the GROUP BY entirely.
    The remaining tickers' MIN(MAX) is used and the new ticker gets
    swept into the date range via per-(ticker, date) skip-existing."""
    from gcp.fetchers import fetch_av_historical_options as mod

    monkeypatch.setattr(
        "gcp.database.query_to_dataframe",
        lambda *a, **k: pd.DataFrame([
            {"ticker": "SPY", "d": pd.Timestamp("2026-04-30")},
            {"ticker": "IWM", "d": pd.Timestamp("2026-04-30")},
            # AVGO requested but absent from result → newly-added
        ]),
    )
    out = mod._resolve_start_from_latest(["SPY", "IWM", "AVGO"])
    assert out == date(2026, 5, 1)


def test_resolve_start_from_latest_no_rows_at_all_falls_back_to_today(monkeypatch):
    """All requested tickers have NULL MAX (none in the table yet) →
    start = today (caller can override with explicit --start-date)."""
    from gcp.fetchers import fetch_av_historical_options as mod

    monkeypatch.setattr(
        "gcp.database.query_to_dataframe",
        lambda *a, **k: pd.DataFrame(columns=["ticker", "d"]),
    )
    out = mod._resolve_start_from_latest(["NEW_TICKER"])
    assert out == date.today()


def test_resolve_start_from_latest_filters_null_d(monkeypatch):
    """A row with d=NaT should be ignored, not treated as the MIN."""
    from gcp.fetchers import fetch_av_historical_options as mod

    monkeypatch.setattr(
        "gcp.database.query_to_dataframe",
        lambda *a, **k: pd.DataFrame([
            {"ticker": "SPY", "d": pd.Timestamp("2026-04-30")},
            {"ticker": "BAD", "d": pd.NaT},
        ]),
    )
    out = mod._resolve_start_from_latest(["SPY", "BAD"])
    assert out == date(2026, 5, 1)  # SPY's MAX+1, BAD ignored


def test_resolve_start_from_latest_no_tickers():
    """Empty ticker list → today fallback (no SQL query attempted)."""
    from gcp.fetchers import fetch_av_historical_options as mod

    out = mod._resolve_start_from_latest([])
    assert out == date.today()


def test_resolve_start_from_latest_sql_shape(monkeypatch):
    """Verifies the SQL call uses GROUP BY + alphavantage filter + bind params."""
    from gcp.fetchers import fetch_av_historical_options as mod

    captured = {}

    def fake_query(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return pd.DataFrame([
            {"ticker": "SPY", "d": pd.Timestamp("2026-04-13")},
        ])

    monkeypatch.setattr("gcp.database.query_to_dataframe", fake_query)
    mod._resolve_start_from_latest(["SPY", "IWM", "QQQ"])

    assert "MAX(snapshot_date)" in captured["sql"]
    assert "GROUP BY ticker" in captured["sql"]
    assert "data_source = 'alphavantage'" in captured["sql"]
    assert captured["params"] == {"t0": "SPY", "t1": "IWM", "t2": "QQQ"}
