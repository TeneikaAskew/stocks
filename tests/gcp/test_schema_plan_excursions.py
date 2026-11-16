"""FEAT-STRAT-001 target hit rates, done_when 'Table': gcp/schema.sql creates
plan_excursions idempotently, with Design 2's columns, key and checks
(docs/superpowers/specs/2026-11-16-feat-strat-001-target-hit-rates.md)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SCHEMA = Path(__file__).resolve().parents[2] / "gcp" / "schema.sql"


def _table_body(sql: str, table: str) -> str:
    m = re.search(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table}\s*\((.*?)\);", sql, re.DOTALL)
    assert m, f"table {table} not found in schema"
    return re.sub(r"\s+", " ", m.group(1))


@pytest.fixture(scope="module")
def body() -> str:
    return _table_body(SCHEMA.read_text(encoding="utf-8"), "plan_excursions")


def test_the_table_is_created_if_not_exists():
    sql = SCHEMA.read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE IF NOT EXISTS plan_excursions") == 1
    assert "CREATE TABLE plan_excursions" not in sql


@pytest.mark.parametrize("column, decl", [
    ("ticker", "VARCHAR(10) NOT NULL"),
    ("session_date", "DATE NOT NULL"),
    ("rule_version", "VARCHAR(40) NOT NULL"),
    ("side", "VARCHAR(5) NOT NULL CHECK (side IN ('calls', 'puts'))"),
    ("trigger_price", "DOUBLE PRECISION NOT NULL"),
    ("stop_price", "DOUBLE PRECISION NOT NULL"),
    ("fill_price", "DOUBLE PRECISION NOT NULL"),
    ("fill_ts", "TIMESTAMPTZ NOT NULL"),
    ("stop_ts", "TIMESTAMPTZ,"),
    ("excursion_r", "DOUBLE PRECISION,"),
    ("excursion_held5_r", "DOUBLE PRECISION,"),
    ("source", "VARCHAR(10) NOT NULL CHECK (source IN ('resolver', 'history'))"),
    ("resolver_version", "VARCHAR(40) NOT NULL"),
    ("written_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
])
def test_every_column_with_its_type_and_nullability(body, column, decl):
    assert f" {column} {decl}" in f" {body}"


def test_fourteen_columns_and_the_key(body):
    cols = re.findall(r"(?:^|, )([a-z_][a-z0-9_]*) (?:VARCHAR|DATE|DOUBLE|TIMESTAMPTZ)", body.strip())
    assert cols == ["ticker", "session_date", "rule_version", "side", "trigger_price",
                    "stop_price", "fill_price", "fill_ts", "stop_ts", "excursion_r",
                    "excursion_held5_r", "source", "resolver_version", "written_at"]
    assert body.strip().endswith("PRIMARY KEY (ticker, session_date, rule_version)")
