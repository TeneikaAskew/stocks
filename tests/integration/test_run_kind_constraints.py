"""The run_kind constraint block is idempotent against a real Postgres.

Audit 2026-09-14 (#1095). The block creates each CHECK only when absent,
because re-adding one validates every row under ACCESS EXCLUSIVE and
`schema.sql` is applied on every schema-touching push — on
historical_signals (1.7M rows) that is a full rescan per deploy, forever.

Codex then pointed out that name-only matching accepts a stale definition:
edit the allowed value set, apply to a database that already holds the
constraint, and the apply succeeds while the old check survives, so the
first writer using a new value fails at runtime instead. The block now
compares `pg_get_constraintdef` and raises on drift.

That comparison is the thing this file exists to pin. The expected string is
Postgres's own normalised rendering, which no amount of reading the DDL will
tell you — it was measured against production, and if it is wrong the block
raises on EVERY apply rather than never. A unit test cannot catch that; only
a real server can.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

REPO = Path(__file__).resolve().parents[2]
TABLES = ("historical_signals", "insight_reports", "premarket_analysis")


def _block() -> str:
    """The run_kind constraint DO block, lifted from gcp/schema.sql."""
    sql = (REPO / "gcp/schema.sql").read_text()
    marker = "    want_def  CONSTANT TEXT :="
    assert marker in sql, "the constraint block moved or changed shape"
    start = sql.rindex("DO $$", 0, sql.index(marker))
    end = sql.index("END $$;", start) + len("END $$;")
    block = sql[start:end]
    assert "pg_get_constraintdef" in block and "has drifted" in block
    return block


def test_the_constraint_block_is_idempotent(db_engine):
    """Applying it a second time must be a no-op, not an exception.

    The schema is already loaded by the integration harness, so all three
    constraints exist when this runs. A `want_def` that did not match
    Postgres's normalised output would raise here.
    """
    with db_engine.begin() as conn:
        conn.execute(text(_block()))
        conn.execute(text(_block()))


def test_every_table_carries_the_constraint(db_engine):
    with db_engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT conname FROM pg_constraint
             WHERE conname = ANY(:names)
        """), {"names": [f"{t}_run_kind_check" for t in TABLES]}).fetchall()
    assert {r[0] for r in rows} == {f"{t}_run_kind_check" for t in TABLES}


def test_drift_is_raised_rather_than_silently_accepted(db_engine):
    """Replace one constraint with a different value set, then re-apply:
    the block must refuse rather than leave the stale definition in place.

    This is the failure Codex named. Rolled back, so the schema the other
    integration tests see is untouched."""
    with db_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text(
                "ALTER TABLE insight_reports DROP CONSTRAINT insight_reports_run_kind_check"))
            conn.execute(text(
                "ALTER TABLE insight_reports ADD CONSTRAINT insight_reports_run_kind_check "
                "CHECK (run_kind IN ('live', 'replay'))"))
            with pytest.raises(Exception, match="has drifted"):
                conn.execute(text(_block()))
        finally:
            trans.rollback()


@pytest.mark.parametrize("table", TABLES)
def test_the_constraint_rejects_a_typo(db_engine, table):
    """'Live' or 'backfil' would be excluded from every reader forever with
    no error anywhere, which is why the CHECK exists at all."""
    with db_engine.connect() as conn:
        trans = conn.begin()
        try:
            with pytest.raises(Exception):
                conn.execute(text(
                    f"UPDATE {table} SET run_kind = 'Live' WHERE true"))
        finally:
            trans.rollback()
