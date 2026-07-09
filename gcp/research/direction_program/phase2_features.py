"""Phase-2 feature families for the DIRECTION and SIZE engines. New columns are
returned NaN-preserving for the engine to concat AFTER featurize (so they never
hit featurize's fillna(0) — CLAUDE.md Rule 3.7). Feature math is reused from
lib/; this module only orchestrates and shapes."""
from __future__ import annotations

import numpy as np
import pandas as pd


def prune_feature_cols(feature_cols: list[str], drop_set: set) -> list[str]:
    return [c for c in feature_cols if c not in drop_set]


# FOMC meeting weeks (Mon–Fri containing a scheduled FOMC decision), 2015-2026.
# Static table — derived from the Fed calendar; extend as new years publish.
_FOMC_WEEKS = {
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
}
_FOMC_WEEK_STARTS = {
    (pd.Timestamp(d) - pd.Timedelta(days=pd.Timestamp(d).weekday())).date()
    for d in _FOMC_WEEKS
}


def calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    d = pd.to_datetime(df["bar_date"])
    week_of_month = ((d.dt.day - 1) // 7 + 1).astype(np.float32)
    month_end = d.dt.is_month_end.astype(np.float32)
    quarter_end = (d.dt.is_month_end & d.dt.month.isin([3, 6, 9, 12])
                   ).astype(np.float32)
    week_start = (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.date
    is_fomc = week_start.map(lambda x: x in _FOMC_WEEK_STARTS).astype(np.float32)
    out = pd.DataFrame({
        "cal_dow": d.dt.weekday.astype(np.float32),
        "cal_week_of_month": week_of_month,
        "cal_is_month_end": month_end,
        "cal_is_quarter_end": quarter_end,
        "cal_is_fomc_week": is_fomc,
    }, index=df.index)
    return out
