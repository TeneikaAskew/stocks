"""Pin the fix for issue #1983: the daily refresh-earnings-views run fails with
``22P02 invalid input syntax for type integer: "43.0"``.

``refresh_daily`` builds its rows with ``_safe_int`` (Python ``int`` or
``None``) and then ``pd.DataFrame(rows)``. pandas widens an INTEGER column to
``float64`` the moment one row carries ``None`` (``43`` becomes ``43.0``), and
``_replace_upcoming_rows`` handed those floats straight to ``table.insert()``.
pg8000 renders a float as ``43.0`` under the INTEGER oid SQLAlchemy declares
for the column, and Postgres refuses it. ``upsert_dataframe`` had been running
``gcp.database._coerce_int_columns`` on exactly this frame; the direct insert
that #1608 introduced (one transaction, so a failed insert cannot erase the
prior snapshot) bypassed it. The first daily run on the deployed image,
``refresh-earnings-views-kjjd9`` on 2026-11-16, bound ``43.0`` for
``total_quarters`` (parameter $20) and exited 1.

These tests capture the records the function binds, so they fail on the
pre-fix code without a Postgres: SQLite's INTEGER affinity would have
accepted ``43.0`` and hidden the defect.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
import sqlalchemy as sa

from gcp import refresh_earnings_views as rev

TODAY = date(2026, 11, 16)

INT_COLUMNS = ("options_volume", "open_interest", "total_quarters", "n_beats",
               "n_meets", "n_misses", "long_winner_count", "short_winner_count")


@pytest.fixture
def engine(monkeypatch):
    """An in-memory table with the INTEGER / FLOAT / JSON columns of
    earnings_upcoming_with_history that the frame below writes."""
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE earnings_upcoming_with_history (
                refresh_date DATE NOT NULL,
                ticker TEXT NOT NULL,
                earnings_date DATE NOT NULL,
                options_volume INTEGER,
                open_interest INTEGER,
                total_quarters INTEGER,
                n_beats INTEGER,
                n_meets INTEGER,
                n_misses INTEGER,
                long_winner_count INTEGER,
                short_winner_count INTEGER,
                beat_rate_pct FLOAT,
                lean_score FLOAT,
                last_3_events JSON,
                PRIMARY KEY (refresh_date, ticker, earnings_date)
            )"""))
    monkeypatch.setattr(rev, "get_engine", lambda: eng)
    return eng


def _capture_insert_records(engine) -> list[dict]:
    """The row dicts SQLAlchemy hands the driver for the INSERT, before any
    dialect rendering, which is what pg8000 would bind in production."""
    captured: list[dict] = []

    @sa.event.listens_for(engine, "before_execute")
    def _grab(conn, clauseelement, multiparams, params, execution_options):
        if isinstance(clauseelement, sa.sql.dml.Insert):
            for batch in multiparams:
                if isinstance(batch, dict):
                    captured.append(batch)
                else:
                    captured.extend(batch)

    return captured


def _frame_as_refresh_daily_builds_it() -> pd.DataFrame:
    """Two reporters: one with lean stats (ints), one without (None), exactly
    the mix the 2026-11-16 run had (211 of 980 tickers with lean stats)."""
    rows = [
        {
            "refresh_date": TODAY, "ticker": "WITHLEAN", "earnings_date": TODAY,
            "options_volume": rev._safe_int(12000), "open_interest": rev._safe_int(None),
            "total_quarters": rev._safe_int(43), "n_beats": rev._safe_int(30),
            "n_meets": rev._safe_int(5), "n_misses": rev._safe_int(8),
            "long_winner_count": rev._safe_int(7), "short_winner_count": rev._safe_int(0),
            "beat_rate_pct": rev._safe_float(69.77), "lean_score": rev._safe_float(None),
            "last_3_events": [{"date": "2026-08-12", "beat_meet_miss": "beat"}],
        },
        {
            "refresh_date": TODAY, "ticker": "NOLEAN", "earnings_date": TODAY,
            "options_volume": rev._safe_int(None), "open_interest": rev._safe_int(None),
            "total_quarters": rev._safe_int(None), "n_beats": rev._safe_int(None),
            "n_meets": rev._safe_int(None), "n_misses": rev._safe_int(None),
            "long_winner_count": rev._safe_int(None), "short_winner_count": rev._safe_int(None),
            "beat_rate_pct": rev._safe_float(None), "lean_score": rev._safe_float(None),
            "last_3_events": [],
        },
    ]
    frame = pd.DataFrame(rows)
    # The mechanism under test: pandas widened every INTEGER column that holds
    # a None to float64, so 43 is now 43.0 inside the frame.
    assert frame["total_quarters"].dtype == "float64"
    assert frame.loc[0, "total_quarters"] == 43.0
    return frame


def test_integer_columns_bind_as_int_or_none(engine):
    captured = _capture_insert_records(engine)

    n = rev._replace_upcoming_rows(_frame_as_refresh_daily_builds_it(), TODAY)

    assert n == 2
    assert len(captured) == 2
    by_ticker = {r["ticker"]: r for r in captured}
    for col in INT_COLUMNS:
        for ticker, rec in by_ticker.items():
            v = rec[col]
            assert v is None or type(v) is int, (
                f"{ticker}.{col} bound as {v!r} ({type(v).__name__}); pg8000 "
                f"renders a float as '{v}' under the INTEGER oid and Postgres "
                f"refuses it with 22P02 (issue #1983)"
            )
    assert by_ticker["WITHLEAN"]["total_quarters"] == 43
    assert by_ticker["WITHLEAN"]["short_winner_count"] == 0
    assert by_ticker["WITHLEAN"]["open_interest"] is None
    assert all(by_ticker["NOLEAN"][c] is None for c in INT_COLUMNS)


def test_float_columns_still_bind_nan_as_none(engine):
    captured = _capture_insert_records(engine)

    rev._replace_upcoming_rows(_frame_as_refresh_daily_builds_it(), TODAY)

    by_ticker = {r["ticker"]: r for r in captured}
    assert by_ticker["WITHLEAN"]["beat_rate_pct"] == pytest.approx(69.77)
    assert by_ticker["WITHLEAN"]["lean_score"] is None
    assert by_ticker["NOLEAN"]["beat_rate_pct"] is None


def test_rows_land_and_replace_the_same_refresh_date(engine):
    """The one-transaction replace keeps working: a second run for the same
    refresh_date leaves exactly the new rows, and the stored integers read
    back as integers."""
    frame = _frame_as_refresh_daily_builds_it()
    rev._replace_upcoming_rows(frame, TODAY)
    rev._replace_upcoming_rows(frame.iloc[:1], TODAY)

    with engine.connect() as conn:
        rows = conn.execute(sa.text(
            "SELECT ticker, total_quarters, typeof(total_quarters) "
            "FROM earnings_upcoming_with_history ORDER BY ticker")).all()
    assert rows == [("WITHLEAN", 43, "integer")]


def test_empty_frame_only_deletes(engine):
    captured = _capture_insert_records(engine)
    rev._replace_upcoming_rows(_frame_as_refresh_daily_builds_it(), TODAY)
    assert rev._replace_upcoming_rows(pd.DataFrame(), TODAY) == 0
    assert len(captured) == 2
    with engine.connect() as conn:
        assert conn.execute(sa.text(
            "SELECT count(*) FROM earnings_upcoming_with_history")).scalar() == 0
