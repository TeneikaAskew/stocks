"""Real-SQL coverage for the realtime options-mark path (Track 2 phase 2a).

Replaces scripts/validate_track2_live.py, which did the same job by
INSERTing six synthetic option snapshots into the PRODUCTION
`etf_options_snapshots` table and deleting them afterwards (audit
2026-09-14). It was carefully built — an impossible strike (99999.99) and
a `TRACK2_TEST_` contract prefix so it could not collide, cleanup in a
`finally` — and production was verified clean, 0 rows left. It is still
the wrong place: synthetic rows belong in a throwaway database, not in the
table the options grid serves, where a crash between INSERT and DELETE
leaves residue and where nothing stops the markers drifting.

What it validates is worth keeping, and hermetic unit tests cannot do it
(CLAUDE.md Rule 0.3 — synthetic in-memory frames run in microseconds,
production runs against the network). The point of the original script was
to prove that this SQL round-trips through cloud-sql-python-connector +
pg8000 + Postgres, that `estimate_options_pnl` dispatches realtime vs
empirical fallback on data PRESENCE, and that `data_source` is populated.
That is exactly what tests/integration/ is for: the same production query
functions, the real schema from gcp/schema.sql, an ephemeral Postgres.

The one thing this cannot cover is the Cloud SQL connector itself, since
the integration DB is reached over DB_HOST. That gap is stated rather than
pretended away; the connector is exercised by every Cloud Run job on every
run, which is stronger coverage than a once-off script was.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

TICKER = "SPY"
VALIDATION_DATE = date(2026, 6, 12)
STRIKE = 500.0
CONTRACT = "SPY260612C00500000"

# Mark drifts up then down; IV crushes monotonically — a realistic 0DTE
# shape, carried over from the script so the assertions stay comparable.
SNAPS = [
    ("2026-06-12 13:30:00+00", 2.50, 0.30, 0.50),
    ("2026-06-12 13:35:00+00", 2.55, 0.28, 0.51),
    ("2026-06-12 13:40:00+00", 2.90, 0.27, 0.55),
    ("2026-06-12 14:00:00+00", 3.20, 0.25, 0.60),
    ("2026-06-12 14:05:00+00", 3.00, 0.24, 0.58),
    ("2026-06-12 14:30:00+00", 2.15, 0.20, 0.45),
]


@pytest.fixture
def realtime_snapshots(db_engine, clean_db):
    """Six REALTIME snapshots for one contract in the ephemeral DB."""
    with db_engine.begin() as conn:
        for ts, mark, iv, delta in SNAPS:
            conn.execute(text("""
                INSERT INTO etf_options_snapshots (
                    ticker, snapshot_ts, snapshot_date, market_session,
                    contract_symbol, option_type, expiration, strike,
                    bid, ask, mark, implied_volatility,
                    delta, gamma, theta, vega, rho, data_source
                ) VALUES (
                    :ticker, :ts, :d, 'REALTIME', :contract,
                    'calls', :d, :strike,
                    :bid, :ask, :mark, :iv,
                    :delta, 0.02, -0.20, 0.10, 0.05, 'alphavantage'
                )
                ON CONFLICT (ticker, snapshot_ts, option_type, expiration, strike)
                DO UPDATE SET mark = EXCLUDED.mark,
                              implied_volatility = EXCLUDED.implied_volatility,
                              delta = EXCLUDED.delta
            """), {
                "ticker": TICKER, "ts": ts, "d": VALIDATION_DATE,
                "contract": CONTRACT, "strike": STRIKE,
                "bid": mark - 0.05, "ask": mark + 0.05,
                "mark": mark, "iv": iv, "delta": delta,
            })
    return SNAPS


def test_theta_curve_round_trips_through_real_postgres(realtime_snapshots):
    """load_realtime_theta_curve's SQL survives a real driver and schema."""
    from lib.options_intraday import load_realtime_theta_curve

    curve = load_realtime_theta_curve(
        ticker=TICKER, intraday_date=VALIDATION_DATE,
        expiration=VALIDATION_DATE, strike=STRIKE, option_type="call",
    )
    assert curve is not None, "query returned no rows against the real schema"
    assert len(curve) == 6
    assert curve["implied_volatility"].iloc[0] == pytest.approx(0.30)
    assert curve["implied_volatility"].iloc[-1] == pytest.approx(0.20)
    assert curve["mark"].iloc[0] == pytest.approx(2.50)
    assert curve["delta"].iloc[2] == pytest.approx(0.55)


