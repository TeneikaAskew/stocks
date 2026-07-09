import numpy as np
import pandas as pd
import gcp.research.direction_program.phase2_features as p2


def test_options_families_select_expected_columns(monkeypatch):
    df = pd.DataFrame({"bar_date": pd.to_datetime(["2026-01-05", "2026-01-06"]).date})

    def fake_join(d, ticker, engine):
        out = d.copy()
        out["pcr_volume_d1"] = [1.1, np.nan]
        out["pcr_oi_d1"] = [0.9, 0.8]
        out["iv_skew_25d_d1"] = [0.03, 0.04]
        out["iv_term_slope_d1"] = [0.01, np.nan]
        out["atm_iv_d1"] = [0.2, 0.21]
        return out
    monkeypatch.setattr(p2, "add_options_features", fake_join)

    pos = p2.options_features(df, "IWM", engine=None, families={"positioning"})
    assert list(pos.columns) == ["pcr_volume_d1", "pcr_oi_d1", "iv_skew_25d_d1"]
    assert np.isnan(pos.iloc[1]["pcr_volume_d1"])  # NaN preserved, not 0

    iv = p2.options_features(df, "IWM", engine=None, families={"options_iv"})
    assert list(iv.columns) == ["atm_iv_d1"]

    both = p2.options_features(df, "IWM", engine=None,
                               families={"positioning", "options_iv"})
    assert set(both.columns) == {
        "pcr_volume_d1", "pcr_oi_d1", "iv_skew_25d_d1",
        "atm_iv_d1"}
