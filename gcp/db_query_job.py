#!/usr/bin/env python3
"""Cloud Run Job entrypoint for ad-hoc SQL execution against Cloud SQL.

Functional twin of ``.github/workflows/db-query.yml``, but runs entirely in
GCP — no GitHub Actions runner required. Designed for sandbox sessions
(Claude Code on the web) whose outbound network policy only allows
TCP/443. The sandbox dispatches via ``gcloud run jobs execute`` (443),
the job runs in GCP with full Cloud SQL access, and results land in
GCS for ``gcloud storage cp`` retrieval (also 443).

Inputs (Cloud Run env vars):
    SQL                         Inline SQL, multi-statement ok separated by ;.
                                Mutually exclusive with SQL_FILE.
    SQL_FILE                    Path to .sql file in the image at ``gcp/queries/``.
                                Sent as ONE statement (no splitting).
                                Mutually exclusive with SQL.
    COMMIT                      'true' to commit writes; default rollback.
    STATEMENT_TIMEOUT_SECONDS   Per-statement timeout (default 120).
    RESULT_GCS_URI              gs://bucket/prefix where artifacts land.
                                If empty, defaults to
                                ``gs://${GCS_BUCKET}/query-results/${EXECUTION_ID}/``
                                using the Cloud Run-injected EXECUTION_NAME / GCS_BUCKET.

Exit codes:
    0  every statement succeeded or failed with a USER error (syntax,
       constraint, statement_timeout). Caller inspects results.json.
    1  SYSTEM error (auth, connection lost, GCS upload failed).
    2  invalid invocation.

Usage from a sandbox:

    EXEC=$(gcloud run jobs execute db-query \\
        --update-env-vars="SQL=SELECT 1, RESULT_GCS_URI=gs://my-bucket/q/test/" \\
        --region=us-east1 --project=$PROJECT --wait --format='value(metadata.name)')
    gcloud storage cp gs://my-bucket/q/test/results.json /tmp/
    cat /tmp/results.json
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_DEFAULT_BUCKET = os.environ.get(
    'GCS_BUCKET', f"{os.environ.get('GCP_PROJECT', 'adept-mountain-474619-d4')}-trading-data"
)
_DEFAULT_PREFIX = 'query-results'


def _resolve_result_uri() -> str:
    explicit = os.environ.get('RESULT_GCS_URI', '').strip()
    if explicit:
        return explicit.rstrip('/')
    # Cloud Run injects CLOUD_RUN_EXECUTION (job execution name) into the env.
    # Falls back to TASK_INDEX if not set (rare; only seen in local emulation).
    exec_id = (
        os.environ.get('CLOUD_RUN_EXECUTION')
        or os.environ.get('CLOUD_RUN_JOB_EXECUTION')
        or os.environ.get('K_REVISION')
        or f"local-{os.getpid()}"
    )
    return f"gs://{_DEFAULT_BUCKET}/{_DEFAULT_PREFIX}/{exec_id}"


def main() -> int:
    sql = os.environ.get('SQL', '').strip()
    sql_file = os.environ.get('SQL_FILE', '').strip()
    commit = os.environ.get('COMMIT', 'false').strip().lower() == 'true'
    timeout = os.environ.get('STATEMENT_TIMEOUT_SECONDS', '120').strip() or '120'

    if bool(sql) == bool(sql_file):
        print('error: provide exactly one of SQL / SQL_FILE env var', file=sys.stderr)
        return 2

    gcs_uri = _resolve_result_uri()
    out_dir = Path('/tmp/query-results')
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, '-m', 'gcp.queries.run_query',
        '--output-dir', str(out_dir),
        '--statement-timeout-seconds', timeout,
        '--upload-to-gcs', gcs_uri,
    ]
    if commit:
        cmd.append('--commit')
    if sql_file:
        cmd.extend(['--sql-file', sql_file])
    else:
        cmd.extend(['--sql', sql])

    print(f'db-query: dispatching run_query  → results will land at {gcs_uri}/')
    # Pass-through env (run_query reads DB_NAME etc. directly from os.environ).
    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
