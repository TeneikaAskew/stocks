"""Phase-2 feature families for the DIRECTION and SIZE engines. New columns are
returned NaN-preserving for the engine to concat AFTER featurize (so they never
hit featurize's fillna(0) — CLAUDE.md Rule 3.7). Feature math is reused from
lib/; this module only orchestrates and shapes."""
from __future__ import annotations


def prune_feature_cols(feature_cols: list[str], drop_set: set) -> list[str]:
    return [c for c in feature_cols if c not in drop_set]
