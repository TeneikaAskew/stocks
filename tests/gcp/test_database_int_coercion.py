"""Tests for gcp/database.py:_coerce_int_columns — the systemic fix for
the recurring 22P02 ("invalid input syntax for type integer") bug class.

pandas widens an INTEGER column to float64 the moment any row carries a
NaN; pg8000 then binds the value as the string "15.0" and Postgres
rejects it. _coerce_int_columns, called inside upsert_dataframe /
bulk_insert_dataframe off the reflected table schema, coerces every
INTEGER-family column back to int (NaN → None) for ALL callers — so the
bug can't be reintroduced by a new writer that forgets a per-caller
coercion list.

Hermetic — builds a SQLAlchemy Table in an in-memory MetaData, no DB.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import sqlalchemy

from gcp.database import _coerce_int_columns


def _table():
    """A SQLAlchemy Table covering all three INT widths + non-INT columns."""
    meta = sqlalchemy.MetaData()
    return sqlalchemy.Table(
        "t", meta,
        sqlalchemy.Column("id", sqlalchemy.BigInteger),
        sqlalchemy.Column("small_n", sqlalchemy.SmallInteger),
        sqlalchemy.Column("n", sqlalchemy.Integer),
        sqlalchemy.Column("price", sqlalchemy.Float),
        sqlalchemy.Column("label", sqlalchemy.String),
    )


def test_float_widened_int_column_is_coerced():
    """An INT column widened to float64 by a NaN: finite rows → int,
    NaN row → None."""
    tbl = _table()
    df = pd.DataFrame({
        "n": [15.0, np.nan, 3.0],   # float64 because of the NaN
        "label": ["a", "b", "c"],
    })
    assert df["n"].dtype == np.float64  # precondition: pandas widened it

    out = _coerce_int_columns(df, tbl)
    vals = list(out["n"])
    assert vals[0] == 15 and isinstance(vals[0], int)
    assert vals[1] is None
    assert vals[2] == 3 and isinstance(vals[2], int)


def test_all_int_widths_covered():
    """BigInteger, SmallInteger and Integer columns are all coerced —
    SmallInteger/BigInteger subclass sqlalchemy.Integer."""
    tbl = _table()
    df = pd.DataFrame({
        "id":      [100.0, np.nan],
        "small_n": [1.0, 2.0],
        "n":       [np.nan, 7.0],
    })
    out = _coerce_int_columns(df, tbl)
    assert list(out["id"]) == [100, None]
    assert list(out["small_n"]) == [1, 2]
    assert list(out["n"]) == [None, 7]
    for col in ("id", "small_n", "n"):
        for v in out[col]:
            assert v is None or isinstance(v, int)


def test_non_int_columns_untouched():
    """Float and String columns must pass through unchanged — coercion
    is INTEGER-only."""
    tbl = _table()
    df = pd.DataFrame({
        "n":     [1.0, np.nan],
        "price": [10.5, np.nan],
        "label": ["x", None],
    })
    out = _coerce_int_columns(df, tbl)
    # price stays float (NaN preserved, not turned to None-or-int)
    assert out["price"].iloc[0] == 10.5
    assert pd.isna(out["price"].iloc[1])
    assert out["label"].iloc[0] == "x"


def test_input_dataframe_not_mutated():
    """_coerce_int_columns returns a new frame; the caller's df is intact."""
    tbl = _table()
    df = pd.DataFrame({"n": [1.0, np.nan]})
    before = df["n"].copy()
    _coerce_int_columns(df, tbl)
    pd.testing.assert_series_equal(df["n"], before)


def test_no_int_columns_in_df_is_noop():
    """A df with no INT-typed columns returns unchanged (same object)."""
    tbl = _table()
    df = pd.DataFrame({"label": ["a", "b"], "price": [1.1, 2.2]})
    out = _coerce_int_columns(df, tbl)
    assert out is df


def test_clean_int_column_stays_int():
    """An already-clean int64 column (no NaN) survives coercion as ints."""
    tbl = _table()
    df = pd.DataFrame({"n": [1, 2, 3]})
    out = _coerce_int_columns(df, tbl)
    assert list(out["n"]) == [1, 2, 3]
    for v in out["n"]:
        assert isinstance(v, int)


def test_negative_and_numpy_scalar_values():
    """Regression for the exact backtest failure: strat_bonus = -1.0
    (numpy float) → -1 (int), not the string '-1.0'."""
    tbl = _table()
    df = pd.DataFrame({"n": pd.Series([np.float64(-1.0), np.float64(0.0)])})
    out = _coerce_int_columns(df, tbl)
    assert list(out["n"]) == [-1, 0]
    assert all(isinstance(v, int) for v in out["n"])


# ── _na_to_none_records: NaN/NaT → None so writes bind SQL NULL, not float8 NaN
#    (2026-06-07 audit family B — flip_price etc. stored NaN, breaking IS NULL).
from gcp.database import _na_to_none_records


class TestNaToNoneRecords:
    def test_float_nan_becomes_none(self):
        recs = _na_to_none_records([{"flip": float("nan"), "x": 1.5, "lbl": "a"}])
        assert recs[0]["flip"] is None
        assert recs[0]["x"] == 1.5
        assert recs[0]["lbl"] == "a"

    def test_nat_and_none_become_none(self):
        recs = _na_to_none_records([{"ts": pd.NaT, "v": None, "ok": 3}])
        assert recs[0]["ts"] is None and recs[0]["v"] is None and recs[0]["ok"] == 3

    def test_zero_and_string_nan_preserved(self):
        # §3.7: 0.0 is a real value (must NOT become None); the STRING 'nan' is not NA.
        recs = _na_to_none_records([{"z": 0.0, "neg": -1, "s": "nan"}])
        assert recs[0]["z"] == 0.0 and recs[0]["neg"] == -1 and recs[0]["s"] == "nan"

    def test_non_scalar_left_as_is(self):
        recs = _na_to_none_records([{"arr": [1, 2], "ok": 1}])
        assert recs[0]["arr"] == [1, 2] and recs[0]["ok"] == 1
