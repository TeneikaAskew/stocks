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
import os
import re
import sys
import time
from contextlib import contextmanager
from typing import Optional
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


_DOLLAR_OPEN = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def _code_of(line: str, tag: Optional[str]) -> tuple[str, Optional[str]]:
    """Return the executable part of ``line`` and the dollar-quote state
    after it — the open delimiter (``$$``, ``$func$``), or None.

    The statement boundary is a ``;`` that ends the CODE, not the text: a
    line reading ``... DOUBLE PRECISION;    -- worst drawdown`` terminates
    a statement even though it ends with a comment. Testing the raw line
    missed those and glued the next statement onto the same unit, so two
    commands travelled as one and the applier's per-statement count, log
    and ordering all described something that never ran that way (Codex
    on #1022; gcp/schema.sql:898 is the live instance).

    Recognising ``--`` alone is not enough — it appears inside values and
    inside PL/pgSQL bodies — so the scan tracks single-quoted literals
    (with ``''`` escaping) and dollar-quoted bodies, and only treats ``--``
    as a comment outside both. Everything before the comment is returned
    verbatim, so the caller still stores the original line.

    The body delimiter is matched by TAG, not assumed to be ``$$``.
    ``$func$ ... $func$`` is as valid, and an author reaches for a tag
    exactly when the body itself contains ``$$``; counting ``$$`` alone
    left such a body unquoted, so a ``RETURN NEW;  -- done`` inside it read
    as a statement boundary and split the function into fragments. The
    one-command-per-unit invariant cannot see that — each fragment carries
    one terminator — so it has its own test. A tag may not start with a
    digit, which is what keeps ``$1`` a parameter placeholder.
    """
    out: list[str] = []
    i, n = 0, len(line)
    in_quote = False
    while i < n:
        ch = line[i]
        if tag is not None:
            if line.startswith(tag, i):        # only the matching tag closes
                out.append(tag)
                i += len(tag)
                tag = None
                continue
        elif in_quote:
            if ch == "'":
                if line[i + 1:i + 2] == "'":   # '' is an escaped quote
                    out.append("''")
                    i += 2
                    continue
                in_quote = False
        else:
            if ch == "$":
                m = _DOLLAR_OPEN.match(line, i)
                if m:
                    tag = m.group(0)
                    out.append(tag)
                    i = m.end()
                    continue
            if line[i:i + 2] == "--":
                break                          # rest of the line is a comment
            if ch == "'":
                in_quote = True
        out.append(ch)
        i += 1
    return "".join(out), tag


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
    dollar_tag: Optional[str] = None   # open body delimiter, else None

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

        # Advance the dollar-quote state across the line and take the part
        # that is code — a `$$` inside a literal does not open a body, and
        # a `;` before an inline comment still ends the statement.
        code, dollar_tag = _code_of(line, dollar_tag)

        if dollar_tag is None and code.rstrip().endswith(";"):
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
        # Populate what this group recreated BEFORE it commits. The earnings
        # group commits both views WITH NO DATA; a refresh after the loop
        # left the endpoints failing with an unpopulated-view error for the
        # length of the refresh, and forever if a later unit failed (Codex
        # on #1022). Inside the transaction, readers see the old view or the
        # new populated one, never an empty one (refresh-earnings-views
        # measures 23-46 s per run, so the lock is held under a minute).
        refreshed = _refresh_unpopulated_matviews_on(conn)
        if refreshed:
            log.info("Populated %d materialized view(s) inside the group's transaction: %s",
                     len(refreshed), ", ".join(refreshed))


