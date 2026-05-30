"""Cloud Run Job entrypoint: ad-hoc DB query → GCS results.

Replaces the GitHub Actions `db-query.yml` workflow with a CR-native
path. Same `gcp/queries/run_query.py` runner does the actual SQL
execution; this module wires it for CR Job invocation:

  - SQL comes from env vars (overridable at execute time via
    `gcloud run jobs execute db-query --update-env-vars=DB_QUERY_SQL=...`)
  - Output written to a temp dir, then uploaded to GCS at a
    deterministic per-execution prefix
  - Exit code mirrors run_query's contract (0 user-error, 1 system-error,
    2 invocation-error)

Sandbox dispatch pattern (works over 443):

  gcloud run jobs execute db-query \\
    --region=us-east1 --wait \\
    --update-env-vars="DB_QUERY_SQL=SELECT count(*) FROM trades,DB_QUERY_LABEL=trade-count"

Then read the result from GCS:

  EXEC=$(gcloud beta run jobs executions list --job=db-query \\
    --region=us-east1 --limit=1 --format='value(name)')
  gcloud storage cat "gs://${PROJECT_ID}-trading-data/query-results/${EXEC}/summary.md"

Why CR-native:
  - The GHA db-query.yml has been unavailable since 2026-05-29 (GHA-side
    setup failure across all repo workflows). The Cloud SQL connector
    works perfectly fine from a CR Job; we just hadn't built the
    sandbox-friendly dispatch layer.
  - Future-proofs against GHA quota / billing / outage.
  - Same psycopg2/pg8000 connector code in the same Python image.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def _gcs_upload(local_dir: Path, bucket: str, prefix: str) -> None:
    """Upload every file under local_dir to gs://bucket/prefix/.

    Uses the python google-cloud-storage client because gsutil is not
    in the CR base image."""
    from google.cloud import storage as gcs
    client = gcs.Client()
    b = client.bucket(bucket)
    for p in local_dir.iterdir():
        if not p.is_file():
            continue
        blob_path = f"{prefix.rstrip('/')}/{p.name}"
        ctype = "text/markdown" if p.suffix == ".md" else (
            "application/json" if p.suffix == ".json" else (
                "text/csv" if p.suffix == ".csv" else "application/octet-stream"
            )
        )
        b.blob(blob_path).upload_from_filename(str(p), content_type=ctype)
        log.info("uploaded %s -> gs://%s/%s", p.name, bucket, blob_path)


def main() -> int:
    sql = os.environ.get("DB_QUERY_SQL", "")
    sql_file = os.environ.get("DB_QUERY_SQL_FILE", "")
    commit = os.environ.get("DB_QUERY_COMMIT", "").lower() in ("1", "true", "yes")
    timeout_s = int(os.environ.get("DB_QUERY_TIMEOUT_SECONDS", "120"))
    bucket = os.environ.get(
        "GCS_BUCKET",
        f"{os.environ.get('PROJECT_ID', 'adept-mountain-474619-d4')}-trading-data",
    )
    # Per-execution prefix — Cloud Run sets CLOUD_RUN_EXECUTION on every run.
    exec_id = os.environ.get("CLOUD_RUN_EXECUTION") or os.environ.get(
        "DB_QUERY_LABEL", "ad-hoc"
    )
    prefix = f"query-results/{exec_id}"

    if not sql and not sql_file:
        log.error("provide DB_QUERY_SQL or DB_QUERY_SQL_FILE env var")
        return 2
    if sql and sql_file:
        log.error("provide DB_QUERY_SQL OR DB_QUERY_SQL_FILE, not both")
        return 2

    tmp_dir = Path(tempfile.mkdtemp(prefix="db-query-"))
    try:
        # Build run_query.py argv
        argv = [
            sys.executable, "-m", "gcp.queries.run_query",
            "--output-dir", str(tmp_dir),
            "--statement-timeout-seconds", str(timeout_s),
            "--run-url", f"cloud-run-job/{exec_id}",
        ]
        if commit:
            argv.append("--commit")
        if sql_file:
            argv += ["--sql-file", sql_file]
        else:
            argv += ["--sql", sql]

        log.info("dispatching: %s", " ".join(argv[:4]) + " --sql=<%d chars>" % len(sql or ''))
        result = subprocess.run(argv, check=False)
        rc = result.returncode

        # Upload everything in tmp_dir → GCS regardless of exit code
        # (so user errors still produce visible summary artifacts)
        _gcs_upload(tmp_dir, bucket, prefix)
        log.info("results at: gs://%s/%s/", bucket, prefix)
        return rc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
