"""Experimental feature joiners for the strat-engine direction-target R&D.

These modules are NOT part of the production featurize path. They exist solely
to test whether non-structural feature families (news sentiment, cross-asset,
options-derived, volatility-regime) make next-bar body direction
(`next_close > next_open`) learnable when the 143-col strat-features baseline
fails 24/24 folds.

Contract: each module exposes `add_<family>_features(df, ticker, engine) -> df`
which takes the labeled dataset (output of `load_labeled_dataset(...,
include_next_bar_ohlc=True)`) and returns the same DataFrame with new numeric
columns added. All new columns must be available at bar T close — strictly NO
look-ahead.

The `strat_dir_walk_forward_extended.py` runner calls one of these per
`--family` flag, then runs the identical 8-fold walk-forward harness on the
extended feature set.

See `docs/DIRECTION_FEATURES_R&D.md` for the verdict and per-family results.
"""
