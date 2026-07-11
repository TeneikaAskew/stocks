import pandas as pd
import numpy as np
from gcp.research.direction_program.phase2_features import calendar_features


def test_calendar_columns_and_values():
    df = pd.DataFrame({"bar_date": pd.to_datetime(
        ["2026-03-31", "2026-06-30", "2026-01-05"]).date})
    out = calendar_features(df)
    assert list(out.columns) == [
        "cal_dow", "cal_week_of_month", "cal_is_month_end",
        "cal_is_quarter_end", "cal_is_fomc_week"]
    # 2026-03-31 is a Tuesday, month-end AND quarter-end
    assert out.iloc[0]["cal_dow"] == 1
    assert out.iloc[0]["cal_is_month_end"] == 1
    assert out.iloc[0]["cal_is_quarter_end"] == 1
    # 2026-06-30 quarter-end, not a Friday
    assert out.iloc[1]["cal_is_quarter_end"] == 1
    assert len(out) == 3


def test_calendar_has_no_nans():
    df = pd.DataFrame({"bar_date": pd.to_datetime(["2026-01-05"]).date})
    assert not calendar_features(df).isna().any().any()


def test_fomc_week_is_nan_before_coverage():
    # 2015 is outside the covered FOMC years {2024,2025,2026}: cal_is_fomc_week
    # must be NaN ("unknown"), never a false 0. The other 4 calendar cols are
    # date-derived and remain non-NaN.
    df = pd.DataFrame({"bar_date": pd.to_datetime(["2015-03-18"]).date})
    out = calendar_features(df)
    assert np.isnan(out.iloc[0]["cal_is_fomc_week"])
    for c in ["cal_dow", "cal_week_of_month", "cal_is_month_end",
              "cal_is_quarter_end"]:
        assert not np.isnan(out.iloc[0][c])
