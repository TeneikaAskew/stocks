"""Schema tests for the bar flag tables (FEAT-DATA-001, bar misprint flags).

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
(Design 2). `gcp/schema.sql` is read as text and split with
`split_statements`, the way the apply job does, so the assertions run against
what it would execute.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from gcp.apply_schema import split_statements

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "gcp" / "schema.sql"

# (column, type, NOT NULL), in the order of Design 2.
FLAG_COLUMNS = (
    ("ticker", "VARCHAR(10)", True),
    ("interval", "VARCHAR(5)", True),
    ("ts", "TIMESTAMPTZ", True),
    ("side", "VARCHAR(4)", True),
    ("rule_version", "VARCHAR(32)", True),
    ("print_kind", "VARCHAR(14)", True),
    ("session_part", "VARCHAR(8)", True),
    ("observed", "DOUBLE PRECISION", True),
    ("reference", "DOUBLE PRECISION", True),
    ("bound", "DOUBLE PRECISION", True),
    ("scale", "DOUBLE PRECISION", True),
    ("excess_bp", "DOUBLE PRECISION", True),
    ("read_start", "TIMESTAMPTZ", True),
    ("read_end", "TIMESTAMPTZ", True),
    ("detected_at", "TIMESTAMPTZ", True),
    ("checked_at", "TIMESTAMPTZ", True),
    ("run_id", "TEXT", True),
)

COVERAGE_COLUMNS = (
    ("ticker", "VARCHAR(10)", True),
    ("interval", "VARCHAR(5)", True),
    ("ts", "TIMESTAMPTZ", True),
    ("rule_version", "VARCHAR(32)", True),
    ("month", "DATE", True),
    ("read_start", "TIMESTAMPTZ", True),
    ("read_end", "TIMESTAMPTZ", True),
    ("params", "JSONB", True),
    ("bars_in_month", "INTEGER", True),
    ("bars_judged", "INTEGER", True),
    ("first_judged_ts", "TIMESTAMPTZ", False),
    ("last_judged_ts", "TIMESTAMPTZ", False),
    ("flags_regular_high", "INTEGER", True),
    ("flags_regular_low", "INTEGER", True),
    ("flags_extended_high", "INTEGER", True),
    ("flags_extended_low", "INTEGER", True),
    ("bars_basis", "JSONB", True),
    ("session_sha256", "JSONB", True),
    ("code_version", "JSONB", True),
    ("run_id", "TEXT", True),
    ("checked_at", "TIMESTAMPTZ", True),
)

INTRADAY_FIRST = "CREATE TABLE IF NOT EXISTS market_data_intraday ("
INTRADAY_LAST = (
    "CREATE INDEX IF NOT EXISTS idx_market_data_intraday_lookup\n"
    "    ON market_data_intraday (ticker, interval, ts DESC);"
)


def _norm(stmt: str) -> str:
    """Strip comments and collapse whitespace."""
    lines = [ln.split("--")[0] if "--" in ln else ln for ln in stmt.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines)).strip().rstrip(";").strip()


def _statement(table: str) -> str:
    head = f"CREATE TABLE IF NOT EXISTS {table} ("
    found = [
        _norm(s) for s in split_statements(SCHEMA.read_text())
        if _norm(s).startswith(head)
    ]
    assert len(found) == 1, f"expected one statement creating {table}, got {len(found)}"
    return found[0]


def _definitions(statement: str) -> list[str]:
    """The comma-separated definitions between the statement's outer parentheses."""
    body = statement[statement.index("(") + 1:statement.rindex(")")]
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(body[start:i].strip())
            start = i + 1
    parts.append(body[start:].strip())
    return parts


def _columns(statement: str) -> dict[str, str]:
    return {
        part.split(" ")[0]: part for part in _definitions(statement)
        if not part.startswith(("CHECK", "PRIMARY KEY"))
    }


def _assert_columns(table: str, expected) -> None:
    columns = _columns(_statement(table))
    assert list(columns) == [name for name, _, _ in expected]
    for name, sql_type, not_null in expected:
        definition = columns[name]
        assert definition.startswith(f"{name} {sql_type}"), definition
        assert ("NOT NULL" in definition) is not_null, definition


def test_both_tables_are_created_idempotently():
    text = SCHEMA.read_text()
    for table in ("intraday_bar_flags", "intraday_bar_flag_coverage"):
        assert text.count(f"CREATE TABLE IF NOT EXISTS {table} (") == 1
        assert len(re.findall(rf"CREATE TABLE\s+{table}\b", text)) == 0


def test_the_flag_table_has_the_columns_of_design_2():
    _assert_columns("intraday_bar_flags", FLAG_COLUMNS)
    columns = _columns(_statement("intraday_bar_flags"))
    assert columns["interval"] == "interval VARCHAR(5) NOT NULL DEFAULT '1min'"
    assert columns["side"] == "side VARCHAR(4) NOT NULL CHECK (side IN ('high', 'low'))"
    assert columns["print_kind"] == (
        "print_kind VARCHAR(14) NOT NULL "
        "CHECK (print_kind IN ('wick', 'open', 'close', 'open_and_close'))"
    )
    assert columns["session_part"] == (
        "session_part VARCHAR(8) NOT NULL CHECK (session_part IN ('regular', 'extended'))"
    )


def test_the_flag_table_has_its_checks_and_key():
    definitions = _definitions(_statement("intraday_bar_flags"))
    assert "CHECK (read_start < read_end)" in definitions
    assert "PRIMARY KEY (ticker, interval, ts, side, rule_version)" in definitions
    assert sum(d.startswith("PRIMARY KEY") for d in definitions) == 1


def test_the_coverage_table_has_the_columns_of_design_2():
    _assert_columns("intraday_bar_flag_coverage", COVERAGE_COLUMNS)
    columns = _columns(_statement("intraday_bar_flag_coverage"))
    assert columns["interval"] == "interval VARCHAR(5) NOT NULL DEFAULT '1min'"
    assert columns["first_judged_ts"] == "first_judged_ts TIMESTAMPTZ"
    assert columns["last_judged_ts"] == "last_judged_ts TIMESTAMPTZ"


def test_the_coverage_table_has_its_checks_and_key():
    definitions = _definitions(_statement("intraday_bar_flag_coverage"))
    assert "CHECK ((bars_judged = 0) = (first_judged_ts IS NULL))" in definitions
    assert "CHECK (read_start < read_end)" in definitions
    assert "PRIMARY KEY (ticker, interval, ts, rule_version)" in definitions
    assert sum(d.startswith("PRIMARY KEY") for d in definitions) == 1


def _intraday_span(text: str) -> str:
    assert text.count(INTRADAY_FIRST) == 1
    assert text.count(INTRADAY_LAST) == 1
    return text[text.index(INTRADAY_FIRST):text.index(INTRADAY_LAST) + len(INTRADAY_LAST)]


# The span's sha256 on origin/main at 999727f1, taken once with
# `git show origin/main:gcp/schema.sql`. A literal keeps the test hermetic:
# CI checks out one commit and has no origin/main to read.
INTRADAY_SPAN_SHA256 = "d8559c99e21f13ac6a780c8845adfc143d9a924aa3caecaa766ef5b4e7decac4"


def test_market_data_intraday_is_byte_for_byte_as_on_main():
    span = _intraday_span(SCHEMA.read_bytes().decode())
    assert hashlib.sha256(span.encode()).hexdigest() == INTRADAY_SPAN_SHA256
    # The span is the table, its five partitions and its index, and nothing else.
    assert len(split_statements(span)) == 7
    assert "intraday_bar_flag" not in span
