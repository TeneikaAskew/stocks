"""_load_gamma_levels must not fabricate a 0 for a missing total_gex.

Rule 3.7: a missing GEX must be NULL/None — not a fabricated 0 that downstream
can't distinguish from a real ~0 reading, and that would pollute the GEX
tercile distribution with fake zeros. A genuine 0.0 is preserved.
"""
from __future__ import annotations

import pytest
import math

import pandas as pd

from gcp.research.strat_engine import strat_data_builder as mod


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Engine:
    def connect(self):
        return _Conn()


def _raw():
    """Raw gamma_levels_eod rows: a normal date, a date with MISSING total_gex,
    and a date with a GENUINE 0.0."""
    return pd.DataFrame([
        {"snapshot_date": "2026-06-16", "level_kind": "king", "level_strike": 500.0,
         "gex": 1.0, "score": 1.0, "regime": "positive_gamma",
         "gamma_balance_price": 498.0, "gamma_flip": 497.0,
         "total_gex": 1.5e7, "spot_estimate": 499.0},
        {"snapshot_date": "2026-06-17", "level_kind": "king", "level_strike": 501.0,
         "gex": 1.0, "score": 1.0, "regime": "negative_gamma",
         "gamma_balance_price": 499.0, "gamma_flip": 498.0,
         "total_gex": None, "spot_estimate": 500.0},   # missing GEX
        {"snapshot_date": "2026-06-18", "level_kind": "gate", "level_strike": 502.0,
         "gex": 0.0, "score": 0.0, "regime": "unknown",
         "gamma_balance_price": 500.0, "gamma_flip": 499.0,
         "total_gex": 0.0, "spot_estimate": 501.0},    # genuine zero
    ])


@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_missing_gex_is_null_genuine_zero_preserved(monkeypatch, builder):
    from gcp.research import p7_build_multi_tf_features
    module = p7_build_multi_tf_features if builder == "p7" else mod
    monkeypatch.setattr(module.pd, "read_sql", lambda *a, **k: _raw())

    out = module._load_gamma_levels(_Engine(), "SPY")

    missing = out.loc[pd.Timestamp("2026-06-17").date(), "total_gex"]
    assert missing is None or (isinstance(missing, float) and math.isnan(missing)), \
        "missing total_gex must be NULL, not a fabricated 0"

    assert out.loc[pd.Timestamp("2026-06-18").date(), "total_gex"] == 0.0, \
        "a genuine 0.0 GEX must be preserved, not nulled"
    assert out.loc[pd.Timestamp("2026-06-16").date(), "total_gex"] == 1.5e7


def test_terciles_drop_null_gex(monkeypatch):
    """The NULL GEX must be excluded from the tercile distribution (dropna),
    not counted as a fake 0 that drags the percentiles down."""
    monkeypatch.setattr(mod.pd, "read_sql", lambda *a, **k: _raw())
    out = mod._load_gamma_levels(_Engine(), "SPY")
    # 3 dates, 1 NULL → 2 non-null feed terciles. (<30 rows → (nan, nan), but
    # the point is the series passed to _compute_terciles has the NULL dropped.)
    assert out["total_gex"].notna().sum() == 2


