"""Schema tests for the bar recompute ledger and its marker columns
(FEAT-DATA-001, recompute paths after the bar rewrite).

`gcp/schema.sql` is read as text and split with `split_statements`, the way
the apply job does, so the assertions run against what it would execute.
"""

from __future__ import annotations

import re
from pathlib import Path

from gcp.apply_schema import split_statements

SCHEMA = Path(__file__).resolve().parents[2] / "gcp" / "schema.sql"

# The appended block starts at this comment line and runs to the end of file.
BLOCK_MARKER = "-- Bar recompute ledger and markers (FEAT-DATA-001)"

LEDGER_COLUMNS = (
    "id", "run_id", "target", "action", "ticker", "session_date", "row_key",
    "old_values", "new_values", "changed", "basis", "written_at",
)

MARKER_LINES = (
    "ALTER TABLE signal_alerts ADD COLUMN IF NOT EXISTS exit_recompute_run TEXT",
    "ALTER TABLE trades ADD COLUMN IF NOT EXISTS exit_recompute_run TEXT",
    "ALTER TABLE market_data_daily ADD COLUMN IF NOT EXISTS pre_recompute_run TEXT",
)


def _norm(stmt: str) -> str:
    """Strip comments and collapse whitespace."""
    lines = [ln.split("--")[0] if "--" in ln else ln for ln in stmt.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines)).strip().rstrip(";").strip()


def _ledger_statement() -> str:
    found = [
        _norm(s) for s in split_statements(SCHEMA.read_text())
        if _norm(s).startswith("CREATE TABLE IF NOT EXISTS bar_recompute_ledger")
    ]
    assert len(found) == 1, f"expected one ledger statement, got {len(found)}"
    return found[0]


def test_the_ledger_and_the_markers_are_declared():
    text = SCHEMA.read_text()
    assert "CREATE TABLE IF NOT EXISTS bar_recompute_ledger" in text
    ledger = _ledger_statement()
    body = ledger[ledger.index("(") + 1:]
    declared = [part.strip().split(" ")[0] for part in re.split(r",(?![^(]*\))", body)]
    for column in LEDGER_COLUMNS:
        assert column in declared, f"{column} is not a column of the ledger"
    assert "UNIQUE (run_id, target, ticker, row_key)" in ledger
    normalized = {_norm(s) for s in split_statements(text)}
    for line in MARKER_LINES:
        assert line in normalized, line


def test_the_action_and_target_columns_hold_their_values():
    ledger = _ledger_statement()
    action = int(re.search(r"\baction VARCHAR\((\d+)\)", ledger).group(1))
    target = int(re.search(r"\btarget VARCHAR\((\d+)\)", ledger).group(1))
    assert action >= len("recompute")
    assert target >= len("signal-alert-exits")


def test_the_block_is_four_statements_for_the_applier():
    text = SCHEMA.read_text()
    assert text.count(BLOCK_MARKER) == 1
    block = text[text.index(BLOCK_MARKER):]
    assert len(split_statements(block)) == 4
