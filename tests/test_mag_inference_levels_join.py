"""Regression test for mag_inference's feature-loader contract.

The 2026-06-19 incident: magnitude-inference raised
"feature drift for orb_5m_high" on every cell. Root cause was an
asymmetry between training and inference SQL — training calls
`load_labeled_dataset(include_levels=True)` which LEFT JOINs
`strat_features_levels_<tf>` (where ORB / historical-level / order-block
columns live); inference did a bare `SELECT * FROM strat_features_<tf>`
and never saw those columns. feature_cols.txt (written by training)
recorded `orb_5m_high` as a numeric feature, so the alignment check
in `_score_and_persist` correctly raised on every bar.

The fix routes inference through the SAME loader training uses
(`strat_dataset.load_strat_features_with_levels`). This test pins
that contract so a future "simplification" back to the bare-SELECT
state is caught by CI, not by a 5am pager alert.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd


def _stub_missing_modules(mods: list[str]) -> None:
    """Only stub when the real package is unavailable; setdefault()
    poisons sys.modules for sibling tests (caught 2026-06-09 in
    PR #597 CI)."""
    for m in mods:
        try:
            __import__(m)
        except ImportError:
            parts = m.split(".")
            for i in range(1, len(parts) + 1):
                key = ".".join(parts[:i])
                if key not in sys.modules:
                    sys.modules[key] = MagicMock()


_stub_missing_modules([
    "google.cloud.storage",
    "sklearn.calibration",
    "sklearn.metrics",
    "lightgbm",
    "joblib",
])


def test_load_recent_features_routes_through_shared_loader():
    """The inference loader MUST call `load_strat_features_with_levels`
    (the same helper training uses) — NOT a bare SELECT against
    `strat_features_<tf>`. Pinning this is the only thing that prevents
    a regression back to the schema-split asymmetry that caused the
    2026-06-19 'feature drift for orb_5m_high' outage."""
    from gcp.research.magnitude_engine import mag_inference as mod

    fake_engine = MagicMock()
    fake_df = pd.DataFrame({
        "ts": pd.date_range("2026-06-19 09:30", periods=2, freq="5min", tz="UTC"),
        "ticker": ["IWM"] * 2,
        "rsi_14": [55.0, 60.0],
        # The level columns inference USED to miss. Pin that they survive.
        "orb_5m_high": [205.0, 205.0],
        "orb_5m_broke_high": [0, 1],
    })

    with patch(
        "gcp.research.strat_engine.strat_dataset.load_strat_features_with_levels",
        return_value=fake_df,
    ) as mock_loader:
        out = mod._load_recent_features("IWM", "5m", 24, engine=fake_engine)

    mock_loader.assert_called_once()
    args, kwargs = mock_loader.call_args
    # Engine + ticker + tf passed positionally OR as kwargs
    assert fake_engine in args or kwargs.get("engine") is fake_engine \
        or args[0] is fake_engine
    assert "IWM" in args or kwargs.get("ticker") == "IWM"
    assert "5m" in args or kwargs.get("tf") == "5m"
    # CRITICAL: include_levels must be True. Without this the loader
    # falls back to bare strat_features_<tf> and the bug returns.
    assert kwargs.get("include_levels") is True, (
        "_load_recent_features MUST request include_levels=True — "
        "otherwise orb_*, historical-level, and order-block columns "
        "are silently dropped and inference drifts vs training"
    )
    # require_strat_candle must be False at inference (training default
    # is True). Inference scores partial / unsettled bars; the NaN guard
    # in _score_and_persist handles unscorable rows.
    assert kwargs.get("require_strat_candle") is False, (
        "inference must NOT require strat_candle IS NOT NULL — the "
        "latest bar is sometimes still computing and dropping it would "
        "silently make 'score the most recent bar' impossible"
    )
    # Result is the joined frame, level columns preserved.
    assert "orb_5m_high" in out.columns
    assert "orb_5m_broke_high" in out.columns


def test_load_recent_features_passes_lookback_cutoff_as_since_ts():
    """The lookback_hours window must reach the loader as `since_ts`
    (timestamp granularity), not since (date granularity). At 24h
    lookback a date filter would over-fetch by up to ~24h and at 1h
    lookback would under-fetch by ~23h. Pin the parameter name."""
    from gcp.research.magnitude_engine import mag_inference as mod

    with patch(
        "gcp.research.strat_engine.strat_dataset.load_strat_features_with_levels",
        return_value=pd.DataFrame(),
    ) as mock_loader:
        before = datetime.now(timezone.utc)
        mod._load_recent_features("IWM", "5m", lookback_hours=24,
                                   engine=MagicMock())
        after = datetime.now(timezone.utc)

    kwargs = mock_loader.call_args.kwargs
    assert "since_ts" in kwargs, "lookback must reach loader via since_ts"
    parsed = datetime.fromisoformat(kwargs["since_ts"])
    # The cutoff must be ~24h before now (allow 1s drift for test runtime).
    expected_lo = before.replace(microsecond=0) - pd.Timedelta(hours=24, seconds=1)
    expected_hi = after.replace(microsecond=0) - pd.Timedelta(hours=24) + pd.Timedelta(seconds=1)
    assert expected_lo <= parsed.replace(microsecond=0) <= expected_hi, (
        f"since_ts={parsed} not in expected 24h-ago window "
        f"[{expected_lo}, {expected_hi}]"
    )


def test_load_strat_features_with_levels_is_the_shared_helper():
    """Both `load_labeled_dataset` (training) and `_load_recent_features`
    (inference) must go through `load_strat_features_with_levels`.
    Asserting both call sites pins the train-vs-inference contract."""
    from gcp.research.strat_engine import strat_dataset

    # The shared helper exists with the expected signature.
    assert hasattr(strat_dataset, "load_strat_features_with_levels")
    fn = strat_dataset.load_strat_features_with_levels
    # Quick signature smoke: takes engine, ticker, tf + the kwargs the
    # inference loader relies on.
    import inspect
    sig = inspect.signature(fn)
    for name in ("ticker", "tf", "since", "until", "since_ts",
                 "include_levels", "require_strat_candle"):
        assert name in sig.parameters, (
            f"load_strat_features_with_levels missing {name!r} param — "
            f"a refactor changed the shared contract; the inference "
            f"path will break"
        )


def test_load_recent_features_recreates_training_lags():
    """Codex P1 (PR #627): training's `label_next_bar_type()` adds
    `prev1/2/3_candle` to the frame BEFORE featurize() one-hot encodes
    them, so `feature_cols.txt` lists `prev1_candle_<value>` dummies.
    Inference MUST re-add those lag columns via the same helper, or
    every `prev*_candle_*` dummy is missing at featurize() time and the
    zero-fill heuristic in `_score_and_persist` silently erases the
    sequence feature on every live prediction.

    This test asserts the loader produces a frame with the lag columns
    populated, using the same session-aware shift training uses."""
    from gcp.research.magnitude_engine import mag_inference as mod

    # Mock the SQL helper to return 6 bars in a single session with
    # known strat_candle values.
    raw = pd.DataFrame({
        "ts": pd.date_range("2026-06-19 13:30", periods=6,
                            freq="5min", tz="UTC"),
        "ticker": ["IWM"] * 6,
        "bar_date": [pd.Timestamp("2026-06-19").date()] * 6,
        "strat_candle": ["1", "2U", "2D", "3", "1", "2U"],
        "orb_5m_high": [205.0] * 6,
    })
    with patch(
        "gcp.research.strat_engine.strat_dataset.load_strat_features_with_levels",
        return_value=raw,
    ):
        out = mod._load_recent_features("IWM", "5m", 24, engine=MagicMock())

    # prev1/2/3_candle MUST be present — these are the source columns
    # featurize() one-hot encodes.
    assert "prev1_candle" in out.columns, (
        "_load_recent_features MUST recreate prev1_candle — without it "
        "featurize produces no prev1_candle_* dummies and the model "
        "silently sees all-zero sequence features (Codex P1 #627)"
    )
    assert "prev2_candle" in out.columns
    assert "prev3_candle" in out.columns
    # Session-aware: row 3 (i=3) has prev1=row 2 strat_candle = '2D'.
    # Warmup drop removes rows 0/1/2 (prev3_candle NaN); the 4th raw row
    # becomes the FIRST surviving row. Check the lag values are right.
    assert len(out) == 3  # rows 3, 4, 5 survived
    assert out.iloc[0]["prev1_candle"] == "2D"   # raw row 3 prev1 = raw row 2 strat = '2D'
    assert out.iloc[0]["prev2_candle"] == "2U"   # raw row 3 prev2 = raw row 1 strat = '2U'
    assert out.iloc[0]["prev3_candle"] == "1"    # raw row 3 prev3 = raw row 0 strat = '1'
    assert out.iloc[2]["prev1_candle"] == "1"    # raw row 5 prev1 = raw row 4 strat = '1'


def test_load_recent_features_drops_session_warmup_bars():
    """Training calls label_next_bar_type with drop_warmup=True (default)
    so the model NEVER saw a row where prev3_candle was NaN. Inference
    must drop those rows too — feeding them to the model would supply
    all-zero prev*_candle_* dummies, which is out-of-distribution."""
    from gcp.research.magnitude_engine import mag_inference as mod
    raw = pd.DataFrame({
        "ts": pd.date_range("2026-06-19 13:30", periods=5,
                            freq="5min", tz="UTC"),
        "ticker": ["IWM"] * 5,
        "bar_date": [pd.Timestamp("2026-06-19").date()] * 5,
        "strat_candle": ["1", "2U", "2D", "3", "1"],
    })
    with patch(
        "gcp.research.strat_engine.strat_dataset.load_strat_features_with_levels",
        return_value=raw,
    ):
        out = mod._load_recent_features("IWM", "5m", 24, engine=MagicMock())
    # First 3 bars have prev3_candle NaN (no 3 prior bars in this session)
    # — they must be dropped.
    assert len(out) == 2, f"expected 2 surviving bars, got {len(out)}"
    assert out["prev3_candle"].notna().all()


def test_add_session_aware_lags_matches_label_next_bar_type():
    """Pin that the new shared helper produces identical prev1/2/3_candle
    columns to the inline logic `label_next_bar_type` used pre-refactor.
    If the helper's shift semantics drift away from the labeler, training
    and inference will start producing different sequence features for
    the same raw frame — the exact failure mode this refactor exists to
    prevent."""
    from gcp.research.strat_engine.strat_dataset import (
        add_session_aware_lags, label_next_bar_type,
    )
    raw = pd.DataFrame({
        "ts": pd.date_range("2026-06-19 13:30", periods=8,
                            freq="5min", tz="UTC"),
        "bar_date": [pd.Timestamp("2026-06-19").date()] * 4 +
                    [pd.Timestamp("2026-06-20").date()] * 4,
        "strat_candle": ["1", "2U", "2D", "3", "1", "2U", "2D", "3"],
        "open": [100.0] * 8, "high": [101.0] * 8,
        "low": [99.0] * 8, "close": [100.5] * 8,
    })

    lags_only = add_session_aware_lags(raw, "5m")
    full = label_next_bar_type(raw, "5m", drop_warmup=False)

    # The helper's lag columns must match the labeler's lag columns
    # for every row the labeler kept.
    for col in ("prev1_candle", "prev2_candle", "prev3_candle"):
        merged = full[["ts", col]].merge(
            lags_only[["ts", col]], on="ts", suffixes=("_full", "_helper"),
        )
        for _, row in merged.iterrows():
            full_val = row[f"{col}_full"]
            helper_val = row[f"{col}_helper"]
            # Both NaN OR both equal
            if pd.isna(full_val) and pd.isna(helper_val):
                continue
            assert full_val == helper_val, (
                f"{col} mismatch at ts={row['ts']}: "
                f"label_next_bar_type={full_val!r} vs "
                f"add_session_aware_lags={helper_val!r}"
            )
    # Session-aware: first row of session 2 (2026-06-20) has prev=NaN
    # because session-aware shift doesn't cross days.
    session_two_first = lags_only[
        lags_only["bar_date"] == pd.Timestamp("2026-06-20").date()
    ].iloc[0]
    assert pd.isna(session_two_first["prev1_candle"]), (
        "session-aware shift must produce NaN for the first bar of a "
        "new session — it crossed days, which is the bug this helper "
        "exists to prevent"
    )


def test_load_labeled_dataset_routes_through_shared_helper():
    """Training's `load_labeled_dataset` must delegate to the same
    helper inference uses. Otherwise the two paths can drift again."""
    from gcp.research.strat_engine import strat_dataset

    raw_frame = pd.DataFrame({
        "ts": pd.date_range("2026-06-18 13:30", periods=4,
                            freq="5min", tz="UTC"),
        "bar_date": pd.date_range("2026-06-18", periods=4, freq="D").date,
        "ticker": ["IWM"] * 4,
        "open": [200.0, 201.0, 202.0, 203.0],
        "high": [201.0, 202.0, 203.0, 204.0],
        "low": [199.0, 200.0, 201.0, 202.0],
        "close": [200.5, 201.5, 202.5, 203.5],
        "volume": [1000, 1100, 1200, 1300],
        "strat_candle": ["1", "2U", "2D", "1"],
        "orb_5m_high": [205.0] * 4,
    })

    with patch.object(
        strat_dataset, "load_strat_features_with_levels",
        return_value=raw_frame,
    ) as mock_helper:
        out = strat_dataset.load_labeled_dataset(
            MagicMock(), "IWM", "5m",
            since="2026-06-18", until="2026-06-19",
            include_levels=True,
        )

    mock_helper.assert_called_once()
    kwargs = mock_helper.call_args.kwargs
    # Training requires strat_candle present (it's the label source).
    assert kwargs.get("require_strat_candle") is True
    # And explicitly asks for the levels join.
    assert kwargs.get("include_levels") is True
    # The level column survived the round-trip.
    assert "orb_5m_high" in out.columns