def test_dealer_regime_null_when_gex_missing():
    """_add_context must NULL dealer_regime when a tercile is missing, not
    persist a malformed "GEX_nan_VEX_*" that downstream null-filters keep
    (Codex review on #640)."""
    import datetime as dt
    import numpy as np

    d15, d16, d17 = dt.date(2026, 6, 15), dt.date(2026, 6, 16), dt.date(2026, 6, 17)
    gamma_df = pd.DataFrame([
        {"snapshot_date": d15, "total_gex": np.nan, "gamma_balance_price": 498.0,
         "gamma_flip": 497.0, "regime": "negative_gamma", "spot": 499.0,
         "min_king_strike": 500.0, "min_gate_strike": 495.0},
        {"snapshot_date": d16, "total_gex": 2e7, "gamma_balance_price": 499.0,
         "gamma_flip": 498.0, "regime": "positive_gamma", "spot": 500.0,
         "min_king_strike": 501.0, "min_gate_strike": 496.0},
        {"snapshot_date": d17, "total_gex": 2.5e7, "gamma_balance_price": 500.0,
         "gamma_flip": 499.0, "regime": "positive_gamma", "spot": 501.0,
         "min_king_strike": 502.0, "min_gate_strike": 497.0},
    ]).set_index("snapshot_date")
    vex_df = pd.DataFrame([
        {"snapshot_date": d15, "total_vex": 5e6},
        {"snapshot_date": d16, "total_vex": 6e6},
        {"snapshot_date": d17, "total_vex": 6.5e6},
    ]).set_index("snapshot_date")
    vix_df = pd.DataFrame([
        {"date": d15, "vix_close": 17.0},
        {"date": d16, "vix_close": 18.0},
        {"date": d17, "vix_close": 19.0},
    ]).set_index("date")
    # bar on d16 → prior day d15 (NaN GEX); bar on d17 → prior day d16 (GEX present)
    out = pd.DataFrame({"bar_date": [d16, d17], "close": [500.0, 501.0]})

    res = mod._add_context(out, "SPY", vix_df, gamma_df, vex_df,
                           gex_terciles=(1e7, 3e7), vex_terciles=(4e6, 7e6)
                           ).set_index("bar_date")

    # d16: prior GEX missing → tercile NaN → dealer_regime null (NaN/None, both
    # write as SQL NULL) — NOT the malformed "GEX_nan_VEX_MID" string
    assert pd.isna(res.loc[d16, "total_gex"])
    assert pd.isna(res.loc[d16, "dealer_regime"])
    # d17: prior GEX present → valid 9-cell label, no "nan"
    dr = res.loc[d17, "dealer_regime"]
    assert dr is not None and dr.startswith("GEX_") and "nan" not in dr


# ── Codex P1 on #1185 (reader sweep): mins_since_open on the market clock ────


def test_featurize_tf_counts_minutes_from_the_eastern_open():
    """The bars' index is the aware UTC instant; add_all_indicators read the
    clock off Time, so the persisted mins_since_open ran 240/300 min late."""
    import numpy as np
    import pandas as pd
    from gcp.research.strat_engine import strat_data_builder as sdb
    frames = []
    for day in ("2026-01-14", "2026-01-15"):   # EST
        wall = pd.date_range(f"{day} 09:30", f"{day} 15:59", freq="1min")
        idx = wall.tz_localize("America/New_York").tz_convert("UTC")
        px = 100 + np.cumsum(np.random.default_rng(3).normal(0, 0.05, len(idx)))
        frames.append(pd.DataFrame({"open": px, "high": px + 0.05, "low": px - 0.05,
                                    "close": px, "volume": 1000.0}, index=idx))
    df_1m = pd.concat(frames)
    out = sdb._featurize_tf(df_1m, "1m", None)
    col = "mins_since_open" if "mins_since_open" in out.columns else "Mins_Since_Open"
    first = out.loc[pd.Timestamp("2026-01-15 14:30", tz="UTC"), col]
    assert first == 0
    assert out.loc[pd.Timestamp("2026-01-15 15:30", tz="UTC"), col] == 60



@pytest.mark.parametrize("stored", ["et_label", "utc"])
def test_load_1m_bars_keeps_the_regular_session_in_either_convention(monkeypatch, stored):
    """Codex P1 on #1185 (3dd141d): an AT TIME ZONE filter in SQL read legacy
    raw 13:30-15:59 labels as 09:30-11:59 ET and dropped the real open."""
    import pandas as pd
    from gcp.research.strat_engine import strat_data_builder as sdb
    wall = pd.date_range("2026-07-15 04:00", "2026-07-15 20:00", freq="1min")
    ts = (wall.tz_localize("UTC") if stored == "et_label"
          else wall.tz_localize("America/New_York").tz_convert("UTC"))
    minute = wall.hour * 60 + wall.minute
    rows = pd.DataFrame({"ts": ts, "open": 1.0, "high": 1.0, "low": 1.0,
                         "close": minute.astype(float),
                         "volume": [5000 if 570 <= m < 600 else 100 for m in minute]})

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Engine:
        def connect(self):
            return _Conn()

    monkeypatch.setattr(sdb.pd, "read_sql",
                        lambda sql, conn, params=None: rows[rows["ts"] >= params["start_ts"]].copy())
    out = sdb._load_1m_bars(_Engine(), "SPY", "2026-07-15")
    assert len(out) == 390
    assert out.index[0] == pd.Timestamp("2026-07-15 13:30", tz="UTC")   # 09:30 EDT
    assert out["close"].iloc[0] == 570.0                               # the 09:30 bar



