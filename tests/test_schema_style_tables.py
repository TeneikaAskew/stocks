"""Phase 4 style-mining schema — user_style_results + playbook_cards_staging.

Verifies that gcp/schema.sql includes idempotent table creation for:
1. user_style_results: mined style profiles per user/ticker with validation metrics
2. playbook_cards_staging: staging table for candidate playbook cards pending admin approval
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "gcp" / "schema.sql"


def _read_schema() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def test_user_style_results_table_created():
    """user_style_results table must exist with idempotent CREATE TABLE IF NOT EXISTS."""
    sql = _read_schema()
    assert "CREATE TABLE IF NOT EXISTS user_style_results" in sql, \
        "missing CREATE TABLE IF NOT EXISTS user_style_results"


def test_user_style_results_primary_key():
    """user_style_results must have id BIGSERIAL PRIMARY KEY."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+user_style_results\s+\([^)]*id\s+BIGSERIAL\s+PRIMARY\s+KEY",
        sql_normalized
    ), "user_style_results must have id BIGSERIAL PRIMARY KEY"


def test_user_style_results_user_email_column():
    """user_style_results must have user_email TEXT NOT NULL."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+user_style_results.*user_email\s+TEXT\s+NOT\s+NULL",
        sql_normalized,
        re.DOTALL
    ), "user_style_results must have user_email TEXT NOT NULL"


def test_user_style_results_ticker_column():
    """user_style_results must have ticker VARCHAR(10) NOT NULL."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+user_style_results.*ticker\s+VARCHAR\(10\)\s+NOT\s+NULL",
        sql_normalized,
        re.DOTALL
    ), "user_style_results must have ticker VARCHAR(10) NOT NULL"


def test_user_style_results_profile_jsonb():
    """user_style_results must have profile JSONB NOT NULL for mined StyleProfile."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+user_style_results.*profile\s+JSONB\s+NOT\s+NULL",
        sql_normalized,
        re.DOTALL
    ), "user_style_results must have profile JSONB NOT NULL"


def test_user_style_results_trained_on_trades():
    """user_style_results must have trained_on_trades INTEGER NOT NULL."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+user_style_results.*trained_on_trades\s+INTEGER\s+NOT\s+NULL",
        sql_normalized,
        re.DOTALL
    ), "user_style_results must have trained_on_trades INTEGER NOT NULL"


def test_user_style_results_avg_expectancy_pct():
    """user_style_results must have avg_expectancy_pct DOUBLE PRECISION (nullable)."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+user_style_results.*avg_expectancy_pct\s+DOUBLE\s+PRECISION",
        sql_normalized,
        re.DOTALL
    ), "user_style_results must have avg_expectancy_pct DOUBLE PRECISION"


def test_user_style_results_avg_win_rate():
    """user_style_results must have avg_win_rate DOUBLE PRECISION (nullable)."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+user_style_results.*avg_win_rate\s+DOUBLE\s+PRECISION",
        sql_normalized,
        re.DOTALL
    ), "user_style_results must have avg_win_rate DOUBLE PRECISION"


def test_user_style_results_stability_score():
    """user_style_results must have stability_score DOUBLE PRECISION (nullable)."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+user_style_results.*stability_score\s+DOUBLE\s+PRECISION",
        sql_normalized,
        re.DOTALL
    ), "user_style_results must have stability_score DOUBLE PRECISION"


def test_user_style_results_created_at_default():
    """user_style_results must have created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+user_style_results.*created_at\s+TIMESTAMPTZ\s+NOT\s+NULL\s+DEFAULT\s+NOW\(\)",
        sql_normalized,
        re.DOTALL
    ), "user_style_results must have created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"


