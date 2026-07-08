"""Phase 2 journal_entries migration — chart-marked trades unification.

Verifies that gcp/schema.sql includes idempotent migrations for journal_entries
to support chart-marked trades: TP/SL levels, active state, source discriminator,
and nullable exit columns for in-flight trades.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "gcp" / "schema.sql"


def _read_schema() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def test_journal_migration_columns_added_idempotently():
    """All new Phase 2 columns must be added via ADD COLUMN IF NOT EXISTS."""
    sql = _read_schema()
    for col in ("stop_loss", "tp1", "tp2", "tp3", "status", "source", "session_id"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in sql, f"missing idempotent ADD for {col}"


def test_exit_columns_made_nullable():
    """exit_ts and exit_price become nullable for active (unexited) trades.

    The assertion is regex-based to tolerate whitespace variation in the schema.
    """
    sql = _read_schema()
    # Normalize internal whitespace to single space for robust matching
    sql_normalized = re.sub(r"\s+", " ", sql)

    exit_ts_pattern = r"ALTER\s+TABLE\s+journal_entries\s+ALTER\s+COLUMN\s+exit_ts\s+DROP\s+NOT\s+NULL"
    exit_price_pattern = r"ALTER\s+TABLE\s+journal_entries\s+ALTER\s+COLUMN\s+exit_price\s+DROP\s+NOT\s+NULL"

    assert re.search(exit_ts_pattern, sql_normalized), \
        "exit_ts must be made nullable via ALTER COLUMN exit_ts DROP NOT NULL"
    assert re.search(exit_price_pattern, sql_normalized), \
        "exit_price must be made nullable via ALTER COLUMN exit_price DROP NOT NULL"


def test_source_index_exists():
    """Query optimization index on (user_email, source, entry_ts DESC)."""
    sql = _read_schema()
    assert "idx_journal_entries_user_source" in sql, \
        "missing index idx_journal_entries_user_source"


def test_status_default_is_closed():
    """New trades without an explicit status default to 'closed' (legacy behavior)."""
    sql = _read_schema()
    # The ADD COLUMN statement must include DEFAULT 'closed'
    assert re.search(
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+status\s+VARCHAR\(10\)\s+NOT\s+NULL\s+DEFAULT\s+'closed'",
        re.sub(r"\s+", " ", sql)
    ), "status column must have DEFAULT 'closed'"


def test_source_default_is_manual():
    """New trades without an explicit source default to 'manual' (backward compat)."""
    sql = _read_schema()
    assert re.search(
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+source\s+VARCHAR\(10\)\s+NOT\s+NULL\s+DEFAULT\s+'manual'",
        re.sub(r"\s+", " ", sql)
    ), "source column must have DEFAULT 'manual'"


def test_session_id_is_nullable():
    """session_id (for replay-trainer grouping) is optional."""
    sql = _read_schema()
    assert re.search(
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+session_id\s+UUID",
        re.sub(r"\s+", " ", sql)
    ), "session_id must be added and nullable (no NOT NULL constraint)"