def test_realtime_marks_round_trip(realtime_snapshots):
    from scripts.analysis.options_pnl_translation import load_realtime_marks

    marks = load_realtime_marks(
        ticker=TICKER, trade_date=VALIDATION_DATE,
        expiration=VALIDATION_DATE, strike=STRIKE, option_type="call",
    )
    assert not marks.empty
    assert len(marks) == 6
    assert marks["mark"].iloc[0] == pytest.approx(2.50)
    assert marks["mark"].iloc[-1] == pytest.approx(2.15)
    assert marks["bid"].iloc[0] == pytest.approx(2.45)


def test_find_mark_at_picks_the_nearest_snapshot(realtime_snapshots):
    from scripts.analysis.options_pnl_translation import (
        find_realtime_mark_at, load_realtime_marks,
    )

    marks = load_realtime_marks(
        ticker=TICKER, trade_date=VALIDATION_DATE,
        expiration=VALIDATION_DATE, strike=STRIKE, option_type="call",
    )
    target = datetime.combine(VALIDATION_DATE, datetime.min.time(),
                              tzinfo=timezone.utc) + timedelta(hours=14, minutes=2)
    found = find_realtime_mark_at(marks, target)
    assert found is not None
    assert found == pytest.approx(3.20), "14:02 is nearest the 14:00 snapshot"


def test_pnl_dispatches_on_data_presence_not_on_a_flag(realtime_snapshots, db_engine):
    """The dispatch that the original script existed to prove: realtime
    marks present means mark-to-mark, absent means the Greeks-approximation
    fallback, and the answer says which it used. A fabricated value in
    either direction would be silent (CLAUDE.md §3.7)."""
    from scripts.analysis.options_pnl_translation import estimate_options_pnl
    from lib.options_intraday import (
        DATA_SOURCE_EMPIRICAL_FALLBACK, DATA_SOURCE_REALTIME,
    )

    entry = datetime.combine(VALIDATION_DATE, datetime.min.time(),
                             tzinfo=timezone.utc) + timedelta(hours=13, minutes=30)
    exit_ = entry + timedelta(hours=1)

    with_data = estimate_options_pnl(
        ticker=TICKER, trade_date=VALIDATION_DATE, expiration=VALIDATION_DATE,
        strike=STRIKE, option_type="call", entry_ts=entry, exit_ts=exit_,
    )
    assert with_data["data_source"] == DATA_SOURCE_REALTIME

    # Same call against a strike with no snapshots must fall back and SAY so.
    without_data = estimate_options_pnl(
        ticker=TICKER, trade_date=VALIDATION_DATE, expiration=VALIDATION_DATE,
        strike=STRIKE + 25.0, option_type="call", entry_ts=entry, exit_ts=exit_,
    )
    assert without_data["data_source"] == DATA_SOURCE_EMPIRICAL_FALLBACK


def test_no_synthetic_contract_markers_leak_into_the_schema():
    """The script this file replaces wrote rows keyed on strike 99999.99 and
    a 'TRACK2_TEST_' contract prefix into PRODUCTION. Nothing in the repo may
    reintroduce that: a test that needs option rows uses this ephemeral DB."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    offenders = []
    for p in list((repo / "scripts").rglob("*.py")) + list((repo / "gcp").rglob("*.py")):
        if "_archive" in p.parts:
            continue
        text_ = p.read_text(errors="ignore")
        if "TRACK2_TEST_" in text_ or "99999.99" in text_:
            offenders.append(p.relative_to(repo).as_posix())
    assert not offenders, (
        f"synthetic option markers aimed at a production table: {offenders}"
    )
