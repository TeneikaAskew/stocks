#!/usr/bin/env python3
"""Run SQL via Cloud SQL connector and emit phone-friendly artifacts.

Invoked from .github/workflows/db-query.yml. Reads SQL from --sql (string,
multi-statement OK separated by ;) or --sql-file (path; sent as ONE statement),
runs each statement in its own transaction with rollback by default
(use --commit to persist), and writes:

    <out>/results.json              structured per-statement results
    <out>/result_NNN.csv            CSV per statement that returned rows
    <out>/summary.md                full markdown summary
    <out>/summary_for_comment.md    same, hard-truncated to 60 KB for issue comment

Exit codes:
    0  every statement either succeeded or failed with a USER error (syntax,
       constraint, statement_timeout). Run is reportable, not a system failure.
    1  a SYSTEM error occurred (auth, connection lost, OOM). Trips the
       db-query workflow's handle-failure job.
    2  invalid invocation (missing/conflicting args).

See docs/incidents/ and CLAUDE.md `## Database access` for usage from sessions.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import sqlparse
# Lift sqlparse's default 10k-token grouping limit so multi-row INSERTs
# (e.g. yfinance-backed VIX backfill, 8500+ rows ≈ 130k tokens) don't
# blow up in clean_for_wrap. Affects parsing only — the resulting SQL
# is still sent verbatim to Postgres. Added 2026-05-23.
import sqlparse.engine.grouping as _sqlparse_grouping
_sqlparse_grouping.MAX_GROUPING_TOKENS = 5_000_000
from sqlalchemy import text
from sqlalchemy.exc import (
    DataError,
    IntegrityError,
    OperationalError,
    ProgrammingError,
    SQLAlchemyError,
)

# Make `gcp.database` importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gcp.database import get_engine  # noqa: E402

ROW_CAP = 50_000           # per-statement row cap; we fetch ROW_CAP+1 to detect truncation
SUMMARY_ROWS = 50          # rows shown in the markdown preview
COMMENT_BYTE_LIMIT = 60_000  # GH issue comment hard limit ~65 KB; leave 5 KB headroom

USER_ERROR_SQLSTATE_CLASSES = ('22', '23', '25', '42')
USER_ERROR_SQLSTATES = ('57014',)              # statement_timeout
SYSTEM_ERROR_SQLSTATE_CLASSES = ('08',)        # connection exception


# ─────────────────────── error classification ───────────────────────

def get_sqlstate(exc: BaseException) -> str:
    """Best-effort SQLSTATE extraction from a pg8000/SQLAlchemy error."""
    orig = getattr(exc, 'orig', exc)
    args = getattr(orig, 'args', None)
    if args and isinstance(args[0], dict):
        return args[0].get('C', '') or ''
    m = re.search(r'sqlstate\s+([0-9A-Z]{5})', str(orig), re.IGNORECASE)
    return m.group(1) if m else ''


def get_error_message(exc: BaseException) -> str:
    """Pull the human-readable message from a pg8000/SQLAlchemy error.

    pg8000 wraps Postgres errors as ProgrammingError(args=({'S':..,'C':..,
    'M':<message>, ...},)) — str() on those renders the whole dict, which
    is unreadable in summaries. Pull the M field directly when available;
    fall back to str() otherwise.
    """
    orig = getattr(exc, 'orig', exc)
    args = getattr(orig, 'args', None)
    if args and isinstance(args[0], dict):
        m = args[0].get('M')
        if m:
            return m
    msg = str(orig).strip()
    if msg:
        return msg
    msg = str(exc).strip()
    if msg:
        return msg
    return exc.__class__.__name__


def classify_error(exc: BaseException) -> str:
    """Return 'user' for SQL/data errors, 'system' for infra errors."""
    sqlstate = get_sqlstate(exc)
    if sqlstate:
        cls = sqlstate[:2]
        if cls in USER_ERROR_SQLSTATE_CLASSES or sqlstate in USER_ERROR_SQLSTATES:
            return 'user'
        if cls in SYSTEM_ERROR_SQLSTATE_CLASSES:
            return 'system'
    if isinstance(exc, (ProgrammingError, DataError, IntegrityError)):
        return 'user'
    if isinstance(exc, OperationalError):
        return 'system'
    return 'system'


# ─────────────────────── statement parsing ───────────────────────

def clean_for_wrap(stmt: str) -> str:
    """Strip comments, trailing semicolons, and trailing whitespace."""
    cleaned = sqlparse.format(stmt, strip_comments=True)
    return cleaned.rstrip().rstrip(';').rstrip()


def can_wrap_for_limit(stmt: str) -> bool:
    """True if stmt is a single SELECT we can safely wrap as `(<stmt>) LIMIT N`.

    Eligibility (all must hold):
      - sqlparse types it as SELECT
      - Single statement only
      - No FOR UPDATE / FOR SHARE (locking semantics break in subquery)
      - No SELECT INTO (creates a table; can't subquery-wrap)
      - Non-empty after stripping comments and trailing semicolons

    Conservative on edge cases: false negatives (won't wrap when we could)
    just mean fallback to client_fetchmany; false positives (wrapping when
    we shouldn't) would break the query. Bias toward not wrapping.
    """
    parsed = sqlparse.parse(stmt)
    if len(parsed) != 1:
        return False
    p = parsed[0]
    if (p.get_type() or '').upper() != 'SELECT':
        return False
    # Normalize whitespace so multi-space sequences don't hide the keywords.
    # Comment stripping is best-effort; if a comment contains "FOR UPDATE"
    # we'd reject the wrap unnecessarily — fine, fallback path still works.
    no_comments = sqlparse.format(stmt, strip_comments=True)
    normalized = re.sub(r'\s+', ' ', no_comments).upper()
    if re.search(r'\bFOR\s+(NO\s+KEY\s+)?UPDATE\b', normalized):
        return False
    if re.search(r'\bFOR\s+(KEY\s+)?SHARE\b', normalized):
        return False
    if re.search(r'\bINTO\b', normalized):
        return False
    return bool(clean_for_wrap(stmt))


# ─────────────────────── value coercion ───────────────────────

def serialize_value(v: Any) -> Any:
    """JSON/CSV-safe value coercion. Datetimes/Decimals serialize via default=str."""
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray, memoryview)):
        try:
            return bytes(v).decode('utf-8', errors='replace')
        except Exception:
            return repr(v)
    return v


# ─────────────────────── execution ───────────────────────

def execute_statement(conn, stmt: str, commit: bool, timeout_seconds: int) -> dict:
    """Run one statement in its own transaction. Returns a structured result."""
    start = time.time()
    out: dict[str, Any] = {
        'sql': stmt,
        'status': 'ok',
        'mode': None,
        'columns': [],
        'rows': [],
        'row_count': 0,
        'truncated': False,
        'duration_ms': 0,
        'error': None,
        'error_class': None,
        'sqlstate': None,
        'row_cap_strategy': 'none',
    }

    cleaned = clean_for_wrap(stmt)
    if not cleaned:
        out['status'] = 'user_error'
        out['error'] = 'empty statement'
        out['error_class'] = 'user'
        out['mode'] = 'rolled_back'
        out['duration_ms'] = int((time.time() - start) * 1000)
        return out

    wrappable = can_wrap_for_limit(stmt)

    tx = conn.begin()
    try:
        timeout_ms = max(1, int(timeout_seconds)) * 1000
        conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))

        if wrappable:
            # Path A: server-side LIMIT via subquery wrap. Postgres caps the
            # result at ROW_CAP+1 before pg8000 buffers anything client-side.
            wrapped = f"SELECT * FROM ({cleaned}) _claude_q LIMIT {ROW_CAP + 1}"
            result = conn.execute(text(wrapped))
            out['row_cap_strategy'] = 'server_limit'
        else:
            # Path B: try a server-side cursor inside a SAVEPOINT so DECLARE
            # CURSOR failures (utility statements, certain DDL, write-only
            # statements) don't poison the outer transaction. Cursor caps via
            # FETCH FORWARD N — server-side, like Path A. Fall back to plain
            # execute (Path C) only if cursor isn't supported for this query.
            sp = conn.begin_nested()
            try:
                conn.execute(text(f"DECLARE _claude_cur NO SCROLL CURSOR FOR {cleaned}"))
                result = conn.execute(text(f"FETCH FORWARD {ROW_CAP + 1} FROM _claude_cur"))
                sp.commit()
                out['row_cap_strategy'] = 'server_cursor'
            except SQLAlchemyError:
                sp.rollback()
                # Path C: last-resort plain execute. pg8000 buffers the full
                # result client-side, so very large result sets in this path
                # (e.g. a SELECT that DECLARE CURSOR rejected and returns
                # millions of rows) can OOM the runner before fetchmany caps.
                # statement_timeout bounds wall-time, not memory. Reached
                # only for statement types Postgres won't cursor.
                result = conn.execute(text(cleaned))
                out['row_cap_strategy'] = 'client_fetchmany'

        if result.returns_rows:
            out['columns'] = list(result.keys())
            fetched = result.fetchmany(ROW_CAP + 1)
            out['truncated'] = len(fetched) > ROW_CAP
            rows = fetched[:ROW_CAP]
            out['rows'] = [[serialize_value(v) for v in r] for r in rows]
            out['row_count'] = len(rows)
        else:
            rc = result.rowcount
            out['row_count'] = rc if (rc is not None and rc >= 0) else 0
            # No rows = strategy doesn't apply, even if we tried to cursor.
            out['row_cap_strategy'] = 'none'

        if commit:
            tx.commit()
            out['mode'] = 'committed'
        else:
            tx.rollback()
            out['mode'] = 'rolled_back'

    except SQLAlchemyError as e:
        try:
            tx.rollback()
        except Exception:
            pass
        cls = classify_error(e)
        out['status'] = 'user_error' if cls == 'user' else 'system_error'
        out['error_class'] = cls
        out['error'] = get_error_message(e)
        out['sqlstate'] = get_sqlstate(e) or None
        out['mode'] = 'rolled_back'
    finally:
        out['duration_ms'] = int((time.time() - start) * 1000)
    return out


# ─────────────────────── summary rendering ───────────────────────

def _render_table(columns: list[str], rows: list[list[Any]]) -> str:
    """Render a markdown table; fall back to manual rendering if pandas/tabulate fails."""
    try:
        df = pd.DataFrame(rows, columns=columns)
        return df.to_markdown(index=False)
    except Exception:
        head = '| ' + ' | '.join(str(c) for c in columns) + ' |'
        sep = '|' + '|'.join(['---'] * len(columns)) + '|'
        body = '\n'.join('| ' + ' | '.join(str(v) for v in r) + ' |' for r in rows)
        return '\n'.join([head, sep, body])


def build_summary(stmts: list[dict], database: str, run_url: str | None,
                  truncate_for_comment: bool) -> str:
    """Render a list of statement results as a phone-friendly markdown summary.

    Each statement gets a section with status icon, commit/rollback icon,
    duration, row count, SQL block, and a result-table preview limited
    to the top ``SUMMARY_ROWS``. ``truncate_for_comment=True`` enforces
    the 60 KB issue-comment ceiling (GitHub's limit is 65 KB; the buffer
    leaves room for the "truncated" footer + workflow-run link). Pass
    False to get the full untruncated body for the artifact ``summary.md``.

    Returns the markdown string. Pure function — no I/O.
    """
    overall_ok = all(s['status'] == 'ok' for s in stmts)
    icon = '✅' if overall_ok else '❌'
    n = len(stmts)
    lines: list[str] = [
        f"## {icon} DB Query Results: `{database}` ({n} statement{'s' if n != 1 else ''})",
        '',
    ]
    for i, s in enumerate(stmts, 1):
        status_icon = {
            'ok': '✅',
            'user_error': '❌',
            'system_error': '💥',
        }.get(s['status'], 'ℹ️')
        mode_icon = {'rolled_back': '↩️', 'committed': '💾'}.get(s['mode'] or '', '')
        lines.append(f"### {status_icon} Statement {i}/{n} {mode_icon} {s['mode'] or ''}")
        lines.append('')
        lines.append(f"- **Duration**: {s['duration_ms']} ms")
        lines.append(f"- **Rows**: {s['row_count']}{' (truncated)' if s['truncated'] else ''}")
        if s['row_cap_strategy'] != 'none':
            lines.append(f"- **Row-cap strategy**: `{s['row_cap_strategy']}`")
        if s['sqlstate']:
            lines.append(f"- **SQLSTATE**: `{s['sqlstate']}`")
        lines.append('')
        lines.append('**SQL**')
        lines.append('```sql')
        lines.append(s['sql'].strip())
        lines.append('```')
        if s['error']:
            lines.append('')
            lines.append('**Error**')
            lines.append('```')
            lines.append(s['error'])
            lines.append('```')
        elif s['columns'] and s['rows']:
            lines.append('')
            lines.append(f"**Result preview** (first {min(SUMMARY_ROWS, len(s['rows']))} rows)")
            lines.append('')
            lines.append(_render_table(s['columns'], s['rows'][:SUMMARY_ROWS]))
            if len(s['rows']) > SUMMARY_ROWS:
                lines.append('')
                lines.append(f"_({len(s['rows']) - SUMMARY_ROWS} more rows in artifact)_")
        elif s['columns']:
            lines.append('')
            lines.append('_No rows returned._')
        lines.append('')
        lines.append('---')
        lines.append('')

    if run_url:
        lines.append(f"_Workflow run:_ {run_url}")

    body = '\n'.join(lines)
    if truncate_for_comment:
        encoded = body.encode('utf-8')
        if len(encoded) > COMMENT_BYTE_LIMIT:
            cut = encoded[:COMMENT_BYTE_LIMIT - 200].rsplit(b'\n', 1)[0].decode('utf-8', errors='ignore')
            body = cut + (
                '\n\n_Comment truncated at 60 KB. Full results in workflow artifact'
                + (f': {run_url}_' if run_url else '._')
            )
    return body


# ─────────────────────── main ───────────────────────

def _upload_dir_to_gcs(out_dir: Path, gcs_uri: str) -> None:
    """Upload every file in out_dir to ``gs://bucket/prefix/<filename>``.

    Used by the db-query Cloud Run Job so the dispatching sandbox session
    can fetch results via ``gcloud storage cp`` (port 443) instead of
    needing GitHub Actions artifact access.
    """
    if not gcs_uri.startswith('gs://'):
        raise ValueError(f'--upload-to-gcs must start with gs:// (got {gcs_uri!r})')
    from google.cloud import storage  # local import — only when needed
    rest = gcs_uri[len('gs://'):]
    bucket_name, _, prefix = rest.partition('/')
    prefix = prefix.rstrip('/')
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    for fp in sorted(out_dir.iterdir()):
        if not fp.is_file():
            continue
        blob_name = f'{prefix}/{fp.name}' if prefix else fp.name
        bucket.blob(blob_name).upload_from_filename(str(fp))
        print(f'uploaded {fp.name} → gs://{bucket_name}/{blob_name}')


def main() -> int:
    ap = argparse.ArgumentParser(description='Run SQL and emit summary artifacts.')
    ap.add_argument('--sql', default='', help='Inline SQL (multi-statement OK separated by ;).')
    ap.add_argument('--sql-file', default='', help='Path to .sql file (sent as one statement).')
    ap.add_argument('--commit', action='store_true', help='Commit transactions; default rollback.')
    ap.add_argument('--statement-timeout-seconds', type=int, default=120)
    ap.add_argument('--output-dir', default='.', help='Where to write artifacts.')
    ap.add_argument('--run-url', default='', help='Workflow run URL for summary footer.')
    ap.add_argument('--upload-to-gcs', default='',
                    help='gs://bucket/prefix to upload every artifact file to '
                         'after the run completes. Used by the db-query Cloud Run Job.')
    args = ap.parse_args()

    if bool(args.sql) == bool(args.sql_file):
        print('error: provide exactly one of --sql / --sql-file', file=sys.stderr)
        return 2

    if args.sql_file:
        path = Path(args.sql_file)
        if not path.is_file():
            print(f'error: sql_file does not exist: {path}', file=sys.stderr)
            return 2
        statements = [path.read_text(encoding='utf-8')]  # single-statement, no splitting
    else:
        statements = [
            s.strip() for s in sqlparse.split(args.sql)
            if s and s.strip().rstrip(';').strip()
        ]
        if not statements:
            print('error: no executable statements in --sql', file=sys.stderr)
            return 2

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    database = os.environ.get('DB_NAME', 'unknown')

    results: list[dict] = []
    saw_system_error = False

    try:
        engine = get_engine()
        with engine.connect() as conn:
            for stmt in statements:
                r = execute_statement(conn, stmt, args.commit, args.statement_timeout_seconds)
                results.append(r)
                if r['status'] == 'system_error':
                    saw_system_error = True
                    print(f'system error encountered, halting batch: {r["error"]}', file=sys.stderr)
                    break
    except (SQLAlchemyError, RuntimeError, ImportError) as e:
        # Engine creation / connection setup failure. Synthesize a result row
        # so the artifact + summary still get written for the failure-handler.
        cls = classify_error(e) if isinstance(e, SQLAlchemyError) else 'system'
        results.append({
            'sql': '<connection setup>',
            'status': 'system_error' if cls == 'system' else 'user_error',
            'mode': 'rolled_back',
            'columns': [], 'rows': [], 'row_count': 0, 'truncated': False,
            'duration_ms': 0,
            'error': get_error_message(e),
            'error_class': cls,
            'sqlstate': get_sqlstate(e) or None,
            'row_cap_strategy': 'none',
        })
        saw_system_error = (cls == 'system')

    # Per-statement CSVs (only when rows were returned)
    for i, r in enumerate(results, 1):
        if r['columns'] and r['rows']:
            csv_path = out_dir / f'result_{i:03d}.csv'
            with csv_path.open('w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(r['columns'])
                for row in r['rows']:
                    w.writerow(row)

    # Structured JSON
    payload = {
        'database': database,
        'commit_mode': bool(args.commit),
        'statement_count': len(results),
        'system_error': saw_system_error,
        'results': results,
    }
    (out_dir / 'results.json').write_text(
        json.dumps(payload, indent=2, default=str), encoding='utf-8'
    )

    # Summaries: full + truncated-for-comment
    full = build_summary(results, database, args.run_url or None, truncate_for_comment=False)
    (out_dir / 'summary.md').write_text(full, encoding='utf-8')

    short = build_summary(results, database, args.run_url or None, truncate_for_comment=True)
    (out_dir / 'summary_for_comment.md').write_text(short, encoding='utf-8')

    statuses = [r['status'] for r in results]
    print(f'done: {len(results)} statements, statuses={statuses}, system_error={saw_system_error}')

    if args.upload_to_gcs:
        try:
            _upload_dir_to_gcs(out_dir, args.upload_to_gcs)
        except Exception as e:
            # Treat upload failure as a system error so the caller knows
            # the artifacts didn't reach GCS (without it, the sandbox has
            # no way to retrieve results).
            print(f'GCS upload failed: {e!r}', file=sys.stderr)
            return 1

    return 1 if saw_system_error else 0


if __name__ == '__main__':
    sys.exit(main())
