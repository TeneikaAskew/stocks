"""Schema/seed smoke test for `exit_config_overrides` (PR-E1).

We don't have a Cloud SQL instance in unit tests, so we verify two
things by parsing the schema file directly:

  1. The CREATE TABLE statement defines the columns the resolver
     module (PR-E2) will read.
  2. The INSERT seed values match the audit recommendations in
     `docs/audit/2026-05-08/recommended_per_ticker_config.json` —
     the seed and the audit doc cannot drift silently.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "gcp" / "schema.sql"
AUDIT_JSON = REPO / "docs" / "audit" / "2026-05-08" / "recommended_per_ticker_config.json"


def _read_schema() -> str:
    return SCHEMA.read_text()


def test_table_definition_present():
    sql = _read_schema()
    assert "CREATE TABLE IF NOT EXISTS exit_config_overrides" in sql
    # Must mention every column the resolver module will read.
    for col in ("call_target", "put_target", "call_stop", "put_stop",
                "call_time_stop", "put_time_stop", "consecutive_periods",
                "disabled_conditions", "calibration_date", "ticker"):
        assert col in sql, f"missing {col} in exit_config_overrides DDL"


def test_primary_key_is_ticker_plus_date():
    sql = _read_schema()
    # Allow whitespace flex; the constraint must be (ticker, calibration_date)
    assert re.search(
        r"PRIMARY\s+KEY\s*\(\s*ticker\s*,\s*calibration_date\s*\)",
        sql,
    )


def test_recent_index_present():
    sql = _read_schema()
    assert "idx_exit_config_overrides_recent" in sql


def test_seed_inserts_three_tickers():
    sql = _read_schema()
    # The INSERT block exists
    assert "INSERT INTO exit_config_overrides" in sql
    assert "ON CONFLICT (ticker, calibration_date) DO NOTHING" in sql
    for tkr in ("'SPY'", "'IWM'", "'QQQ'"):
        assert tkr in sql, f"seed missing {tkr}"


def test_seed_values_match_audit_json():
    """The hardcoded seed in schema.sql must match the audit JSON."""
    sql = _read_schema()
    audit = json.loads(AUDIT_JSON.read_text())

    # Each ticker's call_target / put_target appear in the SQL
    # (the values are unique enough to grep without false-positives).
    for ticker in ("SPY", "IWM", "QQQ"):
        rec = audit[ticker]
        ct = f"{rec['call_target']:.5f}"  # e.g. "0.00301"
        # SQL strips trailing zeros, so check both with/without
        assert (str(rec['call_target']) in sql or
                ct.rstrip('0').rstrip('.') in sql), \
            f"{ticker} call_target {rec['call_target']} not found in schema seed"
        pt = f"{rec['put_target']:.5f}"
        assert (str(rec['put_target']) in sql or
                pt.rstrip('0').rstrip('.') in sql), \
            f"{ticker} put_target {rec['put_target']} not found in schema seed"