def test_four_hour_bars_sit_on_the_eastern_grid_in_winter():
    """Codex P1 on #1185 (ee9912e): 4h bars resampled on the UTC index split a
    winter session on 12:00/16:00/20:00Z. On the Eastern clock the session's
    bars open at 08:00 and 12:00 ET, keyed by their UTC instants."""
    import numpy as np
    import pandas as pd
    from gcp.research.strat_engine import strat_data_builder as sdb
    wall = pd.date_range("2026-01-15 09:30", "2026-01-15 15:59", freq="1min")
    idx = wall.tz_localize("America/New_York").tz_convert("UTC")
    px = 100 + np.cumsum(np.random.default_rng(5).normal(0, 0.05, len(idx)))
    df = pd.DataFrame({"open": px, "high": px + 0.05, "low": px - 0.05,
                       "close": px, "volume": 1000.0}, index=idx)
    out = sdb._featurize_tf(df, "4h", "4h")
    keys = sorted(out.index)
    assert keys == [pd.Timestamp("2026-01-15 13:00", tz="UTC"),   # 08:00 EST
                    pd.Timestamp("2026-01-15 17:00", tz="UTC")]   # 12:00 EST


@pytest.mark.parametrize('builder', ['p7', 'strat_engine'])
def test_research_featurize_tf_retains_legacy_valid_minute_features(builder):
    """A shared adapter change must not silently erase trained candle inputs."""
    import numpy as np
    from lib.eastern_time import eastern_index_to_utc
    from gcp.research import p7_build_multi_tf_features

    module = p7_build_multi_tf_features if builder == 'p7' else mod
    index = eastern_index_to_utc(pd.date_range('2026-04-20 09:30', periods=390, freq='min'))
    values = 100 + np.arange(390) / 100
    raw = pd.DataFrame({'open': values, 'high': values + .02, 'low': values - .02,
                        'close': values + .01, 'volume': 100.}, index=index)
    features = module._featurize_tf(raw, '5m', '5m')
    assert features['strat_candle'].value_counts().to_dict() == {'2U': 77, 'X': 1}
    assert features.iloc[0]['open'] == 100.
    assert features.iloc[0]['close'] == pytest.approx(100.05)
    assert features.iloc[-1]['close'] == pytest.approx(103.90)


@pytest.mark.parametrize('builder', ['p7','strat'])
@pytest.mark.parametrize('bars,expected', [
    ([(100,90,95,96),(101,89,94,99),(102,90,95,100)], 'clean_2u_bull'),
    ([(100,90,95,96),(99,89,94,93),(98,90,94,95),(99,89,94,95)], '212_bull_reversal'),
    ([(100,90,95,96),(101,89,94,99),(100,90,94,95),(101,89,94,95)], '312_bull_reversal'),
])
def test_research_combo_features_keep_declared_legacy_patterns(builder,bars,expected):
    """Canonical 32 and outside-212 fixes cannot rewrite persisted model inputs."""
    from gcp.research import p7_build_multi_tf_features
    module = p7_build_multi_tf_features if builder == 'p7' else mod
    frame = pd.DataFrame(bars,columns=['high','low','open','close'],
                         index=pd.date_range('2026-04-20 13:30',periods=len(bars),freq='min',tz='UTC'))
    frame['volume'] = 100.
    result = module._featurize_tf(frame,'1m',None)
    assert result.iloc[-1]['strat_combo'] == expected
    assert bool(result.iloc[-1]['is_reversal']) is expected.endswith('_reversal')
    assert result.attrs['strat_rule_version'] == 'legacy-pattern-v1'


# ── Strict-prior snapshot selection (feature builders) ───────────────────────

import datetime as _dt

_SP_D2 = _dt.date(2026, 10, 6)
_SP_D1 = _dt.date(2026, 10, 7)
_SP_D = _dt.date(2026, 10, 8)
_SP_D3 = _dt.date(2026, 10, 9)
_SP_COLS = ["total_gex", "gamma_balance_price", "gamma_flip", "regime", "spot",
            "min_king_strike", "min_gate_strike"]


