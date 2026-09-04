#!/usr/bin/env python3
"""
Apply ``gcp/schema.sql`` to Cloud SQL.

The schema file is fully idempotent (every statement uses ``CREATE TABLE
IF NOT EXISTS`` / ``CREATE INDEX IF NOT EXISTS`` / ``ADD COLUMN IF NOT
EXISTS`` / ``CREATE OR REPLACE``), so running this is safe at any time
and the canonical way to roll forward schema changes.

Used as a one-shot Cloud Run Job (``apply-schema-migrations``) so the
codespace doesn't need direct Postgres connectivity.

Usage
-----
    python -m gcp.apply_schema
    python -m gcp.apply_schema --file gcp/schema.sql
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcp.database import execute_sql, is_cloud_sql_configured
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

DEFAULT_SCHEMA = Path(__file__).parent / "schema.sql"


# Marker comments recognized by split_statement_groups. Statements between a
# BEGIN/END pair execute in ONE transaction, so an interrupted apply commits
# either none of them or all of them. schema.sql uses this for the earnings
# mat-view section, whose DROP ... CASCADE + CREATE ... WITH NO DATA pairs
# would otherwise commit separately — an interruption between the committed
# DROP and its CREATE leaves the view ABSENT, a state the refresh job cannot
# repair (refresh_earnings_views._is_view_populated raises on a missing
# relation). Caught by Codex on PR #983.
ATOMIC_BEGIN = "-- ATOMIC-BEGIN"
ATOMIC_END = "-- ATOMIC-END"


def split_statement_groups(sql_text: str) -> list[list[str]]:
    """Split a schema file into execution units.

    Each unit is a list of statements: a singleton for a normal statement,
    or several statements between ``-- ATOMIC-BEGIN`` / ``-- ATOMIC-END``
    marker comments, which the executor runs in one transaction.

    Handles ``$$``-quoted PL/pgSQL bodies (used by trigger functions) by
    tracking whether the cursor is inside a dollar-quoted block before
    splitting on semicolons.

    Malformed markers raise ``ValueError`` (nested/unmatched/unterminated,
    empty group, or a marker in the middle of a statement) rather than being
    silently treated as comments — a dropped marker would silently lose the
    atomicity the schema author asked for (Rule 3.7).
    """
    groups: list[list[str]] = []
    group: Optional[list[str]] = None  # open ATOMIC group, else None
    buf: list[str] = []
    in_dollar = False

    for lineno, line in enumerate(sql_text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            # Token-boundary match: the marker is the whole comment or is
            # followed by whitespace (a label). Prose that merely mentions
            # "-- ATOMIC-BEGIN/END" must not parse as a marker.
            def _is(marker: str) -> bool:
                return stripped == marker or stripped.startswith(marker + " ")

            is_begin, is_end = _is(ATOMIC_BEGIN), _is(ATOMIC_END)
            is_marker = is_begin or is_end
            if is_marker and buf:
                raise ValueError(
                    f"line {lineno}: ATOMIC marker in the middle of a statement"
                )
            if is_marker:
                if is_begin:
                    if group is not None:
                        raise ValueError(f"line {lineno}: nested {ATOMIC_BEGIN}")
                    group = []
                else:
                    if group is None:
                        raise ValueError(
                            f"line {lineno}: {ATOMIC_END} without {ATOMIC_BEGIN}"
                        )
                    if not group:
                        raise ValueError(f"line {lineno}: empty ATOMIC group")
                    groups.append(group)
                    group = None
                continue
            # Preserve blank/comment lines inside the buffer for context but
            # they don't affect statement boundaries.
            if buf:
                buf.append(line)
            continue
        buf.append(line)

        # Toggle dollar-quoted state on each $$ occurrence.
        # (Same line can have an even number of toggles which net to 0.)
        toggles = line.count("$$")
        if toggles % 2 == 1:
            in_dollar = not in_dollar

        if not in_dollar and stripped.endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt:
                if group is not None:
                    group.append(stmt)
                else:
                    groups.append([stmt])
            buf = []

    if group is not None:
        raise ValueError(f"unterminated {ATOMIC_BEGIN} — missing {ATOMIC_END}")
    if buf:
        leftover = "\n".join(buf).strip()
        if leftover:
            groups.append([leftover])
    return groups


def split_statements(sql_text: str) -> list[str]:
    """Flat statement list — split_statement_groups without the grouping."""
    return [stmt for grp in split_statement_groups(sql_text) for stmt in grp]


def run_unit(unit: list[str]) -> None:
    """Execute one unit: a singleton via execute_sql (its own transaction,
    unchanged behavior), a multi-statement ATOMIC group in ONE transaction so
    an interruption or a failing statement rolls the whole group back.
    Raises on failure — the caller decides how loud to be."""
    if len(unit) == 1:
        execute_sql(unit[0])
        return
    import sqlalchemy  # noqa: PLC0415 — lazy, matches gcp.database convention

    from gcp.database import get_engine  # noqa: PLC0415

    engine = get_engine()
    with engine.begin() as conn:
        for stmt in unit:
            conn.execute(sqlalchemy.text(stmt))


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply schema.sql to Cloud SQL.")
    ap.add_argument("--file", default=str(DEFAULT_SCHEMA),
                    help="Path to schema SQL file (default: gcp/schema.sql)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and print statements but do not execute.")
    args = ap.parse_args()

    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured")
        return 2

    schema_path = Path(args.file)
    if not schema_path.exists():
        log.error("Schema file not found: %s", schema_path)
        return 2

    log.info("Loading schema from %s", schema_path)
    sql_text = schema_path.read_text()
    units = split_statement_groups(sql_text)
    n_statements = sum(len(u) for u in units)
    log.info("Parsed %d statements in %d execution units", n_statements, len(units))

    if args.dry_run:
        i = 0
        for unit in units:
            for stmt in unit:
                i += 1
                head = re.sub(r"\s+", " ", stmt)[:80]
                prefix = "[ATOMIC] " if len(unit) > 1 else ""
                log.info("  [%d] %s%s", i, prefix, head)
        return 0

    failed = 0
    for i, unit in enumerate(units, 1):
        head = re.sub(r"\s+", " ", unit[0])[:80]
        label = head if len(unit) == 1 else f"ATOMIC group of {len(unit)} ({head} ...)"
        try:
            run_unit(unit)
            log.info("  [%d/%d] OK  %s", i, len(units), label)
        except Exception as exc:
            failed += 1
            log.error("  [%d/%d] FAILED %s — %s", i, len(units), label, exc)

    if failed:
        log.error("Schema apply finished with %d failed units", failed)
        return 1
    log.info("Schema apply complete (%d statements in %d units).", n_statements, len(units))
    return 0


if __name__ == "__main__":
    sys.exit(main())
