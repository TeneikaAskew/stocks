"""Tests for gcp.fetchers.fetch_av_historical_options_intraday.

The fetcher itself hits AV (external), so we test the pure transform —
_normalize_intraday_response — against a synthetic AV JSON shape. The
HTTP path is exercised by the production smoke test in the runbook.

Coverage:
  - snapshot_ts is the requested UTC timestamp (NOT 23:00 like EOD).
  - market_session = 'HISTORICAL_INTRADAY' (NOT 'EOD').
  - Filter to {0DTE, 1DTE} expirations.
  - Filter to ATM ± ATM_BAND strikes (uses underlying_price if present).
  - Drops rows with missing strike/option_type/expiration.
  - 'type' column maps 'call' → 'calls' / 'put' → 'puts'.
"""
from __future__ import annotations
from datetime import datetime, timezone

import pandas as pd
import pytest

from gcp.fetchers.fetch_av_historical_options_intraday import (
    ATM_BAND, EXPIRY_HORIZON_DAYS, _normalize_intraday_response, _to_et,
)


def _synthetic_av_intraday(spot: float = 450.0, snap_date: str = "2024-06-03"):
    """Build a synthetic AV-shaped DataFrame covering 0DTE + 1DTE + a wing
    contract that should be filtered out.

    AV's JSON-array-of-objects becomes a DataFrame with string columns.
    """
    rows = []
    base_date = pd.Timestamp(snap_date).date()
    next_date = (pd.Timestamp(snap_date) + pd.Timedelta(days=1)).date()
    far_date = (pd.Timestamp(snap_date) + pd.Timedelta(days=30)).date()

    # ATM ± 5 strikes for 0DTE — all should survive the filter
    for k in range(int(spot) - 5, int(spot) + 6):
        for side in ("call", "put"):
            rows.append({
                "contractID": f"SPY{snap_date.replace('-','')}{side[0].upper()}{k:08d}",
                "symbol": "SPY",
                "expiration": str(base_date),
                "strike": f"{k:.2f}",
                "type": side,
                "last": "5.20",
                "mark": "5.30",
                "bid": "5.20",
                "ask": "5.40",
                "volume": "100",
                "open_interest": "500",
                "implied_volatility": "0.18",
                "delta": "0.50" if side == "call" else "-0.50",
                "gamma": "0.05", "theta": "-0.10", "vega": "0.20", "rho": "0.01",
            })

    # 1DTE — should also survive (EXPIRY_HORIZON_DAYS = 1)
    rows.append({
        "contractID": f"SPY{next_date.strftime('%Y%m%d')}C{int(spot):08d}",
        "symbol": "SPY", "expiration": str(next_date), "strike": f"{spot:.2f}",
        "type": "call", "last": "8.0", "mark": "8.1", "bid": "8.0", "ask": "8.2",
        "volume": "10", "open_interest": "20", "implied_volatility": "0.20",
        "delta": "0.55", "gamma": "0.03", "theta": "-0.15", "vega": "0.25", "rho": "0.02",
    })

    # 30-day-out wing — should be filtered out
    rows.append({
        "contractID": f"SPY{far_date.strftime('%Y%m%d')}C{int(spot):08d}",
        "symbol": "SPY", "expiration": str(far_date), "strike": f"{spot:.2f}",
        "type": "call", "last": "15.0", "mark": "15.1", "bid": "15.0", "ask": "15.2",
        "volume": "5", "open_interest": "10", "implied_volatility": "0.18",
        "delta": "0.55", "gamma": "0.02", "theta": "-0.05", "vega": "0.50", "rho": "0.05",
    })

    # 0DTE strike 30 away (outside ATM_BAND=20) — should be filtered out
    rows.append({
        "contractID": f"SPY{snap_date.replace('-','')}C00480000",
        "symbol": "SPY", "expiration": str(base_date), "strike": "480.00",
        "type": "call", "last": "0.02", "mark": "0.02", "bid": "0.01", "ask": "0.03",
        "volume": "0", "open_interest": "5", "implied_volatility": "0.40",
        "delta": "0.02", "gamma": "0.001", "theta": "-0.005", "vega": "0.01", "rho": "0.001",
    })
    df = pd.DataFrame(rows)
    # Provide underlying_price so the helper picks it for ATM-band rather
    # than the median-strike heuristic
    df["underlying_price"] = str(spot)
    return df