def test_user_style_results_index():
    """user_style_results must have index on (user_email, ticker, created_at DESC)."""
    sql = _read_schema()
    assert "idx_user_style_results_user" in sql, \
        "missing index idx_user_style_results_user"
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_user_style_results_user\s+ON\s+user_style_results\s+\(user_email,\s*ticker,\s*created_at\s+DESC\)",
        sql_normalized
    ), "index idx_user_style_results_user must be on (user_email, ticker, created_at DESC)"


def test_playbook_cards_staging_table_created():
    """playbook_cards_staging table must exist with idempotent CREATE TABLE IF NOT EXISTS."""
    sql = _read_schema()
    assert "CREATE TABLE IF NOT EXISTS playbook_cards_staging" in sql, \
        "missing CREATE TABLE IF NOT EXISTS playbook_cards_staging"


def test_playbook_cards_staging_primary_key():
    """playbook_cards_staging must have composite PRIMARY KEY (user_email, ticker, name)."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+playbook_cards_staging.*CONSTRAINT\s+pk_playbook_cards_staging\s+PRIMARY\s+KEY\s+\(user_email,\s*ticker,\s*name\)",
        sql_normalized,
        re.DOTALL
    ), "playbook_cards_staging must have composite PK: pk_playbook_cards_staging (user_email, ticker, name)"


def test_playbook_cards_staging_user_email_column():
    """playbook_cards_staging must have user_email TEXT NOT NULL."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+playbook_cards_staging.*user_email\s+TEXT\s+NOT\s+NULL",
        sql_normalized,
        re.DOTALL
    ), "playbook_cards_staging must have user_email TEXT NOT NULL"


def test_playbook_cards_staging_ticker_column():
    """playbook_cards_staging must have ticker VARCHAR(10) NOT NULL."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+playbook_cards_staging.*ticker\s+VARCHAR\(10\)\s+NOT\s+NULL",
        sql_normalized,
        re.DOTALL
    ), "playbook_cards_staging must have ticker VARCHAR(10) NOT NULL"


def test_playbook_cards_staging_name_column():
    """playbook_cards_staging must have name TEXT NOT NULL."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+playbook_cards_staging.*name\s+TEXT\s+NOT\s+NULL",
        sql_normalized,
        re.DOTALL
    ), "playbook_cards_staging must have name TEXT NOT NULL"


def test_playbook_cards_staging_direction_column():
    """playbook_cards_staging must have direction VARCHAR(8) NOT NULL."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+playbook_cards_staging.*direction\s+VARCHAR\(8\)\s+NOT\s+NULL",
        sql_normalized,
        re.DOTALL
    ), "playbook_cards_staging must have direction VARCHAR(8) NOT NULL"


def test_playbook_cards_staging_conditions_jsonb_default():
    """playbook_cards_staging must have conditions JSONB NOT NULL DEFAULT '[]'::jsonb."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+playbook_cards_staging.*conditions\s+JSONB\s+NOT\s+NULL\s+DEFAULT\s+'\[\]'::jsonb",
        sql_normalized,
        re.DOTALL
    ), "playbook_cards_staging must have conditions JSONB NOT NULL DEFAULT '[]'::jsonb"


def test_playbook_cards_staging_status_default():
    """playbook_cards_staging must have status VARCHAR(16) NOT NULL DEFAULT 'candidate'."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+playbook_cards_staging.*status\s+VARCHAR\(16\)\s+NOT\s+NULL\s+DEFAULT\s+'candidate'",
        sql_normalized,
        re.DOTALL
    ), "playbook_cards_staging must have status VARCHAR(16) NOT NULL DEFAULT 'candidate'"


def test_playbook_cards_staging_generated_at_default():
    """playbook_cards_staging must have generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()."""
    sql = _read_schema()
    sql_normalized = re.sub(r"\s+", " ", sql)
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+playbook_cards_staging.*generated_at\s+TIMESTAMPTZ\s+NOT\s+NULL\s+DEFAULT\s+NOW\(\)",
        sql_normalized,
        re.DOTALL
    ), "playbook_cards_staging must have generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