def _sp_row(date, gex, bal, flip, regime, king, gate):
    return {"snapshot_date": date, "total_gex": gex, "gamma_balance_price": bal,
            "gamma_flip": flip, "regime": regime, "spot": 500.0,
            "min_king_strike": king, "min_gate_strike": gate}


def _sp_d2_row():
    return _sp_row(_SP_D2, 1.5e7, 498.0, float("nan"), "positive_gamma", 505.0, 495.0)


def _sp_d_row():
    return _sp_row(_SP_D, 2.5e7, 600.0, 610.0, "negative_gamma", 620.0, 590.0)


def _sp_d3_row():
    return _sp_row(_SP_D3, 2.6e7, 601.0, 611.0, "negative_gamma", 621.0, 591.0)


def _sp_levels(rows):
    return pd.DataFrame(rows, columns=["snapshot_date"] + _SP_COLS).set_index("snapshot_date")


def _sp_run(builder, rows):
    from gcp.research import p7_build_multi_tf_features
    module = p7_build_multi_tf_features if builder == "p7" else mod
    vix_df = pd.DataFrame([
        {"date": _SP_D1, "vix_close": 17.0},
        {"date": _SP_D, "vix_close": 18.0},
    ]).set_index("date")
    out = pd.DataFrame({"bar_date": [_SP_D, _SP_D], "close": [500.0, 501.0]})
    return module._add_context(out, "SPY", vix_df, _sp_levels(rows), pd.DataFrame(),
                               gex_terciles=(1e7, 3e7), vex_terciles=(4e6, 7e6))


def _assert_flip_distance_nan(res):
    # Only the strat builder emits dist_to_gamma_flip_pct; p7's columns are unchanged.
    if "dist_to_gamma_flip_pct" in res.columns:
        assert res["dist_to_gamma_flip_pct"].isna().all()


def _assert_d2_context(res):
    assert (res["total_gex"] == 1.5e7).all()
    assert (res["gamma_balance_price"] == 498.0).all()
    assert res["gamma_flip"].isna().all()
    _assert_flip_distance_nan(res)
    assert (res["gamma_regime"] == "positive_gamma").all()
    assert res["distance_to_king_pct"].tolist() == pytest.approx(
        [(500.0 - 505.0) / 500.0 * 100, (501.0 - 505.0) / 501.0 * 100])
    assert res["distance_to_gate_pct"].tolist() == pytest.approx(
        [(500.0 - 495.0) / 500.0 * 100, (501.0 - 495.0) / 501.0 * 100])


@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_strict_prior_with_bar_date_snapshot_present(builder):
    _assert_d2_context(_sp_run(builder, [_sp_d2_row(), _sp_d_row(), _sp_d3_row()]))


@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_strict_prior_with_bar_date_snapshot_absent(builder):
    _assert_d2_context(_sp_run(builder, [_sp_d2_row(), _sp_d3_row()]))


@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_strict_prior_never_reads_same_day_or_later(builder):
    res = _sp_run(builder, [_sp_d2_row(), _sp_d_row(), _sp_d3_row()])
    forbidden = {2.5e7, 2.6e7, 600.0, 601.0, 610.0, 611.0, 620.0, 621.0, 590.0, 591.0}
    for col in ["total_gex", "gamma_balance_price", "gamma_flip"]:
        assert not set(res[col].dropna()) & forbidden
    assert not (res["gamma_regime"] == "negative_gamma").any()
    _assert_flip_distance_nan(res)


@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_marker_row_on_prior_day_blocks_older_snapshot(builder):
    nan = float("nan")
    marker = _sp_row(_SP_D1, nan, nan, nan, None, nan, nan)
    marker["spot"] = nan
    res = _sp_run(builder, [_sp_d2_row(), marker, _sp_d_row()])
    assert res["total_gex"].isna().all()
    assert res["gamma_balance_price"].isna().all()
    assert res["distance_to_king_pct"].isna().all()
    assert (res["gamma_regime"] == "unknown").all()


@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_no_prior_snapshot_is_nan_never_zero(builder):
    res = _sp_run(builder, [_sp_d_row(), _sp_d3_row()])
    assert res["total_gex"].isna().all()
    assert (res["gamma_regime"] == "unknown").all()
    _assert_flip_distance_nan(res)
    for col in ["distance_to_king_pct", "distance_to_gate_pct"]:
        assert res[col].isna().all()
