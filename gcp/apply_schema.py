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


# ── Revision guard ─────────────────────────────────────────────────────────
# Cloud Build may start the build for a NEWER main push before a delayed
# build for the preceding push, so ordering job mutations by build start
# time (gcp/cloudbuild/wait_for_earlier_schema_builds.sh) is not enough on
# its own: the older build could still apply last and roll every CREATE OR
# REPLACE view/function back (Codex on #1022). The applier therefore records
# the source revision it applied and orders the incoming one against the
# newest successfully applied one:
#
#   1. ancestry first: the build passes `git rev-list` of its revision; if
#      the newest applied SHA is in it, this revision descends from it and
#      is newer whatever the clocks say;
#   2. otherwise committer time (main is squash-merged, GitHub stamps the
#      merge time);
#   3. an EQUAL committer time with a different SHA that ancestry cannot
#      order is refused. Equal seconds are real: measured 2026-09-07, main
#      had 38 adjacent commit pairs sharing a committer second (Codex on
#      #1022). The trigger checkout is a single-revision fetch, so the
#      build step deepens it before reading the ancestry; if that fails
#      the tie is refused rather than guessed.
REVISION_TABLE = "schema_apply_history"
_REVISION_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {REVISION_TABLE} (
    commit_sha   TEXT        NOT NULL,
    commit_time  BIGINT      NOT NULL,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (commit_sha, applied_at)
)"""


def classify_revision(newest_sha: str | None, newest_time: int | None,
                      commit_sha: str, commit_time: int,
                      ancestors: frozenset[str]) -> str:
    """Order ``commit_sha`` against the newest applied revision.

    Returns one of ``first`` (nothing applied yet), ``same``, ``descendant``
    (the newest applied SHA is an ancestor of this one, proven by the
    checkout), ``newer`` / ``older`` (by committer time, when ancestry cannot
    decide) or ``tie`` (equal committer time, different SHA, no ancestry
    proof). Only ``older`` and ``tie`` are refused.
    """
    if newest_sha is None:
        return "first"
    if newest_sha == commit_sha:
        return "same"
    if newest_sha in ancestors:
        return "descendant"
    assert newest_time is not None
    if commit_time > newest_time:
        return "newer"
    if commit_time < newest_time:
        return "older"
    return "tie"


_REFUSED = {"older", "tie"}


def guard_revision(engine, commit_sha: str, commit_time: int,
                   ancestors: frozenset[str] = frozenset()) -> tuple[bool, str | None]:
    """Return (ok, newest_applied_sha). ``ok`` is False when this revision is
    older than, or cannot be ordered against, the newest successfully applied
    one; the caller must then refuse to apply. The reason is logged here."""
    import sqlalchemy  # noqa: PLC0415

    with engine.begin() as conn:
        conn.execute(sqlalchemy.text(_REVISION_TABLE_SQL))
        row = conn.execute(sqlalchemy.text(
            f"SELECT commit_sha, commit_time FROM {REVISION_TABLE} "
            "ORDER BY commit_time DESC, applied_at DESC LIMIT 1"
        )).fetchone()
    if row is None:
        return True, None
    newest_sha, newest_time = row[0], int(row[1])
    verdict = classify_revision(newest_sha, newest_time, commit_sha, commit_time, ancestors)
    log.info("Revision %s (commit time %d) vs newest applied %s (commit time %d): %s",
             commit_sha, commit_time, newest_sha, newest_time, verdict)
    if verdict in _REFUSED:
        if verdict == "tie":
            log.error("Refusing to apply revision %s: it shares committer time %d with "
                      "the newest applied revision %s and the checkout's ancestry "
                      "(%d SHAs) does not contain it, so the order is unknown. Deepen "
                      "the checkout (git fetch --deepen) and re-run.",
                      commit_sha, commit_time, newest_sha, len(ancestors))
        else:
            log.error("Refusing to apply revision %s (commit time %d): a newer revision "
                      "%s (commit time %d) has already been applied. Out-of-order "
                      "applies roll CREATE OR REPLACE objects back.",
                      commit_sha, commit_time, newest_sha, newest_time)
        return False, newest_sha
    return True, newest_sha


def record_revision(engine, commit_sha: str, commit_time: int) -> None:
    import sqlalchemy  # noqa: PLC0415

    with engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                f"INSERT INTO {REVISION_TABLE} (commit_sha, commit_time) "
                "VALUES (:sha, :t)"
            ),
            {"sha": commit_sha, "t": int(commit_time)},
        )


# ── Materialized views ─────────────────────────────────────────────────────
# schema.sql recreates earnings_event_outcomes and earnings_ticker_lean
# WITH NO DATA on every apply (mat views cannot be CREATE OR REPLACE'd when
# their column set changes), and refresh-earnings-views repopulates them
# only weekly. Now that every staging deploy applies the schema, an
# unpopulated view would break the earnings endpoints until Sunday (Codex on
# #1022). So an apply is not complete until every unpopulated materialized
# view has been refreshed.
_UNPOPULATED_MATVIEWS_SQL = (
    "SELECT schemaname, matviewname FROM pg_matviews "
    "WHERE NOT ispopulated ORDER BY schemaname, matviewname"
)


def refresh_unpopulated_matviews(engine) -> list[str]:
    """Refresh every materialized view Postgres reports as unpopulated.
    Returns the qualified names refreshed. Raises on the first failure so
    the apply fails loud rather than leaving an empty view behind."""
    import sqlalchemy  # noqa: PLC0415

    with engine.begin() as conn:
        rows = conn.execute(sqlalchemy.text(_UNPOPULATED_MATVIEWS_SQL)).fetchall()
    names = [f'"{r[0]}"."{r[1]}"' for r in rows]
    for name in names:
        log.info("Refreshing unpopulated materialized view %s", name)
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text(f"REFRESH MATERIALIZED VIEW {name}"))
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply schema.sql to Cloud SQL.")
    ap.add_argument("--file", default=str(DEFAULT_SCHEMA),
                    help="Path to schema SQL file (default: gcp/schema.sql)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and print statements but do not execute.")
    ap.add_argument("--revision", default=None,
                    help="Source commit SHA being applied (Cloud Build passes it). "
                         "With --revision-time, refuses a revision older than the "
                         "newest successfully applied one and records this apply.")
    ap.add_argument("--revision-time", type=int, default=None,
                    help="Committer time (unix epoch) of --revision.")
    ap.add_argument("--revision-ancestors", default="",
                    help="Whitespace-separated `git rev-list` of --revision, as far "
                         "as the build checkout can see. Orders a revision whose "
                         "committer time equals the newest applied one.")
    args = ap.parse_args()
    if (args.revision is None) != (args.revision_time is None):
        ap.error("--revision and --revision-time must be given together")
    ancestors = frozenset(args.revision_ancestors.split())

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

    from gcp.database import get_engine  # noqa: PLC0415
    engine = get_engine()

    if args.revision is not None:
        ok, _newest = guard_revision(engine, args.revision, args.revision_time, ancestors)
        if not ok:
            return 3          # reason already logged by guard_revision

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

    refreshed = refresh_unpopulated_matviews(engine)
    if refreshed:
        log.info("Refreshed %d materialized view(s) left unpopulated by the apply: %s",
                 len(refreshed), ", ".join(refreshed))

    if args.revision is not None:
        record_revision(engine, args.revision, args.revision_time)
        log.info("Recorded applied revision %s (commit time %d)", args.revision, args.revision_time)

    log.info("Schema apply complete (%d statements in %d units).", n_statements, len(units))
    return 0


if __name__ == "__main__":
    sys.exit(main())
