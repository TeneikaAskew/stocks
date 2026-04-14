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


def split_statements(sql_text: str) -> list[str]:
    """Split a schema file into individual statements.

    Handles ``$$``-quoted PL/pgSQL bodies (used by trigger functions) by
    tracking whether the cursor is inside a dollar-quoted block before
    splitting on semicolons.
    """
    statements: list[str] = []
    buf: list[str] = []
    in_dollar = False

    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
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
                statements.append(stmt)
            buf = []

    if buf:
        leftover = "\n".join(buf).strip()
        if leftover:
            statements.append(leftover)
    return statements


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
    statements = split_statements(sql_text)
    log.info("Parsed %d statements", len(statements))

    if args.dry_run:
        for i, stmt in enumerate(statements, 1):
            head = re.sub(r"\s+", " ", stmt)[:80]
            log.info("  [%d] %s", i, head)
        return 0

    failed = 0
    for i, stmt in enumerate(statements, 1):
        head = re.sub(r"\s+", " ", stmt)[:80]
        try:
            execute_sql(stmt)
            log.info("  [%d/%d] OK  %s", i, len(statements), head)
        except Exception as exc:
            failed += 1
            log.error("  [%d/%d] FAILED %s — %s", i, len(statements), head, exc)

    if failed:
        log.error("Schema apply finished with %d failures", failed)
        return 1
    log.info("Schema apply complete (%d statements).", len(statements))
    return 0


if __name__ == "__main__":
    sys.exit(main())
