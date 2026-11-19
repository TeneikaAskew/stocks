"""Strict-prior gamma context against a real PostgreSQL.

The hermetic tests in tests/gcp/test_strat_data_builder_gamma.py prove the
selection rule on in-memory frames. This module proves the same contract
through the production loaders (`_load_gamma_levels`) and both builders'
`_add_context`, reading `gamma_levels_eod` rows the way production does, so
a SQL, dtype or pivot difference between a frame and a real table cannot
hide a leak (CLAUDE.md Rule 0.3: hermetic tests prove correctness, not
deployability).

The contract: a bar on date D takes its gamma context from the latest
snapshot STRICTLY before D, per field never back-filled. The fixture has no
D-1 row, a D-2 row with a NULL gamma_flip, an older D-3 row WITH a gamma_flip
(a back-fill would pick it up), and D / D+1 rows with values no prior-day
read may show. The old shift-join read D whenever it existed and D-2 never
reached it when D was missing.

`gamma_levels_eod` is created by gcp/research/p2_build_gamma_levels.py, not
by gcp/schema.sql, so the fixture creates it from that module's DDL.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from gcp.research import p2_build_gamma_levels, p7_build_multi_tf_features
from gcp.research.strat_engine import strat_data_builder

TICKER = "SPY"
D_MINUS_3 = date(2026, 10, 5)
D_MINUS_2 = date(2026, 10, 6)
D_MINUS_1 = date(2026, 10, 7)  # deliberately no snapshot row
D = date(2026, 10, 8)
D_PLUS_1 = date(2026, 10, 9)

# (snapshot_date, regime, total_gex, gamma_balance_price, gamma_flip,
#  spot_estimate, king_strike, gate_strike)
SNAPSHOTS = [
    (D_MINUS_3, "positive_gamma", 0.5e7, 470.0, 480.0, 475.0, 485.0, 465.0),
    (D_MINUS_2, "positive_gamma", 1.5e7, 498.0, None, 500.0, 505.0, 495.0),
    (D, "negative_gamma", 2.5e7, 600.0, 610.0, 601.0, 620.0, 590.0),
    (D_PLUS_1, "negative_gamma", 3.5e7, 601.0, 611.0, 602.0, 621.0, 591.0),
]

_INSERT = text("""
    INSERT INTO gamma_levels_eod (
        ticker, snapshot_date, level_kind, level_strike, gex, score, regime,
        gamma_balance_price, gamma_flip, total_gex, spot_estimate
    ) VALUES (
        :ticker, :d, :kind, :strike, 1.0, 1.0, :regime,
        :bal, :flip, :gex, :spot
    )
""")


def _builder(name):
    return {"strat": strat_data_builder, "p7": p7_build_multi_tf_features}[name]


@pytest.fixture
def gamma_levels(db_engine):
    """King + gate rows for each SNAPSHOTS date in the ephemeral DB."""
    with db_engine.begin() as conn:
        # CREATE_TABLE_SQL holds two statements (table + index); run them singly.
        for stmt in p2_build_gamma_levels.CREATE_TABLE_SQL.split(";"):
            if stmt.strip():
                conn.execute(text(stmt))
        conn.execute(text("TRUNCATE gamma_levels_eod"))
        for d, regime, gex, bal, flip, spot, king, gate in SNAPSHOTS:
            for kind, strike in (("king", king), ("gate", gate)):
                conn.execute(_INSERT, {
                    "ticker": TICKER, "d": d, "kind": kind, "strike": strike,
                    "regime": regime, "bal": bal, "flip": flip, "gex": gex,
                    "spot": spot,
                })
    yield db_engine
    with db_engine.begin() as conn:  # cleanup — original error already propagated
        conn.execute(text("TRUNCATE gamma_levels_eod"))


def _bars_on_d():
    return pd.DataFrame({"bar_date": [D, D], "close": [500.0, 501.0]})


def _vix():
    return pd.DataFrame([
        {"date": D_MINUS_1, "vix_close": 17.0},
        {"date": D, "vix_close": 18.0},
    ]).set_index("date")


def _context_on_d(mod, engine):
    gamma_df = mod._load_gamma_levels(engine, TICKER)
    return mod._add_context(_bars_on_d(), TICKER, _vix(), gamma_df, pd.DataFrame(),
                            (1e7, 3e7), (4e6, 7e6))


def _assert_d_minus_2_context_with_null_flip(out, module):
    assert out["total_gex"].tolist() == [1.5e7, 1.5e7]
    assert out["gamma_balance_price"].tolist() == [498.0, 498.0]
    # D-2's flip is NULL: it is not back-filled from D-3's 480.0 nor read from D.
    assert out["gamma_flip"].isna().all()
    if module == "strat":  # only the strat builder emits the distance column
        assert out["dist_to_gamma_flip_pct"].isna().all()
    assert (out["gamma_regime"] == "positive_gamma").all()
    assert out["distance_to_king_pct"].tolist() == pytest.approx(
        [(500.0 - 505.0) / 500.0 * 100, (501.0 - 505.0) / 501.0 * 100])
    assert out["distance_to_gate_pct"].tolist() == pytest.approx(
        [(500.0 - 495.0) / 500.0 * 100, (501.0 - 495.0) / 501.0 * 100])


@pytest.mark.parametrize("module", ["strat", "p7"])
def test_features_on_d_select_d_minus_2_with_null_flip(gamma_levels, module):
    out = _context_on_d(_builder(module), gamma_levels)
    _assert_d_minus_2_context_with_null_flip(out, module)


@pytest.mark.parametrize("module", ["strat", "p7"])
def test_features_on_d_without_a_d_snapshot_still_select_d_minus_2(gamma_levels, module):
    with gamma_levels.begin() as conn:
        conn.execute(text("DELETE FROM gamma_levels_eod WHERE snapshot_date = :d"), {"d": D})
    out = _context_on_d(_builder(module), gamma_levels)
    _assert_d_minus_2_context_with_null_flip(out, module)


@pytest.mark.parametrize("module", ["strat", "p7"])
def test_missing_prior_is_null_never_zero(gamma_levels, module):
    with gamma_levels.begin() as conn:
        conn.execute(text("DELETE FROM gamma_levels_eod WHERE snapshot_date < :d"), {"d": D})
    out = _context_on_d(_builder(module), gamma_levels)
    for col in ("total_gex", "gamma_balance_price", "gamma_flip",
                "distance_to_king_pct", "distance_to_gate_pct"):
        assert out[col].isna().all(), col
    assert (out["gamma_regime"] == "unknown").all()