# ── Revision guard ─────────────────────────────────────────────────────────
# Cloud Build may start the build for a NEWER main push before a delayed
# build for the preceding push, so ordering job mutations by build start
# time (gcp/cloudbuild/wait_for_earlier_schema_builds.sh) is not enough on
# its own: the older build could still apply last and roll every CREATE OR
# REPLACE view/function back (Codex on #1022). The applier therefore records
# the source revision it applied and orders the incoming one against the
# newest successfully applied one:
#
#   1. ancestry first, in both directions: the build passes `git rev-list`
#      of its revision, and each applied revision's rev-list is recorded.
#      If the incoming SHA is in the applied revision's recorded ancestry
#      it is older; if the applied SHA is in the incoming ancestry it is
#      newer; either holds whatever the clocks say. Both directions are
#      needed: a delayed build of ancestor A cannot see its descendant B
#      in its own rev-list, so only B's recorded ancestry can refuse A
#      (Codex on #1022, round 8);
#   2. otherwise committer time (main is squash-merged, GitHub stamps the
#      merge time);
#   3. an EQUAL committer time with a different SHA that ancestry cannot
#      order is refused. Equal seconds are real: measured 2026-09-07, main
#      had 38 adjacent commit pairs sharing a committer second (Codex on
#      #1022). The trigger checkout is a single-revision fetch, so the
#      build step deepens it before reading the ancestry; if that fails
#      the tie is refused rather than guessed.
#
# "Newest applied" is the LAST applied row (applied_at), not the highest
# committer time: under clock skew those differ, and the guard keeps the
# apply order monotonic, so the last applied row is the schema in force.
# Ancestry is recorded to the depth the build could see (100 commits);
# a relationship deeper than that falls back to committer time.
REVISION_TABLE = "schema_apply_history"
_REVISION_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {REVISION_TABLE} (
    commit_sha   TEXT        NOT NULL,
    commit_time  BIGINT      NOT NULL,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ancestors    TEXT        NOT NULL DEFAULT '',
    schema_sha256 TEXT       NOT NULL DEFAULT '',
    forced        BOOLEAN     NOT NULL DEFAULT FALSE,
    status        TEXT        NOT NULL DEFAULT 'ok',
    PRIMARY KEY (commit_sha, applied_at)
)"""
# Space-separated `git rev-list` of the applied revision, and the SHA-256 of
# the schema.sql text that was applied (also declared in schema.sql; the
# guard runs before the apply, so it creates all of them itself).
_REVISION_ANCESTORS_SQL = (
    f"ALTER TABLE {REVISION_TABLE} ADD COLUMN IF NOT EXISTS ancestors TEXT NOT NULL DEFAULT ''"
)
_REVISION_DIGEST_SQL = (
    f"ALTER TABLE {REVISION_TABLE} ADD COLUMN IF NOT EXISTS schema_sha256 TEXT NOT NULL DEFAULT ''"
)
# forced: the operator bypassed the ordering check (--force-revision), so
# the row is an operator's statement, not a build's. status: 'ok' when every
# unit ran, 'partial' when some failed after others committed (units outside
# ATOMIC groups commit on their own), so the row still orders later
# revisions but its digest is never one an apply can skip on.
_REVISION_FORCED_SQL = (
    f"ALTER TABLE {REVISION_TABLE} ADD COLUMN IF NOT EXISTS forced BOOLEAN NOT NULL DEFAULT FALSE"
)
_REVISION_STATUS_SQL = (
    f"ALTER TABLE {REVISION_TABLE} ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ok'"
)


def schema_digest(sql_text: str) -> str:
    """SHA-256 of the schema.sql text, recorded with each applied revision.

    Every staging deploy applies the schema (SCHEMA BEFORE CODE), and 15 of
    the 19 schema pushes in the 30 days to 2026-09-07 also fired the staging
    trigger, so the same content was applied twice back to back; 48 code-only
    pushes in the same window applied an unchanged schema.sql. Each apply
    recreates the two earnings materialized views and holds their ACCESS
    EXCLUSIVE lock for the 22-46 s refresh. When the digest of this file
    equals the newest applied revision's, there is nothing to apply and
    main() records the revision without running a unit (internal review of
    #1022, capacity round).
    """
    import hashlib  # noqa: PLC0415
    return hashlib.sha256(sql_text.encode("utf-8")).hexdigest()


def classify_revision(newest_sha: str | None, newest_time: int | None,
                      newest_ancestors: frozenset[str],
                      commit_sha: str, commit_time: int,
                      ancestors: frozenset[str]) -> str:
    """Order ``commit_sha`` against the newest (last) applied revision.

    Returns one of ``first`` (nothing applied yet), ``same``, ``ancestor``
    (the applied revision recorded this SHA in its ancestry), ``descendant``
    (the applied SHA is in this revision's ancestry), ``newer`` / ``older``
    (by committer time, when ancestry cannot decide) or ``tie`` (equal
    committer time, different SHA, no ancestry proof). ``ancestor``,
    ``older`` and ``tie`` are refused.
    """
    if newest_sha is None:
        return "first"
    if newest_sha == commit_sha:
        return "same"
    if commit_sha in newest_ancestors:
        return "ancestor"
    if newest_sha in ancestors:
        return "descendant"
    assert newest_time is not None
    if commit_time > newest_time:
        return "newer"
    if commit_time < newest_time:
        return "older"
    return "tie"


_REFUSED = {"ancestor", "older", "tie"}


def guard_revision(engine, commit_sha: str, commit_time: int,
                   ancestors: frozenset[str] = frozenset(), force: bool = False,
                   ) -> tuple[bool, str | None, str | None]:
    """Return (ok, newest_applied_sha, in_force_schema_digest). ``ok`` is
    False when this revision is older than, or cannot be ordered against,
    the newest applied one; the caller must then refuse to apply. The
    reason is logged here. The digest is the newest row's when that row
    applied fully (status 'ok'), else '' so nothing can skip on it; it lets
    main() skip an apply whose schema.sql text is already in force.

    ``force`` is the operator override (--force-revision): the verdict is
    still computed and logged, at ERROR, but a refused verdict no longer
    stops the apply. For a manual apply from a branch, whose HEAD the
    ordering rule (written for concurrent builds of main) cannot place.
    """
    import sqlalchemy  # noqa: PLC0415

    with engine.begin() as conn:
        conn.execute(sqlalchemy.text(_REVISION_TABLE_SQL))
        conn.execute(sqlalchemy.text(_REVISION_ANCESTORS_SQL))
        conn.execute(sqlalchemy.text(_REVISION_DIGEST_SQL))
        conn.execute(sqlalchemy.text(_REVISION_FORCED_SQL))
        conn.execute(sqlalchemy.text(_REVISION_STATUS_SQL))
        row = conn.execute(sqlalchemy.text(
            f"SELECT commit_sha, commit_time, ancestors, schema_sha256, status, forced "
            f"FROM {REVISION_TABLE} ORDER BY applied_at DESC LIMIT 1"
        )).fetchone()
    if row is None:
        return True, None, None
    newest_sha, newest_time = row[0], int(row[1])
    newest_ancestors = frozenset((row[2] or "").split())
    newest_digest = (row[3] or "") if (row[4] or "ok") == "ok" else ""
    verdict = classify_revision(newest_sha, newest_time, newest_ancestors,
                                commit_sha, commit_time, ancestors)
    log.info("Revision %s (commit time %d) vs newest applied %s (commit time %d): %s",
             commit_sha, commit_time, newest_sha, newest_time, verdict)
    if verdict in _REFUSED:
        if verdict == "tie":
            log.error("Refusing to apply revision %s: it shares committer time %d with "
                      "the newest applied revision %s and the checkout's ancestry "
                      "(%d SHAs) does not contain it, so the order is unknown. Deepen "
                      "the checkout (git fetch --deepen) and re-run.",
                      commit_sha, commit_time, newest_sha, len(ancestors))
        elif verdict == "ancestor":
            log.error("Refusing to apply revision %s (commit time %d): the newest applied "
                      "revision %s (commit time %d) recorded it as an ancestor%s. "
                      "Out-of-order applies roll CREATE OR REPLACE objects back.",
                      commit_sha, commit_time, newest_sha, newest_time,
                      " although its committer time is higher, so the clocks were skewed"
                      if commit_time > newest_time else "")
        else:
            log.error("Refusing to apply revision %s (commit time %d): a newer revision "
                      "%s (commit time %d) has already been applied. Out-of-order "
                      "applies roll CREATE OR REPLACE objects back.",
                      commit_sha, commit_time, newest_sha, newest_time)
        if force:
            log.error("FORCED: applying revision %s over that refusal because --force-revision "
                      "was passed; the row will be recorded as forced.", commit_sha)
            return True, newest_sha, newest_digest
        return False, newest_sha, newest_digest
    return True, newest_sha, newest_digest


def record_revision(engine, commit_sha: str, commit_time: int,
                    ancestors: frozenset[str] = frozenset(),
                    schema_digest: str = "", forced: bool = False,
                    status: str = "ok") -> None:
    """Record this apply. A re-apply of the SHA that is already the last
    applied row (both triggers apply the same push) merges its ancestry
    into that row instead of inserting a new one: the later build's
    rev-list may be shallow if its deepen failed, and a shallow last row
    would hide the ancestry the first build recorded from the guard
    (Codex on #1022)."""
    import sqlalchemy  # noqa: PLC0415

    with engine.begin() as conn:
        last = conn.execute(sqlalchemy.text(
            f"SELECT commit_sha, applied_at, ancestors FROM {REVISION_TABLE} "
            "ORDER BY applied_at DESC LIMIT 1"
        )).fetchone()
        # The same SHA merges whatever the incoming status: the applier now
        # writes a 'partial' row before the first unit and promotes it after
        # (Codex on #1022), so this has to update rather than insert a second
        # row. Only 'ok' promotes; a later 'partial' leaves an 'ok' alone.
        if last is not None and last[0] == commit_sha:
            merged = frozenset((last[2] or "").split()) | ancestors
            conn.execute(
                sqlalchemy.text(
                    f"UPDATE {REVISION_TABLE} SET ancestors = :anc, schema_sha256 = :dg, "
                    "status = CASE WHEN :status = 'ok' THEN 'ok' ELSE status END, "
                    "forced = (forced OR :forced) "
                    "WHERE commit_sha = :sha AND applied_at = :at"
                ),
                # forced is OR'd: once an operator bypassed the guard for this
                # row, a later plain re-apply of the same SHA must not erase
                # that evidence (Codex on #1022).
                {"anc": " ".join(sorted(merged)), "dg": schema_digest,
                 "status": status, "forced": bool(forced),
                 "sha": commit_sha, "at": last[1]},
            )
            log.info("Revision %s was already the last applied row; merged its ancestry "
                     "(%d SHAs)", commit_sha, len(merged))
            return
        conn.execute(
            sqlalchemy.text(
                f"INSERT INTO {REVISION_TABLE} "
                "(commit_sha, commit_time, ancestors, schema_sha256, forced, status) "
                "VALUES (:sha, :t, :anc, :dg, :forced, :status)"
            ),
            {"sha": commit_sha, "t": int(commit_time), "anc": " ".join(sorted(ancestors)),
             "dg": schema_digest, "forced": bool(forced), "status": status},
        )


# ── Materialized views ─────────────────────────────────────────────────────
# schema.sql recreates earnings_event_outcomes and earnings_ticker_lean
# WITH NO DATA on every apply (mat views cannot be CREATE OR REPLACE'd when
# their column set changes), and refresh-earnings-views repopulates them
# only weekly. Now that every staging deploy applies the schema, an
# unpopulated view would break the earnings endpoints until Sunday (Codex on
# #1022). So the ATOMIC group that recreates them populates them inside its
# own transaction (run_unit), and an end-of-run sweep refreshes anything
# still unpopulated, whether or not every unit succeeded.
_UNPOPULATED_MATVIEWS_SQL = (
    "SELECT schemaname, matviewname FROM pg_matviews "
    "WHERE NOT ispopulated ORDER BY schemaname, matviewname"
)


def _refresh_unpopulated_matviews_on(conn) -> list[str]:
    """Refresh, on ``conn`` (inside whatever transaction it is in), every
    materialized view Postgres reports as unpopulated. Returns the qualified
    names refreshed. Raises on the first failure so the caller's transaction
    rolls back rather than committing an empty view."""
    import sqlalchemy  # noqa: PLC0415

    rows = conn.execute(sqlalchemy.text(_UNPOPULATED_MATVIEWS_SQL)).fetchall()
    names = [f'"{r[0]}"."{r[1]}"' for r in rows]
    for name in names:
        log.info("Refreshing unpopulated materialized view %s", name)
        conn.execute(sqlalchemy.text(f"REFRESH MATERIALIZED VIEW {name}"))
    return names


def refresh_unpopulated_matviews(engine) -> list[str]:
    """End-of-run sweep: one transaction refreshing every view still
    unpopulated. Raises on the first failure so the apply fails loud rather
    than leaving an empty view behind."""
    with engine.begin() as conn:
        return _refresh_unpopulated_matviews_on(conn)


# ── Cross-applier mutual exclusion ─────────────────────────────────────────
# Ordering appliers by build start time is best-effort, and it cannot see an
# applier that is not a Cloud Build at all: the deploy-staging workflow runs
# `python -m gcp.apply_schema` on a GitHub runner, so a build started while
# that runner is mid-apply does not wait for it. Both then pass the revision
# guard before either records, and whichever finishes LAST wins — rolling
# back every CREATE OR REPLACE the other had just applied, and leaving a
# history row describing a schema nobody is running (Codex on #1022).
#
# A Postgres advisory lock is authoritative where the tag scan is advisory:
# every applier reaches the same database, whatever started it. Held across
# guard -> apply -> record, so the second applier reads a RECORDED revision
# instead of a stale one and its guard then decides correctly (skip an
# unchanged digest, refuse an older revision).
#
# Session-scoped, on a connection of its own: the apply runs each unit on
# its own pooled connection, so the lock cannot live on any of those.
_APPLY_LOCK_KEY = 0x5C4E3A01          # arbitrary but fixed
_LOCK_WAIT_SECONDS = int(os.environ.get("SCHEMA_APPLY_LOCK_WAIT", "900"))
_LOCK_POLL_SECONDS = 5


@contextmanager
def schema_apply_lock(engine, wait_seconds: Optional[int] = None):
    """Hold the schema-apply lock for the block, or raise TimeoutError.

    Bounded rather than indefinite: the job's task-timeout is 1800 s and a
    full apply measures 75 s, so 900 s covers a queue of appliers many times
    over while still failing loudly, and visibly in the build log, well
    before the task is killed with no explanation.
    """
    import sqlalchemy  # noqa: PLC0415

    # Read at call time rather than bound as a default: the budget comes
    # from an env var, and a default argument would freeze whatever the
    # value was at import.
    if wait_seconds is None:
        wait_seconds = _LOCK_WAIT_SECONDS
    conn = engine.connect()
    held = False
    try:
        deadline = time.monotonic() + wait_seconds
        announced = False
        while True:
            if conn.execute(sqlalchemy.text("SELECT pg_try_advisory_lock(:k)"),
                            {"k": _APPLY_LOCK_KEY}).scalar():
                held = True
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"another schema apply has held the lock for more than "
                    f"{wait_seconds}s; refusing to apply concurrently")
            if not announced:
                log.info("another schema apply holds the lock; waiting up to %ds",
                         wait_seconds)
                announced = True
            time.sleep(_LOCK_POLL_SECONDS)
        if announced:
            log.info("schema-apply lock acquired after waiting")
        yield
    finally:
        if held:
            try:
                conn.execute(sqlalchemy.text("SELECT pg_advisory_unlock(:k)"),
                             {"k": _APPLY_LOCK_KEY})
            except Exception:
                # cleanup — the original error has already propagated, and
                # closing the session releases the lock regardless.
                log.warning("could not release the schema-apply lock explicitly")
        conn.close()


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
    ap.add_argument("--force-revision", action="store_true",
                    help="Apply even when the revision guard would refuse this revision "
                         "as older than, or unorderable against, the newest applied one. "
                         "Logged at ERROR and recorded as forced. For an operator apply "
                         "from a branch; never for a trigger build.")
    ap.add_argument("--reapply-unchanged", action="store_true",
                    help="Run every unit even when this schema.sql is byte-identical "
                         "to the newest applied revision's (by default such an apply "
                         "is skipped and only recorded). For recreating an object "
                         "that was dropped by hand.")
    args = ap.parse_args()
    if (args.revision is None) != (args.revision_time is None):
        ap.error("--revision and --revision-time must be given together")
    ancestors = frozenset(args.revision_ancestors.split())

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

    # Credentials are checked here, not before the parse: --dry-run exists
    # to validate a schema edit locally, where no Cloud SQL is configured,
    # and checking first made the flag unusable for its only purpose
    # (Codex on #1022).
    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured")
        return 2

    from gcp.database import get_engine  # noqa: PLC0415
    engine = get_engine()

    # Guard, apply and record are ONE critical section: two appliers that
    # each read "nothing newer" before either records will both apply, and
    # whichever finishes last overwrites the other. See schema_apply_lock.
    try:
        _lock = schema_apply_lock(engine)
        _lock.__enter__()
    except TimeoutError as exc:
        log.error("%s", exc)
        return 4
    try:

        digest = schema_digest(sql_text)
        if args.revision is not None:
            ok, newest, newest_digest = guard_revision(engine, args.revision,
                                                       args.revision_time, ancestors,
                                                       force=args.force_revision)
            if not ok:
                return 3          # reason already logged by guard_revision
            if newest_digest == digest and not args.reapply_unchanged:
                # Nothing to apply: the text in force is this text. Still sweep
                # the materialized views (one probe) so a view left unpopulated
                # by anything else is repopulated, then record the revision so
                # the guard's ancestry advances with main.
                log.info("schema.sql at revision %s is unchanged from the newest applied "
                         "revision %s (sha256 %s); skipping the %d units. Pass "
                         "--reapply-unchanged to run them anyway.",
                         args.revision, newest, digest, len(units))
                try:
                    refreshed = refresh_unpopulated_matviews(engine)
                except Exception as exc:
                    log.error("  materialized-view sweep FAILED — %s", exc)
                    return 1
                if refreshed:
                    log.info("Refreshed %d materialized view(s) found unpopulated: %s",
                             len(refreshed), ", ".join(refreshed))
                record_revision(engine, args.revision, args.revision_time, ancestors, digest,
                                forced=args.force_revision)
                log.info("Recorded revision %s (commit time %d) as in force",
                         args.revision, args.revision_time)
                return 0

        # Recorded BEFORE the first unit commits, not after the loop. A
        # Cloud Run task timeout, an OOM or a cancellation never reaches
        # the `if failed` branch below, and singleton units commit one at
        # a time, so a killed apply left the database holding part of this
        # revision while schema_apply_history still named an older one as
        # in force — and a delayed build of an intermediate commit then
        # passed the guard and rolled the updated views back (Codex on
        # #1022). With the row written first, the incoming revision is the
        # newest for the whole window in which that can happen; a complete
        # apply promotes it to 'ok' at the end.
        if args.revision is not None:
            record_revision(engine, args.revision, args.revision_time, ancestors,
                            digest, forced=args.force_revision, status="partial")
            log.info("Recorded revision %s as in-flight (partial) before applying",
                     args.revision)

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

        # The sweep runs whether or not every unit succeeded: a failed unit
        # after the views must not leave them empty until the weekly job.
        try:
            refreshed = refresh_unpopulated_matviews(engine)
        except Exception as exc:
            failed += 1
            log.error("  materialized-view sweep FAILED — %s", exc)
        else:
            if refreshed:
                log.info("Refreshed %d materialized view(s) still unpopulated after the apply: %s",
                         len(refreshed), ", ".join(refreshed))

        if failed:
            log.error("Schema apply finished with %d failed units", failed)
            if args.revision is not None:
                # The units that succeeded are committed, so the schema is
                # partly this revision's. The row is already there from the
                # pre-record; this keeps it 'partial' (record_revision never
                # downgrades an 'ok') so the digest never matches a later
                # apply's and a delayed older build stays refused.
                record_revision(engine, args.revision, args.revision_time, ancestors, digest,
                                forced=args.force_revision, status="partial")
                log.error("Recorded revision %s as PARTIAL (%d failed units); the next apply "
                          "runs every unit again", args.revision, failed)
            return 1

        if args.revision is not None:
            record_revision(engine, args.revision, args.revision_time, ancestors, digest,
                            forced=args.force_revision)
            log.info("Recorded applied revision %s (commit time %d, schema sha256 %s)",
                     args.revision, args.revision_time, digest)

    finally:
        _lock.__exit__(None, None, None)

    log.info("Schema apply complete (%d statements in %d units).", n_statements, len(units))
    return 0


if __name__ == "__main__":
    sys.exit(main())
