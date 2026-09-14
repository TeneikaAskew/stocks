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


# A minimal valid row is DERIVED from the server, never hand-listed.
#
# The first version of this hand-listed "the NOT NULL columns without
# defaults" for each table and got two of the three wrong:
# historical_signals.trade_type and insight_reports.model_versions are both
# NOT NULL with no default, so the INSERT meant to prove the valid value is
# ACCEPTED failed on 23502 instead, and the typo half never reached the
# CHECK at all. Same defect as the UPDATE version round 3 replaced — a test
# that cannot fail for its own reason — and the same root cause as the
# audit it belongs to: a proxy quoted without being checked against the
# thing it stands for (CLAUDE.md §3.11). Asking information_schema removes
# the hand-list, so the test stays correct as the tables gain columns.
_LITERALS = {
    "character varying": "'ZZZ'",
    "text": "'ZZZ'",
    "character": "'Z'",
    "date": "current_date",
    "timestamp with time zone": "now()",
    "timestamp without time zone": "now()",
    "jsonb": "'{}'::jsonb",
    "json": "'{}'::json",
    "uuid": "gen_random_uuid()",
    "integer": "0",
    "bigint": "0",
    "smallint": "0",
    "numeric": "0",
    "double precision": "0",
    "real": "0",
    "boolean": "false",
    "ARRAY": "'{}'",
}


def _minimal_insert(conn, table: str, run_kind: str) -> str:
    """INSERT naming every column the server requires, and nothing else."""
    cols = conn.execute(text("""
        SELECT column_name, data_type
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = :t
           AND is_nullable = 'NO'
           AND column_default IS NULL
           AND is_generated = 'NEVER'
         ORDER BY ordinal_position
    """), {"t": table}).fetchall()
    assert cols, f"{table} has no required columns — is the schema loaded?"
    names, values = ["run_kind"], [f"'{run_kind}'"]
    for name, dtype in cols:
        # run_kind carries DEFAULT 'live', so the query above excludes it.
        # It is named explicitly because it is the column under test.
        if name == "run_kind":
            continue
        names.append(name)
        # An unknown type raises rather than guessing: a silently wrong
        # literal would fail the INSERT before the CHECK is reached, which
        # is the exact failure this rewrite exists to stop.
        assert dtype in _LITERALS, f"{table}.{name} has unhandled type {dtype!r}"
        values.append(_LITERALS[dtype])
    return (f"INSERT INTO {table} ({', '.join(names)}) "
            f"VALUES ({', '.join(values)})")


def _assert_run_kind_is_not_null(conn, table: str) -> None:
    """A nullable run_kind would let a writer skip the CHECK entirely."""
    row = conn.execute(text("""
        SELECT is_nullable FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = :t
           AND column_name = 'run_kind'
    """), {"t": table}).fetchone()
    assert row is not None, f"{table} has no run_kind column"
    assert row[0] == "NO", f"{table}.run_kind must be NOT NULL"


@pytest.mark.parametrize("table", TABLES)
def test_the_constraint_rejects_a_typo(db_engine, table):
    """'Live' or 'backfil' would be excluded from every reader forever with
    no error anywhere, which is why the CHECK exists at all.

    Tests an INSERT, not an UPDATE. The first version ran
    `UPDATE ... WHERE true` against tables the harness leaves empty:
    Postgres evaluates a CHECK only for affected rows, so zero rows meant
    zero evaluations and `pytest.raises` failed with DID NOT RAISE (Codex
    on #1098 round 3)."""
    with db_engine.connect() as conn:
        trans = conn.begin()
        try:
            _assert_run_kind_is_not_null(conn, table)
            # The valid value is accepted. This half is load-bearing: if it
            # raises for any other reason, the typo half below proves
            # nothing, because it would raise for that reason too.
            conn.execute(text(_minimal_insert(conn, table, "live")))
            # ...and the typo is not.
            with pytest.raises(Exception, match="run_kind_check"):
                conn.execute(text(_minimal_insert(conn, table, "Live")))
        finally:
            trans.rollback()
