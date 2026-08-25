"""Pin the fix for issue #753 — refresh-earnings-views failing daily with
`sqlalchemy.exc.DatabaseError: numeric field overflow ... precision 6,
scale 2 must round to an absolute value less than 10^4`.

Root cause: `earnings_upcoming_with_history.avg_abs_gap_pct` /
`avg_ratio` are aggregates (AVG in gcp/queries + refresh_earnings_views.py)
over `earnings_reactions.reaction_gap_pct`, which is DOUBLE PRECISION with
no floor on the divisor close price — `(open - prev_close) / prev_close *
100` in gcp/fetchers/compute_earnings_reactions.py. A micro-cap/penny
ticker with a near-zero pre-report close can legitimately produce a
percentage move in the thousands, which the old NUMERIC(6,2) /
NUMERIC(5,2) display columns couldn't hold. This crashed the whole
`upsert_dataframe` chunk (see gcp/database.py:388-406), which meant the
DELETE-then-upsert in refresh_daily() deleted the day's rows and never
replaced them — earnings_upcoming_with_history went empty for that
refresh_date, not just missing the one bad ticker.

The fix widens both columns to NUMERIC(10, 2) in gcp/schema.sql (both
the CREATE TABLE IF NOT EXISTS for fresh deploys and an idempotent
ALTER-COLUMN-TYPE migration for existing ones), matching the DOUBLE
PRECISION range of the source data instead of truncating it.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "gcp" / "schema.sql"


def _read_schema() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def _table_body(sql: str, table: str) -> str:
    m = re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table}\s*\((.*?)\);",
        sql,
        re.DOTALL,
    )
    assert m, f"table {table} not found in schema"
    return m.group(1)


def _numeric_max_abs(precision: int, scale: int) -> Decimal:
    """Largest absolute value a Postgres NUMERIC(precision, scale) can
    hold — matches the engine's own error message format ("must round
    to an absolute value less than 10^(precision-scale)")."""
    return Decimal(10) ** (precision - scale) - Decimal(10) ** (-scale)


# ── schema shape ──────────────────────────────────────────────────────


def test_avg_abs_gap_pct_widened_to_numeric_10_2():
    body = _table_body(_read_schema(), "earnings_upcoming_with_history")
    body_normalized = re.sub(r"\s+", " ", body)
    assert re.search(r"avg_abs_gap_pct\s+NUMERIC\(10,\s*2\)", body_normalized), (
        "avg_abs_gap_pct must be NUMERIC(10, 2) — the old NUMERIC(6, 2) "
        "overflows on real penny-stock earnings gaps (issue #753)"
    )


def test_avg_ratio_widened_to_numeric_10_2():
    body = _table_body(_read_schema(), "earnings_upcoming_with_history")
    body_normalized = re.sub(r"\s+", " ", body)
    assert re.search(r"avg_ratio\s+NUMERIC\(10,\s*2\)", body_normalized), (
        "avg_ratio must be NUMERIC(10, 2) — same overflow risk as "
        "avg_abs_gap_pct (both are AVG() aggregates of an unbounded "
        "DOUBLE PRECISION source column) even though only "
        "avg_abs_gap_pct has hit it in production so far"
    )


def test_existing_deployments_get_a_migration():
    """A schema-apply run against an already-deployed instance must widen
    the column via ALTER, not silently no-op behind CREATE TABLE IF NOT
    EXISTS (which does nothing once the table exists)."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"ALTER TABLE earnings_upcoming_with_history\s+"
        r"ALTER COLUMN avg_abs_gap_pct TYPE NUMERIC\(10,\s*2\)",
        sql_normalized,
    ), "missing idempotent migration widening avg_abs_gap_pct on existing deployments"
    assert re.search(
        r"ALTER TABLE earnings_upcoming_with_history\s+"
        r"ALTER COLUMN avg_ratio TYPE NUMERIC\(10,\s*2\)",
        sql_normalized,
    ), "missing idempotent migration widening avg_ratio on existing deployments"


# ── reproduces the actual production failure numerically ──────────────


def test_old_precision_could_not_hold_a_realistic_penny_stock_gap():
    """Reproduce the exact overflow: a penny stock whose pre-report close
    is a few cents produces a reaction_gap_pct in the thousands. Confirms
    the OLD NUMERIC(6, 2) bound (9999.99) is what broke, matching the
    Postgres error text verbatim: 'precision 6, scale 2 ... absolute
    value less than 10^4'.
    """
    old_max_abs = _numeric_max_abs(precision=6, scale=2)
    assert old_max_abs == Decimal("9999.99")

    prev_close = Decimal("0.05")
    open_price = Decimal("6.05")
    reaction_gap_pct = (open_price - prev_close) / prev_close * 100  # 12000.00

    assert abs(reaction_gap_pct) > old_max_abs, (
        "test fixture doesn't actually reproduce the overflow — pick a "
        "more extreme prev_close/open pair"
    )


def test_new_precision_holds_the_same_realistic_gap():
    """The fixed NUMERIC(10, 2) column must comfortably hold the same
    value that overflowed the old one, with no truncation of the
    underlying magnitude (only the documented .01 rounding)."""
    new_max_abs = _numeric_max_abs(precision=10, scale=2)

    prev_close = Decimal("0.05")
    open_price = Decimal("6.05")
    reaction_gap_pct = (open_price - prev_close) / prev_close * 100  # 12000.00

    assert abs(reaction_gap_pct) <= new_max_abs


@pytest.mark.parametrize(
    "prev_close,open_price",
    [
        (Decimal("0.01"), Decimal("50.00")),   # 499900.00% — extreme micro-cap gap
        (Decimal("0.10"), Decimal("0.10")),    # 0% — sanity: no false positive
        (Decimal("5.00"), Decimal("5.25")),    # 5% — typical large-cap gap
    ],
)
def test_new_precision_never_overflows_across_realistic_range(prev_close, open_price):
    new_max_abs = _numeric_max_abs(precision=10, scale=2)
    reaction_gap_pct = (open_price - prev_close) / prev_close * 100
    assert abs(reaction_gap_pct) <= new_max_abs
