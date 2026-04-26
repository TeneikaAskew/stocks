"""Unit tests for `gcp/apply_schema.py::split_statements`.

The Cloud Run Job parses `gcp/schema.sql` into individual statements
before executing each one. Wrong splitting corrupts trigger functions
silently — the apply succeeds with a warning, but the trigger body is
truncated. Tests cover:

    - Plain statements split on `;`
    - `$$`-quoted PL/pgSQL bodies kept whole even with internal `;`
    - Comment + blank lines don't trigger statement breaks
    - Leftover (no trailing `;`) is still emitted
    - Even number of `$$` toggles on one line nets to 0
    - Empty input → empty list
"""

from __future__ import annotations

import pytest

from gcp.apply_schema import split_statements


# ──────────────────────────────────────────────────────────────────────
# Plain statements
# ──────────────────────────────────────────────────────────────────────


def test_single_statement_no_trailing_semicolon():
    out = split_statements("CREATE TABLE x (id INT)")
    assert len(out) == 1
    assert "CREATE TABLE x (id INT)" in out[0]


def test_two_simple_statements_split_on_semicolon():
    sql = """
    CREATE TABLE a (id INT);
    CREATE TABLE b (id INT);
    """
    out = split_statements(sql)
    assert len(out) == 2
    assert "CREATE TABLE a" in out[0]
    assert "CREATE TABLE b" in out[1]


def test_empty_input_returns_empty_list():
    assert split_statements("") == []
    assert split_statements("\n\n  \n") == []


def test_comment_only_input_returns_empty_list():
    sql = """
    -- This is just a comment
    -- and another one
    """
    assert split_statements(sql) == []


# ──────────────────────────────────────────────────────────────────────
# Dollar-quoted PL/pgSQL bodies
# ──────────────────────────────────────────────────────────────────────


def test_dollar_quoted_body_is_kept_whole():
    """Trigger function with `;` inside its body must NOT be split."""
    sql = """
    CREATE OR REPLACE FUNCTION update_modified() RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    out = split_statements(sql)
    assert len(out) == 1
    # All four internal lines (BEGIN, NEW.updated_at, RETURN NEW, END)
    # must be in the single statement
    assert "BEGIN" in out[0]
    assert "NEW.updated_at = NOW();" in out[0]
    assert "RETURN NEW;" in out[0]
    assert "END;" in out[0]


def test_two_functions_split_at_outer_semicolons():
    sql = """
    CREATE FUNCTION f1() RETURNS TRIGGER AS $$
    BEGIN
        RAISE NOTICE 'one';
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;

    CREATE FUNCTION f2() RETURNS TRIGGER AS $$
    BEGIN
        RAISE NOTICE 'two';
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    out = split_statements(sql)
    assert len(out) == 2
    assert "f1" in out[0] and "f2" not in out[0]
    assert "f2" in out[1] and "f1" not in out[1]


def test_function_followed_by_plain_statement():
    sql = """
    CREATE FUNCTION f() RETURNS TRIGGER AS $$
    BEGIN
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TABLE t (id INT);
    """
    out = split_statements(sql)
    assert len(out) == 2
    assert "FUNCTION f" in out[0]
    assert "CREATE TABLE t" in out[1]


def test_two_dollar_quotes_on_same_line_net_to_zero():
    """A line with TWO `$$` markers (e.g. `AS $$ body $$`) toggles
    in→out → still outside. Statement boundaries should detect the `;`
    after that line."""
    sql = "CREATE FUNCTION trivial() RETURNS INT AS $$ SELECT 1; $$ LANGUAGE sql;"
    out = split_statements(sql)
    # Note: the inner `;` is INSIDE the dollar quote (since the toggle
    # closes after the second `$$`, we exit dollar-mode at end of line).
    # The trailing `;` outside the quote terminates the statement.
    assert len(out) == 1
    assert "trivial" in out[0]


# ──────────────────────────────────────────────────────────────────────
# Leftover handling — no trailing `;`
# ──────────────────────────────────────────────────────────────────────


def test_unterminated_statement_is_still_emitted():
    """Schema files often have trailing whitespace or omit final `;`.
    The trailing buffer must be returned as a final statement."""
    sql = "CREATE TABLE a (id INT);\nCREATE TABLE b (id INT)\n"
    out = split_statements(sql)
    assert len(out) == 2
    assert "CREATE TABLE b (id INT)" in out[1]


def test_leftover_inside_unclosed_dollar_quote_returned_as_is():
    """If the file is malformed (unclosed $$), the leftover is still
    returned so the caller can surface a clear error rather than
    silently dropping it."""
    sql = "CREATE FUNCTION bad() RETURNS TRIGGER AS $$\nBEGIN\n  -- never closed"
    out = split_statements(sql)
    assert len(out) == 1
    assert "FUNCTION bad" in out[0]


# ──────────────────────────────────────────────────────────────────────
# Comment lines inside a buffered statement
# ──────────────────────────────────────────────────────────────────────


def test_comments_inside_statement_are_preserved():
    """Comment lines between statements should be skipped, but comments
    INSIDE a buffered statement are kept (PL/pgSQL bodies use them)."""
    sql = """
    -- Pre-statement comment (skipped)
    CREATE FUNCTION f() RETURNS TRIGGER AS $$
    BEGIN
        -- Inside-body comment
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    out = split_statements(sql)
    assert len(out) == 1
    assert "Inside-body comment" in out[0]


def test_blank_lines_between_statements_dont_create_empty_entries():
    sql = """

    CREATE TABLE a (id INT);



    CREATE TABLE b (id INT);

    """
    out = split_statements(sql)
    assert len(out) == 2
    # No empty / whitespace-only entries
    assert all(s.strip() for s in out)


# ──────────────────────────────────────────────────────────────────────
# Real-world fixture — round-trip a representative subset of schema.sql
# ──────────────────────────────────────────────────────────────────────


def test_round_trips_real_schema_subset():
    """The smoke test against a representative slice of schema.sql:
    a CREATE TABLE, an index, and a trigger function. Splitting must
    yield exactly 3 statements, with the trigger function intact."""
    sql = """
    -- Comment header
    CREATE TABLE IF NOT EXISTS market_data_daily (
        ticker VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        close DOUBLE PRECISION,
        PRIMARY KEY (ticker, date)
    );

    CREATE INDEX IF NOT EXISTS idx_md_date ON market_data_daily (date DESC);

    CREATE OR REPLACE FUNCTION trg_md_modified() RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    out = split_statements(sql)
    assert len(out) == 3
    assert "CREATE TABLE" in out[0]
    assert "CREATE INDEX" in out[1]
    assert "CREATE OR REPLACE FUNCTION" in out[2]
    assert "RETURN NEW;" in out[2], "trigger body kept whole"