def test_normalize_intraday_basic_shape():
    df = _synthetic_av_intraday(spot=450.0)
    dt = datetime(2024, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
    out = _normalize_intraday_response(df, "SPY", dt)
    assert not out.empty
    # snapshot_ts must be the requested intraday UTC, NOT 23:00 EOD
    assert (out["snapshot_ts"] == pd.Timestamp("2024-06-03 14:00:00", tz="UTC")).all()
    # session marker
    assert (out["market_session"] == "HISTORICAL_INTRADAY").all()
    # ticker uppercased
    assert (out["ticker"] == "SPY").all()
    # data_source recorded
    assert (out["data_source"] == "alphavantage").all()


def test_normalize_intraday_filters_far_expiry():
    df = _synthetic_av_intraday(spot=450.0)
    dt = datetime(2024, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
    out = _normalize_intraday_response(df, "SPY", dt)
    # No row should have expiration > snap_date + EXPIRY_HORIZON_DAYS
    snap = pd.Timestamp("2024-06-03").date()
    horizon = snap + pd.Timedelta(days=EXPIRY_HORIZON_DAYS).to_pytimedelta()
    assert (pd.to_datetime(out["expiration"]).dt.date <= horizon).all()


def test_normalize_intraday_filters_wing_strikes():
    df = _synthetic_av_intraday(spot=450.0)
    dt = datetime(2024, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
    out = _normalize_intraday_response(df, "SPY", dt)
    # ATM ± 20 means strikes 430-470 only
    assert out["strike"].min() >= 450 - ATM_BAND
    assert out["strike"].max() <= 450 + ATM_BAND
    # The far wing strike 480 should be excluded
    assert (out["strike"] != 480.0).all()


def test_normalize_intraday_call_put_mapped():
    df = _synthetic_av_intraday(spot=450.0)
    dt = datetime(2024, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
    out = _normalize_intraday_response(df, "SPY", dt)
    # 'type' column was 'call'/'put' — must be normalized to 'calls'/'puts'
    assert set(out["option_type"].unique()) <= {"calls", "puts"}


def test_normalize_intraday_drops_invalid_rows():
    df = _synthetic_av_intraday()
    # Inject a row with NaN strike → must be dropped
    bad = df.iloc[[0]].copy()
    bad.loc[bad.index[0], "strike"] = ""
    df_with_bad = pd.concat([df, bad], ignore_index=True)
    dt = datetime(2024, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
    out = _normalize_intraday_response(df_with_bad, "SPY", dt)
    # The bad row's strike coerces to NaN and gets dropped by `dropna`
    assert out["strike"].notna().all()


def test_to_et_conversion():
    """14:00 UTC on 2024-06-03 (EDT) = 10:00 ET."""
    dt = datetime(2024, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
    et_str = _to_et(dt)
    assert et_str == "2024-06-03T10:00:00"


def test_to_et_winter():
    """14:00 UTC on 2024-01-03 (EST) = 09:00 ET."""
    dt = datetime(2024, 1, 3, 14, 0, 0, tzinfo=timezone.utc)
    et_str = _to_et(dt)
    assert et_str == "2024-01-03T09:00:00"


# ─────────────────────────── _load_timestamps_from_csv ───────────────────────

from gcp.fetchers.fetch_av_historical_options_intraday import _load_timestamps_from_csv


def test_load_timestamps_local_csv(tmp_path):
    """Local-file path still works after the GCS-URL extension."""
    p = tmp_path / "ts.csv"
    p.write_text("ticker,datetime_utc\nIWM,2024-06-03T14:00:00\nIWM,2024-06-03T14:30:00\n")
    pairs = _load_timestamps_from_csv(str(p))
    assert len(pairs) == 2
    assert pairs[0][0] == "IWM"
    assert pairs[0][1].isoformat() == "2024-06-03T14:00:00+00:00"


def test_load_timestamps_gs_url(monkeypatch):
    """gs:// URL path: stub the google.cloud.storage import chain so the
    loader can resolve `from google.cloud import storage as gcs` even
    when the real google-cloud-storage package isn't installed in the
    test env (it IS installed in the Cloud Run image)."""
    import sys
    import types

    class _FakeBlob:
        def download_as_text(self):
            return "ticker,datetime_utc\nIWM,2024-06-03T14:00:00\n"

    class _FakeBucket:
        def blob(self, _path): return _FakeBlob()

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        def bucket(self, _name): return _FakeBucket()

    fake_storage = types.ModuleType("google.cloud.storage")
    fake_storage.Client = _FakeClient
    fake_cloud = types.ModuleType("google.cloud")
    fake_cloud.storage = fake_storage
    fake_google = types.ModuleType("google")
    fake_google.cloud = fake_cloud
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", fake_storage)

    pairs = _load_timestamps_from_csv("gs://my-bucket/path/to/ts.csv")
    assert len(pairs) == 1
    assert pairs[0][0] == "IWM"


def test_load_timestamps_gs_url_missing_blob_path():
    """gs://bucket alone (no blob) is rejected — fail-fast, not silent."""
    with pytest.raises(ValueError, match="missing blob path"):
        _load_timestamps_from_csv("gs://just-a-bucket")


def test_existing_snapshot_keys_accepts_tz_aware_and_naive(monkeypatch):
    """Both the batch CSV path (tz-aware) and the single-shot
    --datetime arg path (tz-naive) must work. Regression for the
    23:07 UTC 2026-05-27 prod failure where the dict comprehension
    raised 'Cannot pass a datetime or Timestamp with tzinfo with the
    tz parameter'."""
    import gcp.fetchers.fetch_av_historical_options_intraday as mod

    # Force the helper to think Cloud SQL is configured + stub the query
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    captured = {}
    def _fake_query(sql, params):
        captured["params"] = params
        return pd.DataFrame(columns=["snapshot_ts"])
    monkeypatch.setattr(mod, "query_to_dataframe", _fake_query)

    # Mix: one tz-aware (from CSV path) + one tz-naive (single-shot path).
    aware = datetime(2024, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
    naive = datetime(2024, 6, 3, 14, 30, 0)
    result = mod._existing_snapshot_keys("IWM", [aware, naive])
    assert isinstance(result, set)
    # Both inputs converted to UTC tz-aware datetimes — that's the
    # contract for the SQL params:
    assert captured["params"]["t0"].tzinfo is not None
    assert captured["params"]["t1"].tzinfo is not None


def test_utc_ts_helper_covers_all_input_shapes():
    """The 23:13 + 23:50 prod failures both came from pd.Timestamp(x, tz='UTC')
    not accepting tz-aware inputs. Lock that contract here."""
    from gcp.fetchers.fetch_av_historical_options_intraday import _utc_ts

    aware = datetime(2024, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
    naive = datetime(2024, 6, 3, 14, 0, 0)
    ts_aware = pd.Timestamp("2024-06-03 14:00", tz="UTC")
    ts_naive = pd.Timestamp("2024-06-03 14:00")
    iso_naive = "2024-06-03T14:00:00"
    iso_aware = "2024-06-03T14:00:00+00:00"

    for x in (aware, naive, ts_aware, ts_naive, iso_naive, iso_aware):
        out = _utc_ts(x)
        assert isinstance(out, pd.Timestamp), f"_utc_ts({x!r}) not a Timestamp"
        assert out.tzinfo is not None, f"_utc_ts({x!r}) returned naive"
        assert str(out.tz) == "UTC", f"_utc_ts({x!r}) tz={out.tz}, expected UTC"
        assert out.hour == 14 and out.minute == 0
