import numpy as np
import pandas as pd
import gcp.research.direction_program.phase2_features as p2


def test_build_family_columns_calendar_only():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-03-31 15:00"], utc=True),
        "bar_date": pd.to_datetime(["2026-03-31"]).date,
        "close": [100.0]})
    new_df, new_cols = p2.build_family_columns(
        df, {"calendar"}, axis="direction", ticker="IWM", tf="5m", engine=None)
    assert "cal_is_quarter_end" in new_cols
    assert len(new_df) == 1
    assert new_df.iloc[0]["cal_is_quarter_end"] == 1


def test_build_family_columns_combines_and_preserves_nan(monkeypatch):
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-05 15:00"], utc=True),
        "bar_date": pd.to_datetime(["2026-01-05"]).date, "close": [100.0]})

    def fake_opts(d, ticker, engine, families):
        return pd.DataFrame({"atm_iv_d1": [np.nan]}, index=d.index)
    monkeypatch.setattr(p2, "options_features", fake_opts)

    new_df, new_cols = p2.build_family_columns(
        df, {"options_iv", "calendar"}, axis="size", ticker="IWM",
        tf="5m", engine=None)
    assert "atm_iv_d1" in new_cols and "cal_dow" in new_cols
    assert np.isnan(new_df.iloc[0]["atm_iv_d1"])  # NaN preserved
